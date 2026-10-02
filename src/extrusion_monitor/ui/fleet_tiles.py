"""Tarjeta de una línea en el dashboard global y sus indicadores (1 a 5, configurables).

Los indicadores se pintan directamente (sin pyqtgraph): con 100 líneas y 5 indicadores cada una son
500 elementos, y así la ventana sigue ligera.
"""
from __future__ import annotations

import time
from typing import Optional

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QFrame, QGridLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget

from ..analysis.kpis import KPIS
from ..analysis.oee import STATE_LABELS
from ..fleet import FleetTile, LineState, find_var
from ..i18n import tr
from ..recipes import Bounds
from . import theme
from .home_tiles import LinearBar, ProcessGauge, auto_scale, zone
from .kpi_dashboard import Gauge

STATE_KEYS = {"running": "good", "assumed": "good_soft", "slow": "warning", "microstop": "serious",
              "stopped": "critical", "unknown": "neutral"}
CONN_TEXT = {"online": "En línea", "stale": "Retrasada", "offline": "Sin comunicación", "closed": "Programa cerrado"}
LEVEL_KEYS = {"ALARM": "critical", "WARN": "warning", "OK": "good", "INFO": "info"}
TILE_W = 128  # ancho de referencia de una columna de la tarjeta (escala 1)
TILE_MIN_W, TILE_MAX_W = 92, 190  # las tarjetas se reparten el ancho de la ventana dentro de estos límites
CARD_PAD = 20


