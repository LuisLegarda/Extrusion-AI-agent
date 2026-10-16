"""Control PID sobre el HMI: dirección, límites, compuertas de seguridad, aprendizaje y escritura verificada."""
import math
import os
import tempfile

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from extrusion_monitor.acquisition import Reading  # noqa: E402
from extrusion_monitor.analysis.rules import Finding, Level  # noqa: E402
from extrusion_monitor.config import AppConfig, Click, ControlLoop, ControlWrite, Rect, Variable  # noqa: E402
from extrusion_monitor.control import ControlManager, LearnedModel, ModelStore, fit_step  # noqa: E402
from extrusion_monitor.recipes import Limit, Recipe  # noqa: E402

R = Rect(x=0, y=0, w=10, h=10)


def _cfg(**kw) -> AppConfig:
    base = dict(id="c", name="Diámetro", mode="auto", pv_var="diam", input_var="vel_sp", kp=100, ti_s=30,
                u_min=300, u_max=400, interval_s=10, resolution=0.1, operator_idle_s=0,
                write=ControlWrite(field=Click(id="f", x=1, y=1)))
    lp = ControlLoop(**{**base, **kw})
    return AppConfig(variables=[Variable(id="diam", name="Diámetro", region=R, decimals=2),
                                Variable(id="vel_sp", name="Velocidad", kind="setpoint", region=R, decimals=1)],
                     controls=[lp])


RECIPE = Recipe(name="R", limits={"diam": Limit(nominal=3.20, warn=0.03, alarm=0.05)})


def _rd(vid, value, ts):
    r = Reading(vid, value=value, ts=ts, ok=True)
    return r


class Loop:
    def __init__(self, cfg=None, clock_start=1000.0):
        self.cfg = cfg or _cfg()
        self.t = clock_start
        self.mgr = ControlManager(ModelStore(tempfile.mktemp(suffix=".json")), clock=lambda: self.t)
        self.u = 350.0

    def step(self, diam, findings=(), stopped=False, idle=999.0, gate=None):
        readings = {"diam": _rd("diam", diam, self.t), "vel_sp": _rd("vel_sp", self.u, self.t)}
        ev, writes = self.mgr.evaluate(self.cfg, self.t, readings, {}, list(findings), "R", RECIPE, stopped, idle,
                                       lambda _m: gate)
        for w in writes:
            self.mgr.wrote(self.cfg.controls[0], w, True, "", self.t, ev)
            self.u = w.u_to
        self.t += 1
        return ev, writes


def test_inactive_by_default_and_direction():
    lp = Loop()
    assert lp.step(3.25)[1] == []  # desactivado: nunca escribe
    lp.mgr.set_active("c", True)
    writes = []
    for _ in range(30):
        writes += lp.step(3.25)[1]
    assert writes and all(w.u_to > w.u_from for w in writes)  # diámetro alto → acelera el capstan
    lp2 = Loop(_cfg(action="dec_when_high"))
    lp2.mgr.set_active("c", True)
    w2 = [w for _ in range(30) for w in lp2.step(3.25)[1]]
    assert w2 and all(w.u_to < w.u_from for w in w2)


def test_bumpless_start_limits_and_rate():
    cfg = _cfg(max_step=2.0, max_rate_min=3.0)
    lp = Loop(cfg)
    lp.mgr.set_active("c", True)
    w = lp.step(3.20)[1]
    assert w == []  # en el objetivo al activar: no hay salto
    writes = [x for _ in range(120) for x in lp.step(3.40)[1]]
    assert all(abs(x.u_to - x.u_from) <= 2.0 + 1e-9 for x in writes)
    # nunca más de 3 unidades en una ventana de 60 s
    times = [t for t, _ in lp.mgr.state("c").writes]
    for t0 in times:
        assert sum(abs(d) for t, d in lp.mgr.state("c").writes if t0 <= t < t0 + 60) <= 3.0 + 1e-6
    lp.u = 399.9
    for _ in range(200):
        lp.step(3.60)
    assert lp.u <= 400.0  # límite absoluto


def test_safety_gates():
    lp = Loop(_cfg(gate_behavior="modelo"))
    lp.mgr.set_active("c", True)
    alarm = Finding(rule="TOLERANCIA", var_id="z3", level=Level.ALARM, message="", since=0)
    for gate_kw, text in ((dict(stopped=True), "detenida"), (dict(findings=[alarm]), "alarma"),
                          (dict(gate=False), "comportamiento")):
        for _ in range(20):
            ev, w = lp.step(3.30, **gate_kw)
            assert w == []
        assert text in lp.mgr.state("c").detail
    # la alarma de la propia medición no bloquea (es justo lo que se corrige)
    own = Finding(rule="TOLERANCIA", var_id="diam", level=Level.ALARM, message="", since=0)
    assert any(lp.step(3.30, findings=[own])[1] for _ in range(20))


