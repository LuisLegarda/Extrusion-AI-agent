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


class ScreenUnavailable(RuntimeError):
    """La pantalla no se puede capturar (sesión bloqueada, escritorio remoto desconectado…)."""


def is_blank(frame: np.ndarray) -> bool:
    """Captura negra o de un solo color: la sesión está bloqueada o desconectada."""
    small = frame[::16, ::16]
    return small.size == 0 or int(small.max()) - int(small.min()) < 6


class ScreenSource:
    """Captura de pantalla con mss (solo lectura, no interactúa con el HMI).

    Tras una desconexión del escritorio remoto o un bloqueo de sesión el contexto de captura de
    Windows queda inválido (capturas negras, errores o geometría vieja): se vuelve a crear solo
    al detectarlo y periódicamente, para que al regresar la lectura se recupere sin reiniciar.
    """

    REFRESH_S = 60.0  # se renueva el contexto de captura (y la geometría del monitor) cada minuto

    def __init__(self, monitor: int = 1):
        self.monitor = monitor
        self._local = threading.local()
        self.size_changed = False

    def _mss(self, renew: bool = False):
        import time
        inst = getattr(self._local, "mss", None)
        born = getattr(self._local, "born", 0.0)
        if inst is not None and (renew or time.monotonic() - born > self.REFRESH_S):
            try:
                inst.close()
            except Exception:
                pass
            inst = None
        if inst is None:
            import mss
            inst = mss.mss()
            self._local.mss = inst
            self._local.born = time.monotonic()
        return inst

    def monitors(self) -> list[dict]:
        return list(self._mss().monitors)

    def offset(self) -> tuple[int, int]:
        """Posición del monitor capturado en el escritorio virtual (para traducir clics)."""
        mons = self.monitors()
        m = mons[self.monitor] if self.monitor < len(mons) else mons[1]
        return int(m["left"]), int(m["top"])

    def _grab_once(self, renew: bool) -> np.ndarray:
        sct = self._mss(renew)
        idx = self.monitor if self.monitor < len(sct.monitors) else 1
        shot = sct.grab(sct.monitors[idx])
        return cv2.cvtColor(np.asarray(shot), cv2.COLOR_BGRA2BGR)

    def grab(self) -> np.ndarray:
        try:
            frame = self._grab_once(renew=False)
            if not is_blank(frame):
                return frame
        except Exception:
            pass
        # Contexto inválido o captura negra: se reintenta con uno nuevo.
        try:
            frame = self._grab_once(renew=True)
        except Exception as exc:
            raise ScreenUnavailable(f"no se puede capturar la pantalla ({exc})") from exc
        if is_blank(frame):
            raise ScreenUnavailable("la pantalla está en negro (sesión bloqueada o escritorio remoto desconectado)")
        return frame


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


def similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Coincidencia 0..1 entre dos imágenes del mismo tamaño (forma y color)."""
    if a is None or b is None or a.shape != b.shape:
        return 0.0
    mad = float(np.abs(a.astype(np.float32) - b.astype(np.float32)).mean())
    color = max(0.0, 1.0 - mad / 80.0)
    g1 = cv2.cvtColor(a, cv2.COLOR_BGR2GRAY).astype(np.float32).ravel()
    g2 = cv2.cvtColor(b, cv2.COLOR_BGR2GRAY).astype(np.float32).ravel()
    g1 -= g1.mean()
    g2 -= g2.mean()
    denom = float(np.linalg.norm(g1) * np.linalg.norm(g2))
    shape = float(g1 @ g2) / denom if denom > 1e-6 else (1.0 if mad < 8 else 0.0)
    return max(0.0, min(shape, color))
