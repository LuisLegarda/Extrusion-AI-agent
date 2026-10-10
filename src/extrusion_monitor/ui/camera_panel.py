"""Opciones de captura por cámara (se muestran en la variable cuando su captura es «Cámara»)."""
from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDoubleSpinBox, QFormLayout, QGroupBox, QHBoxLayout, QLabel, QMessageBox,
    QPushButton, QSpinBox,
)

from ..config import CameraDef
from ..i18n import tr

if TYPE_CHECKING:
    from .setup_dialog import SetupDialog


class CameraPanel(QGroupBox):
    def __init__(self, dlg: "SetupDialog"):
        super().__init__("Cámara")
        self.dlg = dlg
        self._loading = False
        f = QFormLayout(self)
        row = QHBoxLayout()
        self.cmb_cam = QComboBox()
        self.cmb_cam.currentIndexChanged.connect(self._camera_chosen)
        row.addWidget(self.cmb_cam, 1)
        for text, slot in (("+ Nueva cámara", self.new_camera), ("Eliminar cámara", self._delete_camera)):
            b = QPushButton(text)
            b.clicked.connect(slot)
            row.addWidget(b)
        f.addRow("Cámara", row)
        self.ed_name = QComboBox()  # nombre editable (combo para heredar el estilo de campo)
        self.ed_name.setEditable(True)
        self.ed_name.lineEdit().editingFinished.connect(self._commit)
        f.addRow("Nombre", self.ed_name)
        row = QHBoxLayout()
        self.cmb_source = QComboBox()
        self.cmb_source.setEditable(True)
        self.cmb_source.setToolTip("Índice de la cámara USB (0, 1, …) o dirección de red: rtsp://usuario:clave@IP/…, "
                                   "http://IP/video")
        self.cmb_source.lineEdit().editingFinished.connect(self._commit)
        self.cmb_source.activated.connect(lambda _: self._commit())
        row.addWidget(self.cmb_source, 1)
        b = QPushButton("🔍 Buscar cámaras")
        b.clicked.connect(self._probe)
        row.addWidget(b)
        f.addRow("Fuente", row)
        self.cmb_backend = QComboBox()
        for k, label in (("auto", "automático"), ("dshow", "DirectShow (Windows, recomendado)"),
                         ("msmf", "Media Foundation (Windows)")):
            self.cmb_backend.addItem(label, k)
        f.addRow("Controlador", self.cmb_backend)
        row = QHBoxLayout()
        self.sp_w, self.sp_h = QSpinBox(), QSpinBox()
        for sp, mx in ((self.sp_w, 7680), (self.sp_h, 4320)):
            sp.setRange(0, mx)
            sp.setSpecialValueText("predeterminada")
            row.addWidget(sp)
        f.addRow("Resolución (ancho × alto)", row)
        self.cmb_rotate = QComboBox()
        for deg in (0, 90, 180, 270):
            self.cmb_rotate.addItem(f"{deg}°", deg)
        f.addRow("Rotación", self.cmb_rotate)
        self.cmb_flip = QComboBox()
        for k, label in (("none", "sin espejo"), ("h", "espejo horizontal"), ("v", "espejo vertical")):
            self.cmb_flip.addItem(label, k)
        f.addRow("Espejo", self.cmb_flip)
        row = QHBoxLayout()
        self.chk_auto_exp = QCheckBox("automática")
        self.sp_exp = QDoubleSpinBox()
        self.sp_exp.setRange(-15, 10000)
        self.sp_exp.setDecimals(1)
        self.sp_exp.setToolTip("Valor del controlador; en DirectShow suele ir de -13 (oscuro) a -1 (claro)")
        row.addWidget(self.chk_auto_exp)
        row.addWidget(self.sp_exp, 1)
        f.addRow("Exposición", row)
        row = QHBoxLayout()
        self.chk_auto_focus = QCheckBox("automático")
        self.sp_focus = QDoubleSpinBox()
        self.sp_focus.setRange(0, 1000)
        row.addWidget(self.chk_auto_focus)
        row.addWidget(self.sp_focus, 1)
        f.addRow("Enfoque", row)
        self.sp_bright = QDoubleSpinBox()
        self.sp_bright.setRange(-1, 255)
        self.sp_bright.setSpecialValueText("de la cámara")
        f.addRow("Brillo", self.sp_bright)
        self.sp_fps = QDoubleSpinBox()
        self.sp_fps.setRange(0.2, 30)
        self.sp_fps.setDecimals(1)
        self.sp_fps.setSuffix(" img/s")
        self.sp_fps.setToolTip("Imágenes que se procesan por segundo; menos = menos carga en la PC")
        f.addRow("Lecturas por segundo", self.sp_fps)
        row = QHBoxLayout()
        b = QPushButton("📷 Ver imagen de la cámara")
        b.setToolTip("Muestra la imagen actual de la cámara a la izquierda para marcar o ajustar la región")
        b.clicked.connect(lambda: self.dlg.show_source(self.current_id()))
        row.addWidget(b)
        self.lbl_status = QLabel()
        self.lbl_status.setWordWrap(True)
        row.addWidget(self.lbl_status, 1)
        f.addRow(row)
        for w in (self.cmb_backend, self.cmb_rotate, self.cmb_flip):
            w.currentIndexChanged.connect(self._commit)
        for w in (self.sp_w, self.sp_h, self.sp_exp, self.sp_focus, self.sp_bright, self.sp_fps):
            w.editingFinished.connect(self._commit)
        for w in (self.chk_auto_exp, self.chk_auto_focus):
            w.toggled.connect(self._commit)

    # --- lista de cámaras ------------------------------------------------------------
    def current_id(self) -> Optional[str]:
        return self.cmb_cam.currentData()

    def current(self) -> Optional[CameraDef]:
        return self.dlg.config.camera(self.current_id())

    def load(self, camera_id: Optional[str]) -> None:
        self._loading = True
        self.cmb_cam.clear()
        for c in self.dlg.config.cameras:
            self.cmb_cam.addItem(c.name, c.id)
        self.cmb_cam.setCurrentIndex(max(0, self.cmb_cam.findData(camera_id)))
        self._loading = False
        self._fill()

    def ensure_camera(self) -> str:
        """Id de la cámara elegida; crea la primera si no hay ninguna."""
        if not self.dlg.config.cameras:
            self.new_camera(select_var=False)
        return self.current_id() or self.dlg.config.cameras[0].id

    def new_camera(self, select_var: bool = True) -> None:
        cfg = self.dlg.config
        ids = {c.id for c in cfg.cameras}
        n = 1
        while f"cam{n}" in ids:
            n += 1
        cam = CameraDef(id=f"cam{n}", name=f"{tr('Cámara')} {n}", source=str(len(cfg.cameras)))
        cfg.cameras.append(cam)
        self.load(cam.id)
        self.dlg.camera_changed()
        if select_var:
            self.dlg.camera_selected_for_var(cam.id)

    def _delete_camera(self) -> None:
        cam = self.current()
        if cam is None:
            return
        users = [v.name for v in self.dlg.config.variables if v.from_camera and v.camera_id == cam.id]
        if users:
            QMessageBox.warning(self, tr("Cámara"), tr("La cámara la usan: {v}. Cambia esas variables primero.",
                                                        v=", ".join(users[:6])))
            return
        self.dlg.config.cameras.remove(cam)
        self.load(None)
        self.dlg.camera_changed()

    def _camera_chosen(self) -> None:
        if self._loading:
            return
        self._fill()
        self.dlg.camera_selected_for_var(self.current_id())

    # --- campos ---------------------------------------------------------------------
    def _fill(self) -> None:
        cam = self.current()
        self._loading = True
        for w in (self.ed_name, self.cmb_source, self.cmb_backend, self.sp_w, self.sp_h, self.cmb_rotate,
                  self.cmb_flip, self.chk_auto_exp, self.sp_exp, self.chk_auto_focus, self.sp_focus, self.sp_bright,
                  self.sp_fps):
            w.setEnabled(cam is not None)
        if cam is not None:
            self.ed_name.setEditText(cam.name)
            if self.cmb_source.findText(cam.source) < 0:
                self.cmb_source.addItem(cam.source)
            self.cmb_source.setEditText(cam.source)
            self.cmb_backend.setCurrentIndex(max(0, self.cmb_backend.findData(cam.backend)))
            self.sp_w.setValue(cam.width)
            self.sp_h.setValue(cam.height)
            self.cmb_rotate.setCurrentIndex(max(0, self.cmb_rotate.findData(cam.rotate)))
            self.cmb_flip.setCurrentIndex(max(0, self.cmb_flip.findData(cam.flip)))
            self.chk_auto_exp.setChecked(cam.auto_exposure)
            self.sp_exp.setValue(cam.exposure)
            self.sp_exp.setEnabled(not cam.auto_exposure)
            self.chk_auto_focus.setChecked(cam.auto_focus)
            self.sp_focus.setValue(cam.focus)
            self.sp_focus.setEnabled(not cam.auto_focus)
            self.sp_bright.setValue(-1 if cam.brightness is None else cam.brightness)
            self.sp_fps.setValue(cam.read_fps)
            self.lbl_status.setText(self.dlg.ctx.engine.cameras.status(cam.id))
        self._loading = False

    def _commit(self) -> None:
        cam = self.current()
        if cam is None or self._loading:
            return
        cam.name = self.ed_name.currentText().strip() or cam.name
        cam.source = self.cmb_source.currentText().strip() or cam.source
        cam.backend = self.cmb_backend.currentData()
        cam.width, cam.height = self.sp_w.value(), self.sp_h.value()
        cam.rotate = self.cmb_rotate.currentData()
        cam.flip = self.cmb_flip.currentData()
        cam.auto_exposure = self.chk_auto_exp.isChecked()
        cam.exposure = self.sp_exp.value()
        cam.auto_focus = self.chk_auto_focus.isChecked()
        cam.focus = self.sp_focus.value()
        cam.brightness = None if self.sp_bright.value() < 0 else self.sp_bright.value()
        cam.read_fps = self.sp_fps.value()
        self.sp_exp.setEnabled(not cam.auto_exposure)
        self.sp_focus.setEnabled(not cam.auto_focus)
        i = self.cmb_cam.currentIndex()
        if i >= 0 and self.cmb_cam.itemText(i) != cam.name:
            self.cmb_cam.setItemText(i, cam.name)
        self.dlg.camera_changed()

    def _probe(self) -> None:
        from ..camera import probe_devices
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            found = probe_devices()
        finally:
            QApplication.restoreOverrideCursor()
        current = self.cmb_source.currentText()
        self.cmb_source.clear()
        for i in found:
            self.cmb_source.addItem(str(i))
        self.cmb_source.setEditText(current)
        self.lbl_status.setText(tr("Cámaras encontradas: {c}", c=", ".join(map(str, found)) or tr("ninguna")))