def test_operator_change_holds_and_stale_data():
    lp = Loop(_cfg(operator_hold_s=60))
    lp.mgr.set_active("c", True)
    for _ in range(15):
        lp.step(3.20)
    lp.u = 355.0  # el operador cambia el input a mano
    ev, _ = lp.step(3.30)
    assert any("operador" in e.message for e in ev)
    assert all(lp.step(3.30)[1] == [] for _ in range(50))  # espera tras el cambio
    assert "espera" in lp.mgr.state("c").detail
    # dato viejo
    lp2 = Loop()
    lp2.mgr.set_active("c", True)
    readings = {"diam": _rd("diam", 3.3, lp2.t - 100), "vel_sp": _rd("vel_sp", 350, lp2.t)}
    _, w = lp2.mgr.evaluate(lp2.cfg, lp2.t, readings, {}, [], "R", RECIPE, False, 999, lambda _m: None)
    assert w == [] and "actualizada" in lp2.mgr.state("c").detail


def test_assist_mode_needs_operator():
    lp = Loop(_cfg(mode="assist"))
    lp.mgr.set_active("c", True)
    for _ in range(20):
        assert lp.step(3.30)[1] == []
    st = lp.mgr.state("c")
    assert st.proposal is not None and st.proposal.u_to > st.proposal.u_from
    lp.mgr.accept_proposal("c")
    _, w = lp.step(3.30)
    assert len(w) == 1 and lp.u == pytest.approx(st.writes[-1][1] + 350.0)


def _fopdt(k, theta, tau, du, t0=0.0, n=400, noise=0.0):
    import random
    rnd = random.Random(1)
    out = []
    for i in range(-90, n):
        t = t0 + i
        y = 0.0 if t <= t0 + theta else k * du * (1 - math.exp(-(t - t0 - theta) / tau))
        out.append((t, 3.2 + y + rnd.gauss(0, noise)))
    return out


def test_fit_first_order_with_dead_time():
    obs = fit_step(_fopdt(-0.0046, 8.0, 20.0, 5.0, noise=0.0004), 0.0, 5.0, 300)
    assert obs.k == pytest.approx(-0.0046, rel=0.1)
    assert obs.theta == pytest.approx(8.0, abs=4)
    assert obs.tau == pytest.approx(20.0, rel=0.35)
    assert fit_step(_fopdt(0.0, 8, 20, 5, noise=0.001), 0.0, 5.0, 300) is None  # sin respuesta: no se aprende


def test_learned_pid_from_operator_changes():
    cfg = _cfg(tuning="learned", learn_window_s=200)
    lp = Loop(cfg)
    m = lp.mgr.model("R", "c")
    assert not m.ready and lp.mgr.gains(cfg.controls[0], "R") is None
    # tres cambios del operador con su respuesta
    for k in range(3):
        base_t = lp.t
        sign = 1 if k % 2 == 0 else -1
        lp.u += 5.0 * sign
        prev_offset = 0.0 if k == 0 else -0.023 * (1 if k % 2 == 0 else -1) * 0
        for i in range(260):
            t = lp.t
            y = 0.0 if t <= base_t + 8 else -0.0046 * 5 * sign * (1 - math.exp(-(t - base_t - 8) / 20))
            lp.step(3.2 + y + (prev_offset if i < 0 else 0.0))
        lp.u -= 5.0 * sign  # vuelve (cambio del operador también, pero queda fuera de la ventana anterior)
        for _ in range(260):
            lp.step(3.2)
    m = lp.mgr.model("R", "c")
    assert m.n >= 3 and m.ready and m.summary()[0] < 0
    kc, ti, td = lp.mgr.gains(cfg.controls[0], "R")
    assert kc < 0 and ti > 0  # con K < 0 el PID sube el input cuando la medición está alta


def test_learned_model_persists(tmp_path):
    from extrusion_monitor.control import Observation
    store = ModelStore(tmp_path / "m.json")
    m = LearnedModel([Observation(0, 5, -0.004, 8, 20)])
    store.put("R1", "c", m)
    again = ModelStore(tmp_path / "m.json").get("R1", "c")
    assert again.n == 1 and again.obs[0].k == -0.004
    assert ModelStore(tmp_path / "m.json").get("R2", "c").n == 0  # por receta


