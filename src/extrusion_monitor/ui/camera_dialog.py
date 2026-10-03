"""Cámaras: agregar USB o IP, vista en vivo, rotación, exposición y corrección de perspectiva."""
from __future__ import annotations

from typing import Optional

import numpy as np
from PySide6.QtCore import QPointF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QFormLayout, QHBoxLayout, QLabel, QLineEdit,
    QListWidget, QListWidgetItem, QMessageBox, QPushButton, QSplitter, QVBoxLayout, QWidget,
)

from ..camera import CameraUnavailable, find_usb_cameras, grab_for_setup, warp_size
from ..config import AppConfig, CameraSettings
from ..i18n import tr
from .common import to_pixmap

RESOLUTIONS = [(None, "Automática"), ((640, 480), "640 × 480"), ((1280, 720), "1280 × 720 (HD)"),
               ((1920, 1080), "1920 × 1080 (Full HD)"), ((2560, 1440), "2560 × 1440")]
CORNERS = ["superior izquierda", "superior derecha", "inferior derecha", "inferior izquierda"]


class ClickImage(QLabel):
    """Imagen escalada que informa los clics en coordenadas de la imagen original y dibuja un polígono."""

    clicked = Signal(float, float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(480, 300)
        self.setAlignment(Qt.AlignCenter)
        self.setStyleSheet("background:#111; border:1px solid #444;")
        self._img: Optional[np.ndarray] = None
        self._pix: Optional[QPixmap] = None
        self.points: list[list[float]] = []

    def set_image(self, img: Optional[np.ndarray]) -> None:
        self._img = img
        self._pix = to_pixmap(img) if img is not None else None
        self.update()

    def _geom(self):
        if self._pix is None:
            return None
        pw, ph = self._pix.width(), self._pix.height()
        k = min(self.width() / pw, self.height() / ph)
        w, h = pw * k, ph * k
        return (self.width() - w) / 2, (self.height() - h) / 2, k

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        g = self._geom()
        if g is None:
            return
        x0, y0, k = g
        p = QPainter(self)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        p.drawPixmap(int(x0), int(y0), int(self._pix.width() * k), int(self._pix.height() * k), self._pix)
        if self.points:
            pen = QPen(QColor("#00e5ff"), 2)
            p.setPen(pen)
            pts = [QPointF(x0 + x * k, y0 + y * k) for x, y in self.points]
            for i, a in enumerate(pts):
                p.drawEllipse(a, 6, 6)
                p.drawText(a + QPointF(8, -8), str(i + 1))
                if i:
                    p.drawLine(pts[i - 1], a)
            if len(pts) == 4:
                p.drawLine(pts[3], pts[0])
        p.end()

    def mousePressEvent(self, event) -> None:
        g = self._geom()
        if g is None or event.button() != Qt.LeftButton:
            return
        x0, y0, k = g
        x, y = (event.position().x() - x0) / k, (event.position().y() - y0) / k
        if 0 <= x < self._pix.width() and 0 <= y < self._pix.height():
            self.clicked.emit(x, y)


class CamerasDialog(QDialog):
    """Edita `config.cameras` (la copia del configurador)."""

    def __init__(self, config: AppConfig, ctx, parent=None, select: Optional[str] = None):
        super().__init__(parent)
        self.setWindowTitle("Cámaras")
        self.resize(1150, 680)
        self.config = config
        self.ctx = ctx
        self.cams = [c.model_copy(deep=True) for c in config.cameras]
        self._cur: Optional[int] = None
        self._loading = False
        self._corner_mode = False
        self._last_error = ""
        root = QVBoxLayout(self)
        intro = QLabel(
            "Usa una cámara cuando el equipo no tiene una pantalla que se pueda capturar: displays de 7 segmentos o "
            "LCD, luces, torres andon, manómetros o barras de nivel. Colócala fija y de frente, con luz constante y "
            "sin reflejos; luego marca las variables sobre su imagen en el configurador.")
        intro.setWordWrap(True)
        root.addWidget(intro)
        split = QSplitter(Qt.Horizontal)
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        self.lst = QListWidget()
        self.lst.currentRowChanged.connect(self._select)
        ll.addWidget(self.lst)
        row = QHBoxLayout()
        for text, slot in (("+ Agregar", self._add), ("Quitar", self._remove)):
            b = QPushButton(text)
            b.clicked.connect(slot)
            row.addWidget(b)
        ll.addLayout(row)
        b = QPushButton("🔍 Buscar cámaras USB")
        b.clicked.connect(self._find)
        ll.addWidget(b)
        f = QFormLayout()
        self.ed_name = QLineEdit()
        self.cmb_dev = QComboBox()
        self.cmb_dev.setEditable(True)
        self.cmb_dev.setToolTip("Número de la cámara USB (0, 1…), dirección de una cámara IP "
                                "(rtsp://usuario:clave@ip:554/…, http://ip/video) o «demo» (tablero simulado)")
        for d in ("0", "1", "2", "demo"):
            self.cmb_dev.addItem(d)
        self.cmb_res = QComboBox()
        for v, label in RESOLUTIONS:
            self.cmb_res.addItem(label, v)
        self.cmb_rot = QComboBox()
        for v in (0, 90, 180, 270):
            self.cmb_rot.addItem(f"{v}°", v)
        self.chk_exp = QCheckBox("Exposición manual")
        self.chk_exp.setToolTip("Los LED y displays brillantes se «queman» con la exposición automática: baja la "
                                "exposición hasta que los segmentos se vean nítidos.")
        self.sp_exp = QDoubleSpinBox()
        self.sp_exp.setRange(-15, 10000)
        self.sp_exp.setDecimals(1)
        self.sp_exp.setToolTip("En cámaras USB de Windows suele ir de -13 (muy oscura) a -1 (clara)")
        self.sp_fps = QDoubleSpinBox()
        self.sp_fps.setRange(1, 30)
        self.sp_fps.setSuffix(" cuadros/s")
        exp_row = QHBoxLayout()
        exp_row.addWidget(self.chk_exp)
        exp_row.addWidget(self.sp_exp)
        for label, w in (("Nombre", self.ed_name), ("Cámara", self.cmb_dev), ("Resolución", self.cmb_res),
                         ("Rotación", self.cmb_rot), ("", exp_row), ("Análisis", self.sp_fps)):
            f.addRow(label, w)
        ll.addLayout(f)
        self.ed_name.editingFinished.connect(self._commit)
        self.cmb_dev.currentTextChanged.connect(self._commit)
        for w in (self.cmb_res, self.cmb_rot):
            w.currentIndexChanged.connect(self._commit)
        self.chk_exp.toggled.connect(self._commit)
        self.sp_exp.valueChanged.connect(self._commit)
        self.sp_fps.valueChanged.connect(self._commit)
        persp = QHBoxLayout()
        self.btn_corners = QPushButton("⬚ Corregir perspectiva (4 clics)")
        self.btn_corners.setToolTip("Si la cámara no está de frente: haz clic en las 4 esquinas del tablero o "
                                    "display y la imagen se endereza")
        self.btn_corners.clicked.connect(self._start_corners)
        persp.addWidget(self.btn_corners)
        b = QPushButton("Quitar corrección")
        b.clicked.connect(self._clear_warp)
        persp.addWidget(b)
        ll.addLayout(persp)
        self.lbl_info = QLabel()
        self.lbl_info.setWordWrap(True)
        ll.addWidget(self.lbl_info)
        ll.addStretch()
        split.addWidget(left)

        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        bar = QHBoxLayout()
        self.chk_live = QCheckBox("▶ Vista en vivo")
        self.chk_live.toggled.connect(lambda on: self.timer.start(350) if on else self.timer.stop())
        bar.addWidget(self.chk_live)
        b = QPushButton("📷 Tomar imagen")
        b.clicked.connect(self._refresh)
        bar.addWidget(b)
        bar.addStretch()
        rl.addLayout(bar)
        rl.addWidget(QLabel("Imagen de la cámara (rotada):"))
        self.view_raw = ClickImage()
        self.view_raw.clicked.connect(self._corner_clicked)
        rl.addWidget(self.view_raw, 3)
        rl.addWidget(QLabel("Resultado (sobre esta imagen se marcan las variables):"))
        self.view_out = ClickImage()
        rl.addWidget(self.view_out, 2)
        split.addWidget(right)
        split.setSizes([380, 770])
        root.addWidget(split)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText("Aceptar")
        bb.button(QDialogButtonBox.Cancel).setText("Cancelar")
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        root.addWidget(bb)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._refresh)
        self._fill_list()
        idx = next((i for i, c in enumerate(self.cams) if c.id == select), 0)
        if self.cams:
            self.lst.setCurrentRow(idx)
        else:
            self._enable(False)

    # --- lista -------------------------------------------------------------------------------------------
    def _fill_list(self) -> None:
        self.lst.blockSignals(True)
        self.lst.clear()
        for c in self.cams:
            self.lst.addItem(QListWidgetItem(f"📹 {c.name}  ({c.device})"))
        self.lst.blockSignals(False)

    def _enable(self, on: bool) -> None:
        for w in (self.ed_name, self.cmb_dev, self.cmb_res, self.cmb_rot, self.chk_exp, self.sp_exp, self.sp_fps,
                  self.btn_corners):
            w.setEnabled(on)

    def _add(self) -> None:
        existing = {c.id for c in self.cams}
        n = 1
        while f"cam{n}" in existing:
            n += 1
        dev = "demo" if getattr(self.ctx, "demo", False) and not self.cams else str(len(self.cams))
        self.cams.append(CameraSettings(id=f"cam{n}", name=f"{tr('Cámara')} {n}", device=dev))
        self._fill_list()
        self.lst.setCurrentRow(len(self.cams) - 1)

    def _remove(self) -> None:
        if self._cur is None:
            return
        c = self.cams[self._cur]
        used = [v.name for v in self.config.variables if v.source == c.id]
        if used and QMessageBox.question(
                self, "Quitar cámara", f"«{c.name}» tiene {len(used)} variables. Se quitarán también.\n¿Continuar?"
        ) != QMessageBox.Yes:
            return
        del self.cams[self._cur]
        self._cur = None
        self._fill_list()
        if self.cams:
            self.lst.setCurrentRow(0)
        else:
            self._enable(False)
            self.view_raw.set_image(None)
            self.view_out.set_image(None)

    def _find(self) -> None:
        self.lbl_info.setText(tr("Buscando cámaras USB…"))
        self.repaint()
        found = find_usb_cameras()
        self.lbl_info.setText(tr("Cámaras USB encontradas: ") + (", ".join(map(str, found)) if found else tr("ninguna")))

    def _select(self, row: int) -> None:
        self._cur = row if 0 <= row < len(self.cams) else None
        if self._cur is None:
            return
        c = self.cams[self._cur]
        self._loading = True
        self._enable(True)
        self.ed_name.setText(c.name)
        self.cmb_dev.setCurrentText(c.device)
        res = (c.width, c.height) if c.width and c.height else None
        self.cmb_res.setCurrentIndex(max(0, self.cmb_res.findData(res)))
        self.cmb_rot.setCurrentIndex(max(0, self.cmb_rot.findData(c.rotate)))
        self.chk_exp.setChecked(c.exposure is not None)
        self.sp_exp.setValue(c.exposure if c.exposure is not None else -6)
        self.sp_exp.setEnabled(c.exposure is not None)
        self.sp_fps.setValue(c.fps)
        self._loading = False
        self._refresh()

    def _commit(self) -> None:
        if self._loading or self._cur is None:
            return
        c = self.cams[self._cur]
        res = self.cmb_res.currentData()
        dev = self.cmb_dev.currentText().strip() or "0"
        rot = self.cmb_rot.currentData()
        if rot != c.rotate or dev != c.device:
            c.warp = None  # las esquinas se marcaron sobre otra imagen
        c.name = self.ed_name.text().strip() or c.name
        c.device = dev
        c.width, c.height = (res if res else (None, None))
        c.rotate = rot
        c.exposure = self.sp_exp.value() if self.chk_exp.isChecked() else None
        self.sp_exp.setEnabled(self.chk_exp.isChecked())
        c.fps = self.sp_fps.value()
        item = self.lst.item(self._cur)
        if item:
            item.setText(f"📹 {c.name}  ({c.device})")

    # --- imagen ---------------------------------------------------------------------------------------------
    def _refresh(self) -> None:
        if self._cur is None:
            return
        c = self.cams[self._cur]
        try:
            rotated = grab_for_setup(getattr(self.ctx.engine, "cameras", None), c, "rotated")
        except (CameraUnavailable, Exception) as exc:
            msg = f"<span style='color:#e53935'>{tr('Sin imagen')}: {exc}</span>"
            if msg != self._last_error:
                self.lbl_info.setText(msg)
                self._last_error = msg
            self.view_raw.set_image(None)
            self.view_out.set_image(None)
            return
        self._last_error = ""
        self._rotated = rotated
        if not self._corner_mode:
            self.view_raw.points = [list(p) for p in (c.warp or [])]
        self.view_raw.set_image(rotated)
        from ..camera import process
        out = process(rotated, c.model_copy(update={"rotate": 0}))
        self.view_out.set_image(out)
        h, w = rotated.shape[:2]
        extra = ""
        if c.warp:
            ow, oh = warp_size(c.warp)
            extra = f" · {tr('perspectiva corregida')} → {ow}×{oh}"
        if not self._corner_mode:
            self.lbl_info.setText(f"{tr('Imagen')} {w}×{h}{extra}")

    def _start_corners(self) -> None:
        if self._cur is None:
            return
        self._corner_mode = True
        self.view_raw.points = []
        self.view_raw.update()
        self.lbl_info.setText(f"<b>① {tr('Haz clic en la esquina')} {tr(CORNERS[0])}</b>")

    def _corner_clicked(self, x: float, y: float) -> None:
        if not self._corner_mode or self._cur is None:
            return
        self.view_raw.points.append([round(x, 1), round(y, 1)])
        self.view_raw.update()
        n = len(self.view_raw.points)
        if n < 4:
            self.lbl_info.setText(f"<b>{'①②③④'[n]} {tr('Haz clic en la esquina')} {tr(CORNERS[n])}</b>")
            return
        self._corner_mode = False
        self.cams[self._cur].warp = [list(p) for p in self.view_raw.points]
        self._refresh()

    def _clear_warp(self) -> None:
        if self._cur is None:
            return
        self._corner_mode = False
        self.cams[self._cur].warp = None
        self.view_raw.points = []
        self._refresh()

    # --- cerrar ---------------------------------------------------------------------------------------------
    def accept(self) -> None:
        self.timer.stop()
        ids = {c.id for c in self.cams}
        self.config.variables = [v for v in self.config.variables if not v.on_camera or v.source in ids]
        self.config.cameras = self.cams
        super().accept()

    def reject(self) -> None:
        self.timer.stop()
        super().reject()