def card_metrics(viewport_w: int, columns: int, spacing: int = 10, count: int = 0) -> tuple[int, int]:
    """Tarjetas por fila y ancho de cada una: llenan el ancho disponible sin dejar huecos.

    Con muchas columnas por tarjeta (o una ventana angosta) cabe una sola y sus indicadores se encogen.
    Con pocas líneas (`count`) en una pantalla ancha, las tarjetas crecen hasta su tamaño máximo.
    """
    min_card = columns * TILE_MIN_W + CARD_PAD
    n = max(1, (viewport_w + spacing) // (min_card + spacing))
    if count:
        n = min(n, count)
    card_w = (viewport_w - spacing * (n - 1)) // n
    return n, max(120, min(card_w, columns * TILE_MAX_W + CARD_PAD))


DEFAULT_SHIFT_S = 8 * 3600


def fmt_age(s: Optional[float]) -> str:
    if s is None:
        return "—"
    if s < 90:
        return tr("hace {n} s", n=int(s))
    if s < 5400:
        return tr("hace {n} min", n=int(s / 60))
    if s < 172800:
        return tr("hace {n} h", n=int(s / 3600))
    return tr("hace {n} días", n=int(s / 86400))


def fmt_dur(s: float) -> str:
    s = int(s)
    return f"{s // 3600}:{s % 3600 // 60:02d} h" if s >= 3600 else f"{s // 60} min"


def pct(v) -> str:
    return "—" if v is None else f"{v:.0f} %"


def var_text(v: dict) -> str:
    if v.get("kind") in ("text", "selector"):
        return v.get("text") or "—"
    x = v.get("value")
    if x is None:
        return "—"
    d = v.get("decimals")
    return f"{x:.{d}f}" if isinstance(d, int) else f"{x:.4g}"


def bounds_of(v: dict) -> Bounds:
    lim = (v.get("limits") or [None] * 4) + [None] * 4
    return Bounds(*lim[:4])


def kpi_bounds(key: str) -> Bounds:
    """Indicador «mayor es mejor»: rojo bajo el primer umbral, amarillo hasta el segundo."""
    low, high = KPIS[key][2]
    return Bounds(al=low, wl=high)


def period_since(tile: FleetTile, status: dict, now: float) -> float:
    if tile.range_s > 0:
        return now - tile.range_s
    start = (status.get("oee") or {}).get("shift_start")
    return start if start else now - DEFAULT_SHIFT_S


def trend_key(tile: FleetTile, status: dict) -> Optional[tuple[str, str]]:
    if tile.chart != "trend":
        return None
    if tile.kind == "kpi":
        return ("k", tile.kpi)
    if tile.kind == "var":
        v = find_var(status, tile.var)
        return ("v", v["id"]) if v else ("v", tile.var)
    return None


def tile_title(tile: FleetTile) -> str:
    if tile.title:
        return tile.title
    if tile.kind == "kpi":
        return tr(KPIS.get(tile.kpi, (tile.kpi,))[0])
    if tile.kind == "var":
        return tile.var or tr("Variable")
    return tr({"production": "Producción del turno", "alarms": "Alarmas activas"}[tile.kind])


class MiniTrend(QWidget):
    """Gráfica de tiempo pintada: línea, límites (o umbrales) y escala mínima."""

    def __init__(self):
        super().__init__()
        self.t: list = []
        self.y: list = []
        self.a = self.b = 0.0
        self.bounds = Bounds()
        self.color_key = "measure"
        self.decimals: Optional[int] = None
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMinimumHeight(40)

    def set_data(self, t, y, a: float, b: float, bounds: Bounds, color_key: str, decimals: Optional[int]) -> None:
        self.t, self.y, self.a, self.b, self.bounds = t, y, a, b, bounds
        self.color_key, self.decimals = color_key, decimals
        self.update()

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        lab = 12
        top, bot, left, right = 2.0, h - lab, 30.0, w - 2.0
        p.fillRect(QRectF(left, top, right - left, bot - top), QColor(theme.c("plot_bg")))
        f = QFont(self.font())
        f.setPointSizeF(7.5)
        p.setFont(f)
        p.setPen(QColor(theme.c("muted")))
        if not self.y:
            p.drawText(QRectF(left, top, right - left, bot - top), Qt.AlignCenter, tr("Sin datos aún"))
            p.end()
            return
        lims = [v for v in self.bounds if v is not None]
        lo, hi = min(self.y + lims), max(self.y + lims)
        pad = (hi - lo) * 0.08 or max(abs(hi) * 0.05, 1.0)
        lo, hi = lo - pad, hi + pad
        span_t = (self.b - self.a) or 1.0

        def xy(t, v):
            return QPointF(left + (right - left) * (t - self.a) / span_t, bot - (bot - top) * (v - lo) / (hi - lo))

        for val, key in ((self.bounds.al, "critical"), (self.bounds.ah, "critical"), (self.bounds.wl, "warning"),
                         (self.bounds.wh, "warning")):
            if val is not None and lo <= val <= hi:
                p.setPen(QPen(QColor(theme.c(key)), 1, Qt.DashLine))
                p.drawLine(xy(self.a, val), xy(self.b, val))
        path = QPainterPath()
        for i, (t, v) in enumerate(zip(self.t, self.y)):
            (path.moveTo if i == 0 else path.lineTo)(xy(max(t, self.a), v))
        p.setPen(QPen(QColor(theme.c(self.color_key)), 2))
        p.drawPath(path)
        p.setPen(QColor(theme.c("muted")))
        fmt = (lambda v: f"{v:.{self.decimals}f}") if isinstance(self.decimals, int) else (lambda v: f"{v:.3g}")
        p.drawText(QRectF(0, top - 2, left - 3, 12), Qt.AlignRight, fmt(hi - pad))
        p.drawText(QRectF(0, bot - 10, left - 3, 12), Qt.AlignRight, fmt(lo + pad))
        p.drawText(QRectF(left, bot, 60, lab), Qt.AlignLeft, time.strftime("%H:%M", time.localtime(self.a)))
        p.drawText(QRectF(right - 60, bot, 60, lab), Qt.AlignRight, time.strftime("%H:%M", time.localtime(self.b)))
        p.end()


class FleetTileWidget(QFrame):
    """Un indicador dentro de la tarjeta de la línea."""

    def __init__(self, tile: FleetTile):
        super().__init__()
        self.tile = tile
        self.setObjectName("fleetTile")
        self.setStyleSheet(f"#fleetTile {{ background:{theme.c('surface2')}; border-radius:6px; }}")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(5, 3, 5, 3)
        lay.setSpacing(1)
        self.lbl_title = QLabel()
        self.scale = 1.0  # tamaño relativo de textos (según el ancho real de la columna)
        # El ancho lo decide la cuadrícula de la tarjeta (columnas iguales), no el contenido.
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.lbl_title.setStyleSheet(f"color:{theme.c('text2')}; font-size:11px;")
        lay.addWidget(self.lbl_title)
        self.body: Optional[QWidget] = None
        self.lbl = QLabel()
        self.lbl.setTextFormat(Qt.RichText)
        self.lbl.setAlignment(Qt.AlignCenter)
        self.lbl.setWordWrap(True)
        k, c = tile.kind, tile.chart
        if k in ("production", "alarms") or c == "value":
            lay.addWidget(self.lbl, 1)
            if k == "alarms":
                self.lbl.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        else:
            if c == "gauge":
                self.body = Gauge(needle=False) if k == "kpi" else ProcessGauge()
                self.body.setMinimumSize(60, 50)
            elif c == "bar":
                self.body = LinearBar()
            else:
                self.body = MiniTrend()
            self.body.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Ignored)
            lay.addWidget(self.body, 1)
            if c in ("bar", "trend"):
                lay.addWidget(self.lbl)

    def _px(self, base: float) -> int:
        return max(11, int(base * self.scale))

    def set_scale(self, scale: float) -> None:
        self.scale = scale
        self.lbl_title.setStyleSheet(f"color:{theme.c('text2')}; font-size:{max(9, min(13, int(11 * scale)))}px;")

    def update_line(self, line: LineState, now: float) -> None:
        st = line.status
        t = self.tile
        self.lbl_title.setText(tile_title(t))
        if t.kind == "kpi":
            self._kpi(line, st, now)
        elif t.kind == "var":
            self._var(line, st, now)
        elif t.kind == "production":
            o = st.get("oee") or {}
            if not o:
                self.lbl.setText(f"<span style='color:{theme.c('muted')}'>{tr('OEE sin configurar')}</span>")
                return
            u = o.get("unit", "m")
            size = self._px(18 + 4 * (t.height - 1))
            total, good = o.get("length_total") or 0, o.get("length_good") or 0
            detail = tr("conforme {g} · paros {s}", g=f"{good:,.0f}", s=o.get("n_stops", 0))
            self.lbl.setText(f"<span style='font-size:{size}px'><b>{total:,.0f}</b></span> {u}<br>"
                             f"<span style='font-size:11px; color:{theme.c('text2')}'>{detail}</span>")
        else:
            al = st.get("alarms") or []
            if not al:
                self.lbl.setText(f"<span style='color:{theme.c('good_text')}'>{tr('✔ Sin alarmas')}</span>")
                return
            rows = [f"<span style='color:{theme.c(LEVEL_KEYS.get(a.get('level'), 'neutral'))}'>●</span> "
                    f"{a.get('msg', '')[:80]}" for a in al[:2 * t.height]]
            self.lbl.setText("<span style='font-size:11px'>" + "<br>".join(rows) + "</span>")

    def _kpi(self, line: LineState, st: dict, now: float) -> None:
        t = self.tile
        key = t.kpi if t.kpi in KPIS else "oee"
        title, unit, (low, high), (vmin, vmax), dec = KPIS[key]
        v = (st.get("kpis") or {}).get(key)
        color = "neutral" if v is None else ("critical" if v < low else ("warning" if v < high else "good"))
        text = "—" if v is None else f"{v:.{dec}f}"
        if t.chart == "value":
            size = self._px(26 + 8 * (t.height - 1))
            self.lbl.setText(f"<span style='font-size:{size}px; color:{theme.c(color if v is not None else 'text')}'>"
                             f"<b>{text}</b></span> <span style='color:{theme.c('muted')}'>{unit}</span>")
        elif t.chart == "gauge":
            g = self.body
            g.low, g.high, g.vmin, g.vmax, g.unit, g.decimals = low, high, vmin, vmax, unit, dec
            g.set_value(v)
        elif t.chart == "bar":
            self.body.set_data(v, vmin, vmax, kpi_bounds(key), None, color)
            self.lbl.setText(f"<b style='color:{theme.c(color)}'>{text}</b> {unit}")
        else:
            series = line.series.get(("k", key), ([], []))
            a = period_since(t, st, now)
            self.body.set_data(series[0], series[1], a, now, kpi_bounds(key), "measure", dec)
            self.lbl.setText(f"<span style='font-size:11px'>{tr('Ahora')}: "
                             f"<b style='color:{theme.c(color)}'>{text}</b> {unit}</span>")

    def _var(self, line: LineState, st: dict, now: float) -> None:
        t = self.tile
        v = find_var(st, t.var)
        if not t.title:
            self.lbl_title.setText(f"{v['name']} ({v['unit']})" if v and v.get("unit") else (v or {}).get("name", t.var))
        if v is None:
            self.lbl.setText(f"<span style='color:{theme.c('muted')}'>{tr('No existe en esta línea')}</span>")
            if self.body is not None:
                self.body.hide()
            return
        if self.body is not None:
            self.body.show()
        b = bounds_of(v)
        x = v.get("value")
        lvl = v.get("level")
        color = LEVEL_KEYS.get(lvl) if lvl in ("ALARM", "WARN") else (zone(x, b) if x is not None else "neutral")
        if v.get("kind") in ("text", "selector") or t.chart == "value":
            if v.get("kind") in ("text", "selector") and v.get("expected"):
                color = "good" if v.get("text") == v.get("expected") else "critical"
            size = self._px(24 + 8 * (t.height - 1))
            c = theme.c(color) if color not in ("neutral", None) else theme.c("text")
            ref = v.get("ref")
            self.lbl.setText(f"<span style='font-size:{size}px; color:{c}'><b>{var_text(v)}</b></span> "
                             f"<span style='color:{theme.c('muted')}'>{v.get('unit') or ''}</span>"
                             + (f"<br><span style='font-size:10px; color:{theme.c('muted')}'>Ref {ref:.4g}</span>"
                                if ref is not None else ""))
            if self.body is not None:
                self.body.hide()
            return
        if t.chart in ("gauge", "bar"):
            lo, hi = auto_scale(b, v.get("ref"), [x] if x is not None else None)
            if t.chart == "gauge":
                self.body.set_data(x, lo, hi, b, v.get("ref"), var_text(v), v.get("unit") or "", color)
            else:
                self.body.set_data(x, lo, hi, b, v.get("ref"), color)
                self.lbl.setText(f"<b style='color:{theme.c(color) if color != 'neutral' else theme.c('text')}'>"
                                 f"{var_text(v)}</b> {v.get('unit') or ''}")
        else:
            series = line.series.get(("v", v["id"]), ([], []))
            a = period_since(t, st, now)
            self.body.set_data(series[0], series[1], a, now, b, "measure", v.get("decimals"))
            self.lbl.setText(f"<span style='font-size:11px'>{tr('Ahora')}: <b>{var_text(v)}</b> "
                             f"{v.get('unit') or ''}</span>")


