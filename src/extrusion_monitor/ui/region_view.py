"""Vista de la captura del HMI donde se dibujan y seleccionan regiones."""
from __future__ import annotations

from typing import Optional

import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QPainter, QPen
from PySide6.QtWidgets import QGraphicsRectItem, QGraphicsScene, QGraphicsSimpleTextItem, QGraphicsView

from ..config import Rect
from .common import to_pixmap


class RegionView(QGraphicsView):
    rectDrawn = Signal(object)  # Rect
    regionClicked = Signal(str)
    pointClicked = Signal(int, int)  # solo en modo de grabación de clics

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setScene(QGraphicsScene(self))
        self.setRenderHint(QPainter.Antialiasing)
        self.setDragMode(QGraphicsView.NoDrag)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self._pixmap_item = None
        self._items: list = []
        self._start: Optional[QPointF] = None
        self._rubber: Optional[QGraphicsRectItem] = None
        self.selection: Optional[Rect] = None
        self.point_mode = False
        self._markers: list = []

    def set_image(self, img: np.ndarray) -> None:
        scene = self.scene()
        if self._pixmap_item is not None:
            scene.removeItem(self._pixmap_item)
        self._pixmap_item = scene.addPixmap(to_pixmap(img))
        self._pixmap_item.setZValue(-1)
        scene.setSceneRect(QRectF(0, 0, img.shape[1], img.shape[0]))

    def fit(self) -> None:
        self.fitInView(self.scene().sceneRect(), Qt.KeepAspectRatio)

    def set_regions(self, regions: list[tuple[str, str, Rect, str]], selected: Optional[str] = None) -> None:
        """regions: (id, etiqueta, rect, color)."""
        scene = self.scene()
        for it in self._items:
            scene.removeItem(it)
        self._items.clear()
        for rid, label, r, color in regions:
            c = QColor(color)
            item = QGraphicsRectItem(r.x, r.y, r.w, r.h)
            pen = QPen(c, 3 if rid == selected else 1.5)
            pen.setCosmetic(True)
            item.setPen(pen)
            fill = QColor(c)
            fill.setAlpha(70 if rid == selected else 25)
            item.setBrush(QBrush(fill))
            item.setData(0, rid)
            scene.addItem(item)
            text = QGraphicsSimpleTextItem(label)
            text.setBrush(QBrush(c))
            text.setPos(r.x, r.y - 16)
            text.setFlag(QGraphicsSimpleTextItem.ItemIgnoresTransformations)
            scene.addItem(text)
            self._items += [item, text]

    def set_markers(self, points: list[tuple[int, int, str]]) -> None:
        """Marcas numeradas de los clics grabados del recorrido."""
        scene = self.scene()
        for it in self._markers:
            scene.removeItem(it)
        self._markers.clear()
        for x, y, label in points:
            pen = QPen(QColor("#ff1744"), 3)
            pen.setCosmetic(True)
            ring = scene.addEllipse(x - 14, y - 14, 28, 28, pen)
            text = QGraphicsSimpleTextItem(label)
            text.setBrush(QBrush(QColor("#ff1744")))
            text.setPos(x + 14, y - 30)
            text.setFlag(QGraphicsSimpleTextItem.ItemIgnoresTransformations)
            scene.addItem(text)
            self._markers += [ring, text]

    def wheelEvent(self, event) -> None:
        factor = 1.25 if event.angleDelta().y() > 0 else 0.8
        self.scale(factor, factor)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton and self.point_mode:
            p = self.mapToScene(event.position().toPoint())
            self.pointClicked.emit(int(p.x()), int(p.y()))
            return
        if event.button() == Qt.LeftButton:
            self._start = self.mapToScene(event.position().toPoint())
            if self._rubber is None:
                self._rubber = QGraphicsRectItem()
                pen = QPen(QColor("#00e5ff"), 2, Qt.DashLine)
                pen.setCosmetic(True)
                self._rubber.setPen(pen)
                self.scene().addItem(self._rubber)
            self._rubber.setRect(QRectF(self._start, self._start))
        elif event.button() == Qt.MiddleButton:
            self.setDragMode(QGraphicsView.ScrollHandDrag)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self._start is not None and self._rubber is not None:
            p = self.mapToScene(event.position().toPoint())
            self._rubber.setRect(QRectF(self._start, p).normalized())
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if self.point_mode and event.button() == Qt.LeftButton:
            return
        if event.button() == Qt.LeftButton and self._start is not None:
            end = self.mapToScene(event.position().toPoint())
            r = QRectF(self._start, end).normalized()
            self._start = None
            if r.width() >= 4 and r.height() >= 4:
                self.selection = Rect(x=int(r.x()), y=int(r.y()), w=int(r.width()), h=int(r.height()))
                self.rectDrawn.emit(self.selection)
            else:
                if self._rubber is not None:
                    self._rubber.setRect(QRectF())
                for it in self.scene().items(end):
                    rid = it.data(0)
                    if isinstance(rid, str):
                        self.regionClicked.emit(rid)
                        break
        self.setDragMode(QGraphicsView.NoDrag)
        super().mouseReleaseEvent(event)
