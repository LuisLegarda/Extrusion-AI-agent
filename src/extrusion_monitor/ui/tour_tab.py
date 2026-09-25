"""Pestaña del configurador para grabar y probar el recorrido automático (macro de navegación)."""
from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Optional

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDoubleSpinBox, QFormLayout, QGroupBox, QHBoxLayout, QLabel,
    QListWidget, QListWidgetItem, QMessageBox, QPushButton, QSpinBox, QVBoxLayout, QWidget,
)

from ..capture import crop, load_png
from ..config import Click, TourStep
from ..navigation import TourAborted, TourRunner, click_rect
from ..pages import PageDetector

if TYPE_CHECKING:
    from .setup_dialog import SetupDialog

HOME = "__home__"


class TourTab(QWidget):
    def __init__(self, dlg: "SetupDialog"):
        super().__init__()
        self.dlg = dlg
        self.tour = dlg.config.tour
        self.patches = {}
        for c in self.tour.all_clicks():
            img = load_png(dlg.ctx.workspace.click_patch_file(c.id))
            if img is not None:
                self.patches[c.id] = img
        self.recording: Optional[str] = None  # id del paso (o HOME) que se está grabando
        self._build()
        self.refresh()
        dlg.view.pointClicked.connect(self._point_clicked)

    # --- construcción ---------------------------------------------------------
    def _build(self) -> None:
        lay = QVBoxLayout(self)
        intro = QLabel(
            "El recorrido cambia de pantalla en el HMI con clics grabados, lee los datos de cada "
            "pestaña y regresa a la pantalla principal.<br><b>Seguridad:</b> solo hace clic donde "
            "grabaste y solo si el botón se ve igual que al grabarlo. Además, solo inicia desde la "
            "pantalla principal y se pospone si el operador está usando el HMI.")
        intro.setWordWrap(True)
        lay.addWidget(intro)

        gen = QGroupBox("Ajustes")
        f = QFormLayout(gen)
        self.chk_enabled = QCheckBox("Recorrido automático activado")
        self.chk_enabled.toggled.connect(self._commit)
        f.addRow(self.chk_enabled)
        self.cmb_home = QComboBox()
        self.cmb_home.currentIndexChanged.connect(self._commit)
        f.addRow("Pantalla principal (inicio y regreso)", self.cmb_home)
        self.sp_interval = QDoubleSpinBox()
        self.sp_interval.setRange(5, 3600)
        self.sp_interval.setSuffix(" s")
        self.sp_interval.valueChanged.connect(self._commit)
        f.addRow("Repetir cada", self.sp_interval)
        self.sp_idle = QDoubleSpinBox()
        self.sp_idle.setRange(0, 3600)
        self.sp_idle.setSuffix(" s")
        self.sp_idle.valueChanged.connect(self._commit)
        f.addRow("Operador inactivo al menos", self.sp_idle)
        self.sp_retries = QSpinBox()
        self.sp_retries.setRange(0, 10)
        self.sp_retries.valueChanged.connect(self._commit)
        f.addRow("Reintentos al verificar pantalla", self.sp_retries)
        lay.addWidget(gen)

        steps = QGroupBox("Pasos (en orden)")
        sl = QVBoxLayout(steps)
        self.lst = QListWidget()
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
        self.sp_settle = QDoubleSpinBox()
        self.sp_settle.setRange(0.1, 30)
        self.sp_settle.setSuffix(" s")
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
        lay.addWidget(steps, 1)

        row = QHBoxLayout()
        b = QPushButton("▶ Probar recorrido completo")
        b.clicked.connect(self._test)
        row.addWidget(b)
        lay.addLayout(row)
        self.lbl_status = QLabel()
        self.lbl_status.setWordWrap(True)
        lay.addWidget(self.lbl_status)

    # --- estado ---------------------------------------------------------------------
    def refresh(self, select: Optional[str] = None) -> None:
        cfg = self.dlg.config
        t = self.tour
        for w in (self.chk_enabled, self.cmb_home, self.sp_interval, self.sp_idle, self.sp_retries):
            w.blockSignals(True)
        self.chk_enabled.setChecked(t.enabled)
        self.cmb_home.clear()
        self.cmb_home.addItem("— elegir —", None)
        for p in sorted(cfg.pages, key=lambda p: cfg.page_label(p.id)):
            self.cmb_home.addItem(cfg.page_label(p.id), p.id)
        self.cmb_home.setCurrentIndex(max(0, self.cmb_home.findData(t.home_page)))
        self.sp_interval.setValue(t.interval_s)
        self.sp_idle.setValue(t.idle_required_s)
        self.sp_retries.setValue(t.page_retries)
        for w in (self.chk_enabled, self.cmb_home, self.sp_interval, self.sp_idle, self.sp_retries):
            w.blockSignals(False)
        self.cmb_page.clear()
        for p in sorted(cfg.pages, key=lambda p: cfg.page_label(p.id)):
            self.cmb_page.addItem(cfg.page_label(p.id), p.id)
        current = select or self._current_key()
        self.lst.blockSignals(True)
        self.lst.clear()
        for i, st in enumerate(t.steps, 1):
            it = QListWidgetItem(f"{i}. → {cfg.page_label(st.page) or st.page}   ({len(st.clicks)} clics)")
            it.setData(Qt.UserRole, st.id)
            self.lst.addItem(it)
        home = cfg.page_label(t.home_page) if t.home_page else "pantalla principal"
        it = QListWidgetItem(f"⌂ Regreso a {home}   ({len(t.home_clicks)} clics)")
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

    def _current_key(self) -> Optional[str]:
        it = self.lst.currentItem()
        return it.data(Qt.UserRole) if it else None

    def _step(self, key: Optional[str]) -> Optional[TourStep]:
        return next((s for s in self.tour.steps if s.id == key), None)

    def _clicks(self, key: Optional[str]) -> Optional[list[Click]]:
        if key == HOME:
            return self.tour.home_clicks
        st = self._step(key)
        return st.clicks if st else None

    def _selected(self) -> None:
        key = self._current_key()
        st = self._step(key)
        self.sp_settle.blockSignals(True)
        self.sp_settle.setValue(st.settle_s if st else self.tour.home_settle_s)
        self.sp_settle.blockSignals(False)
        self.show_markers()

    def show_markers(self) -> None:
        clicks = self._clicks(self._current_key()) or []
        self.dlg.view.set_markers([(c.x, c.y, str(i)) for i, c in enumerate(clicks, 1)])

    def _commit(self) -> None:
        t = self.tour
        t.enabled = self.chk_enabled.isChecked()
        t.home_page = self.cmb_home.currentData()
        t.interval_s = self.sp_interval.value()
        t.idle_required_s = self.sp_idle.value()
        t.page_retries = self.sp_retries.value()
        item = self.lst.item(self.lst.count() - 1)
        if item is not None:
            home = self.dlg.config.page_label(t.home_page) if t.home_page else "pantalla principal"
            item.setText(f"⌂ Regreso a {home}   ({len(t.home_clicks)} clics)")

    def _commit_step(self) -> None:
        key = self._current_key()
        st = self._step(key)
        if st:
            st.settle_s = self.sp_settle.value()
        elif key == HOME:
            self.tour.home_settle_s = self.sp_settle.value()

    # --- pasos -----------------------------------------------------------------------
    def _add_step(self) -> None:
        pid = self.cmb_page.currentData()
        if not pid:
            QMessageBox.information(self, "Paso", "Primero crea las pestañas en «Pestañas y variables».")
            return
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
        i = self.tour.steps.index(st)
        j = i + delta
        if 0 <= j < len(self.tour.steps):
            self.tour.steps[i], self.tour.steps[j] = self.tour.steps[j], self.tour.steps[i]
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
        saved = cfg.tour.enabled
        cfg.tour.enabled = True
        problems = [p for p in cfg.validate_references() if p.startswith("Recorrido")]
        cfg.tour.enabled = saved
        missing = [c for c in cfg.tour.all_clicks() if c.id not in self.patches]
        if missing:
            problems.append(f"{len(missing)} clics sin imagen del botón: vuelve a grabarlos")
        if problems:
            QMessageBox.warning(self, "Recorrido incompleto", "\n".join(problems))
            return
        engine = self.dlg.ctx.engine
        runner = TourRunner(cfg, self.dlg.ctx.workspace, engine.source, engine.clicker,
                            PageDetector(cfg, self.dlg.anchors), clock=engine.clock, sleep=engine.sleep,
                            patches=self.patches)
        runner.config.tour.idle_required_s, idle = 0.0, cfg.tour.idle_required_s
        frames: list = []
        tops = [] if self.dlg.ctx.demo else [w for w in QApplication.topLevelWidgets() if w.isVisible()]
        for w in tops:
            w.hide()
        QApplication.processEvents()
        try:
            res = runner.run(frames.append)
        finally:
            cfg.tour.idle_required_s = idle
            for w in tops:
                w.show()
        try:
            self.dlg._set_frame(engine.grab_frame(), fit=False)  # pantalla final (debe ser la principal)
        except Exception:
            pass
        color = "#43a047" if res.ok else "#e53935"
        self.lbl_status.setText(f"<b style='color:{color}'>{'OK' if res.ok else 'FALLÓ'}</b>: "
                                f"{res.message} · {res.duration_s:.1f} s")
