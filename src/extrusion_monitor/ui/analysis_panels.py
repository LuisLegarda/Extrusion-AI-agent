"""Paneles de análisis de la ventana principal: estadística, correlación y comportamiento."""
from __future__ import annotations

import time
from typing import Optional

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QSplitter, QTableWidget, QVBoxLayout,
    QWidget,
)

from ..analysis.statistics import align, capability, correlation, linear_fit, xbar_chart
from ..engine import MonitorEngine, Snapshot
from .behavior_dialog import fill_corr_table

LINE = "#4fc3f7"
WARN = "#f9a825"
ALARM = "#e53935"


def _time_axis() -> dict:
    return {"bottom": pg.DateAxisItem()}


def _hline(plot, value, color, style=Qt.SolidLine, width=1.5, label: str = ""):
    ln = pg.InfiniteLine(pos=value, angle=0, pen=pg.mkPen(color, width=width, style=style),
                         label=label, labelOpts={"position": 0.02, "color": color, "anchors": [(0, 1), (0, 1)]})
    plot.addItem(ln)
    return ln


class StatsPanel(QWidget):
    """Histograma con límites y curva normal, índices de capacidad y carta X̄."""

    def __init__(self, engine: MonitorEngine):
        super().__init__()
        self.engine = engine
        lay = QVBoxLayout(self)
        row = QHBoxLayout()
        row.addWidget(QLabel("Variable:"))
        self.cmb = QComboBox()
        self.cmb.currentIndexChanged.connect(lambda _: self.refresh(self.engine.last))
        row.addWidget(self.cmb, 1)
        lay.addLayout(row)
        self.lbl = QLabel()
        self.lbl.setWordWrap(True)
        self.lbl.setTextFormat(Qt.RichText)
        lay.addWidget(self.lbl)
        split = QSplitter(Qt.Vertical)
        self.hist = pg.PlotWidget(title="Distribución (ventana de tendencia)")
        self.hist.showGrid(x=True, y=True, alpha=0.2)
        self.ctrl = pg.PlotWidget(title="Carta de control X̄ (medias por subgrupo)", axisItems=_time_axis())
        self.ctrl.showGrid(x=True, y=True, alpha=0.2)
        split.addWidget(self.hist)
        split.addWidget(self.ctrl)
        lay.addWidget(split, 1)

    def set_variables(self, config) -> None:
        cur = self.cmb.currentData()
        self.cmb.blockSignals(True)
        self.cmb.clear()
        for v in config.variables:
            if v.kind == "actual":
                self.cmb.addItem(config.var_label(v) + (f" [{v.unit}]" if v.unit else ""), v.id)
        self.cmb.setCurrentIndex(max(0, self.cmb.findData(cur)))
        self.cmb.blockSignals(False)

    def refresh(self, snap: Optional[Snapshot]) -> None:
        vid = self.cmb.currentData()
        self.hist.clear()
        self.ctrl.clear()
        if not vid or snap is None:
            return
        t, y = self.engine.series(vid)
        st = snap.statuses.get(vid)
        if len(y) < 5 or st is None:
            self.lbl.setText("Datos insuficientes: se necesitan al menos 5 lecturas en la ventana de tendencia.")
            return
        lsl = usl = None
        if st.reference is not None and st.alarm_band is not None:
            lsl, usl = st.reference - st.alarm_band, st.reference + st.alarm_band
        cap = capability(y, lsl, usl)
        # Histograma
        bins = min(30, max(8, int(np.sqrt(len(y)))))
        lo, hi = float(y.min()), float(y.max())
        if lsl is not None:
            lo, hi = min(lo, lsl), max(hi, usl)
        if hi <= lo:
            hi = lo + 1
        counts, edges = np.histogram(y, bins=bins, range=(lo - (hi - lo) * 0.05, hi + (hi - lo) * 0.05))
        width = edges[1] - edges[0]
        self.hist.addItem(pg.BarGraphItem(x=edges[:-1] + width / 2, height=counts, width=width * 0.9,
                                          brush=pg.mkBrush(79, 195, 247, 160)))
        if cap.std_overall > 0:
            xs = np.linspace(edges[0], edges[-1], 200)
            pdf = np.exp(-0.5 * ((xs - cap.mean) / cap.std_overall) ** 2) / (cap.std_overall * np.sqrt(2 * np.pi))
            self.hist.plot(xs, pdf * len(y) * width, pen=pg.mkPen("#ffffff", width=2))
        for val, color, name in ((lsl, ALARM, "LIE"), (usl, ALARM, "LSE"), (st.reference, "#9e9e9e", "objetivo"),
                                 (cap.mean, LINE, "media")):
            if val is not None:
                ln = pg.InfiniteLine(pos=val, angle=90, pen=pg.mkPen(color, width=2,
                                                                     style=Qt.DashLine if name == "media" else
                                                                     Qt.SolidLine),
                                     label=name, labelOpts={"position": 0.8 if name == "media" else 0.95,
                                                            "color": color})
                self.hist.addItem(ln)
        # Carta X̄
        sub = self.engine.config.general.spc_subgroup_s
        xb = xbar_chart(t, y, sub)
        if xb is not None:
            self.ctrl.plot(xb.t, xb.means, pen=pg.mkPen(LINE, width=2), symbol="o", symbolSize=5,
                           symbolBrush=LINE)
            if len(xb.out):
                self.ctrl.plot(xb.t[xb.out], xb.means[xb.out], pen=None, symbol="o", symbolSize=9,
                               symbolBrush=ALARM)
            _hline(self.ctrl, xb.center, "#9e9e9e", Qt.DashLine, label="LC")
            _hline(self.ctrl, xb.ucl, WARN, label="LCS")
            _hline(self.ctrl, xb.lcl, WARN, label="LCI")
            if lsl is not None:
                _hline(self.ctrl, lsl, ALARM, width=1)
                _hline(self.ctrl, usl, ALARM, width=1)

        def f(v, d=3):
            return "—" if v is None else f"{v:.{d}g}"

        def grade(v):
            if v is None:
                return "—"
            color = "#2e7d32" if v >= 1.33 else (WARN if v >= 1.0 else ALARM)
            return f"<b style='color:{color}'>{v:.2f}</b>"

        trend = st.trend
        slope = f"{trend.slope_per_min:+.3g}/min" + (" (significativa)" if trend.slope_significant else "") \
            if trend else "—"
        eta = f"{trend.eta_to_alarm_min:.1f} min" if trend and trend.eta_to_alarm_min is not None else "—"
        self.lbl.setText(
            f"n = {cap.n} · media = {f(cap.mean, 5)} · σ total = {f(cap.std_overall)} · σ corto plazo = "
            f"{f(cap.std_within)} · mín/máx = {f(cap.minimum, 5)} / {f(cap.maximum, 5)}<br>"
            f"Cp = {grade(cap.cp)} · Cpk = {grade(cap.cpk)} · Pp = {grade(cap.pp)} · Ppk = {grade(cap.ppk)} · "
            f"fuera de límites estimado = {f(cap.pct_out, 2)} %<br>"
            f"Tendencia = {slope} · tiempo estimado al límite = {eta} · "
            f"reglas SPC: {', '.join(trend.nelson) if trend and trend.nelson else 'ninguna'}"
            + ("" if lsl is not None else "<br><i>Sin límites de alarma en la receta: no se calcula Cp/Cpk.</i>"))


