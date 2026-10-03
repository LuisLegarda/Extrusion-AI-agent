"""Problemas de proceso (monitor): captura de causas de paro y de problemas de calidad, y su análisis.

Captura: la línea de tiempo muestra el estado de la máquina; al elegir un paro se propone su rango
(la parte aún sin causa) y se ajusta con las barras de inicio y fin. Cada tramo guardado con su causa
queda clasificado; si un paro tuvo varias causas se capturan varios tramos.
"""
from __future__ import annotations

import time
from typing import Optional

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QButtonGroup, QComboBox, QDialog, QDoubleSpinBox, QFormLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit,
    QListWidget, QListWidgetItem, QMessageBox, QPushButton, QRadioButton, QSlider, QTabWidget, QVBoxLayout, QWidget,
)

from ..analysis.oee import shift_start
from ..analysis.problems import free_spans, machine_intervals, stop_events
from ..i18n import tr
from . import theme
from .problems_widgets import ProblemsAnalysis, TimelineSelect, fmt_min

PERIODS = [("Turno actual", 0), ("Últimas 8 h", 8 * 3600), ("Últimas 24 h", 86400), ("Últimos 7 días", 7 * 86400)]
ANALYSIS_PERIODS = [("Turno actual", 0), ("Últimas 24 h", 86400), ("Últimos 7 días", 7 * 86400),
                    ("Últimos 30 días", 30 * 86400), ("Últimos 90 días", 90 * 86400)]
STEP_S = 10  # resolución de las barras de inicio y fin


def hm(ts: float) -> str:
    return time.strftime("%H:%M:%S", time.localtime(ts))


