"""Indicadores físicos vistos por cámara (o en pantalla): luces/andon por color, agujas y barras de nivel."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional, Sequence

import cv2
import numpy as np

from ..config import BLINK_SUFFIX, BarOptions, ColorState, GaugeOptions


# --- luces, LED y torres andon -------------------------------------------------------------------
def lamp_feature(img: np.ndarray) -> list[float]:
    """Color de la parte más brillante de la luz (Lab de OpenCV: L 0..255, a/b centrados en 128)."""
    if img is None or img.size == 0:
        return [0.0, 128.0, 128.0]
    if img.ndim == 2:
        img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
    lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB).reshape(-1, 3).astype(np.float32)
    v = img.max(axis=2).reshape(-1)
    k = max(1, int(0.25 * v.size))
    idx = np.argpartition(v, -k)[-k:]
    return [float(x) for x in lab[idx].mean(axis=0)]


def color_distance(a: Sequence[float], b: Sequence[float]) -> float:
    """El tono pesa más que el brillo (la cámara cambia el brillo con la luz del lugar)."""
    return float(np.sqrt(0.35 * (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2))


def classify_color(feat: Sequence[float], states: Iterable[ColorState]) -> tuple[Optional[str], float]:
    best, dist = None, 1e9
    for st in states:
        d = color_distance(feat, st.lab)
        if d < dist:
            best, dist = st.name, d
    return best, (max(0.0, 1.0 - dist / 70.0) if best else 0.0)


def lamp_state(history: Sequence[tuple[float, Sequence[float]]], states: Sequence[ColorState], now: float,
               blink: bool = False, window_s: float = 3.0) -> tuple[Optional[str], float]:
    """Estado de la luz con su historial reciente (ts, color); detecta «X parpadeando»."""
    if not history or not states:
        return None, 0.0
    recent = [(t, f) for t, f in history if t >= now - window_s] or [history[-1]]
    labels = [classify_color(f, states) for _, f in recent]
    last, score = labels[-1]
    if blink and len(states) > 1 and len(labels) >= 4:
        off = min(states, key=lambda c: c.lab[0]).name
        names = [n for n, _ in labels]
        changes = sum(1 for a, b in zip(names, names[1:]) if a != b)
        on = [n for n in names if n != off]
        if changes >= 2 and on and off in names:
            main = max(set(on), key=on.count)
            if on.count(main) >= 0.8 * len(on):
                return main + BLINK_SUFFIX, float(np.mean([s for _, s in labels]))
    # sin parpadeo: lo que se ve en el último medio segundo (evita cambios por un cuadro raro)
    tail = [n for (t, _), (n, _) in zip(recent, labels) if t >= recent[-1][0] - 0.5]
    main = max(set(tail), key=tail.count) if tail else last
    return main, score


# --- agujas (manómetros, termómetros de carátula, tacómetros) ---------------------------------------
@dataclass
class GaugeReading:
    value: Optional[float]
    angle: float
    confidence: float
    profile: Optional[np.ndarray] = None


def _sweep(g: GaugeOptions) -> float:
    s = (g.angle_max - g.angle_min) % 360.0
    return s or 360.0


def gauge_value(img: np.ndarray, g: GaugeOptions) -> GaugeReading:
    if img is None or img.size == 0:
        return GaugeReading(None, 0.0, 0.0)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if img.ndim == 3 else img
    gray = cv2.GaussianBlur(gray, (3, 3), 0).astype(np.float32)
    h, w = gray.shape
    cx, cy = g.cx * w, g.cy * h
    r = g.radius * min(w, h)
    sweep = _sweep(g)
    margin = 6.0
    angles = np.arange(-margin, sweep + margin + 1e-6, 0.5)
    rad = np.radians(g.angle_min + angles)
    ts = np.linspace(0.3, 0.88, 36) * r
    xs = (cx + np.outer(np.cos(rad), ts)).astype(np.float32)
    ys = (cy + np.outer(np.sin(rad), ts)).astype(np.float32)
    samples = cv2.remap(gray, xs, ys, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
    prof = samples.mean(axis=1)
    med = float(np.median(prof))
    noise = 1.4826 * float(np.median(np.abs(prof - med))) + 1.0
    dark, light = med - float(prof.min()), float(prof.max()) - med
    use_dark = g.needle == "dark" or (g.needle == "auto" and dark >= light)
    i = int(np.argmin(prof) if use_dark else np.argmax(prof))
    dev = dark if use_dark else light
    a = float(angles[i])
    if 0 < i < len(prof) - 1:  # interpolación parabólica del pico
        y0, y1, y2 = prof[i - 1], prof[i], prof[i + 1]
        den = y0 - 2 * y1 + y2
        if abs(den) > 1e-6:
            a += 0.5 * float((y0 - y2) / den) * 0.5
    frac = min(1.0, max(0.0, a / sweep))
    conf = float(np.clip(1.0 - 3.0 * noise / max(dev, 1e-6), 0.0, 1.0))
    value = g.value_min + frac * (g.value_max - g.value_min)
    return GaugeReading(value, (g.angle_min + a) % 360.0, conf, prof)


def calibrate_gauge(center: tuple[float, float], p_min: tuple[float, float], p_max: tuple[float, float],
                    size: tuple[int, int], g: GaugeOptions) -> GaugeOptions:
    """Centro y marcas de mínimo y máximo (en px de la región) → parámetros de la aguja."""
    w, h = size
    cx, cy = center
    a0 = float(np.degrees(np.arctan2(p_min[1] - cy, p_min[0] - cx))) % 360
    a1 = float(np.degrees(np.arctan2(p_max[1] - cy, p_max[0] - cx))) % 360
    r = max(np.hypot(p_min[0] - cx, p_min[1] - cy), np.hypot(p_max[0] - cx, p_max[1] - cy))
    return g.model_copy(update=dict(cx=cx / w, cy=cy / h, radius=float(min(2.0, max(0.05, r / min(w, h)))),
                                    angle_min=a0, angle_max=a1, calibrated=True))


# --- barras de nivel y bargraph de LED ------------------------------------------------------------------
@dataclass
class BarReading:
    value: Optional[float]
    fraction: float
    confidence: float


def bar_value(img: np.ndarray, b: BarOptions) -> BarReading:
    if img is None or img.size == 0:
        return BarReading(None, 0.0, 0.0)
    v = (img.max(axis=2) if img.ndim == 3 else img).astype(np.float32)
    v = cv2.GaussianBlur(v, (3, 3), 0)
    if b.direction in ("up", "down"):
        prof = v.mean(axis=1)
        if b.direction == "up":
            prof = prof[::-1]
    else:
        prof = v.mean(axis=0)
        if b.direction == "left":
            prof = prof[::-1]
    lo, hi = float(np.percentile(prof, 5)), float(np.percentile(prof, 95))
    contrast = hi - lo
    if contrast < 20:  # sin borde de nivel: todo apagado (oscuro) o todo encendido (brillante)
        light = b.polarity != "dark"
        if hi < 110:
            frac = 0.0 if light else 1.0
        elif lo > 160:
            frac = 1.0 if light else 0.0
        else:
            return BarReading(None, 0.0, 0.0)
        return BarReading(b.value_min + frac * (b.value_max - b.value_min), frac, 0.6)
    thr = (lo + hi) / 2
    lit = prof > thr
    if b.polarity == "dark":  # p. ej. columna de líquido oscura sobre fondo claro
        lit = ~lit
    idx = np.where(lit)[0]
    frac = 0.0 if idx.size == 0 else (idx[-1] + 1) / len(prof)
    # en un bargraph sólido lo encendido es continuo desde el inicio
    fill = float(lit[: max(1, int(frac * len(prof)))].mean()) if idx.size else 1.0
    conf = float(np.clip(contrast / 80.0, 0, 1)) * (0.5 + 0.5 * fill)
    return BarReading(b.value_min + frac * (b.value_max - b.value_min), float(frac), conf)


# --- dibujo (demo y pruebas) ----------------------------------------------------------------------------
def draw_gauge(img: np.ndarray, cx: int, cy: int, r: int, frac: float, a_min: float = 135.0,
               sweep: float = 270.0) -> None:
    cv2.circle(img, (cx, cy), r, (235, 235, 230), -1, cv2.LINE_AA)
    cv2.circle(img, (cx, cy), r, (60, 60, 60), 3, cv2.LINE_AA)
    for k in range(11):
        a = np.radians(a_min + sweep * k / 10)
        p0 = (int(cx + 0.82 * r * np.cos(a)), int(cy + 0.82 * r * np.sin(a)))
        p1 = (int(cx + 0.95 * r * np.cos(a)), int(cy + 0.95 * r * np.sin(a)))
        cv2.line(img, p0, p1, (40, 40, 40), 2, cv2.LINE_AA)
    a = np.radians(a_min + sweep * frac)
    tip = (int(cx + 0.85 * r * np.cos(a)), int(cy + 0.85 * r * np.sin(a)))
    tail = (int(cx - 0.15 * r * np.cos(a)), int(cy - 0.15 * r * np.sin(a)))
    cv2.line(img, tail, tip, (20, 20, 200), 3, cv2.LINE_AA)
    cv2.circle(img, (cx, cy), max(3, r // 12), (30, 30, 30), -1, cv2.LINE_AA)


def draw_bar(img: np.ndarray, x: int, y: int, w: int, h: int, frac: float, segments: int = 10) -> None:
    cv2.rectangle(img, (x - 3, y - 3), (x + w + 3, y + h + 3), (50, 50, 50), -1)
    sh = h / segments
    lit = int(round(frac * segments))
    for i in range(segments):
        y1 = int(y + h - (i + 1) * sh + 2)
        y2 = int(y + h - i * sh - 2)
        color = ((40, 200, 40) if i < 0.7 * segments else (0, 190, 255) if i < 0.9 * segments else (40, 40, 240)) \
            if i < lit else (45, 55, 45)
        cv2.rectangle(img, (x, y1), (x + w, y2), color, -1)
