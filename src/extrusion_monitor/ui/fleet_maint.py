"""Dashboard global → Mantenimiento: administrador de preventivos y correctivos (solo lectura).

El dashboard no captura nada: lee los paros que registran los monitores, los clasifica como mantenimiento
preventivo o correctivo (por categoría y causa; ajustable en «Clasificación») y muestra indicadores, el estado de
cada línea (hace cuánto fue su último preventivo y correctivo) y la lista de registros.
"""
from __future__ import annotations

import time
from pathlib import Path

import pyqtgraph as pg
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QFrame, QGridLayout, QHBoxLayout, QHeaderView, QLabel,
    QLineEdit, QPushButton, QScrollArea, QTableWidget, QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget,
)

from ..analysis.maintenance import MaintSummary, run_hours, summarize_maintenance  # noqa: F401 (run_hours: pruebas)
from ..fleet import read_problems
from ..fleet_data import FleetHistorian
from ..i18n import tr
from ..plant_settings import MAINT_KINDS, PlantSettings
from . import theme
from .fleet_analyzer import fit_height

PERIODS = [("Últimos 30 días", 30 * 86400), ("Últimos 90 días", 90 * 86400), ("Últimos 7 días", 7 * 86400),
           ("Último año", 365 * 86400)]
KIND_STYLE = {"preventive": ("Preventivo", "#1f4e79"), "corrective": ("Correctivo", "#d9822b")}
STATE_STYLE = {"ok": ("🟢", "al día", "good_text"), "soon": ("🟡", "próximo", "warning_text"),
               "late": ("🔴", "atrasado", "critical"), "none": ("⚪", "sin preventivo", "muted")}


def _ago(days) -> str:
    if days is None:
        return "—"
    if days < 1:
        return tr("hace {h} h", h=f"{days * 24:.0f}")
    return tr("hace {d} días", d=f"{days:.0f}")


class KpiCard(QFrame):
    """Tarjeta como las de un tablero de técnico: título arriba, valor grande al centro."""

    def __init__(self, title: str, sub: str = ""):
        super().__init__()
        self.setObjectName("card")
        self.setMinimumHeight(130)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        t = QLabel(f"<b style='color:{theme.c('title')}'>{title.upper()}</b>")
        t.setAlignment(Qt.AlignCenter)
        t.setWordWrap(True)
        lay.addWidget(t)
        self.sub = QLabel(sub)
        self.sub.setAlignment(Qt.AlignCenter)
        self.sub.setStyleSheet(f"color:{theme.c('muted')}; font-size:11px;")
        lay.addWidget(self.sub)
        self.value = QLabel("—")
        self.value.setAlignment(Qt.AlignCenter)
        lay.addWidget(self.value, 1)

    def set(self, text: str, color: str = "", sub: str = "") -> None:
        self.value.setText(f"<span style='font-size:32px; color:{color or theme.c('text')}'>{text}</span>")
        if sub:
            self.sub.setText(sub)


