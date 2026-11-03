"""Que las ventanas del propio programa no tapen la captura del HMI.

En Windows 10 2004+ y Windows 11 cada ventana del programa se excluye de la captura
(`SetWindowDisplayAffinity(WDA_EXCLUDEFROMCAPTURE)`): el monitor se puede tener encima del HMI y la lectura
no se entera. En Windows anteriores (Windows 7, Windows 10 1809/LTSC 2019…) eso no existe:

* en las capturas puntuales (al abrir la configuración, al grabar un recorrido…) las ventanas se vuelven
  transparentes un instante (`grab_clean`);
* durante el monitoreo no se puede: las variables que una ventana del programa tapa no se leen (conservan su
  último valor y lo dicen) en lugar de leer basura. `occluders()` da esas zonas al motor.
"""
from __future__ import annotations

import sys
import time
from typing import Callable, Optional

from PySide6.QtCore import QEvent, QObject, QRect
from PySide6.QtWidgets import QApplication, QWidget

from ..navigation import exclude_window_from_capture

_supported: Optional[bool] = None  # None: aún no se sabe (ninguna ventana se ha mostrado)


def exclusion_supported() -> Optional[bool]:
    return _supported


def exclude(w: QWidget) -> bool:
    """Excluye una ventana de la captura; recuerda si este Windows lo permite."""
    global _supported
    if sys.platform != "win32":
        return False
    ok = exclude_window_from_capture(int(w.winId()))
    if _supported is None or ok:
        _supported = ok
    return ok


class _ShowFilter(QObject):
    def eventFilter(self, obj, event):  # noqa: N802 (API de Qt)
        if event.type() == QEvent.Show and isinstance(obj, QWidget) and obj.isWindow():
            try:
                exclude(obj)
            except RuntimeError:
                pass
        return False


def install(app: QApplication) -> None:
    """Cada ventana que se muestre (principal, dock, diálogos, mensajes) se excluye de la captura."""
    if sys.platform != "win32" or getattr(app, "_capture_guard", None) is not None:
        return
    app._capture_guard = _ShowFilter()
    app.installEventFilter(app._capture_guard)


def _own_windows() -> list[QWidget]:
    app = QApplication.instance()
    if app is None:
        return []
    return [w for w in app.topLevelWidgets() if w.isVisible() and not w.isMinimized() and w.windowOpacity() > 0]


def grab_clean(grab: Callable[[], object], settle_s: float = 0.15):
    """Captura sin las ventanas del programa: si este Windows no las puede excluir, se vuelven transparentes un
    instante (sin ocultarlas: no parpadea la barra de tareas)."""
    if _supported is not False:
        return grab()
    wins = _own_windows()
    if not wins:
        return grab()
    old = [(w, w.windowOpacity()) for w in wins]
    try:
        for w in wins:
            w.setWindowOpacity(0.0)
        QApplication.processEvents()
        time.sleep(settle_s)  # que el compositor de Windows redibuje lo que está debajo
        QApplication.processEvents()
        return grab()
    finally:
        for w, op in old:
            try:
                w.setWindowOpacity(op)
            except RuntimeError:
                pass


def occluders(offset: tuple[int, int], margin: int = 6) -> list[tuple[int, int, int, int]]:
    """Zonas (x, y, ancho, alto) de la captura que tapan las ventanas visibles del programa.

    Solo cuando este Windows no permite excluirlas. Las coordenadas son las de la imagen capturada: píxeles
    físicos (la captura ignora el escalado de Windows) menos la posición del monitor capturado.
    """
    if _supported is not False:
        return []
    out = []
    for w in _own_windows():
        r: QRect = w.frameGeometry()
        scr = w.screen()
        dpr = scr.devicePixelRatio() if scr is not None else 1.0
        origin = scr.geometry().topLeft() if scr is not None else r.topLeft()
        # Qt (Windows, escalado por monitor): el origen de cada pantalla no se escala, el resto sí.
        x = origin.x() + (r.x() - origin.x()) * dpr - offset[0]
        y = origin.y() + (r.y() - origin.y()) * dpr - offset[1]
        out.append((int(x) - margin, int(y) - margin, int(r.width() * dpr) + 2 * margin,
                    int(r.height() * dpr) + 2 * margin))
    return out
