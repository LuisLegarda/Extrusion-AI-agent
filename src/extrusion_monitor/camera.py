"""Captura por cámara (USB o de red) para variables físicas: displays, indicadores, selectores.

Cada cámara usada se lee en su propio hilo: se descartan las imágenes intermedias (siempre se
procesa la más reciente) y solo se decodifica a `read_fps`, para no cargar la PC. Si la cámara
se desconecta, se reintenta sola. Las fuentes «sim:<nombre>» son cámaras simuladas (demo y pruebas).
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Callable, Optional

import cv2
import numpy as np

from .config import CameraDef

log = logging.getLogger(__name__)

FrameProvider = Callable[[], np.ndarray]
RECONNECT_S = 3.0
MAX_AGE_S = 5.0  # una imagen más vieja que esto se considera «sin imagen»


def transform(frame: np.ndarray, cam: CameraDef) -> np.ndarray:
    if cam.rotate == 90:
        frame = cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE)
    elif cam.rotate == 180:
        frame = cv2.rotate(frame, cv2.ROTATE_180)
    elif cam.rotate == 270:
        frame = cv2.rotate(frame, cv2.ROTATE_90_COUNTERCLOCKWISE)
    if cam.flip == "h":
        frame = cv2.flip(frame, 1)
    elif cam.flip == "v":
        frame = cv2.flip(frame, 0)
    return frame


def _open(cam: CameraDef):
    """Abre la cámara con los ajustes de `cam` (índice o URL)."""
    src = cam.source.strip()
    target = int(src) if src.isdigit() else src
    if isinstance(target, int):
        api = {"dshow": cv2.CAP_DSHOW, "msmf": cv2.CAP_MSMF}.get(cam.backend, cv2.CAP_ANY)
        cap = cv2.VideoCapture(target, api)
    else:
        cap = cv2.VideoCapture(target)
    if not cap.isOpened():
        cap.release()
        return None
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    if cam.width and cam.height:
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, cam.width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, cam.height)
    # Exposición y enfoque: los valores dependen del controlador; si no se soportan, se ignoran.
    if cam.auto_exposure:
        cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, 0.75 if cam.backend == "dshow" else 3)
    else:
        cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, 0.25 if cam.backend == "dshow" else 1)
        cap.set(cv2.CAP_PROP_EXPOSURE, cam.exposure)
    cap.set(cv2.CAP_PROP_AUTOFOCUS, 1 if cam.auto_focus else 0)
    if not cam.auto_focus:
        cap.set(cv2.CAP_PROP_FOCUS, cam.focus)
    if cam.brightness is not None:
        cap.set(cv2.CAP_PROP_BRIGHTNESS, cam.brightness)
    return cap


class CameraSource:
    """Lectura continua de una cámara en segundo plano; `frame()` da la imagen más reciente."""

    def __init__(self, cam: CameraDef, provider: Optional[FrameProvider] = None):
        self.cam = cam
        self.provider = provider
        self._frame: Optional[np.ndarray] = None
        self._ts = 0.0
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self.status = "detenida"

    @property
    def simulated(self) -> bool:
        return self.cam.source.startswith("sim:")

    def start(self) -> None:
        if self.simulated or (self._thread and self._thread.is_alive()):
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name=f"camara-{self.cam.id}", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(2.0)
        self._thread = None

    def frame(self, max_age: float = MAX_AGE_S) -> Optional[np.ndarray]:
        if self.simulated:
            if self.provider is None:
                self.status = "cámara simulada no disponible"
                return None
            self.status = "ok"
            return transform(self.provider(), self.cam)
        with self._lock:
            if self._frame is None or time.monotonic() - self._ts > max_age:
                return None
            return self._frame

    def _run(self) -> None:
        cap = None
        period = 1.0 / self.cam.read_fps
        last = 0.0
        while not self._stop.is_set():
            if cap is None:
                self.status = "conectando…"
                cap = _open(self.cam)
                if cap is None:
                    self.status = f"no se pudo abrir «{self.cam.source}»"
                    self._stop.wait(RECONNECT_S)
                    continue
                self.status = "ok"
                fails = 0
            # grab() descarta imágenes viejas sin decodificarlas; solo se decodifica a read_fps.
            if not cap.grab():
                fails += 1
                if fails > 10:
                    log.warning("Cámara %s sin imagen; se reconecta", self.cam.id)
                    cap.release()
                    cap = None
                    self.status = "sin imagen, reconectando…"
                    self._stop.wait(RECONNECT_S)
                else:
                    self._stop.wait(0.05)
                continue
            fails = 0
            now = time.monotonic()
            if now - last < period:
                continue
            ok, img = cap.retrieve()
            if ok and img is not None:
                last = now
                img = transform(img, self.cam)
                with self._lock:
                    self._frame, self._ts = img, now
        if cap is not None:
            cap.release()
        self.status = "detenida"


class CameraManager:
    """Cámaras activas del programa: solo se abren las que usan las variables."""

    def __init__(self, providers: Optional[dict[str, FrameProvider]] = None):
        self.providers = providers or {}
        self.sources: dict[str, CameraSource] = {}

    def _provider(self, cam: CameraDef) -> Optional[FrameProvider]:
        return self.providers.get(cam.source[4:]) if cam.source.startswith("sim:") else None

    def configure(self, cameras: list[CameraDef]) -> None:
        """Arranca/reinicia las cámaras indicadas y detiene las demás."""
        wanted = {c.id: c for c in cameras}
        for cid in list(self.sources):
            src = self.sources[cid]
            if cid not in wanted or src.cam != wanted[cid]:
                src.stop()
                del self.sources[cid]
        for cid, cam in wanted.items():
            if cid not in self.sources:
                src = CameraSource(cam, self._provider(cam))
                src.start()
                self.sources[cid] = src

    def frames(self) -> dict[str, Optional[np.ndarray]]:
        return {cid: src.frame() for cid, src in self.sources.items()}

    def status(self, camera_id: str) -> str:
        src = self.sources.get(camera_id)
        return src.status if src else "detenida"

    def snapshot(self, cam: CameraDef, timeout: float = 4.0) -> Optional[np.ndarray]:
        """Imagen actual de `cam` (para el configurador); abre la cámara un momento si no está activa."""
        src = self.sources.get(cam.id)
        if src is not None and src.cam == cam:
            img = src.frame()
            if img is not None:
                return img
        tmp = CameraSource(cam, self._provider(cam))
        if tmp.simulated:
            return tmp.frame()
        cap = _open(cam)
        if cap is None:
            return None
        try:
            t0 = time.monotonic()
            img = None
            while time.monotonic() - t0 < timeout:  # las primeras imágenes suelen salir oscuras
                ok, frame = cap.read()
                if ok and frame is not None:
                    img = frame
                    if time.monotonic() - t0 > 0.6:
                        break
            return transform(img, cam) if img is not None else None
        finally:
            cap.release()

    def stop_all(self) -> None:
        for src in self.sources.values():
            src.stop()
        self.sources.clear()


def probe_devices(max_index: int = 5) -> list[int]:
    """Índices de cámaras USB conectadas (para el configurador)."""
    found = []
    for i in range(max_index):
        import sys
        cap = cv2.VideoCapture(i, cv2.CAP_DSHOW) if sys.platform == "win32" else cv2.VideoCapture(i)
        if cap.isOpened():
            found.append(i)
        cap.release()
    return found