class CapturePanel(QWidget):
    saved = Signal()

    def __init__(self, ctx):
        super().__init__()
        self.ctx = ctx
        self.engine = ctx.engine
        self.a = self.b = 0.0
        self.events: list = []
        self.records: list[dict] = []
        self._syncing = False
        lay = QVBoxLayout(self)

        bar = QHBoxLayout()
        bar.addWidget(QLabel("Periodo:"))
        self.cmb_period = QComboBox()
        for label, secs in PERIODS:
            self.cmb_period.addItem(label, secs)
        self.cmb_period.currentIndexChanged.connect(lambda _: self.refresh())
        bar.addWidget(self.cmb_period)
        b = QPushButton("⟳ Actualizar")
        b.clicked.connect(lambda: self.refresh())
        bar.addWidget(b)
        bar.addStretch(1)
        legend = QLabel(tr("Clic en un paro (rojo) para seleccionarlo; arrastra las manijas o usa las barras para "
                           "ajustar el inicio y el fin."))
        legend.setStyleSheet(f"color:{theme.c('muted')};")
        bar.addWidget(legend)
        lay.addLayout(bar)

        self.timeline = TimelineSelect()
        self.timeline.stopClicked.connect(self._stop_clicked)
        self.timeline.selectionChanged.connect(self._timeline_selection)
        lay.addWidget(self.timeline)

        body = QHBoxLayout()
        left = QVBoxLayout()
        self.lbl_pending = QLabel()
        self.lbl_pending.setTextFormat(Qt.RichText)
        left.addWidget(self.lbl_pending)
        self.lst = QListWidget()
        self.lst.currentRowChanged.connect(self._event_selected)
        left.addWidget(self.lst, 1)
        body.addLayout(left, 2)

        box = QGroupBox("Captura")
        form = QFormLayout(box)
        kinds = QHBoxLayout()
        self.rb_down = QRadioButton("Paro")
        self.rb_quality = QRadioButton("Problema de calidad")
        self.rb_down.setChecked(True)
        self.kind_group = QButtonGroup(self)
        for rb in (self.rb_down, self.rb_quality):
            self.kind_group.addButton(rb)
            kinds.addWidget(rb)
            rb.toggled.connect(lambda _: self._fill_categories())
        kinds.addStretch(1)
        form.addRow("Tipo:", kinds)
        self.sl_a, self.lbl_a = QSlider(Qt.Horizontal), QLabel("—")
        self.sl_b, self.lbl_b = QSlider(Qt.Horizontal), QLabel("—")
        for sl, lbl, name in ((self.sl_a, self.lbl_a, "Inicio:"), (self.sl_b, self.lbl_b, "Fin:")):
            row = QHBoxLayout()
            row.addWidget(sl, 1)
            lbl.setMinimumWidth(70)
            row.addWidget(lbl)
            sl.valueChanged.connect(self._slider_moved)
            form.addRow(name, row)
        self.lbl_dur = QLabel("—")
        form.addRow("Tiempo:", self.lbl_dur)
        self.cmb_cat = QComboBox()
        self.cmb_cat.currentIndexChanged.connect(self._fill_reasons)
        form.addRow("Categoría:", self.cmb_cat)
        self.cmb_reason = QComboBox()
        form.addRow("Causa / defecto:", self.cmb_reason)
        self.sp_scrap = QDoubleSpinBox()
        self.sp_scrap.setRange(0, 1e9)
        self.sp_scrap.setDecimals(1)
        form.addRow("Scrap:", self.sp_scrap)
        self.cmb_op = QComboBox()
        form.addRow("Operador:", self.cmb_op)
        self.ed_comment = QLineEdit()
        self.ed_comment.setPlaceholderText("opcional")
        form.addRow("Comentario:", self.ed_comment)
        self.btn_save = QPushButton("💾 Guardar captura")
        self.btn_save.clicked.connect(self.save)
        form.addRow(self.btn_save)
        self.lbl_status = QLabel()
        self.lbl_status.setWordWrap(True)
        form.addRow(self.lbl_status)
        body.addWidget(box, 3)
        lay.addLayout(body, 1)
        self.reload_config()

    # --- configuración -------------------------------------------------------------------
    @property
    def pcfg(self):
        return self.engine.config.problems

    def reload_config(self) -> None:
        self._fill_categories()
        self.cmb_op.clear()
        ops = self.pcfg.operators
        if not ops:
            self.cmb_op.addItem(tr("(sin operadores: agrégalos en Receta → Causas de paro y defectos)"), "")
        for op in ops:
            self.cmb_op.addItem(op, op)
        last = self.ctx.workspace.load_state().get("last_operator")
        idx = self.cmb_op.findData(last)
        if idx >= 0:
            self.cmb_op.setCurrentIndex(idx)
        self.sp_scrap.setSuffix(f" {self.engine.config.oee.length_unit}")

    def kind(self) -> str:
        return "downtime" if self.rb_down.isChecked() else "quality"

    def _fill_categories(self) -> None:
        cats = self.pcfg.downtime if self.kind() == "downtime" else self.pcfg.defects
        self.cmb_cat.blockSignals(True)
        self.cmb_cat.clear()
        for c in cats:
            self.cmb_cat.addItem(c.name + (tr(" (planeado)") if c.planned and self.kind() == "downtime" else ""), c.id)
        self.cmb_cat.blockSignals(False)
        self._fill_reasons()

    def _fill_reasons(self, *_):
        cat = self.pcfg.category(self.kind(), self.cmb_cat.currentData())
        self.cmb_reason.clear()
        for r in (cat.reasons if cat else []):
            self.cmb_reason.addItem(r.name, r.id)

    # --- datos ---------------------------------------------------------------------------
    def period(self, now: Optional[float] = None) -> tuple[float, float]:
        now = now or self.engine.clock()
        secs = self.cmb_period.currentData()
        a = shift_start(now, self.engine.config.oee.shift_starts) if not secs else now - secs
        return a, now

    def refresh(self, keep_selection: bool = True) -> None:
        hist = self.engine.historian
        if hist is None:
            return
        sel = self.timeline.sel if keep_selection else None
        self.a, self.b = self.period()
        intervals = machine_intervals(hist, self.engine.config, self.a, self.b)
        self.records = hist.problems(self.a, self.b)
        self.events = stop_events(intervals, self.records, min_s=0)
        self.timeline.set_data(self.a, self.b, intervals, self.records)
        span = max(1, int((self.b - self.a) / STEP_S))
        for sl in (self.sl_a, self.sl_b):
            sl.blockSignals(True)
            sl.setRange(0, span)
            sl.blockSignals(False)
        self._fill_events()
        if sel is not None:
            self.select_range(max(sel[0], self.a), min(sel[1], self.b), select_event=False)

    def _fill_events(self) -> None:
        self.lst.blockSignals(True)
        self.lst.clear()
        pending = [e for e in self.events if not e.classified]
        self.lbl_pending.setText(
            tr("<b>Paros del periodo</b> · <span style='color:{c}'>{n} sin clasificar</span>",
               c=theme.c("warning_text"), n=len(pending)) if pending else tr("<b>Paros del periodo</b> · todos clasificados"))
        for e in sorted(self.events, key=lambda e: (e.classified, -e.start)):
            mark = "✔" if e.classified else "●"
            text = (f"{mark} {time.strftime('%d/%m %H:%M', time.localtime(e.start))}–{hm(e.end)[:5]} · "
                    f"{fmt_min(e.duration / 60)}")
            if not e.classified:
                text += " · " + tr("sin causa: {m}", m=fmt_min(e.pending_s / 60))
            it = QListWidgetItem(text)
            it.setData(Qt.UserRole, (e.start, e.end))
            if not e.classified:
                it.setForeground(theme.qcolor("warning_text"))
            self.lst.addItem(it)
        self.lst.blockSignals(False)

    # --- selección -----------------------------------------------------------------------
    def _event_selected(self, row: int) -> None:
        it = self.lst.item(row)
        if it is not None:
            self._stop_clicked(*it.data(Qt.UserRole))

    def _stop_clicked(self, a: float, b: float) -> None:
        """Paro elegido: se propone la parte que aún no tiene causa (el primer tramo libre)."""
        self.rb_down.setChecked(True)
        ev = next((e for e in self.events if abs(e.start - a) < 1 and abs(e.end - b) < 1), None)
        spans = free_spans(ev) if ev is not None else [(a, b)]
        self.select_range(*(spans[0] if spans else (a, b)), select_event=False)

    def select_range(self, a: float, b: float, select_event: bool = True, kind: str = "downtime") -> None:
        if kind == "quality":
            self.rb_quality.setChecked(True)
        self._set_sliders(a, b)
        self.timeline.set_selection(a, b)
        self._show_range(a, b)

    def _set_sliders(self, a: float, b: float) -> None:
        self._syncing = True
        self.sl_a.setValue(int((a - self.a) / STEP_S))
        self.sl_b.setValue(int(round((b - self.a) / STEP_S)))
        self._syncing = False

    def _timeline_selection(self, a: float, b: float) -> None:
        self._set_sliders(a, b)
        self._show_range(a, b)

    def _slider_moved(self, _v: int) -> None:
        if self._syncing:
            return
        a = self.a + self.sl_a.value() * STEP_S
        b = self.a + self.sl_b.value() * STEP_S
        if b <= a:  # el fin nunca antes del inicio
            if self.sender() is self.sl_a:
                b = a + STEP_S
                self._set_sliders(a, b)
            else:
                a = b - STEP_S
                self._set_sliders(a, b)
        self.timeline.set_selection(a, b)
        self._show_range(a, b)

    def selection(self) -> Optional[tuple[float, float]]:
        return self.timeline.sel

    def _show_range(self, a: float, b: float) -> None:
        self.lbl_a.setText(hm(a))
        self.lbl_b.setText(hm(b))
        self.lbl_dur.setText(f"<b>{fmt_min((b - a) / 60)}</b> ({b - a:.0f} s)")

    # --- guardar -------------------------------------------------------------------------
    def save(self) -> Optional[dict]:
        sel = self.selection()
        kind = self.kind()
        cat = self.pcfg.category(kind, self.cmb_cat.currentData())
        reason = next((r for r in (cat.reasons if cat else []) if r.id == self.cmb_reason.currentData()), None)
        problems = []
        if sel is None or sel[1] - sel[0] < 1:
            problems.append(tr("Selecciona el rango de tiempo en la línea de tiempo."))
        if cat is None or reason is None:
            problems.append(tr("Elige la categoría y la causa (o el defecto)."))
        if self.pcfg.operators and not self.cmb_op.currentData():
            problems.append(tr("Elige el operador."))
        if problems:
            self.lbl_status.setText(f"<span style='color:{theme.c('critical')}'>{'<br>'.join(problems)}</span>")
            return None
        rec = {"kind": kind, "start": sel[0], "end": sel[1], "category_id": cat.id, "category": cat.name,
               "reason_id": reason.id, "reason": reason.name, "planned": cat.planned and kind == "downtime",
               "scrap": self.sp_scrap.value(), "unit": self.engine.config.oee.length_unit,
               "operator": self.cmb_op.currentData() or "", "comment": self.ed_comment.text().strip(),
               "recipe": self.engine.state.recipe}
        rec = self.engine.historian.add_problem(rec)
        if self.ctx.exporter is not None:
            self.ctx.exporter.queue_problem("add", rec)
        if rec["planned"]:
            self.engine.kpis_ts = None  # un paro planeado cambia el OEE: se recalcula en el siguiente ciclo
        state = self.ctx.workspace.load_state()
        state["last_operator"] = rec["operator"]
        self.ctx.workspace.save_state(state)
        self.sp_scrap.setValue(0)
        self.ed_comment.clear()
        self.lbl_status.setText(f"<span style='color:{theme.c('good_text')}'>"
                                + tr("✔ Guardado: {r} · {m}", r=reason.name, m=fmt_min(rec["duration_s"] / 60))
                                + "</span>")
        self.timeline.set_selection(None, None)
        self.refresh(keep_selection=False)
        # Si el paro aún tiene una parte sin causa, se propone para el siguiente tramo.
        ev = next((e for e in self.events if e.start <= sel[0] < e.end and not e.classified), None)
        if ev is not None and kind == "downtime":
            spans = free_spans(ev)
            if spans:
                self.select_range(*spans[0])
        self.saved.emit()
        return rec