class ClassifyDialog(QDialog):
    """Qué categorías / causas son mantenimiento preventivo o correctivo, y cada cuánto toca preventivo."""

    def __init__(self, home: Path, keys: list[str], lines: list[str], parent=None):
        super().__init__(parent)
        self.home = Path(home)
        self.s = PlantSettings.load(home)
        self.setWindowTitle(tr("Clasificación de mantenimiento"))
        self.resize(760, 560)
        root = QVBoxLayout(self)
        tabs = QTabWidget()
        root.addWidget(tabs, 1)
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.addWidget(QLabel(tr("Paros capturados en los monitores: elige cuáles son mantenimiento preventivo o "
                                "correctivo. «Automático» decide por palabras como «preventivo», «limpieza», "
                                "«calibración» (preventivo) o «falla», «reparación», «mantenimiento» (correctivo).")))
        lay.itemAt(0).widget().setWordWrap(True)
        self.tbl = QTableWidget(len(keys), 2)
        self.tbl.setHorizontalHeaderLabels([tr("Categoría › causa"), tr("Tipo")])
        self.tbl.verticalHeader().setVisible(False)
        self.tbl.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.tbl.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.combos = {}
        for r, key in enumerate(keys):
            self.tbl.setItem(r, 0, QTableWidgetItem(key))
            cmb = QComboBox()
            cmb.addItem(tr("Automático"), "")
            for k, lb in MAINT_KINDS.items():
                cmb.addItem(tr(lb), k)
            cmb.setCurrentIndex(max(0, cmb.findData(self.s.maint_rules.get(key, ""))))
            self.tbl.setCellWidget(r, 1, cmb)
            self.combos[key] = cmb
        lay.addWidget(self.tbl, 1)
        tabs.addTab(w, tr("Tipos de paro"))
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.addWidget(QLabel(tr("Cada cuántos días le toca preventivo a cada línea (para marcar «próximo» al 80 % y "
                                "«atrasado» al pasarse).")))
        self.sp_default = QDoubleSpinBox()
        self.sp_default.setRange(1, 3650)
        self.sp_default.setSuffix(" " + tr("días"))
        self.sp_default.setValue(self.s.default_pm_days)
        row = QHBoxLayout()
        row.addWidget(QLabel(tr("Todas las líneas")))
        row.addWidget(self.sp_default)
        row.addStretch(1)
        lay.addLayout(row)
        self.tbl_l = QTableWidget(len(lines), 2)
        self.tbl_l.setHorizontalHeaderLabels([tr("Línea"), tr("Días (0 = el de todas)")])
        self.tbl_l.verticalHeader().setVisible(False)
        self.tbl_l.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.days = {}
        for r, ln in enumerate(lines):
            self.tbl_l.setItem(r, 0, QTableWidgetItem(ln))
            sp = QDoubleSpinBox()
            sp.setRange(0, 3650)
            sp.setValue(self.s.pm_days.get(ln, 0.0))
            self.tbl_l.setCellWidget(r, 1, sp)
            self.days[ln] = sp
        lay.addWidget(self.tbl_l, 1)
        row = QHBoxLayout()
        row.addWidget(QLabel(tr("Líneas sin monitor todavía (separadas por coma):")))
        self.ed_extra = QLineEdit(", ".join(self.s.extra_lines))
        row.addWidget(self.ed_extra, 1)
        lay.addLayout(row)
        tabs.addTab(w, tr("Frecuencia de preventivo"))
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText(tr("Guardar"))
        bb.button(QDialogButtonBox.Cancel).setText(tr("Cancelar"))
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        root.addWidget(bb)

    def accept(self) -> None:
        s = PlantSettings.load(self.home)
        for key, cmb in self.combos.items():
            if cmb.currentData():
                s.maint_rules[key] = cmb.currentData()
            else:
                s.maint_rules.pop(key, None)
        s.default_pm_days = self.sp_default.value()
        s.pm_days = {ln: sp.value() for ln, sp in self.days.items() if sp.value() > 0}
        s.extra_lines = [x.strip() for x in self.ed_extra.text().split(",") if x.strip()]
        s.save(self.home)
        super().accept()


