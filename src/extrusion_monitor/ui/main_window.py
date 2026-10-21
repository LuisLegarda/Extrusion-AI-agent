"""Ventana principal: menú superior, barra lateral de navegación y páginas (inicio, variables, análisis…)."""
from __future__ import annotations

import time
from typing import Optional

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import QEvent, QSize, Qt, QTimer, QUrl
from PySide6.QtGui import QAction, QActionGroup, QBrush, QColor, QDesktopServices, QShortcut
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDialog, QFileDialog, QFrame, QHeaderView, QLabel, QListWidget,
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
from ..personnel import Personnel, crew
from . import icons, theme
from .common import (  # noqa: F401 (y_range se reexporta)
    SeriesCache, SnapshotBridge, level_color, level_text, level_text_color, steady_range, y_range,
)
from .variable_tree import VariableTree
from .kpi_dashboard import KpiDashboard
from .analysis_panels import BehaviorPanel, CorrelationPanel, StatsPanel
from ..analysis.statistics import capability, projection

MAX_PLOTS = 4
NAV_ROW_H = 36  # alto de cada página en la barra lateral


RANGES = [("5 min", 300), ("15 min", 900), ("30 min", 1800), ("1 h", 3600), ("4 h", 4 * 3600),
          ("8 h", 8 * 3600), ("24 h", 86400), ("7 días", 7 * 86400)]


NAV_ITEMS = [("home", "Inicio", "🏠"), ("variables", "Variables en vivo", "📟"), ("trends", "Tendencias", "📈"),
             ("kpi", "KPI / OEE", "🏭"), ("problems", "Problemas de proceso", "⚠"), ("control", "Control", "🎛"),
             ("spc", "SPC", "📊"), ("corr", "Correlación", "🔗"), ("analysis", "Análisis estadístico", "📐"),
             ("behavior", "Estabilidad (IA)", "🧠"), ("events", "Alarmas y eventos", "🔔")]
