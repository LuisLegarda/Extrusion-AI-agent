import cv2
import numpy as np

from extrusion_monitor.config import OcrOptions, Rect, Variable
from extrusion_monitor.ocr import TemplateOcr
from extrusion_monitor.ocr.robust import RobustReader, dark_background, decimals_of, prepare
from extrusion_monitor.simulator import HmiSimulator, teach_template


def engine():
    sim = HmiSimulator(scenario=None)
    ocr = TemplateOcr()
    teach_template(ocr, sim, OcrOptions(scale=2.0))
    return sim, ocr


def var(**kw):
    return Variable(id="v", name="v", region=Rect(x=0, y=0, w=1, h=1), **kw)


def test_prepare_normalizes_polarity_and_crops():
    sim, _ = engine()
    img = sim.render_text_sample("187.3")  # texto claro sobre fondo oscuro
    p = prepare(img, "lum", "otsu")
    assert p is not None and not dark_background(p)
    assert p[0].min() == 255 and p[:, 0].min() == 255  # margen blanco alrededor del texto


def test_robust_reads_and_learns_variant():
    sim, ocr = engine()
    rr = RobustReader(ocr)
    img = sim.render_text_sample("325.2")
    first = rr.read_number(img, var(), None, lambda v: True)
    assert first.value == 325.2 and first.votes >= 2
    again = rr.read_number(img, var(), 325.2, lambda v: True)
    assert again.value == 325.2 and again.tried == 1  # vía rápida con la variante aprendida
    assert rr.quality("v") == 100


def test_robust_survives_low_contrast_and_noise():
    sim, ocr = engine()
    rr = RobustReader(ocr)
    rng = np.random.default_rng(3)
    img = sim.render_text_sample("45.0")
    bad = cv2.convertScaleAbs(img, alpha=0.4, beta=90)
    bad = np.clip(bad + rng.normal(0, 6, bad.shape), 0, 255).astype(np.uint8)
    res = rr.read_number(bad, var(), None, lambda v: True)
    assert res.value == 45.0


def test_decimals_filter_rejects_lost_point():
    assert decimals_of("7.7") == 1 and decimals_of("77") == 0 and decimals_of("0,456") == 3


def test_new_value_needs_confirmation_or_is_held():
    class Liar:
        name = "fake"
        calls = 0

        def read_binary(self, img, numeric):
            from extrusion_monitor.ocr import OcrResult
            self.calls += 1
            return OcrResult(str(100 + self.calls), 0.9)  # cada variante dice algo distinto

    rr = RobustReader(Liar())
    img = np.full((30, 80, 3), 255, np.uint8)
    cv2.putText(img, "88", (5, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 0), 2)
    res = rr.read_number(img, var(), 50.0, lambda v: True)
    assert res.value is None  # sin consenso no se acepta un valor nuevo
