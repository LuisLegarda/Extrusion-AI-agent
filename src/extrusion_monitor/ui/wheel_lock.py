"""Bloqueo del zoom con la rueda del ratón en todas las gráficas (menú Ver).

Con el bloqueo, la rueda sobre una gráfica desplaza la página (como en el resto de la ventana) en lugar
de acercar o alejar.
"""
from __future__ import annotations

from PySide6.QtCore import QEvent, QObject
from PySide6.QtWidgets import QAbstractScrollArea, QApplication, QGraphicsView


class WheelLock(QObject):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.enabled = False

    def eventFilter(self, obj, event) -> bool:
        if not self.enabled or event.type() != QEvent.Wheel:
            return False
        view = obj.parent() if obj is not None else None
        if not _is_plot(view):
            return False
        area = view.parent()
        while area is not None and not (isinstance(area, QAbstractScrollArea) and not isinstance(area, QGraphicsView)):
            area = area.parent()
        if area is not None:
            QApplication.sendEvent(area.viewport(), event.clone())
        return True  # la gráfica no hace zoom


def _is_plot(view) -> bool:
    try:
        import pyqtgraph as pg
        return isinstance(view, pg.GraphicsView)
    except Exception:  # pragma: no cover
        return False


_lock = None


def lock() -> WheelLock:
    """El filtro único de la aplicación (se instala la primera vez)."""
    global _lock
    if _lock is None:
        _lock = WheelLock(QApplication.instance())
        QApplication.instance().installEventFilter(_lock)
    return _lock
