"""Lectura de variables desde la imagen del HMI, con filtros de plausibilidad."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

from .capture import crop
from .config import AppConfig, Variable
from .ocr import OcrEngine, parse_number
from .pages import PageDetector


@dataclass
class Reading:
    var_id: str
    value: Optional[float] = None  # último valor numérico aceptado
    text: Optional[str] = None  # último texto aceptado (variables de texto)
    ts: Optional[float] = None  # instante del último valor aceptado
    raw: str = ""  # texto leído en el ciclo actual
    ok: bool = False  # lectura del ciclo actual válida
    visible: bool = True  # su página está en pantalla
    confidence: float = 0.0
    reason: str = ""  # motivo de rechazo
    fail_count: int = 0
    decimals: Optional[int] = None  # decimales mostrados por el HMI en la última lectura
    _pending: Optional[float] = field(default=None, repr=False)

    def age(self, now: float) -> Optional[float]:
        return None if self.ts is None else now - self.ts


MIN_CONFIDENCE = 0.55
# Carácter no reconocido entre dígitos: la lectura no es fiable (p. ej. «3?5»).
_AMBIGUOUS = re.compile(r"[0-9.,]\?+[0-9]")


class Acquirer:
    def __init__(self, config: AppConfig, ocr: OcrEngine, pages: Optional[PageDetector] = None):
        self.config = config
        self.ocr = ocr
        self.pages = pages
        self.readings: dict[str, Reading] = {v.id: Reading(v.id) for v in config.variables}

    def read(self, frame: np.ndarray, now: float) -> tuple[set[str], dict[str, Reading]]:
        visible = self.pages.visible_pages(frame) if self.pages and self.config.pages else set()
        for var in self.config.variables:
            rd = self.readings.setdefault(var.id, Reading(var.id))
            rd.visible = var.page is None or var.page in visible
            if not rd.visible:
                rd.ok, rd.raw, rd.reason = False, "", "página no visible"
                continue
            self._read_var(var, rd, frame, now)
        return visible, self.readings

    def _read_var(self, var: Variable, rd: Reading, frame: np.ndarray, now: float) -> None:
        img = crop(frame, var.region)
        numeric = var.kind != "text"
        try:
            res = self.ocr.read(img, numeric, var.ocr)
        except Exception as exc:  # un fallo de OCR no debe detener el monitoreo
            self._fail(rd, f"error OCR: {exc}")
            return
        rd.raw, rd.confidence = res.text, res.confidence
        if var.kind == "text":
            text = res.text.strip()
            if text and "?" not in text:
                rd.text, rd.ts, rd.ok, rd.reason, rd.fail_count = text, now, True, "", 0
            else:
                self._fail(rd, "texto ilegible")
            return
        if res.confidence < MIN_CONFIDENCE:
            self._fail(rd, "confianza OCR baja")
            return
        if _AMBIGUOUS.search(res.text):
            self._fail(rd, "carácter dudoso dentro del número")
            return
        value = parse_number(res.text, var)
        if value is None:
            self._fail(rd, "no numérico")
            return
        if (var.valid_min is not None and value < var.valid_min) or (
                var.valid_max is not None and value > var.valid_max):
            self._fail(rd, f"fuera de rango válido ({value:g})")
            return
        if var.max_step is not None and rd.value is not None and abs(value - rd.value) > var.max_step:
            # Un salto grande se acepta solo si se repite en la siguiente lectura.
            if rd._pending is None or abs(value - rd._pending) > var.max_step * 0.1:
                rd._pending = value
                self._fail(rd, "salto sin confirmar")
                return
        rd._pending = None
        rd.value, rd.ts, rd.ok, rd.reason, rd.fail_count = value, now, True, "", 0
        m = re.search(r"\d[.,](\d+)", res.text)
        rd.decimals = len(m.group(1)) if m else 0

    @staticmethod
    def _fail(rd: Reading, reason: str) -> None:
        rd.ok, rd.reason = False, reason
        rd.fail_count += 1
