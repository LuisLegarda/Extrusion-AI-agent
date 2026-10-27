"""Dibujo de cada tipo de análisis estadístico (gráficas, tablas e interpretación en lenguaje claro).

Cada función `render_<tipo>(R)` recibe un `Render` con los datos ya preparados y agrega gráficas, tablas y
texto. Los títulos de las gráficas se cambian con doble clic sobre ellos y los colores de las series desde
el botón «Colores» (se guardan en el estilo del análisis).
"""
from __future__ import annotations

import math
from typing import Callable, Optional

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QDoubleSpinBox, QFormLayout, QFrame, QGridLayout, QHBoxLayout, QHeaderView, QInputDialog, QLabel, QSlider,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from ..analysis import stattools as st
from ..analysis.dataset import VarData
from ..analysis.statistics import align
from ..i18n import tr
from . import theme

PROB_TICKS = [0.1, 1, 5, 10, 20, 30, 50, 70, 80, 90, 95, 99, 99.9]


def f(v, d: int = 4) -> str:
    if v is None or (isinstance(v, float) and not math.isfinite(v)):
        return "—"
    if isinstance(v, (int, np.integer)):
        return f"{int(v):,}"
    return f"{v:.{d}g}"


def fp(p: Optional[float]) -> str:
    if p is None:
        return "—"
    return "< 0.001" if p < 0.001 else f"{p:.3f}"


def grade(v: Optional[float]) -> str:
    if v is None:
        return "—"
    color = theme.c("good_text") if v >= 1.33 else (theme.c("warning_text") if v >= 1.0 else theme.c("critical"))
    return f"<b style='color:{color}'>{v:.2f}</b>"


