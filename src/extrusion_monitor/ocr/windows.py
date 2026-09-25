"""Motor OCR integrado de Windows 10/11 (Windows.Media.Ocr), sin instalaciones extra."""
from __future__ import annotations

import asyncio
import sys
import threading

import cv2
import numpy as np

from ..config import OcrOptions
from .base import OcrResult, OcrUnavailable, preprocess

MIN_TEXT_HEIGHT = 40  # Windows OCR falla con texto muy pequeño: se escala hasta esta altura.


class WindowsOcr:
    name = "windows"

    def __init__(self, language: str | None = None):
        if sys.platform != "win32":
            raise OcrUnavailable("El OCR de Windows solo está disponible en Windows")
        try:
            from winrt.windows.globalization import Language
            from winrt.windows.graphics.imaging import BitmapPixelFormat, SoftwareBitmap
            from winrt.windows.media.ocr import OcrEngine as WinOcrEngine
            from winrt.windows.storage.streams import DataWriter
        except ImportError as exc:  # pragma: no cover - depende de la plataforma
            raise OcrUnavailable(f"Paquetes winrt no disponibles: {exc}") from exc
        self._SoftwareBitmap = SoftwareBitmap
        self._BitmapPixelFormat = BitmapPixelFormat
        self._DataWriter = DataWriter
        if language:
            engine = WinOcrEngine.try_create_from_language(Language(language))
        else:
            engine = WinOcrEngine.try_create_from_user_profile_languages()
        if engine is None:
            raise OcrUnavailable("No hay paquete de idioma OCR instalado en Windows")
        self._engine = engine
        self._local = threading.local()

    def _loop(self) -> asyncio.AbstractEventLoop:
        loop = getattr(self._local, "loop", None)
        if loop is None:
            loop = asyncio.new_event_loop()
            self._local.loop = loop
        return loop

    def read(self, image: np.ndarray, numeric: bool, opts: OcrOptions | None = None) -> OcrResult:
        opts = opts or OcrOptions()
        binary = preprocess(image, opts)
        if binary.shape[0] < MIN_TEXT_HEIGHT:
            f = MIN_TEXT_HEIGHT / binary.shape[0]
            binary = cv2.resize(binary, None, fx=f, fy=f, interpolation=cv2.INTER_CUBIC)
        binary = cv2.copyMakeBorder(binary, 16, 16, 16, 16, cv2.BORDER_CONSTANT, value=255)
        rgba = cv2.cvtColor(binary, cv2.COLOR_GRAY2RGBA)
        h, w = rgba.shape[:2]
        writer = self._DataWriter()
        writer.write_bytes(list(rgba.tobytes()))
        bitmap = self._SoftwareBitmap.create_copy_from_buffer(
            writer.detach_buffer(), self._BitmapPixelFormat.RGBA8, w, h)
        result = self._loop().run_until_complete(self._engine.recognize_async(bitmap))
        text = " ".join(line.text for line in result.lines).strip()
        return OcrResult(text, 0.85 if text else 0.0)