def _close_quietly(dlg) -> None:
    """Cierra un aviso que pudo cerrarse (y destruirse) ya por su cuenta."""
    try:
        dlg.close()
    except RuntimeError:
        pass


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
        self.cmb_range.activated.connect(lambda _: self.set_marker(None))
        self.cmb_range.currentIndexChanged.connect(lambda _: self.reset_y())  # elegir otro rango quita la hora buscada
        bar.addWidget(self.cmb_range)
        self.chk_auto_y = QCheckBox("Escala Y automática (según límites)")
        self.chk_auto_y.toggled.connect(lambda _: self.reset_y())
        self.chk_auto_y.setChecked(True)
        self.chk_auto_y.setToolTip("La escala se ajusta a los límites de la variable y a los datos visibles; "
                                   "un pico solo la amplía mientras está en pantalla. "
                                   "Desmárcala para hacer zoom manual con el mouse.")
        bar.addWidget(self.chk_auto_y)
        self.chk_ctrl = QCheckBox("Límites de control y Cpk / Ppk")
        self.chk_ctrl.setChecked(True)
        self.chk_ctrl.setToolTip("LCS / LCI = media ± 3σ de corto plazo de los datos visibles (carta de individuos). "
                                 "Cpk y Ppk contra los límites de alarma de la receta.")
        bar.addWidget(self.chk_ctrl)
        bar.addStretch(1)
        self.layout_.addLayout(bar)
        self.placeholder = QLabel("Marca la casilla de una variable para graficar su tendencia.")
        self.placeholder.setAlignment(Qt.AlignCenter)
        self.layout_.addWidget(self.placeholder)
        from .resizable import ResizableStack
        self.stack = ResizableStack(min_h=150)  # alto de cada gráfica ajustable con el ratón
        self.layout_.addWidget(self.stack, 1)

    def set_variables(self, items: list[tuple[str, str]]) -> None:
        wanted = [vid for vid, _ in items]
        for vid in list(self.plots):
            if vid not in wanted:
                w = self.plots.pop(vid)["widget"]
                self.stack.remove(w)
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
            capt = pg.TextItem(anchor=(0, 0))  # Cpk / Ppk, arriba a la izquierda
            capt.setZValue(20)
            w.addItem(capt, ignoreBounds=True)
            lines = {
                "ref": pg.InfiniteLine(angle=0, pen=pg.mkPen(theme.c("reference"), style=Qt.DashLine)),
                "wl": pg.InfiniteLine(angle=0, pen=pg.mkPen(theme.c("warning"))),
                "wh": pg.InfiniteLine(angle=0, pen=pg.mkPen(theme.c("warning"))),
                "al": pg.InfiniteLine(angle=0, pen=pg.mkPen(theme.c("critical"), width=2)),
                "ah": pg.InfiniteLine(angle=0, pen=pg.mkPen(theme.c("critical"), width=2)),
                # límites de control (comportamiento del proceso, no de la receta)
                "ucl": pg.InfiniteLine(angle=0, pen=pg.mkPen(theme.c("setpoint"), width=1, style=Qt.DashDotLine),
                                       label=tr("LCS"), labelOpts={"position": 0.97, "color": theme.c("setpoint")}),
                "lcl": pg.InfiniteLine(angle=0, pen=pg.mkPen(theme.c("setpoint"), width=1, style=Qt.DashDotLine),
                                       label=tr("LCI"), labelOpts={"position": 0.97, "color": theme.c("setpoint")}),
            }
            for ln in lines.values():
                ln.setVisible(False)
                w.addItem(ln)
            # hora buscada (barra de búsqueda): línea vertical
            mark = pg.InfiniteLine(angle=90, pen=pg.mkPen(theme.c("accent"), width=1, style=Qt.DashLine),
                                   label="", labelOpts={"position": 0.95, "color": theme.c("accent")})
            mark.setVisible(False)
            w.addItem(mark, ignoreBounds=True)
            lines["mark"] = mark
            self.stack.add(w)
            self.plots[vid] = {"widget": w, "curve": curve, "sp": sp_curve, "lines": lines,
                               "proj": proj, "proj_lo": proj_lo, "proj_hi": proj_hi, "eta": eta, "cap": capt}
            self._apply_marker(self.plots[vid])
        self.placeholder.setVisible(not self.plots)

    def reset_y(self) -> None:
        """La próxima actualización vuelve a calcular la escala Y (rango o escala automática cambiados)."""
        for p in self.plots.values():
            p["widget"]._yr = None

    def set_marker(self, ts: Optional[float]) -> None:
        """Marca una hora en todas las gráficas (None la quita)."""
        self.marker = ts
        for p in self.plots.values():
            self._apply_marker(p)

    def _apply_marker(self, p: dict) -> None:
        ts = getattr(self, "marker", None)
        mark = p["lines"]["mark"]
        mark.setVisible(ts is not None)
        if ts is not None:
            mark.setPos(ts)
            mark.label.setFormat(time.strftime("%d/%m %H:%M:%S", time.localtime(ts)))

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
                yr = steady_range(getattr(w, "_yr", None), yr)  # sin reajustar la escala en cada lectura
                if yr != getattr(w, "_yr", None):
                    w._yr = yr
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
        self._control(p, t, y, bounds)

    def _control(self, p, t, y, bounds: Bounds) -> None:
        """Límites de control y Cpk / Ppk de los datos visibles."""
        lines, cap_item = p["lines"], p["cap"]
        cap = None
        if self.chk_ctrl.isChecked() and len(t) >= 5:
            t_arr, y_arr = np.asarray(t, float), np.asarray(y, float)
            vis = y_arr[t_arr >= t_arr[-1] - self.range_s]
            cap = capability(vis, bounds.al, bounds.ah) if len(vis) >= 5 else None
        if cap is None or cap.std_within <= 0:
            for k in ("ucl", "lcl"):
                lines[k].setVisible(False)
            cap_item.setText("")
            return
        lines["ucl"].setPos(cap.mean + 3 * cap.std_within)
        lines["lcl"].setPos(cap.mean - 3 * cap.std_within)
        for k in ("ucl", "lcl"):
            lines[k].setVisible(True)

        def grade(v):
            if v is None:
                return "—"
            color = theme.c("good_text") if v >= 1.33 else (theme.c("warning_text") if v >= 1.0 else theme.c("critical"))
            return f"<b style='color:{color}'>{v:.2f}</b>"
        cap_item.setHtml(f"<span style='background:{theme.c('plot_bg')}; color:{theme.c('plot_fg')}'>&nbsp;Cpk "
                         f"{grade(cap.cpk)} · Ppk {grade(cap.ppk)} · n {cap.n}&nbsp;</span>")
        vb = p["widget"].getViewBox()
        (x0, _x1), (_y0, y1) = vb.viewRange()
        cap_item.setPos(x0, y1)


