"""Reportes PDF automáticos.

Un reporte se dispara cuando una variable cruza un valor, cambia, un selector cambia de estado o
se ejecuta un recorrido. Abarca desde el fin del reporte anterior hasta el disparo. Contiene la
evaluación de cada variable (en especificación o Cpk mínimo), gráficas, comportamiento, eventos
y opcionalmente un CSV con los datos.

La generación corre en un hilo aparte con los datos del historial, así el ciclo de monitoreo
no se detiene; las gráficas se reducen a pocos cientos de puntos.
"""
from __future__ import annotations

import json
import logging
import queue
import re
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

import numpy as np

from .config import AppConfig, ReportDef, ReportTrigger, Workspace

log = logging.getLogger(__name__)

MAX_PLOT_POINTS = 400
MAX_EVENTS = 400
LEVEL_NAMES = {0: "OK", 1: "Info", 2: "Aviso", 3: "Alarma"}
_OPS = {">": lambda a, b: a > b, ">=": lambda a, b: a >= b, "<": lambda a, b: a < b, "<=": lambda a, b: a <= b}


@dataclass
class VarLimits:
    lsl: Optional[float] = None
    usl: Optional[float] = None
    target: Optional[float] = None
    expected: Optional[str] = None  # selector / texto: estado esperado


@dataclass
class ReportJob:
    report: ReportDef
    config: AppConfig
    since: float
    until: float
    reason: str
    recipe: Optional[str]
    limits: dict[str, VarLimits]
    behavior_models: list = field(default_factory=list)
    base_name: str = ""
    out_dir: Optional[Path] = None


@dataclass
class VarResult:
    var_id: str
    label: str
    unit: str
    n: int = 0
    mean: Optional[float] = None
    minimum: Optional[float] = None
    maximum: Optional[float] = None
    std: Optional[float] = None
    cpk: Optional[float] = None
    pct_in: Optional[float] = None
    limits: VarLimits = field(default_factory=VarLimits)
    criterion: str = "spec"
    ok: Optional[bool] = None  # None = sin datos / sin límites
    note: str = ""
    t: np.ndarray = field(default_factory=lambda: np.empty(0))
    y: np.ndarray = field(default_factory=lambda: np.empty(0))


@dataclass
class ReportOutput:
    pdf: Optional[Path]
    csv: Optional[Path]
    ok: Optional[bool]
    results: list[VarResult]
    error: str = ""


