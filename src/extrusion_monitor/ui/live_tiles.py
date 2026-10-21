"""Variables en vivo: mosaicos por variable (como los del Inicio) o la tabla de siempre.

Cada mosaico muestra estado, valor y unidad, tolerancia, referencia y calidad de la lectura, con el gráfico
elegido para esa variable (valor con tendencia corta, gauge, barra con límites, gráfica de tiempo o histograma).
Clic derecho: cambiar el gráfico, el tamaño o el tiempo mostrado. Doble clic: graficar en Tendencias.
Las elecciones se guardan solas (preferencias de vista).
"""
from __future__ import annotations

import time
from typing import Callable, Optional

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QAction, QActionGroup
from PySide6.QtWidgets import (
    QButtonGroup, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QMenu, QPushButton, QScrollArea,
    QStackedWidget, QVBoxLayout, QWidget,
)

from ..analysis.rules import Level
from ..config import AppConfig, HomeTile
from ..engine import Snapshot
from ..i18n import tr
from . import theme
from .common import SeriesCache, level_color, level_text
from .home_tiles import CHART_LABELS, VarTile, charts_for, fmt
from .search import normalize

TILE_MIN_W = 250
ROW_H = 190
PLOT_EXTRA_H = 70
RANGES = [("5 min", 300), ("15 min", 900), ("1 h", 3600), ("Turno actual", 0)]
SIZES = [("Normal (1 × 1)", 1, 1), ("Ancho (2 × 1)", 2, 1), ("Grande (2 × 2)", 2, 2)]


def default_chart(var) -> str:
    return "value" if not var.numeric else ("bar" if (var.measured and var.trend) else "value")


class LiveTile(VarTile):
    """Mosaico de una variable con su estado, tolerancia y calidad de lectura."""

    customize = Signal(object)  # el mosaico (menú contextual)
    open_trend = Signal(str)

    def __init__(self, tile: HomeTile, config: AppConfig, series: SeriesCache,
                 quality: Optional[Callable[[str], Optional[float]]] = None):
        super().__init__(tile, config, series)
        self.quality = quality
        self.setCursor(Qt.ArrowCursor)
        self.setToolTip(tr("Clic derecho: gráfico, tamaño y tiempo · doble clic: graficar en Tendencias"))
        head = QHBoxLayout()
        head.setContentsMargins(0, 0, 0, 0)
        self.pill = QLabel("")
        self.pill.setObjectName("statusPill")
        head.addStretch(1)
        head.addWidget(self.pill)
        self.lay.insertLayout(1, head)
        self.lbl_tol = QLabel("")
        self.lbl_tol.setAlignment(Qt.AlignCenter)
        self.lbl_tol.setWordWrap(True)
        self.lbl_tol.setStyleSheet(f"color:{theme.c('text2')}; font-size:11px;")
        self.lay.addWidget(self.lbl_tol)

    @property
    def vid(self) -> str:
        return self.tile.var_ids[0] if self.tile.var_ids else ""

    def update_snapshot(self, snap: Snapshot) -> None:
        super().update_snapshot(snap)
        st = snap.statuses.get(self.vid)
        if st is None:
            self.pill.setText("")
            self.lbl_tol.setText(tr("sin lectura"))
            return
        lvl = st.level
        if not st.fresh:
            text, color = tr("DATO VIEJO"), theme.c("neutral")
        elif lvl is None:
            text, color = tr("SIN LÍMITES"), theme.c("neutral")
        else:
            text, color = level_text(lvl), level_color(lvl).name()
        self.pill.setText(text)
        self.pill.setStyleSheet(f"background:{color}; color:#ffffff; border-radius:8px; padding:1px 8px;"
                                "font-size:10px; font-weight:bold;")
        parts = []
        b = st.bounds
        var = st.var
        if b.al is not None or b.ah is not None:
            parts.append(tr("Tolerancia {lo} … {hi}", lo="—" if b.al is None else fmt(b.al, var),
                            hi="—" if b.ah is None else fmt(b.ah, var)))
        elif b.wl is not None or b.wh is not None:
            parts.append(tr("Aviso {lo} … {hi}", lo="—" if b.wl is None else fmt(b.wl, var),
                            hi="—" if b.wh is None else fmt(b.wh, var)))
        q = self.quality(self.vid) if self.quality else None
        if st.reading.ok:
            read = tr("lectura OK")
        elif not st.reading.visible:
            read = tr("pantalla no visible ahora")  # se lee al pasar el recorrido por su pantalla
        else:
            read = tr("lectura con falla")
        if q is not None:
            read += f" ({q:.0f} %)"  # % de lecturas exitosas recientes
        if st.reading.ts:
            read += " · " + time.strftime("%H:%M:%S", time.localtime(st.reading.ts))
        parts.append(read)
        self.lbl_tol.setText(" · ".join(parts))

    def contextMenuEvent(self, event) -> None:
        self.customize.emit(self)

    def mousePressEvent(self, event) -> None:  # sin navegación con un clic (sí con doble clic)
        QFrame.mousePressEvent(self, event)

    def mouseDoubleClickEvent(self, event) -> None:
        if self.vid:
            self.open_trend.emit(self.vid)


