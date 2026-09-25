from extrusion_monitor.config import OcrOptions
from extrusion_monitor.ocr import TemplateOcr
from extrusion_monitor.simulator import HmiSimulator, teach_template

OPTS = OcrOptions(scale=2.0)


def test_template_reads_numbers_and_text(tmp_path):
    sim = HmiSimulator(scenario=None)
    ocr = TemplateOcr(tmp_path / "glyphs.json")
    teach_template(ocr, sim, OPTS)
    for text in ["187.3", "-0.25", "3.21", "1024", "THHN-12AWG-NEGRO"]:
        res = ocr.read(sim.render_text_sample(text), numeric=text[0].isdigit() or text[0] == "-", opts=OPTS)
        assert res.text == text
        assert res.confidence > 0.6
    # Persistencia
    again = TemplateOcr(tmp_path / "glyphs.json")
    assert again.read(sim.render_text_sample("205"), True, OPTS).text == "205"


def test_teach_rejects_count_mismatch():
    sim = HmiSimulator(scenario=None)
    ocr = TemplateOcr()
    try:
        ocr.teach(sim.render_text_sample("123"), "12", OPTS)
    except ValueError:
        pass
    else:
        raise AssertionError("debería fallar")


def test_empty_engine_returns_nothing():
    sim = HmiSimulator(scenario=None)
    assert TemplateOcr().read(sim.render_text_sample("12"), True, OPTS).text == ""
