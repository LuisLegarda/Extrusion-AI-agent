from __future__ import annotations

import logging
from pathlib import Path

from ..config import GeneralSettings
from .base import OcrEngine, OcrResult, OcrUnavailable, parse_number, preprocess
from .template import TemplateOcr

__all__ = ["OcrEngine", "OcrResult", "OcrUnavailable", "TemplateOcr", "create_engine",
           "parse_number", "preprocess"]

log = logging.getLogger(__name__)
# Motivo por el que no se pudo usar el motor configurado (se muestra en la interfaz).
last_error: str = ""


def create_engine(settings: GeneralSettings, glyphs_file: Path) -> OcrEngine:
    """Crea el motor configurado; si no funciona prueba Tesseract y al final el de plantillas."""
    global last_error
    last_error = ""
    order = [settings.ocr_engine] + [e for e in ("windows", "tesseract") if e != settings.ocr_engine]
    for name in order:
        try:
            if name == "windows":
                from .windows import WindowsOcr
                engine = WindowsOcr()
                engine.self_test()
                return engine
            if name == "tesseract":
                from .tesseract import TesseractOcr
                return TesseractOcr(settings.tesseract_path)
            if name == "template":
                break
        except (OcrUnavailable, ImportError, OSError) as exc:
            log.warning("Motor OCR %s no disponible: %s", name, exc)
            if name == settings.ocr_engine:
                last_error = str(exc)
    return TemplateOcr(glyphs_file)
