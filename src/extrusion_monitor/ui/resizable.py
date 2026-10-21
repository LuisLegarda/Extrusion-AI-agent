"""Gráficas con alto ajustable: se arrastra la barra inferior con el ratón (doble clic: alto automático).

`ResizableStack` es una columna con desplazamiento: mientras nadie cambie el alto, las gráficas llenan la
pantalla; la que se arrastra queda con su alto fijo y, si ya no caben, aparece la barra de desplazamiento.
"""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QScrollArea, QSizePolicy, QVBoxLayout, QWidget

from ..i18n import tr
from . import theme

QWIDGETSIZE_MAX = 16777215
GRIP_H = 8


class _Grip(QFrame):
    def __init__(self, box: "ResizableBox"):
        super().__init__(box)
        self.box = box
        self.setObjectName("resizeGrip")
        self.setFixedHeight(GRIP_H)
        self.setCursor(Qt.SizeVerCursor)
        self.setToolTip(tr("Arrastra para cambiar el alto de la gráfica (doble clic: alto automático)"))
        self.setAttribute(Qt.WA_Hover)
        self._y0: Optional[float] = None
        self._h0 = 0

    def paintEvent(self, _e) -> None:
        """Agarradera centrada (se resalta al pasar el ratón)."""
        from PySide6.QtCore import QRectF
        from PySide6.QtGui import QColor, QPainter
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        hover = self.underMouse() or self._y0 is not None
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(theme.c("accent") if hover else theme.c("muted")))
        w = 64 if hover else 48
        p.drawRoundedRect(QRectF((self.width() - w) / 2, (self.height() - 4) / 2, w, 4), 2, 2)
        p.end()

    def enterEvent(self, e) -> None:
        self.update()

    def leaveEvent(self, e) -> None:
        self.update()

    def mousePressEvent(self, e) -> None:
        if e.button() == Qt.LeftButton:
            self._y0 = e.globalPosition().y()
            self._h0 = self.box.height()

    def mouseMoveEvent(self, e) -> None:
        if self._y0 is not None:
            self.box.set_height(int(self._h0 + e.globalPosition().y() - self._y0))

    def mouseReleaseEvent(self, e) -> None:
        if self._y0 is not None:
            self._y0 = None
            self.box.resized.emit(self.box.height())

    def mouseDoubleClickEvent(self, e) -> None:
        self.box.set_height(None)
        self.box.resized.emit(0)


class ResizableBox(QWidget):
    """Una gráfica (o tarjeta) con su barra para cambiar el alto."""

    resized = Signal(int)  # alto elegido (0 = automático)

    def __init__(self, child: QWidget, min_h: int = 160, parent=None):
        super().__init__(parent)
        self.child = child
        self.min_h = min_h
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addWidget(child, 1)
        self.grip = _Grip(self)
        lay.addWidget(self.grip)
        self.fixed: Optional[int] = None
        self.set_height(None)

    def set_height(self, h: Optional[int]) -> None:
        if h is None:
            self.fixed = None
            self.setMinimumHeight(self.min_h)
            self.setMaximumHeight(QWIDGETSIZE_MAX)
            self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        else:
            self.fixed = max(self.min_h, h)
            self.setFixedHeight(self.fixed)


class ResizableStack(QScrollArea):
    """Columna de gráficas con alto ajustable y desplazamiento vertical."""

    def __init__(self, min_h: int = 160, parent=None):
        super().__init__(parent)
        self.min_h = min_h
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.inner = QWidget()
        self.lay = QVBoxLayout(self.inner)
        self.lay.setContentsMargins(0, 0, 0, 0)
        self.lay.setSpacing(4)
        self.setWidget(self.inner)
        self.boxes: dict[int, ResizableBox] = {}

    def add(self, w: QWidget) -> ResizableBox:
        box = ResizableBox(w, self.min_h)
        self.boxes[id(w)] = box
        self.lay.addWidget(box)
        return box

    def insert(self, index: int, w: QWidget) -> ResizableBox:
        box = self.boxes.get(id(w)) or ResizableBox(w, self.min_h)
        self.boxes[id(w)] = box
        self.lay.insertWidget(index, box)
        return box

    def box(self, w: QWidget) -> Optional[ResizableBox]:
        return self.boxes.get(id(w))

    def remove(self, w: QWidget) -> None:
        box = self.boxes.pop(id(w), None)
        if box is not None:
            self.lay.removeWidget(box)
            box.setParent(None)
            box.deleteLater()
