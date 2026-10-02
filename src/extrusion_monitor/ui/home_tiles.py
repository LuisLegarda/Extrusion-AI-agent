"""Mosaicos de variable del tablero de Inicio: valor actual, gauge, barra, tendencia e histograma."""
from __future__ import annotations

import math
from typing import Optional

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QFrame, QLabel, QSizePolicy, QVBoxLayout, QWidget

from ..analysis.rules import Level, VarStatus, fmt
from ..analysis.kpis import KPIS, kpi_var
from ..analysis.oee import shift_start
from ..analysis.statistics import capability
from ..config import NUMERIC_CHARTS, TEXT_CHARTS, AppConfig, HomeTile, Variable
from ..engine import Snapshot
from ..i18n import tr, translate_text
from ..recipes import Bounds
from . import theme
from .common import SeriesCache, level_color, level_text, y_range
from .kpi_dashboard import Sparkline

CHART_LABELS = {"value": "Valor actual", "gauge": "Gauge", "bar": "Barra con límites", "trend": "Tendencia",
                "histogram": "Histograma (distribución)"}


def charts_for(var: Optional[Variable]) -> tuple[str, ...]:
    """Gráficos que aplican al tipo de variable."""
    if var is None or var.numeric:
        return NUMERIC_CHARTS
    return TEXT_CHARTS


def zone(v: float, b: Bounds) -> str:
    """Zona del valor según los límites: «critical», «warning», «good» o «neutral» (sin límites)."""
    if (b.al is not None and v < b.al) or (b.ah is not None and v > b.ah):
        return "critical"
    if (b.wl is not None and v < b.wl) or (b.wh is not None and v > b.wh):
        return "warning"
    return "good" if b.any else "neutral"


def auto_scale(bounds: Bounds, reference: Optional[float], values, var: Optional[Variable] = None,
               fixed: tuple[Optional[float], Optional[float]] = (None, None)) -> tuple[float, float]:
    """Escala del gauge o de la barra: límites de la variable con margen, más los datos recientes."""
    lims = [v for v in (bounds.al, bounds.wl, bounds.wh, bounds.ah, reference) if v is not None]
    data = [float(v) for v in np.asarray(values, float).ravel() if np.isfinite(v)] if values is not None else []
    pts = lims + data
    if not pts and var is not None:
        pts = [v for v in (var.valid_min, var.valid_max) if v is not None]
    if not pts:
        lo, hi = 0.0, 100.0
    else:
        lo, hi = min(pts), max(pts)
        span = hi - lo
        # Margen: la mitad de la banda de límites a cada lado (las zonas rojas quedan visibles).
        pad = span * 0.5 if lims and span > 0 else (span * 0.15 if span > 0 else max(abs(hi) * 0.1, 1.0))
        lo, hi = lo - pad, hi + pad
        if var is not None:  # sin salir del rango válido (p. ej. no mostrar negativos en un %)
            if var.valid_min is not None and min(pts) >= var.valid_min:
                lo = max(lo, var.valid_min)
            if var.valid_max is not None and max(pts) <= var.valid_max:
                hi = min(hi, var.valid_max)
    if fixed[0] is not None:
        lo = fixed[0]
    if fixed[1] is not None:
        hi = fixed[1]
    if hi <= lo:
        hi = lo + 1.0
    return lo, hi


def zone_segments(lo: float, hi: float, bounds: Bounds) -> list[tuple[float, float, str]]:
    """Tramos [a, b] de la escala con su zona de color."""
    cuts = sorted({lo, hi} | {v for v in bounds if v is not None and lo < v < hi})
    return [(a, b, zone((a + b) / 2, bounds)) for a, b in zip(cuts, cuts[1:])]


def tile_title(tile: HomeTile, config: AppConfig) -> str:
    if tile.title:
        return tile.title
    names = []
    for vid in tile.var_ids:
        v = config.variable(vid)
        if v is not None:
            names.append(v.name + (f" ({v.unit})" if v.unit and tile.chart != "trend" else ""))
    return " · ".join(names) or tr("Variable")


