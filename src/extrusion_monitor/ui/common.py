"""Utilidades compartidas de la interfaz."""
from __future__ import annotations

from typing import Optional

import numpy as np
from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QColor, QImage, QPixmap

from ..analysis.rules import Level
from . import theme

_LEVEL_KEYS = {None: "neutral", Level.OK: "good", Level.INFO: "info", Level.WARN: "warning",
               Level.ALARM: "critical"}
LEVEL_TEXT = {None: "—", Level.OK: "OK", Level.INFO: "INFO", Level.WARN: "AVISO", Level.ALARM: "ALARMA"}


def level_color(level: Optional[Level]) -> QColor:
    """Color de estado del tema (bueno / aviso / alarma…)."""
    return QColor(theme.c(_LEVEL_KEYS.get(level, "neutral")))


def level_text_color(level: Optional[Level]) -> QColor:
    """Texto legible sobre el color de estado (oscuro sobre amarillo)."""
    return QColor("#1b1b1b" if level == Level.WARN else "#ffffff")


def level_text(level: Optional[Level]) -> str:
    from ..i18n import tr
    return tr(LEVEL_TEXT.get(level, "—"))


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
