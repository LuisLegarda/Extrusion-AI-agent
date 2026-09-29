"""Dashboard KPI: OEE, estado de la máquina e indicadores de Industria 5.0."""
from __future__ import annotations

import datetime as dt
import math
import time
from typing import Optional

import pyqtgraph as pg
from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QComboBox, QFrame, QGridLayout, QHBoxLayout, QHeaderView, QLabel, QSizePolicy, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)

from ..analysis.oee import (ASSUMED, MICROSTOP, RUNNING, SLOW, STATE_LABELS, STATE_ORDER, STOPPED, UNKNOWN, OeeResult,
                            OeeSample, compute, human_factors, sparkline)
from ..engine import MonitorEngine

STATE_COLORS = {RUNNING: "#43a047", ASSUMED: "#a5d6a7", SLOW: "#fbc02d", MICROSTOP: "#fb8c00",
                STOPPED: "#e53935", UNKNOWN: "#9e9e9e"}
RED, YELLOW, GREEN = QColor("#e53935"), QColor("#fbc02d"), QColor("#43a047")

PERIODS = [("shift", "Turno actual"), (3600, "Última hora"), (8 * 3600, "Últimas 8 h"),
           (24 * 3600, "Últimas 24 h"), (7 * 86400, "Últimos 7 días")]


def fmt_duration(s: Optional[float]) -> str:
    if s is None:
        return "—"
    s = int(round(s))
    d, rem = divmod(s, 86400)
    h, rem = divmod(rem, 3600)
    m, sec = divmod(rem, 60)
    return (f"{d}d " if d else "") + f"{h:02d}:{m:02d}:{sec:02d}"


def pct(v: Optional[float]) -> str:
    return "—" if v is None else f"{100 * v:.1f} %"


def shift_start(now: float, starts: list[str]) -> float:
    """Inicio del turno en curso según las horas de inicio configuradas (p. ej. 06:00, 14:00, 22:00)."""
    t = dt.datetime.fromtimestamp(now)
    cands = []
    for s in starts:
        try:
            hh, mm = (int(x) for x in s.strip().split(":"))
        except ValueError:
            continue
        for day in (0, -1):
            c = (t + dt.timedelta(days=day)).replace(hour=hh, minute=mm, second=0, microsecond=0)
            if c <= t:
                cands.append(c)
    return max(cands).timestamp() if cands else now - 8 * 3600


class Gauge(QWidget):
    """Indicador de aguja con bandas rojo/amarillo/verde (por defecto 0-100 %)."""

    def __init__(self, low: float = 60, high: float = 85, parent=None, vmin: float = 0.0, vmax: float = 100.0,
                 unit: str = "%", decimals: int = 1, needle: bool = False):
        super().__init__(parent)
        self.value: Optional[float] = None
        self.needle = needle
        self.low, self.high = low, high
        self.vmin, self.vmax, self.unit, self.decimals = vmin, vmax, unit, decimals
        self.setMinimumSize(150, 120)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    def set_value(self, v: Optional[float]) -> None:
        if v != self.value:
            self.value = v
            self.update()

    def _pos(self, v: float) -> float:
        """Valor → 0..100 del arco."""
        return 100.0 * (min(max(v, self.vmin), self.vmax) - self.vmin) / ((self.vmax - self.vmin) or 1.0)

    def _color(self, v: float) -> QColor:
        return RED if v < self.low else (YELLOW if v < self.high else GREEN)

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        side = min(w, h * 1.25) - 16
        rect = QRectF((w - side) / 2, 8, side, side)
        thick = max(8.0, side * 0.09)
        start, span = 225.0, -270.0

        def arc(a: float, b: float, color: QColor, width: float) -> None:
            pen = QPen(color, width)
            pen.setCapStyle(Qt.FlatCap)
            p.setPen(pen)
            p.drawArc(rect.adjusted(thick, thick, -thick, -thick),
                      int((start + span * a / 100) * 16), int(span * (b - a) / 100 * 16))

        arc(0, 100, QColor(120, 120, 120, 60), thick)
        lo, hi = self._pos(self.low), self._pos(self.high)
        for a, b, c in ((0, lo, RED), (lo, hi, YELLOW), (hi, 100, GREEN)):
            arc(a, b, c, thick * 0.35)
        if self.value is not None:
            v = self._pos(self.value)
            arc(0, v, self._color(self.value), thick)
        if self.value is not None and self.needle:
            v = self._pos(self.value)
            ang = math.radians(start + span * v / 100)
            c = rect.center()
            r = side / 2 - thick * 1.6
            p.setPen(QPen(self.palette().text().color(), 2))
            p.drawLine(c, QPointF(c.x() + r * math.cos(ang), c.y() - r * math.sin(ang)))
        f = QFont(self.font())
        f.setPointSizeF(max(10.0, side * 0.12))
        f.setBold(True)
        p.setFont(f)
        p.setPen(self.palette().text().color())
        text = "—" if self.value is None else f"{self.value:.{self.decimals}f}"
        p.drawText(rect.adjusted(0, side * 0.18, 0, 0), Qt.AlignCenter, text)
        f.setPointSizeF(max(8.0, side * 0.07))
        f.setBold(False)
        p.setFont(f)
        p.drawText(rect.adjusted(0, side * 0.42, 0, 0), Qt.AlignCenter, self.unit)
        p.end()


