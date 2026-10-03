"""Cámaras e indicadores físicos: 7 segmentos, luces/andon por color, agujas, barras y el motor con cámaras."""
import os

import cv2
import numpy as np
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from extrusion_monitor import simulator as sm  # noqa: E402
from extrusion_monitor.camera import CameraFeed, CameraManager, CameraUnavailable, process  # noqa: E402
from extrusion_monitor.config import (AppConfig, BarOptions, CameraSettings, ColorState, GaugeOptions,  # noqa: E402
                                      Rect, Variable)
from extrusion_monitor.vision import indicators, sevenseg  # noqa: E402


def _display(text, led=True, slant=8.0, scale=0.6, noise=6, ghost=True, seed=0):
    rng = np.random.default_rng(seed)
    img = np.full((80, 40 + int(len(text) * 0.75 * 55) + 30, 3), (25, 25, 25) if led else (150, 190, 170), np.uint8)
    off = ((55, 55, 75) if led else (120, 150, 135)) if ghost else None
    sevenseg.draw_text(img, text, 15, 12, 55, on=(40, 60, 255) if led else (40, 50, 40), off=off, slant=slant)
    img = cv2.GaussianBlur(img, (3, 3), 0)
    img = np.clip(img.astype(int) + rng.normal(0, noise, img.shape), 0, 255).astype(np.uint8)
    return cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)


@pytest.mark.parametrize("text", ["215.3", "88.88", "1234", "-12.5", "0.07", "70.1", "5.6", "300", "49.9"])
@pytest.mark.parametrize("led", [True, False])
def test_seven_segment_led_and_lcd(text, led):
    for slant, scale in ((0.0, 0.8), (10.0, 0.4)):
        r = sevenseg.decode(_display(text, led, slant, scale))
        assert r.text == text, (slant, scale, r.text)
        assert r.confidence > 0.6
        assert r.polarity == ("light" if led else "dark")


def test_seven_segment_letters_are_not_numbers():
    r = sevenseg.decode(_display("E r", ghost=False), numeric=False)
    assert "E" in r.text and "r" in r.text


def test_gauge_and_calibration():
    g = indicators.calibrate_gauge((100, 100), (100 - 50, 100 + 50), (100 + 50, 100 + 50), (200, 200),
                                   GaugeOptions(value_min=0, value_max=250))
    assert g.calibrated and round(g.angle_min) == 135 and round(g.angle_max) == 45
    rng = np.random.default_rng(1)
    for frac in (0.0, 0.2, 0.5, 0.83, 1.0):
        img = np.full((200, 200, 3), 90, np.uint8)
        indicators.draw_gauge(img, 100, 100, 90, frac)
        img = np.clip(img + rng.normal(0, 8, img.shape), 0, 255).astype(np.uint8)
        r = indicators.gauge_value(img, g.model_copy(update={"radius": 0.45}))
        assert abs(r.value - 250 * frac) < 3 and r.confidence > 0.5


def test_level_bar():
    for frac in (0.0, 0.3, 0.6, 1.0):
        img = np.full((220, 60, 3), 30, np.uint8)
        indicators.draw_bar(img, 10, 10, 40, 200, frac)
        r = indicators.bar_value(img[10:210, 10:50], BarOptions(value_max=100))
        assert r.value is not None and abs(r.value - 100 * frac) <= 6


