"""Límites mín/máx en recetas y recuperación de la pantalla tras bloqueo/desconexión."""
import numpy as np

from extrusion_monitor.analysis.rules import R_TOL, Level
from extrusion_monitor.bootstrap import build
from extrusion_monitor.capture import is_blank
from extrusion_monitor.recipes import Limit, recipe_from_csv, recipe_to_csv
from extrusion_monitor.simulator import HmiSimulator, Scenario, SimulatorSource


class FakeTime:
    def __init__(self):
        self.t = 1000.0

    def clock(self):
        return self.t

    def sleep(self, s):
        self.t += s


def make(tmp_path):
    ft = FakeTime()
    sim = HmiSimulator(scenario=Scenario(period=1e7), clock=ft.clock)
    ctx = build(tmp_path, demo=True, source=SimulatorSource(sim), clock=ft.clock, sleep=ft.sleep)
    return ctx, sim, ft


def run(ctx, ft, n):
    snaps = []
    for _ in range(n):
        snaps.append(ctx.engine.step())
        ft.t += 1
    return snaps


def test_limit_bounds_and_csv_roundtrip():
    lim = Limit(mode="range", alarm_max=5.0, warn_max=4.0)  # solo máximo
    b = lim.bounds(None)
    assert (b.wl, b.wh, b.al, b.ah) == (None, 4.0, None, 5.0) and lim.active and lim.center() is None
    assert Limit(mode="range", alarm_min=10, alarm_max=20).center() == 15
    assert Limit(mode="range", alarm_min=20, alarm_max=10).check()
    assert Limit(mode="range", warn_min=5, alarm_min=8).check()  # aviso fuera del rango de alarma
    b = Limit(nominal=100, warn=2, alarm=5).bounds(100)
    assert (b.wl, b.wh, b.al, b.ah) == (98, 102, 95, 105)
    from extrusion_monitor.recipes import Recipe
    r = Recipe(name="x", limits={"exc": lim, "z1": Limit(nominal=160, warn=3, alarm=6)})
    back = recipe_from_csv("x", recipe_to_csv(r))
    assert back.limits["exc"] == lim and back.limits["z1"].alarm == 6


def test_min_max_limits_in_engine(tmp_path):
    ctx, sim, ft = make(tmp_path)
    recipe = ctx.recipes.get(ctx.recipes.names()[0])
    # Diámetro nominal 3.20: rango 3.10–3.18 (el valor real queda por encima del máximo) y excentricidad ≤ 10 %.
    recipe.limits["diam"] = Limit(mode="range", alarm_min=3.10, alarm_max=3.18)
    recipe.limits["exc"] = Limit(mode="range", alarm_max=10.0)
    ctx.recipes.save(recipe)
    snaps = run(ctx, ft, 8)
    st = snaps[-1].statuses["diam"]
    assert st.bounds.al == 3.10 and st.bounds.ah == 3.18 and st.reference == 3.14
    assert st.level == Level.ALARM
    assert any(f.rule == R_TOL and f.var_id == "diam" and "máx" in f.message for f in snaps[-1].findings)
    ex = snaps[-1].statuses["exc"]
    assert ex.level == Level.OK and ex.bounds.ah == 10.0 and ex.bounds.al is None


class BlankableSource:
    def __init__(self, inner):
        self.inner = inner
        self.mode = "ok"

    def grab(self):
        frame = self.inner.grab()
        if self.mode == "black":
            from extrusion_monitor.capture import ScreenUnavailable
            raise ScreenUnavailable("la pantalla está en negro")
        if self.mode == "resized":
            return np.zeros((frame.shape[0] + 100, frame.shape[1] + 200, 3), np.uint8) + 60
        return frame


def test_screen_lost_and_recovered(tmp_path):
    ctx, sim, ft = make(tmp_path)
    src = BlankableSource(ctx.engine.source)
    ctx.engine.source = src
    ctx.engine.tour_runner.source = src
    run(ctx, ft, 5)
    assert ctx.engine.last.statuses["diam"].reading.visible
    src.mode = "black"
    snaps = run(ctx, ft, 30)  # sesión bloqueada: no hay recorridos ni lecturas nuevas
    assert all("no disponible" in s.error for s in snaps)
    assert sum(e.kind == "screen" for s in snaps for e in s.events) == 1
    assert all(s.tour is None for s in snaps)
    src.mode = "resized"  # regreso con otra resolución (escritorio remoto)
    snap = ctx.engine.step()
    assert "resolución" in snap.error
    src.mode = "ok"
    ft.t += 1
    snaps = run(ctx, ft, 3)
    assert not snaps[-1].error
    assert any(e.kind == "screen" and "de nuevo" in e.message for s in snaps for e in s.events)
    st = snaps[-1].statuses["diam"]
    assert st.reading.visible and st.fresh


def test_is_blank():
    assert is_blank(np.zeros((100, 100, 3), np.uint8))
    img = np.zeros((100, 100, 3), np.uint8)
    img[40:60, 40:60] = 200
    assert not is_blank(img)
