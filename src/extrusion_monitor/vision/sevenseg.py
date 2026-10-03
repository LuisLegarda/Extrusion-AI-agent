"""Lectura de displays de 7 segmentos (LED o LCD), típicos de controladores y sensores de equipos antiguos.

El OCR general falla con estos dígitos (los segmentos no se tocan y muchos van inclinados), así que se
decodifican directamente: se binariza, se corrige la inclinación, se separan los dígitos y se mira qué
segmentos están encendidos.

Segmentos:   ─a─
            f   b
             ─g─
            e   c
             ─d─   · (punto decimal)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import cv2
import numpy as np

SEGS = "abcdefg"
PATTERNS: dict[tuple[int, ...], str] = {
    (1, 1, 1, 1, 1, 1, 0): "0", (0, 1, 1, 0, 0, 0, 0): "1", (1, 1, 0, 1, 1, 0, 1): "2",
    (1, 1, 1, 1, 0, 0, 1): "3", (0, 1, 1, 0, 0, 1, 1): "4", (1, 0, 1, 1, 0, 1, 1): "5",
    (1, 0, 1, 1, 1, 1, 1): "6", (1, 1, 1, 0, 0, 0, 0): "7", (1, 1, 1, 0, 0, 1, 0): "7",
    (1, 1, 1, 1, 1, 1, 1): "8", (1, 1, 1, 1, 0, 1, 1): "9", (1, 1, 1, 0, 0, 1, 1): "9",
    (0, 0, 0, 0, 0, 0, 1): "-", (1, 0, 0, 1, 1, 1, 1): "E", (0, 0, 0, 0, 1, 0, 1): "r",
    (0, 1, 1, 0, 1, 1, 1): "H", (0, 0, 0, 1, 1, 1, 0): "L", (1, 1, 0, 0, 1, 1, 1): "P",
    (1, 0, 0, 0, 1, 1, 1): "F", (1, 0, 0, 1, 1, 1, 0): "C", (0, 0, 1, 1, 1, 0, 1): "o",
    (1, 1, 1, 0, 1, 1, 1): "A", (0, 0, 1, 1, 1, 1, 1): "b", (0, 1, 1, 1, 1, 0, 1): "d",
    (0, 0, 1, 0, 1, 0, 1): "n", (0, 0, 1, 1, 1, 0, 0): "u", (0, 0, 0, 1, 1, 0, 1): "c",
}
# En un valor numérico, las letras que comparten forma con un dígito se leen como el dígito.
NUMERIC = {"b": "6", "o": "0", "O": "0", "S": "5"}
WORK_H = 90  # alto de trabajo de la banda de dígitos (px)


@dataclass
class SegResult:
    text: str = ""
    confidence: float = 0.0
    digits: list = field(default_factory=list)  # (carácter, confianza, caja x0, x1, segmentos)
    slant: float = 0.0
    polarity: str = ""
    debug: Optional[np.ndarray] = None  # imagen binaria con las cajas, para el configurador


def _channel(img: np.ndarray) -> np.ndarray:
    """Brillo por el canal máximo: un LED rojo o verde queda brillante (en gris se vería oscuro)."""
    return img.max(axis=2) if img.ndim == 3 else img


def binarize(img: np.ndarray, polarity: str = "auto") -> tuple[np.ndarray, str]:
    v = _channel(img)
    h = max(1, v.shape[0])
    f = float(np.clip(WORK_H * 1.3 / h, 0.5, 10.0))
    v = cv2.resize(v, None, fx=f, fy=f, interpolation=cv2.INTER_CUBIC if f > 1 else cv2.INTER_AREA)
    v = cv2.GaussianBlur(v, (3, 3), 0)
    _, bright = cv2.threshold(v, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    if polarity == "auto":
        polarity = "light" if (bright > 0).mean() < 0.5 else "dark"  # los segmentos son la minoría
    mask = bright if polarity == "light" else cv2.bitwise_not(bright)
    # Marcos y bordes del display: componentes muy anchos o pegados a todo un borde.
    n, lab, stats, _ = cv2.connectedComponentsWithStats(mask, 8)
    H, W = mask.shape
    for i in range(1, n):
        x, y, w, hh, area = stats[i]
        if w > 0.85 * W or hh > 0.97 * H or area < 0.0004 * H * W:
            mask[lab == i] = 0
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
    return mask, polarity


def _shear(mask: np.ndarray, deg: float) -> np.ndarray:
    """Quita una inclinación de `deg` grados (positiva = lo de arriba va a la derecha)."""
    if abs(deg) < 1e-3:
        return mask
    h, w = mask.shape
    k = float(np.tan(np.radians(deg)))
    pad = int(abs(k) * h) + 2
    m = np.float32([[1, k, -k * h / 2 + pad / 2], [0, 1, 0]])
    return cv2.warpAffine(mask, m, (w + pad, h), flags=cv2.INTER_NEAREST)


def _band(mask: np.ndarray) -> Optional[tuple[int, int]]:
    rows = (mask > 0).sum(axis=1)
    on = rows > max(2, 0.01 * mask.shape[1])
    if not on.any():
        return None
    # banda continua más alta (tolera huecos pequeños entre segmentos)
    best, start, gap = None, None, 0
    tol = max(2, mask.shape[0] // 25)
    for i, o in enumerate(list(on) + [False] * (tol + 1)):
        if o:
            start = i if start is None else start
            gap = 0
        elif start is not None:
            gap += 1
            if gap > tol:
                end = i - gap + 1
                if best is None or end - start > best[1] - best[0]:
                    best = (start, end)
                start, gap = None, 0
    return best


def _slant_score(mask: np.ndarray) -> float:
    """Con la inclinación corregida los segmentos verticales caen en pocas columnas: proyección más «picuda»."""
    cols = (mask > 0).sum(axis=0).astype(np.float64)
    total = cols.sum()
    return float((cols ** 2).sum() / total) if total else -1.0


def estimate_slant(mask: np.ndarray) -> float:
    scores = {deg: _slant_score(_shear(mask, deg)) for deg in range(-24, 25, 2)}
    best = max(scores, key=lambda d: (round(scores[d], 3), -abs(d)))
    fine = {d / 2: _slant_score(_shear(mask, d / 2)) for d in range(2 * best - 3, 2 * best + 4)}
    return float(max(fine, key=lambda d: (round(fine[d], 3), -abs(d))))


def _groups(cols: np.ndarray, gap: int) -> list[list[int]]:
    runs, start = [], None
    for i, c in enumerate(list(cols) + [0]):
        if c and start is None:
            start = i
        elif not c and start is not None:
            runs.append([start, i])
            start = None
    merged: list[list[int]] = []
    for r in runs:
        if merged and r[0] - merged[-1][1] <= gap:
            merged[-1][1] = r[1]
        else:
            merged.append(r)
    return merged


def _segments(cell: np.ndarray) -> tuple[tuple[int, ...], float]:
    """Estado de los 7 segmentos de una celda (alto = banda de dígitos) y certeza 0..1."""
    h, w = cell.shape
    on = cell > 0

    def hline(y0, y1):  # mejor fila: fracción encendida en la franja central
        sub = on[int(y0 * h):max(int(y0 * h) + 1, int(y1 * h)), int(0.2 * w):max(int(0.2 * w) + 1, int(0.8 * w))]
        return float(sub.mean(axis=1).max()) if sub.size else 0.0

    def vline(x0, x1, y0, y1):
        sub = on[int(y0 * h):max(int(y0 * h) + 1, int(y1 * h)), int(x0 * w):max(int(x0 * w) + 1, int(x1 * w))]
        return float(sub.mean(axis=0).max()) if sub.size else 0.0

    fills = [hline(0, 0.2), vline(0.6, 1, 0.12, 0.45), vline(0.6, 1, 0.55, 0.88), hline(0.8, 1),
             vline(0, 0.4, 0.55, 0.88), vline(0, 0.4, 0.12, 0.45), hline(0.38, 0.62)]
    bits = tuple(int(f >= 0.5) for f in fills)
    certainty = float(np.mean([min(1.0, abs(f - 0.5) * 3) for f in fills]))
    return bits, certainty


def _nearest(bits: tuple[int, ...]) -> tuple[str, int]:
    best, dist = "?", 99
    for pat, ch in PATTERNS.items():
        d = sum(a != b for a, b in zip(pat, bits))
        if d < dist:
            best, dist = ch, d
    return best, dist


def decode(img: np.ndarray, polarity: str = "auto", slant: Optional[float] = None,
           digits: Optional[int] = None, numeric: bool = True, debug: bool = False) -> SegResult:
    res = SegResult()
    if img is None or img.size == 0 or min(img.shape[:2]) < 6:
        return res
    mask, res.polarity = binarize(img, polarity)
    band = _band(mask)
    if band is None:
        return res
    # se recorta a la banda antes de estimar la inclinación (el ruido de arriba/abajo no estorba)
    mask = mask[band[0]:band[1]]
    res.slant = estimate_slant(mask) if slant is None else float(slant)
    m = _shear(mask, res.slant)
    band = _band(m)
    if band is None:
        return res
    top, bot = band
    H = bot - top
    if H < 8:
        return res
    m = m[top:bot].copy()
    # Los dígitos se separan con la parte de arriba (sin los puntos decimales, que van abajo y a veces
    # tocan el dígito siguiente); los puntos son lo que queda abajo fuera de los dígitos.
    gap = max(2, int(0.07 * H))
    groups = _groups(m[:int(0.7 * H)].any(axis=0), gap)
    inside = np.zeros(m.shape[1], bool)
    for x0, x1 in groups:
        inside[x0:x1] = True
    low = m[int(0.7 * H):].any(axis=0) & ~inside
    dots = [(x0 + x1) / 2 for x0, x1 in _groups(low, 1) if 1 < x1 - x0 < 0.3 * H]
    out, confs, cells = [], [], []
    for x0, x1 in groups:
        sub = m[:, x0:x1]
        ys = np.where(sub.any(axis=1))[0]
        if ys.size == 0:
            continue
        gy0, gy1 = ys[0] / H, (ys[-1] + 1) / H
        gw = (x1 - x0) / H
        gh = gy1 - gy0
        if gh < 0.3:
            if 0.25 < (gy0 + gy1) / 2 < 0.75 and gw > 0.15:
                out.append("-")
                confs.append(0.9)
                cells.append(("-", x0, x1))
            continue  # dos puntos o ruido
        if gw < 0.3 and gh > 0.6:
            ch, c = "1", 1.0
        else:
            bits, cert = _segments(m[:, x0:x1])
            ch = PATTERNS.get(bits)
            if ch is None:
                ch, dist = _nearest(bits)
                c = 0.45 * cert if dist == 1 else 0.0
                if dist > 1:
                    ch = "?"
            else:
                c = 0.6 + 0.4 * cert
        if numeric:
            ch = NUMERIC.get(ch, ch)
        out.append(ch)
        confs.append(c)
        cells.append((ch, x0, x1))
    # cada punto va después del último dígito que empieza a su izquierda
    for dx in sorted(dots, reverse=True):
        k = max((i for i, cell in enumerate(cells) if cell[1] < dx), default=None)
        if k is not None and k < len(cells) - 1:
            out.insert(k + 1, ".")
            cells.insert(k + 1, (".", int(dx), int(dx) + 1))
            confs.append(1.0)
    text = "".join(out).strip(".")
    if numeric:
        text = text.replace("..", ".")
    n_digits = sum(ch.isalnum() for ch in text)
    conf = float(np.mean(confs)) if confs else 0.0
    if digits and n_digits > digits:
        conf *= 0.5
    if "?" in text or not n_digits:
        conf = min(conf, 0.3)
    res.text, res.confidence, res.digits = text, conf, cells
    if debug:
        dbg = cv2.cvtColor(m, cv2.COLOR_GRAY2BGR)
        for cell in cells:
            cv2.rectangle(dbg, (cell[1], 0), (max(cell[1] + 1, cell[2] - 1), H - 1),
                          (0, 200, 0) if cell[0] != "?" else (0, 0, 255), 1)
        res.debug = dbg
    return res


# --- dibujo (demo y pruebas) ----------------------------------------------------------------------
def segment_polys(x: float, y: float, h: float, slant_deg: float = 0.0) -> dict[str, np.ndarray]:
    """Polígonos de los 7 segmentos de un dígito de alto h con esquina superior izquierda (x, y)."""
    w, t = 0.55 * h, 0.12 * h
    k = np.tan(np.radians(slant_deg))
    g = 0.02 * h

    def P(px, py):
        return [x + px + k * (h - py), y + py]  # inclinación: lo de arriba se desplaza a la derecha

    def hseg(yc):
        return [P(t / 2 + g, yc), P(t + g, yc - t / 2), P(w - t - g, yc - t / 2), P(w - t / 2 - g, yc),
                P(w - t - g, yc + t / 2), P(t + g, yc + t / 2)]

    def vseg(xc, y0, y1):
        return [P(xc, y0 + g), P(xc + t / 2, y0 + t / 2 + g), P(xc + t / 2, y1 - t / 2 - g), P(xc, y1 - g),
                P(xc - t / 2, y1 - t / 2 - g), P(xc - t / 2, y0 + t / 2 + g)]

    segs = {"a": hseg(t / 2), "g": hseg(h / 2), "d": hseg(h - t / 2),
            "f": vseg(t / 2, t / 2, h / 2), "b": vseg(w - t / 2, t / 2, h / 2),
            "e": vseg(t / 2, h / 2, h - t / 2), "c": vseg(w - t / 2, h / 2, h - t / 2)}
    return {k2: np.array(v, np.int32) for k2, v in segs.items()}


_CHAR_BITS = {}
for _pat, _ch in PATTERNS.items():
    _CHAR_BITS.setdefault(_ch, _pat)
_CHAR_BITS[" "] = (0,) * 7


def draw_text(img: np.ndarray, text: str, x: int, y: int, h: int, on=(40, 40, 255), off=None,
              slant: float = 8.0, pitch: float = 0.75) -> None:
    """Dibuja `text` como display de 7 segmentos (on/off en BGR; off=None no dibuja los apagados)."""
    cx = float(x)
    for i, ch in enumerate(text):
        if ch == ".":
            r = max(2, int(0.07 * h))
            cv2.circle(img, (int(cx - 0.08 * h), int(y + h - r)), r, on, -1, cv2.LINE_AA)
            continue
        bits = _CHAR_BITS.get(ch, (0,) * 7)
        for s, poly in segment_polys(cx, y, h, slant).items():
            lit = bits[SEGS.index(s)]
            if lit or off is not None:
                cv2.fillPoly(img, [poly], on if lit else off, cv2.LINE_AA)
        cx += pitch * h
