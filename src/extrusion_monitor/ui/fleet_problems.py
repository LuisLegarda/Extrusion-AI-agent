"""Dashboard global → Problemas de proceso: Pareto de paros y defectos de todas las líneas, con CSV."""
from __future__ import annotations

import time

from PySide6.QtWidgets import QComboBox, QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout

from ..fleet import read_problems
from ..i18n import tr
from .problems_widgets import ProblemsAnalysis

PERIODS = [("Últimas 24 h", 86400), ("Últimos 7 días", 7 * 86400), ("Últimos 30 días", 30 * 86400),
           ("Últimos 90 días", 90 * 86400)]


class FleetProblemsDialog(QDialog):
    """No modal: se puede dejar abierto junto al dashboard."""

    def __init__(self, window, parent=None):
        super().__init__(parent)
        self.window = window  # FleetWindow: lector actual y áreas
        self.setWindowTitle("Problemas de proceso · todas las líneas")
        self.resize(1150, 760)
        root = QVBoxLayout(self)
        bar = QHBoxLayout()
        bar.addWidget(QLabel("Líneas:"))
        self.cmb_lines = QComboBox()
        self.cmb_lines.setMinimumWidth(240)
        self.cmb_lines.currentIndexChanged.connect(self.refresh)
        bar.addWidget(self.cmb_lines)
        bar.addWidget(QLabel("Periodo:"))
        self.cmb_period = QComboBox()
        for label, secs in PERIODS:
            self.cmb_period.addItem(label, secs)
        self.cmb_period.setCurrentIndex(1)
        self.cmb_period.currentIndexChanged.connect(self.refresh)
        bar.addWidget(self.cmb_period)
        b = QPushButton("⟳ Actualizar")
        b.clicked.connect(self.refresh)
        bar.addWidget(b)
        bar.addStretch()
        root.addLayout(bar)
        self.analysis = ProblemsAnalysis(show_line=True, can_delete=False)
        root.addWidget(self.analysis, 1)
        note = QLabel("Las capturas las hace el operador en el monitor de cada línea (Problemas de proceso). Aquí "
                      "solo se analizan y se descargan.")
        note.setWordWrap(True)
        root.addWidget(note)
        self._fill_lines()
        self.refresh()

    def _fill_lines(self) -> None:
        reader, st = self.window.reader, self.window.settings
        cur = self.cmb_lines.currentData()
        self.cmb_lines.blockSignals(True)
        self.cmb_lines.clear()
        self.cmb_lines.addItem(tr("Todas las líneas"), ("all", ""))
        areas = sorted({st.area_of(ln) for ln in reader.lines.values() if st.area_of(ln)})
        for a in areas:
            self.cmb_lines.addItem(f"{tr('Área')}: {a}", ("area", a))
        for lid, ln in sorted(reader.lines.items(), key=lambda kv: kv[1].name):
            self.cmb_lines.addItem(ln.name, ("line", lid))
        idx = self.cmb_lines.findData(cur) if cur else 0
        self.cmb_lines.setCurrentIndex(max(0, idx))
        self.cmb_lines.blockSignals(False)

    def selected_lines(self) -> list:
        reader, st = self.window.reader, self.window.settings
        kind, key = self.cmb_lines.currentData() or ("all", "")
        lines = list(reader.lines.values())
        if kind == "area":
            return [ln for ln in lines if st.area_of(ln) == key]
        if kind == "line":
            return [ln for ln in lines if ln.line_id == key]
        return lines

    def refresh(self) -> None:
        since = time.time() - (self.cmb_period.currentData() or 7 * 86400)
        records = []
        for ln in self.selected_lines():
            records += read_problems(ln, since)
        units = {r.get("unit") for r in records if r.get("unit")}
        self.analysis.set_data(records, None, units.pop() if len(units) == 1 else "")

    def showEvent(self, event) -> None:
        self._fill_lines()
        super().showEvent(event)
