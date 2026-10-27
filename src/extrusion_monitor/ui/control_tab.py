"""Configuración → Control: lazos PID que ajustan un input del HMI según una medición."""
from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Optional

from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDoubleSpinBox, QFormLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QMessageBox, QPushButton, QScrollArea, QVBoxLayout, QWidget,
)

from ..capture import crop
from ..config import SCREEN, Click, ControlLoop
from ..i18n import tr
from ..navigation import click_rect

if TYPE_CHECKING:
    from .setup_dialog import SetupDialog

MODES = [("simulate", "Simulación (calcula y registra, no escribe)"), ("assist", "Asistido (propone; el operador aplica)"),
         ("auto", "Automático (ajusta solo, dentro de los límites)")]
MARKS = {"field": "Clic en el CAMPO del input (donde se escribe el valor)",
         "confirm": "Clic en el botón de CONFIRMACIÓN del HMI (p. ej. «OK»)",
         "inc": "Clic en el botón que SUBE el valor (+)", "dec": "Clic en el botón que BAJA el valor (−)"}


def _opt(text: str) -> Optional[float]:
    t = text.strip().replace(",", ".")
    return float(t) if t else None


def _fmt(v: Optional[float]) -> str:
    return "" if v is None else f"{v:g}"


class ControlTab(QWidget):
    def __init__(self, dlg: "SetupDialog"):
        super().__init__()
        self.dlg = dlg
        self._cur: Optional[str] = None
        self._loading = False
        self._marking: Optional[str] = None
        lay = QHBoxLayout(self)
        left_w = QWidget()
        left_w.setMaximumWidth(260)
        left = QVBoxLayout(left_w)
        left.setContentsMargins(0, 0, 0, 0)
        intro = QLabel("Un lazo ajusta un <b>input del HMI</b> (p. ej. velocidad del capstan) para llevar una "
                       "<b>medición</b> (p. ej. diámetro) a su objetivo. Al abrir el programa los lazos quedan "
                       "desactivados: se activan en la página <b>Control</b>.")
        intro.setWordWrap(True)
        left.addWidget(intro)
        self.lst = QListWidget()
        self.lst.currentRowChanged.connect(self._select)
        left.addWidget(self.lst, 1)
        row = QHBoxLayout()
        for text, slot in (("+ Lazo", self._add), ("Quitar", self._remove)):
            b = QPushButton(text)
            b.clicked.connect(slot)
            row.addWidget(b)
        left.addLayout(row)
        lay.addWidget(left_w)

        form_w = QWidget()
        self.form = QVBoxLayout(form_w)
        g = QGroupBox("Lazo")
        f = QFormLayout(g)
        self.ed_name = QLineEdit()
        self.cmb_mode = QComboBox()
        for k, label in MODES:
            self.cmb_mode.addItem(label, k)
        self.cmb_pv = QComboBox()
        self.cmb_target = QComboBox()
        self.cmb_target.addItem("Nominal de la receta", "recipe")
        self.cmb_target.addItem("Valor fijo", "fixed")
        self.ed_target = QLineEdit()
        self.cmb_in = QComboBox()
        f.addRow("Nombre", self.ed_name)
        f.addRow("Modo al activarlo", self.cmb_mode)
        f.addRow("Medición a controlar", self.cmb_pv)
        f.addRow("Objetivo", self.cmb_target)
        f.addRow("Valor objetivo fijo", self.ed_target)
        f.addRow("Input del HMI que se ajusta", self.cmb_in)
        self.form.addWidget(g)

        g = QGroupBox("Cómo se cambia el input en el HMI")
        f = QFormLayout(g)
        self.cmb_method = QComboBox()
        self.cmb_method.addItem("Escribiendo el valor (clic en el campo, valor y Enter)", "type")
        self.cmb_method.addItem("Con botones + / −", "buttons")
        f.addRow("Método", self.cmb_method)
        self.lbl_marks = QLabel()
        self.lbl_marks.setWordWrap(True)
        f.addRow("Clics grabados", self.lbl_marks)
        r1 = QHBoxLayout()
        self.btn_field = QPushButton("🎯 Campo")
        self.btn_confirm = QPushButton("🎯 Confirmación (opcional)")
        self.btn_noconfirm = QPushButton("Sin confirmación")
        self.btn_inc = QPushButton("🎯 Botón +")
        self.btn_dec = QPushButton("🎯 Botón −")
        for b, key in ((self.btn_field, "field"), (self.btn_confirm, "confirm"), (self.btn_inc, "inc"),
                       (self.btn_dec, "dec")):
            b.clicked.connect(lambda _=False, key=key: self._start_mark(key))
            r1.addWidget(b)
        self.btn_noconfirm.clicked.connect(self._no_confirm)
        r1.addWidget(self.btn_noconfirm)
        f.addRow(r1)
        self.chk_selall = QCheckBox("Seleccionar todo (Ctrl+A) antes de escribir")
        f.addRow(self.chk_selall)
        self.sp_step = QDoubleSpinBox()
        self.sp_step.setRange(0.0001, 1e6)
        self.sp_step.setDecimals(4)
        f.addRow("Cambio por cada clic de botón", self.sp_step)
        self.cmb_route = QComboBox()
        self.cmb_route.setToolTip("Si el input está en otra pestaña: recorrido que lleva a ella (su regreso se usa "
                                  "al terminar). Se graba en «Recorrido automático».")
        f.addRow("Ruta a la pantalla del input", self.cmb_route)
        self.sp_verify = QDoubleSpinBox()
        self.sp_verify.setRange(1, 120)
        self.sp_verify.setSuffix(" s")
        f.addRow("Esperar el valor en el HMI hasta", self.sp_verify)
        self.form.addWidget(g)

        g = QGroupBox("PID")
        f = QFormLayout(g)
        self.cmb_tuning = QComboBox()
        self.cmb_tuning.addItem("Manual (valores de esta receta)", "manual")
        self.cmb_tuning.addItem("Aprendido de los cambios del operador", "learned")
        f.addRow("Ajuste", self.cmb_tuning)
        self.cmb_action = QComboBox()
        self.cmb_action.addItem("Si la medición está alta, SUBIR el input", "inc_when_high")
        self.cmb_action.addItem("Si la medición está alta, BAJAR el input", "dec_when_high")
        f.addRow("Acción", self.cmb_action)
        self.sp_kp = self._dspin(0, 1e7, 4)
        self.sp_ti = self._dspin(0, 1e5, 1, " s")
        self.sp_td = self._dspin(0, 1e5, 1, " s")
        self.sp_aggr = self._dspin(0.2, 5, 2)
        self.sp_aggr.setToolTip("PID aprendido: 0.5 = más rápido · 1 = normal · 2 = más suave")
        f.addRow("Kp (input por unidad de error)", self.sp_kp)
        f.addRow("Ti (0 = sin integral)", self.sp_ti)
        f.addRow("Td", self.sp_td)
        f.addRow("Suavidad del PID aprendido", self.sp_aggr)
        self.lbl_model = QLabel()
        self.lbl_model.setWordWrap(True)
        b = QPushButton("Copiar el PID aprendido a manual")
        b.clicked.connect(self._copy_learned)
        f.addRow(self.lbl_model)
        f.addRow(b)
        self.chk_learn = QCheckBox("Aprender de los cambios que haga el operador en el input")
        f.addRow(self.chk_learn)
        self.sp_window = self._dspin(30, 7200, 0, " s")
        f.addRow("Observar la medición tras cada cambio", self.sp_window)
        self.form.addWidget(g)

        g = QGroupBox("Límites y seguridad")
        f = QFormLayout(g)
        self.ed_umin, self.ed_umax, self.ed_step, self.ed_rate, self.ed_res = (QLineEdit() for _ in range(5))
        for e in (self.ed_step, self.ed_rate):
            e.setPlaceholderText("sin límite")
        self.ed_res.setPlaceholderText("según los decimales del input")
        f.addRow("Input mínimo", self.ed_umin)
        f.addRow("Input máximo", self.ed_umax)
        f.addRow("Cambio máximo por ajuste", self.ed_step)
        f.addRow("Cambio máximo por minuto", self.ed_rate)
        f.addRow("Redondear el input a", self.ed_res)
        self.sp_dead = self._dspin(0, 1e6, 4)
        f.addRow("Banda muerta (error tolerado)", self.sp_dead)
        self.sp_int = self._dspin(2, 3600, 0, " s")
        f.addRow("Tiempo mínimo entre ajustes", self.sp_int)
        self.chk_alarm = QCheckBox("Detener si hay una alarma en otra variable")
        self.chk_stopped = QCheckBox("Detener si la línea está detenida")
        f.addRow(self.chk_alarm)
        f.addRow(self.chk_stopped)
        self.sp_idle = self._dspin(0, 3600, 0, " s")
        f.addRow("No ajustar si el operador usó el HMI hace menos de", self.sp_idle)
        self.sp_hold = self._dspin(0, 86400, 0, " s")
        f.addRow("Tras un cambio del operador, esperar", self.sp_hold)
        self.sp_age = self._dspin(1, 3600, 0, " s")
        f.addRow("Medición vieja después de", self.sp_age)
        self.cmb_gate = QComboBox()
        f.addRow("Solo con comportamiento normal", self.cmb_gate)
        self.form.addWidget(g)
        self.form.addStretch()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(form_w)
        lay.addWidget(scroll, 1)

        for w in (self.cmb_mode, self.cmb_pv, self.cmb_target, self.cmb_in, self.cmb_method, self.cmb_route,
                  self.cmb_tuning, self.cmb_action, self.cmb_gate):
            w.currentIndexChanged.connect(self.commit)
        for w in (self.ed_name, self.ed_target, self.ed_umin, self.ed_umax, self.ed_step, self.ed_rate, self.ed_res):
            w.editingFinished.connect(self.commit)
        for w in (self.sp_step, self.sp_verify, self.sp_kp, self.sp_ti, self.sp_td, self.sp_aggr, self.sp_window,
                  self.sp_dead, self.sp_int, self.sp_idle, self.sp_hold, self.sp_age):
            w.valueChanged.connect(self.commit)
        for w in (self.chk_selall, self.chk_learn, self.chk_alarm, self.chk_stopped):
            w.toggled.connect(self.commit)
        dlg.view.pointClicked.connect(self._point)
        self.refresh()

    @staticmethod
    def _dspin(lo, hi, dec, suffix=""):
        s = QDoubleSpinBox()
        s.setRange(lo, hi)
        s.setDecimals(dec)
        s.setSuffix(suffix)
        return s

    # --- lista ------------------------------------------------------------------------------------------
    @property
    def loops(self) -> list[ControlLoop]:
        return self.dlg.config.controls

    def loop(self) -> Optional[ControlLoop]:
        return self.dlg.config.control(self._cur) if self._cur else None

    def refresh(self) -> None:
        cfg = self.dlg.config
        self._loading = True
        for cmb, kinds in ((self.cmb_pv, ("actual", "formula", "setpoint")), (self.cmb_in, ("setpoint", "actual"))):
            cur = cmb.currentData()
            cmb.clear()
            cmb.addItem("— elegir —", None)
            for v in cfg.variables:
                if v.kind in kinds and (cmb is self.cmb_pv or (v.source == SCREEN and v.reader == "ocr")):
                    cmb.addItem(cfg.var_label(v), v.id)
            cmb.setCurrentIndex(max(0, cmb.findData(cur)))
        cur = self.cmb_route.currentData()
        self.cmb_route.clear()
        self.cmb_route.addItem("— está en la misma pantalla —", None)
        for t in cfg.tours:
            self.cmb_route.addItem(t.name, t.id)
        self.cmb_route.setCurrentIndex(max(0, self.cmb_route.findData(cur)))
        self.cmb_gate.clear()
        self.cmb_gate.addItem("— no exigir —", None)
        for m in self.dlg.ctx.engine.behaviors.store.models:
            self.cmb_gate.addItem(m.name, m.id)
        self._loading = False
        self.lst.blockSignals(True)
        self.lst.clear()
        for lp in self.loops:
            it = QListWidgetItem(f"🎛 {lp.name}")
            self.lst.addItem(it)
        self.lst.blockSignals(False)
        idx = next((i for i, lp in enumerate(self.loops) if lp.id == self._cur), 0 if self.loops else -1)
        self.lst.setCurrentRow(idx)
        self._select(idx)

    def _add(self) -> None:
        lp = ControlLoop(id=uuid.uuid4().hex[:8], name=tr("Lazo de control"))
        self.loops.append(lp)
        self._cur = lp.id
        self.refresh()

    def _remove(self) -> None:
        lp = self.loop()
        if lp is None:
            return
        if QMessageBox.question(self, tr("Quitar lazo"), tr("¿Quitar el lazo «{n}»?", n=lp.name)) != QMessageBox.Yes:
            return
        for c in lp.write.clicks():
            self.dlg.tour_tab.patches.pop(c.id, None)
        self.dlg.config.controls = [x for x in self.loops if x.id != lp.id]
        self._cur = None
        self.refresh()

    def _select(self, row: int) -> None:
        enabled = 0 <= row < len(self.loops)
        for i in range(self.form.count()):
            w = self.form.itemAt(i).widget()
            if w is not None:
                w.setEnabled(enabled)
        if not enabled:
            self._cur = None
            return
        lp = self.loops[row]
        self._cur = lp.id
        self._loading = True
        self.ed_name.setText(lp.name)
        self.cmb_mode.setCurrentIndex(max(0, self.cmb_mode.findData(lp.mode)))
        self.cmb_pv.setCurrentIndex(max(0, self.cmb_pv.findData(lp.pv_var)))
        self.cmb_target.setCurrentIndex(max(0, self.cmb_target.findData(lp.target)))
        self.ed_target.setText(_fmt(lp.target_value))
        self.cmb_in.setCurrentIndex(max(0, self.cmb_in.findData(lp.input_var)))
        w = lp.write
        self.cmb_method.setCurrentIndex(max(0, self.cmb_method.findData(w.method)))
        self.chk_selall.setChecked(w.select_all)
        self.sp_step.setValue(w.step)
        self.cmb_route.setCurrentIndex(max(0, self.cmb_route.findData(w.route_tour)))
        self.sp_verify.setValue(w.verify_s)
        self.cmb_tuning.setCurrentIndex(max(0, self.cmb_tuning.findData(lp.tuning)))
        self.cmb_action.setCurrentIndex(max(0, self.cmb_action.findData(lp.action)))
        self.sp_kp.setValue(lp.kp)
        self.sp_ti.setValue(lp.ti_s)
        self.sp_td.setValue(lp.td_s)
        self.sp_aggr.setValue(lp.aggressiveness)
        self.chk_learn.setChecked(lp.learn)
        self.sp_window.setValue(lp.learn_window_s)
        for e, v in ((self.ed_umin, lp.u_min), (self.ed_umax, lp.u_max), (self.ed_step, lp.max_step),
                     (self.ed_rate, lp.max_rate_min), (self.ed_res, lp.resolution)):
            e.setText(_fmt(v))
        self.sp_dead.setValue(lp.deadband)
        self.sp_int.setValue(lp.interval_s)
        self.chk_alarm.setChecked(lp.stop_on_alarm)
        self.chk_stopped.setChecked(lp.stop_when_line_stopped)
        self.sp_idle.setValue(lp.operator_idle_s)
        self.sp_hold.setValue(lp.operator_hold_s)
        self.sp_age.setValue(lp.max_pv_age_s)
        self.cmb_gate.setCurrentIndex(max(0, self.cmb_gate.findData(lp.gate_behavior)))
        self._loading = False
        self._update_widgets(lp)

    def _update_widgets(self, lp: ControlLoop) -> None:
        typ = lp.write.method == "type"
        for w in (self.btn_field, self.btn_confirm, self.btn_noconfirm, self.chk_selall):
            w.setVisible(typ)
        for w in (self.btn_inc, self.btn_dec, self.sp_step):
            w.setVisible(not typ)
        lbl = self.sp_step.parentWidget().layout().labelForField(self.sp_step)
        if lbl is not None:
            lbl.setVisible(not typ)
        self.ed_target.setEnabled(lp.target == "fixed")
        manual = lp.tuning == "manual"
        for w in (self.sp_kp, self.sp_ti, self.sp_td, self.cmb_action):
            w.setEnabled(manual)
        self.sp_aggr.setEnabled(not manual)
        w = lp.write
        marks = []
        if typ:
            marks.append(f"{tr('campo')}: {'✔' if w.field else '—'}")
            marks.append(f"{tr('confirmación')}: {'✔' if w.confirm else tr('no')}")
        else:
            marks += [f"+: {'✔' if w.inc else '—'}", f"−: {'✔' if w.dec else '—'}"]
        self.lbl_marks.setText(" · ".join(marks))
        self.show_markers()
        eng = self.dlg.ctx.engine
        m = eng.control.model(eng.state.recipe, lp.id)
        s = m.summary()
        if s is None:
            self.lbl_model.setText(tr("Aún no hay cambios del operador observados para la receta activa."))
        else:
            k, theta, tau = s
            pid = m.pid(lp.aggressiveness)
            txt = tr("Aprendido ({n} cambios): la medición cambia {k} por unidad de input, retardo {th} s, "
                     "constante {tau} s.", n=m.n, k=f"{k:+.4g}", th=f"{theta:.0f}", tau=f"{tau:.0f}")
            if pid and m.ready:
                txt += " " + tr("PID sugerido: Kp {kp}, Ti {ti} s.", kp=f"{abs(pid[0]):.4g}", ti=f"{pid[1]:.0f}")
            elif not m.consistent:
                txt += " " + tr("Las observaciones no coinciden en la dirección: se necesitan más.")
            self.lbl_model.setText(txt)

    def show_markers(self) -> None:
        """Marca en la captura los clics grabados del lazo seleccionado."""
        lp = self.loop()
        if lp is None or self.dlg.tabs.currentWidget() is not self:
            return
        w = lp.write
        names = {"field": tr("campo"), "confirm": "OK", "inc": "+", "dec": "−"}
        pts = [(c.x, c.y, names[k]) for k, c in (("field", w.field), ("confirm", w.confirm), ("inc", w.inc),
                                                  ("dec", w.dec)) if c is not None]
        self.dlg.view.set_markers(pts)

    def _copy_learned(self) -> None:
        lp = self.loop()
        if lp is None:
            return
        eng = self.dlg.ctx.engine
        m = eng.control.model(eng.state.recipe, lp.id)
        pid = m.pid(lp.aggressiveness) if m.ready else None
        if pid is None:
            QMessageBox.information(self, tr("PID aprendido"), tr("Aún no hay suficientes observaciones."))
            return
        lp.kp, lp.ti_s, lp.td_s = abs(pid[0]), pid[1], 0.0
        lp.action = "inc_when_high" if pid[0] < 0 else "dec_when_high"
        lp.tuning = "manual"
        self._select(self.lst.currentRow())

    def commit(self) -> list[str]:
        lp = self.loop()
        if lp is not None and not self._loading:
            lp.name = self.ed_name.text().strip() or lp.name
            lp.mode = self.cmb_mode.currentData()
            lp.pv_var = self.cmb_pv.currentData()
            lp.target = self.cmb_target.currentData()
            lp.target_value = _opt(self.ed_target.text())
            lp.input_var = self.cmb_in.currentData()
            w = lp.write
            w.method = self.cmb_method.currentData()
            w.select_all = self.chk_selall.isChecked()
            w.step = self.sp_step.value()
            w.route_tour = self.cmb_route.currentData()
            w.verify_s = self.sp_verify.value()
            lp.tuning = self.cmb_tuning.currentData()
            lp.action = self.cmb_action.currentData()
            lp.kp, lp.ti_s, lp.td_s = self.sp_kp.value(), self.sp_ti.value(), self.sp_td.value()
            lp.aggressiveness = self.sp_aggr.value()
            lp.learn, lp.learn_window_s = self.chk_learn.isChecked(), self.sp_window.value()
            try:
                lp.u_min, lp.u_max = _opt(self.ed_umin.text()), _opt(self.ed_umax.text())
                lp.max_step, lp.max_rate_min = _opt(self.ed_step.text()), _opt(self.ed_rate.text())
                lp.resolution = _opt(self.ed_res.text()) or None
            except ValueError:
                pass
            lp.deadband, lp.interval_s = self.sp_dead.value(), self.sp_int.value()
            lp.stop_on_alarm, lp.stop_when_line_stopped = self.chk_alarm.isChecked(), self.chk_stopped.isChecked()
            lp.operator_idle_s, lp.operator_hold_s = self.sp_idle.value(), self.sp_hold.value()
            lp.max_pv_age_s = self.sp_age.value()
            lp.gate_behavior = self.cmb_gate.currentData()
            item = self.lst.currentItem()
            if item:
                item.setText(f"🎛 {lp.name}")
            self._update_widgets(lp)
        return []

    # --- clics -------------------------------------------------------------------------------------------
    def _start_mark(self, key: str) -> None:
        if self.loop() is None:
            return
        if self.dlg.source != SCREEN:
            self.dlg.set_source(SCREEN)
        if self.dlg.frame is None:
            QMessageBox.information(self, tr("Captura"), tr("Primero captura la pantalla del HMI."))
            return
        self._marking = key
        self.dlg.view.point_mode = True
        self.dlg._hint(tr(MARKS[key]) + " · " + tr("Esc para cancelar"), strong=True)

    def _point(self, x: int, y: int) -> None:
        lp = self.loop()
        if self._marking is None or lp is None or self.dlg.frame is None:
            return
        key, self._marking = self._marking, None
        self.dlg.view.point_mode = False
        self.dlg._hint()
        old = getattr(lp.write, key)
        if old is not None:
            self.dlg.tour_tab.patches.pop(old.id, None)
        c = Click(id=f"ctl_{uuid.uuid4().hex[:10]}", x=x, y=y)
        self.dlg.tour_tab.patches[c.id] = crop(self.dlg.frame, click_rect(c)).copy()
        setattr(lp.write, key, c)
        self._update_widgets(lp)

    def cancel_mark(self) -> bool:
        if self._marking is None:
            return False
        self._marking = None
        self.dlg.view.point_mode = False
        self.dlg._hint()
        return True

    def _no_confirm(self) -> None:
        lp = self.loop()
        if lp is None or lp.write.confirm is None:
            return
        self.dlg.tour_tab.patches.pop(lp.write.confirm.id, None)
        lp.write.confirm = None
        self._update_widgets(lp)