class LiveTilesView(QWidget):
    """Cuadrícula de mosaicos agrupados por pantalla del HMI, con filtro."""

    changed = Signal(dict)  # elecciones por variable (para guardarlas)
    open_trend = Signal(str)

    def __init__(self, series: SeriesCache, quality=None, allow=None):
        super().__init__()
        self.series = series
        self.quality = quality
        self.allow = allow or (lambda _key: True)
        self.config: Optional[AppConfig] = None
        self.prefs: dict[str, dict] = {}
        self.tiles: list[LiveTile] = []
        self._last = 0.0
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.filter = QLineEdit()
        self.filter.setPlaceholderText(tr("Filtrar variables…"))
        self.filter.setClearButtonEnabled(True)
        self.filter.setFocusPolicy(Qt.ClickFocus)
        self.filter.textChanged.connect(lambda _: self._place())
        lay.addWidget(self.filter)
        self.area = QScrollArea()
        self.area.setWidgetResizable(True)
        self.area.setFrameShape(QFrame.NoFrame)
        self.inner = QWidget()
        self.inner.setObjectName("content")
        self.grid = QGridLayout(self.inner)
        self.grid.setContentsMargins(0, 0, 4, 0)
        self.grid.setSpacing(10)
        self.area.setWidget(self.inner)
        lay.addWidget(self.area, 1)
        self._cols = 0
        self._resize = QTimer(self)
        self._resize.setSingleShot(True)
        self._resize.setInterval(120)
        self._resize.timeout.connect(self._maybe_reflow)

    # --- construcción -------------------------------------------------------------------
    def rebuild(self, config: AppConfig, prefs: Optional[dict] = None) -> None:
        self.config = config
        if prefs is not None:
            self.prefs = {k: dict(v) for k, v in prefs.items() if isinstance(v, dict)}
        for t in self.tiles:
            t.setParent(None)
            t.deleteLater()
        self.tiles = []
        linked = {v.setpoint_var for v in config.variables if v.setpoint_var}
        for v in config.variables:
            if v.id in linked:
                continue  # la consigna se muestra como referencia de su medición
            p = self.prefs.get(v.id, {})
            chart = p.get("chart") if p.get("chart") in charts_for(v) else default_chart(v)
            tile = HomeTile(id=f"live_{v.id}", kind="var", var_ids=[v.id], chart=chart,
                            width=int(p.get("w", 1)), height=int(p.get("h", 1)),
                            range_s=float(p.get("range", 900)))
            w = LiveTile(tile, config, self.series, self.quality)
            w.customize.connect(self._menu)
            w.open_trend.connect(self.open_trend.emit)
            self.tiles.append(w)
        self._cols = 0
        self._place()

    def _columns(self) -> int:
        return max(1, (self.area.viewport().width() - 4) // TILE_MIN_W)

    def _maybe_reflow(self) -> None:
        if self._columns() != self._cols:
            self._place()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._resize.start()

    def _place(self) -> None:
        while self.grid.count():
            item = self.grid.takeAt(0)
            w = item.widget()
            if w is not None and not isinstance(w, LiveTile):
                w.deleteLater()
            elif w is not None:
                w.hide()
        if self.config is None:
            return
        cols = self._cols = self._columns()
        q = normalize(self.filter.text())
        row = 0
        order = {p.id: i for i, p in enumerate(self.config.pages)}
        groups: dict[str, list[LiveTile]] = {}
        for t in sorted(self.tiles, key=lambda t: order.get(getattr(self.config.variable(t.vid), "page", None),
                                                            len(order))):
            v = self.config.variable(t.vid)
            if v is None:
                continue
            label = self.config.page_label(v.page) or tr("Sin pantalla")
            if q and q not in normalize(f"{self.config.var_label(v)} {v.id} {v.unit}"):
                continue
            groups.setdefault(label, []).append(t)
        for label, tiles in groups.items():
            head = QLabel(f"<b style='color:{theme.c('title')}; font-size:14px'>{label}</b>")
            head.setContentsMargins(2, 8, 0, 0)
            self.grid.addWidget(head, row, 0, 1, cols)
            row += 1
            used: set[tuple[int, int]] = set()
            r0 = row
            for t in tiles:
                w, h = min(t.tile.width, cols), t.tile.height
                r = r0
                while True:
                    c = next((c for c in range(cols - w + 1)
                              if all((r + i, c + j) not in used for i in range(h) for j in range(w))), None)
                    if c is not None:
                        break
                    r += 1
                used |= {(r + i, c + j) for i in range(h) for j in range(w)}
                extra = 0 if t.chart in ("value", "bar") else PLOT_EXTRA_H  # gauge y gráficas necesitan más alto
                t.setMinimumHeight(ROW_H * h + 10 * (h - 1) + extra)
                self.grid.addWidget(t, r, c, h, w)
                t.show()
                row = max(row, r + h)
        for c in range(cols):
            self.grid.setColumnStretch(c, 1)
        self.grid.setRowStretch(row, 1)
        if self.isVisible() and self.series.engine.last is not None:
            self.update_snapshot(self.series.engine.last, force=True)

    # --- menú por mosaico ---------------------------------------------------------------
    def _menu(self, tile: LiveTile) -> None:
        from PySide6.QtGui import QCursor
        v = self.config.variable(tile.vid) if self.config else None
        if v is None:
            return
        m = QMenu(self)
        m.addSection(self.config.var_label(v))
        sub = m.addMenu(tr("Gráfico"))
        grp = QActionGroup(sub)
        for key in charts_for(v):
            act = QAction(tr(CHART_LABELS[key]), sub, checkable=True)
            act.setChecked(key == tile.tile.chart)
            act.triggered.connect(lambda _=False, k=key: self.set_pref(tile.vid, chart=k))
            grp.addAction(act)
            sub.addAction(act)
        sub = m.addMenu(tr("Tamaño"))
        for label, w, h in SIZES:
            act = sub.addAction(tr(label))
            act.setCheckable(True)
            act.setChecked((tile.tile.width, tile.tile.height) == (w, h))
            act.triggered.connect(lambda _=False, w=w, h=h: self.set_pref(tile.vid, w=w, h=h))
        if v.numeric:
            sub = m.addMenu(tr("Tiempo mostrado (gráfica e histograma)"))
            for label, secs in RANGES:
                act = sub.addAction(tr(label))
                act.setCheckable(True)
                act.setChecked(float(tile.tile.range_s) == float(secs))
                act.triggered.connect(lambda _=False, s=secs: self.set_pref(tile.vid, range=s))
        m.addSeparator()
        m.addAction(tr("📈 Graficar en Tendencias"), lambda: self.open_trend.emit(tile.vid))
        m.addAction(tr("Restablecer este mosaico"), lambda: self.set_pref(tile.vid, reset=True))
        m.exec(QCursor.pos())

    def set_pref(self, vid: str, reset: bool = False, **kw) -> None:
        if not self.allow("charts"):
            return
        if reset:
            self.prefs.pop(vid, None)
        else:
            self.prefs.setdefault(vid, {}).update(kw)
        self.rebuild(self.config)
        self.changed.emit(self.prefs)

    # --- datos --------------------------------------------------------------------------
    def update_snapshot(self, snap: Snapshot, force: bool = False) -> None:
        now = time.monotonic()
        if not force and now - self._last < 1.0:
            return
        self._last = now
        for t in self.tiles:
            if t.isVisible() and (force or not t.visibleRegion().isEmpty()):
                t.update_snapshot(snap)


class LivePage(QWidget):
    """Página «Variables en vivo»: mosaicos o tabla."""

    modeChanged = Signal(str)

    def __init__(self, table: QWidget, tiles: LiveTilesView):
        super().__init__()
        self.table, self.tiles = table, tiles
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        bar = QHBoxLayout()
        bar.addWidget(QLabel(tr("Vista:")))
        self.btns = QButtonGroup(self)
        self.btn_tiles = QPushButton(tr("▦ Mosaicos"))
        self.btn_table = QPushButton(tr("☰ Tabla"))
        for b in (self.btn_tiles, self.btn_table):
            b.setCheckable(True)
            b.setFocusPolicy(Qt.NoFocus)
            self.btns.addButton(b)
            bar.addWidget(b)
        bar.addSpacing(12)
        hint = QLabel(tr("Clic derecho en un mosaico: gráfico, tamaño y tiempo · doble clic: Tendencias"))
        hint.setStyleSheet(f"color:{theme.c('muted')};")
        bar.addWidget(hint)
        bar.addStretch(1)
        lay.addLayout(bar)
        self.stack = QStackedWidget()
        self.stack.addWidget(tiles)
        self.stack.addWidget(table)
        lay.addWidget(self.stack, 1)
        self.btn_tiles.clicked.connect(lambda: self.set_mode("tiles"))
        self.btn_table.clicked.connect(lambda: self.set_mode("table"))
        self.set_mode("tiles", emit=False)

    @property
    def mode(self) -> str:
        return "tiles" if self.stack.currentWidget() is self.tiles else "table"

    def set_mode(self, mode: str, emit: bool = True) -> None:
        tiles = mode != "table"
        self.stack.setCurrentWidget(self.tiles if tiles else self.table)
        self.btn_tiles.setChecked(tiles)
        self.btn_table.setChecked(not tiles)
        if emit:
            self.modeChanged.emit(self.mode)

    def update_snapshot(self, snap: Snapshot) -> None:
        self.table.update_snapshot(snap)  # liviana: siempre al día para cambiar de vista sin esperar
        if self.mode == "tiles":
            self.tiles.update_snapshot(snap)
