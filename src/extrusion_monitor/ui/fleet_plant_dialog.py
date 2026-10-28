"""Dashboard global → Metas, costos y reporte semanal de la planta."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QFormLayout, QHeaderView, QLabel, QLineEdit,
    QPushButton, QSpinBox, QTableWidget, QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget,
)

from ..i18n import tr
from ..plant_settings import PlantSettings, Targets

TARGET_COLS = [("production_shift", "Producción por turno"), ("oee", "OEE mínimo (%)"),
               ("availability", "Disponibilidad mínima (%)"), ("mttr_min", "MTTR máximo (min)"),
               ("scrap_day", "Desperdicio máximo por día")]
DAYS = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
DEFAULT_ROW = "__todas__"


class PlantDialog(QDialog):
    def __init__(self, home: Path, lines: list[str], on_notify=None, on_send_now=None, parent=None):
        super().__init__(parent)
        self.home = Path(home)
        self.s = PlantSettings.load(home)
        self.setWindowTitle(tr("Metas, costos y reporte semanal"))
        self.resize(880, 520)
        root = QVBoxLayout(self)
        tabs = QTabWidget()
        root.addWidget(tabs, 1)

        # metas
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.addWidget(QLabel(tr("Metas por línea (0 = sin meta). La fila «Todas las líneas» aplica a las que no tienen "
                                "metas propias.")))
        names = [DEFAULT_ROW] + list(lines)
        self.tbl = QTableWidget(len(names), len(TARGET_COLS) + 1)
        self.tbl.setHorizontalHeaderLabels([tr("Línea")] + [tr(lb) for _, lb in TARGET_COLS])
        self.tbl.verticalHeader().setVisible(False)
        self.tbl.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.tbl.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.spins: dict[tuple[str, str], QDoubleSpinBox] = {}
        for r, name in enumerate(names):
            it = QTableWidgetItem(tr("Todas las líneas") if name == DEFAULT_ROW else name)
            it.setFlags(Qt.ItemIsEnabled)
            it.setData(Qt.UserRole, name)
            self.tbl.setItem(r, 0, it)
            t = self.s.default_targets if name == DEFAULT_ROW else self.s.targets.get(name, Targets())
            for c, (key, _lb) in enumerate(TARGET_COLS, 1):
                sp = QDoubleSpinBox()
                sp.setRange(0, 1e9)
                sp.setDecimals(0 if key != "mttr_min" else 1)
                sp.setValue(getattr(t, key))
                self.tbl.setCellWidget(r, c, sp)
                self.spins[(name, key)] = sp
        lay.addWidget(self.tbl, 1)
        tabs.addTab(w, tr("🎯 Metas"))

        # costos
        w = QWidget()
        f = QFormLayout(w)
        self.ed_cur = QLineEdit(self.s.currency)
        self.ed_cur.setMaximumWidth(80)
        f.addRow(tr("Moneda"), self.ed_cur)
        self.sp_stop = QDoubleSpinBox()
        self.sp_stop.setRange(0, 1e9)
        self.sp_stop.setDecimals(2)
        self.sp_stop.setValue(self.s.cost_stop_h)
        f.addRow(tr("Costo de una hora de paro"), self.sp_stop)
        self.sp_scrap = QDoubleSpinBox()
        self.sp_scrap.setRange(0, 1e9)
        self.sp_scrap.setDecimals(4)
        self.sp_scrap.setValue(self.s.cost_scrap_unit)
        f.addRow(tr("Costo por unidad de desperdicio (m, kg…)"), self.sp_scrap)
        note = QLabel(tr("Con estos costos el analizador muestra cuánto cuestan los paros y el desperdicio (costo de la "
                         "mala calidad) por línea y en total."))
        note.setWordWrap(True)
        f.addRow(note)
        tabs.addTab(w, tr("💲 Costos"))

        # reporte semanal
        w = QWidget()
        f = QFormLayout(w)
        self.chk_weekly = QCheckBox(tr("Enviar cada semana el reporte del analizador (PDF) por correo o mensaje"))
        self.chk_weekly.setChecked(self.s.weekly.enabled)
        f.addRow(self.chk_weekly)
        self.cmb_day = QComboBox()
        for i, d in enumerate(DAYS):
            self.cmb_day.addItem(tr(d), i)
        self.cmb_day.setCurrentIndex(self.s.weekly.weekday)
        self.sp_hour = QSpinBox()
        self.sp_hour.setRange(0, 23)
        self.sp_hour.setSuffix(":00")
        self.sp_hour.setValue(self.s.weekly.hour)
        f.addRow(tr("Día"), self.cmb_day)
        f.addRow(tr("Hora"), self.sp_hour)
        b = QPushButton(tr("📨 Destinatarios y canales…"))
        b.setEnabled(on_notify is not None)
        if on_notify:
            b.clicked.connect(on_notify)
        f.addRow(b)
        b2 = QPushButton(tr("Enviar ahora el reporte de los últimos 7 días"))
        b2.setEnabled(on_send_now is not None)
        if on_send_now:
            b2.clicked.connect(lambda: (self._apply(), on_send_now()))
        f.addRow(b2)
        note = QLabel(tr("El PDF también se guarda en la carpeta «reportes» del dashboard."))
        note.setWordWrap(True)
        f.addRow(note)
        tabs.addTab(w, tr("📄 Reporte semanal"))

        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText(tr("Guardar"))
        bb.button(QDialogButtonBox.Cancel).setText(tr("Cancelar"))
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        root.addWidget(bb)

    def _apply(self) -> PlantSettings:
        s = PlantSettings.load(self.home)  # conserva mantenimiento, mapa y fecha del último reporte
        for r in range(self.tbl.rowCount()):
            name = self.tbl.item(r, 0).data(Qt.UserRole)
            t = Targets(**{key: self.spins[(name, key)].value() for key, _ in TARGET_COLS})
            if name == DEFAULT_ROW:
                s.default_targets = t
            elif t.any():
                s.targets[name] = t
            else:
                s.targets.pop(name, None)
        s.currency = self.ed_cur.text().strip() or "$"
        s.cost_stop_h = self.sp_stop.value()
        s.cost_scrap_unit = self.sp_scrap.value()
        s.weekly.enabled = self.chk_weekly.isChecked()
        s.weekly.weekday = self.cmb_day.currentData()
        s.weekly.hour = self.sp_hour.value()
        s.save(self.home)
        self.s = s
        return s

    def accept(self) -> None:
        self._apply()
        super().accept()