class TileFrame(QFrame):
    """Tarjeta del tablero con título; un clic lleva a la vista detallada."""

    clicked = Signal(str)

    def __init__(self, title: str, target: str = "", tooltip: str = ""):
        super().__init__()
        self.target = target
        self.setObjectName("card")
        if target:
            self.setCursor(Qt.PointingHandCursor)
        if tooltip:
            self.setToolTip(tooltip)
        self.lay = QVBoxLayout(self)
        self.lay.setContentsMargins(10, 8, 10, 8)
        self.lay.setSpacing(4)
        self.lbl_title = QLabel(f"<span style='font-size:14px; color:{theme.c('title')}'><b>{title}</b></span>")
        self.lbl_title.setAlignment(Qt.AlignCenter)
        self.lay.addWidget(self.lbl_title)

    def mousePressEvent(self, event) -> None:
        if self.target:
            self.clicked.emit(self.target)
        super().mousePressEvent(event)


class ProcessGauge(QWidget):
    """Gauge de una variable de proceso: zonas de color según sus límites, aguja y marca de referencia."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.value: Optional[float] = None
        self.lo, self.hi = 0.0, 100.0
        self.bounds = Bounds()
        self.reference: Optional[float] = None
        self.text = "—"
        self.unit = ""
        self.color_key = "neutral"
        self.setMinimumSize(130, 105)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    def set_data(self, value, lo, hi, bounds, reference, text, unit, color_key) -> None:
        self.value, self.lo, self.hi, self.bounds, self.reference = value, lo, hi, bounds, reference
        self.text, self.unit, self.color_key = text, unit, color_key
        self.update()

    def _frac(self, v: float) -> float:
        return (min(max(v, self.lo), self.hi) - self.lo) / ((self.hi - self.lo) or 1.0)

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        side = min(w, h * 1.15) - 16
        rect = QRectF((w - side) / 2, 8, side, side)
        thick = max(8.0, side * 0.09)
        start, span = 225.0, -270.0
        inner = rect.adjusted(thick, thick, -thick, -thick)

        def arc(a: float, b: float, color: QColor, width: float) -> None:
            pen = QPen(color, width)
            pen.setCapStyle(Qt.FlatCap)
            p.setPen(pen)
            p.drawArc(inner, int((start + span * a) * 16), int(span * (b - a) * 16))

        arc(0, 1, QColor(theme.c("track")), thick)
        for a, b, key in zone_segments(self.lo, self.hi, self.bounds):
            if key != "neutral":
                arc(self._frac(a), self._frac(b), QColor(theme.c(key)), thick)
        c = inner.center()
        r_out = inner.width() / 2
        if self.reference is not None:  # marca de referencia (consigna o nominal)
            ang = math.radians(start + span * self._frac(self.reference))
            p.setPen(QPen(QColor(theme.c("setpoint")), 3))
            p.drawLine(QPointF(c.x() + (r_out - thick) * math.cos(ang), c.y() - (r_out - thick) * math.sin(ang)),
                       QPointF(c.x() + (r_out + thick * 0.8) * math.cos(ang),
                               c.y() - (r_out + thick * 0.8) * math.sin(ang)))
        if self.value is not None:
            ang = math.radians(start + span * self._frac(self.value))
            r = r_out - thick * 0.9
            p.setPen(QPen(QColor(theme.c("text")), 3))
            p.drawLine(c, QPointF(c.x() + r * math.cos(ang), c.y() - r * math.sin(ang)))
            p.setBrush(QColor(theme.c("text")))
            p.drawEllipse(c, 4, 4)
        f = QFont(self.font())
        f.setPointSizeF(max(10.0, side * 0.11))
        f.setBold(True)
        p.setFont(f)
        p.setPen(QColor(theme.c(self.color_key if self.color_key != "neutral" else "text")))
        p.drawText(rect.adjusted(0, side * 0.42, 0, 0), Qt.AlignHCenter | Qt.AlignTop, self.text)
        if side < 84:  # muy pequeño (dock chico): solo el arco, la aguja y el valor
            p.end()
            return
        f.setPointSizeF(max(7.5, side * 0.055))
        f.setBold(False)
        p.setFont(f)
        p.setPen(QColor(theme.c("muted")))
        p.drawText(rect.adjusted(0, side * 0.58, 0, 0), Qt.AlignHCenter | Qt.AlignTop, self.unit)
        # extremos de la escala, junto al final del arco por dentro
        for frac, align in ((0.0, Qt.AlignLeft), (1.0, Qt.AlignRight)):
            v = self.lo if frac == 0 else self.hi
            ang = math.radians(start + span * frac)
            x = c.x() + (r_out - thick) * math.cos(ang)
            y = c.y() - (r_out - thick) * math.sin(ang) - 6
            box = QRectF(x - 60 if align == Qt.AlignRight else x, y, 60, 16)
            p.drawText(box, align | Qt.AlignTop, f"{v:.4g}")
        p.end()


class LinearBar(QWidget):
    """Barra horizontal con zonas de límites, marca del valor y de la referencia."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.value: Optional[float] = None
        self.lo, self.hi = 0.0, 100.0
        self.bounds = Bounds()
        self.reference: Optional[float] = None
        self.color_key = "neutral"
        self.setMinimumHeight(46)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

    def set_data(self, value, lo, hi, bounds, reference, color_key) -> None:
        self.value, self.lo, self.hi, self.bounds, self.reference = value, lo, hi, bounds, reference
        self.color_key = color_key
        self.update()

    def _x(self, v: float, x0: float, width: float) -> float:
        return x0 + width * (min(max(v, self.lo), self.hi) - self.lo) / ((self.hi - self.lo) or 1.0)

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        x0, width = 6.0, self.width() - 12.0
        y, bh = 6.0, max(14.0, min(26.0, self.height() * 0.4))
        p.fillRect(QRectF(x0, y, width, bh), QColor(theme.c("track")))
        for a, b, key in zone_segments(self.lo, self.hi, self.bounds):
            if key != "neutral":
                col = QColor(theme.c(key))
                col.setAlpha(110)
                xa, xb = self._x(a, x0, width), self._x(b, x0, width)
                p.fillRect(QRectF(xa, y + bh * 0.62, xb - xa, bh * 0.38), col)
        if self.value is not None:
            xv = self._x(self.value, x0, width)
            p.fillRect(QRectF(x0, y, xv - x0, bh * 0.6), QColor(theme.c(
                self.color_key if self.color_key != "neutral" else "measure")))
            p.setPen(QPen(QColor(theme.c("text")), 2))
            p.drawLine(QPointF(xv, y - 3), QPointF(xv, y + bh + 3))
        if self.reference is not None:
            xr = self._x(self.reference, x0, width)
            p.setPen(QPen(QColor(theme.c("setpoint")), 2, Qt.DashLine))
            p.drawLine(QPointF(xr, y - 4), QPointF(xr, y + bh + 4))
        f = QFont(self.font())
        f.setPointSizeF(8)
        p.setFont(f)
        p.setPen(QColor(theme.c("muted")))
        ty = y + bh + 4
        p.drawText(QRectF(x0, ty, 80, 14), Qt.AlignLeft | Qt.AlignTop, f"{self.lo:.4g}")
        p.drawText(QRectF(x0 + width - 80, ty, 80, 14), Qt.AlignRight | Qt.AlignTop, f"{self.hi:.4g}")
        p.end()


