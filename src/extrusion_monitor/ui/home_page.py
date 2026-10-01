"""Inicio: estado general de la máquina en una sola vista (indicadores tipo gauge)."""
from __future__ import annotations

import time
from typing import Callable, Optional

from PySide6.QtCore import QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QFrame, QGridLayout, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QPushButton, QScrollArea, QSizePolicy,
    QVBoxLayout, QWidget,
)

from ..analysis.kpis import KPIS
from ..analysis.oee import STATE_LABELS, OeeResult, compute, human_factors
from ..analysis.rules import Level
from ..config import KPI_KINDS
from ..engine import MonitorEngine, Snapshot
from ..i18n import tr, translate_text
from . import theme
from .common import SeriesCache, level_color
from .home_tiles import KpiTrendTile, KpiValueTile, make_var_tile
from .kpi_dashboard import STATE_COLORS, Gauge, OeeSample, fmt_duration, shift_start

STABILITY_WINDOW_S = 1800.0  # estabilidad: % del tiempo normal en los últimos 30 min


def make_card(title: str) -> tuple[QFrame, QVBoxLayout]:
    fr = QFrame()
    fr.setObjectName("card")
    lay = QVBoxLayout(fr)
    lay.setContentsMargins(12, 10, 12, 10)
    lb = QLabel(f"<span style='font-size:14px; color:{theme.c('title')}'><b>{tr(title)}</b></span>")
    lay.addWidget(lb)
    return fr, lay


class GaugeCard(QFrame):
    """Tarjeta con gauge; un clic lleva a la vista detallada."""

    clicked = Signal(str)

    def __init__(self, key: str, title: str, gauge: Gauge, tooltip: str):
        super().__init__()
        self.key = key
        self.setObjectName("card")
        self.setToolTip(tr(tooltip) + tr("\n(clic para ver el detalle)"))
        self.setCursor(Qt.PointingHandCursor)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 8, 10, 8)
        lb = QLabel(f"<span style='font-size:14px; color:{theme.c('title')}'><b>{tr(title)}</b></span>")
        lb.setAlignment(Qt.AlignCenter)
        lay.addWidget(lb)
        self.gauge = gauge
        gauge.setMinimumSize(130, 110)
        lay.addWidget(gauge, 1)
        self.sub = QLabel("—")
        self.sub.setAlignment(Qt.AlignCenter)
        self.sub.setWordWrap(True)
        self.sub.setStyleSheet(f"color:{theme.c('muted')};")
        lay.addWidget(self.sub)

    def set(self, value: Optional[float], sub: str) -> None:
        self.gauge.set_value(value)
        self.sub.setText(translate_text(sub))

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
        p.fillRect(0, 0, w, h, QColor(theme.c("track")))
        span = (self.b - self.a) or 1.0
        for iv in self.intervals:
            x0 = w * (max(iv.start, self.a) - self.a) / span
            x1 = w * (min(iv.end, self.b) - self.a) / span
            if x1 > x0:
                p.fillRect(QRectF(x0, 0, max(1.0, x1 - x0), h), QColor(STATE_COLORS.get(iv.state, theme.c("neutral"))))
        p.setPen(QPen(QColor(theme.c("muted"))))
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
            p.setPen(QColor(theme.c("muted")))
            p.drawText(self.rect(), Qt.AlignCenter | Qt.TextWordWrap,
                       tr("Sin datos: se necesitan límites en la receta y lecturas en la ventana de tendencia."))
            p.end()
            return
        w = self.width()
        row_h = min(26.0, self.height() / len(self.rows))
        label_w = w * 0.45
        for i, (name, v) in enumerate(self.rows):
            y = i * row_h
            p.setPen(QColor(theme.c("text")))
            p.drawText(QRectF(0, y, label_w - 6, row_h), Qt.AlignRight | Qt.AlignVCenter,
                       p.fontMetrics().elidedText(name, Qt.ElideLeft, int(label_w - 8)))
            bar_w = w - label_w - 48
            p.fillRect(QRectF(label_w, y + row_h * 0.25, bar_w, row_h * 0.5), QColor(theme.c("track")))
            if v is not None:
                frac = max(0.0, min(1.0, v / self.vmax))
                color = QColor(theme.c("critical") if v < self.low else
                               (theme.c("warning") if v < self.high else theme.c("good")))
                p.fillRect(QRectF(label_w, y + row_h * 0.25, bar_w * frac, row_h * 0.5), color)
            p.setPen(QColor(theme.c("text")))
            p.drawText(QRectF(w - 46, y, 46, row_h), Qt.AlignRight | Qt.AlignVCenter,
                       "—" if v is None else f"{v:.2f}")
        p.end()


