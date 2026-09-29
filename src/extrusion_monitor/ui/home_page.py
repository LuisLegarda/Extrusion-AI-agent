"""Inicio: estado general de la máquina en una sola vista (indicadores tipo gauge)."""
from __future__ import annotations

import time
from typing import Callable, Optional

from PySide6.QtCore import QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QFrame, QGridLayout, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QSizePolicy, QVBoxLayout, QWidget,
)

from ..analysis.oee import STATE_LABELS, OeeResult, compute, human_factors
from ..analysis.rules import Level
from ..engine import MonitorEngine, Snapshot
from .common import level_color
from .kpi_dashboard import STATE_COLORS, Gauge, OeeSample, fmt_duration, shift_start

CARD_STYLE = ("QFrame#card { background: palette(base); border: 1px solid #d5dbe3; border-radius: 8px; }"
              "QFrame#card QLabel { border: none; background: transparent; }")
STABILITY_WINDOW_S = 1800.0  # estabilidad: % del tiempo normal en los últimos 30 min


def make_card(title: str) -> tuple[QFrame, QVBoxLayout]:
    fr = QFrame()
    fr.setObjectName("card")
    fr.setStyleSheet(CARD_STYLE)
    lay = QVBoxLayout(fr)
    lay.setContentsMargins(12, 10, 12, 10)
    lb = QLabel(f"<span style='font-size:14px; color:#1f3b57'><b>{title}</b></span>")
    lay.addWidget(lb)
    return fr, lay


class GaugeCard(QFrame):
    """Tarjeta con gauge; un clic lleva a la vista detallada."""

    clicked = Signal(str)

    def __init__(self, key: str, title: str, gauge: Gauge, tooltip: str):
        super().__init__()
        self.key = key
        self.setObjectName("card")
        self.setStyleSheet(CARD_STYLE)
        self.setToolTip(tooltip + "\n(clic para ver el detalle)")
        self.setCursor(Qt.PointingHandCursor)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 8, 10, 8)
        lb = QLabel(f"<span style='font-size:14px; color:#1f3b57'><b>{title}</b></span>")
        lb.setAlignment(Qt.AlignCenter)
        lay.addWidget(lb)
        self.gauge = gauge
        gauge.setMinimumSize(130, 110)
        lay.addWidget(gauge, 1)
        self.sub = QLabel("—")
        self.sub.setAlignment(Qt.AlignCenter)
        self.sub.setWordWrap(True)
        self.sub.setStyleSheet("color:#5f6b7a;")
        lay.addWidget(self.sub)

    def set(self, value: Optional[float], sub: str) -> None:
        self.gauge.set_value(value)
        self.sub.setText(sub)

    def mousePressEvent(self, event) -> None:
        self.clicked.emit(self.key)
        super().mousePressEvent(event)


class StateStrip(QWidget):
    """Franja de colores con el estado de la máquina en el turno."""

    def __init__(self):
        super().__init__()
        self.intervals: list = []
        self.a = self.b = 0.0
        self.setMinimumHeight(34)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def set_data(self, intervals: list, a: float, b: float) -> None:
        self.intervals, self.a, self.b = intervals, a, b
        self.update()

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        w, h = self.width(), self.height() - 14
        p.fillRect(0, 0, w, h, QColor("#eceff1"))
        span = (self.b - self.a) or 1.0
        for iv in self.intervals:
            x0 = w * (max(iv.start, self.a) - self.a) / span
            x1 = w * (min(iv.end, self.b) - self.a) / span
            if x1 > x0:
                p.fillRect(QRectF(x0, 0, max(1.0, x1 - x0), h), QColor(STATE_COLORS.get(iv.state, "#9e9e9e")))
        p.setPen(QPen(QColor("#5f6b7a")))
        f = p.font()
        f.setPointSizeF(8)
        p.setFont(f)
        if self.b > self.a:
            for k in range(5):
                t = self.a + span * k / 4
                x = w * k / 4
                align = Qt.AlignLeft if k == 0 else (Qt.AlignRight if k == 4 else Qt.AlignHCenter)
                rect = QRectF(x - (0 if k == 0 else (60 if k == 4 else 30)), h, 60, 14)
                p.drawText(rect, align, time.strftime("%H:%M", time.localtime(t)))
        p.end()


