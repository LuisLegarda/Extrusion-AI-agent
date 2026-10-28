"""Lectura de variables desde la imagen del HMI, con filtros de plausibilidad."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable, Optional

import numpy as np

import cv2

from .capture import crop, similarity
from .config import AppConfig, Variable
from .ocr import OcrEngine, parse_number
from .ocr.robust import RobustReader
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
    def __init__(self, config: AppConfig, ocr: OcrEngine, pages: Optional[PageDetector] = None,
                 selector_images: Optional[dict[str, dict[str, np.ndarray]]] = None):
        self.config = config
        self.ocr = ocr
        self.pages = pages
        self.selector_images = selector_images or {}
        self.robust = RobustReader(ocr)
        self.readings: dict[str, Reading] = {v.id: Reading(v.id) for v in config.variables}
        # Validación opcional de textos (p. ej. que el nombre leído sea una receta conocida).
        self.text_accept: dict[str, Callable[[str], bool]] = {}
        self._lamp_hist: dict[str, list] = {}
        self._compile_formulas()

    def read(self, frame: Optional[np.ndarray], now: float,
             cams: Optional[dict] = None) -> tuple[set[str], dict[str, Reading]]:
        """Lee las variables de la pantalla (`frame`) y, si se pasan, de las cámaras (`cams`: id → CameraView).

        Sin `frame` no se leen las de la pantalla y sin `cams` no se tocan las de las cámaras (p. ej. en un
        recorrido, que solo cambia la pantalla).
        """
        visible = self.pages.visible_pages(frame) if frame is not None and self.pages and self.config.pages \
            else set()
        for var in self.config.variables:
            if var.kind == "formula":
                continue
            if var.on_camera:
                if cams is None:
                    continue
                rd = self.readings.setdefault(var.id, Reading(var.id))
                rd.visible = True
                view = cams.get(var.source)
                if view is None or not view.ok:
                    self._fail(rd, f"cámara sin imagen: {getattr(view, 'error', None) or 'no configurada'}")
                    continue
                self._read_var(var, rd, view.frame, now, view)
                continue
            if frame is None:
                continue
            rd = self.readings.setdefault(var.id, Reading(var.id))
            rd.visible = var.page is None or var.page in visible
            if not rd.visible:
                rd.ok, rd.raw, rd.reason = False, "", "página no visible"
                continue
            self._read_var(var, rd, frame, now)
        self._eval_formulas()
        return visible, self.readings

    def _compile_formulas(self) -> None:
        from .analysis.formula import FormulaError, compile_formula, evaluation_order
        known = {v.id for v in self.config.variables}
        self._formulas = {}
        for v in self.config.variables:
            if v.kind == "formula":
                try:
                    self._formulas[v.id] = compile_formula(v.formula, known - {v.id})
                except FormulaError:
                    pass
        try:
            self._formula_order = evaluation_order(self._formulas)
        except FormulaError:
            self._formula_order = []

    def _eval_formulas(self) -> None:
        """Calcula las fórmulas; su instante es el del dato más viejo que usan (propaga lo «viejo»)."""
        for vid in self._formula_order:
            f = self._formulas[vid]
            rd = self.readings.setdefault(vid, Reading(vid))
            rd.visible = True
            inputs = [self.readings.get(d) for d in f.deps]
            if any(r is None or r.value is None or r.ts is None for r in inputs):
                self._fail(rd, "faltan datos de entrada")
                continue
            ts = min(r.ts for r in inputs) if inputs else None
            if rd.ts is not None and ts is not None and ts <= rd.ts and rd.value is not None:
                rd.ok = True
                continue  # sin datos nuevos
            value = f.evaluate({d: self.readings[d].value for d in f.deps})
            if value is None:
                self._fail(rd, "resultado no válido (p. ej. división entre 0)")
                continue
            rd.value, rd.ts, rd.ok, rd.reason, rd.fail_count = value, ts, True, "", 0
            rd.raw = f"{value:.6g}"

    def _read_var(self, var: Variable, rd: Reading, frame: np.ndarray, now: float, view=None) -> None:
        img = crop(frame, var.region)
        if var.kind == "selector":
            if var.state_method == "color":
                self._read_lamp(var, rd, img, now, view)
            else:
                self._read_selector(var, rd, img, now)
            return
        if var.kind != "text" and var.reader != "ocr":
            crops = [crop(f, var.region) for f in view.frames] if view is not None else [img]
            self._read_indicator(var, rd, crops, now)
            return
        if view is not None and len(view.frames) > 1:
            img = combine([crop(f, var.region) for f in view.frames], "median")  # menos ruido de cámara
        if var.ocr.auto:
            self._read_robust(var, rd, img, now)
            return
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

    def _read_robust(self, var: Variable, rd: Reading, img: np.ndarray, now: float) -> None:
        try:
            if var.kind == "text":
                res = self.robust.read_text(img, var, self.text_accept.get(var.id))
                rd.raw, rd.confidence = res.text, res.confidence
                if res.text:
                    rd.text, rd.ts, rd.ok, rd.reason, rd.fail_count = res.text, now, True, "", 0
                else:
                    self._fail(rd, "texto ilegible")
                return

            def plausible(v: float) -> bool:
                return not ((var.valid_min is not None and v < var.valid_min) or
                            (var.valid_max is not None and v > var.valid_max))

            # Los decimales aprendidos solo se usan cuando ya hay varias lecturas coherentes.
            learned = rd.decimals if rd.value is not None and self._stable(var.id) else None
            res = self.robust.read_number(img, var, rd.value, plausible, decimals=learned)
        except Exception as exc:  # un fallo de OCR no debe detener el monitoreo
            self._fail(rd, f"error OCR: {exc}")
            return
        rd.raw, rd.confidence = res.text, res.confidence
        if res.value is None:
            reason = "variantes en desacuerdo" if res.candidates else "sin lectura válida"
            self._fail(rd, f"{reason} ({res.tried} intentos)")
            return
        self._accept(var, rd, res.value, res.text, now)

    def _accept(self, var: Variable, rd: Reading, value: float, text: str, now: float) -> None:
        if var.max_step is not None and rd.value is not None and abs(value - rd.value) > var.max_step:
            # Un salto grande se acepta solo si se repite en la siguiente lectura.
            if rd._pending is None or abs(value - rd._pending) > var.max_step * 0.1:
                rd._pending = value
                self._fail(rd, "salto sin confirmar")
                return
        rd._pending = None
        rd.value, rd.ts, rd.ok, rd.reason, rd.fail_count = value, now, True, "", 0
        m = re.search(r"\d[.,](\d+)", text)
        rd.decimals = len(m.group(1)) if m else 0

    def _stable(self, var_id: str) -> bool:
        h = self.robust.history.get(var_id)
        return bool(h) and len(h) >= 5 and sum(list(h)[-5:]) >= 4

    def quality(self, var_id: str) -> Optional[float]:
        return self.robust.quality(var_id)

    # --- indicadores físicos (cámara o pantalla) ------------------------------------------------------
    def _read_lamp(self, var: Variable, rd: Reading, img: np.ndarray, now: float, view) -> None:
        from .vision.indicators import lamp_feature, lamp_state
        if not var.color_states:
            self._fail(rd, "luz sin colores enseñados")
            return
        hist = view.lamps.get(var.id) if view is not None else None
        if not hist:  # pantalla (o la cámara aún no midió esta luz): historial propio, una muestra por ciclo
            h = self._lamp_hist.setdefault(var.id, [])
            h.append((now, lamp_feature(img)))
            del h[:-60]
            hist = h
        state, score = lamp_state(hist, var.color_states, now, var.blink, var.blink_window_s)
        rd.raw, rd.confidence = state or "", score
        if state is not None and score >= 0.35:
            rd.text, rd.ts, rd.ok, rd.reason, rd.fail_count = state, now, True, "", 0
        else:
            self._fail(rd, f"color no reconocido (más cercano «{state}» {score:.2f})")

    def _read_indicator(self, var: Variable, rd: Reading, crops: list, now: float) -> None:
        from .vision import indicators, sevenseg
        try:
            if var.reader == "sevenseg":
                # Mediana de los últimos cuadros (quita ruido); si no se lee, el máximo: un display LED
                # multiplexado puede salir incompleto en cada cuadro. El máximo va después porque, si el
                # valor cambió entre cuadros, mezcla dígitos (un 4 y un 5 dan 9).
                options = [crops[-1]] if len(crops) == 1 else [combine(crops, "median"), combine(crops, "max")]
                best = None
                for im in options:
                    r = sevenseg.decode(im, var.seg.polarity, var.seg.slant, var.seg.digits)
                    if best is None or r.confidence > best.confidence + 0.15:
                        best = r
                    if best.confidence >= MIN_CONFIDENCE and parse_number(best.text, var) is not None:
                        break
                rd.raw, rd.confidence = best.text, best.confidence
                if best.confidence < MIN_CONFIDENCE:
                    self._fail(rd, f"display ilegible («{best.text}»)")
                    return
                value = parse_number(best.text, var)
                if value is None:
                    self._fail(rd, f"no numérico («{best.text}»)")
                    return
                text = best.text
            else:
                img = combine(crops, "median")
                r = indicators.gauge_value(img, var.gauge) if var.reader == "gauge" else \
                    indicators.bar_value(img, var.bar)
                rd.confidence = r.confidence
                if r.value is None or r.confidence < 0.3:
                    self._fail(rd, "aguja no encontrada" if var.reader == "gauge" else "nivel no distinguible")
                    return
                value = float(round(r.value, var.decimals) if var.decimals is not None else r.value)
                text = f"{value:.{var.decimals}f}" if var.decimals is not None else f"{value:g}"
                rd.raw = text
        except Exception as exc:  # un fallo de lectura no debe detener el monitoreo
            self._fail(rd, f"error de lectura: {exc}")
            return
        if (var.valid_min is not None and value < var.valid_min) or (
                var.valid_max is not None and value > var.valid_max):
            self._fail(rd, f"fuera de rango válido ({value:g})")
            return
        self._accept(var, rd, value, text, now)

    def _read_selector(self, var: Variable, rd: Reading, img: np.ndarray, now: float) -> None:
        state, score = match_state(img, self.selector_images.get(var.id, {}))
        rd.raw, rd.confidence = state or "", score
        if state is not None and score >= var.state_threshold:
            rd.text, rd.ts, rd.ok, rd.reason, rd.fail_count = state, now, True, "", 0
        elif not self.selector_images.get(var.id):
            self._fail(rd, "selector sin estados capturados")
        else:
            self._fail(rd, f"estado no reconocido (mejor «{state}» {score:.2f})")

    @staticmethod
    def _fail(rd: Reading, reason: str) -> None:
        rd.ok, rd.reason = False, reason
        rd.fail_count += 1


def combine(crops: list, how: str = "median") -> np.ndarray:
    """Combina las regiones de varios cuadros seguidos (mismo tamaño): «max» o «median»."""
    crops = [c for c in crops if c is not None and c.shape == crops[-1].shape]
    if len(crops) <= 1:
        return crops[-1] if crops else np.zeros((1, 1, 3), np.uint8)
    stack = np.stack(crops)
    return stack.max(axis=0) if how == "max" else np.median(stack, axis=0).astype(np.uint8)


def match_state(img: np.ndarray, states: dict[str, np.ndarray]) -> tuple[Optional[str], float]:
    """Estado cuya imagen de referencia se parece más a la región actual."""
    best, best_score = None, 0.0
    for name, ref in states.items():
        cur = img if img.shape == ref.shape else cv2.resize(img, (ref.shape[1], ref.shape[0]))
        score = similarity(cur, ref)
        if score > best_score:
            best, best_score = name, score
    return best, best_score
