"""OCR por plantillas de caracteres enseñadas por el usuario.

Los HMI usan fuentes fijas y nítidas, por lo que comparar cada carácter contra
muestras guardadas de la misma pantalla es rápido y muy fiable, sin
dependencias externas. Se enseña indicando el texto que muestra una región.
"""
from __future__ import annotations

import base64
import json
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import cv2
import numpy as np

from ..config import OcrOptions
from .base import OcrResult, preprocess

GLYPH_W, GLYPH_H = 16, 24


@dataclass
class Glyph:
    image: np.ndarray  # GLYPH_H x GLYPH_W float32 en 0..1 (1 = tinta)
    rel_height: float  # alto del carácter / alto de la línea
    rel_top: float  # posición vertical del centro dentro de la línea (0 arriba, 1 abajo)
    aspect: float  # ancho / alto


def segment(binary: np.ndarray) -> list[tuple[int, int, int, int]]:
    """Separa caracteres en una imagen binaria (tinta = 0). Devuelve cajas x, y, w, h."""
    ink = (binary == 0).astype(np.uint8)
    n, _, stats, _ = cv2.connectedComponentsWithStats(ink, connectivity=8)
    boxes = [tuple(int(v) for v in stats[i][:4]) for i in range(1, n)]
    if not boxes:
        return []
    max_h = max(b[3] for b in boxes)
    # Descarta ruido: componentes minúsculos respecto al alto de línea.
    min_area = max(2, int((max_h * 0.08) ** 2))
    boxes = [b for b in boxes if b[2] * b[3] >= min_area or b[3] >= max_h * 0.3]
    boxes.sort(key=lambda b: b[0])
    # Une componentes que se solapan horizontalmente (p. ej. segmentos de un display de 7 segmentos).
    merged: list[list[int]] = []
    for x, y, w, h in boxes:
        if merged:
            mx, my, mw, mh = merged[-1]
            overlap = min(mx + mw, x + w) - max(mx, x)
            v_overlap = min(my + mh, y + h) - max(my, y)
            # Partes de un mismo carácter se apilan en vertical; caracteres vecinos comparten altura.
            inside = mx <= x and x + w <= mx + mw and my <= y and y + h <= my + mh
            if overlap > 0.3 * min(mw, w) and (v_overlap < 0.5 * min(mh, h) or inside):
                nx, ny = min(mx, x), min(my, y)
                merged[-1] = [nx, ny, max(mx + mw, x + w) - nx, max(my + mh, y + h) - ny]
                continue
        merged.append([x, y, w, h])
    return [tuple(b) for b in merged]


def _line_extent(boxes) -> tuple[int, int]:
    top = min(b[1] for b in boxes)
    bottom = max(b[1] + b[3] for b in boxes)
    return top, max(1, bottom - top)


def extract_glyphs(binary: np.ndarray) -> list[Glyph]:
    boxes = segment(binary)
    if not boxes:
        return []
    top, line_h = _line_extent(boxes)
    glyphs = []
    for x, y, w, h in boxes:
        crop = (binary[y:y + h, x:x + w] == 0).astype(np.float32)
        side = max(w, h * GLYPH_W / GLYPH_H)
        canvas_w = int(round(side))
        canvas_h = int(round(side * GLYPH_H / GLYPH_W))
        canvas = np.zeros((max(canvas_h, h), max(canvas_w, w)), np.float32)
        oy = (canvas.shape[0] - h) // 2
        ox = (canvas.shape[1] - w) // 2
        canvas[oy:oy + h, ox:ox + w] = crop
        img = cv2.resize(canvas, (GLYPH_W, GLYPH_H), interpolation=cv2.INTER_AREA)
        glyphs.append(Glyph(
            image=img,
            rel_height=h / line_h,
            rel_top=((y + h / 2) - top) / line_h,
            aspect=w / h,
        ))
    return glyphs


