"""OCR integrado de Windows: solo se ejecuta en Windows (CI de GitHub y equipos reales)."""
import sys

import cv2
import numpy as np
import pytest

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="solo Windows")


def engine():
    from extrusion_monitor.ocr import OcrUnavailable
    from extrusion_monitor.ocr.windows import WindowsOcr
    try:
        eng = WindowsOcr()
    except OcrUnavailable as exc:
        pytest.skip(f"OCR de Windows no disponible en este equipo: {exc}")
    return eng


def field(text: str, fg=(0, 0, 0), bg=(255, 255, 255), border=None) -> np.ndarray:
    img = np.full((40, 130, 3), bg, np.uint8)
    if border:
        cv2.rectangle(img, (0, 0), (129, 39), border, 3)
    cv2.putText(img, text, (12, 29), cv2.FONT_HERSHEY_SIMPLEX, 0.9, fg, 2, cv2.LINE_AA)
    return img


def test_self_test_passes():
    engine().self_test()


@pytest.mark.parametrize("text,kw", [
    ("300.0", {}),
    ("116", {"fg": (200, 80, 60), "border": (200, 120, 30)}),  # consigna azul con marco
    ("0.991", {}),
    ("352", {"fg": (255, 255, 255), "bg": (30, 30, 30)}),
])
def test_reads_hmi_like_fields(text, kw):
    from extrusion_monitor.config import OcrOptions
    from extrusion_monitor.ocr import parse_number
    res = engine().read(field(text, **kw), True, OcrOptions(scale=2.0))
    assert parse_number(res.text) == float(text), res.text