class FakeClicker:
    def __init__(self, sim_value):
        self.value = sim_value
        self.clicks, self.keys, self.typed = [], [], ""

    def click(self, x, y):
        self.clicks.append((x, y))
        if (x, y) == (5, 5):
            self.value += 0.5
        elif (x, y) == (6, 6):
            self.value -= 0.5

    def type_text(self, t):
        self.typed += t

    def key(self, k):
        self.keys.append(k)
        if k == "enter":
            self.value = float(self.typed)

    def idle_seconds(self):
        return 999.0


def _writer(clicker, method="type"):
    import numpy as np
    from extrusion_monitor.control import ControlWriter

    class Source:
        def grab(self):
            return np.zeros((20, 20, 3), np.uint8)

    class Pages:
        def visible_pages(self, frame):
            return set()

    class Runner:
        def __init__(self):
            from extrusion_monitor.navigation import TourRunner
            self.source, self.clicker, self.pages = Source(), clicker, Pages()
            self._own_input_at = 0.0
            self._tour = None
            self.patches = {}
            self.sleep = lambda s: None
            self.clock = lambda: 0.0
            self._impl = TourRunner

        def _mark_own_input(self):
            pass

        def _check_operator(self):
            pass

        def _clicks(self, clicks, frame, where):
            for c in clicks:
                self.clicker.click(c.x, c.y)
            return frame

    def read(_frame):
        return {"vel_sp": Reading("vel_sp", value=clicker.value, ts=0, ok=True)}

    t = [0.0]

    def clock():
        t[0] += 1
        return t[0]
    return ControlWriter(Runner(), read, clock=clock, sleep=lambda s: None)


def test_writer_type_and_buttons_verified():
    cfg = _cfg()
    clk = FakeClicker(350.0)
    ok, msg = _writer(clk).write(cfg, cfg.controls[0], 351.3, 350.0, 1)
    assert ok, msg
    assert clk.typed == "351.3" and clk.keys == ["ctrl+a", "enter"] and clk.value == 351.3
    cfg2 = _cfg()
    cfg2.controls[0].write = ControlWrite(method="buttons", inc=Click(id="i", x=5, y=5), dec=Click(id="d", x=6, y=6),
                                          step=0.5)
    clk2 = FakeClicker(350.0)
    ok, msg = _writer(clk2).write(cfg2, cfg2.controls[0], 351.5, 350.0, 1)
    assert ok and len(clk2.clicks) == 3 and clk2.value == 351.5


def test_writer_detects_rejected_value():
    cfg = _cfg()

    class Stubborn(FakeClicker):
        def key(self, k):
            self.keys.append(k)  # el HMI no acepta el valor

    clk = Stubborn(350.0)
    ok, msg = _writer(clk).write(cfg, cfg.controls[0], 352.0, 350.0, 1)
    assert not ok and "no muestra" in msg


def test_config_validation():
    bad = AppConfig(controls=[ControlLoop(id="x")]).validate_references()
    assert any("medición" in p for p in bad) and any("límites" in p for p in bad)
    assert not [p for p in _cfg().validate_references() if "Control" in p]


def test_demo_closed_loop_writes_and_verifies(tmp_path):
    import sys
    sys.path.insert(0, os.path.dirname(__file__))
    from test_end_to_end import FakeTime
    from extrusion_monitor.bootstrap import build
    from extrusion_monitor.simulator import HmiSimulator, SimulatorSource
    ft = FakeTime()
    sim = HmiSimulator(clock=ft.clock)
    ctx = build(tmp_path, demo=True, source=SimulatorSource(sim), clock=ft.clock, sleep=ft.sleep)
    eng = ctx.engine
    for _ in range(5):
        eng.step()
        ft.t += 1
    for t in eng.config.tours:
        t.enabled = False
    eng.config.controls[0].mode = "auto"
    eng.reconfigure(eng.config)
    eng.control.set_active("diam_vel", True)
    sim.overrides["vel"] = 340.0  # el operador dejó la velocidad baja: diámetro alto
    sim.sp["vel"] = 340.0
    msgs = []
    while ft.t < 1000 + 150:
        msgs += [e.message for e in eng.step().events if e.kind == "control"]
        ft.t += 1
    wrote = [m for m in msgs if "→" in m and "simulación" not in m]
    assert wrote, msgs
    assert sim.sp["vel"] > 340.0  # aceleró para bajar el diámetro
    assert not any("detenido" in m for m in msgs)
    assert eng.last.control["diam_vel"]["active"]
