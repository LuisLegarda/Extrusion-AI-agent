"""Dashboard global → Mantenimiento: plan preventivo por horas de operación y fallas por causa (MTBF / MTTR)."""
from __future__ import annotations

import time
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QComboBox, QDoubleSpinBox, QFrame, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMessageBox,
    QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from ..analysis.plant import RUN_STATES, summarize
from ..fleet_data import FleetHistorian
from ..i18n import tr
from ..plant_settings import Equipment, PlantSettings
from . import theme
from .fleet_analyzer import fit_height

PERIODS = [("Últimos 30 días", 30 * 86400), ("Últimos 90 días", 90 * 86400), ("Últimos 7 días", 7 * 86400)]


def run_hours(rows: list[dict]) -> float:
    """Horas en marcha según el estado publicado cada minuto (o minutos con datos, en monitores anteriores)."""
    if any(r.get("s") for r in rows):
        return sum(min(300.0, max(0.0, r["ts"] - (r.get("from") or r["ts"] - 60))) / 3600
                   for r in rows if r.get("s") in RUN_STATES)
    return len(rows) / 60


def maintenance_status(hist: FleetHistorian, plant: PlantSettings, now: float) -> dict[str, list[dict]]:
    """Por línea: cada equipo con sus horas desde el último servicio, avance y estado."""
    out: dict[str, list[dict]] = {}
    for line, items in plant.equipment.items():
        hist.line = line
        rows_cache: dict[float, float] = {}
        res = []
        for e in items:
            since = e.last_service or now - 30 * 86400
            if since not in rows_cache:
                rows_cache[since] = run_hours(hist.rows_by_line(since, now).get(line, []))
            h = rows_cache[since]
            pct = 100 * h / e.interval_h if e.interval_h else 0.0
            state = "due" if pct >= 100 else ("soon" if pct >= 80 else "ok")
            res.append({"equipment": e, "hours": h, "pct": pct, "state": state})
        out[line] = res
    hist.line = ""
    return out


