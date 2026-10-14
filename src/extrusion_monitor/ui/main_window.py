"""Ventana principal: menú superior, barra lateral de navegación y páginas (inicio, variables, análisis…)."""
from __future__ import annotations

import time
from typing import Optional

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import QEvent, Qt, QTimer, QUrl
from PySide6.QtGui import QAction, QActionGroup, QBrush, QColor, QDesktopServices
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QFileDialog, QFrame, QHeaderView, QLabel, QListWidget,
    QHBoxLayout, QListWidgetItem, QMainWindow, QMenu, QMessageBox, QSplitter, QStackedWidget, QTableWidget,
    QTableWidgetItem, QTabWidget, QToolButton, QVBoxLayout, QWidget,
)

from .. import version_label
from ..analysis.rules import Level
from ..bootstrap import AppContext, make_clicker, make_ocr
from ..capture import ScreenSource
from ..navigation import exclude_window_from_capture
from ..engine import Snapshot
from ..recipes import Bounds
from ..i18n import LANGS, lang as i18n_lang, tr, translate_text
from . import theme
from .common import (  # noqa: F401 (y_range se reexporta)
    SeriesCache, SnapshotBridge, level_color, level_text, level_text_color, y_range,
)
from .variable_tree import VariableTree
from .kpi_dashboard import KpiDashboard
from .analysis_panels import BehaviorPanel, CorrelationPanel, StatsPanel
from ..analysis.statistics import projection

MAX_PLOTS = 4


RANGES = [("5 min", 300), ("15 min", 900), ("30 min", 1800), ("1 h", 3600), ("4 h", 4 * 3600),
          ("8 h", 8 * 3600), ("24 h", 86400), ("7 días", 7 * 86400)]


NAV_ITEMS = [("home", "Inicio", "🏠"), ("variables", "Variables en vivo", "📟"), ("trends", "Tendencias", "📈"),
             ("kpi", "KPI / OEE", "🏭"), ("spc", "SPC", "📊"), ("corr", "Correlación", "🔗"),
             ("behavior", "Estabilidad (IA)", "🧠"), ("events", "Alarmas y eventos", "🔔")]
NAV_TOOLS = [("recipes", "Recetas", "📋"), ("reports", "Reportes", "📄"), ("setup", "Configurar receta", "⚙")]
HELP_URL = "https://github.com/LuisLegarda/Extrusion-AI-agent#readme"


class TrendPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout_ = QVBoxLayout(self)
        self.layout_.setContentsMargins(0, 0, 0, 0)
        self.plots: dict[str, dict] = {}
        bar = QHBoxLayout()
        bar.setContentsMargins(4, 2, 4, 0)
        bar.addWidget(QLabel("Rango:"))
        self.cmb_range = QComboBox()
        for label, secs in RANGES:
            self.cmb_range.addItem(label, secs)
        self.cmb_range.setCurrentIndex(1)
        self.cmb_range.setToolTip("Tiempo mostrado. Más allá de la ventana en memoria se lee del historial.")
        bar.addWidget(self.cmb_range)
        self.chk_auto_y = QCheckBox("Escala Y automática (según límites)")
        self.chk_auto_y.setChecked(True)
        self.chk_auto_y.setToolTip("La escala se ajusta a los límites de la variable y a los datos visibles; "
                                   "un pico solo la amplía mientras está en pantalla. "
                                   "Desmárcala para hacer zoom manual con el mouse.")
        bar.addWidget(self.chk_auto_y)
        bar.addStretch(1)
        self.layout_.addLayout(bar)
        self.placeholder = QLabel("Marca la casilla de una variable para graficar su tendencia.")
        self.placeholder.setAlignment(Qt.AlignCenter)
        self.layout_.addWidget(self.placeholder)

    def set_variables(self, items: list[tuple[str, str]]) -> None:
        wanted = [vid for vid, _ in items]
        for vid in list(self.plots):
            if vid not in wanted:
                w = self.plots.pop(vid)["widget"]
                self.layout_.removeWidget(w)
                w.deleteLater()
        for vid, title in items:
            if vid in self.plots:
                continue
            w = pg.PlotWidget(axisItems={"bottom": pg.DateAxisItem()})
            w.setTitle(title)
            w.setClipToView(True)
            w.setDownsampling(auto=True, mode="peak")
            w.showGrid(x=True, y=True, alpha=0.3)
            curve = w.plot(pen=pg.mkPen(theme.c("measure"), width=2), name=tr("medición"))
            sp_curve = w.plot(pen=pg.mkPen(theme.c("setpoint"), width=2, style=Qt.DashLine), name=tr("consigna"))
            proj = w.plot(pen=pg.mkPen(theme.c("projection"), width=2, style=Qt.DotLine), name=tr("proyección"))
            proj_lo = pg.PlotDataItem(pen=pg.mkPen(None))
            proj_hi = pg.PlotDataItem(pen=pg.mkPen(None))
            pc = QColor(theme.c("projection"))
            pc.setAlpha(45)
            band = pg.FillBetweenItem(proj_lo, proj_hi, brush=pg.mkBrush(pc))
            w.addItem(proj_lo)
            w.addItem(proj_hi)
            w.addItem(band)
            eta = pg.TextItem(color=theme.c("projection"), anchor=(1, 1))
            w.addItem(eta)
            lines = {
                "ref": pg.InfiniteLine(angle=0, pen=pg.mkPen(theme.c("reference"), style=Qt.DashLine)),
                "wl": pg.InfiniteLine(angle=0, pen=pg.mkPen(theme.c("warning"))),
                "wh": pg.InfiniteLine(angle=0, pen=pg.mkPen(theme.c("warning"))),
                "al": pg.InfiniteLine(angle=0, pen=pg.mkPen(theme.c("critical"), width=2)),
                "ah": pg.InfiniteLine(angle=0, pen=pg.mkPen(theme.c("critical"), width=2)),
            }
            for ln in lines.values():
                ln.setVisible(False)
                w.addItem(ln)
            self.layout_.addWidget(w)
            self.plots[vid] = {"widget": w, "curve": curve, "sp": sp_curve, "lines": lines,
                               "proj": proj, "proj_lo": proj_lo, "proj_hi": proj_hi, "eta": eta}
        self.placeholder.setVisible(not self.plots)

    @property
    def range_s(self) -> float:
        return float(self.cmb_range.currentData())

    def _fit_view(self, w, t, y, ref, bounds, pr) -> None:
        if not len(t):
            return
        now = float(t[-1])
        end = float(pr["t"][-1]) if pr is not None else now
        w.setXRange(now - self.range_s, max(end, now), padding=0.01)
        if self.chk_auto_y.isChecked():
            alarm = [bounds.al, bounds.ah] if bounds.al is not None or bounds.ah is not None else [bounds.wl, bounds.wh]
            yr = y_range(np.asarray(y)[np.asarray(t) >= now - self.range_s], alarm + [ref])
            if yr is not None:
                w.setYRange(*yr, padding=0)

    def update_plot(self, vid: str, t, y, ref: Optional[float], bounds: Bounds = Bounds(),
                    sp_series=None, horizon_s: float = 0.0, fit_s: float = 0.0) -> None:
        p = self.plots.get(vid)
        if not p:
            return
        p["curve"].setData(t, y)
        pr = projection(t, y, horizon_s, fit_s) if horizon_s > 0 else None
        if pr is not None:
            p["proj"].setData(pr["t"], pr["y"])
            p["proj_lo"].setData(pr["t"], pr["lo"])
            p["proj_hi"].setData(pr["t"], pr["hi"])
            end = float(pr["y"][-1])
            text = tr("en {m} min: {v}", m=f"{horizon_s / 60:.0f}", v=f"{end:.4g}")
            if (bounds.ah is not None and end > bounds.ah) or (bounds.al is not None and end < bounds.al):
                text += tr("  ⚠ fuera de alarma")
            p["eta"].setText(text)
            p["eta"].setPos(float(pr["t"][-1]), end)
        else:
            for k in ("proj", "proj_lo", "proj_hi"):
                p[k].setData([], [])
            p["eta"].setText("")
        if sp_series is not None and len(sp_series[0]):
            # La consigna es escalonada: se prolonga hasta el último instante de la medición.
            st, sy = sp_series
            if len(t) and t[-1] > st[-1]:
                st, sy = np.append(st, t[-1]), np.append(sy, sy[-1])
            p["sp"].setData(st, sy)
        self._fit_view(p["widget"], t, y, ref, bounds, pr)
        lines = p["lines"]
        for key, val in (("ref", ref), ("wl", bounds.wl), ("wh", bounds.wh), ("al", bounds.al), ("ah", bounds.ah)):
            lines[key].setVisible(val is not None)
            if val is not None:
                lines[key].setValue(val)


