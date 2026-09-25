"""Motor OCR usando el ejecutable de Tesseract (opcional, puede incluirse junto al .exe)."""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional

import cv2
import numpy as np

from ..config import OcrOptions
from .base import OcrResult, OcrUnavailable, preprocess


def find_tesseract(explicit: Optional[str] = None) -> Optional[str]:
    candidates = [explicit] if explicit else []
    if getattr(sys, "frozen", False):
        candidates.append(str(Path(sys.executable).parent / "tesseract" / "tesseract.exe"))
    candidates += [shutil.which("tesseract"), r"C:\Program Files\Tesseract-OCR\tesseract.exe"]
    for c in candidates:
        if c and Path(c).exists():
            return c
    return None


class TesseractOcr:
    name = "tesseract"

    def __init__(self, path: Optional[str] = None):
        self.exe = find_tesseract(path)
        if not self.exe:
            raise OcrUnavailable("No se encontró tesseract.exe")
        self._startupinfo = None
        if sys.platform == "win32":
            si = subprocess.STARTUPINFO()
            si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            self._startupinfo = si

    def read(self, image: np.ndarray, numeric: bool, opts: OcrOptions | None = None) -> OcrResult:
        binary = preprocess(image, opts or OcrOptions())
        binary = cv2.copyMakeBorder(binary, 10, 10, 10, 10, cv2.BORDER_CONSTANT, value=255)
        ok, png = cv2.imencode(".png", binary)
        if not ok:
            return OcrResult("", 0.0)
        args = [self.exe, "stdin", "stdout", "--psm", "7"]
        if numeric:
            args += ["-c", "tessedit_char_whitelist=0123456789.,-+"]
        try:
            out = subprocess.run(args, input=png.tobytes(), capture_output=True, timeout=10,
                                 startupinfo=self._startupinfo)
        except (OSError, subprocess.TimeoutExpired):
            return OcrResult("", 0.0)
        text = out.stdout.decode("utf-8", "ignore").strip()
        # Tesseract por línea de comandos no entrega confianza; se asume media si hubo texto.
        return OcrResult(text, 0.8 if text else 0.0)