# --- disparadores ------------------------------------------------------------------------
class ReportManager:
    """Detecta los disparadores en cada ciclo y encola la generación en un hilo aparte."""

    def __init__(self, workspace: Workspace, clock: Callable[[], float] = time.time):
        self.workspace = workspace
        self.clock = clock
        self._prev: dict[tuple[str, int], object] = {}
        self._last_fire: dict[str, float] = {}
        self._state = self._load_state()
        self._queue: "queue.Queue[Optional[tuple[ReportJob, Callable]]]" = queue.Queue()
        self._thread: Optional[threading.Thread] = None
        self.done: deque = deque(maxlen=50)  # (ReportJob, ReportOutput) para el motor / la interfaz
        self.busy = False

    # estado persistente: fin del último reporte de cada definición
    def _load_state(self) -> dict:
        try:
            return json.loads(self.workspace.reports_state_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def _save_state(self) -> None:
        try:
            self.workspace.reports_state_file.write_text(json.dumps(self._state), encoding="utf-8")
        except OSError:
            log.exception("No se pudo guardar el estado de reportes")

    def last_end(self, report_id: str) -> Optional[float]:
        v = self._state.get(report_id)
        return float(v) if v is not None else None

    def check(self, config: AppConfig, readings: dict, events: list) -> list[tuple[ReportDef, str]]:
        """Devuelve los reportes disparados en este ciclo (con su motivo)."""
        fired = []
        now = self.clock()
        for rep in config.reports:
            if not rep.enabled or not rep.triggers:
                continue
            reasons = [r for i, tr in enumerate(rep.triggers)
                       if (r := self._eval(rep.id, i, tr, config, readings, events))]
            if not reasons:
                continue
            last = self._last_fire.get(rep.id)
            if last is not None and now - last < rep.min_interval_s:
                continue
            fired.append((rep, "; ".join(reasons)))
        return fired

    def _eval(self, rid: str, i: int, tr: ReportTrigger, config: AppConfig, readings: dict,
              events: list) -> str:
        key = (rid, i)
        if tr.kind == "tour":
            for e in events:
                if e.kind == "tour_done" and (tr.tour_id is None or e.var_id == tr.tour_id):
                    t = config.get_tour(e.var_id)
                    return f"recorrido «{t.name if t else e.var_id}» ejecutado"
            return ""
        var = config.variable(tr.var_id) if tr.var_id else None
        rd = readings.get(tr.var_id) if tr.var_id else None
        if var is None or rd is None or not rd.ok:
            return ""
        label = config.var_label(var)
        prev = self._prev.get(key)
        if tr.kind == "cross":
            if rd.value is None:
                return ""
            cond = _OPS[tr.op](rd.value, tr.value)
            self._prev[key] = cond
            if prev is False and cond:
                return f"{label} {tr.op} {tr.value:g} ({rd.value:g})"
            return ""
        if tr.kind == "change":
            cur = rd.text if var.kind in ("text", "selector") else rd.value
            if cur is None:
                return ""
            if prev is None:
                self._prev[key] = cur
                return ""
            if isinstance(cur, str) or isinstance(prev, str):
                changed = cur != prev
            else:
                changed = abs(cur - prev) > tr.value if tr.value > 0 else cur != prev
            if changed:
                self._prev[key] = cur
                return f"{label} cambió de {prev} a {cur}"
            return ""
        if tr.kind == "selector":
            cur = rd.text
            if cur is None:
                return ""
            self._prev[key] = cur
            if prev is not None and cur != prev and (tr.state is None or cur == tr.state):
                return f"{label}: {prev} → {cur}"
        return ""

    # --- periodo y cola ------------------------------------------------------------------
    def make_job(self, rep: ReportDef, config: AppConfig, reason: str, recipe: Optional[str],
                 limits: dict[str, VarLimits], behavior_models: list, name_text: Optional[str]) -> ReportJob:
        now = self.clock()
        since = self.last_end(rep.id)
        earliest = now - rep.max_period_h * 3600
        if since is None or since < earliest:
            since = earliest
        self._state[rep.id] = now
        self._last_fire[rep.id] = now
        self._save_state()
        stamp = time.strftime("%Y%m%d_%H%M%S", time.localtime(now))
        base = safe_filename(name_text) if name_text else ""
        base = base or stamp
        out = Path(rep.output_dir) if rep.output_dir else self.workspace.default_reports_dir()
        return ReportJob(rep, config, since, now, reason, recipe, limits, behavior_models, base, out)

    def submit(self, job: ReportJob, historian, on_done: Callable[[ReportJob, ReportOutput], None]) -> None:
        self._queue.put((job, historian, on_done))
        if self._thread is None or not self._thread.is_alive():
            self._thread = threading.Thread(target=self._worker, name="reportes", daemon=True)
            self._thread.start()

    def _worker(self) -> None:
        while True:
            try:
                item = self._queue.get(timeout=30)
            except queue.Empty:
                return  # sin trabajo: el hilo termina y se vuelve a crear cuando haga falta
            job, historian, on_done = item
            self.busy = True
            try:
                out = generate(job, historian)
            except Exception as exc:  # el reporte nunca debe tumbar el monitoreo
                log.exception("Fallo al generar el reporte")
                out = ReportOutput(None, None, None, [], error=str(exc))
            finally:
                self.busy = False
            self.done.append((job, out))
            try:
                on_done(job, out)
            except Exception:
                log.exception("Error al notificar el reporte")

    def wait_idle(self, timeout: float = 30.0) -> bool:
        """Para pruebas: espera a que se generen los reportes encolados."""
        t0 = time.monotonic()
        while time.monotonic() - t0 < timeout:
            if self._queue.empty() and not self.busy:
                return True
            time.sleep(0.05)
        return False


def safe_filename(text: str) -> str:
    text = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "_", str(text)).strip(" ._")
    return text[:80]