def _similarity(a: Glyph, b: Glyph) -> float:
    va = a.image.ravel() - a.image.mean()
    vb = b.image.ravel() - b.image.mean()
    denom = float(np.linalg.norm(va) * np.linalg.norm(vb))
    corr = float(va @ vb) / denom if denom > 1e-9 else (1.0 if np.allclose(a.image, b.image) else 0.0)
    # Penaliza diferencias de tamaño/posición: distinguen '.' de '-' de dígitos.
    penalty = (abs(a.rel_height - b.rel_height) * 0.8
               + abs(a.rel_top - b.rel_top) * 0.8
               + min(abs(np.log((a.aspect + 1e-3) / (b.aspect + 1e-3))), 2.0) * 0.15)
    return corr - penalty


class TemplateOcr:
    name = "template"

    def __init__(self, path: Optional[Path] = None, max_per_char: int = 8):
        self.path = Path(path) if path else None
        self.max_per_char = max_per_char
        self._glyphs: dict[str, list[Glyph]] = {}
        self._lock = threading.Lock()
        if self.path and self.path.exists():
            self.load()

    @property
    def known_chars(self) -> str:
        return "".join(sorted(self._glyphs))

    def teach(self, image: np.ndarray, text: str, opts: OcrOptions) -> int:
        """Aprende los caracteres de `image` sabiendo que muestra `text`. Devuelve cuántos aprendió."""
        chars = [c for c in text if not c.isspace()]
        glyphs = extract_glyphs(preprocess(image, opts))
        if len(glyphs) != len(chars):
            raise ValueError(
                f"Se detectaron {len(glyphs)} caracteres en la imagen pero el texto tiene {len(chars)}. "
                "Ajusta la región o el umbral.")
        with self._lock:
            for ch, g in zip(chars, glyphs):
                lst = self._glyphs.setdefault(ch, [])
                if any(_similarity(g, o) > 0.97 for o in lst):
                    continue
                lst.append(g)
                del lst[:-self.max_per_char]
        if self.path:
            self.save()
        return len(chars)

    def clear(self) -> None:
        with self._lock:
            self._glyphs.clear()
        if self.path:
            self.save()

    def read(self, image: np.ndarray, numeric: bool, opts: OcrOptions | None = None) -> OcrResult:
        opts = opts or OcrOptions()
        glyphs = extract_glyphs(preprocess(image, opts))
        if not glyphs or not self._glyphs:
            return OcrResult("", 0.0)
        text, confs = [], []
        with self._lock:
            for g in glyphs:
                best_ch, best, second = "?", -9.0, -9.0
                for ch, samples in self._glyphs.items():
                    if numeric and not (ch.isdigit() or ch in ".,-+"):
                        continue
                    s = max(_similarity(g, t) for t in samples)
                    if s > best:
                        best_ch, second, best = ch, best, s
                    elif s > second:
                        second = s
                if best > 0.5:
                    text.append(best_ch)
                    confs.append(max(0.0, min(1.0, best)) * (1.0 if second < best - 0.05 else 0.8))
                else:
                    text.append("?")  # p. ej. la unidad dentro del recuadro; no cuenta en la confianza
        return OcrResult("".join(text), float(min(confs)) if confs else 0.0)

    def save(self) -> None:
        data = {
            ch: [{
                "img": base64.b64encode((g.image * 255).astype(np.uint8).tobytes()).decode(),
                "h": g.rel_height, "t": g.rel_top, "a": g.aspect,
            } for g in lst]
            for ch, lst in self._glyphs.items()
        }
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"w": GLYPH_W, "hgt": GLYPH_H, "glyphs": data}), encoding="utf-8")
        tmp.replace(self.path)

    def load(self) -> None:
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        glyphs: dict[str, list[Glyph]] = {}
        for ch, lst in raw.get("glyphs", {}).items():
            for item in lst:
                arr = np.frombuffer(base64.b64decode(item["img"]), np.uint8).reshape(GLYPH_H, GLYPH_W)
                glyphs.setdefault(ch, []).append(
                    Glyph(arr.astype(np.float32) / 255.0, item["h"], item["t"], item["a"]))
        with self._lock:
            self._glyphs = glyphs