class ProblemsPage(QWidget):
    """Página «Problemas de proceso»: captura y análisis (Pareto de paros y de defectos)."""

    pendingChanged = Signal(int)

    def __init__(self, ctx):
        super().__init__()
        self.ctx = ctx
        self.engine = ctx.engine
        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 0, 4, 0)
        self.tabs = QTabWidget()
        self.capture = CapturePanel(ctx)
        self.capture.saved.connect(self._after_save)
        self.tabs.addTab(self.capture, "📝 Capturar")
        analysis = QWidget()
        al = QVBoxLayout(analysis)
        bar = QHBoxLayout()
        bar.addWidget(QLabel("Periodo:"))
        self.cmb_period = QComboBox()
        for label, secs in ANALYSIS_PERIODS:
            self.cmb_period.addItem(label, secs)
        self.cmb_period.setCurrentIndex(2)
        self.cmb_period.currentIndexChanged.connect(lambda _: self.refresh_analysis())
        bar.addWidget(self.cmb_period)
        bar.addStretch(1)
        al.addLayout(bar)
        self.analysis = ProblemsAnalysis(can_delete=True)
        self.analysis.deleteRequested.connect(self.delete)
        al.addWidget(self.analysis, 1)
        self.tabs.addTab(analysis, "📊 Análisis (Pareto)")
        self.tabs.currentChanged.connect(lambda _: self.refresh())
        lay.addWidget(self.tabs)
        self.pending = 0
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(30000)

    def _tick(self) -> None:
        if self.isVisible():
            self.refresh()
        else:
            self.count_pending()

    def refresh(self) -> None:
        if self.tabs.currentIndex() == 0:
            self.capture.refresh()
        else:
            self.refresh_analysis()
        self.count_pending()

    def refresh_analysis(self) -> None:
        hist = self.engine.historian
        if hist is None:
            return
        now = self.engine.clock()
        secs = self.cmb_period.currentData()
        a = shift_start(now, self.engine.config.oee.shift_starts) if not secs else now - secs
        records = hist.problems(a, now)
        events = stop_events(machine_intervals(hist, self.engine.config, a, now), records,
                             min_s=self.engine.config.problems.prompt_min_s)
        self.analysis.set_data(records, events, self.engine.config.oee.length_unit)

    def count_pending(self) -> int:
        """Paros del turno (de al menos el tiempo del aviso) que aún no tienen causa."""
        hist = self.engine.historian
        if hist is None or not self.engine.config.oee.enabled:
            n = 0
        else:
            now = self.engine.clock()
            a = shift_start(now, self.engine.config.oee.shift_starts)
            evs = stop_events(machine_intervals(hist, self.engine.config, a, now), hist.problems(a, now),
                              min_s=self.engine.config.problems.prompt_min_s)
            n = sum(not e.classified for e in evs)
        if n != self.pending:
            self.pending = n
            self.pendingChanged.emit(n)
        return n

    def _after_save(self) -> None:
        self.count_pending()

    def delete(self, pid: int) -> None:
        if QMessageBox.question(self, tr("Eliminar"), tr("¿Eliminar la captura seleccionada?")) != QMessageBox.Yes:
            return
        rec = self.engine.historian.delete_problem(pid)
        if rec is not None and self.ctx.exporter is not None:
            self.ctx.exporter.queue_problem("del", rec)
        if rec is not None and rec.get("planned"):
            self.engine.kpis_ts = None
        self.refresh_analysis()
        self.count_pending()

    def classify(self, a: float, b: float) -> None:
        """Desde el aviso: abre la captura con ese paro seleccionado."""
        self.tabs.setCurrentIndex(0)
        self.capture.refresh(keep_selection=False)
        self.capture._stop_clicked(a, b)

    def reload_config(self) -> None:
        self.capture.reload_config()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        QTimer.singleShot(0, self.refresh)


class StopPrompt(QDialog):
    """Aviso al reanudar la línea: clasificar el paro ahora o dejarlo pendiente."""

    def __init__(self, a: float, b: float, on_classify, parent=None):
        super().__init__(None, Qt.Tool | Qt.WindowStaysOnTopHint)
        self.setWindowTitle(tr("Clasificar paro"))
        self.setAttribute(Qt.WA_DeleteOnClose)
        lay = QVBoxLayout(self)
        lbl = QLabel(tr("La línea estuvo detenida <b>{m}</b> ({a}–{b}).<br>¿Cuál fue la causa?",
                        m=fmt_min((b - a) / 60), a=hm(a)[:5], b=hm(b)[:5]))
        lbl.setTextFormat(Qt.RichText)
        lay.addWidget(lbl)
        row = QHBoxLayout()
        go = QPushButton(tr("📝 Clasificar ahora"))
        go.setDefault(True)
        go.clicked.connect(lambda: (self.close(), on_classify(a, b)))
        later = QPushButton(tr("Después"))
        later.setToolTip(tr("Queda en la lista de paros sin clasificar"))
        later.clicked.connect(self.close)
        row.addWidget(go)
        row.addWidget(later)
        lay.addLayout(row)