class MainWindow(QMainWindow):
    def __init__(self, ctx: AppContext):
        super().__init__()
        self.ctx = ctx
        self.engine = ctx.engine
        self._config_version = ctx.engine.config_version
        self._prompts: dict = {}
        self._stop_since: Optional[float] = None  # inicio del paro en curso (para el aviso al reanudar)
        self._stop_prompt = None
        self._control_prompts: dict = {}  # lazo -> (aviso, propuesta) del modo asistido
        self._series = SeriesCache(ctx.engine)
        self.bridge = SnapshotBridge()
        self.bridge.snapshot.connect(self.on_snapshot, Qt.QueuedConnection)
        self.engine.listeners.append(self.bridge.snapshot.emit)
        # Preferencias de vista (gráficas, SPC, correlación, rango, página): se guardan solas al cambiarlas
        self._view = dict(ctx.workspace.load_state().get("view") or {})
        self._plotted: list[str] = list(self._view.get("plotted") or [])
        self._view_timer = QTimer(self)
        self._view_timer.setSingleShot(True)
        self._view_timer.timeout.connect(self._write_view)
        self._restoring = True  # mientras se construye la ventana no se guarda nada
        self._rebuilding = False
        self.dock = None  # barra compacta que queda sobre el HMI al minimizar (se crea al usarla)
        from .supervisor import SupervisorGate
        self.gate = SupervisorGate(ctx.workspace.home, self)  # acciones que piden un supervisor (opcional)
        self._build_ui()
        self._guard_controls()
        self._update_session()
        self._restore_view_controls()
        self.rebuild_table()
        self.refresh_recipes()
        self._update_title()
        if self._view.get("page") in self.pages:
            self.show_page(self._view["page"])
        self._restoring = False

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
        rl.setContentsMargins(12, 10, 12, 6)
        rl.setSpacing(8)
        rl.addWidget(self._build_topbar())
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
        from .live_tiles import LivePage, LiveTilesView
        self.live_tiles = LiveTilesView(self._series, quality=lambda vid: self.engine.acquirer.quality(vid),
                                        allow=self.gate.allow)
        self.live_tiles.changed.connect(self._live_prefs_changed)
        self.live_tiles.open_trend.connect(self.search_plot)
        self.live_page = LivePage(self.table, self.live_tiles)
        self.live_page.set_mode(self._view.get("live_mode", "tiles"), emit=False)
        self.live_page.modeChanged.connect(lambda _m: self._save_view())

        self.trends = TrendPanel()
        self.trends.cmb_range.currentIndexChanged.connect(self._replot)
        self.trends.chk_auto_y.toggled.connect(self._replot)
        self.trends.chk_ctrl.toggled.connect(self._replot)
        for sig in (self.trends.cmb_range.currentIndexChanged, self.trends.chk_auto_y.toggled,
                    self.trends.chk_ctrl.toggled):
            sig.connect(self._save_view)
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
        self.stats_panel.selectionChanged.connect(self._save_view)
        self.corr_panel = CorrelationPanel(self.engine)
        self.corr_panel.changed.connect(self._save_view)
        self.behavior_panel = BehaviorPanel(self.engine)
        self.analysis_pages = (self.stats_panel, self.corr_panel, self.behavior_panel)
        self._analysis_at = 0.0
        self.kpi = KpiDashboard(self.engine)
        from .stats_page import StatsPage
        self.stats_page = StatsPage(self.ctx)

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
        from .problems_page import ProblemsPage
        self.problems_page = ProblemsPage(self.ctx)
        self.problems_page.pendingChanged.connect(self._problems_badge)
        QTimer.singleShot(0, lambda: self.home.set_pending(self.problems_page.pending))
        from .control_page import ControlPage
        self.control_page = ControlPage(self.ctx, on_config_changed=self._save_profile)
        self.control_page.allow = self.gate.allow
        self.problems_page.allow = self.gate.allow

        self.pages: dict[str, QWidget] = {}
        for key, w in (("home", self.home), ("variables", self.live_page), ("trends", trends_page), ("kpi", self.kpi),
                       ("problems", self.problems_page), ("control", self.control_page),
                       ("spc", self.stats_panel), ("corr", self.corr_panel),
                       ("analysis", self.stats_page), ("behavior", self.behavior_panel),
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
        from .wheel_lock import lock as wheel_lock
        self.act_wheel = QAction("🔒 Bloquear zoom de las gráficas con la rueda del ratón", self, checkable=True)
        self.act_wheel.setChecked(bool(self.ctx.workspace.load_state().get("ui", {}).get("lock_wheel", False)))
        wheel_lock().enabled = self.act_wheel.isChecked()
        self.act_wheel.toggled.connect(self._wheel_toggled)
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
        m.addAction("⚠ Causas de paro y defectos…", self.open_problems_config)
        m.addAction("🧠 Comportamiento (entrenar)…", self.open_behavior)
        m.addAction("✎ Tablero de Inicio…", self.open_home_config)
        m.addAction("▭ Dock al minimizar…", self.open_dock_config)

        # --- Acciones: lo que se hace en el momento ---
        m = mb.addMenu("A&cciones")
        m.addAction(self.act_tour_pause)
        act = m.addAction("■ Detener todo el control", self.stop_all_control)
        act.setShortcut("Ctrl+Shift+X")
        m.addMenu(self._tour_menu)
        m.addMenu(self._report_menu)

        # --- Configuración: ajustes de este equipo (no cambian con la receta) ---
        m = mb.addMenu("C&onfiguración")
        m.addAction("🌐 Dashboard global (exportación)…", self.open_station)
        m.addAction("🏷 Identidad de la estación (logo, texto, línea)…", self.open_branding)
        m.addAction("👷 Personal (operadores y supervisores)…", self.open_personnel)
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
        # Ver: solo modos de pantalla; las páginas están en la barra lateral (sus atajos Ctrl+1…9 siguen activos)
        m = mb.addMenu("&Ver")
        for i, (key, _label, _icon) in enumerate(NAV_ITEMS[:9], 1):
            act = QAction(self)
            act.setShortcut(f"Ctrl+{i}")
            act.triggered.connect(lambda _=False, key=key: self.show_page(key))
            self.addAction(act)
        m.addAction(self.act_top)
        m.addAction(self.act_wheel)
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
        side.setFixedWidth(236)
        lay = QVBoxLayout(side)
        lay.setContentsMargins(10, 14, 10, 10)
        from .branding import header_widget
        self.brand = header_widget(self.ctx.workspace.home)  # logo, texto propio y número de línea
        self.brand.setCursor(Qt.PointingHandCursor)
        self.brand.setToolTip(tr("Logo, texto y número de línea: Configuración → Identidad de la estación"))
        self.brand.mouseDoubleClickEvent = lambda _e: self.open_branding()
        self._brand_lay = lay
        lay.addWidget(self.brand)
        lay.addSpacing(12)
        self.nav = QListWidget()
        self.nav.setObjectName("nav")
        self.nav.setFocusPolicy(Qt.NoFocus)
        self.nav.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.nav.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.nav.setTextElideMode(Qt.ElideRight)
        self.nav.setIconSize(QSize(18, 18))
        for key, label, _icon in NAV_ITEMS:
            it = QListWidgetItem(tr(label))
            it.setIcon(icons.icon(key, theme.c("nav_icon"), theme.c("accent_text")))
            it.setData(Qt.UserRole, key)
            it.setSizeHint(QSize(0, NAV_ROW_H))
            self.nav.addItem(it)
        self.nav.setFixedHeight(len(NAV_ITEMS) * (NAV_ROW_H + 2) + 6)  # alto exacto: sin barra de desplazamiento
        self.nav.currentItemChanged.connect(self._nav_changed)
        lay.addWidget(self.nav)
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setStyleSheet(f"color:{theme.c('sidebar_border')};")
        lay.addWidget(line)
        self.nav2 = QListWidget()
        self.nav2.setObjectName("nav")
        self.nav2.setFocusPolicy(Qt.NoFocus)
        self.nav2.setIconSize(QSize(18, 18))
        self.nav2.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.nav2.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.nav2.setTextElideMode(Qt.ElideRight)
        for key, label, _icon in NAV_TOOLS:
            it = QListWidgetItem(tr(label))
            it.setIcon(icons.icon(key, theme.c("nav_icon"), theme.c("accent_text")))
            it.setData(Qt.UserRole, key)
            it.setSizeHint(QSize(0, NAV_ROW_H))
            self.nav2.addItem(it)
        self.nav2.setFixedHeight(len(NAV_TOOLS) * (NAV_ROW_H + 2) + 6)
        self.nav2.itemClicked.connect(self._tool_clicked)
        lay.addWidget(self.nav2)
        lay.addStretch(1)
        self.lbl_side_status = QLabel()
        self.lbl_side_status.setWordWrap(True)
        self.lbl_side_status.setStyleSheet(f"color:{theme.c('muted')}; font-size:11px;")
        lay.addWidget(self.lbl_side_status)
        return side

    def _build_topbar(self) -> QFrame:
        """Barra superior: búsqueda, turno, campana de alarmas y quién está en turno."""
        from .search import SearchBox
        bar = QFrame()
        bar.setObjectName("topbar")
        row = QHBoxLayout(bar)
        row.setContentsMargins(10, 6, 10, 6)
        row.setSpacing(10)
        self.search = SearchBox(self)
        self.search.setMinimumWidth(320)
        row.addWidget(self.search, 3)
        QShortcut("Ctrl+K", self, self.search.open)
        QShortcut("Ctrl+F", self, self.search.open)
        row.addStretch(1)
        self.lbl_shift = QLabel()
        self.lbl_shift.setObjectName("topInfo")
        self.lbl_shift.setToolTip(tr("Inicio del turno en curso (Configuración → KPI / OEE → turnos)"))
        row.addWidget(self.lbl_shift)
        self.btn_bell = QToolButton()
        self.btn_bell.setObjectName("bell")
        self.btn_bell.setIcon(icons.icon("events", theme.c("nav_icon")))
        self.btn_bell.setIconSize(QSize(18, 18))
        self.btn_bell.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.btn_bell.setToolTip(tr("Alarmas y avisos activos (clic: Alarmas y eventos)"))
        self.btn_bell.clicked.connect(lambda: self.show_page("events"))
        row.addWidget(self.btn_bell)
        self.btn_session = QToolButton()
        self.btn_session.setObjectName("session")
        self.btn_session.clicked.connect(self._session_clicked)
        self.gate.changed.connect(self._update_session)
        self.gate.denied.connect(self._denied)
        row.addWidget(self.btn_session)
        self.cmb_user = QComboBox()  # quién está en turno (operador o supervisor): un solo selector
        self.cmb_user.setObjectName("crew")
        self.cmb_user.setMinimumWidth(190)
        self.cmb_user.setIconSize(QSize(16, 16))
        self.cmb_user.setToolTip(tr("Usuario en turno (operador o supervisor)"))
        self.cmb_user.activated.connect(lambda _i: self._crew_chosen())
        row.addWidget(self.cmb_user)
        self.fill_crew()
        self._update_shift_label()
        self._login_dlg = None
        self._login_snooze = 0.0  # «Más tarde» en el aviso de cambio de turno
        self._shift_timer = QTimer(self)
        self._shift_timer.timeout.connect(self._update_shift_label)
        self._shift_timer.timeout.connect(self.check_shift)
        self._shift_timer.timeout.connect(self._update_session)
        self._shift_timer.start(30000)
        QTimer.singleShot(3000, self.check_shift)
        return bar

    # --- personal en turno ---------------------------------------------------------------
    def fill_crew(self) -> None:
        people = Personnel.load(self.ctx.workspace.home)
        cur = crew(self.ctx.workspace.load_state())["user"]
        names = people.names() + [n for n in self.ctx.config.problems.operators if n and not people.find(n)]
        if cur and cur not in names:
            names.append(cur)  # dado de baja pero aún en turno
        cmb = self.cmb_user
        cmb.blockSignals(True)
        cmb.clear()
        cmb.addItem(icons.icon("user", theme.c("nav_icon")), tr("— Usuario —"), "")
        for n in names:
            person = people.find(n)
            sup = person is not None and person.role == "supervisor"
            cmb.addItem(icons.icon("shield" if sup else "user", theme.c("nav_icon")),
                        f"{n} · {tr('Supervisor')}" if sup else n, n)
        cmb.insertSeparator(cmb.count())
        cmb.addItem(tr("✎ Editar personal…"), "__edit__")
        cmb.setCurrentIndex(max(0, cmb.findData(cur)))
        cmb.blockSignals(False)

    def _crew_chosen(self) -> None:
        name = self.cmb_user.currentData()
        if name == "__edit__":
            self.fill_crew()  # regresa a quien estaba
            self.open_personnel()
            return
        people = Personnel.load(self.ctx.workspace.home)
        if name and people.login.confirm != "none" and name != crew(self.ctx.workspace.load_state())["user"]:
            self.fill_crew()  # hasta confirmar sigue quien estaba
            self.ask_login(people, name=name)
            return
        self.set_user(name or "")

    def set_user(self, name: str, shift_key: Optional[str] = None) -> None:
        """Guarda quién está en turno (y, si viene del aviso de turno, qué vuelta de turno confirmó)."""
        state = self.ctx.workspace.load_state()
        person = Personnel.load(self.ctx.workspace.home).find(name)
        c = crew(state)
        crew_before = c["user"]
        state["crew"] = {"user": name, "role": person.role if person else ("operator" if name else ""),
                         "shift_key": shift_key if shift_key is not None else c["shift_key"]}
        if name:
            state["last_operator"] = name
        self.ctx.workspace.save_state(state)
        if self.gate.user is not None and self.gate.user != name:
            self.gate.end()  # cambió quién está en turno: la sesión de supervisor se cierra
        if self.engine.historian is not None and name != crew_before:
            try:  # queda en el historial: el análisis estadístico agrupa y filtra por operador
                self.engine.historian.write_events([(self.engine.clock(), "crew", int(Level.INFO), "USUARIO",
                                                     name, f"Usuario en turno: {name or '—'}",
                                                     self.engine.state.recipe)])
            except Exception:
                pass
        self.fill_crew()
        self.problems_page.capture.reload_config()

    def ask_login(self, people: Personnel, name: str = "", shift=None, on_postpone=None) -> None:
        """Ventana de confirmación (sin bloquear el monitoreo); al confirmar cambia el usuario en turno."""
        from ..personnel import shift_key
        from .login_dialog import LoginDialog
        if self._login_dlg is not None:
            self._login_dlg.raise_()
            return
        dlg = LoginDialog(people, shift, name, self, can_postpone=shift is not None)
        key = shift_key(shift, self.engine.clock()) if shift is not None else None

        def done(result: int) -> None:
            self._login_dlg = None
            if result == QDialog.Accepted:
                self.set_user(dlg.name, key)
                person = people.find(dlg.name)
                if people.login.confirm == "badge_password" and person is not None and person.role == "supervisor":
                    self.gate.start(person.name, people.login.session_min)  # ya confirmó con contraseña
            elif on_postpone is not None:
                on_postpone()
            dlg.deleteLater()
        dlg.finished.connect(done)
        self._login_dlg = dlg
        dlg.open()

    def _guard_controls(self) -> None:
        """Controles protegidos: sin sesión de supervisor, un clic muestra el aviso (con opción de iniciar sesión)."""
        g = self.gate.guard
        g(self.cmb_recipe, "recipes")
        g(self.chk_auto, "recipes")
        g(self.home.btn_custom, "charts")
        g(self.stats_panel.lst, "analysis")
        g(self.corr_panel.lst, "analysis")
        g(self.corr_panel.cmb_x, "analysis")
        g(self.corr_panel.cmb_y, "analysis")
        g(self.behavior_panel.cmb, "analysis")

    def _session_clicked(self) -> None:
        if self.gate.active():
            self.gate.end()
        else:
            self.gate.login()

    def _update_session(self) -> None:
        """Botón de sesión de supervisor (solo con la protección encendida) y controles bloqueados sin ella."""
        lock = bool(Personnel.load(self.ctx.workspace.home).supervisors_ready())
        on = self.gate.active()
        self.btn_session.setVisible(lock or on)
        if on:
            self.btn_session.setText(tr("🔓 {n} · {m} min · cerrar sesión", n=self.gate.user,
                                        m=self.gate.remaining_min()))
            self.btn_session.setToolTip(tr("Sesión de supervisor activa (clic: cerrar sesión)"))
        else:
            self.btn_session.setText(tr("🔒 Supervisor"))
            self.btn_session.setToolTip(tr("Iniciar la sesión de supervisor para hacer cambios protegidos"))

    def _denied(self, reason: str) -> None:
        """Acción protegida sin sesión de supervisor: no se hace; solo se avisa."""
        self.statusBar().showMessage(tr("🔒 Requiere la sesión de supervisor: {r}", r=tr(reason)), 8000)

    def check_shift(self) -> None:
        """Turno detectado por la hora (opcional): al empezar uno nuevo se pregunta quién entra."""
        from ..personnel import shift_key
        people = Personnel.load(self.ctx.workspace.home)
        now = self.engine.clock()
        shift = people.current_shift(now)
        if not people.login.auto_shift or shift is None or self._login_dlg is not None or now < self._login_snooze:
            return
        if crew(self.ctx.workspace.load_state())["shift_key"] == shift_key(shift, now):
            return

        def later() -> None:
            self._login_snooze = self.engine.clock() + 600  # se vuelve a preguntar en 10 min
        self.ask_login(people, crew(self.ctx.workspace.load_state())["user"], shift, later)

    def open_personnel(self) -> None:
        if not self.gate.allow("personnel"):
            return
        from .personnel_dialog import PersonnelDialog
        if PersonnelDialog(self.ctx.workspace.home, self.ctx.config.problems.operators, self,
                           shift_starts=self.ctx.config.oee.shift_starts).exec():
            self.fill_crew()
            self.problems_page.capture.reload_config()
            self._update_shift_label()
            self._update_session()
            self.check_shift()

    def _update_shift_label(self) -> None:
        from ..analysis.oee import shift_start
        now = self.engine.clock()
        shift = Personnel.load(self.ctx.workspace.home).current_shift(now)
        if shift is not None:  # turnos de Configuración → Personal
            text = shift.label()
        else:
            a = shift_start(now, self.ctx.config.oee.shift_starts)
            text = tr("Turno desde {t}", t=time.strftime("%H:%M", time.localtime(a)))
        self.lbl_shift.setText(text + "  ·  " + time.strftime("%d/%m/%Y", time.localtime(now)))

    def _update_bell(self, snap: Snapshot) -> None:
        n_alarm = sum(f.level >= Level.ALARM for f in snap.findings)
        n_warn = sum(f.level == Level.WARN for f in snap.findings)
        n = n_alarm + n_warn
        key = "critical" if n_alarm else ("warning_text" if n_warn else "nav_icon")
        self.btn_bell.setIcon(icons.icon("events", theme.c(key)))
        self.btn_bell.setText(str(n) if n else "")
        self.btn_bell.setProperty("alert", "alarm" if n_alarm else ("warn" if n_warn else ""))
        self.btn_bell.style().unpolish(self.btn_bell)
        self.btn_bell.style().polish(self.btn_bell)

    # --- acciones de la búsqueda -------------------------------------------------------------
    def search_plot(self, vid: str) -> None:
        """Variable elegida en la búsqueda: se grafica en Tendencias."""
        v = self.ctx.config.variable(vid)
        if v is None:
            return
        if not v.numeric:
            self.search_live(vid)
            return
        if vid not in self._plotted:
            self.table.set_checked(vid, True)
            self._plot_toggled(vid, True)
        self.show_page("trends")

    def search_live(self, vid: str) -> None:
        self.show_page("variables")
        if self.live_page.mode == "tiles":
            self.live_tiles.filter.setText(self.ctx.config.var_label(self.ctx.config.variable(vid)))
            return
        select = getattr(self.table, "select_var", None)
        if select is not None:
            select(vid)

    def search_spc(self, vid: str) -> None:
        from .analysis_panels import MAX_SPC
        sel = [x for x in self.stats_panel.selected if x != vid] + [vid]
        self.stats_panel.set_variables(self.ctx.config, sel[-MAX_SPC:])
        self._save_view()
        self.show_page("spc")

    def search_corr(self, vid: str) -> None:
        c = self.corr_panel
        checked = list(dict.fromkeys(c.selected_ids() + [vid]))
        c.set_variables(self.ctx.config, checked, x=c.cmb_x.currentData() if c.cmb_x.currentData() != vid else None,
                        y=vid)
        self._save_view()
        self.show_page("corr")

    def goto_time(self, ts: float) -> None:
        """Hora elegida en la búsqueda: Tendencias con un rango que la incluye y una marca en ella."""
        ago = self.engine.clock() - ts
        idx = next((i for i in range(self.trends.cmb_range.count())
                    if self.trends.cmb_range.itemData(i) >= ago * 1.1), self.trends.cmb_range.count() - 1)
        self.trends.cmb_range.setCurrentIndex(idx)
        self.trends.set_marker(ts)
        self.show_page("trends")
        self._replot()

    def capture_at(self, ts: float) -> None:
        self.show_page("problems")
        self.problems_page.tabs.setCurrentIndex(0)
        self.problems_page.capture.focus_time(ts)

    def open_problem(self, rec: dict) -> None:
        self.show_page("problems")
        self.problems_page.tabs.setCurrentIndex(0)
        self.problems_page.capture.focus_record(rec)

    def search_recipe(self, name: str) -> None:
        if name == self.engine.state.recipe:
            self.open_recipes()
            return
        if QMessageBox.question(self, tr("Cambiar receta"),
                                tr("¿Cambiar la receta activa a «{r}»?", r=name)) != QMessageBox.Yes:
            return
        idx = self.cmb_recipe.findData(name)
        if idx >= 0:
            self.cmb_recipe.setCurrentIndex(idx)
            self._recipe_chosen(idx)

    def run_tool(self, key: str) -> None:
        if key == "recipes":
            self.open_recipes()
        elif key == "setup":
            self.open_setup()
        else:
            self.show_page(key)

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
        self._save_view()
        self._refresh_analysis(force=True)
        snap = self.engine.last
        if snap is not None and self.stack.currentWidget() is self.home:
            self.home.update_snapshot(snap, force=True)
        if self.stack.currentWidget() is self.pages.get("trends"):
            self._replot()
        if snap is not None and self.stack.currentWidget() is self.live_page:
            self.live_page.update_snapshot(snap)

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
        self.live_tiles.rebuild(cfg, self._view.get("live_tiles") or {})
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
        self.stats_panel.set_variables(cfg, self.stats_panel.selected or self._view.get("spc"))
        corr = self.corr_panel.selected_ids() if self.corr_panel.lst.count() else self._view.get("corr")
        self.corr_panel.set_variables(cfg, corr if corr else self._plotted,
                                      self._view.get("corr_x"), self._view.get("corr_y"))
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
        self._save_view()
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
        if name != self.engine.state.recipe and not self.gate.allow("recipes"):
            self.refresh_recipes()  # sigue la receta que estaba
            return
        # Elegir manualmente una receta desactiva la selección automática.
        if self.chk_auto.isChecked() and self.ctx.config.general.recipe_name_var:
            self.chk_auto.setChecked(False)
        self.engine.set_recipe(name)
        self._save_state()

    def _auto_toggled(self, on: bool) -> None:
        if on != self.engine.state.auto_recipe and not self.gate.allow("recipes"):
            self.chk_auto.blockSignals(True)
            self.chk_auto.setChecked(self.engine.state.auto_recipe)
            self.chk_auto.blockSignals(False)
            self.act_auto.blockSignals(True)
            self.act_auto.setChecked(self.engine.state.auto_recipe)
            self.act_auto.blockSignals(False)
            return
        self.engine.set_recipe(self.engine.state.recipe, auto=on)
        self._save_state()

    # --- preferencias de vista (se guardan solas) ------------------------------------------------------------
    def _restore_view_controls(self) -> None:
        v = self._view
        tr_ = self.trends
        for w in (tr_.cmb_range, tr_.chk_auto_y, tr_.chk_ctrl):
            w.blockSignals(True)
        if v.get("range"):
            tr_.cmb_range.setCurrentIndex(max(0, tr_.cmb_range.findData(v["range"])))
        if "auto_y" in v:
            tr_.chk_auto_y.setChecked(bool(v["auto_y"]))
        if "ctrl" in v:
            tr_.chk_ctrl.setChecked(bool(v["ctrl"]))
        for w in (tr_.cmb_range, tr_.chk_auto_y, tr_.chk_ctrl):
            w.blockSignals(False)

    def _save_view(self, *_args) -> None:
        if self._rebuilding or getattr(self, "_restoring", True) or not hasattr(self, "corr_panel"):
            return
        self._view.update({
            "plotted": list(self._plotted), "range": self.trends.cmb_range.currentData(),
            "auto_y": self.trends.chk_auto_y.isChecked(), "ctrl": self.trends.chk_ctrl.isChecked(),
            "spc": list(self.stats_panel.selected), "corr": self.corr_panel.selected_ids(),
            "corr_x": self.corr_panel.cmb_x.currentData(), "corr_y": self.corr_panel.cmb_y.currentData(),
            "page": self.current_page() or self._view.get("page"), "live_mode": self.live_page.mode,
            "live_tiles": self.live_tiles.prefs})
        self._view_timer.start(800)  # se agrupan los cambios seguidos en una sola escritura

    def _live_prefs_changed(self, prefs: dict) -> None:
        self._view["live_tiles"] = prefs
        self._save_view()

    def _write_view(self) -> None:
        try:
            state = self.ctx.workspace.load_state()
            state["view"] = self._view
            self.ctx.workspace.save_state(state)
        except OSError:
            pass

    def _save_state(self) -> None:
        state = self.ctx.workspace.load_state()
        state.update({"recipe": self.engine.state.recipe, "auto_recipe": self.engine.state.auto_recipe})
        self.ctx.workspace.save_state(state)

    # --- acciones --------------------------------------------------------------
    def toggle_run(self) -> None:
        if self.engine.running:
            if not self.gate.allow("stop"):
                return
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
        if not self.gate.allow("setup"):
            return
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
        if not self.gate.allow("station"):
            return
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
        if not self.gate.allow("charts"):
            return
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
        if not self.gate.allow("charts"):
            return
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
        if not self.gate.allow("recipes"):
            return
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
            self.rebuild_table()  # las gráficas elegidas se conservan si la receta nueva tiene esas variables
            self._update_title()
        if snap.recipe != self.cmb_recipe.currentData():
            self.refresh_recipes()
        self._update_prompts(snap)
        self._watch_stop(snap)
        self._control_proposals(snap)
        if self.stack.currentWidget() is self.control_page:
            self.control_page.refresh(snap)
        if self.dock is not None and self.dock.isVisible():
            self.dock.update_snapshot(snap)
        page = self.stack.currentWidget()
        # Solo se dibuja la página visible (no carga la PC con gráficas ocultas).
        if page is self.home:
            self.home.update_snapshot(snap)
        if page is self.live_page:
            self.live_page.update_snapshot(snap)
        if page is self.pages["trends"]:
            self._update_plots(snap)
        self._refresh_analysis()
        self._update_findings(snap)
        self._append_events(snap)
        self._update_bell(snap)
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

    # --- problemas de proceso ----------------------------------------------------------------
    def _problems_badge(self, n: int) -> None:
        for i in range(self.nav.count()):
            it = self.nav.item(i)
            if it.data(Qt.UserRole) == "problems":
                it.setText(tr("Problemas de proceso") + (f"  ({n})" if n else ""))
                it.setToolTip(tr("{n} paros sin clasificar en el turno", n=n) if n else "")
        self.home.set_pending(n)

    def _watch_stop(self, snap: Snapshot) -> None:
        """Al reanudar la línea tras un paro largo, avisa para clasificarlo (o queda como pendiente)."""
        o = self.engine.config.oee
        pc = self.engine.config.problems
        st = snap.statuses.get(o.speed_var) if (o.enabled and o.speed_var) else None
        if st is None or st.reading.value is None or not st.fresh:
            return
        stopped = st.reading.value <= o.stop_threshold
        if stopped:
            if self._stop_since is None:
                self._stop_since = snap.ts
            return
        a, self._stop_since = self._stop_since, None
        if a is None or not pc.prompt or snap.ts - a < pc.prompt_min_s:
            return
        self.problems_page.refresh()
        if self._stop_prompt is not None:
            self._stop_prompt.close()
        from .problems_page import StopPrompt
        self._stop_prompt = StopPrompt(a, snap.ts, self._classify_stop)
        self._stop_prompt.show()

    def _classify_stop(self, a: float, b: float) -> None:
        self._stop_prompt = None
        if self.dock is not None and self.dock.isVisible():
            self.restore_from_dock()
        self.showNormal()
        self.raise_()
        self.activateWindow()
        self.show_page("problems")
        self.problems_page.classify(a, b)

    def _control_proposals(self, snap: Snapshot) -> None:
        """Modo asistido: aviso flotante con la propuesta (se cierra solo si la propuesta cambia o desaparece)."""
        from .control_page import ProposalPrompt
        ctl = self.engine.control
        for lid, info in (snap.control or {}).items():
            prop = info.get("proposal") if info.get("active") and info.get("mode") == "assist" else None
            cur = self._control_prompts.get(lid)
            if cur is not None and cur[1] != prop:
                _close_quietly(cur[0])
                self._control_prompts.pop(lid, None)
                cur = None
            if prop and cur is None and self.stack.currentWidget() is not self.control_page:
                lp = self.engine.config.control(lid)
                var = self.engine.config.variable(lp.input_var or "") if lp else None
                dec = var.decimals if var is not None and var.decimals is not None else 2
                dlg = ProposalPrompt(info.get("name", lid), f"{prop[0]:.{dec}f}", f"{prop[1]:.{dec}f}",
                                     lambda lid=lid: ctl.accept_proposal(lid), lambda lid=lid: ctl.reject_proposal(lid))
                dlg.show()
                self._control_prompts[lid] = (dlg, prop)

    def stop_all_control(self) -> None:
        self.engine.control.stop_all()
        self.control_page.refresh()
        self.statusBar().showMessage(tr("Control detenido en todos los lazos"), 5000)

    def open_branding(self) -> None:
        if not self.gate.allow("station"):
            return
        from .branding import BrandingDialog, header_widget
        if not BrandingDialog(self.ctx.workspace.home, self).exec():
            return
        new = header_widget(self.ctx.workspace.home)
        new.setCursor(Qt.PointingHandCursor)
        new.setToolTip(self.brand.toolTip())
        new.mouseDoubleClickEvent = lambda _e: self.open_branding()
        self._brand_lay.replaceWidget(self.brand, new)
        self.brand.deleteLater()
        self.brand = new

    def open_problems_config(self) -> None:
        if not self.gate.allow("catalogs"):
            return
        from .problems_config import ProblemsConfigDialog
        dlg = ProblemsConfigDialog(self.engine.config.problems, self)
        if not dlg.exec():
            return
        self.engine.config.problems = dlg.settings()
        self.ctx.workspace.save_config(self.engine.config)
        self._save_profile()  # va con la receta activa
        self.problems_page.reload_config()

    def open_behavior(self) -> None:
        if not self.gate.allow("catalogs"):
            return
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
                it.setText(tr("Alarmas y eventos") + (f"  ({n_alarm})" if n_alarm else ""))
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
        if not self._rebuilding and not self.gate.allow("stop"):
            event.ignore()
            return
        if self._view_timer.isActive():
            self._view_timer.stop()
            self._write_view()
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
        if self._stop_prompt is not None:
            self._stop_prompt.close()
            self._stop_prompt = None
        for dlg, _p in self._control_prompts.values():
            _close_quietly(dlg)
        self._control_prompts.clear()
        self.problems_page.timer.stop()

    # --- idioma y tema ------------------------------------------------------------
    def _wheel_toggled(self, on: bool) -> None:
        """Rueda del ratón sobre las gráficas: zoom (normal) o desplazar la página (bloqueado). Se recuerda."""
        from .wheel_lock import lock as wheel_lock
        wheel_lock().enabled = on
        state = self.ctx.workspace.load_state()
        state["ui"] = {**state.get("ui", {}), "lock_wheel": on}
        self.ctx.workspace.save_state(state)

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
        self._view_timer.stop()
        self._write_view()  # la ventana nueva lee las preferencias del disco
        new = MainWindow(self.ctx)
        new.setGeometry(self.geometry())
        new._plotted = list(self._plotted)
        new.rebuild_table()
        new.act_top.setChecked(self.act_top.isChecked())
        new.act_tour_pause.setChecked(self.act_tour_pause.isChecked())
        if self.gate.active():  # la sesión de supervisor sigue en la ventana nueva
            new.gate.user, new.gate.until = self.gate.user, self.gate.until
            new._update_session()
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