def _unique(path: Path) -> Path:
    if not path.exists():
        return path
    stamp = time.strftime("%Y%m%d_%H%M%S")
    cand = path.with_name(f"{path.stem}_{stamp}{path.suffix}")
    n = 2
    while cand.exists():
        cand = path.with_name(f"{path.stem}_{stamp}_{n}{path.suffix}")
        n += 1
    return cand


# --- cálculo ---------------------------------------------------------------------------
def evaluate_var(job: ReportJob, rv, rows: list[tuple]) -> VarResult:
    from .analysis.statistics import capability
    cfg = job.config
    var = cfg.variable(rv.var_id)
    lim = job.limits.get(rv.var_id, VarLimits())
    res = VarResult(rv.var_id, cfg.var_label(var) if var else rv.var_id, var.unit if var else "",
                    limits=lim, criterion=rv.criterion)
    if var is not None and var.kind in ("text", "selector"):
        texts = [r[2] for r in rows if r[2] is not None]
        res.n = len(texts)
        if lim.expected and texts:
            # Tiempo en el estado esperado (cada muestra vale hasta la siguiente).
            ts = [r[0] for r in rows if r[2] is not None] + [job.until]
            dur = np.diff(ts)
            good = sum(d for d, tx in zip(dur, texts) if tx == lim.expected)
            res.pct_in = 100.0 * good / max(dur.sum(), 1e-9)
            res.ok = res.pct_in >= 99.999
            res.note = f"esperado «{lim.expected}»"
        elif texts:
            res.note = "estados: " + ", ".join(sorted(set(texts))[:6])
        return res
    vals = [(r[0], r[1]) for r in rows if r[1] is not None]
    if not vals:
        res.note = "sin datos en el periodo"
        return res
    arr = np.asarray(vals, float)
    res.t, res.y = arr[:, 0], arr[:, 1]
    y = res.y
    res.n = len(y)
    res.mean, res.minimum, res.maximum = float(y.mean()), float(y.min()), float(y.max())
    res.std = float(y.std(ddof=1)) if len(y) > 1 else 0.0
    has_spec = lim.lsl is not None or lim.usl is not None
    if has_spec:
        inside = np.ones(len(y), bool)
        if lim.lsl is not None:
            inside &= y >= lim.lsl
        if lim.usl is not None:
            inside &= y <= lim.usl
        res.pct_in = 100.0 * float(inside.mean())
        cap = capability(y, lim.lsl, lim.usl)
        res.cpk = cap.cpk if cap else None
    if rv.criterion == "cpk":
        if res.cpk is None:
            res.note = "Cpk no calculable (faltan límites o datos)"
        else:
            res.ok = res.cpk >= rv.cpk_min
            res.note = f"Cpk mín. {rv.cpk_min:g}"
    elif has_spec:
        res.ok = res.pct_in >= 99.999
        res.note = "todas las lecturas en especificación"
    else:
        res.note = "sin límites en la receta"
    return res


