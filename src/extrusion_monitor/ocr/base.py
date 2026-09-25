"""Interfaz común de motores OCR, preprocesado y conversión de texto a número."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional, Protocol

import cv2
import numpy as np

from ..config import OcrOptions, Variable


@dataclass
class OcrResult:
    text: str
    confidence: float  # 0..1


class OcrEngine(Protocol):
    name: str

    def read(self, image: np.ndarray, numeric: bool, opts: OcrOptions | None = None) -> OcrResult:
        """Lee el texto de una imagen BGR ya recortada a la región de la variable."""
        ...


class OcrUnavailable(RuntimeError):
    pass


def preprocess(image: np.ndarray, opts: OcrOptions) -> np.ndarray:
    """Devuelve una imagen binaria (texto negro = 0, fondo blanco = 255) escalada."""
    gray = image if image.ndim == 2 else cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    if opts.scale != 1.0:
        gray = cv2.resize(gray, None, fx=opts.scale, fy=opts.scale, interpolation=cv2.INTER_CUBIC)
    if opts.threshold is None:
        _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    else:
        _, binary = cv2.threshold(gray, opts.threshold, 255, cv2.THRESH_BINARY)
    if opts.invert == "yes":
        binary = 255 - binary
    elif opts.invert == "auto":
        # El texto ocupa menos área que el fondo: si predomina lo negro, se invierte.
        if np.count_nonzero(binary == 0) > binary.size / 2:
            binary = 255 - binary
    if opts.clear_border:
        binary = clear_border(binary)
    return binary


def clear_border(binary: np.ndarray) -> np.ndarray:
    """Elimina marcos y líneas que tocan el borde de la región (cajas de campos del HMI).

    Solo se borran componentes que tocan el borde y además son largos (>60 % del ancho o del
    alto), para no perder dígitos que queden rozando el borde de una región ajustada.
    """
    ink = (binary == 0).astype(np.uint8)
    n, labels, stats, _ = cv2.connectedComponentsWithStats(ink, connectivity=8)
    h, w = binary.shape
    out = binary.copy()
    for i in range(1, n):
        x, y, cw, ch, _ = stats[i]
        touches = x == 0 or y == 0 or x + cw >= w or y + ch >= h
        if touches and (cw > 0.6 * w or ch > 0.6 * h):
            out[labels == i] = 255
    return out


_CONFUSIONS = str.maketrans({
    "O": "0", "o": "0", "D": "0", "Q": "0",
    "l": "1", "I": "1", "|": "1", "i": "1", "!": "1",
    "S": "5", "s": "5", "B": "8", "Z": "2", "z": "2", "g": "9", "G": "6",
    "—": "-", "–": "-", "_": "-",
})


def parse_number(text: str, var: Variable | None = None) -> Optional[float]:
    """Convierte el texto de OCR a número tolerando confusiones típicas y coma decimal."""
    if text is None:
        return None
    s = text.strip().translate(_CONFUSIONS)
    s = re.sub(r"\s+", "", s)
    m = re.search(r"-?[0-9][0-9.,]*", s)
    if not m:
        return None
    s = m.group(0).rstrip(".,")
    sep = var.decimal_separator if var else "auto"
    if sep == ",":
        s = s.replace(".", "").replace(",", ".")
    elif sep == ".":
        s = s.replace(",", "")
    else:
        if "," in s and "." in s:
            # El separador que aparece al final es el decimal.
            if s.rfind(",") > s.rfind("."):
                s = s.replace(".", "").replace(",", ".")
            else:
                s = s.replace(",", "")
        elif s.count(",") == 1:
            s = s.replace(",", ".")
        elif s.count(",") > 1:
            s = s.replace(",", "")
        if s.count(".") > 1:
            head, _, tail = s.rpartition(".")
            s = head.replace(".", "") + "." + tail
    try:
        value = float(s)
    except ValueError:
        return None
    if var and var.fix_missing_decimal and var.decimals and "." not in s:
        value /= 10 ** var.decimals
    return value