class Sparkline(QWidget):
    def __init__(self, color: str = "#1e88e5", parent=None):
        super().__init__(parent)
        self.values: list[Optional[float]] = []
        self.color = QColor(color)
        self.setMinimumHeight(34)

    def set_values(self, values: list[Optional[float]]) -> None:
        self.values = values
        self.update()

    def paintEvent(self, _event) -> None:
        pts = [(i, v) for i, v in enumerate(self.values) if v is not None]
        if len(pts) < 2:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height() - 4
        n = max(len(self.values) - 1, 1)
        lo, hi = min(v for _, v in pts), max(v for _, v in pts)
        if hi - lo < 1e-9:
            lo, hi = lo - 0.01, hi + 0.01
        path = QPainterPath()
        fill = QPainterPath()
        for k, (i, v) in enumerate(pts):
            pt = QPointF(w * i / n, 2 + h * (1 - (v - lo) / (hi - lo)))
            (path.moveTo if k == 0 else path.lineTo)(pt)
            if k == 0:
                fill.moveTo(QPointF(pt.x(), h + 2))
            fill.lineTo(pt)
        fill.lineTo(QPointF(w * pts[-1][0] / n, h + 2))
        c = QColor(self.color)
        c.setAlpha(50)
        p.fillPath(fill, c)
        p.setPen(QPen(self.color, 2))
        p.drawPath(path)
        p.end()


def card(title: str) -> tuple[QFrame, QVBoxLayout]:
    fr = QFrame()
    fr.setFrameShape(QFrame.StyledPanel)
    fr.setStyleSheet("QFrame { border: 1px solid #c8ccd2; border-radius: 6px; }"
                     "QLabel { border: none; }")
    lay = QVBoxLayout(fr)
    lay.setContentsMargins(10, 8, 10, 8)
    lb = QLabel(f"<b>{title}</b>")
    lay.addWidget(lb)
    return fr, lay


class KpiCard(QFrame):
    def __init__(self, title: str, low: float, high: float, tooltip: str):
        super().__init__()
        self.setFrameShape(QFrame.StyledPanel)
        self.setStyleSheet("QFrame { border: 1px solid #c8ccd2; border-radius: 6px; } QLabel { border: none; }")
        self.setToolTip(tooltip)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 8, 10, 8)
        lay.addWidget(QLabel(f"<b>{title}</b>"))
        self.gauge = Gauge(low, high)
        lay.addWidget(self.gauge, 1)
        self.spark = Sparkline()
        lay.addWidget(self.spark)
        self.prev = QLabel()
        lay.addWidget(self.prev)

    def set(self, value: Optional[float], previous: Optional[float], spark: list[Optional[float]]) -> None:
        self.gauge.set_value(None if value is None else 100 * value)
        self.spark.set_values(spark)
        self.prev.setText(f"<span style='color:#757575'>Periodo anterior</span><br><b>{pct(previous)}</b>")


