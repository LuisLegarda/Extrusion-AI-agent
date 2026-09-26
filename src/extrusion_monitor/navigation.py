"""Recorrido automático por las pantallas del HMI (macro de navegación con clics verificados).

Seguridad:
* Solo se hace clic en puntos grabados por el usuario, y solo si la imagen del botón
  coincide con la grabada (evita hacer clic sobre otro control si la pantalla cambió).
* El recorrido solo empieza si el HMI está en la pantalla principal y cada paso
  verifica la pantalla de llegada; ante cualquier discrepancia se detiene.
* Si el operador usa el mouse o el teclado, el recorrido se pospone o se interrumpe
  sin hacer más clics.
"""
from __future__ import annotations

import logging
import os
import sys
import time
from dataclasses import dataclass, field
from typing import Callable, Optional, Protocol

import numpy as np

from .capture import FrameSource, crop, load_png, similarity
from .config import AppConfig, Click, Rect, Workspace
from .pages import PageDetector

log = logging.getLogger(__name__)


class TourAborted(Exception):
    pass


class Clicker(Protocol):
    def click(self, x: int, y: int) -> None:
        """Clic izquierdo en coordenadas de la captura."""
        ...

    def idle_seconds(self) -> float:
        """Segundos desde la última entrada del operador (mouse/teclado)."""
        ...


def click_rect(c: Click) -> Rect:
    h = c.patch // 2
    return Rect(x=c.x - h, y=c.y - h, w=c.patch, h=c.patch)


def patch_matches(frame: np.ndarray, c: Click, patch: Optional[np.ndarray]) -> float:
    """Coincidencia 0..1 entre la zona actual del botón y la imagen grabada."""
    if patch is None:
        return 0.0
    return similarity(crop(frame, click_rect(c)), patch)


@dataclass
class TourResult:
    ok: bool
    started: float
    duration_s: float = 0.0
    pages_read: list[str] = field(default_factory=list)
    message: str = ""
    skipped: bool = False  # no se inició (operador activo o fuera de la pantalla principal)


class TourRunner:
    def __init__(self, config: AppConfig, workspace: Workspace, source: FrameSource, clicker: Clicker,
                 pages: PageDetector, clock: Callable[[], float] = time.time,
                 sleep: Callable[[float], None] = time.sleep,
                 patches: Optional[dict[str, np.ndarray]] = None):
        self.config = config
        self.source = source
        self.clicker = clicker
        self.pages = pages
        self.clock = clock
        self.sleep = sleep
        if patches is None:
            patches = {c.id: load_png(workspace.click_patch_file(c.id)) for c in config.tour.all_clicks()}
        self.patches = patches
        self.last_run: Optional[float] = None
        self.last_result: Optional[TourResult] = None
        self._own_input_at = 0.0

    @property
    def settings(self):
        return self.config.tour

    def due(self, now: float) -> bool:
        t = self.settings
        if not (t.enabled and t.steps and t.home_page):
            return False
        return self.last_run is None or now - self.last_run >= t.interval_s

    def run(self, on_frame: Callable[[np.ndarray], None], stop: Callable[[], bool] = lambda: False) -> TourResult:
        """Ejecuta el recorrido. `on_frame` recibe la captura de cada pantalla alcanzada."""
        t = self.settings
        started = self.clock()
        self.last_run = started
        res = TourResult(ok=False, started=started)
        idle = self.clicker.idle_seconds()
        if idle < t.idle_required_s:
            res.skipped = True
            res.message = f"pospuesto: operador activo hace {idle:.0f} s"
            return self._finish(res)
        frame = self.source.grab()
        if t.home_page not in self.pages.visible_pages(frame):
            res.skipped = True
            res.message = "pospuesto: el HMI no está en la pantalla principal"
            return self._finish(res)
        on_frame(frame)
        self._mark_own_input()  # referencia: desde aquí cualquier entrada ajena es del operador
        left_home = False
        try:
            for i, step in enumerate(t.steps, 1):
                if stop():
                    raise TourAborted("detenido")
                frame = self._clicks(step.clicks, frame, f"paso {i}")
                left_home = True
                frame = self._arrive(step.page, step.settle_s, f"paso {i}")
                on_frame(frame)
                res.pages_read.append(step.page)
            frame = self._clicks(t.home_clicks, frame, "regreso")
            self._arrive(t.home_page, t.home_settle_s, "regreso")
            left_home = False
            res.ok = True
            res.message = f"{len(res.pages_read)} pantallas leídas"
        except TourAborted as exc:
            res.message = f"interrumpido: {exc}"
            if left_home and "operador" not in str(exc):
                res.message += self._try_return_home()
        return self._finish(res)

    def _finish(self, res: TourResult) -> TourResult:
        res.duration_s = self.clock() - res.started
        self.last_result = res
        return res

    def _clicks(self, clicks: list[Click], frame: np.ndarray, where: str) -> np.ndarray:
        for n, c in enumerate(clicks, 1):
            score = patch_matches(frame, c, self.patches.get(c.id))
            if score < c.match_threshold:
                raise TourAborted(f"{where}, clic {n}: el botón no coincide con el grabado ({score:.2f})")
            self._check_operator()
            self.clicker.click(c.x, c.y)
            self._mark_own_input()
            if n < len(clicks):
                self.sleep(0.6)
                frame = self.source.grab()
        return frame

    def _arrive(self, page_id: str, settle_s: float, where: str) -> np.ndarray:
        page = self.config.page(page_id)
        for _attempt in range(self.settings.page_retries + 1):
            self.sleep(settle_s)
            self._check_operator()
            frame = self.source.grab()
            if page_id in self.pages.visible_pages(frame):
                return frame
        name = page.name if page else page_id
        raise TourAborted(f"{where}: no se llegó a «{name}»")

    def _try_return_home(self) -> str:
        """Tras un fallo, intenta volver a la principal solo si los botones de regreso coinciden."""
        try:
            frame = self.source.grab()
            self._clicks(self.settings.home_clicks, frame, "regreso de emergencia")
            self._arrive(self.settings.home_page, self.settings.home_settle_s, "regreso de emergencia")
            return " · se regresó a la pantalla principal"
        except TourAborted as exc:
            return f" · no se pudo regresar a la principal ({exc})"

    def _mark_own_input(self) -> None:
        self._own_input_at = self.clock()

    def _check_operator(self) -> None:
        # Nuestros clics también cuentan como entrada: hay actividad ajena si la última entrada
        # es posterior a nuestro último clic.
        idle = self.clicker.idle_seconds()
        since_own = self.clock() - self._own_input_at
        if idle + 0.5 < since_own:
            raise TourAborted("el operador está usando el HMI")