def behavior_series(model, historian, since: float, until: float) -> tuple[np.ndarray, np.ndarray]:
    """D²/umbral del modelo en el periodo, recalculado desde el historial."""
    from .analysis.statistics import align
    series = {}
    for vid in model.variables:
        rows = historian.samples(vid, since, until)
        rows = [r for r in rows if r[1] is not None]
        if not rows:
            return np.empty(0), np.empty(0)
        a = np.asarray(rows, float)
        series[vid] = (a[:, 0], a[:, 1])
    grid, m, names = align(series, max(model.step_s, 1.0), max(10 * model.step_s, 120.0), since, until)
    if not len(grid) or names != model.variables:
        return np.empty(0), np.empty(0)
    d = m - np.asarray(model.mean)
    d2 = np.einsum("ij,jk,ik->i", d, np.asarray(model.cov_inv), d)
    thr = model.d2_threshold * model.sensitivity or 1.0
    return grid, d2 / thr


def _downsample(t: np.ndarray, y: np.ndarray, n: int = MAX_PLOT_POINTS) -> tuple[np.ndarray, np.ndarray]:
    """Mín/máx por tramo: conserva los picos con pocos puntos."""
    if len(t) <= n:
        return t, y
    buckets = np.array_split(np.arange(len(t)), n // 2)
    idx = []
    for b in buckets:
        seg = y[b]
        i1, i2 = b[int(np.argmin(seg))], b[int(np.argmax(seg))]
        idx.extend(sorted((i1, i2)))
    idx = np.asarray(idx)
    return t[idx], y[idx]


# --- PDF -------------------------------------------------------------------------------
def generate(job: ReportJob, historian) -> ReportOutput:
    rep, cfg = job.report, job.config
    out_dir = Path(job.out_dir or ".")
    out_dir.mkdir(parents=True, exist_ok=True)
    results = []
    for rv in rep.variables:
        rows = historian.samples_full(rv.var_id, job.since, job.until)
        results.append(evaluate_var(job, rv, rows))
    verdicts = [r.ok for r in results if r.ok is not None]
    overall = (all(verdicts) if verdicts else None)
    csv_path = None
    csv_vars = [rv.var_id for rv in rep.variables if rv.csv]
    if rep.export_csv and csv_vars:
        csv_path = _unique(out_dir / f"{job.base_name}.csv")
        headers = {v: cfg.var_label(cfg.variable(v)) + (f" [{cfg.variable(v).unit}]" if cfg.variable(v).unit else "")
                   for v in csv_vars if cfg.variable(v)}
        historian.export_csv(csv_path, job.since, job.until, variables=csv_vars, headers=headers)
    pdf_path = _unique(out_dir / f"{job.base_name}.pdf")
    _write_pdf(pdf_path, job, results, overall, historian)
    return ReportOutput(pdf_path, csv_path, overall, results)


def _fmt(v: Optional[float], d: int = 3) -> str:
    if v is None:
        return "—"
    if abs(v) >= 1000:
        return f"{v:,.0f}"
    return f"{v:.{d}f}".rstrip("0").rstrip(".") or "0"


def _ts(t: float) -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(t))


def _chart(t: np.ndarray, y: np.ndarray, width: float, height: float, lines: list[tuple[float, object]],
           since: float, until: float, y_label: str = ""):
    from reportlab.graphics.charts.lineplots import LinePlot
    from reportlab.graphics.shapes import Drawing, String
    from reportlab.lib import colors

    d = Drawing(width, height)
    lp = LinePlot()
    lp.x, lp.y = 45, 22
    lp.width, lp.height = width - 60, height - 34
    t, y = _downsample(t, y)
    data = [list(zip(t.tolist(), y.tolist()))]
    vals = list(y)
    for val, _ in lines:
        data.append([(since, val), (until, val)])
        vals.append(val)
    lp.data = data
    lp.lines[0].strokeColor = colors.HexColor("#1565c0")
    lp.lines[0].strokeWidth = 1.2
    for i, (_, col) in enumerate(lines, 1):
        lp.lines[i].strokeColor = col
        lp.lines[i].strokeWidth = 0.9
        lp.lines[i].strokeDashArray = [4, 3]
    lo, hi = float(min(vals)), float(max(vals))
    pad = (hi - lo) * 0.08 or max(abs(hi) * 0.05, 1e-3)
    lp.yValueAxis.valueMin, lp.yValueAxis.valueMax = lo - pad, hi + pad
    lp.yValueAxis.labels.fontSize = 6
    lp.xValueAxis.valueMin, lp.xValueAxis.valueMax = since, until
    span = until - since
    fmt = "%H:%M" if span <= 86400 else "%d/%m %H:%M"
    lp.xValueAxis.labelTextFormat = lambda v: time.strftime(fmt, time.localtime(v))
    lp.xValueAxis.valueSteps = list(np.linspace(since, until, 6))
    lp.xValueAxis.labels.fontSize = 6
    d.add(lp)
    if y_label:
        d.add(String(2, height - 9, y_label, fontSize=7, fillColor=colors.HexColor("#424242")))
    return d


