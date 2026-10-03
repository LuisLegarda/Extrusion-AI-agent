"""Cámaras (USB o IP) como fuente de imagen para equipos sin un HMI que se pueda capturar.

Cada cámara se lee en un hilo propio: guarda los últimos cuadros (ya rotados y con la perspectiva
corregida) y, en cada cuadro, el color de las luces configuradas, para detectar parpadeos más rápidos
que el ciclo de lectura. Si la cámara se desconecta se vuelve a abrir sola.
"""
from __future__ import annotations

import logging
import sys
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Callable, Optional

import cv2
import numpy as np

from .capture import crop, is_blank
from .config import CameraSettings, Rect

log = logging.getLogger(__name__)

KEEP_FRAMES = 3  # para combinar cuadros (los displays LED multiplexados no se ven completos en uno solo)
LAMP_HISTORY = 120
STALE_S = 10.0


class CameraUnavailable(RuntimeError):
    pass


class OpenCvCamera:
    """Cámara USB (por índice) o IP (RTSP / HTTP MJPEG) con OpenCV."""

    def __init__(self, s: CameraSettings):
        dev = s.device.strip()
        if dev.isdigit():
            backend = cv2.CAP_DSHOW if sys.platform == "win32" else cv2.CAP_ANY
            self.cap = cv2.VideoCapture(int(dev), backend)
        else:
            self.cap = cv2.VideoCapture(dev)
        if not self.cap.isOpened():
            raise CameraUnavailable(f"no se pudo abrir la cámara «{dev}»")
        if s.width and s.height:
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, s.width)
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, s.height)
        if s.exposure is not None:
            self.cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, 0.25 if sys.platform == "win32" else 1)
            self.cap.set(cv2.CAP_PROP_EXPOSURE, float(s.exposure))
        self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

    def read(self) -> np.ndarray:
        ok, frame = self.cap.read()
        if not ok or frame is None:
            raise CameraUnavailable("la cámara no entrega imagen")
        return frame

    def release(self) -> None:
        try:
            self.cap.release()
        except Exception:
            pass


def open_camera(s: CameraSettings):
    if s.device.strip().lower() == "demo":
        from .simulator import SimCamera
        return SimCamera()
    return OpenCvCamera(s)


def warp_size(pts: list[list[float]]) -> tuple[int, int]:
    p = np.array(pts, np.float32)
    w = max(np.linalg.norm(p[1] - p[0]), np.linalg.norm(p[2] - p[3]))
    h = max(np.linalg.norm(p[3] - p[0]), np.linalg.norm(p[2] - p[1]))
    return max(8, int(round(w))), max(8, int(round(h)))


def process(frame: np.ndarray, s: CameraSettings) -> np.ndarray:
    """Rotación y corrección de perspectiva configuradas (las regiones se marcan sobre este resultado)."""
    if s.rotate == 90:
        frame = cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE)
    elif s.rotate == 180:
        frame = cv2.rotate(frame, cv2.ROTATE_180)
    elif s.rotate == 270:
        frame = cv2.rotate(frame, cv2.ROTATE_90_COUNTERCLOCKWISE)
    if s.warp and len(s.warp) == 4:
        w, h = warp_size(s.warp)
        dst = np.float32([[0, 0], [w - 1, 0], [w - 1, h - 1], [0, h - 1]])
        m = cv2.getPerspectiveTransform(np.float32(s.warp), dst)
        frame = cv2.warpPerspective(frame, m, (w, h))
    return frame


@dataclass
class CameraView:
    """Lo que el ciclo de lectura ve de una cámara."""

    frames: list = field(default_factory=list)  # últimos cuadros procesados (el último al final)
    ts: Optional[float] = None
    error: Optional[str] = None
    lamps: dict = field(default_factory=dict)  # var_id -> [(ts, color Lab)]

    @property
    def ok(self) -> bool:
        return bool(self.frames) and self.error is None

    @property
    def frame(self) -> Optional[np.ndarray]:
        return self.frames[-1] if self.frames else None


