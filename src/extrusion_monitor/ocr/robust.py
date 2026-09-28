"""Lectura robusta: varias variantes de preprocesado con votación y memoria por variable.

Un umbral fijo funciona con un fondo/color y falla cuando cambian (campo resaltado,
valor que se pone rojo en alarma, compresión del escritorio remoto, antialiasing).
Aquí cada lectura puede probar varias formas de preparar la imagen; se acepta el valor
cuando es plausible y, si hay duda, cuando varias variantes coinciden. La variante que
funcionó se recuerda por variable y se prueba primero en el siguiente ciclo.
"""
from __future__ import annotations

import re
from collections import Counter, deque
from dataclasses import dataclass, field
from typing import Callable, Iterator, Optional

import cv2
import numpy as np

from ..config import Variable
from .base import OcrResult, clear_border, parse_number

TARGET_TEXT_H = 44  # alto de texto al que se normaliza antes del OCR
PAD = 10

# Variante = (gris, binarización, suavizado). Orden: primero lo que suele funcionar en HMI.
DEFAULT_ORDER = [("lum", "otsu", False), ("lum", "otsu", True), ("lum", "adaptive", False),
                 ("lum", "raw", False), ("min", "otsu", False), ("lum", "adaptive", True),
                 ("min", "adaptive", False), ("lum", "raw", True), ("max", "otsu", False)]


def to_gray(img: np.ndarray, mode: str) -> np.ndarray:
    if img.ndim == 2:
        return img
    if mode == "min":  # texto de color (p. ej. azul) sobre fondo claro queda oscuro
        return img.min(axis=2)
    if mode == "max":  # texto claro sobre fondo de color
        return img.max(axis=2)
    return cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)