class FleetMaintenance(QWidget):
    def __init__(self, reader_fn, home: Path, allow=None):
        super().__init__()
        self.reader_fn = reader_fn
        self.home = Path(home)
        self.allow = allow or (lambda _k: True)
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
        bar.addWidget(QLabel(tr("Fallas en:")))
        self.cmb_period = QComboBox()
        for label, secs in PERIODS:
            self.cmb_period.addItem(tr(label), secs)
        self.cmb_period.currentIndexChanged.connect(lambda _: self.refresh())
        bar.addWidget(self.cmb_period)
        bar.addStretch(1)
        lay.addLayout(bar)

        card = QFrame()
        card.setObjectName("card")
        cl = QVBoxLayout(card)
        cl.addWidget(QLabel(f"<b style='font-size:14px; color:{theme.c('title')}'>"
                            f"{tr('Plan preventivo por horas de operación')}</b>"))
        self.tbl = QTableWidget(0, 7)
        self.tbl.setHorizontalHeaderLabels([tr("Equipo / componente"), tr("Cada (h de operación)"),
                                            tr("Horas desde el servicio"), tr("Avance"), tr("Estado"),
                                            tr("Último servicio"), tr("Nota")])
        self.tbl.verticalHeader().setVisible(False)
        self.tbl.setEditTriggers(QTableWidget.NoEditTriggers)
        hh = self.tbl.horizontalHeader()
        hh.setSectionResizeMode(QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(0, QHeaderView.Stretch)
        hh.setSectionResizeMode(6, QHeaderView.Stretch)
        cl.addWidget(self.tbl)
        row = QHBoxLayout()
        for text, slot in ((tr("+ Equipo"), self.add), (tr("✔ Servicio hecho"), self.serviced),
                           (tr("✎ Cambiar"), self.edit), (tr("Quitar"), self.remove)):
            b = QPushButton(text)
            b.clicked.connect(slot)
            row.addWidget(b)
        row.addStretch(1)
        cl.addLayout(row)
        note = QLabel(tr("Las horas cuentan solo el tiempo en marcha que publica el monitor de la línea. Al llegar al "
                         "80 % se marca en amarillo y al 100 % en rojo."))
        note.setWordWrap(True)
        note.setStyleSheet(f"color:{theme.c('muted')}; font-size:11px;")
        cl.addWidget(note)
        lay.addWidget(card)

        card = QFrame()
        card.setObjectName("card")
        cl = QVBoxLayout(card)
        cl.addWidget(QLabel(f"<b style='font-size:14px; color:{theme.c('title')}'>"
                            f"{tr('Fallas por causa (paros capturados)')}</b>"))
        self.tbl_f = QTableWidget(0, 5)
        self.tbl_f.setHorizontalHeaderLabels([tr("Causa"), tr("Eventos"), tr("Minutos"), "MTTR", "MTBF"])
        self.tbl_f.verticalHeader().setVisible(False)
        self.tbl_f.setEditTriggers(QTableWidget.NoEditTriggers)
        hh = self.tbl_f.horizontalHeader()
        hh.setSectionResizeMode(QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(0, QHeaderView.Stretch)
        cl.addWidget(self.tbl_f)
        self.lbl_f = QLabel("")
        self.lbl_f.setWordWrap(True)
        cl.addWidget(self.lbl_f)
        lay.addWidget(card)
        lay.addStretch(1)

    @property
    def line(self) -> str:
        return self.cmb_line.currentData() or ""

    def _fill_lines(self) -> None:
        cur = self.cmb_line.currentData()
        names = [ln.name for ln in sorted(self.reader_fn().lines.values(), key=lambda ln: ln.name)]
        self.cmb_line.blockSignals(True)
        self.cmb_line.clear()
        for n in names:
            self.cmb_line.addItem(n, n)
        self.cmb_line.setCurrentIndex(max(0, self.cmb_line.findData(cur)))
        self.cmb_line.blockSignals(False)

    def refresh(self) -> None:
        self._fill_lines()
        line = self.line
        plant = PlantSettings.load(self.home)
        now = time.time()
        hist = FleetHistorian(self.reader_fn())
        status = maintenance_status(hist, plant, now).get(line, [])
        self.tbl.setRowCount(len(status))
        colors = {"ok": theme.c("good_text"), "soon": theme.c("warning_text"), "due": theme.c("critical")}
        labels = {"ok": "🟢 " + tr("al día"), "soon": "🟡 " + tr("próximo"), "due": "🔴 " + tr("vencido")}
        for r, st in enumerate(status):
            e = st["equipment"]
            vals = [e.name, f"{e.interval_h:,.0f}", f"{st['hours']:,.1f}", f"{st['pct']:.0f} %", labels[st["state"]],
                    time.strftime("%d/%m/%Y", time.localtime(e.last_service)) if e.last_service else "—", e.note]
            for c, v in enumerate(vals):
                it = QTableWidgetItem(v)
                if c in (1, 2, 3):
                    it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                if c in (3, 4):
                    it.setForeground(QColor(colors[st["state"]]))
                self.tbl.setItem(r, c, it)
        fit_height(self.tbl)
        span = float(self.cmb_period.currentData() or 30 * 86400)
        hist.line = line
        s = summarize(hist, now - span, now, plant=plant)
        m = s.lines[0] if s.lines else None
        fails = sorted((m.failures if m else {}).items(), key=lambda kv: -kv[1]["min"])
        self.tbl_f.setRowCount(len(fails))
        for r, (cause, f) in enumerate(fails):
            vals = [cause, str(f["n"]), f"{f['min']:.0f}", "—" if f.get("mttr") is None else f"{f['mttr']:.0f} min",
                    "—" if f.get("mtbf") is None else f"{f['mtbf']:.1f} h"]
            for c, v in enumerate(vals):
                it = QTableWidgetItem(v)
                if c:
                    it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.tbl_f.setItem(r, c, it)
        fit_height(self.tbl_f)
        if fails:
            worst = min(fails, key=lambda kv: kv[1]["mtbf"] or 1e9)
            self.lbl_f.setText(tr("La falla más frecuente es «{c}»: ocurre cada {h} h de operación en promedio y tarda "
                                  "{m} min en resolverse. Es candidata a mantenimiento preventivo.", c=worst[0],
                                  h=f"{worst[1]['mtbf'] or 0:.1f}", m=f"{worst[1]['mttr'] or 0:.0f}"))
        else:
            self.lbl_f.setText(tr("Sin paros capturados en el periodo."))

    # --- edición del plan ---
    def _items(self, plant: PlantSettings) -> list[Equipment]:
        return plant.equipment.setdefault(self.line, [])

    def _row_dialog(self, e: Equipment) -> bool:
        from PySide6.QtWidgets import QDialog, QDialogButtonBox, QFormLayout
        dlg = QDialog(self)
        dlg.setWindowTitle(tr("Equipo / componente"))
        f = QFormLayout(dlg)
        ed = QLineEdit(e.name)
        sp = QDoubleSpinBox()
        sp.setRange(1, 1e6)
        sp.setValue(e.interval_h)
        sp.setSuffix(" h")
        note = QLineEdit(e.note)
        f.addRow(tr("Nombre"), ed)
        f.addRow(tr("Servicio cada (horas de operación)"), sp)
        f.addRow(tr("Nota"), note)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(dlg.accept)
        bb.rejected.connect(dlg.reject)
        f.addRow(bb)
        if not dlg.exec() or not ed.text().strip():
            return False
        e.name, e.interval_h, e.note = ed.text().strip(), sp.value(), note.text().strip()
        return True

    def add(self) -> None:
        if not self.line or not self.allow("maintenance"):
            return
        plant = PlantSettings.load(self.home)
        e = Equipment(tr("Nuevo equipo"), 500.0, time.time())
        if self._row_dialog(e):
            self._items(plant).append(e)
            plant.save(self.home)
            self.refresh()

    def _selected(self, plant: PlantSettings):
        r = self.tbl.currentRow()
        items = self._items(plant)
        return items[r] if 0 <= r < len(items) else None

    def edit(self) -> None:
        plant = PlantSettings.load(self.home)
        e = self._selected(plant)
        if e is not None and self.allow("maintenance") and self._row_dialog(e):
            plant.save(self.home)
            self.refresh()

    def serviced(self, confirm: bool = True) -> None:
        plant = PlantSettings.load(self.home)
        e = self._selected(plant)
        if e is None:
            return
        if confirm and QMessageBox.question(self, tr("Servicio hecho"), tr("¿Registrar el servicio de «{e}» hoy? Las horas "
                                                                           "vuelven a cero.", e=e.name)) != QMessageBox.Yes:
            return
        e.last_service = time.time()
        plant.save(self.home)
        self.refresh()

    def remove(self) -> None:
        plant = PlantSettings.load(self.home)
        e = self._selected(plant)
        if e is not None and self.allow("maintenance"):
            self._items(plant).remove(e)
            plant.save(self.home)
            self.refresh()
