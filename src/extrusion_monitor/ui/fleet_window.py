"""Dashboard global: estado de todas las líneas a partir de la carpeta compartida.

Cada línea se muestra en una tarjeta con 1 a 5 indicadores configurables (plantilla común con excepciones
por línea), agrupadas por área. Avisa con sonido y parpadeo cuando una línea entra en alarma, se detiene o
pierde comunicación. Tiene modo TV (pantalla completa con páginas que rotan) y exportación a CSV.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Optional

import pyqtgraph as pg
from PySide6.QtCore import QSize, Qt, QTimer, QUrl
from PySide6.QtGui import QActionGroup, QBrush, QColor, QDesktopServices, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication, QComboBox, QFrame, QGridLayout, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
    QListWidget, QListWidgetItem, QMainWindow, QMenu, QMessageBox, QScrollArea, QSplitter, QTableWidget,
    QStackedWidget, QTableWidgetItem, QTabWidget, QToolButton, QVBoxLayout, QWidget,
)

from .. import version_label
from ..fleet import FleetReader, FleetSettings, load_fleet_settings, save_fleet_settings
from ..i18n import LANGS, lang as i18n_lang, tr, translate_text
from . import icons, theme
from .home_status import StatusTile
from .fleet_tiles import (CONN_TEXT, LEVEL_KEYS, LineCard, blink_timer, card_metrics, fmt_age, period_since, severity,
                          trend_key)

FILTERS = [("all", "Todas"), ("alarm", "Con alarma o aviso"), ("stopped", "Detenidas"),
           ("offline", "Sin comunicación")]
SORTS = [("name", "Nombre"), ("status", "Gravedad"), ("oee", "OEE (menor primero)")]
TREND_RANGES = [("1 h", 3600), ("8 h", 8 * 3600), ("24 h", 86400), ("7 días", 7 * 86400)]
NO_AREA = "Sin área"
HELP_URL = "https://github.com/LuisLegarda/Extrusion-AI-agent#dashboard-global-varias-líneas"


def natural(text: str) -> list:
    """Orden natural: «Línea 2» antes que «Línea 10»."""
    import re
    return [int(p) if p.isdigit() else p for p in re.split(r"(\d+)", text.lower())]


def pct(v) -> str:
    return "—" if v is None else f"{100 * v:.0f} %"


def fmt_val(v: dict) -> str:
    if v.get("kind") in ("text", "selector"):
        return v.get("text") or "—"
    x = v.get("value")
    if x is None:
        return "—"
    d = v.get("decimals")
    return f"{x:.{d}f}" if isinstance(d, int) else f"{x:.4g}"


class FleetTile(StatusTile):
    """Tarjeta de resumen con el estilo del monitor (ícono, valor y descripción)."""

    def __init__(self, key: str, icon: str, title: str, color_key: str):
        super().__init__(key, icon, title, "", color_key)
        self.setCursor(Qt.ArrowCursor)
        self.sub.hide()
        self.setFixedHeight(58)
        self._base = theme.c(color_key)

    @property
    def val(self) -> QLabel:
        return self.value

    def set(self, text: str, color: Optional[str] = None) -> None:  # noqa: D401 (misma firma que antes)
        super().set(text, "", color or self._base)


class LineDetail(QWidget):
    """Detalle de una línea: variables, alarmas, tendencia y eventos."""

    def __init__(self, reader: FleetReader):
        super().__init__()
        self.reader = reader
        self.line_id: Optional[str] = None
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.lbl = QLabel()
        self.lbl.setTextFormat(Qt.RichText)
        self.lbl.setWordWrap(True)
        lay.addWidget(self.lbl)
        self.tabs = QTabWidget()
        self.tbl = QTableWidget(0, 6)
        self.tbl.setHorizontalHeaderLabels(["Variable", "Valor", "Unidad", "Referencia", "Estado", "Cpk"])
        self.tbl.verticalHeader().setVisible(False)
        self.tbl.setEditTriggers(QTableWidget.NoEditTriggers)
        hdr = self.tbl.horizontalHeader()
        hdr.setSectionResizeMode(QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(0, QHeaderView.Stretch)
        self.tbl.cellDoubleClicked.connect(self._row_to_trend)
        self.tabs.addTab(self.tbl, "Variables")
        self.lst_alarms = QListWidget()
        self.tabs.addTab(self.lst_alarms, "Alarmas activas")
        trend = QWidget()
        tl = QVBoxLayout(trend)
        bar = QHBoxLayout()
        self.cmb_var = QComboBox()
        self.cmb_var.setMinimumWidth(220)
        self.cmb_var.currentIndexChanged.connect(self.refresh_trend)
        self.cmb_rng = QComboBox()
        for label, secs in TREND_RANGES:
            self.cmb_rng.addItem(label, secs)
        self.cmb_rng.setCurrentIndex(1)
        self.cmb_rng.currentIndexChanged.connect(self.refresh_trend)
        bar.addWidget(QLabel("Variable:"))
        bar.addWidget(self.cmb_var, 1)
        bar.addWidget(QLabel("Rango:"))
        bar.addWidget(self.cmb_rng)
        tl.addLayout(bar)
        self.plot = pg.PlotWidget(axisItems={"bottom": pg.DateAxisItem()})
        self.plot.showGrid(x=True, y=True, alpha=0.25)
        self.curve = self.plot.plot(pen=pg.mkPen(theme.c("measure"), width=2))
        self.lo = pg.PlotDataItem(pen=pg.mkPen(None))
        self.hi = pg.PlotDataItem(pen=pg.mkPen(None))
        band = QColor(theme.c("measure"))
        band.setAlpha(45)
        self.plot.addItem(self.lo)
        self.plot.addItem(self.hi)
        self.plot.addItem(pg.FillBetweenItem(self.lo, self.hi, brush=pg.mkBrush(band)))
        self.lines = {k: pg.InfiniteLine(angle=0, pen=pg.mkPen(theme.c(c), width=w)) for k, c, w in (
            ("wl", "warning", 1), ("wh", "warning", 1), ("al", "critical", 2), ("ah", "critical", 2))}
        for ln in self.lines.values():
            ln.setVisible(False)
            self.plot.addItem(ln)
        tl.addWidget(self.plot, 1)
        self.lbl_trend = QLabel()
        self.lbl_trend.setStyleSheet(f"color:{theme.c('muted')};")
        tl.addWidget(self.lbl_trend)
        self.tabs.addTab(trend, "Tendencia")
        self.lst_events = QListWidget()
        self.tabs.addTab(self.lst_events, "Eventos")
        lay.addWidget(self.tabs, 1)
        self._vars_key = None

    def show_line(self, line_id: Optional[str]) -> None:
        self.line_id = line_id
        self._vars_key = None
        self.refresh(time.time())
        self.refresh_trend()

    def refresh(self, now: float) -> None:
        line = self.reader.lines.get(self.line_id) if self.line_id else None
        if line is None:
            self.lbl.setText(tr("Elige una línea para ver su detalle."))
            self.tbl.setRowCount(0)
            return
        st = line.status
        o = st.get("oee") or {}
        unit = o.get("unit", "m")
        extra = (tr("Producido en el turno: <b>{t}</b> (conforme {g})",
                    t=f"{(o.get('length_total') or 0):,.0f} {unit}", g=f"{(o.get('length_good') or 0):,.0f} {unit}")
                 + " · " + tr("Paros: <b>{s}</b> · microparos: <b>{m}</b>", s=o.get("n_stops", 0),
                              m=o.get("n_microstops", 0))) if o else ""
        self.lbl.setText(f"<span style='font-size:17px; color:{theme.c('title')}'><b>{line.name}</b></span> "
                         f"<span style='color:{theme.c('muted')}'>({line.line_id} · {tr(CONN_TEXT[line.connection(now)])}"
                         f" · {fmt_age(line.age(now))})</span><br>{tr('Receta: {r}', r=st.get('recipe') or '—')}"
                         f"{'<br>' + extra if extra else ''}")
        vars_ = st.get("variables") or []
        self.tbl.setRowCount(len(vars_))
        for i, v in enumerate(vars_):
            ref = v.get("ref")
            lvl = v.get("level")
            cells = [v.get("label") or v.get("name"), fmt_val(v), v.get("unit") or "",
                     "" if ref is None else f"{ref:.4g}", tr({"ALARM": "ALARMA", "WARN": "AVISO"}.get(lvl, lvl or "—")),
                     "" if v.get("cpk") is None else (f"{v['cpk']:.2f}" if v["cpk"] < 10 else "> 10")]
            for c, text in enumerate(cells):
                it = QTableWidgetItem(text)
                if c == 4 and lvl in LEVEL_KEYS:
                    it.setBackground(QBrush(QColor(theme.c(LEVEL_KEYS[lvl]))))
                    it.setForeground(QBrush(QColor("#1b1b1b" if lvl == "WARN" else "#ffffff")))
                if c == 1 and not v.get("fresh"):
                    it.setForeground(QBrush(QColor(theme.c("muted"))))
                self.tbl.setItem(i, c, it)
        self.lst_alarms.clear()
        for a in st.get("alarms") or []:
            it = QListWidgetItem(f"{time.strftime('%H:%M:%S', time.localtime(a['since']))}  {translate_text(a['msg'])}")
            it.setForeground(QBrush(QColor(theme.c(LEVEL_KEYS.get(a.get("level"), "neutral")))))
            self.lst_alarms.addItem(it)
        if not self.lst_alarms.count():
            self.lst_alarms.addItem(tr("✔ Sin alarmas ni avisos activos"))
        self.lst_events.clear()
        for e in reversed(line.events[-200:]):
            it = QListWidgetItem(f"{time.strftime('%d/%m %H:%M:%S', time.localtime(e.get('ts', 0)))}  "
                                 f"[{tr({'WARN': 'AVISO', 'ALARM': 'ALARMA'}.get(e.get('level'), e.get('level', '')))}]  "
                                 f"{translate_text(e.get('msg', ''))}")
            if e.get("level") in ("WARN", "ALARM"):
                it.setForeground(QBrush(QColor(theme.c(LEVEL_KEYS[e["level"]]))))
            self.lst_events.addItem(it)
        key = tuple(v["id"] for v in vars_ if v.get("kind") in ("actual", "formula", "setpoint"))
        if key != self._vars_key:
            self._vars_key = key
            cur = self.cmb_var.currentData()
            self.cmb_var.blockSignals(True)
            self.cmb_var.clear()
            for v in vars_:
                if v["id"] in key:
                    self.cmb_var.addItem(f"{v.get('label') or v['name']} ({v.get('unit') or ''})", v["id"])
            idx = self.cmb_var.findData(cur)
            self.cmb_var.setCurrentIndex(max(0, idx))
            self.cmb_var.blockSignals(False)

    def _row_to_trend(self, row: int, _col: int) -> None:
        vars_ = (self.reader.lines.get(self.line_id).status.get("variables") or []) if self.line_id else []
        if 0 <= row < len(vars_):
            idx = self.cmb_var.findData(vars_[row]["id"])
            if idx >= 0:
                self.cmb_var.setCurrentIndex(idx)
                self.tabs.setCurrentIndex(2)

    def refresh_trend(self, *_):
        vid = self.cmb_var.currentData()
        if not self.line_id or not vid:
            self.curve.setData([], [])
            return
        rng = float(self.cmb_rng.currentData())
        t, mean, lo, hi = self.reader.trend(self.line_id, vid, time.time() - rng)
        self.curve.setData(t, mean)
        self.lo.setData(t, lo)
        self.hi.setData(t, hi)
        var = next((v for v in (self.reader.lines[self.line_id].status.get("variables") or []) if v["id"] == vid), {})
        for key, val in zip(("wl", "wh", "al", "ah"), var.get("limits") or [None] * 4):
            self.lines[key].setVisible(val is not None)
            if val is not None:
                self.lines[key].setValue(val)
        self.plot.setXRange(time.time() - rng, time.time(), padding=0.01)
        self.lbl_trend.setText(tr("{n} puntos (media por minuto; la banda es el mínimo y máximo)", n=len(t)))


class FleetWindow(QMainWindow):
    def __init__(self, folder: Optional[str], settings_file: Path, state_file: Optional[Path] = None):
        super().__init__()
        self.settings_file = Path(settings_file)
        # Idioma y tema: los mismos que el programa de monitoreo si comparten carpeta de datos.
        self.state_file = Path(state_file) if state_file else self.settings_file.with_name("state.json")
        self.settings: FleetSettings = load_fleet_settings(self.settings_file)
        if folder and folder != self.settings.dir:
            self.settings.dir = folder
            self._save_settings()  # la carpeta indicada al abrir queda recordada
        self.setWindowTitle(tr("Dashboard global de líneas"))
        self.resize(1500, 900)
        self.reader = FleetReader(self.settings.dir)
        self.cards: dict[str, LineCard] = {}
        self.selected: Optional[str] = None
        self.plant_events: list[dict] = []
        self._order: list[str] = []
        self._layout_key = None
        self._headers: list = []
        self._flags: dict[str, tuple] = {}  # id -> (alarma, detenida, sin comunicación) del ciclo anterior
        self._first_scan = True
        self.tv = False
        self._page = 0

        central = QWidget()
        outer = QHBoxLayout(central)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        self.sidebar = self._build_sidebar()
        outer.addWidget(self.sidebar)
        right = QWidget()
        right.setObjectName("content")
        root = QVBoxLayout(right)
        root.setContentsMargins(12, 10, 12, 6)
        root.setSpacing(8)
        outer.addWidget(right, 1)

        # Barra superior (como el monitor): buscador, filtro, orden y campana de alarmas
        self.top = QFrame()
        self.top.setObjectName("topbar")
        top = QHBoxLayout(self.top)
        top.setContentsMargins(10, 6, 10, 6)
        top.setSpacing(10)
        self.ed_search = QLineEdit()
        self.ed_search.setObjectName("search")
        self.ed_search.setPlaceholderText(tr("Buscar línea, área o estado…"))
        self.ed_search.setClearButtonEnabled(True)
        self.ed_search.setFocusPolicy(Qt.ClickFocus)
        self.ed_search.addAction(icons.icon("search", theme.c("muted")), QLineEdit.LeadingPosition)
        self.ed_search.setMinimumWidth(280)
        self.ed_search.textChanged.connect(lambda _: self.refresh(rescan=False))
        top.addWidget(self.ed_search, 2)
        top.addStretch(1)
        self.cmb_filter = QComboBox()
        for k, label in FILTERS:
            self.cmb_filter.addItem(label, k)
        self.cmb_filter.currentIndexChanged.connect(lambda _: self.refresh(rescan=False))
        top.addWidget(self.cmb_filter)
        self.lbl_sort = QLabel("Orden:")
        top.addWidget(self.lbl_sort)
        self.cmb_sort = QComboBox()
        for k, label in SORTS:
            self.cmb_sort.addItem(label, k)
        self.cmb_sort.currentIndexChanged.connect(lambda _: self.refresh(rescan=False))
        top.addWidget(self.cmb_sort)
        self.btn_bell = QToolButton()
        self.btn_bell.setObjectName("bell")
        self.btn_bell.setIconSize(QSize(18, 18))
        self.btn_bell.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.btn_bell.setIcon(icons.icon("events", theme.c("nav_icon")))
        self.btn_bell.setToolTip(tr("Líneas con alarma o aviso (clic: mostrar solo esas)"))
        self.btn_bell.clicked.connect(lambda: self.cmb_filter.setCurrentIndex(self.cmb_filter.findData("alarm")))
        top.addWidget(self.btn_bell)
        root.addWidget(self.top)
        self.stack = QStackedWidget()  # páginas: líneas, analizador, problemas y análisis (en la misma ventana)
        root.addWidget(self.stack, 1)
        lines_page = QWidget()
        lroot = QVBoxLayout(lines_page)
        lroot.setContentsMargins(0, 0, 0, 0)
        lroot.setSpacing(8)

        summary = QHBoxLayout()
        summary.setSpacing(10)
        self.tiles = {k: FleetTile(k, ic, t, ck) for k, ic, t, ck in (
            ("lines", "variables", "Líneas", "accent"), ("running", "play", "En marcha", "good_text"),
            ("stopped", "pause", "Detenidas", "critical"), ("alarm", "alert", "Con alarma", "critical"),
            ("offline", "stop", "Sin comunicación", "neutral"), ("oee", "oee", "OEE promedio (turno)", "accent"))}
        for t in self.tiles.values():
            summary.addWidget(t)
        self.lbl_page = QLabel()
        summary.addWidget(self.lbl_page)
        lroot.addLayout(summary)

        self.split = QSplitter(Qt.Horizontal)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.grid_host = QWidget()
        self.grid = QGridLayout(self.grid_host)
        self.grid.setSpacing(10)
        self.grid.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.scroll.setWidget(self.grid_host)
        self.empty = QLabel()
        self.empty.setAlignment(Qt.AlignCenter)
        self.empty.setWordWrap(True)
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        ll.addWidget(self.empty)
        ll.addWidget(self.scroll, 1)
        self.vsplit = QSplitter(Qt.Vertical)
        self.vsplit.addWidget(left)
        self.events_box = QWidget()
        el = QVBoxLayout(self.events_box)
        el.setContentsMargins(0, 0, 0, 0)
        el.addWidget(QLabel("<b>Alarmas y avisos recientes de la planta</b>"))
        self.lst_plant = QListWidget()
        self.lst_plant.itemDoubleClicked.connect(lambda it: self.select(it.data(Qt.UserRole)))
        el.addWidget(self.lst_plant, 1)
        self.vsplit.addWidget(self.events_box)
        self.vsplit.setSizes([650, 200])
        self.split.addWidget(self.vsplit)
        self.detail = LineDetail(self.reader)
        self.split.addWidget(self.detail)
        self.split.setSizes([1000, 500])
        lroot.addWidget(self.split, 1)
        self.pages = {"lines": lines_page}
        self.stack.addWidget(lines_page)
        self.setCentralWidget(central)
        self._build_menus()

        self.notifier = self._make_notifier()
        self.weekly_timer = QTimer(self)
        self.weekly_timer.timeout.connect(lambda: self.send_weekly())
        self.weekly_timer.start(60000)
        self.map_blink = QTimer(self)
        self.map_blink.timeout.connect(lambda: self.pages["map"].blink_tick()
                                       if "map" in self.pages and self.current_page == "map" else None)
        self.map_blink.start(600)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(int(self.settings.poll_s * 1000))
        self.trend_timer = QTimer(self)
        self.trend_timer.timeout.connect(self.detail.refresh_trend)
        self.trend_timer.start(60000)  # la tendencia llega por minuto
        self.tv_timer = QTimer(self)
        self.tv_timer.timeout.connect(self._next_page)
        self.blink = blink_timer(self, lambda: self.cards.values())
        QShortcut(QKeySequence("Esc"), self, activated=lambda: self.tv and self.toggle_tv())
        self._set_dir_label()
        self.detail.show_line(None)
        QTimer.singleShot(0, self.refresh)

    # --- barra lateral (como el monitor) -----------------------------------------------------
    def _build_sidebar(self) -> QWidget:
        from .branding import header_widget
        side = QWidget()
        side.setObjectName("sidebar")
        side.setFixedWidth(236)
        lay = QVBoxLayout(side)
        lay.setContentsMargins(10, 14, 10, 10)
        lay.addWidget(header_widget(self.settings_file.parent))
        lay.addSpacing(12)
        self.nav = QListWidget()
        self.nav.setObjectName("nav")
        self.nav.setFocusPolicy(Qt.NoFocus)
        self.nav.setIconSize(QSize(18, 18))
        self.nav.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.nav.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        items = [("lines", "Líneas", "home", None), ("map", "Mapa de planta", "page", None),
                 ("analyzer", "Analizador de planta", "kpi", None),
                 ("problems", "Problemas de proceso", "problems", None),
                 ("analysis", "Análisis estadístico", "analysis", None),
                 ("maintenance", "Mantenimiento", "setup", None),
                 ("ack", "Silenciar avisos", "check", self.acknowledge_all),
                 ("csv", "Exportar", "reports", self.export_csv), ("tv", "Modo TV", "page", self.toggle_tv),
                 ("setup", "Configuración", "setup", self.open_setup)]
        tips = {"ack": "Detiene el parpadeo y el sonido de las tarjetas de las líneas que entraron en alarma, se "
                       "detuvieron o perdieron comunicación. Las alarmas siguen a la vista; si vuelve a pasar, "
                       "vuelve a avisar.",
                "analyzer": "Problemas, fallas, tiempos muertos, estabilidad y tendencia de todas las líneas, con "
                            "conclusiones automáticas",
                "analysis": "Análisis estadístico con los datos que publican los monitores (por línea, turno, día…)",
                "map": "Un mosaico por línea, agrupado por área, con su estado, OEE y producción (ideal para TV)",
                "maintenance": "Preventivos y correctivos leídos de los paros que se capturan en los monitores: tiempo, "
                               "desperdicio y hace cuánto fue el último, por línea"}
        self._nav_actions = {}
        for key, label, ic, slot in items:
            it = QListWidgetItem(tr(label))
            it.setIcon(icons.icon(ic, theme.c("nav_icon"), theme.c("accent_text")))
            it.setData(Qt.UserRole, key)
            it.setSizeHint(QSize(0, 36))
            if key in tips:
                it.setToolTip(tr(tips[key]))
            self.nav.addItem(it)
            self._nav_actions[key] = slot
        self.nav.setFixedHeight(len(items) * 38 + 6)
        self.nav.setCurrentRow(0)
        self.nav.itemClicked.connect(self._nav_clicked)
        lay.addWidget(self.nav)
        lay.addStretch(1)
        self.lbl_dir = QLabel()  # estado de la carpeta de datos (sin mostrar la ruta)
        self.lbl_dir.setWordWrap(True)
        self.lbl_dir.setStyleSheet(f"color:{theme.c('muted')}; font-size:11px;")
        lay.addWidget(self.lbl_dir)
        return side

    def _nav_clicked(self, item) -> None:
        key = item.data(Qt.UserRole)
        slot = self._nav_actions.get(key)
        if slot is None:
            self.show_page(key)
            return
        self._select_nav(self.current_page)  # las acciones no cambian la página
        slot()

    def _select_nav(self, key: str) -> None:
        for i in range(self.nav.count()):
            if self.nav.item(i).data(Qt.UserRole) == key:
                self.nav.setCurrentRow(i)

    @property
    def current_page(self) -> str:
        w = self.stack.currentWidget()
        return next((k for k, v in self.pages.items() if v is w), "lines")

    def show_page(self, key: str) -> None:
        """Páginas dentro de la misma ventana (se crean la primera vez que se abren)."""
        if key not in self.pages:
            home = self.settings_file.parent
            if key == "problems":
                from .fleet_problems import FleetProblemsPage
                w = FleetProblemsPage(self)
            elif key == "analyzer":
                from .fleet_analyzer import FleetAnalyzer
                w = FleetAnalyzer(lambda: self.reader, home, on_notify=self.open_notifications,
                                  on_send_now=lambda: self.send_weekly(force=True))
            elif key == "map":
                from .fleet_map import FleetMap
                w = FleetMap(lambda: self.reader, home, lambda: self.settings)
                w.open_line.connect(self._open_from_map)
            elif key == "maintenance":
                from .fleet_maint import FleetMaintenance
                w = FleetMaintenance(lambda: self.reader, home)
            elif key == "analysis":
                from ..fleet_data import FleetStatsContext
                from .stats_page import StatsPage
                self.stats_ctx = FleetStatsContext(lambda: self.reader, home)
                w = StatsPage(self.stats_ctx)
            else:
                return
            self.pages[key] = w
            self.stack.addWidget(w)
        if key == "analysis":
            self.stats_ctx.refresh()  # variables y líneas que haya en este momento
        elif key in ("analyzer", "problems", "map", "maintenance"):
            self.pages[key].refresh()  # con los datos más recientes al abrirla
        self.stack.setCurrentWidget(self.pages[key])
        for wdg in (self.cmb_filter, self.cmb_sort, self.ed_search, self.lbl_sort):
            wdg.setVisible(key == "lines")  # búsqueda, filtro y orden son de la vista de líneas
        self.top.setVisible(key == "lines" and not self.tv)
        self._select_nav(key)

    # --- menús: archivo, vista, idioma y tema ------------------------------------------------
    def _build_menus(self) -> None:
        """Solo lo que no está ya a la vista: Archivo · Configuración · Ver · Ayuda (mismo orden que el monitor).

        Filtro, orden, búsqueda, reconocer avisos, exportar y modo TV están en la barra superior; sonido y
        agrupar por área, en la configuración.
        """
        mb = self.menuBar()
        m = mb.addMenu("&Archivo")
        act = m.addAction("⤓ Exportar…", self.export_csv)
        act.setShortcut("Ctrl+E")
        m.addAction("📉 Problemas de proceso (Pareto y exportar)…", self.open_problems)
        m.addSeparator()
        act = m.addAction("Salir", self.close)
        act.setShortcut("Ctrl+Q")

        m = mb.addMenu("C&onfiguración")
        m.addAction("⚙ Carpeta de datos y avisos…", lambda: self.open_setup(0))
        m.addAction("Indicadores de las tarjetas…", lambda: self.open_setup(1))
        m.addAction("Líneas y áreas…", lambda: self.open_setup(2))
        m.addAction("🎯 Metas, costos y reporte semanal…", self.open_plant)
        m.addAction("📨 Notificaciones (correo y mensajes)…", self.open_notifications)
        from .wheel_lock import lock as wheel_lock
        self.act_wheel = m.addAction("🔒 Bloquear zoom de las gráficas con la rueda del ratón")
        self.act_wheel.setCheckable(True)
        self.act_wheel.setChecked(bool(self._ui_state().get("ui", {}).get("lock_wheel", True)))
        wheel_lock().enabled = self.act_wheel.isChecked()
        self.act_wheel.toggled.connect(self._wheel_toggled)
        m.addSeparator()
        lm = m.addMenu("🌐 Idioma / Language")
        grp = QActionGroup(lm)
        for code, label in LANGS.items():
            act = lm.addAction(label, lambda code=code: self._set_ui_pref("lang", code))
            act.setCheckable(True)
            act.setChecked(code == i18n_lang())
            grp.addAction(act)
        tm = m.addMenu("🎨 Tema")
        grp2 = QActionGroup(tm)
        for code, label in (("light", "Claro"), ("dark", "Oscuro")):
            act = tm.addAction(tr(label), lambda code=code: self._set_ui_pref("theme", code))
            act.setCheckable(True)
            act.setChecked(code == theme.name())
            grp2.addAction(act)

        m = mb.addMenu("&Ver")
        self.act_detail = m.addAction("Panel de detalle de la línea")
        self.act_events = m.addAction("Panel de alarmas de la planta")
        for act, widget in ((self.act_detail, self.detail), (self.act_events, self.events_box)):
            act.setCheckable(True)
            act.setChecked(True)
            act.toggled.connect(lambda on, widget=widget: widget.setVisible(on and not self.tv))
        m.addSeparator()
        act = m.addAction("📺 Modo TV", self.toggle_tv)
        act.setShortcut("F11")
        m.addAction("📺 Modo TV con el mapa de planta", lambda: self.toggle_tv(map_view=True))

        m = mb.addMenu("A&yuda")
        act = m.addAction("Manual de uso", lambda: QDesktopServices.openUrl(QUrl(HELP_URL)))
        act.setShortcut("F1")
        m.addAction("Acerca de…", self._about)
        # Los atajos siguen funcionando con el menú oculto (modo TV).
        for menu in mb.findChildren(QMenu):
            self.addActions([a for a in menu.actions() if not a.shortcut().isEmpty()])
        QShortcut(QKeySequence("Ctrl+K"), self, activated=self.acknowledge_all)  # reconocer avisos

    def _about(self) -> None:
        QMessageBox.about(self, "Acerca de", tr("<b>Dashboard global de líneas</b><br>Estado, indicadores y alarmas de "
                                             "todas las líneas a partir de la carpeta de datos compartida.<br>Solo lee "
                                             "los archivos que publican las líneas: no modifica nada en ellas.")
                          + f"<br><br>{tr('Versión')}: {version_label()}")

    def _ui_state(self) -> dict:
        try:
            return json.loads(self.state_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def _wheel_toggled(self, on: bool) -> None:
        from .wheel_lock import lock as wheel_lock
        wheel_lock().enabled = on
        state = self._ui_state()
        state["ui"] = {**state.get("ui", {}), "lock_wheel": on}
        try:
            self.state_file.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")
        except OSError:
            pass

    def _set_ui_pref(self, key: str, value: str) -> None:
        state = self._ui_state()
        ui = dict(state.get("ui", {}))
        if ui.get(key, {"lang": "es", "theme": "light"}[key]) == value:
            return
        ui[key] = value
        state["ui"] = ui
        try:
            self.state_file.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")
        except OSError:
            pass
        from .main_window import apply_ui_prefs
        apply_ui_prefs(ui)
        self.rebuild_window()

    def rebuild_window(self) -> "FleetWindow":
        """Vuelve a construir la ventana con el idioma o tema nuevos (misma carpeta y configuración)."""
        new = FleetWindow(None, self.settings_file, self.state_file)
        new.setGeometry(self.geometry())
        new.cmb_sort.setCurrentIndex(self.cmb_sort.currentIndex())
        new.cmb_filter.setCurrentIndex(self.cmb_filter.currentIndex())
        new.plant_events = list(self.plant_events)
        new._fill_plant_events()
        if self.isMaximized():
            new.showMaximized()
        else:
            new.show()
        if self.selected:
            QTimer.singleShot(100, lambda: new.select(self.selected) if self.selected in new.cards else None)
        self.close()
        self.deleteLater()
        rebuilt_fleet_windows.append(new)
        return new

    def closeEvent(self, event) -> None:
        for t in (self.timer, self.trend_timer, self.tv_timer, self.blink, self.weekly_timer, self.map_blink):
            t.stop()
        super().closeEvent(event)

    # --- configuración ---------------------------------------------------------------------
    def _set_dir_label(self) -> None:
        """Estado de la carpeta de datos en la barra lateral, sin mostrar su ruta."""
        if not self.settings.dir:
            text = tr("○ Carpeta de datos sin elegir")
        elif self.reader.error:
            text = tr("● Sin acceso a la carpeta de datos")
        else:
            text = tr("● Carpeta de datos conectada · {n} líneas", n=len(self.reader.lines))
        self.lbl_dir.setText(text)

    def _save_settings(self) -> None:
        try:
            save_fleet_settings(self.settings_file, self.settings)
        except OSError:
            pass

    def open_setup(self, tab: int = 0) -> None:
        from .fleet_setup import FleetSetupDialog
        dlg = FleetSetupDialog(self.settings, self.reader.lines, self)
        dlg.tabs.setCurrentIndex(int(tab or 0))
        if not dlg.exec():
            return
        new = dlg.result_settings()
        folder_changed = new.dir != self.settings.dir
        self.settings = new
        self._save_settings()
        self.timer.start(int(new.poll_s * 1000))
        if folder_changed:
            self.set_folder(new.dir)
        else:
            self._rebuild_cards()
            self.refresh()

    def set_folder(self, d: str) -> None:
        self.settings.dir = d
        self.reader = FleetReader(d)
        self.detail.reader = self.reader
        self.plant_events.clear()
        self.lst_plant.clear()
        self._flags.clear()
        self._first_scan = True
        self._rebuild_cards()
        self._set_dir_label()
        self._save_settings()
        self.refresh()

    def _rebuild_cards(self) -> None:
        for c in self.cards.values():
            c.deleteLater()
        self.cards.clear()
        self._order = []
        self._layout_key = None

    # --- actualización ---------------------------------------------------------------------
    def refresh(self, rescan: bool = True) -> None:
        now = time.time()
        s = self.settings
        if not s.dir:
            self.empty.setText(tr("Elige la carpeta donde escriben las líneas (⚙ Configuración)."))
            self.empty.setVisible(True)
            return
        if rescan:
            new = self.reader.scan()
            alarms = [e for e in new if e.get("level") in ("WARN", "ALARM")]
            if alarms:
                self.plant_events = (self.plant_events + alarms)[-500:]
                self._fill_plant_events()
        lines = self.reader.lines
        for lid, ln in lines.items():
            tiles = s.tiles_for(lid)
            keys = {k for k in (trend_key(t, ln.status) for t in tiles) if k}
            if keys:
                since = min(period_since(t, ln.status, now) for t in tiles if trend_key(t, ln.status))
                self.reader.update_series(ln, keys, since)
            if lid not in self.cards:
                card = LineCard(lid, tiles, s.card_columns)
                card.clicked.connect(self.select)
                card.selected = lid == self.selected
                self.cards[lid] = card
        for lid in [k for k in self.cards if k not in lines]:
            self.cards.pop(lid).deleteLater()
        self._notify(now)
        shown = self._visible(now)
        for lid in shown:
            self.cards[lid].update_line(lines[lid], now, s.offline_s, s.area_of(lines[lid]))
        self._layout(shown, now)
        self._summary(now)
        self._set_dir_label()
        self._update_ack()
        if "map" in self.pages and self.current_page == "map":
            self.pages["map"].refresh()
        if self.reader.error:
            self.empty.setText(tr("No se puede leer la carpeta de datos: revisa la red o los permisos "
                                  "(⚙ Configuración)."))
        elif not lines:
            self.empty.setText(tr("Ninguna línea ha escrito todavía en esta carpeta."))
        self.empty.setVisible(bool(self.reader.error) or not lines)
        if self.selected:
            self.detail.refresh(now)

    def _notify(self, now: float) -> None:
        """Aviso (sonido y parpadeo) cuando una línea pasa a alarma, se detiene o pierde comunicación."""
        s = self.settings
        beep = False
        for lid, ln in self.reader.lines.items():
            st = ln.status
            conn = ln.connection(now, s.offline_s)
            flags = (bool(st.get("n_alarms")) and conn in ("online", "stale"),
                     (st.get("machine") or {}).get("state") in ("stopped",) and conn in ("online", "stale"),
                     conn == "offline")
            old = self._flags.get(lid)
            self._flags[lid] = flags
            if old is None or self._first_scan:
                continue
            reasons = []
            if s.notify_alarm and flags[0] and not old[0]:
                reasons.append(tr("entró en alarma"))
            if s.notify_stop and flags[1] and not old[1]:
                reasons.append(tr("se detuvo"))
            if s.notify_offline and flags[2] and not old[2]:
                reasons.append(tr("perdió comunicación"))
            if reasons:
                card = self.cards.get(lid)
                if card is not None:
                    card.blinking = True
                beep = True
                self.plant_events.append({"ts": now, "level": "ALARM", "line_id": lid,
                                          "msg": tr("{n} {r}", n=ln.name, r=", ".join(reasons))})
                self._fill_plant_events()
        self._first_scan = False
        if beep and s.sound:
            QApplication.beep()
            QApplication.alert(self)

    def acknowledge_all(self) -> None:
        """Silencia los avisos: deja de parpadear y de sonar (las alarmas siguen a la vista)."""
        for c in self.cards.values():
            c.acknowledge()
        self._update_ack()

    def _update_ack(self) -> None:
        n = sum(1 for c in self.cards.values() if c.blinking)
        for i in range(self.nav.count()):
            it = self.nav.item(i)
            if it.data(Qt.UserRole) == "ack":
                it.setText(tr("Silenciar avisos") + (f"  ({n})" if n else ""))
                it.setForeground(QColor(theme.c("critical")) if n else QColor(theme.c("nav_text")))

    def _visible(self, now: float) -> list[str]:
        lines = self.reader.lines
        s = self.settings
        q = self.ed_search.text().strip().lower()
        flt = self.cmb_filter.currentData()
        out = []
        for lid, ln in lines.items():
            if q and q not in ln.name.lower() and q not in lid.lower() and q not in s.area_of(ln).lower():
                continue
            st = ln.status
            conn = ln.connection(now, s.offline_s)
            if flt == "alarm" and not (st.get("n_alarms") or st.get("n_warnings")):
                continue
            if flt == "stopped" and (st.get("machine") or {}).get("state") not in ("stopped", "microstop"):
                continue
            if flt == "offline" and conn not in ("offline", "closed", "stale"):
                continue
            out.append(lid)
        key = self.cmb_sort.currentData()
        if key == "status":
            out.sort(key=lambda k: (-severity(lines[k], now, s.offline_s), natural(lines[k].name)))
        elif key == "oee":
            def oee(k):
                v = (lines[k].status.get("kpis") or {}).get("oee")
                return (v is None, v or 0, natural(lines[k].name))
            out.sort(key=oee)
        else:
            out.sort(key=lambda k: natural(lines[k].name))
        if s.group_by_area:
            out.sort(key=lambda k: natural(s.area_of(lines[k]) or "￿"))  # estable: conserva el orden
        return out

    def _columns(self) -> int:
        """Tarjetas por fila; de paso ajusta el ancho de todas para llenar la ventana."""
        m = self.grid.contentsMargins()
        avail = self.scroll.viewport().width() - m.left() - m.right() - 2
        cols, card_w = card_metrics(avail, self.settings.card_columns, self.grid.horizontalSpacing(),
                                    count=len(self.cards))
        for card in self.cards.values():
            card.set_width(card_w)
        return cols

    def _layout(self, order: list[str], now: float) -> None:
        s = self.settings
        lines = self.reader.lines
        cols = self._columns()
        pages = [order]
        if self.tv and order:
            card_h = max(c.sizeHint().height() for c in self.cards.values()) + 10
            rows = max(1, (self.scroll.viewport().height() - 10) // card_h)
            per = rows * cols
            pages = [order[i:i + per] for i in range(0, len(order), per)]
            self._page %= len(pages)
            self.lbl_page.setText(tr("Página {p} de {n}", p=self._page + 1, n=len(pages)) if len(pages) > 1 else "")
        else:
            self.lbl_page.setText("")
        shown = pages[self._page] if self.tv else order
        area_of = {k: s.area_of(lines[k]) or tr(NO_AREA) for k in order} if s.group_by_area else {}
        areas = [area_of.get(k) for k in shown]
        key = (tuple(shown), tuple(areas), cols, self.scroll.viewport().width())
        if key == self._layout_key:
            for hdr, area, group in self._headers:  # mismo acomodo: solo se actualizan los resúmenes
                hdr.setText(self._area_header(area, group, now))
            return
        self._layout_key = key
        self._headers = []
        self._order = list(shown)
        while self.grid.count():
            it = self.grid.takeAt(0)
            w = it.widget()
            if w is not None and not isinstance(w, LineCard):
                w.hide()  # que no quede encimado mientras se borra
                w.setParent(None)
                w.deleteLater()
        for c in self.cards.values():
            c.setVisible(False)
        row, col, current = 0, 0, object()
        for lid, area in zip(shown, areas):
            if area != current and area is not None:
                if col:
                    row, col = row + 1, 0
                group = [k for k in order if area_of.get(k) == area]  # el resumen cuenta toda el área
                hdr = QLabel(self._area_header(area, group, now))
                hdr.setTextFormat(Qt.RichText)
                self._headers.append((hdr, area, group))
                self.grid.addWidget(hdr, row, 0, 1, cols)
                row += 1
            current = area
            card = self.cards[lid]
            self.grid.addWidget(card, row, col)
            card.setVisible(True)
            col += 1
            if col >= cols:
                row, col = row + 1, 0

    def _area_header(self, area: str, ids: list[str], now: float) -> str:
        lines = self.reader.lines
        s = self.settings
        on = [lines[k] for k in ids if lines[k].connection(now, s.offline_s) in ("online", "stale")]
        alarms = sum(bool(ln.status.get("n_alarms")) for ln in on)
        oees = [(ln.status.get("kpis") or {}).get("oee") for ln in on]
        oees = [x for x in oees if x is not None]
        oee = f"{sum(oees) / len(oees):.0f} %" if oees else "—"
        return (f"<span style='font-size:16px; color:{theme.c('title')}'><b>{area}</b></span> "
                f"<span style='color:{theme.c('muted')}'>· {tr('{n} líneas', n=len(ids))} · OEE {oee}"
                + (f" · <b style='color:{theme.c('critical')}'>{tr('{n} con alarma', n=alarms)}</b>" if alarms else "")
                + "</span>")

    def _summary(self, now: float) -> None:
        s = self.settings
        lines = list(self.reader.lines.values())
        conn = [ln.connection(now, s.offline_s) for ln in lines]
        online = [ln for ln, c in zip(lines, conn) if c in ("online", "stale")]
        states = [(ln.status.get("machine") or {}).get("state") for ln in online]
        self.tiles["lines"].set(str(len(lines)))
        self.tiles["running"].set(str(sum(x in ("running", "slow", "assumed") for x in states)), theme.c("good"))
        self.tiles["stopped"].set(str(sum(x in ("stopped", "microstop") for x in states)), theme.c("critical"))
        n_alarm = sum(bool(ln.status.get("n_alarms")) for ln in online)
        self.tiles["alarm"].set(str(n_alarm), theme.c("critical") if n_alarm else theme.c("good_text"))
        self.btn_bell.setText(str(n_alarm) if n_alarm else "")
        self.btn_bell.setIcon(icons.icon("events", theme.c("critical") if n_alarm else theme.c("nav_icon")))
        off = sum(c in ("offline", "closed") for c in conn)
        self.tiles["offline"].set(str(off), theme.c("neutral") if off else None)
        oees = [(ln.status.get("kpis") or {}).get("oee") for ln in online]
        oees = [x for x in oees if x is not None]
        self.tiles["oee"].set(f"{sum(oees) / len(oees):.0f} %" if oees else "—")

    def _fill_plant_events(self) -> None:
        self.lst_plant.clear()
        lines = self.reader.lines
        for e in reversed(self.plant_events[-200:]):
            name = lines[e["line_id"]].name if e["line_id"] in lines else e["line_id"]
            msg = translate_text(e.get("msg", ""))
            text = msg if msg.startswith(name) else f"{name}  ·  {msg}"
            it = QListWidgetItem(f"{time.strftime('%d/%m %H:%M:%S', time.localtime(e.get('ts', 0)))}  {text}")
            it.setData(Qt.UserRole, e["line_id"])
            it.setForeground(QBrush(QColor(theme.c(LEVEL_KEYS.get(e.get("level"), "neutral")))))
            self.lst_plant.addItem(it)

    def select(self, line_id: str) -> None:
        if self.selected in self.cards:
            self.cards[self.selected].selected = False
        self.selected = line_id
        if line_id in self.cards:
            self.cards[line_id].selected = True
            self.cards[line_id].acknowledge()
        self.detail.show_line(line_id)
        self.refresh(rescan=False)

    # --- modo TV y exportación ---------------------------------------------------------------
    def toggle_tv(self, map_view: bool = False) -> None:
        self.tv = not self.tv
        if self.tv:
            self.show_page("map" if map_view else "lines")
        self.top.setVisible(not self.tv)
        self.sidebar.setVisible(not self.tv)
        self.menuBar().setVisible(not self.tv)
        self.detail.setVisible(not self.tv and self.act_detail.isChecked())
        self.events_box.setVisible(not self.tv and self.act_events.isChecked())
        if self.tv:
            self.showFullScreen()
            self.tv_timer.start(int(self.settings.tv_rotate_s * 1000))
        else:
            self.showNormal()
            self.tv_timer.stop()
            self._page = 0
        self._layout_key = None
        QTimer.singleShot(50, lambda: self.refresh(rescan=False))

    def _next_page(self) -> None:
        self._page += 1
        self._layout_key = None
        self.refresh(rescan=False)

    def open_problems(self) -> None:
        self.show_page("problems")

    def _open_from_map(self, line_id: str) -> None:
        if self.tv:
            return
        self.show_page("lines")
        if line_id in self.cards:
            self.select(line_id)

    # --- notificaciones y reporte semanal ---------------------------------------------------------
    def _make_notifier(self):
        from ..notify import Notifier
        return Notifier(self.settings_file.parent, None, where=lambda: tr("Dashboard global"))

    def open_notifications(self) -> None:
        from .notify_dialog import NotifyDialog
        NotifyDialog(self.notifier, self).exec()

    def open_plant(self) -> None:
        from .fleet_plant_dialog import PlantDialog
        lines = [ln.name for ln in sorted(self.reader.lines.values(), key=lambda ln: ln.name)]
        if PlantDialog(self.settings_file.parent, lines, self.open_notifications,
                       lambda: self.send_weekly(force=True), self).exec() and "analyzer" in self.pages:
            self.pages["analyzer"].refresh()

    def weekly_due(self, now: float) -> bool:
        import datetime as dt
        from ..plant_settings import PlantSettings
        w = PlantSettings.load(self.settings_file.parent).weekly
        if not w.enabled:
            return False
        d = dt.datetime.fromtimestamp(now)
        slot = (d - dt.timedelta(days=(d.weekday() - w.weekday) % 7)).replace(hour=w.hour, minute=0, second=0,
                                                                                 microsecond=0)
        if slot > d:
            slot -= dt.timedelta(days=7)
        return w.last < slot.timestamp()

    def send_weekly(self, force: bool = False, now: Optional[float] = None) -> Optional[Path]:
        """Reporte de la planta de los últimos 7 días (PDF) a la carpeta «reportes» y por correo o mensaje."""
        from ..plant_settings import PlantSettings
        from .fleet_analyzer import FleetAnalyzer
        now = now or time.time()
        if not force and not self.weekly_due(now):
            return None
        home = self.settings_file.parent
        an = FleetAnalyzer(lambda: self.reader, home)
        an.cmb_period.setCurrentIndex(max(0, an.cmb_period.findData(7 * 86400)))
        title = tr("Reporte semanal de planta") + " · " + time.strftime("%d/%m/%Y", time.localtime(now))
        try:
            path = an.write_pdf(home / "reportes" / time.strftime("Planta_semanal_%Y%m%d.pdf", time.localtime(now)), title)
        except Exception:
            import logging
            logging.getLogger(__name__).exception("reporte semanal")
            return None
        finally:
            an.deleteLater()
        s = PlantSettings.load(home)
        s.weekly.last = now
        s.save(home)
        self.notifier.emit("report", f"weekly:{int(now)}", title, tr("Reporte semanal de la planta (adjunto)."),
                           "INFO", attachment=path, force=True)
        return path

    EXPORT_CONTENTS = [("summary", "Resumen actual de las líneas"),
                       ("trend1", "Datos por minuto de las líneas (últimas 24 h)"),
                       ("trend7", "Datos por minuto de las líneas (últimos 7 días)")]

    def export_csv(self, path: Optional[str] = None, fmt: Optional[str] = None,
                   content: str = "summary") -> Optional[str]:
        """Exportar: resumen de las líneas o sus datos por minuto, en CSV, Excel o para software estadístico."""
        from .export_dialog import export_table
        return export_table(self, "Exportar resumen de líneas", "lineas", self._export_rows, self.EXPORT_CONTENTS,
                            path=path, fmt=fmt, content=content if fmt else None)

    def _export_rows(self, content: str) -> tuple[list[str], list[list]]:
        from ..tabular import epoch
        lines = sorted(self.reader.lines.values(), key=lambda ln: natural(ln.name))
        if content.startswith("trend"):
            return self._export_trend(lines, 86400 * (7 if content == "trend7" else 1))
        now = time.time()
        s = self.settings
        cols = ["linea", "id", "area", "comunicacion", "estado", "receta", "oee_%", "disponibilidad_%",
                "rendimiento_%", "calidad_%", "producido", "conforme", "unidad", "paros", "alarmas", "avisos",
                "actualizado"]
        rows = []
        for ln in lines:
            st = ln.status
            k = st.get("kpis") or {}
            o = st.get("oee") or {}

            def num(v, d=1):
                return None if v is None else round(float(v), d)

            rows.append([ln.name, ln.line_id, s.area_of(ln), tr(CONN_TEXT[ln.connection(now, s.offline_s)]),
                         (st.get("machine") or {}).get("label", ""), st.get("recipe") or "",
                         num(k.get("oee")), num(k.get("availability")), num(k.get("performance")),
                         num(k.get("quality")), num(o.get("length_total"), 0), num(o.get("length_good"), 0),
                         o.get("unit", ""), o.get("n_stops"), st.get("n_alarms", 0), st.get("n_warnings", 0),
                         epoch(st.get("ts"))])
        return [tr(c) for c in cols], rows

    def _export_trend(self, lines: list, span: float) -> tuple[list[str], list[list]]:
        """Formato largo para análisis: una fila por línea y minuto, una columna por variable e indicador."""
        from ..analysis.oee import STATE_LABELS
        from ..fleet_data import FleetHistorian, line_variables
        from ..tabular import epoch
        now = time.time()
        names: dict[str, str] = {}
        for ln in lines:
            for v in line_variables(ln):
                if v.get("kind") not in ("text", "selector"):
                    unit = f" ({v['unit']})" if v.get("unit") else ""
                    names.setdefault(v["id"], (v.get("name") or v["id"]) + unit)
        kpis = [("oee", "OEE %"), ("availability", "Disponibilidad %"), ("performance", "Rendimiento %"),
                ("quality", "Calidad %"), ("stability", "Estabilidad %"), ("i5", "Índice 5.0")]
        rows_by = FleetHistorian(self.reader).rows_by_line(now - span, now)
        used_v = [vid for vid in names if any(vid in (r.get("v") or {}) for rs in rows_by.values() for r in rs)]
        used_k = [(k, lb) for k, lb in kpis if any(k in (r.get("k") or {}) for rs in rows_by.values() for r in rs)]
        header = [tr("fecha_hora"), tr("linea"), tr("estado"), tr("usuario")] + [names[v] for v in used_v] + \
            [tr(lb) for _k, lb in used_k]
        out = []
        for ln in lines:
            for r in rows_by.get(ln.name, []):
                v, k = r.get("v") or {}, r.get("k") or {}
                out.append([epoch(r.get("ts")), ln.name, tr(STATE_LABELS.get(r.get("s"), r.get("s") or "")),
                            r.get("u") or ""] +
                           [(v[vid][0] if isinstance(v[vid], list) else v[vid]) if vid in v else None
                            for vid in used_v] + [k.get(key) for key, _lb in used_k])
        out.sort(key=lambda row: (row[0] is None, row[0] or 0, row[1]))
        return header, out

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._layout_key = None
        if self.cards:
            QTimer.singleShot(0, lambda: self.refresh(rescan=False))


rebuilt_fleet_windows: list = []  # referencia a la ventana nueva tras cambiar idioma o tema


def run_fleet(folder: Optional[str], home: Optional[Path] = None) -> int:
    import sys

    from ..config import default_home
    from ..i18n import Translator
    from ..logsetup import setup_logging, show_startup_error
    from .main_window import apply_ui_prefs

    home_dir = Path(home) if home else default_home()
    log_path = setup_logging(home_dir, "fleet")
    app = QApplication.instance() or QApplication(sys.argv[:1])
    app.setApplicationName("Dashboard global de líneas")
    app.setWindowIcon(theme.app_icon("dashboard"))
    try:
        state = json.loads((home_dir / "state.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        state = {}
    try:
        apply_ui_prefs(state.get("ui", {}))
        Translator().install(app)
        win = FleetWindow(folder, home_dir / "fleet.json", home_dir / "state.json")
    except Exception as exc:
        show_startup_error(exc, log_path)
        return 1
    win.show()
    if not win.settings.dir:
        QTimer.singleShot(300, win.open_setup)  # primera vez: pedir la carpeta de datos
    return app.exec()