class WindowsClicker:
    """Clics reales en Windows. Las coordenadas de la captura se trasladan al escritorio."""

    def __init__(self, offset: tuple[int, int] = (0, 0)):
        if sys.platform != "win32":
            raise RuntimeError("Solo disponible en Windows")
        import ctypes
        from ctypes import wintypes

        self.ctypes, self.wintypes = ctypes, wintypes
        self.user32 = ctypes.windll.user32
        self.kernel32 = ctypes.windll.kernel32
        self.offset = offset
        self.pid = os.getpid()

    def _screen(self, x: int, y: int) -> tuple[int, int]:
        return x + self.offset[0], y + self.offset[1]

    def _covered_by_us(self, sx: int, sy: int) -> bool:
        pt = self.wintypes.POINT(sx, sy)
        hwnd = self.user32.WindowFromPoint(pt)
        if not hwnd:
            return False
        pid = self.wintypes.DWORD()
        self.user32.GetWindowThreadProcessId(hwnd, self.ctypes.byref(pid))
        return pid.value == self.pid

    def click(self, x: int, y: int) -> None:
        sx, sy = self._screen(x, y)
        if self._covered_by_us(sx, sy):
            raise TourAborted(f"la ventana del monitor tapa el botón en ({x}, {y}); muévela o minimízala")
        prev = self.wintypes.POINT()
        self.user32.GetCursorPos(self.ctypes.byref(prev))
        self.user32.SetCursorPos(sx, sy)
        MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP = 0x0002, 0x0004
        self.user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
        time.sleep(0.05)
        self.user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
        time.sleep(0.05)
        self.user32.SetCursorPos(prev.x, prev.y)

    def idle_seconds(self) -> float:
        class LASTINPUTINFO(self.ctypes.Structure):
            _fields_ = [("cbSize", self.wintypes.UINT), ("dwTime", self.wintypes.DWORD)]

        info = LASTINPUTINFO()
        info.cbSize = self.ctypes.sizeof(LASTINPUTINFO)
        if not self.user32.GetLastInputInfo(self.ctypes.byref(info)):
            return 0.0
        ticks = self.kernel32.GetTickCount() & 0xFFFFFFFF
        return ((ticks - info.dwTime) & 0xFFFFFFFF) / 1000.0


class UnavailableClicker:
    """Usado donde no hay clics reales disponibles: el recorrido nunca se inicia."""

    def click(self, x: int, y: int) -> None:
        raise TourAborted("los clics automáticos solo están disponibles en Windows")

    def idle_seconds(self) -> float:
        return 0.0


def exclude_window_from_capture(win_id: int) -> bool:
    """Evita que la ventana del monitor aparezca en la captura (Windows 10 2004+)."""
    if sys.platform != "win32":
        return False
    try:
        import ctypes
        WDA_EXCLUDEFROMCAPTURE = 0x11
        return bool(ctypes.windll.user32.SetWindowDisplayAffinity(int(win_id), WDA_EXCLUDEFROMCAPTURE))
    except Exception:  # pragma: no cover
        return False
