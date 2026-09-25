"""Utilidades compartidas de la interfaz."""
from __future__ import annotations

from typing import Optional

import numpy as np
from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QColor, QImage, QPixmap

from ..analysis.rules import Level

LEVEL_COLORS = {
    None: QColor("#5c6370"),
    Level.OK: QColor("#2e7d32"),
    Level.INFO: QColor("#1565c0"),
    Level.WARN: QColor("#f9a825"),
    Level.ALARM: QColor("#c62828"),
}
LEVEL_TEXT = {None: "—", Level.OK: "OK", Level.INFO: "INFO", Level.WARN: "AVISO", Level.ALARM: "ALARMA"}

STYLE = """
QWidget { font-size: 13px; }
QTableWidget { gridline-color: #3a3f4b; }
QHeaderView::section { padding: 4px; font-weight: bold; }
QLabel#banner { font-size: 20px; font-weight: bold; padding: 6px 12px; border-radius: 4px; color: white; }
QToolBar { spacing: 6px; }
"""


def level_color(level: Optional[Level]) -> QColor:
    return LEVEL_COLORS.get(level, LEVEL_COLORS[None])


def to_pixmap(img: np.ndarray) -> QPixmap:
    """Convierte una imagen BGR o en escala de grises de numpy a QPixmap."""
    img = np.ascontiguousarray(img)
    if img.ndim == 2:
        h, w = img.shape
        q = QImage(img.data, w, h, w, QImage.Format_Grayscale8)
    else:
        h, w, _ = img.shape
        rgb = np.ascontiguousarray(img[:, :, ::-1])
        q = QImage(rgb.data, w, h, 3 * w, QImage.Format_RGB888)
    return QPixmap.fromImage(q.copy())


class SnapshotBridge(QObject):
    """Pasa instantáneas del hilo de monitoreo al hilo de la interfaz."""

    snapshot = Signal(object)
