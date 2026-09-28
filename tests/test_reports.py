"""Reportes PDF: disparadores, periodo desde el reporte anterior, evaluación y CSV."""
import csv

from extrusion_monitor.acquisition import Reading
from extrusion_monitor.bootstrap import build
from extrusion_monitor.config import AppConfig, ReportDef, ReportTrigger, ReportVar, Variable, Rect, Workspace
from extrusion_monitor.reports import ReportJob, ReportManager, VarLimits, evaluate_var
from extrusion_monitor.simulator import HmiSimulator, Scenario, SimulatorSource


class FakeTime:
    def __init__(self):
        self.t = 1_700_000_000.0

    def clock(self):
        return self.t

    def sleep(self, s):
        self.t += s


def test_triggers(tmp_path):
    ws = Workspace(tmp_path)
    cfg = AppConfig(variables=[
        Variable(id="v", name="V", kind="actual", region=Rect(x=0, y=0, w=5, h=5)),
        Variable(id="s", name="S", kind="selector", states=["ON", "OFF"], region=Rect(x=0, y=0, w=5, h=5))],
        reports=[ReportDef(id="r", min_interval_s=0, triggers=[
            ReportTrigger(kind="cross", var_id="v", op=">", value=10),
            ReportTrigger(kind="selector", var_id="s", state="OFF")])])
    t = [0.0]
    m = ReportManager(ws, lambda: t[0])

    def check(v, s):
        return m.check(cfg, {"v": Reading("v", value=v, ok=True), "s": Reading("s", text=s, ok=True)}, [])

    assert not check(5, "ON")
    assert check(12, "ON")  # cruza el umbral
    assert not check(13, "ON")  # sigue arriba: no vuelve a disparar
    assert check(3, "OFF")  # selector a OFF
    assert not check(3, "ON")


def test_evaluate_spec_and_cpk(tmp_path):
    import numpy as np
    cfg = AppConfig(variables=[Variable(id="v", name="V", kind="actual", region=Rect(x=0, y=0, w=5, h=5))])
    job = ReportJob(ReportDef(id="r"), cfg, 0, 100, "", None, {"v": VarLimits(lsl=9, usl=11, target=10)})
    rng = np.random.default_rng(1)
    rows = [(i, 10 + rng.normal(0, 0.1), None) for i in range(100)]
    r = evaluate_var(job, ReportVar(var_id="v", criterion="spec"), rows)
    assert r.ok and r.pct_in == 100
    r = evaluate_var(job, ReportVar(var_id="v", criterion="cpk", cpk_min=5), rows)
    assert r.ok is False and r.cpk is not None and r.cpk < 5
    rows.append((101, 12.0, None))
    assert evaluate_var(job, ReportVar(var_id="v"), rows).ok is False


def test_report_after_tour_in_demo(tmp_path):
    ft = FakeTime()
    sim = HmiSimulator(scenario=Scenario(period=10_000), clock=ft.clock)
    ctx = build(tmp_path, demo=True, source=SimulatorSource(sim), clock=ft.clock, sleep=ft.sleep)
    out_dir = tmp_path / "salida"
    rep = ReportDef(id="turno", name="Reporte de prueba", triggers=[ReportTrigger(kind="tour")],
                    variables=[ReportVar(var_id="diam"), ReportVar(var_id="z1", criterion="cpk", cpk_min=0.5),
                               ReportVar(var_id="inyeccion")],
                    name_var="receta_hmi", output_dir=str(out_dir), reset_analysis=True, min_interval_s=0)
    ctx.config.reports = [rep]
    ctx.engine.reconfigure(ctx.config)
    from extrusion_monitor.profiles import save_profile
    save_profile(ctx.workspace, ctx.recipes.names()[0], ctx.config)
    for _ in range(40):
        ctx.engine.step()
        ft.t += 1
    assert ctx.engine.reports.wait_idle()
    pdfs = sorted(out_dir.glob("*.pdf"))
    assert pdfs, list(out_dir.iterdir()) if out_dir.exists() else "sin carpeta"
    assert pdfs[0].name.startswith("THHN-12AWG-NEGRO")
    assert pdfs[0].read_bytes()[:4] == b"%PDF"
    job, out = ctx.engine.reports.done[-1]
    assert not out.error and out.csv is not None
    with open(out.csv, encoding="utf-8-sig") as f:
        header = next(csv.reader(f, delimiter=";"))
    assert len(header) == 4
    # El segundo reporte empieza donde terminó el primero.
    if len(ctx.engine.reports.done) > 1:
        a, b = ctx.engine.reports.done[-2][0], ctx.engine.reports.done[-1][0]
        assert b.since == a.until
    ctx.engine.step()
    assert any(e.kind == "report" for e in ctx.engine.last.events) or \
        any("Reporte" in (e[5] or "") for e in ctx.engine.historian.events(0))


def test_decrease_trigger_and_both_criterion(tmp_path):
    import numpy as np
    ws = Workspace(tmp_path)
    cfg = AppConfig(variables=[Variable(id="len", name="Longitud", kind="actual", region=Rect(x=0, y=0, w=5, h=5))],
                    reports=[ReportDef(id="r", min_interval_s=0,
                                       triggers=[ReportTrigger(kind="decrease", var_id="len", value=10)])])
    m = ReportManager(ws, lambda: 0.0)
    fired = [bool(m.check(cfg, {"len": Reading("len", value=v, ok=True)}, [])) for v in (100, 900, 2500, 2495, 3)]
    assert fired == [False, False, False, False, True]  # solo el reinicio del carrete, no el ruido

    job = ReportJob(ReportDef(id="r"), cfg, 0, 100, "", None, {"len": VarLimits(lsl=9, usl=11)})
    rng = np.random.default_rng(2)
    rows = [(i, 10 + rng.normal(0, 0.1), None) for i in range(50)]
    assert evaluate_var(job, ReportVar(var_id="len", criterion="both", cpk_min=1.0), rows).ok
    rows.append((60, 11.5, None))  # una lectura fuera de spec: falla aunque el Cpk alcance
    r = evaluate_var(job, ReportVar(var_id="len", criterion="both", cpk_min=0.1), rows)
    assert r.ok is False and "fuera de spec" in r.note


def test_pdf_is_complete_with_special_text(tmp_path):
    from extrusion_monitor.reports import generate
    from extrusion_monitor.storage import Historian
    h = Historian(tmp_path / "h.sqlite")
    h.write_samples([(1000.0 + i, "v", float("nan") if i == 5 else 10.0 + (i % 3) * 0.1, None) for i in range(50)])
    h.write_events([(1010.0, "raised", 2, "R", "v", "valor < 5 & otro > 7 → Δ σ ≤", None)])
    cfg = AppConfig(variables=[Variable(id="v", name="Zona › 1", unit="°C", kind="actual",
                                        region=Rect(x=0, y=0, w=5, h=5))])
    rep = ReportDef(id="r", name="R & <prueba>", variables=[ReportVar(var_id="v", criterion="both")])
    job = ReportJob(rep, cfg, 1000, 1060, "len < 5", "Receta → 1", {"v": VarLimits(lsl=9, usl=11, target=10)},
                    base_name="x", out_dir=tmp_path / "out")
    out = generate(job, h)
    data = out.pdf.read_bytes()
    assert data.startswith(b"%PDF") and data.rstrip().endswith(b"%%EOF")
    assert not list((tmp_path / "out").glob("*.tmp.pdf"))
    assert b"/Symbol" not in data
