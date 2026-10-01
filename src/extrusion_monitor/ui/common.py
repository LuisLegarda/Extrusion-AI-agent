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


def y_range(y, limits) -> Optional[tuple[float, float]]:
    """Escala Y: los límites de la variable (con margen) más los datos visibles.

    Un pico amplía la escala solo mientras está dentro del rango de tiempo mostrado; al salir,
    la escala vuelve a los límites.
    """
    y = np.asarray(y, float)
    y = y[np.isfinite(y)]
    vals = [float(v) for v in limits if v is not None]
    lo, hi = (min(vals), max(vals)) if vals else (None, None)
    if len(y):
        dlo, dhi = float(y.min()), float(y.max())
        lo = dlo if lo is None else min(lo, dlo)
        hi = dhi if hi is None else max(hi, dhi)
    if lo is None:
        return None
    span = hi - lo
    pad = span * 0.1 if span > 0 else max(abs(hi) * 0.05, 1.0)
    return lo - pad, hi + pad


class SeriesCache:
    """Serie de una variable para un rango de tiempo: memoria (ventana de tendencia) o historial (rangos largos)."""

    def __init__(self, engine):
        self.engine = engine
        self._hist: dict = {}

    def get(self, vid: str, range_s: float):
        import time
        t, y = self.engine.series(vid)
        window = self.engine.config.general.trend_window_min * 60
        if range_s <= window or self.engine.historian is None:
            return t, y
        now = time.time()
        key = (vid, range_s)
        cached = self._hist.get(key)
        # El historial se consulta como máximo cada 15 s por variable y rango (no carga la PC).
        if cached is None or now - cached[0] > 15:
            rows = [r for r in self.engine.historian.samples(vid, now - range_s, now + 60) if r[1] is not None]
            arr = np.asarray(rows, float) if rows else np.empty((0, 2))
            cached = (now, arr[:, 0] if len(arr) else np.empty(0), arr[:, 1] if len(arr) else np.empty(0))
            self._hist[key] = cached
        ht, hy = cached[1], cached[2]
        if len(t):
            keep = ht < t[0]
            ht, hy = np.concatenate([ht[keep], t]), np.concatenate([hy[keep], y])
        return ht, hy


class SnapshotBridge(QObject):
    """Pasa instantáneas del hilo de monitoreo al hilo de la interfaz."""

    snapshot = Signal(object)