class CorrelationPanel(QWidget):
    """Matriz de correlación en la ventana de tendencia y dispersión entre dos variables."""

    def __init__(self, engine: MonitorEngine):
        super().__init__()
        self.engine = engine
        lay = QHBoxLayout(self)
        left = QVBoxLayout()
        left.addWidget(QLabel("Variables a comparar"))
        self.lst = QListWidget()
        self.lst.itemChanged.connect(lambda _: self.refresh(self.engine.last))
        left.addWidget(self.lst)
        lay.addLayout(left, 1)
        right = QVBoxLayout()
        self.tbl = QTableWidget()
        self.tbl.setEditTriggers(QTableWidget.NoEditTriggers)
        self.tbl.setMaximumHeight(220)
        right.addWidget(self.tbl)
        row = QHBoxLayout()
        row.addWidget(QLabel("X:"))
        self.cmb_x = QComboBox()
        row.addWidget(self.cmb_x, 1)
        row.addWidget(QLabel("Y:"))
        self.cmb_y = QComboBox()
        row.addWidget(self.cmb_y, 1)
        for c in (self.cmb_x, self.cmb_y):
            c.currentIndexChanged.connect(lambda _: self.refresh(self.engine.last))
        right.addLayout(row)
        self.lbl = QLabel()
        right.addWidget(self.lbl)
        self.scatter = pg.PlotWidget(title="Dispersión")
        self.scatter.showGrid(x=True, y=True, alpha=0.2)
        right.addWidget(self.scatter, 1)
        lay.addLayout(right, 3)

    def set_variables(self, config, checked: list[str]) -> None:
        self.config = config
        self.lst.blockSignals(True)
        self.lst.clear()
        for v in config.variables:
            if v.numeric:
                it = QListWidgetItem(config.var_label(v))
                it.setData(Qt.UserRole, v.id)
                it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
                it.setCheckState(Qt.Checked if v.id in checked else Qt.Unchecked)
                self.lst.addItem(it)
        self.lst.blockSignals(False)
        self._fill_combos()

    def _checked(self) -> list[str]:
        return [self.lst.item(i).data(Qt.UserRole) for i in range(self.lst.count())
                if self.lst.item(i).checkState() == Qt.Checked]

    def _fill_combos(self) -> None:
        ids = self._checked()
        for c, default in ((self.cmb_x, 0), (self.cmb_y, 1)):
            cur = c.currentData()
            c.blockSignals(True)
            c.clear()
            for vid in ids:
                c.addItem(self.config.var_label(self.config.variable(vid)), vid)
            idx = c.findData(cur)
            c.setCurrentIndex(idx if idx >= 0 else min(default, len(ids) - 1))
            c.blockSignals(False)

    def refresh(self, snap: Optional[Snapshot]) -> None:
        if not hasattr(self, "config"):
            return
        if self.cmb_x.count() != len(self._checked()):
            self._fill_combos()
        ids = self._checked()
        self.scatter.clear()
        if len(ids) < 2:
            self.lbl.setText("Marca al menos 2 variables.")
            self.tbl.setRowCount(0)
            return
        series = {vid: self.engine.series(vid) for vid in ids}
        g = self.engine.config.general
        gap = max(self.engine.rules.stale_limit(self.config.variable(v)) for v in ids)
        _, m, names = align(series, max(g.sample_interval_s, 2.0), gap)
        if m.shape[0] < 5:
            self.lbl.setText("Datos insuficientes en la ventana de tendencia.")
            return
        fill_corr_table(self.tbl, [self.config.var_label(self.config.variable(v)) for v in names], correlation(m))
        vx, vy = self.cmb_x.currentData(), self.cmb_y.currentData()
        if vx in names and vy in names and vx != vy:
            x, y = m[:, names.index(vx)], m[:, names.index(vy)]
            self.scatter.plot(x, y, pen=None, symbol="o", symbolSize=5, symbolBrush=pg.mkBrush(79, 195, 247, 150))
            fit = linear_fit(x, y)
            if fit:
                b, a, r2 = fit
                xs = np.array([x.min(), x.max()])
                self.scatter.plot(xs, a + b * xs, pen=pg.mkPen(WARN, width=2))
                self.lbl.setText(f"Y = {a:.4g} + {b:.4g}·X · R² = {r2:.2f} · n = {len(x)}")
            self.scatter.setLabel("bottom", self.cmb_x.currentText().split(" › ")[-1])
            self.scatter.setLabel("left", self.cmb_y.currentText().split(" › ")[-1])


