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
QMainWindow, QWidget#content { background: #f4f6f9; }
QMenuBar { background: #2f343b; color: #ffffff; padding: 2px 6px; font-size: 14px; font-weight: bold; }
QMenuBar::item { background: transparent; padding: 6px 12px; }
QMenuBar::item:selected { background: #44505e; border-radius: 4px; }
QMenu { background: #ffffff; border: 1px solid #c7d3e3; }
QMenu::item { padding: 6px 24px 6px 18px; }
QMenu::item:selected { background: #1f4e79; color: #ffffff; }
QWidget#sidebar { background: #e8f0fa; border-right: 1px solid #c7d3e3; }
QListWidget#nav { background: transparent; border: none; font-size: 14px; outline: 0; }
QListWidget#nav::item { padding: 8px 10px; border-radius: 6px; margin: 1px 0; color: #1f3b57; }
QListWidget#nav::item:hover { background: #d3e2f4; }
QListWidget#nav::item:selected { background: #1f4e79; color: #ffffff; font-weight: bold; }
QToolButton#run { background: #1f4e79; color: #ffffff; font-weight: bold; padding: 7px 16px; border-radius: 6px; }
QToolButton#run:hover { background: #2a6299; }
QTabWidget::pane { border: 1px solid #d5dbe3; background: #ffffff; border-radius: 4px; }
QTabBar::tab { padding: 6px 14px; }
QTabBar::tab:selected { background: #ffffff; font-weight: bold; color: #1f4e79; }
QTableWidget, QTreeWidget, QListWidget { background: #ffffff; }
QTableWidget { gridline-color: #e1e6ed; }
QHeaderView::section { padding: 4px; font-weight: bold; background: #eef2f7; border: none;
                       border-bottom: 1px solid #d5dbe3; color: #1f3b57; }
QLabel#banner { font-size: 18px; font-weight: bold; padding: 6px 14px; border-radius: 6px; color: white; }
QPushButton { padding: 5px 12px; }
QStatusBar { background: #e8edf3; color: #37474f; }
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