def test_lamp_color_and_blinking():
    off = ColorState(name="Apagado", lab=[60, 128, 128])
    amber = ColorState(name="Ámbar", lab=[200, 150, 200])
    states = [off, amber]
    hist = [(t / 10, amber.lab if (t // 5) % 2 == 0 else off.lab) for t in range(30)]  # 1 Hz
    assert indicators.lamp_state(hist, states, 3.0, blink=True)[0] == "Ámbar parpadeando"
    steady = [(t / 10, amber.lab) for t in range(30)]
    assert indicators.lamp_state(steady, states, 3.0, blink=True)[0] == "Ámbar"
    v = Variable(id="a", name="A", kind="selector", region=Rect(x=0, y=0, w=4, h=4), state_method="color",
                 blink=True, color_states=states)
    assert v.state_names == ["Apagado", "Ámbar", "Ámbar parpadeando"]


def test_rotation_and_perspective():
    img = np.zeros((100, 200, 3), np.uint8)
    img[10:20, 150:160] = 255
    s = CameraSettings(id="c", rotate=90)
    assert process(img, s).shape[:2] == (200, 100)
    s = CameraSettings(id="c", warp=[[50, 0], [150, 0], [150, 100], [50, 100]])
    assert process(img, s).shape[:2] == (100, 100)


class _Broken:
    def read(self):
        raise CameraUnavailable("cable desconectado")

    def release(self):
        pass


def test_feed_reconnects_after_failure():
    calls = []

    def opener(s):
        calls.append(1)
        if len(calls) == 1:
            return _Broken()
        return sm.SimCamera(clock=lambda: 5.0)

    feed = CameraFeed(CameraSettings(id="c", device="x"), opener)
    assert not feed.poll() and "cable" in feed.view().error
    feed._retry_at = 0
    assert feed.poll() and feed.view().ok


def _demo(tmp_path, t):
    from extrusion_monitor.bootstrap import build
    clock = lambda: t[0]  # noqa: E731
    ctx = build(tmp_path, demo=True, clock=clock, sleep=lambda s: None)
    for f in ctx.engine.cameras.feeds.values():
        f.opener = lambda s: sm.SimCamera(clock=clock)
    return ctx


def _cycle(eng, t, tt):
    for k in range(5):  # el hilo de la cámara toma varios cuadros por ciclo
        t[0] = tt + 0.1 * k
        for f in eng.cameras.feeds.values():
            f.poll()
    t[0] = tt + 0.5
    return eng.step()


def test_demo_panel_read_through_engine(tmp_path):
    t = [10.0]
    eng = _demo(tmp_path, t).engine
    for tt in (10, 11, 75, 75.5, 76, 76.5, 77):
        _cycle(eng, t, tt)
        r = eng.acquirer.readings
        exp = sm.panel_values(t[0])
        assert r["cam_temp"].value == pytest.approx(exp["cam_temp"], abs=0.11)
        assert r["cam_rpm"].value == pytest.approx(exp["cam_rpm"], abs=0.11)
        assert r["cam_presion"].value == pytest.approx(exp["cam_presion"], abs=4)
        assert r["cam_nivel"].value == pytest.approx(exp["cam_nivel"], abs=12)  # bargraph de 10 segmentos
        if tt < 70:
            assert (r["andon_verde"].text, r["andon_rojo"].text) == ("Verde", "Apagado")
    assert eng.acquirer.readings["andon_ambar"].text == "Ámbar parpadeando"
    assert eng.last.statuses["cam_temp"].reading.ok


def test_camera_loss_is_reported_once_and_screen_keeps_reading(tmp_path):
    t = [10.0]
    eng = _demo(tmp_path, t).engine
    _cycle(eng, t, 10)
    for f in eng.cameras.feeds.values():
        f._close()
        f.opener = lambda s: _Broken()
    events = []
    for tt in (12, 14, 16):
        events += [e.message for e in _cycle(eng, t, tt).events]
    lost = [m for m in events if m.startswith("Cámara")]
    assert len(lost) == 1 and "sin imagen" in lost[0]
    r = eng.acquirer.readings
    assert not r["cam_temp"].ok and r["cam_temp"].value is not None  # se conserva el último dato
    assert r["vel"].ok  # la pantalla del HMI se sigue leyendo


def test_camera_only_machine_does_not_capture_screen(tmp_path):
    from extrusion_monitor.config import Workspace
    from extrusion_monitor.engine import MonitorEngine
    from extrusion_monitor.ocr import TemplateOcr
    from extrusion_monitor.recipes import RecipeStore
    cams, cam_vars = sm.demo_camera_config()
    cfg = AppConfig(cameras=cams, variables=cam_vars)
    assert not cfg.needs_screen

    class NoScreen:
        def grab(self):
            raise AssertionError("no debe capturar la pantalla")

    ws = Workspace(tmp_path)
    eng = MonitorEngine(ws, cfg, RecipeStore(ws.recipes_dir), NoScreen(), TemplateOcr(ws.glyphs_file),
                        clock=lambda: 20.0)
    for f in eng.cameras.feeds.values():
        f.opener = lambda s: sm.SimCamera(clock=lambda: 20.0)
    snap = eng.step()
    assert not snap.error and eng.acquirer.readings["cam_temp"].ok


def test_old_configuration_still_loads():
    v = Variable.model_validate({"id": "x", "name": "X", "region": {"x": 0, "y": 0, "w": 5, "h": 5}})
    assert v.source == "screen" and v.reader == "ocr" and not v.on_camera
    cfg = AppConfig.model_validate({"variables": [v.model_dump()]})
    assert cfg.cameras == [] and cfg.needs_screen


def test_setup_dialog_with_camera(tmp_path):
    from PySide6.QtWidgets import QApplication
    from extrusion_monitor.bootstrap import build
    from extrusion_monitor.ui.setup_dialog import SetupDialog
    QApplication.instance() or QApplication([])
    ctx = build(tmp_path, demo=True)
    d = SetupDialog(ctx)
    assert d.cmb_source.count() == 2
    d._select_key(("var", "cam_temp"))
    assert d.source == "cam1" and "confianza" in d.lbl_result.text()
    d._select_key(("var", "andon_verde"))
    assert "Estado detectado" in d.lbl_result.text()
    d._select_key(("var", "vel"))
    assert d.source == "screen"
