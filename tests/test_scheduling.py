"""Disparadores de recorridos: intervalo, fuera de pantalla, selector, valor a cero y cuenta regresiva."""
from extrusion_monitor.acquisition import Reading
from extrusion_monitor.config import AppConfig, Page, TourDef, TourStep
from extrusion_monitor.scheduling import TourScheduler


def make(**kw):
    t = [0.0]
    tour = TourDef(id="t1", name="T1", steps=[TourStep(id="s", page="main")], **kw)
    cfg = AppConfig(pages=[Page(id="main", name="Main")], tours=[tour])
    return TourScheduler(cfg, lambda: t[0]), t


def rd(vid, value=None, text=None):
    return Reading(vid, value=value, text=text, ok=True)


def test_interval():
    s, t = make(interval_s=60)
    s.update(0, set(), {})
    job = s.pop()
    assert job and job.tour_id == "t1"
    s.mark_run("t1", 0)
    s.update(30, set(), {})
    assert s.pop() is None
    s.update(61, set(), {})
    assert s.pop() is not None


def test_off_page_with_countdown_and_snooze():
    s, t = make(off_page="main", off_page_s=120, confirm=True, countdown_s=15, snooze_s=300)
    s.update(0, {"main"}, {})
    s.update(10, set(), {})
    s.update(100, set(), {})
    assert not s.pending_prompts()
    msgs = s.update(131, set(), {})
    assert msgs and "t1" in s.pending_prompts() and s.pop() is None
    t[0] = 135
    s.snooze("t1")  # el operador pospone
    s.update(140, set(), {})
    assert not s.pending_prompts() and s.pop() is None
    s.update(436, set(), {})  # tras posponer vuelve a aparecer
    assert "t1" in s.pending_prompts()
    s.update(452, set(), {})  # ignorado: se ejecuta solo
    job = s.pop()
    assert job and job.consent
    s.mark_run("t1", 452)
    s.update(453, {"main"}, {})
    assert s.pop() is None


def test_confirm_runs_immediately():
    s, t = make(zero_var="vel", confirm=True)
    s.update(0, set(), {"vel": rd("vel", 100)})
    s.update(1, set(), {"vel": rd("vel", 0)})
    assert "t1" in s.pending_prompts()
    s.confirm("t1")
    job = s.pop()
    assert job.consent and not s.pending_prompts()


def test_selector_change_to_state_and_zero_edge():
    s, _ = make(selector_var="sel", selector_state="OFF")
    s.update(0, set(), {"sel": rd("sel", text="ON")})
    assert s.pop() is None
    s.update(1, set(), {"sel": rd("sel", text="OFF")})
    assert s.pop() is not None
    s.update(2, set(), {"sel": rd("sel", text="ON")})  # cambio a otro estado: no dispara
    assert s.pop() is None

    s, _ = make(zero_var="vel", zero_threshold=0.5)
    s.update(0, set(), {"vel": rd("vel", 0)})  # ya en cero al iniciar: no es flanco
    assert s.pop() is None
    s.update(1, set(), {"vel": rd("vel", 50)})
    s.update(2, set(), {"vel": rd("vel", 0.2)})
    assert s.pop() is not None
    s.update(3, set(), {"vel": rd("vel", 0.1)})
    assert s.pop() is None