class LineCard(QFrame):
    """Tarjeta de una línea: encabezado (estado), 1 a 5 indicadores y pie (antigüedad del dato)."""

    clicked = Signal(str)

    def __init__(self, line_id: str, tiles: list[FleetTile], columns: int):
        super().__init__()
        self.line_id = line_id
        self.setObjectName("card")
        self.columns = columns
        self.rows = 0
        self.grid: Optional[QGridLayout] = None
        self.setCursor(Qt.PointingHandCursor)
        self.selected = False
        self.blinking = False
        self._blink_on = False
        self._style = ""
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 6, 8, 6)
        lay.setSpacing(4)
        self.lbl_head = QLabel()
        self.lbl_head.setTextFormat(Qt.RichText)
        self.lbl_head.setWordWrap(True)
        lay.addWidget(self.lbl_head)
        grid = QGridLayout()
        grid.setSpacing(4)
        from .home_page import pack_tiles
        self.tiles = [FleetTileWidget(t) for t in tiles]
        rows = 0
        for w, (r, c, h, wd) in zip(self.tiles, pack_tiles(tiles, columns)):
            grid.addWidget(w, r, c, h, wd)
            rows = max(rows, r + h)
        self.rows, self.grid = rows, grid
        self._card_w = 0
        self.set_width(columns * TILE_W + CARD_PAD)
        for c in range(columns):
            grid.setColumnStretch(c, 1)
        lay.addLayout(grid)
        self.lbl_foot = QLabel()
        self.lbl_foot.setStyleSheet(f"color:{theme.c('muted')}; font-size:10px;")
        lay.addWidget(self.lbl_foot)

    def set_width(self, card_w: int) -> None:
        """Ancho de la tarjeta: las columnas se lo reparten y los indicadores (alto y textos) se escalan."""
        if card_w == self._card_w:
            return
        self._card_w = card_w
        self.setFixedWidth(card_w)
        tile_w = (card_w - CARD_PAD) / self.columns
        row_h = int(max(60, min(150, tile_w * 0.75)))
        for r in range(self.rows):
            self.grid.setRowMinimumHeight(r, row_h)
        scale = max(0.6, min(1.5, tile_w / TILE_W))
        for w in self.tiles:
            w.set_scale(scale)

    def update_line(self, line: LineState, now: float, offline_s: float, area: str) -> None:
        st = line.status
        conn = line.connection(now, offline_s)
        dot = theme.c({"online": "good", "stale": "warning"}.get(conn, "neutral"))
        machine = st.get("machine") or {}
        if conn in ("offline", "closed"):
            state = f"<span style='color:{theme.c('muted')}'><b>{tr(CONN_TEXT[conn])}</b></span>"
        elif machine.get("state"):
            since = machine.get("since")
            state = (f"<b style='color:{theme.c(STATE_KEYS.get(machine['state'], 'neutral'))}'>"
                     f"{tr(STATE_LABELS.get(machine['state'], ''))}</b>"
                     + (f" <span style='color:{theme.c('muted')}'>{fmt_dur(now - since)}</span>" if since else ""))
        else:
            state = f"<b>{tr('Monitoreando') if st.get('monitoring') else tr('Monitoreo detenido')}</b>"
        na, nw = st.get("n_alarms") or 0, st.get("n_warnings") or 0
        badge = ""
        if na:
            badge = f" <b style='color:{theme.c('critical')}'>▲ {na}</b>"
        elif nw:
            badge = f" <b style='color:{theme.c('warning_text')}'>▲ {nw}</b>"
        self.lbl_head.setText(
            f"<span style='color:{dot}'>●</span> <span style='font-size:14px; color:{theme.c('title')}'>"
            f"<b>{line.name}</b></span>{badge}<br><span style='font-size:13px'>{state}</span> "
            f"<span style='color:{theme.c('text2')}; font-size:11px'>· {st.get('recipe') or '—'}</span>")
        for w in self.tiles:
            w.update_line(line, now)
        self.lbl_foot.setText(tr("Actualizado {a}", a=fmt_age(line.age(now))) + (f" · {area}" if area else ""))
        self.setToolTip(f"{line.line_id}\n{line.path}")
        self._sev = severity(line, now, offline_s)
        self._paint_border()

    def _paint_border(self) -> None:
        sev = getattr(self, "_sev", 1)
        key = {4: "critical", 3: "critical", 2: "warning", 1: "good", 0: "neutral"}[sev]
        width = 3 if self.selected else 2
        if self.blinking and self._blink_on:
            style = f"#card {{ border: 4px solid {theme.c('critical')}; border-radius: 8px; " \
                    f"background:{theme.c('critical')}; }}"
        else:
            style = f"#card {{ border: {width}px solid {theme.c(key)}; border-radius: 8px; }}"
        if style != self._style:  # recalcular estilos de 100 tarjetas es costoso
            self._style = style
            self.setStyleSheet(style)

    def blink_tick(self) -> None:
        if self.blinking:
            self._blink_on = not self._blink_on
            self._paint_border()

    def acknowledge(self) -> None:
        self.blinking = False
        self._blink_on = False
        self._paint_border()

    def mousePressEvent(self, event) -> None:
        self.acknowledge()
        self.clicked.emit(self.line_id)
        super().mousePressEvent(event)


def severity(line: LineState, now: float, offline_s: float = 30.0) -> int:
    """0 = sin comunicación · 1 = normal · 2 = aviso · 3 = detenida · 4 = alarma (para ordenar y colorear)."""
    conn = line.connection(now, offline_s)
    st = line.status
    if conn in ("offline", "closed"):
        return 0
    if st.get("n_alarms"):
        return 4
    if (st.get("machine") or {}).get("state") in ("stopped", "microstop"):
        return 3
    if st.get("n_warnings"):
        return 2
    return 1


def blink_timer(parent, cards_fn) -> QTimer:
    timer = QTimer(parent)
    timer.timeout.connect(lambda: [c.blink_tick() for c in cards_fn() if c.blinking])
    timer.start(600)
    return timer