class Render(QWidget):
    """Área de resultados de un análisis: cuadrícula de gráficas, tablas y textos."""

    titleEdited = Signal(str, str)  # clave de la gráfica, título nuevo

    def __init__(self, record: dict, data: list[VarData], ctx=None, extra: Optional[dict] = None):
        super().__init__()
        self.record = record
        self.data = data
        self.ctx = ctx
        self.extra = extra or {}
        self.style = record.setdefault("style", {})
        self.series: list[str] = []  # nombres de las series que usan color (para el diálogo de colores)
        self.csv_rows: list[list] = []
        self.csv_header: list[str] = []
        self.lay = QGridLayout(self)
        self.lay.setContentsMargins(0, 0, 0, 0)
        self.lay.setSpacing(10)
        self._row = 0

    def data_table(self) -> tuple[list[str], list[list]]:
        """Los datos con que se calculó el análisis: fecha, grupo y una columna por variable (para Minitab)."""
        from ..tabular import epoch
        if self.extra.get("problems") is not None:
            from ..analysis.problems import CSV_COLUMNS, table_row
            return [tr(c) for c in CSV_COLUMNS], [table_row(r) for r in self.extra["problems"]]
        series = [v for v in self.data if len(v.y)]
        if not series:
            return [], []
        grouped = any(len(v.groups) and v.groups.any() for v in series)
        by_key: dict[tuple, dict] = {}  # (instante, grupo): varias líneas comparten los mismos minutos
        for i, v in enumerate(series):
            for k in range(len(v.y)):
                g = str(v.groups[k]) if grouped and len(v.groups) else ""
                by_key.setdefault((round(float(v.t[k]), 3), g), {})[i] = float(v.y[k])
        names = [v.label + (f" ({v.unit})" if v.unit else "") for v in series]
        header = [tr("fecha_hora")] + ([tr("Grupo")] if grouped else []) + names
        rows = []
        for (t, g) in sorted(by_key):
            r = by_key[(t, g)]
            rows.append([epoch(t)] + ([g] if grouped else []) + [r.get(i) for i in range(len(series))])
        return header, rows

    # --- utilidades -----------------------------------------------------------------------------------
    @property
    def params(self) -> dict:
        return self.record.get("params", {})

    def color(self, i: int, name: str = "") -> QColor:
        cols = self.style.get("colors") or []
        if name and name not in self.series:
            self.series.append(name)
        k = self.series.index(name) if name in self.series else i
        return QColor(cols[k]) if k < len(cols) and cols[k] else QColor(theme.series(k))

    def plot(self, key: str, title: str, row: int, col: int, rowspan: int = 1, colspan: int = 1,
             date_axis: bool = False, min_h: int = 280) -> pg.PlotWidget:
        w = pg.PlotWidget(axisItems={"bottom": pg.DateAxisItem()} if date_axis else None)
        w.setMinimumHeight(min_h)
        w.showGrid(x=True, y=True, alpha=0.2)
        w.setBackground(theme.c("plot_bg"))
        text = self.style.get("titles", {}).get(key) or title
        w.setTitle(f"<b>{text}</b>", color=theme.c("title"))
        lbl = w.getPlotItem().titleLabel
        lbl.setToolTip(tr("Doble clic para cambiar el título"))
        lbl.mouseDoubleClickEvent = lambda _e, k=key, t=text: self._rename(k, t)
        self.lay.addWidget(w, row, col, rowspan, colspan)
        return w

    def _rename(self, key: str, current: str) -> None:
        text, ok = QInputDialog.getText(self, tr("Título de la gráfica"), tr("Título:"), text=current)
        if ok:
            self.titleEdited.emit(key, text.strip())

    def table(self, headers: list[str], rows: list[list], row: int, col: int, colspan: int = 1,
              title: str = "") -> QTableWidget:
        box = QWidget()
        bl = QVBoxLayout(box)
        bl.setContentsMargins(0, 0, 0, 0)
        if title:
            bl.addWidget(QLabel(f"<b style='color:{theme.c('title')}'>{title}</b>"))
        t = QTableWidget(len(rows), len(headers))
        t.setHorizontalHeaderLabels(headers)
        t.verticalHeader().setVisible(False)
        t.setEditTriggers(QTableWidget.NoEditTriggers)
        for r, vals in enumerate(rows):
            for c, v in enumerate(vals):
                it = QTableWidgetItem(v if isinstance(v, str) else f(v))
                if c:
                    it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                t.setItem(r, c, it)
        hh = t.horizontalHeader()
        hh.setSectionResizeMode(QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(0, QHeaderView.Stretch)  # la primera columna (nombres) toma el espacio sobrante
        h = t.horizontalHeader().height() + sum(t.rowHeight(i) for i in range(min(len(rows), 14))) + 6
        t.setMinimumHeight(min(h, 420))
        t.setMaximumHeight(max(h, 120) if len(rows) <= 14 else 420)
        bl.addWidget(t)
        self.lay.addWidget(box, row, col, 1, colspan)
        if not self.csv_rows:
            self.csv_header, self.csv_rows = list(headers), [list(r) for r in rows]  # valores sin formato
        return t

    def text(self, html: str, row: int, col: int = 0, colspan: int = 2) -> QLabel:
        lb = QLabel(html.replace("< ", "&lt; "))  # «p < 0.05» en texto enriquecido
        lb.setWordWrap(True)
        lb.setTextFormat(Qt.RichText)
        lb.setObjectName("insight")
        lb.setStyleSheet(f"QLabel#insight {{ background:{theme.c('surface2')}; border-left: 4px solid "
                         f"{theme.c('accent')}; padding: 8px 12px; border-radius: 4px; }}")
        self.lay.addWidget(lb, row, col, 1, colspan)
        return lb

    def empty(self, msg: str) -> None:
        lb = QLabel(msg)
        lb.setAlignment(Qt.AlignCenter)
        lb.setWordWrap(True)
        lb.setStyleSheet(f"color:{theme.c('muted')}; padding: 40px;")
        self.lay.addWidget(lb, 0, 0)


# --- piezas de gráficas ----------------------------------------------------------------------------


def colormap():
    """Viridis (archivo de pyqtgraph); si el ejecutable no lo trae, la misma paleta en 6 puntos."""
    try:
        return pg.colormap.get("viridis")
    except Exception:
        return pg.ColorMap(np.linspace(0, 1, 6), [(68, 1, 84), (65, 68, 135), (42, 120, 142), (34, 168, 132),
                                                   (122, 209, 81), (253, 231, 37)])


def cat_axis(w: pg.PlotWidget, names: list[str]) -> None:
    w.getAxis("bottom").setTicks([[(i, str(n)) for i, n in enumerate(names)]])


def hist_bars(w, y, edges, color: QColor, density: bool, alpha: int = 150):
    counts, _ = np.histogram(y, bins=edges)
    width = edges[1] - edges[0]
    h = counts / (len(y) * width) if density and len(y) else counts
    c = QColor(color)
    c.setAlpha(alpha)
    w.addItem(pg.BarGraphItem(x=edges[:-1] + width / 2, height=h, width=width * 0.95, brush=pg.mkBrush(c),
                              pen=pg.mkPen(QColor(color).darker(140), width=0.6)))
    return h


def normal_curve(w, mean, sd, lo, hi, scale: float, color: QColor, dash: bool = False, name: str = ""):
    if sd <= 0:
        return
    xs = np.linspace(lo, hi, 240)
    pdf = np.exp(-0.5 * ((xs - mean) / sd) ** 2) / (sd * math.sqrt(2 * math.pi)) * scale
    w.plot(xs, pdf, pen=pg.mkPen(color, width=2.2, style=Qt.DashLine if dash else Qt.SolidLine), name=name or None)


def vline(w, x, color: str, label: str = "", dash: bool = True):
    w.addItem(pg.InfiniteLine(pos=x, angle=90, pen=pg.mkPen(color, width=1.6, style=Qt.DashLine if dash else Qt.SolidLine),
                              label=label, labelOpts={"position": 0.95, "color": color}))


def hline(w, y, color: str, label: str = "", dash: bool = False, width: float = 1.4):
    w.addItem(pg.InfiniteLine(pos=y, angle=0, pen=pg.mkPen(color, width=width, style=Qt.DashLine if dash else Qt.SolidLine),
                              label=label, labelOpts={"position": 0.98, "color": color, "anchors": [(1, 1), (1, 1)]}))


def edges_for(arrays: list[np.ndarray], bins: int, extra: tuple = ()) -> np.ndarray:
    vals = np.concatenate([a for a in arrays if len(a)]) if any(len(a) for a in arrays) else np.array([0.0, 1.0])
    lo, hi = float(vals.min()), float(vals.max())
    for e in extra:
        if e is not None:
            lo, hi = min(lo, e), max(hi, e)
    if hi <= lo:
        hi = lo + 1
    pad = (hi - lo) * 0.04
    n = bins or int(min(40, max(8, math.sqrt(len(vals)))))
    return np.linspace(lo - pad, hi + pad, n + 1)


def control_plot(w, chart: st.ControlChart, color: QColor, t=None):
    x = np.arange(1, len(chart.values) + 1) if t is None else t
    w.plot(x, chart.values, pen=pg.mkPen(color, width=1.5), symbol="o", symbolSize=4, symbolBrush=color,
           symbolPen=None)
    bad = np.union1d(chart.out, chart.runs).astype(int)
    if len(bad):
        w.plot(np.asarray(x)[bad], chart.values[bad], pen=None, symbol="s", symbolSize=8,
               symbolBrush=theme.c("critical"), symbolPen=None)
    hline(w, chart.center, theme.c("good_text"), f"X̄={f(chart.center)}" if chart.label in ("I", "X̄") else
          f"{chart.label}̄={f(chart.center)}")
    hline(w, chart.ucl, theme.c("critical"), f"LCS={f(chart.ucl)}", dash=True)
    if chart.lcl > -1e300 and not (chart.label in ("MR", "R") and chart.lcl == 0):
        hline(w, chart.lcl, theme.c("critical"), f"LCI={f(chart.lcl)}", dash=True)


def prob_plot(w, norm: st.Normality, color: QColor):
    w.plot(norm.x, norm.z, pen=None, symbol="o", symbolSize=5, symbolBrush=color, symbolPen=None)
    xs = np.array([norm.x.min(), norm.x.max()])
    w.plot(xs, (xs - norm.mean) / norm.sd, pen=pg.mkPen(theme.c("critical"), width=2))
    w.getAxis("left").setTicks([[(st.norm_ppf(p / 100), f"{p:g}") for p in PROB_TICKS]])
    w.setLabel("left", tr("Porcentaje"))


def boxes(w, groups: list[tuple[str, np.ndarray]], color_fn: Callable[[int, str], QColor]):
    for i, (name, y) in enumerate(groups):
        y = st.clean(y)
        if not len(y):
            continue
        q1, med, q3 = np.percentile(y, [25, 50, 75])
        iqr = q3 - q1
        lo_w = float(y[y >= q1 - 1.5 * iqr].min())
        hi_w = float(y[y <= q3 + 1.5 * iqr].max())
        col = color_fn(i, name)
        fill = QColor(col)
        fill.setAlpha(170)
        w.addItem(pg.BarGraphItem(x=[i], y0=[q1], height=[q3 - q1], width=0.55, brush=fill,
                                  pen=pg.mkPen(col.darker(150), width=1.2)))
        w.plot([i - 0.275, i + 0.275], [med, med], pen=pg.mkPen(col.darker(200), width=2.5))
        w.plot([i, i], [q3, hi_w], pen=pg.mkPen(col.darker(160), width=1.3))
        w.plot([i, i], [lo_w, q1], pen=pg.mkPen(col.darker(160), width=1.3))
        for v in (lo_w, hi_w):
            w.plot([i - 0.12, i + 0.12], [v, v], pen=pg.mkPen(col.darker(160), width=1.3))
        out = y[(y < lo_w) | (y > hi_w)]
        if len(out):
            sel = out if len(out) <= 400 else np.random.default_rng(0).choice(out, 400, replace=False)
            w.plot(np.full(len(sel), i), sel, pen=None, symbol="x", symbolSize=6, symbolPen=col.darker(150))
        w.plot([i], [float(y.mean())], pen=None, symbol="o", symbolSize=9, symbolBrush=theme.c("text2"),
               symbolPen=None)
    cat_axis(w, [g[0] for g in groups])


def series_groups(R: Render) -> list[tuple[str, np.ndarray]]:
    """(nombre, datos): cada variable, o cada grupo si hay una sola variable agrupada."""
    out = []
    for v in R.data:
        g = v.by_group()
        if len(R.data) == 1 or len(g) == 1:
            out += list(g.items()) if len(g) > 1 else [(v.label, v.y)]
        else:
            out += [(f"{v.label} · {k}", y) for k, y in g.items()]
    return out


def unit_of(R: Render) -> str:
    return R.data[0].unit if R.data else ""


def averaged_note(R: Render) -> str:
    avg = max((v.averaged_s for v in R.data), default=0)
    return tr(" · datos promediados cada {s} s por ser muchos", s=f"{avg:.0f}") if avg else ""


# --- tipos de análisis ------------------------------------------------------------------------------


def render_describe(R: Render) -> None:
    cols, heads = [], []
    for v in R.data:
        for g, y in v.by_group().items():
            heads.append(v.label if g == v.label else f"{v.label} · {g}")
            cols.append(st.describe(y))
    rows = [[tr(label)] + [c.get(key) for c in cols] for key, label in st.DESCRIBE_LABELS]
    R.table([tr("Estadístico")] + heads, rows, 0, 0, 2, tr("Estadística descriptiva"))
    if cols and cols[0].get("n"):
        c = cols[0]
        txt = tr("<b>{h}</b>: media {m}, desviación estándar {s} (CV {cv} %), de {mn} a {mx}. La mitad de los datos "
                 "está entre {q1} y {q3}.", h=heads[0], m=f(c["mean"]), s=f(c["sd"]), cv=f(c.get("cv"), 3),
                 mn=f(c["min"]), mx=f(c["max"]), q1=f(c["q1"]), q3=f(c["q3"]))
        if c.get("skew") is not None and abs(c["skew"]) > 1:
            txt += " " + tr("La distribución es asimétrica (asimetría {a}): revisa la normalidad antes de calcular "
                            "capacidad.", a=f(c["skew"], 2))
        R.text(txt + averaged_note(R), 1)


def render_histogram(R: Render) -> None:
    p = R.params
    lsl, usl = p.get("lsl"), p.get("usl")
    groups = series_groups(R)
    density = len(groups) > 1
    panel = bool(p.get("panel")) and len(groups) > 1
    edges = edges_for([g[1] for g in groups], int(p.get("bins") or 0), (lsl, usl))
    rows = []
    plots = []
    if panel:
        cols = 2 if len(groups) > 1 else 1
        for i, (name, y) in enumerate(groups):
            w = R.plot(f"hist_{i}", name, i // cols, i % cols)
            plots.append((w, [(i, name, y)]))
    else:
        title = tr("Histograma de {v}", v=", ".join(v.label for v in R.data))
        w = R.plot("hist", title, 0, 0, 1, 2, min_h=380)
        if len(groups) > 1:
            w.addLegend(offset=(-10, 10))
        plots.append((w, list((i, n, y) for i, (n, y) in enumerate(groups))))
    for w, items in plots:
        for i, name, y in items:
            y = st.clean(y)
            col = R.color(i, name)
            hist_bars(w, y, edges, col, density and not panel, alpha=110 if len(items) > 1 else 170)
            d = st.describe(y)
            if p.get("fit", True) and d.get("n", 0) > 2:
                scale = 1.0 if (density and not panel) else len(y) * (edges[1] - edges[0])
                normal_curve(w, d["mean"], d["sd"], edges[0], edges[-1], scale, col.darker(130), name=name)
            rows.append([name, d.get("mean"), d.get("sd"), d.get("n")])
        for val, lab in ((lsl, tr("LIE")), (usl, tr("LSE"))):
            if val is not None:
                vline(w, val, theme.c("critical"), f"{lab} {f(val)}")
        w.setLabel("left", tr("Densidad") if density and not panel else tr("Frecuencia"))
        w.setLabel("bottom", unit_of(R))
    n_rows = (len(groups) + 1) // 2 if panel else 1
    R.table([tr("Serie"), tr("Media"), tr("Desv. est."), "N"], rows, n_rows, 0, 2)
    if len(rows) >= 2:
        best = min(rows, key=lambda r: r[2] or math.inf)
        R.text(tr("La serie con menor variación es <b>{n}</b> (desv. est. {s}). Compara las medias y la dispersión "
                  "de cada serie; para saber si la diferencia es real usa «Comparar grupos».", n=best[0],
                  s=f(best[2])) + averaged_note(R), n_rows + 1)


def render_boxplot(R: Render) -> None:
    groups = series_groups(R)
    w = R.plot("box", tr("Gráfica de caja de {v}", v=", ".join(v.label for v in R.data)), 0, 0, 1, 2, min_h=380)
    boxes(w, groups, R.color)
    w.setLabel("left", unit_of(R))
    rows = []
    for name, y in groups:
        d = st.describe(y)
        rows.append([name, d.get("n"), d.get("q1"), d.get("median"), d.get("q3"), d.get("iqr"), d.get("mean")])
    R.table([tr("Serie"), "N", "Q1", tr("Mediana"), "Q3", tr("Rango IQ"), tr("Media")], rows, 1, 0, 2)
    if len(rows) > 1:
        wide = max(rows, key=lambda r: r[5] or 0)
        R.text(tr("La caja muestra el 50 % central de los datos y la línea, la mediana; el punto es la media y las "
                  "× son valores atípicos. Mayor dispersión: <b>{n}</b> (rango IQ {r}).", n=wide[0], r=f(wide[5]))
               + averaged_note(R), 2)


def render_timeseries(R: Render) -> None:
    w = R.plot("ts", tr("Gráfica de tiempo de {v}", v=", ".join(v.label for v in R.data)), 0, 0, 1, 2, date_axis=True,
               min_h=380)
    if len(R.data) > 1:
        w.addLegend(offset=(-10, 10))
    w.setClipToView(True)
    w.setDownsampling(auto=True, mode="peak")
    for i, v in enumerate(R.data):
        w.plot(v.t, v.y, pen=pg.mkPen(R.color(i, v.label), width=1.6), name=v.label)
    p = R.params
    for val, lab in ((p.get("lsl"), tr("LIE")), (p.get("usl"), tr("LSE"))):
        if val is not None:
            hline(w, val, theme.c("critical"), f"{lab} {f(val)}", dash=True)
    rows = [[v.label, len(v.y), float(np.mean(v.y)) if len(v.y) else None,
             float(np.min(v.y)) if len(v.y) else None, float(np.max(v.y)) if len(v.y) else None] for v in R.data]
    R.table([tr("Variable"), "N", tr("Media"), tr("Mínimo"), tr("Máximo")], rows, 1, 0, 2)
    txt = []
    for v in R.data:
        if len(v.t) > 10 and np.ptp(v.t) > 0:
            slope, _ = np.polyfit((v.t - v.t[0]) / 3600.0, v.y, 1)
            sd = float(np.std(v.y)) or 1.0
            drift = abs(slope) * np.ptp(v.t) / 3600.0
            if drift > sd:
                txt.append(tr("<b>{v}</b> tiene una tendencia {d} de {s} {u}/h en el periodo.", v=v.label,
                              d=tr("a subir") if slope > 0 else tr("a bajar"), s=f(abs(slope), 3), u=v.unit))
    R.text("<br>".join(txt) if txt else tr("Sin tendencias marcadas en el periodo: los valores se mantienen alrededor "
                                           "de su media.") + averaged_note(R), 2)


def render_bar(R: Render) -> None:
    stat = R.params.get("stat", "mean")
    fn = {"mean": np.mean, "median": np.median, "sum": np.sum, "sd": lambda y: np.std(y, ddof=1),
          "count": len, "max": np.max, "min": np.min}[stat]
    groups = [(n, st.clean(y)) for n, y in series_groups(R)]
    groups = [(n, y) for n, y in groups if len(y)]
    names = [n for n, _ in groups]
    vals = [float(fn(y)) if len(y) > (1 if stat == "sd" else 0) else 0.0 for _, y in groups]
    label = dict(BAR_STATS)[stat]
    w = R.plot("bar", tr("{s} por grupo", s=tr(label)), 0, 0, 1, 2, min_h=380)
    for i, (n, v) in enumerate(zip(names, vals)):
        w.addItem(pg.BarGraphItem(x=[i], height=[v], width=0.6, brush=pg.mkBrush(R.color(i, n)),
                                  pen=pg.mkPen(R.color(i, n).darker(140))))
        t = pg.TextItem(f(v), color=theme.c("text"), anchor=(0.5, 1))
        t.setPos(i, v)
        w.addItem(t)
    cat_axis(w, names)
    w.setLabel("left", tr(label))
    R.table([tr("Grupo"), tr(label)], [[n, v] for n, v in zip(names, vals)], 1, 0, 2)


BAR_STATS = [("mean", "Media"), ("median", "Mediana"), ("sum", "Suma"), ("count", "Conteo"),
             ("sd", "Desviación estándar"), ("max", "Máximo"), ("min", "Mínimo")]


def render_compare(R: Render) -> None:
    groups = {n: st.clean(y) for n, y in series_groups(R)}
    groups = {n: y for n, y in groups.items() if len(y) > 1}
    if len(groups) < 2:
        R.empty(tr("Se necesitan al menos dos grupos con datos: agrupa (turno, día, mes, operador…) o elige "
                   "varias variables."))
        return
    gs = st.group_stats(groups)
    w = R.plot("interval", tr("Gráfica de intervalos (media e IC 95 %)"), 0, 0, 1, 2, min_h=360)
    for i, g in enumerate(gs):
        col = R.color(i, g.name)
        w.addItem(pg.ErrorBarItem(x=np.array([i]), y=np.array([g.mean]), top=np.array([g.ci_hi - g.mean]),
                                  bottom=np.array([g.mean - g.ci_lo]), beam=0.18, pen=pg.mkPen(col, width=2)))
        w.plot([i], [g.mean], pen=None, symbol="o", symbolSize=10, symbolBrush=col, symbolPen=None)
    cat_axis(w, [g.name for g in gs])
    w.setLabel("left", unit_of(R))
    R.table([tr("Grupo"), "N", tr("Media"), tr("Desv. est."), tr("IC 95 % bajo"), tr("IC 95 % alto")],
            [[g.name, g.n, g.mean, g.sd, g.ci_lo, g.ci_hi] for g in gs], 1, 0, 2, tr("Grupos"))
    an = st.anova_oneway(groups)
    if an is None:
        return
    R.table([tr("Fuente"), "GL", "SC", "CM", "F", "p"],
            [[tr("Entre grupos"), an.df_between, an.ss_between, an.ms_between, an.f, fp(an.p)],
             [tr("Error (dentro)"), an.df_within, an.ss_within, an.ms_within, "", ""],
             [tr("Total"), an.df_between + an.df_within, an.ss_between + an.ss_within, "", "", ""]],
            2, 0, 2, tr("ANOVA de un factor"))
    txt = ""
    if len(gs) == 2:
        names = list(groups)
        tt = st.welch_t(groups[names[0]], groups[names[1]])
        if tt is not None:
            txt = tr("Prueba t (Welch): diferencia de medias {d} (IC 95 %: {a} a {b}), t = {t}, p = {p}. ",
                     d=f(tt.diff), a=f(tt.ci_lo), b=f(tt.ci_hi), t=f(tt.t, 3), p=fp(tt.p))
    best = max(gs, key=lambda g: g.mean)
    worst = min(gs, key=lambda g: g.mean)
    if an.p < 0.05:
        txt += tr("<b>Hay diferencia significativa entre los grupos</b> (p = {p} < 0.05). Media más alta: <b>{a}</b> "
                  "({ma}); más baja: <b>{b}</b> ({mb}). El factor explica el {r} % de la variación.",
                  p=fp(an.p), a=best.name, ma=f(best.mean), b=worst.name, mb=f(worst.mean), r=f(100 * an.r2, 3))
    else:
        txt += tr("<b>No hay diferencia significativa</b> entre los grupos (p = {p} ≥ 0.05): las diferencias "
                  "observadas pueden deberse al azar.", p=fp(an.p))
    R.text(txt + averaged_note(R), 3)


def render_normality(R: Render) -> None:
    v = R.data[0]
    norm = st.anderson_darling(v.y)
    if norm is None:
        R.empty(tr("Se necesitan al menos 8 datos con variación."))
        return
    w = R.plot("prob", tr("Gráfica de probabilidad normal de {v}", v=v.label), 0, 0, 1, 2, min_h=400)
    prob_plot(w, norm, R.color(0, v.label))
    w.setLabel("bottom", v.unit)
    R.table([tr("Estadístico"), tr("Valor")], [[tr("Media"), norm.mean], [tr("Desv. est."), norm.sd], ["N", norm.n],
                                               ["AD (A²)", norm.a2], [tr("Valor p"), fp(norm.p)]], 1, 0, 2)
    R.text(tr("<b>Los datos siguen una distribución normal</b> (Anderson-Darling p = {p} ≥ 0.05): los índices de "
              "capacidad Cp/Cpk son confiables.", p=fp(norm.p)) if norm.normal else
           tr("<b>Los datos no siguen una distribución normal</b> (Anderson-Darling p = {p} < 0.05). Puede haber "
              "mezcla de condiciones (turnos, recetas, arranques) o una distribución sesgada: separa por grupo o "
              "interpreta Cp/Cpk con cuidado.", p=fp(norm.p)) + averaged_note(R), 2)


def _cap_tables(R: Render, cap: st.CapabilityReport, row: int) -> None:
    R.table([tr("Datos del proceso"), ""],
            [[tr("LIE"), cap.lsl], [tr("Objetivo"), cap.target], [tr("LSE"), cap.usl], [tr("Media"), cap.mean], ["N", cap.n],
             [tr("Desv. est. (dentro)"), cap.sd_within], [tr("Desv. est. (general)"), cap.sd_overall]], row, 0)
    R.table([tr("Índice"), tr("Dentro (corto plazo)"), tr("General (largo plazo)")],
            [["Cp / Pp", cap.cp, cap.pp], ["CPL / PPL", cap.cpl, cap.ppl], ["CPU / PPU", cap.cpu, cap.ppu],
             ["Cpk / Ppk", cap.cpk, cap.ppk], ["Cpm", "", cap.cpm],
             ["PPM " + tr("observadas"), "", cap.ppm_obs], ["PPM " + tr("esperadas"), cap.ppm_within, cap.ppm_overall]],
            row, 1)


def _cap_text(cap: st.CapabilityReport) -> str:
    k = cap.cpk if cap.cpk is not None else cap.ppk
    if k is None:
        return ""
    if k >= 1.33:
        verdict = tr("<b>El proceso es capaz</b>")
    elif k >= 1.0:
        verdict = tr("<b>El proceso es apenas capaz</b> (mejorar la variación o el centrado)")
    else:
        verdict = tr("<b>El proceso no es capaz</b>")
    txt = tr("{v}: Cpk {k} · Ppk {pk}. Se esperan {ppm} PPM fuera de especificación.", v=verdict, k=grade(cap.cpk),
             pk=grade(cap.ppk), ppm=f(cap.ppm_overall, 3))
    if cap.cp is not None and cap.cpk is not None and cap.cp - cap.cpk > 0.25:
        side = tr("superior") if cap.cpu is not None and cap.cpl is not None and cap.cpu < cap.cpl else tr("inferior")
        txt += " " + tr("El proceso está <b>descentrado</b> hacia el límite {s}: centrarlo subiría el Cpk a ~{cp}.",
                        s=side, cp=f(cap.cp, 3))
    if cap.cpk is not None and cap.ppk is not None and cap.cpk - cap.ppk > 0.3:
        txt += " " + tr("La variación a largo plazo es mucho mayor que la de corto plazo (Ppk ≪ Cpk): hay "
                        "cambios entre turnos, recetas o con el tiempo.")
    return txt


def _cap_hist(R: Render, w, y, cap: st.CapabilityReport, color: QColor) -> None:
    edges = edges_for([y], int(R.params.get("bins") or 0), (cap.lsl, cap.usl, cap.target))
    hist_bars(w, y, edges, color, False, 170)
    scale = len(y) * (edges[1] - edges[0])
    normal_curve(w, cap.mean, cap.sd_overall, edges[0], edges[-1], scale, QColor(theme.c("critical")),
                 name=tr("General"))
    normal_curve(w, cap.mean, cap.sd_within, edges[0], edges[-1], scale, QColor(theme.c("text2")), dash=True,
                 name=tr("Dentro"))
    for val, lab in ((cap.lsl, tr("LIE")), (cap.target, tr("Objetivo")), (cap.usl, tr("LSE"))):
        if val is not None:
            vline(w, val, theme.c("critical") if lab != tr("Objetivo") else theme.c("good_text"), f"{lab} {f(val)}")


def _spec(R: Render):
    p = R.params
    return p.get("lsl"), p.get("usl"), p.get("target")


def render_capability(R: Render) -> None:
    v = R.data[0]
    lsl, usl, target = _spec(R)
    cap = st.capability_report(v.y, lsl, usl, target)
    if cap is None:
        R.empty(tr("Indica al menos un límite de especificación (LIE o LSE) y elige un rango con 5 datos o más."))
        return
    w = R.plot("cap", tr("Capacidad del proceso de {v}", v=v.label), 0, 0, 1, 2, min_h=380)
    w.addLegend(offset=(-10, 10))
    _cap_hist(R, w, st.clean(v.y), cap, R.color(0, v.label))
    w.setLabel("bottom", v.unit)
    _cap_tables(R, cap, 1)
    R.text(_cap_text(cap) + averaged_note(R), 2)


def render_sixpack(R: Render) -> None:
    v = R.data[0]
    y = st.clean(v.y)
    lsl, usl, target = _spec(R)
    cap = st.capability_report(y, lsl, usl, target)
    charts = st.imr_charts(y)
    if cap is None or charts is None:
        R.empty(tr("Indica al menos un límite de especificación y elige un rango con datos suficientes."))
        return
    col = R.color(0, v.label)
    ic, mc = charts
    control_plot(R.plot("i", tr("Carta I"), 0, 0, min_h=230), ic, col)
    control_plot(R.plot("mr", tr("Carta de rango móvil"), 1, 0, min_h=230), mc, col)
    w = R.plot("last", tr("Últimas 25 observaciones"), 2, 0, min_h=230)
    last = y[-25:]
    w.plot(np.arange(len(y) - len(last) + 1, len(y) + 1), last, pen=None, symbol="o", symbolSize=6, symbolBrush=col)
    w.setLabel("bottom", tr("Observación"))
    _cap_hist(R, R.plot("hist", tr("Histograma de capacidad"), 0, 1, min_h=230), y, cap, col)
    norm = st.anderson_darling(y)
    wp = R.plot("prob", tr("Gráfica de probabilidad normal") + (f"  (AD p = {fp(norm.p)})" if norm else ""), 1, 1,
                min_h=230)
    if norm is not None:
        prob_plot(wp, norm, col)
    wc = R.plot("capplot", tr("Gráfica de capacidad"), 2, 1, min_h=230)
    rows = [(tr("Dentro"), cap.mean - 3 * cap.sd_within, cap.mean + 3 * cap.sd_within, theme.c("text2")),
            (tr("General"), cap.mean - 3 * cap.sd_overall, cap.mean + 3 * cap.sd_overall, theme.c("critical")),
            (tr("Especificación"), lsl if lsl is not None else cap.mean - 3 * cap.sd_overall,
             usl if usl is not None else cap.mean + 3 * cap.sd_overall, theme.c("good_text"))]
    for i, (name, a, b, c) in enumerate(rows):
        wc.plot([a, b], [i, i], pen=pg.mkPen(c, width=4))
        wc.plot([a, b], [i, i], pen=None, symbol="|", symbolSize=16, symbolPen=pg.mkPen(c, width=2))
    wc.getAxis("left").setTicks([[(i, r[0]) for i, r in enumerate(rows)]])
    wc.getAxis("left").setWidth(100)
    wc.setYRange(-0.6, 2.6)
    txt = _cap_text(cap)
    n_out = len(np.union1d(ic.out, ic.runs))
    txt += " " + (tr("La carta I tiene <b>{n} puntos fuera de control</b>: el proceso no es estable y los índices "
                     "pueden no representar el futuro.", n=n_out) if n_out else
                  tr("Las cartas no muestran puntos fuera de control: el proceso es estable."))
    if norm is not None and not norm.normal:
        txt += " " + tr("Los datos no son normales (p = {p}).", p=fp(norm.p))
    R.text(txt + averaged_note(R), 3)


def render_control(R: Render) -> None:
    v = R.data[0]
    y = st.clean(v.y)
    kind = R.params.get("chart", "imr")
    n = int(R.params.get("subgroup") or 5)
    charts = st.xbar_r_charts(y, n) if kind == "xbar_r" else st.imr_charts(y)
    if charts is None:
        R.empty(tr("Datos insuficientes para la carta de control."))
        return
    top, bottom = charts
    col = R.color(0, v.label)
    t1 = tr("Carta X̄ (subgrupos de {n})", n=n) if kind == "xbar_r" else tr("Carta de valores individuales (I)")
    t2 = tr("Carta R") if kind == "xbar_r" else tr("Carta de rango móvil (MR)")
    control_plot(R.plot("top", f"{t1} — {v.label}", 0, 0, 1, 2, min_h=300), top, col)
    control_plot(R.plot("bottom", t2, 1, 0, 1, 2, min_h=240), bottom, col)
    n_out, n_run, n_r = len(top.out), len(top.runs), len(bottom.out)
    R.table([tr("Prueba"), tr("Puntos")], [[tr("Fuera de límites de control"), n_out],
                                          [tr("9 o más seguidos del mismo lado"), n_run],
                                          [tr("Rango fuera de límites"), n_r]], 2, 0, 2)
    R.text(tr("<b>Proceso estable</b>: ningún punto sale de los límites ni hay corridas.") if not (n_out or n_run or n_r)
           else tr("<b>Proceso fuera de control</b>: {a} puntos fuera de límites, {b} en corridas y {c} rangos "
                   "fuera. Busca causas especiales en esos momentos (cambio de receta, arranque, material).",
                   a=n_out, b=n_run, c=n_r) + averaged_note(R), 3)


def _aligned(R: Render, vids: list[str]):
    series = {v.vid: (v.t, v.y) for v in R.data if v.vid in vids and len(v.t)}
    step = float(R.params.get("step_s") or 5.0)
    t, m, names = align(series, step, max(30.0, 3 * step))
    return t, m, names


def render_matrix(R: Render) -> None:
    vids = [v.vid for v in R.data]
    t, m, names = _aligned(R, vids)
    if len(t) < 5 or len(names) < 2:
        R.empty(tr("Se necesitan al menos dos variables con datos en los mismos momentos."))
        return
    labels = {v.vid: v.label for v in R.data}
    k = len(names)
    sel = np.arange(len(t)) if len(t) <= 3000 else np.random.default_rng(0).choice(len(t), 3000, replace=False)
    grid = QWidget()
    gl = QGridLayout(grid)
    gl.setSpacing(2)
    for i in range(k):
        for j in range(k):
            w = pg.PlotWidget()
            w.setMinimumSize(150, 150)
            w.setBackground(theme.c("plot_bg"))
            w.hideButtons()
            if i == j:
                edges = edges_for([m[:, i]], 0)
                hist_bars(w, m[:, i], edges, R.color(i, labels[names[i]]), False)
                w.setTitle(labels[names[i]], size="9pt")
            else:
                w.plot(m[sel, j], m[sel, i], pen=None, symbol="o", symbolSize=3,
                       symbolBrush=R.color(0, labels[names[0]]), symbolPen=None)
            gl.addWidget(w, i, j)
    R.lay.addWidget(grid, 0, 0, 1, 2)
    corr = np.corrcoef(m.T)
    n = len(t)
    rows = []
    pairs = []
    for i in range(k):
        row = [labels[names[i]]]
        for j in range(k):
            r = float(corr[i, j])
            row.append(f"{r:+.3f}")
            if j > i:
                tt = r * math.sqrt((n - 2) / max(1e-12, 1 - r * r))
                pairs.append((abs(r), labels[names[i]], labels[names[j]], r, st.t_sf2(tt, n - 2)))
        rows.append(row)
    R.table([""] + [labels[x] for x in names], rows, 1, 0, 2, tr("Correlación de Pearson (r)"))
    pairs.sort(reverse=True)
    txt = []
    for a, x, y, r, p in pairs[:3]:
        strength = tr("fuerte") if a >= 0.7 else (tr("moderada") if a >= 0.4 else tr("débil"))
        sense = tr("directa") if r > 0 else tr("inversa")
        txt.append(tr("<b>{x}</b> y <b>{y}</b>: relación {s} {d} (r = {r}, p = {p})", x=x, y=y, s=strength, d=sense,
                      r=f"{r:+.2f}", p=fp(p)))
    R.text("<br>".join(txt) + "<br>" + tr("Correlación no es causalidad: confirma con un cambio controlado."), 2)


def render_contour(R: Render) -> None:
    p = R.params
    vx, vy, vz = p.get("x"), p.get("y"), p.get("z")
    t, m, names = _aligned(R, [vx, vy, vz])
    if len(t) < 10 or len(names) < 3:
        R.empty(tr("Se necesitan las tres variables (X, Y, Z) con datos en los mismos momentos."))
        return
    labels = {v.vid: v.label for v in R.data}
    ix, iy, iz = names.index(vx), names.index(vy), names.index(vz)
    x, y, z = m[:, ix], m[:, iy], m[:, iz]
    nb = int(p.get("grid") or 20)
    sums, xe, ye = np.histogram2d(x, y, bins=nb, weights=z)
    cnt, _, _ = np.histogram2d(x, y, bins=[xe, ye])
    with np.errstate(invalid="ignore", divide="ignore"):
        zz = sums / cnt
    w = R.plot("contour", tr("Contorno de {z} contra {x} y {y}", z=labels[vz], x=labels[vx], y=labels[vy]), 0, 0, 1, 2,
               min_h=420)
    finite = zz[np.isfinite(zz)]
    img = pg.ImageItem(zz)  # las celdas sin datos (NaN) quedan transparentes
    if len(finite):
        img.setLevels((float(finite.min()), float(finite.max())))
    cmap = colormap()
    img.setLookupTable(cmap.getLookupTable(nPts=256))
    img.setRect(pg.QtCore.QRectF(xe[0], ye[0], xe[-1] - xe[0], ye[-1] - ye[0]))
    w.addItem(img)
    if len(finite):
        for lv in np.linspace(finite.min(), finite.max(), 7)[1:-1]:
            iso = pg.IsocurveItem(data=np.nan_to_num(zz, nan=float(finite.mean())), level=float(lv),
                                  pen=pg.mkPen(theme.c("text"), width=1))
            iso.setParentItem(img)
        bar = pg.ColorBarItem(values=(float(finite.min()), float(finite.max())), colorMap=cmap, interactive=False,
                              label=labels[vz])
        bar.setImageItem(img, insert_in=w.getPlotItem())
    w.setLabel("bottom", labels[vx])
    w.setLabel("left", labels[vy])
    if len(finite):
        k = np.unravel_index(np.nanargmax(zz), zz.shape)
        k2 = np.unravel_index(np.nanargmin(zz), zz.shape)
        R.text(tr("{z} más alto ({zmax}) con {x} ≈ {xa} y {y} ≈ {ya}; más bajo ({zmin}) con {x} ≈ {xb} y {y} ≈ {yb}. "
                  "Las zonas sin color no tienen datos.", z=labels[vz], zmax=f(float(zz[k])), x=labels[vx],
                  xa=f((xe[k[0]] + xe[k[0] + 1]) / 2), y=labels[vy], ya=f((ye[k[1]] + ye[k[1] + 1]) / 2),
                  zmin=f(float(zz[k2])), xb=f((xe[k2[0]] + xe[k2[0] + 1]) / 2),
                  yb=f((ye[k2[1]] + ye[k2[1] + 1]) / 2)), 1)


class Simulator(QFrame):
    """Simulación de respuesta: se mueven los factores y se ve la respuesta predicha con sus intervalos."""

    def __init__(self, reg: st.Regression, labels: list[str], y_label: str, on_change=None):
        super().__init__()
        self.reg, self.on_change = reg, on_change
        self.setObjectName("card")
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel(f"<b style='font-size:14px; color:{theme.c('title')}'>"
                             f"{tr('Simulación de respuesta')}</b> — {y_label}"))
        form = QFormLayout()
        self.spins: list[QDoubleSpinBox] = []
        for i, name in enumerate(labels):
            lo, hi = float(reg.x_min[i]), float(reg.x_max[i])
            span = (hi - lo) or 1.0
            row = QHBoxLayout()
            sl = QSlider(Qt.Horizontal)
            sl.setRange(0, 1000)
            sp = QDoubleSpinBox()
            sp.setDecimals(4)
            sp.setRange(lo - span, hi + span)
            sp.setSingleStep(span / 100)
            sp.setValue((lo + hi) / 2)
            sl.setValue(500)
            sl.valueChanged.connect(lambda v, sp=sp, lo=lo, span=span: sp.setValue(lo + span * v / 1000))
            sp.valueChanged.connect(self._update)
            row.addWidget(sl, 1)
            row.addWidget(sp)
            form.addRow(f"{name}  ({f(lo)} … {f(hi)})", row)
            self.spins.append(sp)
        lay.addLayout(form)
        self.out = QLabel()
        self.out.setTextFormat(Qt.RichText)
        self.out.setWordWrap(True)
        lay.addWidget(self.out)
        self._update()

    def values(self) -> list[float]:
        return [s.value() for s in self.spins]

    def _update(self, *_):
        x = self.values()
        yhat, clo, chi, plo, phi = self.reg.predict(x)
        outside = any(v < lo or v > hi for v, lo, hi in zip(x, self.reg.x_min, self.reg.x_max))
        self.out.setText(
            f"<span style='font-size:26px; color:{theme.c('accent')}'><b>{f(yhat)}</b></span><br>"
            + tr("IC 95 % de la media: {a} a {b} · IP 95 % de una lectura: {c} a {d}", a=f(clo), b=f(chi), c=f(plo),
                 d=f(phi))
            + (f"<br><b style='color:{theme.c('warning_text')}'>"
               + tr("⚠ Fuera del rango de los datos: la predicción es una extrapolación.") + "</b>" if outside else ""))
        if self.on_change:
            self.on_change(x)


def render_regression(R: Render) -> None:
    p = R.params
    vy = p.get("y")
    xs = [x for x in p.get("xs", []) if x != vy]
    t, m, names = _aligned(R, [vy] + xs)
    labels = {v.vid: v.label for v in R.data}
    if vy not in names or len(names) < 2 or len(t) < 10:
        R.empty(tr("Se necesitan la respuesta (Y) y al menos un factor (X) con datos en los mismos momentos."))
        return
    iy = names.index(vy)
    xi = [names.index(x) for x in xs if x in names]
    xnames = [labels[names[i]] for i in xi]
    reg = st.ols(m[:, xi], m[:, iy], xnames, bool(p.get("quadratic")), bool(p.get("interactions")))
    if reg is None:
        R.empty(tr("No hay suficientes datos para ajustar el modelo."))
        return
    eq = f"{labels[vy]} = " + " ".join(
        (f"{c:+.4g}" if k else f"{c:.4g}") + ("" if k == 0 else f"·{reg.terms[k]}") for k, c in enumerate(reg.coef))
    R.text(f"<b>{tr('Ecuación de regresión')}</b><br><code>{eq}</code><br>"
           + tr("S = {s} · R² = {r2} % · R² ajustado = {r2a} % · F = {f} · p = {p} · N = {n}", s=f(reg.s),
                r2=f(100 * reg.r2, 3), r2a=f(100 * reg.r2_adj, 3), f=f(reg.f, 4), p=fp(reg.p_model), n=reg.n), 0)
    R.table([tr("Término"), tr("Coeficiente"), tr("Error est."), "t", "p", tr("¿Significativo?")],
            [[reg.terms[k], float(reg.coef[k]), float(reg.se[k]), float(reg.t[k]), fp(float(reg.p[k])),
              ("✔" if reg.p[k] < 0.05 else "—") if k else ""] for k in range(len(reg.terms))], 1, 0, 2,
            tr("Coeficientes"))
    col = R.color(0, labels[vy])
    if len(xi) == 1 and not reg.interactions:
        w = R.plot("fit", tr("Gráfica de línea ajustada"), 2, 0, 1, 2, min_h=340)
        x = m[:, xi[0]]
        sel = np.arange(len(x)) if len(x) <= 4000 else np.random.default_rng(0).choice(len(x), 4000, replace=False)
        w.plot(x[sel], m[sel, iy], pen=None, symbol="o", symbolSize=4, symbolBrush=col, symbolPen=None)
        xx = np.linspace(reg.x_min[0], reg.x_max[0], 80)
        pr = np.array([reg.predict([v]) for v in xx])
        w.plot(xx, pr[:, 0], pen=pg.mkPen(theme.c("critical"), width=2.5))
        for k, dash in ((1, True), (2, True), (3, False), (4, False)):
            w.plot(xx, pr[:, k], pen=pg.mkPen(theme.c("critical") if k < 3 else theme.c("text2"), width=1,
                                              style=Qt.DashLine if dash else Qt.DotLine))
        w.setLabel("bottom", xnames[0])
        w.setLabel("left", labels[vy])
        next_row = 3
    else:
        w = R.plot("obs", tr("Observado contra ajustado"), 2, 0, min_h=320)
        w.plot(reg.fitted, reg.fitted + reg.resid, pen=None, symbol="o", symbolSize=4, symbolBrush=col, symbolPen=None)
        lo, hi = float(reg.fitted.min()), float(reg.fitted.max())
        w.plot([lo, hi], [lo, hi], pen=pg.mkPen(theme.c("critical"), width=2))
        w.setLabel("bottom", tr("Ajustado"))
        w.setLabel("left", tr("Observado"))
        if len(xi) >= 2:
            _surface(R, reg, xnames, labels[vy], 2, 1)
        next_row = 3
    wr = R.plot("resid", tr("Residuos contra ajustados"), next_row, 0, min_h=260)
    wr.plot(reg.fitted, reg.resid, pen=None, symbol="o", symbolSize=4, symbolBrush=col, symbolPen=None)
    hline(wr, 0, theme.c("critical"))
    norm = st.anderson_darling(reg.resid)
    wn = R.plot("rprob", tr("Probabilidad normal de los residuos"), next_row, 1, min_h=260)
    if norm is not None:
        prob_plot(wn, norm, col)
    sim = Simulator(reg, xnames, labels[vy], on_change=R.extra.get("sim_change"))
    R.lay.addWidget(sim, next_row + 1, 0, 1, 2)
    R.simulator = sim
    sig = [reg.terms[k] for k in range(1, len(reg.terms)) if reg.p[k] < 0.05]
    txt = tr("El modelo explica el <b>{r} %</b> de la variación de {y}.", r=f(100 * reg.r2, 3), y=labels[vy])
    txt += " " + (tr("Factores significativos (p < 0.05): {s}.", s=", ".join(sig)) if sig else
                  tr("Ningún factor es significativo: el modelo no sirve para predecir."))
    if reg.r2 < 0.5:
        txt += " " + tr("R² bajo: faltan factores importantes o la relación no es de este tipo.")
    txt += " " + tr("Mueve los factores en la simulación para ver la respuesta esperada.")
    R.text(txt + averaged_note(R), next_row + 2)


def _surface(R: Render, reg: st.Regression, xnames: list[str], y_label: str, row: int, col: int) -> None:
    """Superficie de respuesta predicha de los dos primeros factores (los demás en su punto medio)."""
    w = R.plot("surface", tr("Superficie de respuesta: {y}", y=y_label), row, col, min_h=320)
    n = 40
    a = np.linspace(reg.x_min[0], reg.x_max[0], n)
    b = np.linspace(reg.x_min[1], reg.x_max[1], n)
    mid = (reg.x_min + reg.x_max) / 2
    zz = np.empty((n, n))
    for i, va in enumerate(a):
        for j, vb in enumerate(b):
            x = mid.copy()
            x[0], x[1] = va, vb
            zz[i, j] = float(reg.row(x) @ reg.coef)
    img = pg.ImageItem(zz)
    cmap = colormap()
    img.setLookupTable(cmap.getLookupTable(nPts=256))
    img.setRect(pg.QtCore.QRectF(a[0], b[0], a[-1] - a[0] or 1, b[-1] - b[0] or 1))
    w.addItem(img)
    for lv in np.linspace(zz.min(), zz.max(), 8)[1:-1]:
        iso = pg.IsocurveItem(data=zz, level=float(lv), pen=pg.mkPen("#ffffff", width=1))
        iso.setParentItem(img)
    w.setLabel("bottom", xnames[0])
    w.setLabel("left", xnames[1])


def render_pareto(R: Render) -> None:
    recs = R.extra.get("problems", [])
    by = R.params.get("by", "reason")
    measure = R.params.get("measure", "minutes")
    vals: dict[str, float] = {}
    for r in recs:
        key = str(r.get(by) or tr("(sin dato)"))
        v = {"minutes": (r.get("duration_s") or 0) / 60, "count": 1, "scrap": r.get("scrap") or 0}[measure]
        vals[key] = vals.get(key, 0.0) + float(v)
    names, values, cum = st.pareto(vals)
    if not names:
        R.empty(tr("No hay capturas en el rango elegido."))
        return
    mlabel = dict(PARETO_MEASURES)[measure]
    w = R.plot("pareto", tr("Pareto de {k} por {b}", k=tr(dict(PARETO_SOURCES)[R.params.get("source", "downtime")]).lower(),
                            b=tr(dict(PARETO_BY)[by]).lower()), 0, 0, 1, 2, min_h=400)
    for i, (n, v) in enumerate(zip(names, values)):
        w.addItem(pg.BarGraphItem(x=[i], height=[v], width=0.7, brush=pg.mkBrush(R.color(0, tr("Barras"))),
                                  pen=pg.mkPen(R.color(0, tr("Barras")).darker(140))))
    cat_axis(w, names)
    w.setLabel("left", tr(mlabel))
    # % acumulado en el eje derecho
    vb2 = pg.ViewBox()
    vb2.setZValue(100)  # la línea acumulada encima de las barras
    pi = w.getPlotItem()
    pi.showAxis("right")
    pi.scene().addItem(vb2)
    pi.getAxis("right").linkToView(vb2)
    vb2.setXLink(pi)
    vb2.setYRange(0, 105)
    pi.getAxis("right").setLabel(tr("% acumulado"))
    line_col = R.color(1, tr("% acumulado"))
    vb2.addItem(pg.PlotCurveItem(np.arange(len(cum)), cum, pen=pg.mkPen(line_col, width=2.5)))
    vb2.addItem(pg.ScatterPlotItem(np.arange(len(cum)), cum, size=7, brush=line_col, pen=None))

    def sync():
        vb2.setGeometry(pi.vb.sceneBoundingRect())
        vb2.linkedViewChanged(pi.vb, vb2.XAxis)
    pi.vb.sigResized.connect(sync)
    sync()
    R._keep = vb2
    total = float(values.sum())
    R.table([tr("Categoría"), tr(mlabel), "%", tr("% acumulado")],
            [[n, float(v), f"{100 * v / total:.1f}", f"{c:.1f}"] for n, v, c in zip(names, values, cum)], 1, 0, 2)
    k80 = int(np.searchsorted(cum, 80) + 1)
    R.text(tr("<b>{k} de {n}</b> categorías concentran el 80 % ({top}). Atacar primero «{first}» ({pct} % del "
              "total) es lo que más reduce {m}.", k=min(k80, len(names)), n=len(names),
              top=", ".join(names[:min(k80, len(names))]), first=names[0], pct=f"{100 * values[0] / total:.0f}",
              m=tr(mlabel).lower()), 2)


PARETO_SOURCES = [("downtime", "Paros"), ("quality", "Defectos de calidad")]
PARETO_BY = [("reason", "Causa / defecto"), ("category", "Categoría"), ("operator", "Operador"), ("shift", "Turno"),
             ("day", "Día"), ("month", "Mes"), ("recipe", "Receta"), ("line", "Línea")]
PARETO_MEASURES = [("minutes", "Minutos"), ("count", "Número de capturas"), ("scrap", "Desperdicio")]

RENDERERS = {
    "describe": render_describe, "histogram": render_histogram, "boxplot": render_boxplot,
    "timeseries": render_timeseries, "bar": render_bar, "compare": render_compare, "normality": render_normality,
    "capability": render_capability, "sixpack": render_sixpack, "control": render_control,
    "matrix": render_matrix, "contour": render_contour, "regression": render_regression, "pareto": render_pareto,
}