class KpiDashboard(QWidget):
    def __init__(self, engine: MonitorEngine):
        super().__init__()
        self.engine = engine
        self.result: Optional[OeeResult] = None
        root = QVBoxLayout(self)
        top = QHBoxLayout()
        top.addWidget(QLabel("<span style='font-size:18px'><b>OEE</b></span>"))
        top.addStretch()
        self.lbl_range = QLabel()
        top.addWidget(self.lbl_range)
        top.addWidget(QLabel("Periodo:"))
        self.cmb = QComboBox()
        for key, label in PERIODS:
            self.cmb.addItem(label, key)
        self.cmb.currentIndexChanged.connect(lambda _: self.refresh())
        top.addWidget(self.cmb)
        root.addLayout(top)
        self.lbl_config = QLabel()
        self.lbl_config.setWordWrap(True)
        root.addWidget(self.lbl_config)

        grid = QGridLayout()
        self.cards = {
            "oee": KpiCard("OEE", 60, 85, "Disponibilidad × Rendimiento × Calidad"),
            "availability": KpiCard("Disponibilidad", 80, 90, "Tiempo en marcha / tiempo planificado. "
                                                            "Velocidad ≤ umbral = línea detenida."),
            "performance": KpiCard("Rendimiento", 80, 95, "Velocidad real promedio / velocidad nominal "
                                                         "(los microparos cuentan como velocidad 0)."),
            "quality": KpiCard("Calidad", 95, 99, "Longitud producida en condición conforme / longitud total."),
        }
        for i, c in enumerate(self.cards.values()):
            grid.addWidget(c, 0, i)
        other, ol = card("Otros KPIs")
        self.tbl_other = QTableWidget(0, 3)
        self.tbl_other.setHorizontalHeaderLabels(["", "Actual", "Anterior"])
        self.tbl_other.verticalHeader().setVisible(False)
        self.tbl_other.setEditTriggers(QTableWidget.NoEditTriggers)
        self.tbl_other.verticalHeader().setDefaultSectionSize(22)
        self.tbl_other.setStyleSheet("QTableWidget { border: none; }")
        ol.addWidget(self.tbl_other)
        grid.addWidget(other, 0, 4)
        for i in range(5):
            grid.setColumnStretch(i, 1)
        root.addLayout(grid, 3)

        bottom = QHBoxLayout()
        status, sl = card("Estado de la máquina")
        self.lbl_state = QLabel()
        sl.addWidget(self.lbl_state)
        self.timeline = pg.PlotWidget(axisItems={"bottom": pg.DateAxisItem()})
        self.timeline.setMouseEnabled(y=False)
        self.timeline.showGrid(x=True, y=False, alpha=0.2)
        rows = ["Resumen"] + [STATE_LABELS[s] for s in STATE_ORDER]
        self.timeline.getAxis("left").setTicks([[(-i, r) for i, r in enumerate(rows)]])
        self.timeline.setYRange(-len(rows) + 0.4, 0.6)
        sl.addWidget(self.timeline, 1)
        bottom.addWidget(status, 3)
        dist, dl = card("Distribución")
        self.tbl_dist = QTableWidget(0, 3)
        self.tbl_dist.setHorizontalHeaderLabels(["Estado", "Duración", "Veces"])
        self.tbl_dist.verticalHeader().setVisible(False)
        self.tbl_dist.setEditTriggers(QTableWidget.NoEditTriggers)
        self.tbl_dist.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.tbl_dist.setStyleSheet("QTableWidget { border: none; }")
        dl.addWidget(self.tbl_dist)
        bottom.addWidget(dist, 1)
        i5, il = card("Industria 5.0 · personas, resiliencia y sostenibilidad")
        row = QHBoxLayout()
        self.g_human, self.g_resil, self.g_sust = Gauge(50, 80), Gauge(70, 90), Gauge(90, 97)
        for g, name, tip in (
                (self.g_human, "Factor humano", "Carga de alarmas por hora según ISA-18.2: ≤6/h manejable"),
                (self.g_resil, "Resiliencia", "% del tiempo con el proceso en condición normal (sin avisos)"),
                (self.g_sust, "Sostenibilidad", "Material conforme, penalizado por tiempo detenido")):
            col = QVBoxLayout()
            lb = QLabel(f"<b>{name}</b>")
            lb.setAlignment(Qt.AlignCenter)
            col.addWidget(lb)
            g.setToolTip(tip)
            g.setMinimumSize(110, 95)
            col.addWidget(g, 1)
            row.addLayout(col)
        il.addLayout(row, 1)
        self.lbl_i5 = QLabel()
        self.lbl_i5.setWordWrap(True)
        il.addWidget(self.lbl_i5)
        bottom.addWidget(i5, 2)
        root.addLayout(bottom, 3)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(5000)

    # --- datos -----------------------------------------------------------------------------
    def _period(self, now: float) -> tuple[float, float]:
        key = self.cmb.currentData()
        o = self.engine.config.oee
        if key == "shift":
            return shift_start(now, o.shift_starts), now
        return now - float(key), now

    def _samples(self, a: float, b: float) -> list[OeeSample]:
        rows = self.engine.historian.oee_samples(a, b) if self.engine.historian else []
        return [OeeSample(r[0], r[1], r[2], r[3], r[4], None if r[5] is None else bool(r[5]), r[6] or 0)
                for r in rows]

    def refresh(self) -> None:
        if not self.isVisible():
            return
        o = self.engine.config.oee
        speed_var = self.engine.config.variable(o.speed_var) if o.speed_var else None
        if not (o.enabled and speed_var):
            self.lbl_config.setText("<b>Configura el OEE</b> en ⚙ Configurar variables → pestaña «KPI / OEE»: "
                                    "elige la variable de velocidad de línea, la velocidad nominal y cómo se "
                                    "mide la calidad.")
            return
        now = self.engine.clock()
        a, b = self._period(now)
        span = b - a
        samples = self._samples(a - span, b)  # incluye el periodo anterior
        res = compute(samples, a, b, o.microstop_s, o.length_factor)
        prev = compute(samples, a - span, a, o.microstop_s, o.length_factor)
        spark = sparkline(samples, a, b, o.microstop_s, o.length_factor)
        self.result = res
        fmt = "%d/%m %H:%M"
        self.lbl_range.setText(f"{time.strftime(fmt, time.localtime(a))} → {time.strftime(fmt, time.localtime(b))}  ")
        qmode = {"spec": "variables en especificación", "selector": "indicador visual",
                 "both": "variables en especificación e indicador visual"}[o.quality_mode]
        self.lbl_config.setText(
            f"<span style='color:#757575'>Velocidad: {self.engine.config.var_label(speed_var)} · paro si ≤ "
            f"{o.stop_threshold:g} · microparo &lt; {o.microstop_s:g} s · calidad por {qmode}</span>")
        for k, c in self.cards.items():
            c.set(getattr(res, k), getattr(prev, k), spark[k])
        self._fill_other(res, prev, speed_var.unit)
        self._fill_timeline(res, a, b)
        self._fill_distribution(res)
        self._fill_i5(res, a, b)

    def _fill_other(self, res: OeeResult, prev: OeeResult, unit: str) -> None:
        u = self.engine.config.oee.length_unit
        def speed(r: OeeResult) -> str:
            return "—" if r.avg_speed is None else f"{r.avg_speed:.4g} {unit}"

        rows = [
            ("TEEP", pct(res.teep), pct(prev.teep)),
            ("MTBF", fmt_duration(res.mtbf_s), fmt_duration(prev.mtbf_s)),
            ("MTTR", fmt_duration(res.mttr_s), fmt_duration(prev.mttr_s)),
            ("Paros", str(res.n_stops), str(prev.n_stops)),
            ("Microparos", str(res.n_microstops), str(prev.n_microstops)),
            ("En marcha", fmt_duration(res.run_s), fmt_duration(prev.run_s)),
            ("Detenido", fmt_duration(res.stop_s), fmt_duration(prev.stop_s)),
            ("Producido", f"{res.length_total:,.0f} {u}", f"{prev.length_total:,.0f} {u}"),
            ("Conforme", f"{res.length_good:,.0f} {u}", f"{prev.length_good:,.0f} {u}"),
            ("Desperdicio", f"{res.length_scrap:,.0f} {u}", f"{prev.length_scrap:,.0f} {u}"),
            ("Vel. promedio", speed(res), speed(prev)),
            ("Vel. nominal", "—" if res.avg_nominal is None else f"{res.avg_nominal:.4g} {unit}", ""),
        ]
        self.tbl_other.setRowCount(len(rows))
        for i, row in enumerate(rows):
            for c, v in enumerate(row):
                it = QTableWidgetItem(v)
                if c:
                    it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.tbl_other.setItem(i, c, it)
        self.tbl_other.resizeColumnsToContents()

    def _fill_timeline(self, res: OeeResult, a: float, b: float) -> None:
        self.timeline.clear()
        for state in STATE_ORDER:
            ivs = [iv for iv in res.intervals if iv.state == state]
            if not ivs:
                continue
            row = -(STATE_ORDER.index(state) + 1)
            color = pg.mkBrush(STATE_COLORS[state])
            for y in (0, row):
                self.timeline.addItem(pg.BarGraphItem(
                    x0=[iv.start for iv in ivs], x1=[iv.end for iv in ivs], y=[y] * len(ivs), height=0.7,
                    brush=color, pen=pg.mkPen(None)))
        self.timeline.setXRange(a, b, padding=0.01)
        cur = res.intervals[-1] if res.intervals else None
        if cur is not None:
            color = STATE_COLORS[cur.state]
            self.lbl_state.setText(f"Estado actual: <b style='color:{color}'>{STATE_LABELS[cur.state]}</b> "
                                   f"desde hace {fmt_duration(cur.duration)}")
        else:
            self.lbl_state.setText("Sin datos en el periodo.")

    def _fill_distribution(self, res: OeeResult) -> None:
        states = [s for s in STATE_ORDER if s in res.distribution]
        self.tbl_dist.setRowCount(len(states))
        for i, s in enumerate(states):
            d, n = res.distribution[s]
            it = QTableWidgetItem(f"● {STATE_LABELS[s]}")
            it.setForeground(QColor(STATE_COLORS[s]))
            self.tbl_dist.setItem(i, 0, it)
            self.tbl_dist.setItem(i, 1, QTableWidgetItem(fmt_duration(d)))
            self.tbl_dist.setItem(i, 2, QTableWidgetItem(str(n)))

    def _fill_i5(self, res: OeeResult, a: float, b: float) -> None:
        events = self.engine.historian.events_between(a, b) if self.engine.historian else []
        hf = human_factors(events, res)
        self.g_human.set_value(hf.human_score)
        self.g_resil.set_value(hf.resilience_score)
        self.g_sust.set_value(hf.sustainability_score)
        idx = "—" if hf.index is None else f"{hf.index:.0f}"
        color = "#757575" if hf.index is None else ("#43a047" if hf.index >= 80 else
                                                     ("#fbc02d" if hf.index >= 60 else "#e53935"))
        scrap = 100 * (1 - res.quality) if res.quality is not None else None
        self.lbl_i5.setText(
            f"<b>Índice 5.0: <span style='color:{color}; font-size:16px'>{idx}</span></b> / 100<br>"
            f"Alarmas y avisos: {hf.alarms_per_hour:.1f}/h (ISA-18.2 recomienda ≤ 6/h) · "
            f"intervenciones del operador: {hf.interventions_per_hour:.1f}/h<br>"
            f"Tiempo en condición normal: {'—' if res.normal_pct is None else f'{res.normal_pct:.0f} %'} · "
            f"recuperación media: {fmt_duration(hf.mean_recovery_s)}<br>"
            f"Desperdicio: {'—' if scrap is None else f'{scrap:.1f} %'} "
            f"({res.length_scrap:,.0f} {self.engine.config.oee.length_unit}) · tiempo detenido: "
            f"{fmt_duration(res.stop_s)}")

    def showEvent(self, event) -> None:
        super().showEvent(event)
        QTimer.singleShot(0, self.refresh)