class MainWindow(QMainWindow):
    def __init__(self, ctx: AppContext):
        super().__init__()
        self.ctx = ctx
        self.engine = ctx.engine
        self._config_version = ctx.engine.config_version
        self._prompts: dict = {}
        self._series = SeriesCache(ctx.engine)
        self.bridge = SnapshotBridge()
        self.bridge.snapshot.connect(self.on_snapshot, Qt.QueuedConnection)
        self.engine.listeners.append(self.bridge.snapshot.emit)
        self._plotted: list[str] = []
        self._rebuilding = False
        self.dock = None  # barra compacta que queda sobre el HMI al minimizar (se crea al usarla)
        self._build_ui()
        self.rebuild_table()
        self.refresh_recipes()
        self._update_title()

    # --- construcción -------------------------------------------------------
    def _build_ui(self) -> None:
        self.resize(1440, 880)
        self._build_actions()
        self._build_menus()

        central = QWidget()
        outer = QHBoxLayout(central)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(self._build_sidebar())
        right = QWidget()
        right.setObjectName("content")
        rl = QVBoxLayout(right)
        rl.setContentsMargins(10, 8, 10, 6)
        rl.addLayout(self._build_header())
        self.stack = QStackedWidget()
        rl.addWidget(self.stack, 1)
        outer.addWidget(right, 1)
        self.setCentralWidget(central)

        # --- páginas ---
        from .home_page import HomePage
        self.home = HomePage(self.engine)
        self.home.navigate.connect(self.show_page)
        self.home.customize.connect(self.open_home_config)

        self.table = VariableTree()
        self.table.quality_fn = lambda vid: self.engine.acquirer.quality(vid)
        self.table.plotToggled.connect(self._plot_toggled)

        self.trends = TrendPanel()
        self.trends.cmb_range.currentIndexChanged.connect(self._replot)
        self.trends.chk_auto_y.toggled.connect(self._replot)
        self.plot_list = QListWidget()
        self.plot_list.setMaximumWidth(280)
        self.plot_list.setTextElideMode(Qt.ElideRight)
        self.plot_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.plot_list.itemChanged.connect(self._plot_list_changed)
        trends_page = QSplitter(Qt.Horizontal)
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        ll.addWidget(QLabel(f"<b>{tr('Variables a graficar')}</b> {tr('(máx. {n})', n=MAX_PLOTS)}"))
        ll.addWidget(self.plot_list, 1)
        trends_page.addWidget(left)
        trends_page.addWidget(self.trends)
        trends_page.setSizes([240, 1100])

        self.stats_panel = StatsPanel(self.engine)
        self.corr_panel = CorrelationPanel(self.engine)
        self.behavior_panel = BehaviorPanel(self.engine)
        self.analysis_pages = (self.stats_panel, self.corr_panel, self.behavior_panel)
        self._analysis_at = 0.0
        self.kpi = KpiDashboard(self.engine)

        tabs = QTabWidget()
        self.findings = QTableWidget(0, 5)
        self.findings.setHorizontalHeaderLabels(["Desde", "Nivel", "Regla", "Variable", "Descripción"])
        self.findings.verticalHeader().setVisible(False)
        self.findings.setEditTriggers(QTableWidget.NoEditTriggers)
        self.findings.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.findings.horizontalHeader().setStretchLastSection(True)
        tabs.addTab(self.findings, "Hallazgos activos")
        self.log = QListWidget()
        tabs.addTab(self.log, "Registro de eventos")
        self.tabs = tabs

        from .reports_page import ReportsPage
        self.reports_page = ReportsPage(self.ctx, self)

        self.pages: dict[str, QWidget] = {}
        for key, w in (("home", self.home), ("variables", self.table), ("trends", trends_page), ("kpi", self.kpi),
                       ("spc", self.stats_panel), ("corr", self.corr_panel), ("behavior", self.behavior_panel),
                       ("events", tabs), ("reports", self.reports_page)):
            self.pages[key] = w
            self.stack.addWidget(w)
        self.stack.currentChanged.connect(self._page_changed)
        self.show_page("home")

        self.lbl_tour = QLabel()
        self.lbl_page = QLabel()
        self.lbl_ocr = QLabel()
        self.lbl_cycle = QLabel()
        self.lbl_export = QLabel()
        for w in (self.lbl_tour, self.lbl_page, self.lbl_ocr, self.lbl_export, self.lbl_cycle):
            self.statusBar().addPermanentWidget(w)

    # --- acciones y menús ---------------------------------------------------------
    def _build_actions(self) -> None:
        self.act_run = QAction("▶ Iniciar monitoreo", self)
        self.act_run.setShortcut("F5")
        self.act_run.triggered.connect(self.toggle_run)
        self.act_auto = QAction("Cargar automáticamente la receta del HMI", self, checkable=True)
        self.act_auto.setChecked(self.engine.state.auto_recipe)
        self.act_tour_pause = QAction("⏸ Pausar recorridos", self, checkable=True)
        self.act_tour_pause.setToolTip("Detiene los clics automáticos en el HMI (se siguen leyendo los datos visibles)")
        self.act_tour_pause.toggled.connect(self._tour_pause)
        self.act_top = QAction("📌 Siempre visible", self, checkable=True)
        self.act_top.toggled.connect(self._always_on_top)
        self._tour_menu = QMenu("⟳ Ejecutar recorrido ahora", self)
        self._tour_menu.aboutToShow.connect(self._fill_tour_menu)
        self._report_menu = QMenu("📄 Generar reporte ahora", self)
        self._report_menu.aboutToShow.connect(self._fill_report_menu)

    def _build_menus(self) -> None:
        """Misma estructura que el dashboard global: Archivo · Receta · Acciones · Configuración · Ver · Ayuda."""
        mb = self.menuBar()
        # --- Archivo: el monitoreo y sus datos ---
        m = mb.addMenu("&Archivo")
        m.addAction(self.act_run)
        m.addSeparator()
        act = m.addAction("⤓ Exportar historial a CSV…", self.export_csv)
        act.setShortcut("Ctrl+E")
        m.addAction("📂 Abrir carpeta de reportes", self._open_reports_dir)
        m.addAction("📂 Abrir carpeta de datos", lambda: self._open_dir(self.ctx.workspace.home))
        m.addSeparator()
        m.addAction("🛟 Crear respaldo de la configuración", self._backup_now)
        m.addAction("📂 Abrir carpeta de respaldos", self._open_backups)
        m.addSeparator()
        act = m.addAction("Salir", self.close)
        act.setShortcut("Ctrl+Q")

        # --- Receta: la receta activa y todo lo que se guarda con ella ---
        m = mb.addMenu("&Receta")
        self._recipe_menu = m.addMenu("Receta activa")
        self._recipe_menu.aboutToShow.connect(self._fill_recipe_menu)
        m.addAction(self.act_auto)
        act = m.addAction("📋 Recetas y límites…", self.open_recipes)
        act.setShortcut("Ctrl+R")
        m.addSection("Configuración de la receta")
        for label, tab in (("Pestañas y variables…", "Pestañas y variables"),
                           ("Recorridos…", "Recorrido automático"), ("KPI / OEE…", "KPI / OEE"),
                           ("Reportes automáticos…", "Reportes"),
                           ("Lectura y análisis (general)…", "General")):
            m.addAction(label, lambda tab=tab: self.open_setup(tab))
        m.addAction("📹 Cámaras (equipos sin pantalla)…", lambda: self.open_setup(cameras=True))
        m.addAction("🧠 Comportamiento (entrenar)…", self.open_behavior)
        m.addAction("✎ Tablero de Inicio…", self.open_home_config)
        m.addAction("▭ Dock al minimizar…", self.open_dock_config)

        # --- Acciones: lo que se hace en el momento ---
        m = mb.addMenu("A&cciones")
        m.addAction(self.act_tour_pause)
        m.addMenu(self._tour_menu)
        m.addMenu(self._report_menu)

        # --- Configuración: ajustes de este equipo (no cambian con la receta) ---
        m = mb.addMenu("C&onfiguración")
        m.addAction("🌐 Dashboard global (exportación)…", self.open_station)
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

        # --- Ver: páginas y modos de pantalla ---
        m = mb.addMenu("&Ver")
        for i, (key, label, _icon) in enumerate(NAV_ITEMS + [("reports", "Reportes", "")], 1):
            act = m.addAction(label, lambda key=key: self.show_page(key))
            act.setShortcut(f"Ctrl+{i}")
        m.addSeparator()
        m.addAction(self.act_top)
        act = m.addAction("Pantalla completa", self._toggle_fullscreen)
        act.setShortcut("F11")
        act = m.addAction("▭ Minimizar a dock", self.minimize_to_dock)
        act.setShortcut("Ctrl+D")

        m = mb.addMenu("A&yuda")
        act = m.addAction("Manual de uso", lambda: self._open_url(HELP_URL))
        act.setShortcut("F1")
        m.addAction("Acerca de…", self._about)

    def _build_sidebar(self) -> QWidget:
        side = QWidget()
        side.setObjectName("sidebar")
        side.setFixedWidth(215)
        lay = QVBoxLayout(side)
        lay.setContentsMargins(10, 14, 10, 10)
        logo = QLabel(f"<div style='font-size:20px; color:{theme.c('accent')}'><b>⫶⫶ Extrusion</b></div>"
                      f"<div style='color:{theme.c('muted')}'>{tr('Monitor de línea')}</div>")
        logo.setAlignment(Qt.AlignCenter)
        lay.addWidget(logo)
        lay.addSpacing(12)
        self.nav = QListWidget()
        self.nav.setObjectName("nav")
        self.nav.setFocusPolicy(Qt.NoFocus)
        self.nav.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        for key, label, icon in NAV_ITEMS:
            it = QListWidgetItem(f"{icon}  {label}")
            it.setData(Qt.UserRole, key)
            self.nav.addItem(it)
        self.nav.setFixedHeight(len(NAV_ITEMS) * 38 + 6)
        self.nav.currentItemChanged.connect(self._nav_changed)
        lay.addWidget(self.nav)
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setStyleSheet(f"color:{theme.c('sidebar_border')};")
        lay.addWidget(line)
        self.nav2 = QListWidget()
        self.nav2.setObjectName("nav")
        self.nav2.setFocusPolicy(Qt.NoFocus)
        for key, label, icon in NAV_TOOLS:
            it = QListWidgetItem(f"{icon}  {label}")
            it.setData(Qt.UserRole, key)
            self.nav2.addItem(it)
        self.nav2.setFixedHeight(len(NAV_TOOLS) * 38 + 6)
        self.nav2.itemClicked.connect(self._tool_clicked)
        lay.addWidget(self.nav2)
        lay.addStretch(1)
        self.lbl_side_status = QLabel()
        self.lbl_side_status.setWordWrap(True)
        self.lbl_side_status.setStyleSheet(f"color:{theme.c('muted')}; font-size:11px;")
        lay.addWidget(self.lbl_side_status)
        return side

    def _build_header(self) -> QHBoxLayout:
        row = QHBoxLayout()
        self.lbl_title = QLabel()
        row.addWidget(self.lbl_title)
        self.banner = QLabel("DETENIDO")
        self.banner.setObjectName("banner")
        self._set_banner(None, "DETENIDO")
        row.addWidget(self.banner, 1)
        row.addSpacing(8)
        row.addWidget(QLabel("Receta:"))
        self.cmb_recipe = QComboBox()
        self.cmb_recipe.setMinimumWidth(230)
        self.cmb_recipe.activated.connect(self._recipe_chosen)
        row.addWidget(self.cmb_recipe)
        self.chk_auto = QCheckBox("Auto desde HMI")
        self.chk_auto.setChecked(self.engine.state.auto_recipe)
        self.chk_auto.toggled.connect(self._auto_toggled)
        self.act_auto.toggled.connect(self.chk_auto.setChecked)
        self.chk_auto.toggled.connect(self.act_auto.setChecked)
        row.addWidget(self.chk_auto)
        self.btn_run = QToolButton()
        self.btn_run.setObjectName("run")
        self.btn_run.setDefaultAction(self.act_run)
        row.addWidget(self.btn_run)
        return row

    # --- navegación -----------------------------------------------------------------
    def show_page(self, key: str) -> None:
        w = self.pages.get(key)
        if w is None:
            return
        self.stack.setCurrentWidget(w)
        for i in range(self.nav.count()):
            if self.nav.item(i).data(Qt.UserRole) == key:
                self.nav.blockSignals(True)
                self.nav.setCurrentRow(i)
                self.nav.blockSignals(False)
                break

    def current_page(self) -> str:
        w = self.stack.currentWidget()
        return next((k for k, v in self.pages.items() if v is w), "")

    def _nav_changed(self, item, _prev) -> None:
        if item is not None:
            self.show_page(item.data(Qt.UserRole))

    def _tool_clicked(self, item) -> None:
        key = item.data(Qt.UserRole)
        self.nav2.clearSelection()
        if key == "recipes":
            self.open_recipes()
        elif key == "setup":
            self.open_setup()
        else:
            self.show_page(key)

    def _page_changed(self, _index: int) -> None:
        self._refresh_analysis(force=True)
        snap = self.engine.last
        if snap is not None and self.stack.currentWidget() is self.home:
            self.home.update_snapshot(snap, force=True)
        if self.stack.currentWidget() is self.pages.get("trends"):
            self._replot()
        if snap is not None and self.stack.currentWidget() is self.table:
            self._update_table(snap)

    def _fill_recipe_menu(self) -> None:
        self._recipe_menu.clear()
        group = QActionGroup(self._recipe_menu)
        for name in [None] + self.ctx.recipes.names():
            act = self._recipe_menu.addAction(name or "— sin receta —")
            act.setCheckable(True)
            act.setChecked(name == self.engine.state.recipe)
            group.addAction(act)
            act.triggered.connect(lambda _=False, n=name: self._choose_recipe(n))

    def _choose_recipe(self, name: Optional[str]) -> None:
        idx = self.cmb_recipe.findData(name)
        if idx >= 0:
            self.cmb_recipe.setCurrentIndex(idx)
            self._recipe_chosen(idx)

    def _open_dir(self, path) -> None:
        from pathlib import Path
        d = Path(path)
        d.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(d)))

    def _backup_now(self) -> None:
        from ..backup import create_backup, prune
        try:
            out = create_backup(self.ctx.workspace.home, "manual")
            prune(self.ctx.workspace.home)
        except OSError as e:
            QMessageBox.warning(self, "Respaldo", f"{tr('No se pudo crear el respaldo')}: {e}")
            return
        QMessageBox.information(self, "Respaldo", f"{tr('Respaldo creado')}:\n{out}")

    def _open_backups(self) -> None:
        from ..backup import backups_dir
        self._open_dir(backups_dir(self.ctx.workspace.home))

    def _open_url(self, url: str) -> None:
        QDesktopServices.openUrl(QUrl(url))

    def _toggle_fullscreen(self) -> None:
        self.showNormal() if self.isFullScreen() else self.showFullScreen()

    def _about(self) -> None:
        QMessageBox.about(self, "Acerca de", tr("<b>Monitor de extrusión</b><br>Verificación de parámetros, recetas, "
                                             "tendencias, KPI/OEE y reportes a partir de la pantalla del HMI.<br>"
                                             "Solo lee la pantalla: no modifica el PLC ni el software del fabricante.")
                          + f"<br><br>{tr('Versión')}: {version_label()}")

    def _update_title(self) -> None:
        demo = tr(" — MODO DEMO (HMI simulado)") if self.ctx.demo else ""
        self.setWindowTitle(f"{tr('Monitor de extrusión')} · {self.ctx.config.machine_name}{demo}")
        self.lbl_title.setText(f"<span style='font-size:17px; color:{theme.c('title')}'>"
                               f"<b>{self.ctx.config.machine_name}</b></span>"
                               f"<span style='color:{theme.c('critical')}'>{'  DEMO' if self.ctx.demo else ''}</span>")

    def _set_banner(self, level: Optional[Level], text: str) -> None:
        self.banner.setText(text)
        self.banner.setStyleSheet(f"background:{level_color(level).name()}; color:{level_text_color(level).name()};")

    def rebuild_table(self) -> None:
        cfg = self.ctx.config
        if not self._plotted:
            self._plotted = [v.id for v in cfg.variables if v.measured and v.trend][:3]
        self._plotted = [vid for vid in self._plotted if cfg.variable(vid)]
        self.table.rebuild(cfg, self._plotted)
        self.plot_list.blockSignals(True)
        self.plot_list.clear()
        for v in cfg.variables:
            if v.numeric:
                it = QListWidgetItem(VariableTree.title(v, cfg))
                it.setToolTip(VariableTree.title(v, cfg))
                it.setData(Qt.UserRole, v.id)
                it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
                it.setCheckState(Qt.Checked if v.id in self._plotted else Qt.Unchecked)
                self.plot_list.addItem(it)
        self.plot_list.blockSignals(False)
        self._sync_plots()
        self.stats_panel.set_variables(cfg)
        self.corr_panel.set_variables(cfg, self._plotted)
        self.behavior_panel.set_models()
        self.home.rebuild()
        if self.dock is not None:
            self.dock.rebuild()

    def _sync_plots(self) -> None:
        cfg = self.ctx.config
        items = []
        for vid in self._plotted:
            v = cfg.variable(vid)
            if v:
                items.append((vid, VariableTree.title(v, cfg)))
        self.trends.set_variables(items)

    def _plot_toggled(self, vid: str, on: bool) -> None:
        if on and vid not in self._plotted:
            self._plotted.append(vid)
            if len(self._plotted) > MAX_PLOTS:
                old = self._plotted.pop(0)
                self.table.set_checked(old, False)
                self._set_plot_item(old, False)
        elif not on and vid in self._plotted:
            self._plotted.remove(vid)
        self._set_plot_item(vid, on)
        self._sync_plots()
        if self.engine.last:
            self._update_plots(self.engine.last)

    def _set_plot_item(self, vid: str, on: bool) -> None:
        self.plot_list.blockSignals(True)
        for i in range(self.plot_list.count()):
            it = self.plot_list.item(i)
            if it.data(Qt.UserRole) == vid:
                it.setCheckState(Qt.Checked if on else Qt.Unchecked)
        self.plot_list.blockSignals(False)

    def _plot_list_changed(self, item) -> None:
        vid, on = item.data(Qt.UserRole), item.checkState() == Qt.Checked
        self.table.set_checked(vid, on)
        self._plot_toggled(vid, on)

    # --- recetas -------------------------------------------------------------
    def refresh_recipes(self) -> None:
        self.cmb_recipe.blockSignals(True)
        self.cmb_recipe.clear()
        self.cmb_recipe.addItem("— sin receta —", None)
        for name in self.ctx.recipes.names():
            self.cmb_recipe.addItem(name, name)
        idx = self.cmb_recipe.findData(self.engine.state.recipe)
        self.cmb_recipe.setCurrentIndex(max(0, idx))
        self.cmb_recipe.blockSignals(False)

    def _recipe_chosen(self, index: int) -> None:
        name = self.cmb_recipe.itemData(index)
        # Elegir manualmente una receta desactiva la selección automática.
        if self.chk_auto.isChecked() and self.ctx.config.general.recipe_name_var:
            self.chk_auto.setChecked(False)
        self.engine.set_recipe(name)
        self._save_state()

    def _auto_toggled(self, on: bool) -> None:
        self.engine.set_recipe(self.engine.state.recipe, auto=on)
        self._save_state()

    def _save_state(self) -> None:
        state = self.ctx.workspace.load_state()
        state.update({"recipe": self.engine.state.recipe, "auto_recipe": self.engine.state.auto_recipe})
        self.ctx.workspace.save_state(state)

    # --- acciones --------------------------------------------------------------
    def toggle_run(self) -> None:
        if self.engine.running:
            self.engine.stop()
            self.act_run.setText(tr("▶ Iniciar monitoreo"))
            self._set_banner(None, tr("DETENIDO"))
        else:
            if not self.ctx.config.variables:
                QMessageBox.information(self, tr("Sin variables"),
                                        tr("Primero configura las variables a leer del HMI."))
                return
            self.engine.start()
            self.act_run.setText(tr("■ Detener monitoreo"))

    def open_setup(self, tab: Optional[str] = None, cameras: bool = False) -> None:
        from .setup_dialog import SetupDialog
        was_running = self.engine.running
        # Durante la configuración el monitoreo (y su recorrido con clics) se detiene.
        self.engine.stop()
        dlg = SetupDialog(self.ctx, self)
        if tab:
            for i in range(dlg.tabs.count()):
                if dlg.tabs.tabText(i) == tab:
                    dlg.tabs.setCurrentIndex(i)
                    break
        if cameras:
            QTimer.singleShot(0, dlg._open_cameras)
        accepted = dlg.exec()
        if accepted:
            if not self.ctx.demo and dlg.config.general.monitor != self.ctx.config.general.monitor:
                self.engine.source = ScreenSource(dlg.config.general.monitor)
                self.engine.clicker = make_clicker(self.engine.source)
            self.ctx.config = dlg.config
            self.engine.reconfigure(dlg.config, make_ocr(self.ctx))
            self._save_profile()  # la receta activa guarda la configuración completa
            self.rebuild_table()
            self._update_title()
        if was_running:
            self.engine.start()

    def _save_profile(self) -> None:
        err = self.engine.save_profile()
        if err:
            QMessageBox.warning(self, tr("Receta no actualizada"),
                                err + "\n\n" + tr("La configuración quedó guardada, pero si cambias de receta y vuelves "
                                                   "se cargará la versión anterior. Cierra programas que tengan abierta "
                                                   "la carpeta de datos y vuelve a guardar."))

    def open_station(self) -> None:
        from .station_dialog import StationDialog
        ex = self.ctx.exporter
        if ex is None:
            return
        dlg = StationDialog(ex, self)
        if dlg.exec():
            ex.reconfigure(dlg.settings())
            ex.start()
            self._update_export_label()

    def _update_export_label(self) -> None:
        ex = self.ctx.exporter
        if ex is None or ex.line_dir is None:
            self.lbl_export.setText("")
            return
        if ex.last_error:
            self.lbl_export.setText(f"<span style='color:{theme.c('critical')}'>{tr('Dashboard global: sin acceso')}</span>")
            self.lbl_export.setToolTip(ex.last_error)
        elif ex.last_ok is not None:
            self.lbl_export.setText(tr("Dashboard global: OK"))
            self.lbl_export.setToolTip(str(ex.line_dir))

    # --- dock (al minimizar) -------------------------------------------------------------
    def changeEvent(self, event) -> None:
        super().changeEvent(event)
        if event.type() == QEvent.WindowStateChange and not self._rebuilding:
            self._sync_dock()

    def _sync_dock(self) -> None:
        """Minimizado y con el dock activado: el dock queda en pantalla; al restaurar se oculta."""
        want = self.isMinimized() and self.engine.config.dock.enabled
        if want:
            if self.dock is None:
                from .dock import DockWindow
                self.dock = DockWindow(self.engine, self.ctx.workspace)
                self.dock.restore.connect(self.restore_from_dock)
            screen = self.screen() or QApplication.primaryScreen()
            self.dock.show()
            self.dock.place(screen.availableGeometry())
            if self.engine.last is not None:
                self.dock.update_snapshot(self.engine.last, force=True)
        elif self.dock is not None and self.dock.isVisible():
            self.dock.hide()

    def restore_from_dock(self) -> None:
        self.showMaximized() if self.windowState() & Qt.WindowMaximized else self.showNormal()
        self.raise_()
        self.activateWindow()

    def minimize_to_dock(self) -> None:
        if not self.engine.config.dock.enabled:
            self.open_dock_config()  # primera vez: activarlo y elegir qué muestra
            if not self.engine.config.dock.enabled:
                return
        self.showMinimized()

    def open_dock_config(self) -> None:
        from .dock_dialog import DockConfigDialog
        dlg = DockConfigDialog(self.engine.config, self)
        if not dlg.exec():
            return
        self.engine.config.dock = dlg.dock
        self.ctx.config = self.engine.config
        self.ctx.workspace.save_config(self.engine.config)
        self._save_profile()  # el dock es parte de la configuración de la receta activa
        if dlg.reset_position:
            state = self.ctx.workspace.load_state()
            if state.pop("dock_pos", None) is not None:
                self.ctx.workspace.save_state(state)
        if self.dock is not None:
            self.dock.rebuild()
        self._sync_dock()

    def open_home_config(self) -> None:
        from .home_config_dialog import HomeConfigDialog
        dlg = HomeConfigDialog(self.engine.config, self)
        if not dlg.exec():
            return
        self.engine.config.home = dlg.home
        self.ctx.config = self.engine.config
        self.ctx.workspace.save_config(self.engine.config)
        self._save_profile()  # el tablero es parte de la configuración de la receta activa
        self.home.rebuild()
        self.show_page("home")

    def open_recipes(self) -> None:
        from .recipe_dialog import RecipeDialog
        dlg = RecipeDialog(self.ctx, self)
        if dlg.exec():
            current = self.engine.state.recipe
            if current and current not in self.ctx.recipes.names():
                self.engine.set_recipe(None)
            else:
                self.engine.rules.reset()
            self.refresh_recipes()
            self._save_state()

    def export_csv(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Exportar historial (últimas 24 h)",
                                              f"historial_{time.strftime('%Y%m%d_%H%M')}.csv", "CSV (*.csv)")
        if not path:
            return
        n = self.engine.historian.export_csv(path, time.time() - 86400)
        QMessageBox.information(self, tr("Exportado"), tr("Se exportaron {n} registros.", n=n))

    def _tour_pause(self, on: bool) -> None:
        self.engine.tour_paused = on

    def showEvent(self, event) -> None:
        super().showEvent(event)
        # La ventana del monitor no debe aparecer en las capturas del HMI (Windows 10 2004+).
        exclude_window_from_capture(int(self.winId()))

    def _fill_tour_menu(self) -> None:
        self._tour_menu.clear()
        for t in self.ctx.config.tours:
            act = self._tour_menu.addAction(t.name + ("" if t.enabled else "  (desactivado)"))
            act.triggered.connect(lambda _=False, tid=t.id: self.engine.run_tour_now(tid))

    def _fill_report_menu(self) -> None:
        self._report_menu.clear()
        reps = self.ctx.config.reports
        if not reps:
            self._report_menu.addAction("Sin reportes: créalos en ⚙ Configurar → Reportes").setEnabled(False)
        for r in reps:
            act = self._report_menu.addAction(r.name)
            act.triggered.connect(lambda _=False, rid=r.id: self.engine.generate_report(rid))
        self._report_menu.addSeparator()
        self._report_menu.addAction("Abrir carpeta de reportes").triggered.connect(self._open_reports_dir)

    def _open_reports_dir(self) -> None:
        from pathlib import Path

        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices
        reps = self.ctx.config.reports
        d = Path(reps[0].output_dir) if reps and reps[0].output_dir else self.ctx.workspace.default_reports_dir()
        d.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(d)))

    def _update_prompts(self, snap: Snapshot) -> None:
        from .tour_prompt import TourPrompt
        for tid in [k for k in self._prompts if k not in snap.prompts]:
            self._prompts.pop(tid).dismiss()
        for tid, (deadline, reason) in snap.prompts.items():
            dlg = self._prompts.get(tid)
            if dlg is not None and not dlg._done:
                dlg.deadline = deadline
                continue
            t = self.ctx.config.get_tour(tid)
            dlg = TourPrompt(t.name if t else tid, reason, deadline, self.engine.clock,
                             lambda tid=tid: self.engine.confirm_tour(tid),
                             lambda tid=tid: self.engine.snooze_tour(tid), self)
            self._prompts[tid] = dlg
            dlg.show()
            dlg.raise_()

    def _update_tour_label(self) -> None:
        tours = [t for t in self.ctx.config.tours if t.enabled and t.steps]
        if not tours:
            self.lbl_tour.setText(tr("Recorrido: desactivado"))
            return
        if self.engine.tour_paused:
            self.lbl_tour.setText(tr("Recorrido: EN PAUSA"))
            return
        res = self.engine.last_tour_result
        if res is None:
            self.lbl_tour.setText(tr("Recorridos: {n} activos, pendiente", n=len(tours)))
            return
        when = time.strftime("%H:%M:%S", time.localtime(res.started))
        state = tr("OK" if res.ok else ("pospuesto" if res.skipped else "FALLÓ"))
        color = theme.c("good_text") if res.ok else (theme.c("muted") if res.skipped else theme.c("critical"))
        detail = res.message.replace("pospuesto: ", "") if res.skipped else res.message
        t = self.ctx.config.get_tour(res.tour_id)
        name = f"«{t.name}» " if t and len(tours) > 1 else ""
        label = tr("Recorrido {name}{when}: {state}", name=name, when=when, state=state)
        self.lbl_tour.setText(f"<span style='color:{color}'>{label}</span> · {detail}")

    def _always_on_top(self, on: bool) -> None:
        self.setWindowFlag(Qt.WindowStaysOnTopHint, on)
        self.show()

    # --- actualización -----------------------------------------------------------
    def on_snapshot(self, snap: Snapshot) -> None:
        if self.engine.config_version != self._config_version:
            # Se cargó el perfil de otra receta: la configuración completa cambió.
            self._config_version = self.engine.config_version
            self.ctx.config = self.engine.config
            self._plotted = []
            self.rebuild_table()
            self._update_title()
        if snap.recipe != self.cmb_recipe.currentData():
            self.refresh_recipes()
        self._update_prompts(snap)
        if self.dock is not None and self.dock.isVisible():
            self.dock.update_snapshot(snap)
        page = self.stack.currentWidget()
        # Solo se dibuja la página visible (no carga la PC con gráficas ocultas).
        if page is self.home:
            self.home.update_snapshot(snap)
        if page is self.table:
            self._update_table(snap)
        if page is self.pages["trends"]:
            self._update_plots(snap)
        self._refresh_analysis()
        self._update_findings(snap)
        self._append_events(snap)
        counts = {lvl: sum(1 for f in snap.findings if f.level == lvl) for lvl in Level}
        if snap.error:
            self._set_banner(Level.ALARM, translate_text(snap.error))
        elif self.engine.running:
            text = tr({Level.OK: "PROCESO OK", Level.INFO: "PROCESO OK",
                       Level.WARN: "AVISO", Level.ALARM: "ALARMA"}[snap.overall])
            detail = "   ·   " + tr("{n} alarmas · {m} avisos", n=counts[Level.ALARM], m=counts[Level.WARN])
            self._set_banner(snap.overall if snap.overall > Level.INFO else Level.OK, text + detail)
        pages = ", ".join(sorted(snap.pages)) or ("—" if self.ctx.config.pages else tr("sin páginas definidas"))
        self.lbl_page.setText(tr("Página HMI: {pages}", pages=pages))
        self._update_tour_label()
        self.lbl_ocr.setText(tr("OCR: {engine} · lecturas {ok}/{total}", engine=snap.ocr_engine, ok=snap.read_ok,
                                total=snap.read_total))
        stamp = time.strftime('%H:%M:%S', time.localtime(snap.ts))
        self.lbl_cycle.setText(tr("Ciclo: {ms} ms · {time}", ms=f"{snap.cycle_ms:.0f}", time=stamp))
        self._update_export_label()
        self.lbl_side_status.setText(
            f"{tr('● En monitoreo') if self.engine.running else tr('○ Detenido')}<br>"
            f"{tr('Receta: {r}', r=snap.recipe or '—')}<br>{tr('Última lectura: {t}', t=stamp)}")

    def open_behavior(self) -> None:
        from .behavior_dialog import BehaviorDialog
        BehaviorDialog(self.ctx, self, preselect=[v for v in self._plotted]).exec()
        self._save_profile()
        self.behavior_panel.set_models()

    def _refresh_analysis(self, force: bool = False) -> None:
        w = self.stack.currentWidget()
        if w not in self.analysis_pages:
            return
        now = time.monotonic()
        if not force and now - self._analysis_at < 2.0:
            return  # estadística y correlación se recalculan cada 2 s como máximo
        self._analysis_at = now
        w.refresh(self.engine.last)

    def _update_table(self, snap: Snapshot) -> None:
        self.table.update_snapshot(snap)

    def _replot(self, *_):
        if self.engine.last is not None:
            self._update_plots(self.engine.last)

    def _plot_series(self, vid: str):
        """Serie para el rango elegido: memoria (ventana de tendencia) o historial (rangos largos)."""
        return self._series.get(vid, self.trends.range_s)

    def _update_plots(self, snap: Snapshot) -> None:
        for vid in self._plotted:
            t, y = self._plot_series(vid)
            st = snap.statuses.get(vid)
            if st is None:
                continue
            sp_id = self.table.setpoint_of(vid)
            sp_series = self._plot_series(sp_id) if sp_id else None
            g = self.ctx.config.general
            self.trends.update_plot(vid, t, y, st.reference, st.bounds, sp_series,
                                    horizon_s=g.trend_horizon_min * 60,
                                    fit_s=max(120.0, g.trend_window_min * 60 / 3))

    def _update_findings(self, snap: Snapshot) -> None:
        self.findings.setRowCount(len(snap.findings))
        for i, f in enumerate(snap.findings):
            var = self.ctx.config.variable(f.var_id)
            name = var.name if var else ""
            if f.var_id.startswith("@"):
                model = self.engine.behaviors.store.get(f.var_id[1:])
                name = model.name if model else ""
            vals = [time.strftime("%H:%M:%S", time.localtime(f.since)), translate_text(f.level.label),
                    translate_text(f.rule), name, translate_text(f.message)]
            for c, text in enumerate(vals):
                it = QTableWidgetItem(text)
                if c == 1:
                    it.setBackground(QBrush(level_color(f.level)))
                    it.setForeground(QBrush(level_text_color(f.level)))
                self.findings.setItem(i, c, it)
        n_alarm = sum(1 for f in snap.findings if f.level >= Level.WARN)
        self.tabs.setTabText(0, tr("Hallazgos activos ({n})", n=n_alarm) if n_alarm else tr("Hallazgos activos"))
        for i in range(self.nav.count()):
            it = self.nav.item(i)
            if it.data(Qt.UserRole) == "events":
                it.setText(tr("🔔  Alarmas y eventos ({n})", n=n_alarm) if n_alarm else tr("🔔  Alarmas y eventos"))
                it.setForeground(QBrush(theme.qcolor("critical")) if n_alarm else QBrush())

    def _append_events(self, snap: Snapshot) -> None:
        alarm = False
        for e in snap.events:
            item = QListWidgetItem(f"{time.strftime('%H:%M:%S', time.localtime(e.ts))}  "
                                   f"[{level_text(e.level)}]  {translate_text(e.message)}")
            if e.level >= Level.WARN:
                item.setForeground(QBrush(level_color(e.level)))
            self.log.insertItem(0, item)
            if e.level == Level.ALARM and e.kind in ("raised", "escalated"):
                alarm = True
        while self.log.count() > 1000:
            self.log.takeItem(self.log.count() - 1)
        if alarm:
            if self.ctx.config.general.beep_on_alarm:
                QApplication.beep()
            QApplication.alert(self)

    def closeEvent(self, event) -> None:
        self._detach()
        if not self._rebuilding:
            self.engine.stop()
            if self.ctx.exporter is not None:
                self.ctx.exporter.stop(closed=True)  # el dashboard global muestra «programa cerrado»
            self._save_state()
            if self.engine.historian:
                self.engine.historian.close()
        super().closeEvent(event)

    def _detach(self) -> None:
        if self.dock is not None:
            self.dock.close()
            self.dock = None
        try:
            self.engine.listeners.remove(self.bridge.snapshot.emit)
        except ValueError:
            pass
        self.home.timer.stop()
        self.kpi.timer.stop()
        for dlg in self._prompts.values():
            dlg.dismiss()
        self._prompts.clear()

    # --- idioma y tema ------------------------------------------------------------
    def _set_ui_pref(self, key: str, value: str) -> None:
        state = self.ctx.workspace.load_state()
        ui = dict(state.get("ui", {}))
        if ui.get(key) == value:
            return
        ui[key] = value
        state["ui"] = ui
        self.ctx.workspace.save_state(state)
        apply_ui_prefs(ui)
        self.rebuild_window()

    def rebuild_window(self) -> "MainWindow":
        """Vuelve a construir la ventana (idioma o tema nuevos); el monitoreo sigue corriendo."""
        new = MainWindow(self.ctx)
        new.setGeometry(self.geometry())
        new._plotted = list(self._plotted)
        new.rebuild_table()
        new.act_top.setChecked(self.act_top.isChecked())
        new.act_tour_pause.setChecked(self.act_tour_pause.isChecked())
        if self.engine.running:
            new.act_run.setText(tr("■ Detener monitoreo"))
        if self.isMaximized():
            new.showMaximized()
        else:
            new.show()
        new.show_page(self.current_page())
        if self.engine.last is not None:
            new.on_snapshot(self.engine.last)
        self._rebuilding = True
        self.close()
        self.deleteLater()
        rebuilt_windows.append(new)
        return new


rebuilt_windows: list = []  # referencia a la ventana nueva tras cambiar idioma o tema


def apply_ui_prefs(ui: dict) -> None:
    """Aplica idioma y tema guardados (antes de construir la ventana)."""
    from ..i18n import set_lang
    set_lang(ui.get("lang", "es"))
    theme.set_theme(ui.get("theme", "light"))
    app = QApplication.instance()
    if app is not None:
        theme.apply(app)


def start_timer_autorun(window: MainWindow, delay_ms: int = 300) -> None:
    QTimer.singleShot(delay_ms, window.toggle_run)
