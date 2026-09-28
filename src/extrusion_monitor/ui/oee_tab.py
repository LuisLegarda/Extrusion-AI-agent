"""Pestaña del configurador para el cálculo de OEE."""
from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDoubleSpinBox, QFormLayout, QGroupBox, QLabel, QLineEdit, QVBoxLayout, QWidget,
)

if TYPE_CHECKING:
    from .setup_dialog import SetupDialog


class OeeTab(QWidget):
    def __init__(self, dlg: "SetupDialog"):
        super().__init__()
        self.dlg = dlg
        lay = QVBoxLayout(self)
        intro = QLabel(
            "<b>OEE = Disponibilidad × Rendimiento × Calidad</b><br>"
            "• <b>Disponibilidad</b>: tiempo en marcha / tiempo planificado (velocidad ≤ umbral = línea detenida; "
            "los paros cortos son microparos y cuentan en el rendimiento).<br>"
            "• <b>Rendimiento</b>: velocidad real promedio / velocidad nominal.<br>"
            "• <b>Calidad</b>: longitud producida en condición conforme / longitud total.")
        intro.setWordWrap(True)
        lay.addWidget(intro)
        f = QFormLayout()
        self.chk = QCheckBox("Calcular OEE")
        f.addRow(self.chk)
        self.cmb_speed = QComboBox()
        f.addRow("Variable de velocidad de línea", self.cmb_speed)
        self.sp_stop = QDoubleSpinBox()
        self.sp_stop.setRange(0, 100000)
        self.sp_stop.setDecimals(2)
        f.addRow("Detenida si velocidad ≤", self.sp_stop)
        self.cmb_nominal = QComboBox()
        for k, label in (("recipe", "Nominal de la receta"), ("setpoint", "Consigna leída del HMI"),
                         ("fixed", "Valor fijo")):
            self.cmb_nominal.addItem(label, k)
        f.addRow("Velocidad nominal", self.cmb_nominal)
        self.sp_nominal = QDoubleSpinBox()
        self.sp_nominal.setRange(0, 1e6)
        f.addRow("Valor fijo", self.sp_nominal)
        self.sp_slow = QDoubleSpinBox()
        self.sp_slow.setRange(10, 100)
        self.sp_slow.setSuffix(" % de la nominal")
        f.addRow("Marcha lenta por debajo de", self.sp_slow)
        self.sp_micro = QDoubleSpinBox()
        self.sp_micro.setRange(0, 3600)
        self.sp_micro.setSuffix(" s")
        f.addRow("Microparo: paro menor a", self.sp_micro)
        self.cmb_unit = QComboBox()
        for label, factor, unit in (("m/min", 1.0, "m"), ("m/s", 60.0, "m"), ("ft/min", 1.0, "ft"),
                                    ("km/h", 1000 / 60, "m")):
            self.cmb_unit.addItem(label, (factor, unit))
        f.addRow("Unidad de la velocidad", self.cmb_unit)
        self.chk_gap = QCheckBox("Tiempo sin datos cuenta como productivo si al volver todo está en parámetros")
        f.addRow(self.chk_gap)
        self.sp_gap = QDoubleSpinBox()
        self.sp_gap.setRange(0, 1440)
        self.sp_gap.setSuffix(" min")
        f.addRow("…hasta un hueco de", self.sp_gap)
        lay.addLayout(f)

        q = QGroupBox("Calidad")
        qf = QFormLayout(q)
        self.cmb_qmode = QComboBox()
        for k, label in (("spec", "Todas las mediciones dentro de especificación"),
                         ("selector", "Indicador visual (selector) en estado bueno"),
                         ("both", "Ambos")):
            self.cmb_qmode.addItem(label, k)
        qf.addRow("Conforme cuando", self.cmb_qmode)
        self.cmb_qsel = QComboBox()
        self.cmb_qsel.currentIndexChanged.connect(self._fill_states)
        qf.addRow("Indicador", self.cmb_qsel)
        self.cmb_qstate = QComboBox()
        qf.addRow("Estado bueno", self.cmb_qstate)
        self.chk_strict = QCheckBox("Los avisos también cuentan como no conforme (por defecto solo alarmas)")
        qf.addRow(self.chk_strict)
        lay.addWidget(q)
        f2 = QFormLayout()
        self.ed_shifts = QLineEdit()
        self.ed_shifts.setPlaceholderText("06:00, 14:00, 22:00")
        f2.addRow("Inicio de turnos", self.ed_shifts)
        lay.addLayout(f2)
        lay.addStretch()
        self.load()

    def load(self) -> None:
        cfg = self.dlg.config
        o = cfg.oee
        self.chk.setChecked(o.enabled)
        self.cmb_speed.clear()
        self.cmb_speed.addItem("— elegir —", None)
        for v in cfg.variables:
            if v.measured:
                self.cmb_speed.addItem(cfg.var_label(v) + (f" [{v.unit}]" if v.unit else ""), v.id)
        self.cmb_speed.setCurrentIndex(max(0, self.cmb_speed.findData(o.speed_var)))
        self.sp_stop.setValue(o.stop_threshold)
        self.cmb_nominal.setCurrentIndex(max(0, self.cmb_nominal.findData(o.nominal_source)))
        self.sp_nominal.setValue(o.nominal_value or 0)
        self.sp_slow.setValue(o.slow_pct)
        self.sp_micro.setValue(o.microstop_s)
        for i in range(self.cmb_unit.count()):
            if self.cmb_unit.itemData(i) == (o.length_factor, o.length_unit):
                self.cmb_unit.setCurrentIndex(i)
        self.cmb_qmode.setCurrentIndex(max(0, self.cmb_qmode.findData(o.quality_mode)))
        self.cmb_qsel.blockSignals(True)
        self.cmb_qsel.clear()
        self.cmb_qsel.addItem("— ninguno —", None)
        for v in cfg.variables:
            if v.kind == "selector":
                self.cmb_qsel.addItem(cfg.var_label(v), v.id)
        self.cmb_qsel.setCurrentIndex(max(0, self.cmb_qsel.findData(o.quality_selector)))
        self.cmb_qsel.blockSignals(False)
        self._fill_states()
        self.cmb_qstate.setCurrentIndex(max(0, self.cmb_qstate.findData(o.quality_good_state)))
        self.chk_strict.setChecked(o.strict_quality)
        self.chk_gap.setChecked(o.gap_productive)
        self.sp_gap.setValue(o.gap_productive_max_s / 60)
        self.ed_shifts.setText(", ".join(o.shift_starts))

    def _fill_states(self) -> None:
        v = self.dlg.config.variable(self.cmb_qsel.currentData()) if self.cmb_qsel.currentData() else None
        self.cmb_qstate.clear()
        for st in (v.states if v else []):
            self.cmb_qstate.addItem(st, st)

    def commit(self) -> list[str]:
        o = self.dlg.config.oee
        o.enabled = self.chk.isChecked()
        o.speed_var = self.cmb_speed.currentData()
        o.stop_threshold = self.sp_stop.value()
        o.nominal_source = self.cmb_nominal.currentData()
        o.nominal_value = self.sp_nominal.value() or None
        o.slow_pct = self.sp_slow.value()
        o.microstop_s = self.sp_micro.value()
        o.length_factor, o.length_unit = self.cmb_unit.currentData()
        o.quality_mode = self.cmb_qmode.currentData()
        o.quality_selector = self.cmb_qsel.currentData()
        o.quality_good_state = self.cmb_qstate.currentData()
        o.strict_quality = self.chk_strict.isChecked()
        o.gap_productive = self.chk_gap.isChecked()
        o.gap_productive_max_s = self.sp_gap.value() * 60
        o.shift_starts = [s.strip() for s in self.ed_shifts.text().split(",") if s.strip()] or o.shift_starts
        problems = []
        if o.enabled:
            if not o.speed_var:
                problems.append("OEE: elige la variable de velocidad de línea")
            if o.nominal_source == "fixed" and not o.nominal_value:
                problems.append("OEE: indica la velocidad nominal fija")
            if o.quality_mode in ("selector", "both") and not (o.quality_selector and o.quality_good_state):
                problems.append("OEE: elige el indicador de calidad y su estado bueno")
        return problems