class BarList(QWidget):
    """Lista de barras horizontales (p. ej. Cpk por variable) con color por umbral."""

    def __init__(self, low: float, high: float, vmax: float):
        super().__init__()
        self.rows: list[tuple[str, Optional[float]]] = []
        self.low, self.high, self.vmax = low, high, vmax
        self.setMinimumHeight(120)

    def set_rows(self, rows: list[tuple[str, Optional[float]]]) -> None:
        self.rows = rows
        self.update()

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        if not self.rows:
            p.setPen(QColor("#8a94a3"))
            p.drawText(self.rect(), Qt.AlignCenter | Qt.TextWordWrap,
                       "Sin datos: se necesitan límites en la receta y lecturas en la ventana de tendencia.")
            p.end()
            return
        w = self.width()
        row_h = min(26.0, self.height() / len(self.rows))
        label_w = w * 0.45
        for i, (name, v) in enumerate(self.rows):
            y = i * row_h
            p.setPen(QColor("#33415c"))
            p.drawText(QRectF(0, y, label_w - 6, row_h), Qt.AlignRight | Qt.AlignVCenter,
                       p.fontMetrics().elidedText(name, Qt.ElideLeft, int(label_w - 8)))
            bar_w = w - label_w - 48
            p.fillRect(QRectF(label_w, y + row_h * 0.25, bar_w, row_h * 0.5), QColor("#eceff1"))
            if v is not None:
                frac = max(0.0, min(1.0, v / self.vmax))
                color = QColor("#e53935") if v < self.low else (QColor("#fbc02d") if v < self.high else QColor("#43a047"))
                p.fillRect(QRectF(label_w, y + row_h * 0.25, bar_w * frac, row_h * 0.5), color)
            p.setPen(QColor("#33415c"))
            p.drawText(QRectF(w - 46, y, 46, row_h), Qt.AlignRight | Qt.AlignVCenter,
                       "—" if v is None else f"{v:.2f}")
        p.end()


