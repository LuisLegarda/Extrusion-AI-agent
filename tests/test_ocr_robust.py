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


def test_bare_zero_is_read_even_when_the_variable_has_decimals():
    """Muchos HMI muestran «0» (sin punto) aunque la variable lleve decimales («12.5»): no es un punto perdido."""
    from extrusion_monitor.ocr import OcrResult
    from extrusion_monitor.ocr.robust import bare_zero
    assert bare_zero("0") and bare_zero("-0") and bare_zero(" 00 ") and not bare_zero("0.0")
    assert not bare_zero("10") and not bare_zero("77")

    class Says:
        name = "fake"

        def __init__(self, text):
            self.text = text

        def read_binary(self, img, numeric):
            return OcrResult(self.text, 0.9)

    img = np.full((30, 80, 3), 255, np.uint8)
    cv2.putText(img, "0", (5, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 0), 2)
    for declared, learned in ((1, None), (None, 1)):  # decimales declarados en la variable o aprendidos
        res = RobustReader(Says("0")).read_number(img, var(decimals=declared), 12.5, lambda v: True,
                                                  decimals=learned)
        assert res.value == 0.0
    # «77» cuando se esperan decimales sigue rechazándose (punto perdido)
    assert RobustReader(Says("77")).read_number(img, var(), 7.7, lambda v: True, decimals=1).value is None


def test_a_zero_does_not_change_the_learned_decimals(tmp_path):
    from extrusion_monitor.acquisition import Reading
    from extrusion_monitor.bootstrap import build
    ctx = build(tmp_path / "home", demo=True)
    acq = ctx.engine.acquirer
    v = ctx.engine.config.variables[0]
    rd = Reading(v.id)
    acq._accept(v, rd, 12.5, "12.5", 1.0)
    acq._accept(v, rd, 0.0, "0", 2.0)
    assert rd.value == 0.0 and rd.decimals == 1  # sigue esperando un decimal para «12.5»
