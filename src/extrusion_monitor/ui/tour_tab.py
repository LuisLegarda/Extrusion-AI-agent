"""Pestaña del configurador: recorridos (macros de navegación) con pasos grabados y disparadores."""
from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Optional

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDoubleSpinBox, QFormLayout, QGroupBox, QHBoxLayout, QLabel,
    QLineEdit, QListWidget, QListWidgetItem, QMessageBox, QPushButton, QScrollArea, QSpinBox, QVBoxLayout,
    QWidget,
)

from ..i18n import translate_widget
from ..capture import crop, load_png
from ..config import Click, TourDef, TourStep
from ..navigation import TourAborted, TourRunner, click_rect
from ..pages import PageDetector

if TYPE_CHECKING:
    from .setup_dialog import SetupDialog

HOME = "__home__"


class TourTab(QWidget):
    """Lista de recorridos: cada uno con sus pasos (clics grabados), regreso y disparadores."""

    def __init__(self, dlg: "SetupDialog"):
        super().__init__()
        self.dlg = dlg
        self.patches = {}
        for c in dlg.config.all_tour_clicks():
            img = load_png(dlg.ctx.workspace.click_patch_file(c.id))
            if img is not None:
                self.patches[c.id] = img
        self.tour: Optional[TourDef] = None
        self.recording: Optional[str] = None  # id del paso (o HOME) que se está grabando
        self._loading = False
        self._build()
        self.reload()
        dlg.view.pointClicked.connect(self._point_clicked)

    # --- construcción ---------------------------------------------------------
    def _build(self) -> None:
        outer = QVBoxLayout(self)
        intro = QLabel(
            "Un recorrido hace clics grabados en el HMI (uno o varios pasos), puede leer los datos de cada "
            "pantalla y regresar. Se dispara cada X tiempo, si el HMI queda fuera de una pantalla, si un "
            "selector cambia o si un valor baja a cero. <b>Seguridad:</b> solo hace clic donde grabaste y "
            "si el botón se ve igual; se pospone si el operador está usando el HMI.")
        intro.setWordWrap(True)
        outer.addWidget(intro)
        row = QHBoxLayout()
        row.addWidget(QLabel("Recorrido:"))
        self.cmb_tour = QComboBox()
        self.cmb_tour.currentIndexChanged.connect(self._tour_selected)
        row.addWidget(self.cmb_tour, 1)
        for text, slot in (("+ Nuevo", self._new_tour), ("Duplicar", self._dup_tour), ("Eliminar", self._del_tour)):
            b = QPushButton(text)
            b.clicked.connect(slot)
            row.addWidget(b)
        outer.addLayout(row)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        body = QWidget()
        scroll.setWidget(body)
        outer.addWidget(scroll, 1)
        lay = QVBoxLayout(body)

        gen = QGroupBox("Ajustes")
        f = QFormLayout(gen)
        self.ed_name = QLineEdit()
        self.ed_name.editingFinished.connect(self._commit)
        f.addRow("Nombre", self.ed_name)
        self.chk_enabled = QCheckBox("Activado")
        self.chk_read = QCheckBox("Leer las variables de cada pantalla visitada")
        f.addRow(self.chk_enabled)
        f.addRow(self.chk_read)
        self.cmb_start = QComboBox()
        f.addRow("Iniciar solo desde", self.cmb_start)
        self.cmb_return = QComboBox()
        f.addRow("Pantalla de regreso (verificada)", self.cmb_return)
        self.sp_idle = self._spin(0, 3600, " s")
        f.addRow("Operador inactivo al menos", self.sp_idle)
        self.sp_retries = QSpinBox()
        self.sp_retries.setRange(0, 10)
        f.addRow("Reintentos al verificar pantalla", self.sp_retries)
        lay.addWidget(gen)

        trig = QGroupBox("Disparadores (cualquiera activa el recorrido)")
        f = QFormLayout(trig)
        self.chk_interval = QCheckBox("Cada")
        self.sp_interval = self._spin(5, 86400, " s")
        f.addRow(self.chk_interval, self.sp_interval)
        self.cmb_off = QComboBox()
        self.sp_off = self._spin(5, 86400, " s")
        r = QHBoxLayout()
        r.addWidget(self.cmb_off, 1)
        r.addWidget(QLabel("durante"))
        r.addWidget(self.sp_off)
        f.addRow("Fuera de la pantalla", r)
        self.cmb_sel = QComboBox()
        self.cmb_sel.currentIndexChanged.connect(self._fill_states)
        self.cmb_state = QComboBox()
        r = QHBoxLayout()
        r.addWidget(self.cmb_sel, 1)
        r.addWidget(QLabel("a"))
        r.addWidget(self.cmb_state)
        f.addRow("Si el selector cambia", r)
        self.cmb_zero = QComboBox()
        self.sp_zero = self._spin(-1e9, 1e9, "")
        r = QHBoxLayout()
        r.addWidget(self.cmb_zero, 1)
        r.addWidget(QLabel("≤"))
        r.addWidget(self.sp_zero)
        f.addRow("Si el valor baja a", r)
        self.chk_confirm = QCheckBox("Avisar con cuenta regresiva (el operador puede posponer)")
        f.addRow(self.chk_confirm)
        self.sp_countdown = self._spin(3, 600, " s")
        f.addRow("Cuenta regresiva", self.sp_countdown)
        self.sp_snooze = self._spin(10, 86400, " s")
        f.addRow("Al posponer, volver a avisar tras", self.sp_snooze)
        lay.addWidget(trig)
        for w in (self.chk_enabled, self.chk_read, self.chk_interval, self.chk_confirm):
            w.toggled.connect(self._commit)
        for w in (self.cmb_start, self.cmb_return, self.cmb_off, self.cmb_sel, self.cmb_state, self.cmb_zero):
            w.currentIndexChanged.connect(self._commit)
        for w in (self.sp_idle, self.sp_retries, self.sp_interval, self.sp_off, self.sp_zero,
                  self.sp_countdown, self.sp_snooze):
            w.valueChanged.connect(self._commit)

        steps = QGroupBox("Pasos (en orden)")
        sl = QVBoxLayout(steps)
        self.lst = QListWidget()
        self.lst.setMinimumHeight(140)
        self.lst.currentRowChanged.connect(lambda _: self._selected())
        sl.addWidget(self.lst)
        row = QHBoxLayout()
        self.cmb_page = QComboBox()
        row.addWidget(self.cmb_page, 1)
        b = QPushButton("+ Paso a esta pestaña")
        b.clicked.connect(self._add_step)
        row.addWidget(b)
        sl.addLayout(row)
        row = QHBoxLayout()
        for text, slot in (("↑", lambda: self._move(-1)), ("↓", lambda: self._move(1)),
                           ("Eliminar paso", self._delete_step)):
            b = QPushButton(text)
            b.clicked.connect(slot)
            row.addWidget(b)
        sl.addLayout(row)
        form = QFormLayout()
        self.sp_settle = self._spin(0.1, 30, " s")
        self.sp_settle.valueChanged.connect(self._commit_step)
        form.addRow("Espera tras el clic", self.sp_settle)
        sl.addLayout(form)
        row = QHBoxLayout()
        self.btn_rec = QPushButton("● Grabar clics (en vivo)")
        self.btn_rec.setToolTip("Cada clic en la captura se ejecuta también en el HMI y se recaptura la pantalla")
        self.btn_rec.clicked.connect(self._toggle_record)
        row.addWidget(self.btn_rec)
        b = QPushButton("Borrar clics")
        b.clicked.connect(self._clear_clicks)
        row.addWidget(b)
        sl.addLayout(row)
        lay.addWidget(steps)

        row = QHBoxLayout()
        b = QPushButton("▶ Probar este recorrido")
        b.clicked.connect(self._test)
        row.addWidget(b)
        lay.addLayout(row)
        self.lbl_status = QLabel()
        self.lbl_status.setWordWrap(True)
        lay.addWidget(self.lbl_status)

    @staticmethod
    def _spin(lo: float, hi: float, suffix: str) -> QDoubleSpinBox:
        sp = QDoubleSpinBox()
        sp.setRange(lo, hi)
        sp.setDecimals(1)
        sp.setSuffix(suffix)
        return sp

    # --- recorridos ----------------------------------------------------------------
    def reload(self) -> None:
        """Vuelve a leer la lista de recorridos de la configuración."""
        tours = self.dlg.config.tours
        keep = self.tour.id if any(x is self.tour for x in tours) else None
        self._loading = True
        self.cmb_tour.clear()
        for t in tours:
            self.cmb_tour.addItem(t.name, t.id)
        self._loading = False
        idx = self.cmb_tour.findData(keep) if keep else 0
        self.cmb_tour.setCurrentIndex(max(0, idx))
        self._tour_selected()

    def _tour_selected(self) -> None:
        if self._loading:
            return
        if self.recording is not None:
            self.stop_recording()
        self.tour = self.dlg.config.get_tour(self.cmb_tour.currentData()) if self.cmb_tour.count() else None
        self.refresh()

    def _new_tour(self) -> None:
        cfg = self.dlg.config
        n = len(cfg.tours) + 1
        t = TourDef(id=uuid.uuid4().hex[:10], name=f"Recorrido {n}", read_data=False,
                    start_page=None, off_page=None)
        cfg.tours.append(t)
        self.tour = t
        self.reload()

    def _dup_tour(self) -> None:
        if self.tour is None:
            return
        t = self.tour.model_copy(deep=True)
        t.id = uuid.uuid4().hex[:10]
        t.name = f"{self.tour.name} (copia)"
        for c in t.all_clicks():
            old = c.id
            c.id = uuid.uuid4().hex[:12]
            if old in self.patches:
                self.patches[c.id] = self.patches[old]
        for st in t.steps:
            st.id = uuid.uuid4().hex[:10]
        self.dlg.config.tours.append(t)
        self.tour = t
        self.reload()

    def _del_tour(self) -> None:
        if self.tour is None:
            return
        if QMessageBox.question(self, "Eliminar", f"¿Eliminar el recorrido «{self.tour.name}»?") != QMessageBox.Yes:
            return
        for c in self.tour.all_clicks():
            self.patches.pop(c.id, None)
        self.dlg.config.tours.remove(self.tour)
        self.tour = None
        self.reload()

    def commit(self) -> list[str]:
        self._commit()
        return []

    # --- estado ---------------------------------------------------------------------
    def _fill_pages(self, cmb: QComboBox, none_label: str, value: Optional[str]) -> None:
        cfg = self.dlg.config
        cmb.clear()
        cmb.addItem(none_label, None)
        for p in sorted(cfg.pages, key=lambda p: cfg.page_label(p.id)):
            cmb.addItem(cfg.page_label(p.id), p.id)
        cmb.setCurrentIndex(max(0, cmb.findData(value)))

    def _fill_vars(self, cmb: QComboBox, kinds: tuple, value: Optional[str]) -> None:
        cfg = self.dlg.config
        cmb.clear()
        cmb.addItem("— no —", None)
        for v in cfg.variables:
            if v.kind in kinds:
                cmb.addItem(cfg.var_label(v), v.id)
        cmb.setCurrentIndex(max(0, cmb.findData(value)))

    def _fill_states(self) -> None:
        if self._loading and self.tour is None:
            return
        var = self.dlg.config.variable(self.cmb_sel.currentData()) if self.cmb_sel.currentData() else None
        cur = self.tour.selector_state if self.tour else None
        was = self._loading
        self._loading = True
        self.cmb_state.clear()
        self.cmb_state.addItem("cualquier estado", None)
        for st in (var.states if var else []):
            self.cmb_state.addItem(st, st)
        self.cmb_state.setCurrentIndex(max(0, self.cmb_state.findData(cur)))
        self._loading = was

    def refresh(self, select: Optional[str] = None) -> None:
        cfg = self.dlg.config
        t = self.tour
        self._loading = True
        self.cmb_page.clear()
        for p in sorted(cfg.pages, key=lambda p: cfg.page_label(p.id)):
            self.cmb_page.addItem(cfg.page_label(p.id), p.id)
        self.setEnabledAll(t is not None)
        if t is not None:
            self.ed_name.setText(t.name)
            self.chk_enabled.setChecked(t.enabled)
            self.chk_read.setChecked(t.read_data)
            self._fill_pages(self.cmb_start, "— cualquier pantalla —", t.start_page)
            self._fill_pages(self.cmb_return, "— no verificar —", t.return_page)
            self._fill_pages(self.cmb_off, "— no —", t.off_page)
            self._fill_vars(self.cmb_sel, ("selector", "text"), t.selector_var)
            self._fill_states()
            self._fill_vars(self.cmb_zero, ("actual", "setpoint", "formula"), t.zero_var)
            self.sp_idle.setValue(t.idle_required_s)
            self.sp_retries.setValue(t.page_retries)
            self.chk_interval.setChecked(t.interval_s is not None)
            self.sp_interval.setValue(t.interval_s or 60)
            self.sp_off.setValue(t.off_page_s)
            self.sp_zero.setValue(t.zero_threshold)
            self.chk_confirm.setChecked(t.confirm)
            self.sp_countdown.setValue(t.countdown_s)
            self.sp_snooze.setValue(t.snooze_s)
        self._loading = False
        current = select or self._current_key()
        self.lst.blockSignals(True)
        self.lst.clear()
        if t is not None:
            for i, st in enumerate(t.steps, 1):
                it = QListWidgetItem(f"{i}. → {cfg.page_label(st.page) or st.page}   ({len(st.clicks)} clics)")
                it.setData(Qt.UserRole, st.id)
                self.lst.addItem(it)
            it = QListWidgetItem(self._return_text())
            it.setData(Qt.UserRole, HOME)
            self.lst.addItem(it)
        self.lst.blockSignals(False)
        for i in range(self.lst.count()):
            if self.lst.item(i).data(Qt.UserRole) == current:
                self.lst.setCurrentRow(i)
                break
        else:
            self.lst.setCurrentRow(0)
        self._selected()
        translate_widget(self)

    def setEnabledAll(self, on: bool) -> None:
        for w in self.findChildren(QGroupBox):
            w.setEnabled(on)

    def _return_text(self) -> str:
        t = self.tour
        dest = self.dlg.config.page_label(t.return_page) if t.return_page else "(sin verificar)"
        return f"⌂ Regreso {dest}   ({len(t.return_clicks)} clics)"

    def _current_key(self) -> Optional[str]:
        it = self.lst.currentItem()
        return it.data(Qt.UserRole) if it else None

    def _step(self, key: Optional[str]) -> Optional[TourStep]:
        return next((s for s in self.tour.steps if s.id == key), None) if self.tour else None

    def _clicks(self, key: Optional[str]) -> Optional[list[Click]]:
        if self.tour is None:
            return None
        if key == HOME:
            return self.tour.return_clicks
        st = self._step(key)
        return st.clicks if st else None

    def _selected(self) -> None:
        key = self._current_key()
        st = self._step(key)
        self.sp_settle.blockSignals(True)
        self.sp_settle.setValue(st.settle_s if st else (self.tour.return_settle_s if self.tour else 1.5))
        self.sp_settle.blockSignals(False)
        self.show_markers()

    def show_markers(self) -> None:
        clicks = self._clicks(self._current_key()) or []
        self.dlg.view.set_markers([(c.x, c.y, str(i)) for i, c in enumerate(clicks, 1)])

    def _commit(self) -> None:
        t = self.tour
        if t is None or self._loading:
            return
        t.name = self.ed_name.text().strip() or t.name
        t.enabled = self.chk_enabled.isChecked()
        t.read_data = self.chk_read.isChecked()
        t.start_page = self.cmb_start.currentData()
        t.return_page = self.cmb_return.currentData()
        t.idle_required_s = self.sp_idle.value()
        t.page_retries = self.sp_retries.value()
        t.interval_s = self.sp_interval.value() if self.chk_interval.isChecked() else None
        t.off_page = self.cmb_off.currentData()
        t.off_page_s = self.sp_off.value()
        t.selector_var = self.cmb_sel.currentData()
        t.selector_state = self.cmb_state.currentData() if t.selector_var else None
        t.zero_var = self.cmb_zero.currentData()
        t.zero_threshold = self.sp_zero.value()
        t.confirm = self.chk_confirm.isChecked()
        t.countdown_s = self.sp_countdown.value()
        t.snooze_s = self.sp_snooze.value()
        i = self.cmb_tour.currentIndex()
        if i >= 0 and self.cmb_tour.itemText(i) != t.name:
            self.cmb_tour.setItemText(i, t.name)
        item = self.lst.item(self.lst.count() - 1)
        if item is not None:
            item.setText(self._return_text())

    def _commit_step(self) -> None:
        key = self._current_key()
        st = self._step(key)
        if st:
            st.settle_s = self.sp_settle.value()
        elif key == HOME and self.tour:
            self.tour.return_settle_s = self.sp_settle.value()

    # --- pasos -----------------------------------------------------------------------
    def _add_step(self) -> None:
        pid = self.cmb_page.currentData()
        if not pid:
            QMessageBox.information(self, "Paso", "Primero crea las pestañas en «Pestañas y variables».")
            return
        if self.tour is None:
            self._new_tour()
        st = TourStep(id=uuid.uuid4().hex[:10], page=pid)
        self.tour.steps.append(st)
        self.refresh(st.id)

    def _delete_step(self) -> None:
        st = self._step(self._current_key())
        if st:
            self.tour.steps.remove(st)
            for c in st.clicks:
                self.patches.pop(c.id, None)
            self.refresh()

    def _move(self, delta: int) -> None:
        st = self._step(self._current_key())
        if not st:
            return
        steps = self.tour.steps
        i = steps.index(st)
        j = i + delta
        if 0 <= j < len(steps):
            steps[i], steps[j] = steps[j], steps[i]
            self.refresh(st.id)

    def _clear_clicks(self) -> None:
        clicks = self._clicks(self._current_key())
        if clicks is not None:
            for c in clicks:
                self.patches.pop(c.id, None)
            clicks.clear()
            self.refresh()

    # --- grabación en vivo -------------------------------------------------------------
    def _toggle_record(self) -> None:
        if self.recording is not None:
            self.stop_recording()
            return
        key = self._current_key()
        if self._clicks(key) is None:
            return
        if self.dlg.frame is None:
            QMessageBox.information(self, "Captura", "Primero captura la pantalla del HMI.")
            return
        self.recording = key
        self.dlg.view.point_mode = True
        self.btn_rec.setText("■ Terminar grabación")
        self.dlg._hint("GRABANDO: haz clic en la captura sobre el botón del HMI. El clic se ejecuta en el HMI "
                       "y la captura se actualiza. Pulsa «Terminar grabación» al llegar a la pantalla.", strong=True)

    def stop_recording(self) -> None:
        self.recording = None
        self.dlg.view.point_mode = False
        self.btn_rec.setText("● Grabar clics (en vivo)")
        self.dlg._hint()
        self.refresh()

    def _point_clicked(self, x: int, y: int) -> None:
        if self.recording is None or self.dlg.frame is None:
            return
        clicks = self._clicks(self.recording)
        c = Click(id=uuid.uuid4().hex[:12], x=x, y=y)
        self.patches[c.id] = crop(self.dlg.frame, click_rect(c)).copy()
        clicks.append(c)
        self.show_markers()
        self._live_click(x, y)

    def _live_click(self, x: int, y: int) -> None:
        clicker = self.dlg.ctx.engine.clicker
        settle = self.sp_settle.value()
        if self.dlg.ctx.demo:
            clicker.click(x, y)
            self.dlg._set_frame(self.dlg.ctx.engine.grab_frame(), fit=False)
            self.show_markers()
            return
        tops = [w for w in QApplication.topLevelWidgets() if w.isVisible()]
        for w in tops:
            w.hide()

        def do_click():
            try:
                clicker.click(x, y)
            except TourAborted as exc:
                self.lbl_status.setText(f"<span style='color:#e53935'>{exc}</span>")
            QTimer.singleShot(int(settle * 1000), grab)

        def grab():
            try:
                frame = self.dlg.ctx.engine.grab_frame()
            finally:
                for w in tops:
                    w.show()
            self.dlg._set_frame(frame, fit=False)
            self.show_markers()

        QTimer.singleShot(400, do_click)

    # --- prueba -------------------------------------------------------------------------
    def _test(self) -> None:
        cfg = self.dlg.config
        t = self.tour
        if t is None:
            return
        self._commit()
        problems = [p for p in cfg.validate_references() if p.startswith(f"Recorrido «{t.name}»")]
        missing = [c for c in t.all_clicks() if c.id not in self.patches]
        if missing:
            problems.append(f"{len(missing)} clics sin imagen del botón: vuelve a grabarlos")
        if not t.steps:
            problems.append("El recorrido no tiene pasos")
        if problems:
            QMessageBox.warning(self, "Recorrido incompleto", "\n".join(problems))
            return
        engine = self.dlg.ctx.engine
        runner = TourRunner(cfg, self.dlg.ctx.workspace, engine.source, engine.clicker,
                            PageDetector(cfg, self.dlg.anchors), clock=engine.clock, sleep=engine.sleep,
                            patches=self.patches)
        frames: list = []
        tops = [] if self.dlg.ctx.demo else [w for w in QApplication.topLevelWidgets() if w.isVisible()]
        for w in tops:
            w.hide()
        QApplication.processEvents()
        try:
            res = runner.run(t, frames.append, skip_idle=True)
        finally:
            for w in tops:
                w.show()
        try:
            self.dlg._set_frame(engine.grab_frame(), fit=False)  # pantalla final
        except Exception:
            pass
        color = "#43a047" if res.ok else "#e53935"
        self.lbl_status.setText(f"<b style='color:{color}'>{'OK' if res.ok else 'FALLÓ'}</b>: "
                                f"{res.message} · {res.duration_s:.1f} s")