class BehaviorPanel(QWidget):
    """Distancia al comportamiento aprendido (D²) en el tiempo y contribución de cada variable."""

    def __init__(self, engine: MonitorEngine):
        super().__init__()
        self.engine = engine
        lay = QVBoxLayout(self)
        row = QHBoxLayout()
        row.addWidget(QLabel("Modelo:"))
        self.cmb = QComboBox()
        self.cmb.currentIndexChanged.connect(lambda _: self.refresh(self.engine.last))
        row.addWidget(self.cmb, 1)
        lay.addLayout(row)
        self.lbl = QLabel()
        self.lbl.setWordWrap(True)
        lay.addWidget(self.lbl)
        split = QSplitter(Qt.Vertical)
        self.plot = pg.PlotWidget(title="Desviación respecto a lo normal (D² / umbral)", axisItems=_time_axis())
        self.plot.showGrid(x=True, y=True, alpha=0.2)
        self.bars = pg.PlotWidget(title="Contribución por variable (%)")
        split.addWidget(self.plot)
        split.addWidget(self.bars)
        lay.addWidget(split, 1)

    def set_models(self) -> None:
        cur = self.cmb.currentData()
        self.cmb.blockSignals(True)
        self.cmb.clear()
        for m in self.engine.behaviors.store.models:
            self.cmb.addItem(m.name + ("" if m.enabled else " (inactivo)"), m.id)
        self.cmb.setCurrentIndex(max(0, self.cmb.findData(cur)))
        self.cmb.blockSignals(False)

    def refresh(self, snap: Optional[Snapshot]) -> None:
        if self.cmb.count() != len(self.engine.behaviors.store.models):
            self.set_models()
        mid = self.cmb.currentData()
        self.plot.clear()
        self.bars.clear()
        if not mid:
            self.lbl.setText("No hay modelos. Crea uno en ⚙ Configurar variables → «Entrenar comportamiento…» "
                             "o con el botón 🧠 Comportamiento.")
            return
        model = self.engine.behaviors.store.get(mid)
        hist = list(self.engine.behaviors.history.get(mid, []))
        cfg = self.engine.config
        if hist:
            t = np.array([h[0] for h in hist])
            ratio = np.array([h[1] / h[2] if h[2] > 0 else 0 for h in hist])
            self.plot.plot(t, ratio, pen=pg.mkPen(LINE, width=2))
            _hline(self.plot, 1.0, WARN, label="umbral")
            _hline(self.plot, 2.0, ALARM, label="alarma")
        res = self.engine.behaviors.last.get(mid)
        if res is None:
            reason = "inactivo" if model and not model.enabled else (
                "no aplica a la receta activa" if model and model.recipe and model.recipe != self.engine.state.recipe
                else "esperando datos vigentes de todas sus variables")
            self.lbl.setText(f"Sin evaluación: {reason}.")
            return
        labels = [cfg.var_label(cfg.variable(v)).split(" › ")[-1] if cfg.variable(v) else v
                  for v in res.contributions]
        vals = list(res.contributions.values())
        colors = [pg.mkBrush(ALARM) if abs(res.z[v]) > model.z_limit * model.sensitivity else pg.mkBrush(LINE)
                  for v in res.contributions]
        self.bars.addItem(pg.BarGraphItem(x=np.arange(len(vals)), height=vals, width=0.6, brushes=colors))
        self.bars.getAxis("bottom").setTicks([list(enumerate(labels))])
        state = "NORMAL" if res.ratio <= 1 else ("ANORMAL" if res.ratio <= 2 else "MUY ANORMAL")
        color = "#2e7d32" if res.ratio <= 1 else (WARN if res.ratio <= 2 else ALARM)
        zs = ", ".join(f"{lb} z={res.z[v]:+.1f}" for lb, v in zip(labels, res.contributions))
        def lab(v):
            return cfg.var_label(cfg.variable(v)).split(" › ")[-1] if cfg.variable(v) else v

        broken = "; ".join(f"{lab(a)} ↔ {lab(b)} ({r:+.1f}σ)" for a, b, r in res.broken_pairs) or "ninguna"
        self.lbl.setText(
            f"<b style='color:{color}'>{state}</b> · D²/umbral = {res.ratio:.2f} · "
            f"{time.strftime('%H:%M:%S', time.localtime(res.ts))}<br>{zs}<br>Relaciones rotas: {broken}")
