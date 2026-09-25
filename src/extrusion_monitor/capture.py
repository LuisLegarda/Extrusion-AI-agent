"""Fuentes de imagen: pantalla del HMI, archivo de imagen o simulador."""
from __future__ import annotations

import threading
from pathlib import Path
from typing import Protocol

import cv2
import numpy as np

from .config import Rect


class FrameSource(Protocol):
    def grab(self) -> np.ndarray:
        """Devuelve la pantalla completa como imagen BGR."""
        ...


class ScreenSource:
    """Captura de pantalla con mss (solo lectura, no interactúa con el HMI)."""

    def __init__(self, monitor: int = 1):
        self.monitor = monitor
        self._local = threading.local()

    def _mss(self):
        inst = getattr(self._local, "mss", None)
        if inst is None:
            import mss
            inst = mss.mss()
            self._local.mss = inst
        return inst

    def monitors(self) -> list[dict]:
        return list(self._mss().monitors)

    def offset(self) -> tuple[int, int]:
        """Posición del monitor capturado en el escritorio virtual (para traducir clics)."""
        mons = self.monitors()
        m = mons[self.monitor] if self.monitor < len(mons) else mons[1]
        return int(m["left"]), int(m["top"])

    def grab(self) -> np.ndarray:
        sct = self._mss()
        idx = self.monitor if self.monitor < len(sct.monitors) else 1
        shot = sct.grab(sct.monitors[idx])
        return cv2.cvtColor(np.asarray(shot), cv2.COLOR_BGRA2BGR)


class ImageFileSource:
    """Útil para configurar fuera de línea con una captura guardada y para pruebas."""

    def __init__(self, path: Path | str):
        img = cv2.imdecode(np.fromfile(str(path), np.uint8), cv2.IMREAD_COLOR)
        if img is None:
            raise ValueError(f"No se pudo leer la imagen {path}")
        self.image = img

    def grab(self) -> np.ndarray:
        return self.image.copy()


def crop(frame: np.ndarray, r: Rect) -> np.ndarray:
    h, w = frame.shape[:2]
    x0, y0 = max(0, r.x), max(0, r.y)
    x1, y1 = min(w, r.x + r.w), min(h, r.y + r.h)
    if x1 <= x0 or y1 <= y0:
        return np.zeros((1, 1, 3), np.uint8)
    return frame[y0:y1, x0:x1]


def save_png(path: Path, image: np.ndarray) -> None:
    ok, buf = cv2.imencode(".png", image)
    if not ok:
        raise ValueError("No se pudo codificar la imagen")
    buf.tofile(str(path))


def load_png(path: Path) -> np.ndarray | None:
    if not Path(path).exists():
        return None
    return cv2.imdecode(np.fromfile(str(path), np.uint8), cv2.IMREAD_COLOR)