class HomePage(QWidget):
    """Dashboard general: OEE, índice 5.0, estabilidad, Cpk mínimo, conformidad y lectura."""

    navigate = Signal(str)

    def __init__(self, engine: MonitorEngine):
        super().__init__()
        self.engine = engine
        self._last_fast = 0.0
        self.oee: Optional[OeeResult] = None
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 10, 14, 10)
        root.setSpacing(10)

        grid = QGridLayout()
        grid.setSpacing(10)
        self.cards = {
            "oee": GaugeCard("kpi", "OEE (turno)", Gauge(60, 85, needle=False),
                             "Disponibilidad × Rendimiento × Calidad del turno en curso"),
            "i5": GaugeCard("kpi", "Índice 5.0", Gauge(60, 80, decimals=0, unit="/ 100", needle=False),
                            "Factor humano (carga de alarmas), resiliencia y sostenibilidad del turno"),
            "stability": GaugeCard("behavior", "Estabilidad", Gauge(80, 95, decimals=0, needle=False),
                                   "% del tiempo (últimos 30 min) en que el comportamiento aprendido fue normal"),
            "cpk": GaugeCard("spc", "Cpk mínimo (proceso)", Gauge(1.0, 1.33, vmin=0, vmax=2.0, unit="Cpk", decimals=2, needle=False),
                             "El Cpk más bajo de las variables con límites (ventana de tendencia)"),
            "conform": GaugeCard("variables", "En especificación", Gauge(90, 99, decimals=0, needle=False),
                                 "% de las variables verificadas que están dentro de tolerancia ahora"),
            "read": GaugeCard("variables", "Calidad de lectura", Gauge(90, 98, decimals=0, needle=False),
                              "% de las variables visibles leídas correctamente en el último ciclo"),
        }
        for i, c in enumerate(self.cards.values()):
            c.clicked.connect(self.navigate.emit)
            grid.addWidget(c, 0, i)
            grid.setColumnStretch(i, 1)
        root.addLayout(grid, 3)

        mid = QHBoxLayout()
        mid.setSpacing(10)
        st, sl = make_card("Estado de la máquina")
        self.lbl_state = QLabel("—")
        self.lbl_state.setTextFormat(Qt.RichText)
        self.lbl_state.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.lbl_state.setWordWrap(True)
        sl.addWidget(self.lbl_state, 1)
        mid.addWidget(st, 3)
        al, all_ = make_card("Alarmas y avisos activos")
        self.lst_alarms = QListWidget()
        self.lst_alarms.setStyleSheet("QListWidget { border: none; }")
        self.lst_alarms.itemDoubleClicked.connect(lambda _: self.navigate.emit("events"))
        all_.addWidget(self.lst_alarms, 1)
        mid.addWidget(al, 4)
        cp, cl = make_card("Cpk por variable (las 6 más bajas)")
        self.bars = BarList(1.0, 1.33, 2.0)
        cl.addWidget(self.bars, 1)
        mid.addWidget(cp, 4)
        root.addLayout(mid, 4)

        tl, tll = make_card("Estado del turno")
        self.strip = StateStrip()
        tll.addWidget(self.strip)
        self.lbl_legend = QLabel(" ".join(
            f"<span style='color:{STATE_COLORS[s]}'>■</span> {STATE_LABELS[s]}&nbsp;&nbsp;" for s in STATE_COLORS))
        self.lbl_legend.setStyleSheet("color:#5f6b7a;")
        tll.addWidget(self.lbl_legend)
        root.addWidget(tl)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh_oee)
        self.timer.start(10000)

    # --- datos rápidos (cada ciclo, máx. 1 vez por segundo) -------------------------------
    def update_snapshot(self, snap: Snapshot, force: bool = False) -> None:
        now = time.monotonic()
        if not force and (not self.isVisible() or now - self._last_fast < 1.0):
            return
        self._last_fast = now
        cfg = self.engine.config
        # Cpk por variable
        cpks = []
        speed = cfg.oee.speed_var if cfg.oee.enabled else None
        for vid, st in snap.statuses.items():
            # La velocidad de línea se evalúa en el OEE (sus paros no son un problema de capacidad).
            if vid != speed and st.var.measured and st.trend is not None and st.trend.cpk is not None:
                cpks.append((st.var.name, st.trend.cpk, cfg.var_label(st.var)))
        cpks.sort(key=lambda r: r[1])
        if cpks:
            worst = cpks[0]
            self.cards["cpk"].set(worst[1], worst[2])
        else:
            self.cards["cpk"].set(None, "Sin límites o sin datos suficientes")
        self.bars.set_rows([(label, v) for _, v, label in cpks[:6]])
        # Conformidad actual
        checked = [st for st in snap.statuses.values() if st.fresh and st.level is not None
                   and (st.bounds.any or st.expected)]
        if checked:
            ok = sum(st.level < Level.WARN for st in checked)
            self.cards["conform"].set(100.0 * ok / len(checked), f"{ok} de {len(checked)} variables")
        else:
            self.cards["conform"].set(None, "Sin receta o sin límites")
        # Calidad de lectura
        if snap.read_total:
            self.cards["read"].set(100.0 * snap.read_ok / snap.read_total,
                                   f"{snap.read_ok} de {snap.read_total} leídas" +
                                   (f" · {snap.error}" if snap.error else ""))
        else:
            self.cards["read"].set(None, snap.error or "Sin variables visibles")
        self._stability(snap.ts)
        self._alarms(snap)

    def _stability(self, now: float) -> None:
        mons = self.engine.behaviors
        scores = []
        for m in mons.active(self.engine.state.recipe):
            h = [x for x in mons.history.get(m.id, ()) if x[0] >= now - STABILITY_WINDOW_S]
            if h:
                scores.append((100.0 * sum(d2 <= thr for _, d2, thr in h) / len(h), m.name))
        if scores:
            worst = min(scores)
            sub = f"«{worst[1]}»" if len(scores) > 1 else "comportamiento normal"
            self.cards["stability"].set(worst[0], sub)
        elif mons.store.models:
            self.cards["stability"].set(None, "Sin datos frescos de los modelos")
        else:
            self.cards["stability"].set(None, "Entrena un comportamiento (menú Entrenamiento)")

    def _alarms(self, snap: Snapshot) -> None:
        self.lst_alarms.clear()
        findings = sorted(snap.findings, key=lambda f: (-int(f.level), f.since))
        for f in findings[:30]:
            if f.level < Level.WARN:
                continue
            it = QListWidgetItem(f"{time.strftime('%H:%M', time.localtime(f.since))}  {f.message}")
            it.setForeground(level_color(f.level))
            self.lst_alarms.addItem(it)
        if not self.lst_alarms.count():
            it = QListWidgetItem("✔ Sin alarmas ni avisos activos")
            it.setForeground(QColor("#2e7d32"))
            self.lst_alarms.addItem(it)

    # --- OEE e índice 5.0 (historial, cada 10 s) ------------------------------------------
    def refresh_oee(self, force: bool = False) -> None:
        if not force and not self.isVisible():
            return
        eng = self.engine
        o = eng.config.oee
        speed_var = eng.config.variable(o.speed_var) if o.speed_var else None
        if not (o.enabled and speed_var and eng.historian):
            for k in ("oee", "i5"):
                self.cards[k].set(None, "Configura el OEE (Configuración → KPI / OEE)")
            self.lbl_state.setText(self._state_text(None))
            return
        now = eng.clock()
        a = shift_start(now, o.shift_starts)
        rows = eng.historian.oee_samples(a, now)
        samples = [OeeSample(r[0], r[1], r[2], r[3], r[4], None if r[5] is None else bool(r[5]), r[6] or 0)
                   for r in rows]
        res = compute(samples, a, now, o.microstop_s, o.length_factor)
        self.oee = res

        def pc(v):
            return "—" if v is None else f"{100 * v:.0f}"

        self.cards["oee"].set(None if res.oee is None else 100 * res.oee,
                              f"D {pc(res.availability)} · R {pc(res.performance)} · C {pc(res.quality)}")
        hf = human_factors(eng.historian.events_between(a, now), res)
        self.cards["i5"].set(hf.index, f"{hf.alarms_per_hour:.1f} alarmas/h · "
                                       f"normal {'—' if res.normal_pct is None else f'{res.normal_pct:.0f} %'}")
        self.strip.set_data(res.intervals, a, now)
        self.lbl_state.setText(self._state_text(res))

    def _state_text(self, res: Optional[OeeResult]) -> str:
        eng = self.engine
        snap = eng.last
        cfg = eng.config
        o = cfg.oee
        lines = []
        cur = res.intervals[-1] if res is not None and res.intervals else None
        if cur is not None:
            color = STATE_COLORS[cur.state]
            lines.append(f"<span style='font-size:22px; color:{color}'><b>● {STATE_LABELS[cur.state]}</b></span>"
                         f"&nbsp;&nbsp;desde hace {fmt_duration(cur.duration)}")
        elif not eng.running:
            lines.append("<span style='font-size:22px; color:#757575'><b>● Monitoreo detenido</b></span>")
        if snap is not None and o.speed_var:
            st = snap.statuses.get(o.speed_var)
            if st is not None and st.reading.value is not None:
                nominal = f" / {res.avg_nominal:.4g}" if res is not None and res.avg_nominal else ""
                lines.append(f"Velocidad: <b>{st.reading.value:g}</b>{nominal} {st.var.unit}")
        lines.append(f"Receta: <b>{eng.state.recipe or '—'}</b>")
        if res is not None:
            u = o.length_unit
            lines.append(f"Producido en el turno: <b>{res.length_total:,.0f} {u}</b> "
                         f"(conforme {res.length_good:,.0f} {u})")
            lines.append(f"Paros: <b>{res.n_stops}</b> · microparos: <b>{res.n_microstops}</b> · "
                         f"detenido {fmt_duration(res.stop_s)}")
        if snap is not None:
            n_alarm = sum(f.level >= Level.ALARM for f in snap.findings)
            n_warn = sum(f.level == Level.WARN for f in snap.findings)
            lines.append(f"Hallazgos: <b style='color:#c62828'>{n_alarm} alarmas</b> · "
                         f"<b style='color:#b28704'>{n_warn} avisos</b>")
        return "<br>".join(lines)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        QTimer.singleShot(0, lambda: self.refresh_oee(force=True))
        if self.engine.last is not None:
            QTimer.singleShot(0, lambda: self.update_snapshot(self.engine.last, force=True))