BUILTIN_TILES = {**{k: v[0] for k, v in KPIS.items()},
                 "machine": "Estado de la máquina", "alarms": "Alarmas y avisos activos",
                 "cpk_bars": "Cpk por variable (las 6 más bajas)", "shift": "Estado del turno"}
KPI_INFO = {  # clave -> (vista detallada, descripción)
    "oee": ("kpi", "Disponibilidad × Rendimiento × Calidad del turno en curso"),
    "availability": ("kpi", "Tiempo en marcha / tiempo planificado del turno"),
    "performance": ("kpi", "Velocidad real promedio / velocidad nominal del turno"),
    "quality": ("kpi", "Metros conformes / metros producidos en el turno"),
    "i5": ("kpi", "Factor humano (carga de alarmas), resiliencia y sostenibilidad del turno"),
    "stability": ("behavior", "% del tiempo (últimos 30 min) en que el comportamiento aprendido fue normal"),
    "cpk": ("spc", "El Cpk más bajo de las variables con límites (ventana de tendencia)"),
    "conform": ("variables", "% de las variables verificadas que están dentro de tolerancia ahora"),
    "read": ("variables", "% de las variables visibles leídas correctamente en el último ciclo"),
}
ROW_MIN_H = 170  # alto mínimo de una fila del tablero


def pack_tiles(tiles, columns: int) -> list[tuple[int, int, int, int]]:
    """Posición (fila, columna, alto, ancho) de cada mosaico: se colocan en orden en el primer hueco libre."""
    used: set[tuple[int, int]] = set()
    out = []
    for t in tiles:
        w, h = min(t.width, columns), t.height
        r = 0
        while True:
            col = next((c for c in range(columns - w + 1)
                        if all((r + i, c + j) not in used for i in range(h) for j in range(w))), None)
            if col is not None:
                break
            r += 1
        used |= {(r + i, col + j) for i in range(h) for j in range(w)}
        out.append((r, col, h, w))
    return out