def dark_background(gray: np.ndarray) -> bool:
    """El fondo es el tono más frecuente; si es más oscuro que el promedio, el texto es claro."""
    hist = np.bincount((gray // 16).ravel(), minlength=16)
    mode = (int(np.argmax(hist)) + 0.5) * 16
    return mode < float(gray.mean())


def prepare(img: np.ndarray, gray_mode: str, bin_mode: str, scale: Optional[float] = None,
            threshold: Optional[int] = None, clear: bool = True, smooth: bool = False) -> Optional[np.ndarray]:
    """Imagen lista para el OCR: texto oscuro sobre blanco, recortada al texto y escalada."""
    gray = to_gray(img, gray_mode)
    if gray.size == 0:
        return None
    if scale is None:
        scale = max(1.0, min(6.0, TARGET_TEXT_H / max(1, gray.shape[0] * 0.7)))
    if scale != 1.0:
        gray = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    if dark_background(gray):
        gray = 255 - gray
    if smooth:
        # Quita ruido de compresión (escritorio remoto) y antialiasing antes de binarizar.
        # Gaussiano suave: la mediana borraría los puntos decimales pequeños.
        gray = cv2.GaussianBlur(gray, (3, 3), 0)
    if threshold is not None:
        _, out = cv2.threshold(gray, threshold, 255, cv2.THRESH_BINARY)
    elif bin_mode == "otsu":
        _, out = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    elif bin_mode == "adaptive":
        block = max(11, (gray.shape[0] // 2) | 1)
        out = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, block, 10)
    else:  # raw: gris con contraste estirado, el motor decide
        lo, hi = np.percentile(gray, (2, 98))
        out = np.clip((gray.astype(np.float32) - lo) * 255.0 / max(hi - lo, 1), 0, 255).astype(np.uint8)
    mask = out < 128
    if clear:
        binary = np.where(mask, 0, 255).astype(np.uint8)
        cleared = clear_border(binary)
        removed = (binary == 0) & (cleared == 255)
        out = np.where(removed, 255, out).astype(np.uint8)
        mask = out < 128
    ys, xs = np.nonzero(mask)
    if len(ys) == 0:
        return None
    y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
    out = out[y0:y1, x0:x1]
    h = out.shape[0]
    if h < TARGET_TEXT_H * 0.6 or h > TARGET_TEXT_H * 1.8:
        f = TARGET_TEXT_H / max(h, 1)
        out = cv2.resize(out, None, fx=f, fy=f, interpolation=cv2.INTER_CUBIC if f > 1 else cv2.INTER_AREA)
    return cv2.copyMakeBorder(out, PAD, PAD, PAD, PAD, cv2.BORDER_CONSTANT, value=255)


@dataclass
class RobustResult:
    text: str
    value: Optional[float]
    confidence: float
    variant: Optional[tuple]
    tried: int
    votes: int = 0
    candidates: dict = field(default_factory=dict)  # valor -> votos (diagnóstico)


class RobustReader:
    def __init__(self, engine, max_variants: int = 6):
        self.engine = engine
        self.max_variants = max_variants
        self.preferred: dict[str, tuple] = {}
        self.history: dict[str, deque[bool]] = {}

    def quality(self, var_id: str) -> Optional[float]:
        h = self.history.get(var_id)
        return None if not h else 100.0 * sum(h) / len(h)

    def _record(self, var_id: str, ok: bool) -> None:
        self.history.setdefault(var_id, deque(maxlen=100)).append(ok)

    def _variants(self, var: Variable) -> Iterator[tuple]:
        seen = set()
        first = self.preferred.get(var.id)
        order = ([first] if first else []) + DEFAULT_ORDER
        for v in order:
            if v not in seen:
                seen.add(v)
                yield v

    def _ocr(self, img: np.ndarray, var: Variable, variant: tuple, numeric: bool) -> Optional[OcrResult]:
        o = var.ocr
        prep = prepare(img, variant[0], variant[1], clear=o.clear_border, smooth=variant[2],
                       threshold=o.threshold if variant[:2] == ("lum", "otsu") and not variant[2] else None)
        if prep is None:
            return None
        if getattr(self.engine, "name", "") == "template":
            prep = np.where(prep < 128, 0, 255).astype(np.uint8)  # plantillas: solo binario
        reader = getattr(self.engine, "read_binary", None)
        if reader is None:
            return self.engine.read(img, numeric, o)
        return reader(prep, numeric)

    def read_number(self, img: np.ndarray, var: Variable, previous: Optional[float],
                    plausible: Callable[[float], bool], exhaustive: bool = False,
                    decimals: Optional[int] = None) -> RobustResult:
        """`plausible(v)`: rango válido. `decimals`: decimales esperados (declarados o aprendidos)."""
        if var.decimals is not None:
            decimals = var.decimals
        votes: Counter = Counter()
        families: dict[float, set] = {}
        texts: dict[float, str] = {}
        first_variant: dict[float, tuple] = {}
        tried = 0
        limit = len(DEFAULT_ORDER) + 1 if exhaustive else self.max_variants
        for variant in self._variants(var):
            if tried >= limit:
                break
            tried += 1
            res = self._ocr(img, var, variant, True)
            if res is None or not res.text or res.confidence < 0.3:
                continue
            if re.search(r"[0-9.,]\?+[0-9]", res.text):
                continue
            value = parse_number(res.text, var)
            if value is None or not plausible(value):
                continue
            if decimals is not None and not var.fix_missing_decimal and decimals_of(res.text) != decimals:
                continue  # p. ej. «77» cuando el HMI muestra «7.7»: se perdió el punto
            family = variant[:2]  # con/sin suavizado cuentan como una sola opinión
            if family in families.setdefault(value, set()):
                continue
            families[value].add(family)
            votes[value] += 1
            texts.setdefault(value, res.text)
            first_variant.setdefault(value, variant)
            if exhaustive:
                continue
            # Vía rápida: el valor no cambió respecto a la lectura anterior (caso normal en un HMI).
            if tried == 1 and previous is not None and _small_change(value, previous, res.text, decimals):
                break
            if votes[value] >= 2:
                break
        if not votes:
            self._record(var.id, False)
            return RobustResult("", None, 0.0, None, tried)
        best = max(votes, key=lambda v: (votes[v], -abs(v - previous) if previous is not None else 0))
        n = votes[best]
        unchanged = previous is not None and tried == 1 and _small_change(best, previous, texts[best], decimals)
        if n < 2 and not unchanged and not (exhaustive and len(votes) == 1):
            # Un valor nuevo debe confirmarlo una segunda variante; si no, se conserva el anterior.
            self._record(var.id, False)
            return RobustResult(texts[best], None, 0.3, None, tried, n, dict(votes))
        self.preferred[var.id] = first_variant[best]
        self._record(var.id, True)
        conf = 0.95 if n >= 2 else 0.85
        return RobustResult(texts[best], best, conf, first_variant[best], tried, n, dict(votes))

    def read_text(self, img: np.ndarray, var: Variable, accept: Callable[[str], bool] | None = None) -> RobustResult:
        """Texto: primera variante legible (y aceptada, p. ej. nombre de receta conocido)."""
        tried = 0
        fallback = None
        for variant in self._variants(var):
            if tried >= self.max_variants:
                break
            tried += 1
            res = self._ocr(img, var, variant, False)
            text = (res.text or "").strip() if res else ""
            if not text or "?" in text:
                continue
            if accept is None or accept(text):
                self.preferred[var.id] = variant
                self._record(var.id, True)
                return RobustResult(text, None, 0.9, variant, tried, 1)
            fallback = fallback or (text, variant)
        if fallback:
            self._record(var.id, True)
            return RobustResult(fallback[0], None, 0.7, fallback[1], tried, 1)
        self._record(var.id, False)
        return RobustResult("", None, 0.0, None, tried)


def _small_change(value: float, previous: float, text: str, decimals: Optional[int]) -> bool:
    """Cambio pequeño y coherente (fluctuación normal del proceso): se acepta sin segunda variante.

    Los errores típicos de OCR (un dígito cambiado en las decenas, punto decimal perdido)
    producen saltos grandes o cambian los decimales, y no pasan este filtro.
    """
    if decimals is not None and decimals_of(text) != decimals:
        return False
    step = 10 ** -(decimals if decimals is not None else decimals_of(text))
    return abs(value - previous) <= max(abs(previous) * 0.02, 3 * step)


def _close(value: float, previous: float, var: Variable) -> bool:
    if var.max_step is not None:
        return abs(value - previous) <= var.max_step
    return abs(value - previous) <= max(abs(previous) * 0.25, 1.0)


def decimals_of(text: str) -> int:
    m = re.search(r"\d[.,](\d+)", text.replace(" ", ""))
    return len(m.group(1)) if m else 0