def _write_pdf(path: Path, job: ReportJob, results: list[VarResult], overall: Optional[bool], historian) -> None:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    rep, cfg = job.report, job.config
    styles = getSampleStyleSheet()
    small = styles["BodyText"].clone("small", fontSize=7, leading=8.5)
    page = landscape(A4)
    doc = SimpleDocTemplate(str(path), pagesize=page, leftMargin=12 * mm, rightMargin=12 * mm,
                            topMargin=12 * mm, bottomMargin=12 * mm, title=rep.name, author="Extrusion Monitor")
    width = page[0] - 24 * mm
    story = [Paragraph(f"{rep.name} — {cfg.machine_name}", styles["Title"])]
    info = [["Periodo", f"{_ts(job.since)}  →  {_ts(job.until)}  ({(job.until - job.since) / 3600:.2f} h)"],
            ["Receta", job.recipe or "—"], ["Motivo", job.reason], ["Generado", _ts(time.time())]]
    t = Table(info, colWidths=[30 * mm, width - 30 * mm])
    t.setStyle(TableStyle([("FONTSIZE", (0, 0), (-1, -1), 8), ("TEXTCOLOR", (0, 0), (0, -1), colors.grey)]))
    story += [t, Spacer(1, 4 * mm)]
    color = {True: "#2e7d32", False: "#c62828", None: "#757575"}[overall]
    text = {True: "CONFORME", False: "NO CONFORME", None: "SIN EVALUACIÓN"}[overall]
    story.append(Paragraph(f"<font color='{color}' size=16><b>Resultado: {text}</b></font>", styles["BodyText"]))
    story.append(Spacer(1, 4 * mm))

    head = ["Variable", "Unidad", "n", "Media", "Mín", "Máx", "σ", "LIE", "LSE", "% en spec", "Cpk", "Criterio",
            "Resultado"]
    rows = [head]
    for r in results:
        crit = "Cpk" if r.criterion == "cpk" else "Spec"
        verdict = {True: "OK", False: "NO", None: "—"}[r.ok]
        rows.append([Paragraph(r.label, small), r.unit, str(r.n), _fmt(r.mean), _fmt(r.minimum), _fmt(r.maximum),
                     _fmt(r.std), _fmt(r.limits.lsl), _fmt(r.limits.usl),
                     "—" if r.pct_in is None else f"{r.pct_in:.1f}", _fmt(r.cpk, 2),
                     Paragraph(f"{crit}: {r.note}", small), verdict])
    col_w = [60 * mm, 14 * mm, 12 * mm] + [17 * mm] * 6 + [16 * mm, 13 * mm]
    col_w += [width - sum(col_w) - 17 * mm, 17 * mm]
    t = Table(rows, colWidths=col_w, repeatRows=1)
    style = [("FONTSIZE", (0, 0), (-1, -1), 7), ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#263238")),
             ("TEXTCOLOR", (0, 0), (-1, 0), colors.white), ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
             ("VALIGN", (0, 0), (-1, -1), "MIDDLE")]
    for i, r in enumerate(results, 1):
        if r.ok is not None:
            style.append(("BACKGROUND", (-1, i), (-1, i), colors.HexColor("#c8e6c9" if r.ok else "#ffcdd2")))
    t.setStyle(TableStyle(style))
    story += [t, Spacer(1, 5 * mm)]

    chart_vars = {rv.var_id for rv in rep.variables if rv.chart}
    charts = [r for r in results if r.var_id in chart_vars and len(r.t) >= 2]
    if charts:
        story.append(Paragraph("Tendencias", styles["Heading2"]))
        cells = []
        cw, ch = width / 2 - 2 * mm, 55 * mm
        for r in charts:
            lines = []
            if r.limits.lsl is not None:
                lines.append((r.limits.lsl, colors.HexColor("#c62828")))
            if r.limits.usl is not None:
                lines.append((r.limits.usl, colors.HexColor("#c62828")))
            if r.limits.target is not None:
                lines.append((r.limits.target, colors.HexColor("#9e9e9e")))
            label = r.label + (f" [{r.unit}]" if r.unit else "")
            cells.append(_chart(r.t, r.y, cw, ch, lines, job.since, job.until, label))
        grid = [cells[i:i + 2] + [""] * (2 - len(cells[i:i + 2])) for i in range(0, len(cells), 2)]
        story += [Table(grid, colWidths=[cw + 2 * mm] * 2), Spacer(1, 4 * mm)]

    if job.behavior_models:
        story.append(Paragraph("Comportamiento (D² / umbral; > 1 = fuera de lo normal)", styles["Heading2"]))
        cells = []
        cw, ch = width / 2 - 2 * mm, 55 * mm
        for m in job.behavior_models:
            bt, br = behavior_series(m, historian, job.since, job.until)
            if len(bt) < 2:
                story.append(Paragraph(f"«{m.name}»: sin datos suficientes en el periodo.", small))
                continue
            out = float((br > 1).mean() * 100)
            cells.append(_chart(bt, br, cw, ch, [(1.0, colors.HexColor("#c62828"))], job.since, job.until,
                                f"{m.name}: {out:.1f} % del tiempo fuera de lo normal"))
        if cells:
            grid = [cells[i:i + 2] + [""] * (2 - len(cells[i:i + 2])) for i in range(0, len(cells), 2)]
            story += [Table(grid, colWidths=[cw + 2 * mm] * 2), Spacer(1, 4 * mm)]

    ev_vars = {rv.var_id for rv in rep.variables if rv.events}
    if ev_vars or rep.include_general_events:
        evs = [e for e in historian.events_between(job.since, job.until)
               if (e[4] in ev_vars) or (rep.include_general_events and not e[4])]
        story.append(Paragraph(f"Eventos ({len(evs)})", styles["Heading2"]))
        if evs:
            rows = [["Fecha y hora", "Nivel", "Variable", "Mensaje"]]
            for e in evs[-MAX_EVENTS:]:
                var = cfg.variable(e[4]) if e[4] else None
                rows.append([_ts(e[0]), LEVEL_NAMES.get(e[2], str(e[2])),
                             Paragraph(cfg.var_label(var) if var else (e[4] or ""), small),
                             Paragraph(str(e[5]), small)])
            t = Table(rows, colWidths=[32 * mm, 16 * mm, 60 * mm, width - 108 * mm], repeatRows=1)
            t.setStyle(TableStyle([("FONTSIZE", (0, 0), (-1, -1), 7), ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
                                   ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#263238")),
                                   ("TEXTCOLOR", (0, 0), (-1, 0), colors.white), ("VALIGN", (0, 0), (-1, -1), "TOP")]))
            story.append(t)
            if len(evs) > MAX_EVENTS:
                story.append(Paragraph(f"Se muestran los últimos {MAX_EVENTS} eventos.", small))
        else:
            story.append(Paragraph("Sin eventos en el periodo.", small))
    doc.build(story)