class FleetMaintenance(QWidget):
    def __init__(self, reader_fn, home: Path, allow=None):
        super().__init__()
        self.reader_fn = reader_fn
        self.home = Path(home)
        self.summary: MaintSummary | None = None
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        bar = QHBoxLayout()
        bar.addWidget(QLabel(f"<b style='font-size:16px; color:{theme.c('title')}'>{tr('Mantenimiento')}</b>"))
        bar.addSpacing(16)
        bar.addWidget(QLabel(tr("Línea:")))
        self.cmb_line = QComboBox()
        self.cmb_line.setMinimumWidth(200)
        self.cmb_line.currentIndexChanged.connect(lambda _: self.refresh())
        bar.addWidget(self.cmb_line)
        bar.addWidget(QLabel(tr("Periodo:")))
        self.cmb_period = QComboBox()
        for label, secs in PERIODS:
            self.cmb_period.addItem(tr(label), secs)
        self.cmb_period.currentIndexChanged.connect(lambda _: self.refresh())
        bar.addWidget(self.cmb_period)
        b = QPushButton(tr("⚙ Clasificación…"))
        b.setToolTip(tr("Qué paros son preventivo o correctivo y cada cuánto toca preventivo"))
        b.clicked.connect(self.classify)
        bar.addWidget(b)
        bar.addStretch(1)
        lay.addLayout(bar)
        note = QLabel(tr("Solo lectura: los datos vienen de los paros que capturan los operadores en el monitor de cada "
                         "línea (Problemas de proceso)."))
        note.setStyleSheet(f"color:{theme.c('muted')}; font-size:11px;")
        lay.addWidget(note)
        self.area = QScrollArea()
        self.area.setWidgetResizable(True)
        self.area.setFrameShape(QFrame.NoFrame)
        lay.addWidget(self.area, 1)

    @property
    def line(self) -> str:
        return self.cmb_line.currentData() or ""

    def _names(self) -> list[str]:
        plant = PlantSettings.load(self.home)
        names = [ln.name for ln in sorted(self.reader_fn().lines.values(), key=lambda ln: ln.name)]
        return list(dict.fromkeys(names + plant.extra_lines))

    def _fill_lines(self) -> None:
        cur = self.cmb_line.currentData()
        self.cmb_line.blockSignals(True)
        self.cmb_line.clear()
        self.cmb_line.addItem(tr("Todas las líneas"), "")
        for n in self._names():  # aparecen solas: las que publican datos más las agregadas a mano
            self.cmb_line.addItem(n, n)
        self.cmb_line.setCurrentIndex(max(0, self.cmb_line.findData(cur)))
        self.cmb_line.blockSignals(False)

    def classify(self) -> None:
        keys = set()
        for ln in self.reader_fn().lines.values():
            for r in read_problems(ln, time.time() - 365 * 86400):
                if r.get("kind") == "downtime":
                    keys.add(f"{r.get('category') or ''} › {r.get('reason') or ''}")
                    keys.add(str(r.get("category") or ""))
        if ClassifyDialog(self.home, sorted(k for k in keys if k.strip(" ›")), self._names(), self).exec():
            self.refresh()

    def refresh(self) -> None:
        self._fill_lines()
        plant = PlantSettings.load(self.home)
        now = time.time()
        span = float(self.cmb_period.currentData() or 30 * 86400)
        s = self.summary = summarize_maintenance(FleetHistorian(self.reader_fn()), plant, now - span, now, self.line)
        body = QWidget()
        g = QGridLayout(body)
        g.setSpacing(10)
        n_lines = len([m for m in s.lines if m.has_data])
        cards = [
            (tr("Preventivos atrasados"), tr("Líneas")),
            (tr("Paros por mantenimiento"), tr("en el periodo")),
            (tr("Correctivos"), tr("eventos · horas")),
            (tr("Preventivos"), tr("eventos · horas")),
            (tr("Mantenimiento programado"), tr("% del tiempo de mantenimiento")),
            (tr("MTTR correctivo"), tr("duración promedio")),
            (tr("Desperdicio por mantenimiento"), tr("preventivo + correctivo")),
        ]
        widgets = [KpiCard(t, sub) for t, sub in cards]
        late = len(s.late)
        widgets[0].set(f"{late} <span style='font-size:16px'>{tr('de')} {n_lines}</span>",
                       theme.c("critical") if late else theme.c("good_text"))
        widgets[1].set(f"{int(s.total('n_prev') + s.total('n_corr'))}")
        widgets[2].set(f"{int(s.total('n_corr'))} · {s.total('min_corr') / 60:.1f} h", "#d9822b")
        widgets[3].set(f"{int(s.total('n_prev'))} · {s.total('min_prev') / 60:.1f} h", "#1f4e79")
        pm = s.pm_pct
        widgets[4].set("—" if pm is None else f"{pm:.0f} %",
                       "" if pm is None else (theme.c("good_text") if pm >= 70 else theme.c("warning_text")))
        widgets[5].set("—" if s.mttr_corr is None else f"{s.mttr_corr:.0f} min")
        scrap = s.total("scrap_prev") + s.total("scrap_corr")
        unit = next((e.unit for e in s.events if e.unit), "")
        widgets[6].set(f"{scrap:,.0f} <span style='font-size:14px'>{unit}</span>")
        for i, w in enumerate(widgets):
            g.addWidget(w, 0, i)
        g.addWidget(self._lines_table(s), 1, 0, 1, len(widgets))
        g.addWidget(self._chart(s), 2, 0, 1, len(widgets))
        g.addWidget(self._events_table(s), 3, 0, 1, len(widgets))
        g.setRowStretch(4, 1)
        self.area.setWidget(body)

    def _card(self, title: str) -> tuple[QFrame, QVBoxLayout]:
        fr = QFrame()
        fr.setObjectName("card")
        lay = QVBoxLayout(fr)
        lay.addWidget(QLabel(f"<b style='font-size:14px; color:{theme.c('title')}'>{title}</b>"))
        return fr, lay

    def _lines_table(self, s: MaintSummary) -> QFrame:
        fr, lay = self._card(tr("Estado por línea"))
        heads = [tr("Línea"), tr("Estado del preventivo"), tr("Último preventivo"), tr("Último correctivo"),
                 tr("Preventivos"), tr("Correctivos"), tr("MTTR correctivo"), tr("MTBF correctivo"),
                 tr("Desperdicio")]
        t = QTableWidget(len(s.lines), len(heads))
        t.setHorizontalHeaderLabels(heads)
        t.verticalHeader().setVisible(False)
        t.setEditTriggers(QTableWidget.NoEditTriggers)
        for r, m in enumerate(s.lines):
            icon, label, key = STATE_STYLE[m.state] if m.has_data else ("⚪", "sin datos", "muted")
            last_p = "—" if m.last_prev is None else time.strftime("%d/%m/%Y", time.localtime(m.last_prev)) + \
                f" ({_ago(m.days_since_prev)})"
            last_c = "—" if m.last_corr is None else time.strftime("%d/%m/%Y", time.localtime(m.last_corr)) + \
                f" ({_ago(m.days_since_corr)})"
            vals = [m.name, f"{icon} {tr(label)} · {tr('cada {d} d', d=f'{m.pm_days:.0f}')}", last_p, last_c, f"{m.n_prev} · {m.min_prev / 60:.1f} h",
                    f"{m.n_corr} · {m.min_corr / 60:.1f} h",
                    "—" if m.mttr_corr is None else f"{m.mttr_corr:.0f} min",
                    "—" if m.mtbf_corr is None else f"{m.mtbf_corr:.0f} h",
                    f"{m.scrap_prev + m.scrap_corr:,.0f}"]
            for c, v in enumerate(vals):
                it = QTableWidgetItem(v)
                if c >= 4:
                    it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                if c == 1:
                    it.setForeground(QColor(theme.c(key)))
                t.setItem(r, c, it)
        hh = t.horizontalHeader()
        hh.setSectionResizeMode(QHeaderView.ResizeToContents)  # el nombre de la línea completo
        hh.setStretchLastSection(True)
        fit_height(t)
        lay.addWidget(t)
        return fr

    def _chart(self, s: MaintSummary) -> QFrame:
        fr, lay = self._card(tr("Horas de mantenimiento por línea"))
        w = pg.PlotWidget()
        w.setMinimumHeight(220)
        w.setBackground(theme.c("plot_bg"))
        w.showGrid(x=False, y=True, alpha=0.2)
        w.setMouseEnabled(x=False, y=False)
        w.hideButtons()
        w.addLegend(offset=(-10, 10))
        names = [m.name for m in s.lines]
        prev = pg.BarGraphItem(x=list(range(len(names))), height=[m.min_prev / 60 for m in s.lines], width=0.6,
                               brush=pg.mkBrush(KIND_STYLE["preventive"][1]))
        corr = pg.BarGraphItem(x=list(range(len(names))), y0=[m.min_prev / 60 for m in s.lines],
                               height=[m.min_corr / 60 for m in s.lines], width=0.6,
                               brush=pg.mkBrush(KIND_STYLE["corrective"][1]))
        w.addItem(prev)
        w.addItem(corr)
        w.getPlotItem().legend.addItem(prev, tr("Preventivo"))
        w.getPlotItem().legend.addItem(corr, tr("Correctivo"))
        w.getAxis("bottom").setTicks([[(i, n) for i, n in enumerate(names)]])
        w.setLabel("left", tr("horas"))
        lay.addWidget(w)
        return fr

    def _events_table(self, s: MaintSummary) -> QFrame:
        events = s.events
        fr, lay = self._card(tr("Registros de mantenimiento ({n})", n=len(events)))
        heads = [tr("Fecha"), tr("Línea"), tr("Tipo"), tr("Categoría"), tr("Causa"), tr("Duración"),
                 tr("Desperdicio"), tr("Operador"), tr("Comentario")]
        t = QTableWidget(len(events), len(heads))
        t.setHorizontalHeaderLabels(heads)
        t.verticalHeader().setVisible(False)
        t.setEditTriggers(QTableWidget.NoEditTriggers)
        t.setAlternatingRowColors(True)
        for r, e in enumerate(events):
            label, color = KIND_STYLE[e.kind]
            vals = [time.strftime("%d/%m/%Y %H:%M", time.localtime(e.start)), e.line, tr(label), e.category,
                    e.reason, f"{e.minutes:.0f} min", f"{e.scrap:g} {e.unit}".strip() if e.scrap else "",
                    e.operator, e.comment]
            for c, v in enumerate(vals):
                it = QTableWidgetItem(v)
                if c == 2:
                    it.setBackground(QColor(color))
                    it.setForeground(QColor("#ffffff"))
                if c in (5, 6):
                    it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                t.setItem(r, c, it)
        hh = t.horizontalHeader()
        hh.setSectionResizeMode(QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(8, QHeaderView.Stretch)
        if len(events) <= 15:
            fit_height(t)
        else:
            t.setFixedHeight(520)
        lay.addWidget(t)
        if not events:
            lay.addWidget(QLabel(tr("Sin paros de mantenimiento en el periodo. Si los operadores los capturan con otro "
                                    "nombre, ajústalo en «⚙ Clasificación».")))
        return fr