class CameraFeed:
    def __init__(self, settings: CameraSettings, opener: Callable = open_camera, clock=time.time):
        self.settings = settings
        self.opener = opener
        self.clock = clock
        self.cam = None
        self.frames: deque = deque(maxlen=KEEP_FRAMES)
        self.raw: Optional[np.ndarray] = None  # último cuadro sin procesar (para ajustar rotación/perspectiva)
        self.ts: Optional[float] = None
        self.error: Optional[str] = None
        self.probes: list[tuple[str, Rect]] = []
        self.lamps: dict[str, deque] = {}
        self.lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._retry_at = 0.0
        self._backoff = 2.0

    def set_probes(self, probes: list[tuple[str, Rect]]) -> None:
        with self.lock:
            self.probes = list(probes)
            self.lamps = {vid: self.lamps.get(vid, deque(maxlen=LAMP_HISTORY)) for vid, _ in probes}

    def poll(self) -> bool:
        """Lee y procesa un cuadro. Devuelve False si la cámara no está disponible."""
        from .vision.indicators import lamp_feature
        now = time.monotonic()
        if self.cam is None:
            if now < self._retry_at:
                return False
            try:
                self.cam = self.opener(self.settings)
                self._backoff = 2.0
            except Exception as exc:
                self._fail(f"{exc}", now)
                return False
        try:
            raw = self.cam.read()
            if is_blank(raw):
                raise CameraUnavailable("la imagen está en negro (¿tapa puesta o sin luz?)")
            frame = process(raw, self.settings)
        except Exception as exc:
            self._fail(str(exc), now)
            self._close()
            return False
        ts = self.clock()
        with self.lock:
            self.frames.append(frame)
            self.raw = raw
            self.ts = ts
            self.error = None
            for vid, r in self.probes:
                self.lamps.setdefault(vid, deque(maxlen=LAMP_HISTORY)).append((ts, lamp_feature(crop(frame, r))))
        return True

    def _fail(self, msg: str, now: float) -> None:
        with self.lock:
            self.error = msg
        self._retry_at = now + self._backoff
        self._backoff = min(30.0, self._backoff * 2)

    def _close(self) -> None:
        if self.cam is not None:
            try:
                self.cam.release()
            except Exception:
                pass
            self.cam = None

    def view(self) -> CameraView:
        with self.lock:
            err = self.error
            if err is None and self.ts is not None and self.clock() - self.ts > STALE_S:
                err = "sin imagen nueva"
            if self.ts is None and err is None:
                err = "conectando…"
            return CameraView(list(self.frames), self.ts, err, {k: list(v) for k, v in self.lamps.items()})

    # --- hilo -----------------------------------------------------------------------------------------
    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name=f"camara-{self.settings.id}", daemon=True)
        self._thread.start()

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def stop(self, timeout: float = 3.0) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout)
        self._thread = None
        self._close()

    def _run(self) -> None:
        period = 1.0 / max(1.0, self.settings.fps)
        while not self._stop.is_set():
            t0 = time.monotonic()
            try:
                ok = self.poll()
            except Exception:  # nunca debe caerse el hilo
                log.exception("Fallo en la cámara %s", self.settings.id)
                ok = False
            wait = period - (time.monotonic() - t0) if ok else 0.5
            if wait > 0:
                self._stop.wait(wait)


class CameraManager:
    """Todas las cámaras de la configuración."""

    def __init__(self, opener: Callable = open_camera, clock=time.time):
        self.opener = opener
        self.clock = clock
        self.feeds: dict[str, CameraFeed] = {}
        self._started = False

    def configure(self, cameras: list[CameraSettings], probes: dict[str, list[tuple[str, Rect]]]) -> None:
        wanted = {c.id: c for c in cameras}
        for cid in list(self.feeds):
            if cid not in wanted or self.feeds[cid].settings != wanted[cid]:
                self.feeds.pop(cid).stop()
        for cid, s in wanted.items():
            if cid not in self.feeds:
                self.feeds[cid] = CameraFeed(s, self.opener, self.clock)
                if self._started:
                    self.feeds[cid].start()
            self.feeds[cid].set_probes(probes.get(cid, []))

    def start(self) -> None:
        self._started = True
        for f in self.feeds.values():
            f.start()

    def stop(self) -> None:
        self._started = False
        for f in self.feeds.values():
            f.stop()

    def views(self) -> dict[str, CameraView]:
        """Estado de cada cámara; si los hilos no corren (pruebas, configurador) se lee un cuadro ahora."""
        out = {}
        for cid, f in self.feeds.items():
            if not f.running:
                f.poll()
            out[cid] = f.view()
        return out

    def grab(self, cam_id: str, raw: bool = False) -> Optional[np.ndarray]:
        f = self.feeds.get(cam_id)
        if f is None:
            return None
        if not f.running:
            f.poll()
        with f.lock:
            img = f.raw if raw else (f.frames[-1] if f.frames else None)
        return None if img is None else img.copy()


def grab_once(s: CameraSettings, opener: Callable = open_camera, raw: bool = False, tries: int = 5) -> np.ndarray:
    """Un cuadro de una cámara que no está en uso (configurador). Se descartan los primeros (exposición)."""
    cam = opener(s)
    try:
        frame = None
        for _ in range(tries):
            frame = cam.read()
        return frame if raw else process(frame, s)
    finally:
        cam.release()


def find_usb_cameras(max_index: int = 5) -> list[int]:
    found = []
    for i in range(max_index):
        backend = cv2.CAP_DSHOW if sys.platform == "win32" else cv2.CAP_ANY
        cap = cv2.VideoCapture(i, backend)
        try:
            if cap.isOpened() and cap.read()[0]:
                found.append(i)
        finally:
            cap.release()
    return found


def grab_for_setup(manager: Optional[CameraManager], s: CameraSettings, stage: str = "final") -> np.ndarray:
    """Cuadro para el configurador con los ajustes `s` (aunque aún no se hayan guardado).

    stage: «raw» (tal cual), «rotated» (rotado, sin perspectiva: ahí se marcan las esquinas) o «final».
    Si el motor ya tiene abierta esa cámara se usa su último cuadro (Windows no deja abrirla dos veces).
    """
    feed = None
    if manager is not None:
        feed = manager.feeds.get(s.id)
        if feed is None or feed.settings.device != s.device:
            feed = next((f for f in manager.feeds.values() if f.settings.device == s.device), None)
    same = feed is not None and (feed.settings.device, feed.settings.width, feed.settings.height,
                                 feed.settings.exposure) == (s.device, s.width, s.height, s.exposure)
    if same:
        if not feed.running:
            feed.poll()
        with feed.lock:
            raw = None if feed.raw is None else feed.raw.copy()
        if raw is None:
            raise CameraUnavailable(feed.error or "sin imagen")
    else:
        if feed is not None:
            feed._close()  # libera el dispositivo para abrirlo con los ajustes nuevos
        raw = grab_once(s, raw=True)
    if stage == "raw":
        return raw
    if stage == "rotated":
        return process(raw, s.model_copy(update={"warp": None}))
    return process(raw, s)