class HomePage(QWidget):
    """Dashboard general configurable: indicadores del sistema y variables con el gráfico elegido."""

    navigate = Signal(str)
    customize = Signal()

    def __init__(self, engine: MonitorEngine):
        super().__init__()
        self.engine = engine
        self._last_fast = 0.0
        self.oee: Optional[OeeResult] = None
        self.series = SeriesCache(engine)
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 6, 14, 10)
        root.setSpacing(6)
        bar = QHBoxLayout()
        bar.addStretch(1)
        self.btn_custom = QPushButton("✎ Personalizar tablero")
        self.btn_custom.setToolTip("Elige qué indicadores y variables se muestran y con qué tipo de gráfico")
        self.btn_custom.clicked.connect(self.customize.emit)
        bar.addWidget(self.btn_custom)
        root.addLayout(bar)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        root.addWidget(self.scroll, 1)
        self.rebuild()

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh_oee)
        self.timer.start(10000)

    # --- construcción ---------------------------------------------------------------------
    def rebuild(self) -> None:
        """Vuelve a armar el tablero con la configuración actual."""
        home = self.engine.config.home
        self.cards: dict[str, GaugeCard] = {}
        self.kpi_widgets: dict[str, list] = {}  # clave -> gauges, valores y gráficas de ese indicador
        self.var_tiles: list = []
        self.lbl_state = self.lst_alarms = self.bars = self.strip = None
        content = QWidget()
        content.setObjectName("content")
        grid = QGridLayout(content)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(10)
        cols = home.columns
        places = pack_tiles(home.tiles, cols)
        rows: dict[int, bool] = {}
        for tile, (r, c, h, w) in zip(home.tiles, places):
            widget = self._make_tile(tile)
            grid.addWidget(widget, r, c, h, w)
            fixed = tile.kind == "shift"
            for i in range(h):
                rows[r + i] = rows.get(r + i, False) or not fixed
        for c in range(cols):
            grid.setColumnStretch(c, 1)
        for r, grows in rows.items():
            grid.setRowStretch(r, 1 if grows else 0)
            if grows:
                grid.setRowMinimumHeight(r, ROW_MIN_H)
        if not home.tiles:
            empty = QLabel(tr("El tablero está vacío: usa «✎ Personalizar tablero» para agregar indicadores."))
            empty.setAlignment(Qt.AlignCenter)
            grid.addWidget(empty, 0, 0)
        elif not any(rows.values()):
            grid.setRowStretch(max(rows) + 1, 1)
        old = self.scroll.takeWidget()
        if old is not None:
            old.deleteLater()
        self.scroll.setWidget(content)
        if self.isVisible():
            QTimer.singleShot(0, lambda: self.refresh_oee(force=True))
            if self.engine.last is not None:
                QTimer.singleShot(0, lambda: self.update_snapshot(self.engine.last, force=True))

    def _make_tile(self, tile) -> QWidget:
        title = tile.title or BUILTIN_TILES.get(tile.kind, "")
        k = tile.kind
        if k == "var":
            w = make_var_tile(tile, self.engine.config, self.series)
            w.clicked.connect(self.navigate.emit)
            self.var_tiles.append(w)
            return w
        if k in KPI_KINDS:
            target, tip = KPI_INFO[k]
            if tile.kpi_chart == "gauge":
                _t, unit, (low, high), (vmin, vmax), dec = KPIS[k]
                w = GaugeCard(target, title, Gauge(low, high, vmin=vmin, vmax=vmax, unit=unit, decimals=dec,
                                                   needle=False), tip)
                self.cards.setdefault(k, w)  # el primero de cada clave (vista rápida y pruebas)
            elif tile.kpi_chart == "value":
                w = KpiValueTile(tile, tr(title), target)
            else:
                w = KpiTrendTile(tile, tr(title), target, self.engine)
            w.clicked.connect(self.navigate.emit)
            self.kpi_widgets.setdefault(k, []).append(w)
            return w
        fr, lay = make_card(title)
        if k == "machine":
            self.lbl_state = QLabel("—")
            self.lbl_state.setTextFormat(Qt.RichText)
            self.lbl_state.setAlignment(Qt.AlignTop | Qt.AlignLeft)
            self.lbl_state.setWordWrap(True)
            lay.addWidget(self.lbl_state, 1)
        elif k == "alarms":
            self.lst_alarms = QListWidget()
            self.lst_alarms.setStyleSheet("QListWidget { border: none; }")
            self.lst_alarms.itemDoubleClicked.connect(lambda _: self.navigate.emit("events"))
            lay.addWidget(self.lst_alarms, 1)
        elif k == "cpk_bars":
            self.bars = BarList(1.0, 1.33, 2.0)
            lay.addWidget(self.bars, 1)
        elif k == "shift":
            self.strip = StateStrip()
            lay.addWidget(self.strip)
            legend = QLabel(" ".join(
                f"<span style='color:{STATE_COLORS[s]}'>■</span> {tr(STATE_LABELS[s])}&nbsp;&nbsp;" for s in STATE_COLORS))
            legend.setStyleSheet(f"color:{theme.c('muted')};")
            lay.addWidget(legend)
            fr.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
        return fr

    def _set(self, key: str, value, sub: str) -> None:
        for w in self.kpi_widgets.get(key, ()):
            w.set(value, sub)

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
            self._set("cpk", worst[1], worst[2])
        else:
            self._set("cpk", None, "Sin límites o sin datos suficientes")
        if self.bars is not None:
            self.bars.set_rows([(label, v) for _, v, label in cpks[:6]])
        # Conformidad actual
        checked = [st for st in snap.statuses.values() if st.fresh and st.level is not None
                   and (st.bounds.any or st.expected)]
        if checked:
            ok = sum(st.level < Level.WARN for st in checked)
            self._set("conform", 100.0 * ok / len(checked), tr("{ok} de {n} variables", ok=ok, n=len(checked)))
        else:
            self._set("conform", None, "Sin receta o sin límites")
        # Calidad de lectura
        if snap.read_total:
            self._set("read", 100.0 * snap.read_ok / snap.read_total,
                      tr("{ok} de {n} leídas", ok=snap.read_ok, n=snap.read_total) +
                      (f" · {snap.error}" if snap.error else ""))
        else:
            self._set("read", None, snap.error or "Sin variables visibles")
        self._stability(snap.ts)
        self._alarms(snap)
        for tile in self.var_tiles:
            tile.update_snapshot(snap)

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
            self._set("stability", worst[0], sub)
        elif mons.store.models:
            self._set("stability", None, "Sin datos frescos de los modelos")
        else:
            self._set("stability", None, "Entrena un comportamiento (menú Entrenamiento)")

    def _alarms(self, snap: Snapshot) -> None:
        if self.lst_alarms is None:
            return
        self.lst_alarms.clear()
        findings = sorted(snap.findings, key=lambda f: (-int(f.level), f.since))
        for f in findings[:30]:
            if f.level < Level.WARN:
                continue
            it = QListWidgetItem(f"{time.strftime('%H:%M', time.localtime(f.since))}  {f.message}")
            it.setForeground(level_color(f.level))
            self.lst_alarms.addItem(it)
        if not self.lst_alarms.count():
            it = QListWidgetItem(tr("✔ Sin alarmas ni avisos activos"))
            it.setForeground(QColor(theme.c("good_text")))
            self.lst_alarms.addItem(it)

    # --- OEE e índice 5.0 (historial, cada 10 s) ------------------------------------------
    def refresh_oee(self, force: bool = False) -> None:
        if not force and not self.isVisible():
            return
        eng = self.engine
        o = eng.config.oee
        speed_var = eng.config.variable(o.speed_var) if o.speed_var else None
        if not (o.enabled and speed_var and eng.historian):
            for k in ("oee", "availability", "performance", "quality", "i5"):
                self._set(k, None, "Configura el OEE (Configuración → KPI / OEE)")
            if self.lbl_state is not None:
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

        self._set("oee", None if res.oee is None else 100 * res.oee,
                  f"D {pc(res.availability)} · R {pc(res.performance)} · C {pc(res.quality)}")
        u = o.length_unit
        for k, sub in (("availability", tr("detenido {d}", d=fmt_duration(res.stop_s))),
                       ("performance", tr("{v} de {n} promedio", v="—" if res.avg_speed is None else f"{res.avg_speed:.4g}",
                                          n="—" if res.avg_nominal is None else f"{res.avg_nominal:.4g}")),
                       ("quality", tr("{g} de {t} conformes", g=f"{res.length_good:,.0f} {u}",
                                      t=f"{res.length_total:,.0f} {u}"))):
            v = getattr(res, k)
            self._set(k, None if v is None else 100 * v, sub)
        hf = human_factors(eng.historian.events_between(a, now), res)
        self._set("i5", hf.index, tr("{a} alarmas/h · normal {p}", a=f"{hf.alarms_per_hour:.1f}",
                                     p="—" if res.normal_pct is None else f"{res.normal_pct:.0f} %"))
        if self.strip is not None:
            self.strip.set_data(res.intervals, a, now)
        if self.lbl_state is not None:
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
            lines.append(f"<span style='font-size:22px; color:{color}'><b>● {tr(STATE_LABELS[cur.state])}</b></span>"
                         "&nbsp;&nbsp;" + tr("desde hace {d}", d=fmt_duration(cur.duration)))
        elif not eng.running:
            lines.append(f"<span style='font-size:22px; color:{theme.c('muted')}'>"
                         f"<b>{tr('● Monitoreo detenido')}</b></span>")
        if snap is not None and o.speed_var:
            st = snap.statuses.get(o.speed_var)
            if st is not None and st.reading.value is not None:
                nominal = f" / {res.avg_nominal:.4g}" if res is not None and res.avg_nominal else ""
                lines.append(tr("Velocidad: <b>{v}</b>{nom} {u}", v=f"{st.reading.value:g}", nom=nominal,
                                u=st.var.unit))
        lines.append(tr("Receta: <b>{r}</b>", r=eng.state.recipe or "—"))
        if res is not None:
            u = o.length_unit
            lines.append(tr("Producido en el turno: <b>{t}</b> (conforme {g})", t=f"{res.length_total:,.0f} {u}",
                            g=f"{res.length_good:,.0f} {u}"))
            lines.append(tr("Paros: <b>{s}</b> · microparos: <b>{m}</b> · detenido {d}", s=res.n_stops,
                            m=res.n_microstops, d=fmt_duration(res.stop_s)))
        if snap is not None:
            n_alarm = sum(f.level >= Level.ALARM for f in snap.findings)
            n_warn = sum(f.level == Level.WARN for f in snap.findings)
            lines.append(tr("Hallazgos: <b style='color:{ca}'>{a} alarmas</b> · <b style='color:{cw}'>{w} avisos</b>",
                            ca=theme.c("critical"), a=n_alarm, cw=theme.c("warning_text"), w=n_warn))
        return "<br>".join(lines)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        QTimer.singleShot(0, lambda: self.refresh_oee(force=True))
        if self.engine.last is not None:
            QTimer.singleShot(0, lambda: self.update_snapshot(self.engine.last, force=True))
