from __future__ import annotations

from pathlib import Path

from ..config import GeneralSettings
from .base import OcrEngine, OcrResult, OcrUnavailable, parse_number, preprocess
from .template import TemplateOcr

__all__ = ["OcrEngine", "OcrResult", "OcrUnavailable", "TemplateOcr", "create_engine",
           "parse_number", "preprocess"]


def create_engine(settings: GeneralSettings, glyphs_file: Path) -> OcrEngine:
    """Crea el motor configurado; si no está disponible recurre al de plantillas."""
    try:
        if settings.ocr_engine == "windows":
            from .windows import WindowsOcr
            return WindowsOcr()
        if settings.ocr_engine == "tesseract":
            from .tesseract import TesseractOcr
            return TesseractOcr(settings.tesseract_path)
    except OcrUnavailable:
        pass
    return TemplateOcr(glyphs_file)