def period_s(range_s: float, config: AppConfig, now: Optional[float] = None) -> float:
    """Segundos mostrados: `range_s`, o desde el inicio del turno si es 0."""
    if range_s > 0:
        return range_s
    import time as _time
    now = now or _time.time()
    return max(60.0, now - shift_start(now, config.oee.shift_starts))


class VarTile(TileFrame):
    """Mosaico de una o varias variables con el gráfico elegido."""

    def __init__(self, tile: HomeTile, config: AppConfig, series: SeriesCache):
        super().__init__(tile_title(tile, config), target="trends" if tile.chart == "trend" else "variables",
                         tooltip=tr("{chart}\n(clic para ver el detalle)", chart=tr(CHART_LABELS[tile.chart])))
        self.tile = tile
        self.config = config
        self.series = series
        self.vars = [v for v in (config.variable(vid) for vid in tile.var_ids) if v is not None]
        chart = tile.chart if self.vars and tile.chart in charts_for(self.vars[0]) else "value"
        self.chart = chart
        self.lbl_value = self.lbl_info = self.spark = self.gauge = self.bar = self.plot = None
        if not self.vars:
            msg = QLabel(tr("Elige una variable (✎ Personalizar)") if not tile.var_ids else
                         tr("La variable ya no existe"))
            msg.setAlignment(Qt.AlignCenter)
            msg.setStyleSheet(f"color:{theme.c('muted')};")
            self.lay.addWidget(msg, 1)
            return
        if chart in ("value", "bar"):
            self.lbl_value = QLabel("—")
            self.lbl_value.setAlignment(Qt.AlignCenter)
            self.lbl_value.setTextFormat(Qt.RichText)
            self.lay.addWidget(self.lbl_value, 1)
            if chart == "bar":
                self.bar = LinearBar()
                self.lay.addWidget(self.bar)
            elif self.vars[0].numeric:
                self.spark = Sparkline()
                self.spark.setMinimumHeight(28)
                self.lay.addWidget(self.spark)
        elif chart == "gauge":
            self.gauge = ProcessGauge()
            self.gauge.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Ignored)
            self.lay.addWidget(self.gauge, 1)
        else:
            axis = {"bottom": pg.DateAxisItem()} if chart == "trend" else {}
            self.plot = pg.PlotWidget(axisItems=axis)
            self.plot.setMinimumHeight(110)
            # Sin tamaño preferido: la gráfica ocupa lo que le da la cuadrícula (no estira las filas).
            self.plot.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)
            self.plot.showGrid(x=True, y=True, alpha=0.25)
            self.plot.setMouseEnabled(x=False, y=False)
            self.plot.hideButtons()
            self.plot.setMenuEnabled(False)
            if chart == "trend":
                self.plot.setClipToView(True)
                self.plot.setDownsampling(auto=True, mode="peak")
                if len(self.vars) > 1:
                    self.plot.addLegend(offset=(6, 4), labelTextSize="8pt")
                self.curves = []
                for i, v in enumerate(self.vars):
                    color = theme.c("measure") if len(self.vars) == 1 else theme.series(i)
                    self.curves.append(self.plot.plot(pen=pg.mkPen(color, width=2), name=v.name))
                self.lines = {}
                if len(self.vars) == 1:
                    for key, color, style, wdt in (("ref", "reference", Qt.DashLine, 1), ("wl", "warning", Qt.SolidLine, 1),
                                                   ("wh", "warning", Qt.SolidLine, 1), ("al", "critical", Qt.SolidLine, 2),
                                                   ("ah", "critical", Qt.SolidLine, 2)):
                        ln = pg.InfiniteLine(angle=0, pen=pg.mkPen(theme.c(color), width=wdt, style=style))
                        ln.setVisible(False)
                        self.plot.addItem(ln)
                        self.lines[key] = ln
            self.lay.addWidget(self.plot, 1)
        self.lbl_info = QLabel("")
        self.lbl_info.setAlignment(Qt.AlignCenter)
        self.lbl_info.setWordWrap(True)
        self.lbl_info.setStyleSheet(f"color:{theme.c('muted')};")
        self.lay.addWidget(self.lbl_info)

    # --- actualización ------------------------------------------------------------------
    def update_snapshot(self, snap: Snapshot) -> None:
        if not self.vars:
            return
        st = snap.statuses.get(self.vars[0].id)
        if self.chart == "trend":
            self._trend(snap)
        elif self.chart == "histogram":
            self._histogram(st)
        elif st is not None:
            if not st.var.numeric:
                self._state(st)
            elif self.chart == "gauge":
                self._gauge(st)
            else:
                self._value(st)

    def _ref_text(self, st: VarStatus) -> str:
        parts = []
        if st.reference is not None:
            parts.append(tr("Ref {v} ({src})", v=fmt(st.reference, st.var), src=tr(st.ref_source or "receta")))
        if st.deviation is not None:
            parts.append(f"Δ {st.deviation:+.3g}")
        if not st.fresh:
            parts.append(tr("dato viejo"))
        return " · ".join(parts)

    def _color_key(self, st: VarStatus) -> str:
        v = st.reading.value
        if st.level is not None and st.level >= Level.ALARM:
            return "critical"
        if st.level is not None and st.level >= Level.WARN:
            return "warning"
        if v is not None and st.bounds.any:
            return zone(v, st.bounds)
        return "neutral"

    def _value(self, st: VarStatus) -> None:
        v = st.reading.value
        key = self._color_key(st)
        color = theme.c(key) if key != "neutral" else theme.c("text")
        text = fmt(v, st.var, st.reading.decimals) if v is not None else "—"
        size = getattr(self, "value_px", None) or 30 + 8 * (self.tile.height - 1)
        self.lbl_value.setText(f"<span style='font-size:{size}px; color:{color}'><b>{text}</b></span>"
                               f"<span style='font-size:13px; color:{theme.c('muted')}'> {st.var.unit}</span>")
        t, y = self.series.get(st.var.id, period_s(self.tile.range_s, self.config))
        if self.bar is not None:
            lo, hi = auto_scale(st.bounds, st.reference, y[-200:] if len(y) else None, st.var,
                                (self.tile.scale_min, self.tile.scale_max))
            self.bar.set_data(v, lo, hi, st.bounds, st.reference, key)
        if self.spark is not None:
            self.spark.color = QColor(theme.c(key) if key not in ("neutral", "good") else theme.c("measure"))
            step = max(1, len(y) // 120)
            self.spark.set_values([float(x) for x in y[::step]])
        info = self._ref_text(st)
        if st.level is not None:
            info = f"<b style='color:{level_color(st.level).name()}'>{level_text(st.level)}</b>" + \
                   (f" · {info}" if info else "")
        self.lbl_info.setText(info)

    def _gauge(self, st: VarStatus) -> None:
        v = st.reading.value
        key = self._color_key(st)
        _t, y = self.series.get(st.var.id, period_s(self.tile.range_s, self.config))
        lo, hi = auto_scale(st.bounds, st.reference, y[-200:] if len(y) else None, st.var,
                            (self.tile.scale_min, self.tile.scale_max))
        text = fmt(v, st.var, st.reading.decimals) if v is not None else "—"
        self.gauge.set_data(v, lo, hi, st.bounds, st.reference, text, st.var.unit, key)
        self.lbl_info.setText(self._ref_text(st))

    def _state(self, st: VarStatus) -> None:
        text = st.reading.text or "—"
        if st.expected:
            key = "good" if text == st.expected else "critical"
        else:
            key = "text"
        color = theme.c(key)
        size = getattr(self, "value_px", None) or 26 + 8 * (self.tile.height - 1)
        self.lbl_value.setText(f"<span style='font-size:{size}px; color:{color}'><b>{text}</b></span>")
        info = tr("Esperado: {s}", s=st.expected) if st.expected else ""
        if not st.fresh:
            info = (info + " · " if info else "") + tr("dato viejo")
        self.lbl_info.setText(info)

    def _trend(self, snap: Snapshot) -> None:
        now = snap.ts
        rng = period_s(self.tile.range_s, self.config, now)
        ys = []
        for v, curve in zip(self.vars, self.curves):
            t, y = self.series.get(v.id, rng)
            curve.setData(t, y)
            if len(t):
                ys.append(np.asarray(y)[np.asarray(t) >= now - rng])
        self.plot.setXRange(now - rng, now, padding=0.01)
        limits = []
        if len(self.vars) == 1:
            st = snap.statuses.get(self.vars[0].id)
            b = st.bounds if st is not None else Bounds()
            ref = st.reference if st is not None else None
            for key, val in (("ref", ref), ("wl", b.wl), ("wh", b.wh), ("al", b.al), ("ah", b.ah)):
                self.lines[key].setVisible(val is not None)
                if val is not None:
                    self.lines[key].setValue(val)
            limits = [b.al, b.ah] if b.al is not None or b.ah is not None else [b.wl, b.wh]
            limits.append(ref)
            if st is not None and st.reading.value is not None:
                self.lbl_info.setText(f"{fmt(st.reading.value, st.var, st.reading.decimals)} {st.var.unit}"
                                      + (f" · {self._ref_text(st)}" if self._ref_text(st) else ""))
        yr = y_range(np.concatenate(ys) if ys else np.empty(0), limits)
        if yr is not None:
            self.plot.setYRange(*yr, padding=0)

    def _histogram(self, st: Optional[VarStatus]) -> None:
        self.plot.clear()
        _t, y = self.series.get(self.vars[0].id, period_s(self.tile.range_s, self.config))
        y = np.asarray(y, float)
        y = y[np.isfinite(y)]
        if len(y) < 5 or st is None:
            self.lbl_info.setText(tr("Datos insuficientes"))
            return
        lsl, usl = st.bounds.al, st.bounds.ah
        lo, hi = float(y.min()), float(y.max())
        lo = min(lo, lsl) if lsl is not None else lo
        hi = max(hi, usl) if usl is not None else hi
        if hi <= lo:
            hi = lo + 1
        bins = min(25, max(8, int(np.sqrt(len(y)))))
        counts, edges = np.histogram(y, bins=bins, range=(lo - (hi - lo) * 0.05, hi + (hi - lo) * 0.05))
        width = edges[1] - edges[0]
        self.plot.addItem(pg.BarGraphItem(x=edges[:-1] + width / 2, height=counts, width=width * 0.9,
                                          brush=pg.mkBrush(theme.c("hist"))))
        for val, key in ((lsl, "critical"), (usl, "critical"), (st.reference, "reference")):
            if val is not None:
                self.plot.addItem(pg.InfiniteLine(pos=val, angle=90, pen=pg.mkPen(theme.c(key), width=2)))
        cap = capability(y, lsl, usl)
        parts = [tr("n = {n}", n=len(y))]
        if cap is not None:
            parts.append(tr("media {m}", m=f"{cap.mean:.4g}"))
            if cap.cpk is not None:
                parts.append(f"Cpk {cap.cpk:.2f}")
        self.lbl_info.setText(" · ".join(parts))


# --- indicadores del sistema como valor o gráfica de tiempo ----------------------------------------
def kpi_color(key: str, v: Optional[float]) -> str:
    low, high = KPIS[key][2]
    if v is None:
        return theme.c("text")
    return theme.c("critical" if v < low else ("warning" if v < high else "good"))


def kpi_fmt(key: str, v: Optional[float]) -> str:
    return "—" if v is None else f"{v:.{KPIS[key][4]}f}"


class KpiValueTile(TileFrame):
    """Indicador como número grande con color por umbral."""

    def __init__(self, tile: HomeTile, title: str, target: str):
        super().__init__(title, target=target)
        self.tile = tile
        self.key = tile.kind
        self.lbl_value = QLabel("—")
        self.lbl_value.setAlignment(Qt.AlignCenter)
        self.lbl_value.setTextFormat(Qt.RichText)
        self.lay.addWidget(self.lbl_value, 1)
        self.sub = QLabel("")
        self.sub.setAlignment(Qt.AlignCenter)
        self.sub.setWordWrap(True)
        self.sub.setStyleSheet(f"color:{theme.c('muted')};")
        self.lay.addWidget(self.sub)

    def set(self, value: Optional[float], sub: str) -> None:
        size = getattr(self, "value_px", None) or 34 + 10 * (self.tile.height - 1)
        unit = KPIS[self.key][1]
        self.lbl_value.setText(f"<span style='font-size:{size}px; color:{kpi_color(self.key, value)}'>"
                               f"<b>{kpi_fmt(self.key, value)}</b></span>"
                               f"<span style='font-size:13px; color:{theme.c('muted')}'> {unit}</span>")
        self.sub.setText(translate_text(sub))


class KpiTrendTile(TileFrame):
    """Indicador en el tiempo: historial guardado cada 30 s más el valor actual."""

    def __init__(self, tile: HomeTile, title: str, target: str, engine):
        super().__init__(title, target=target)
        self.tile = tile
        self.key = tile.kind
        self.engine = engine
        self._cache: tuple = (0.0, 0.0, np.empty(0), np.empty(0))  # (consultado, desde, t, y)
        self.plot = pg.PlotWidget(axisItems={"bottom": pg.DateAxisItem()})
        self.plot.setMinimumHeight(110)
        self.plot.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)
        self.plot.showGrid(x=True, y=True, alpha=0.25)
        self.plot.setMouseEnabled(x=False, y=False)
        self.plot.hideButtons()
        self.plot.setMenuEnabled(False)
        self.curve = self.plot.plot(pen=pg.mkPen(theme.c("measure"), width=2))
        low, high = KPIS[self.key][2]
        for val, color in ((low, "critical"), (high, "good")):
            self.plot.addItem(pg.InfiniteLine(pos=val, angle=0, pen=pg.mkPen(theme.c(color), style=Qt.DashLine)))
        self.lay.addWidget(self.plot, 1)
        self.sub = QLabel("")
        self.sub.setAlignment(Qt.AlignCenter)
        self.sub.setStyleSheet(f"color:{theme.c('muted')};")
        self.lay.addWidget(self.sub)

    def history(self, since: float, now: float):
        hist = self.engine.historian
        if hist is None:
            return np.empty(0), np.empty(0)
        asked, frm, t, y = self._cache
        if now - asked > 15 or abs(frm - since) > 60:  # el historial se consulta como máximo cada 15 s
            rows = [r for r in hist.samples(kpi_var(self.key), since, now + 60) if r[1] is not None]
            arr = np.asarray(rows, float) if rows else np.empty((0, 2))
            t, y = (arr[:, 0], arr[:, 1]) if len(arr) else (np.empty(0), np.empty(0))
            self._cache = (now, since, t, y)
        return t, y

    def set(self, value: Optional[float], sub: str) -> None:
        import time as _time
        now = _time.time()
        rng = period_s(self.tile.range_s, self.engine.config, now)
        t, y = self.history(now - rng, now)
        if value is not None:
            t, y = np.append(t, now), np.append(y, value)
        self.curve.setData(t, y)
        self.plot.setXRange(now - rng, now, padding=0.01)
        yr = y_range(y, list(KPIS[self.key][2]))
        if yr is not None:
            lo_lim, hi_lim = KPIS[self.key][3]
            self.plot.setYRange(max(yr[0], lo_lim - (hi_lim - lo_lim) * 0.05), min(yr[1], hi_lim * 1.05), padding=0)
        self.sub.setText(f"{tr('Ahora')}: <b style='color:{kpi_color(self.key, value)}'>{kpi_fmt(self.key, value)}"
                         f"</b> {KPIS[self.key][1]}" + (f" · {translate_text(sub)}" if sub else ""))


def make_var_tile(tile: HomeTile, config: AppConfig, series: SeriesCache) -> VarTile:
    w = VarTile(tile, config, series)
    w.lbl_title.setText(translate_text(w.lbl_title.text()))
    return w
