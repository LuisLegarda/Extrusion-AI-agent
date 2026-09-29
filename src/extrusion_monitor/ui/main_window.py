"""Ventana principal: estado de variables, tendencias, hallazgos y registro."""
from __future__ import annotations

import time
from typing import Optional

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction, QBrush, QColor
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QFileDialog, QHeaderView, QLabel, QListWidget,
    QHBoxLayout, QListWidgetItem, QMainWindow, QMenu, QMessageBox, QSplitter, QTableWidget, QTableWidgetItem,
    QTabWidget, QToolBar, QToolButton, QVBoxLayout, QWidget,
)

from ..analysis.rules import Level
from ..bootstrap import AppContext, make_clicker, make_ocr
from ..capture import ScreenSource
from ..navigation import exclude_window_from_capture
from ..engine import Snapshot
from ..recipes import Bounds
from .common import SnapshotBridge, level_color
from .variable_tree import VariableTree
from .kpi_dashboard import KpiDashboard
from .analysis_panels import BehaviorPanel, CorrelationPanel, StatsPanel
from ..analysis.statistics import projection

MAX_PLOTS = 4


RANGES = [("5 min", 300), ("15 min", 900), ("30 min", 1800), ("1 h", 3600), ("4 h", 4 * 3600),
          ("8 h", 8 * 3600), ("24 h", 86400), ("7 días", 7 * 86400)]


def y_range(y, limits) -> Optional[tuple[float, float]]:
    """Escala Y: los límites de la variable (con margen) más los datos visibles.

    Un pico amplía la escala solo mientras está dentro del rango de tiempo mostrado; al salir,
    la escala vuelve a los límites.
    """
    y = np.asarray(y, float)
    y = y[np.isfinite(y)]
    vals = [float(v) for v in limits if v is not None]
    lo, hi = (min(vals), max(vals)) if vals else (None, None)
    if len(y):
        dlo, dhi = float(y.min()), float(y.max())
        lo = dlo if lo is None else min(lo, dlo)
        hi = dhi if hi is None else max(hi, dhi)
    if lo is None:
        return None
    span = hi - lo
    pad = span * 0.1 if span > 0 else max(abs(hi) * 0.05, 1.0)
    return lo - pad, hi + pad


class TrendPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        pg.setConfigOptions(antialias=True)
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
            curve = w.plot(pen=pg.mkPen("#4fc3f7", width=2), name="medición")
            sp_curve = w.plot(pen=pg.mkPen("#1e88e5", width=2, style=Qt.DashLine), name="consigna")
            proj = w.plot(pen=pg.mkPen("#ffb74d", width=2, style=Qt.DotLine), name="proyección")
            proj_lo = pg.PlotDataItem(pen=pg.mkPen(None))
            proj_hi = pg.PlotDataItem(pen=pg.mkPen(None))
            band = pg.FillBetweenItem(proj_lo, proj_hi, brush=pg.mkBrush(255, 183, 77, 45))
            w.addItem(proj_lo)
            w.addItem(proj_hi)
            w.addItem(band)
            eta = pg.TextItem(color="#ffb74d", anchor=(1, 1))
            w.addItem(eta)
            lines = {
                "ref": pg.InfiniteLine(angle=0, pen=pg.mkPen("#9e9e9e", style=Qt.DashLine)),
                "wl": pg.InfiniteLine(angle=0, pen=pg.mkPen("#f9a825")),
                "wh": pg.InfiniteLine(angle=0, pen=pg.mkPen("#f9a825")),
                "al": pg.InfiniteLine(angle=0, pen=pg.mkPen("#e53935", width=2)),
                "ah": pg.InfiniteLine(angle=0, pen=pg.mkPen("#e53935", width=2)),
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
            text = f"en {horizon_s / 60:.0f} min: {end:.4g}"
            if (bounds.ah is not None and end > bounds.ah) or (bounds.al is not None and end < bounds.al):
                text += "  ⚠ fuera de alarma"
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
        self._hist_cache: dict = {}
        self.bridge = SnapshotBridge()
        self.bridge.snapshot.connect(self.on_snapshot, Qt.QueuedConnection)
        self.engine.listeners.append(self.bridge.snapshot.emit)
        self._plotted: list[str] = []
        self._build_ui()
        self.rebuild_table()
        self.refresh_recipes()
        self._update_title()

    # --- construcción -------------------------------------------------------
    def _build_ui(self) -> None:
        self.resize(1400, 860)
        tb = QToolBar("Principal")
        tb.setMovable(False)
        self.addToolBar(tb)
        self.act_run = QAction("▶ Iniciar", self)
        self.act_run.triggered.connect(self.toggle_run)
        tb.addAction(self.act_run)
        tb.addSeparator()
        tb.addWidget(QLabel(" Receta: "))
        self.cmb_recipe = QComboBox()
        self.cmb_recipe.setMinimumWidth(240)
        self.cmb_recipe.activated.connect(self._recipe_chosen)
        tb.addWidget(self.cmb_recipe)
        self.chk_auto = QCheckBox("Auto desde HMI")
        self.chk_auto.setChecked(self.engine.state.auto_recipe)
        self.chk_auto.toggled.connect(self._auto_toggled)
        tb.addWidget(self.chk_auto)
        tb.addSeparator()
        act_setup = QAction("⚙ Configurar variables", self)
        act_setup.triggered.connect(self.open_setup)
        tb.addAction(act_setup)
        act_recipes = QAction("📋 Recetas", self)
        act_recipes.triggered.connect(self.open_recipes)
        tb.addAction(act_recipes)
        act_beh = QAction("🧠 Comportamiento", self)
        act_beh.setToolTip("Entrenar el comportamiento normal (variación y correlación entre variables)")
        act_beh.triggered.connect(self.open_behavior)
        tb.addAction(act_beh)
        act_export = QAction("⤓ Exportar CSV", self)
        act_export.triggered.connect(self.export_csv)
        tb.addAction(act_export)
        tb.addSeparator()
        self.act_tour_pause = QAction("⏸ Pausar recorrido", self, checkable=True)
        self.act_tour_pause.setToolTip("Detiene los clics automáticos en el HMI (se siguen leyendo los datos visibles)")
        self.act_tour_pause.toggled.connect(self._tour_pause)
        tb.addAction(self.act_tour_pause)
        self.btn_tour_now = QToolButton()
        self.btn_tour_now.setText("⟳ Recorrer ahora")
        self.btn_tour_now.setToolTip("Ejecuta el recorrido de lectura; la flecha permite elegir otro recorrido")
        self.btn_tour_now.setPopupMode(QToolButton.MenuButtonPopup)
        self.btn_tour_now.clicked.connect(lambda: self.engine.run_tour_now())
        self._tour_menu = QMenu(self)
        self._tour_menu.aboutToShow.connect(self._fill_tour_menu)
        self.btn_tour_now.setMenu(self._tour_menu)
        tb.addWidget(self.btn_tour_now)
        self.btn_report = QToolButton()
        self.btn_report.setText("📄 Reporte")
        self.btn_report.setToolTip("Generar ahora un reporte PDF configurado")
        self.btn_report.setPopupMode(QToolButton.InstantPopup)
        self._report_menu = QMenu(self)
        self._report_menu.aboutToShow.connect(self._fill_report_menu)
        self.btn_report.setMenu(self._report_menu)
        tb.addWidget(self.btn_report)
        tb.addSeparator()
        self.act_top = QAction("📌 Siempre visible", self, checkable=True)
        self.act_top.toggled.connect(self._always_on_top)
        tb.addAction(self.act_top)

        central = QWidget()
        lay = QVBoxLayout(central)
        self.banner = QLabel("DETENIDO")
        self.banner.setObjectName("banner")
        self._set_banner(None, "DETENIDO")
        lay.addWidget(self.banner)

        vsplit = QSplitter(Qt.Vertical)
        hsplit = QSplitter(Qt.Horizontal)
        self.table = VariableTree()
        self.table.quality_fn = lambda vid: self.engine.acquirer.quality(vid)
        self.table.plotToggled.connect(self._plot_toggled)
        hsplit.addWidget(self.table)
        self.trends = TrendPanel()
        self.trends.cmb_range.currentIndexChanged.connect(self._replot)
        self.trends.chk_auto_y.toggled.connect(self._replot)
        self.analysis = QTabWidget()
        self.analysis.addTab(self.trends, "📈 Tendencias")
        self.stats_panel = StatsPanel(self.engine)
        self.analysis.addTab(self.stats_panel, "📊 Estadística")
        self.corr_panel = CorrelationPanel(self.engine)
        self.analysis.addTab(self.corr_panel, "🔗 Correlación")
        self.behavior_panel = BehaviorPanel(self.engine)
        self.analysis.addTab(self.behavior_panel, "🧠 Comportamiento")
        self.analysis.currentChanged.connect(lambda _: self._refresh_analysis(force=True))
        self._analysis_at = 0.0
        hsplit.addWidget(self.analysis)
        hsplit.setSizes([760, 640])
        vsplit.addWidget(hsplit)

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
        vsplit.addWidget(tabs)
        vsplit.setSizes([600, 260])
        self.main_tabs = QTabWidget()
        self.main_tabs.addTab(vsplit, "📟 Monitoreo")
        self.kpi = KpiDashboard(self.engine)
        self.main_tabs.addTab(self.kpi, "🏭 KPI / OEE")
        lay.addWidget(self.main_tabs)
        self.setCentralWidget(central)

        self.lbl_tour = QLabel()
        self.lbl_page = QLabel()
        self.lbl_ocr = QLabel()
        self.lbl_cycle = QLabel()
        for w in (self.lbl_tour, self.lbl_page, self.lbl_ocr, self.lbl_cycle):
            self.statusBar().addPermanentWidget(w)

    def _update_title(self) -> None:
        demo = " — MODO DEMO (HMI simulado)" if self.ctx.demo else ""
        self.setWindowTitle(f"Monitor de extrusión · {self.ctx.config.machine_name}{demo}")

    def _set_banner(self, level: Optional[Level], text: str) -> None:
        self.banner.setText(text)
        self.banner.setStyleSheet(f"background:{level_color(level).name()};")

    def rebuild_table(self) -> None:
        cfg = self.ctx.config
        if not self._plotted:
            self._plotted = [v.id for v in cfg.variables if v.measured and v.trend][:3]
        self._plotted = [vid for vid in self._plotted if cfg.variable(vid)]
        self.table.rebuild(cfg, self._plotted)
        self._sync_plots()
        self.stats_panel.set_variables(cfg)
        self.corr_panel.set_variables(cfg, self._plotted)
        self.behavior_panel.set_models()

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
                self.table.set_checked(self._plotted.pop(0), False)
        elif not on and vid in self._plotted:
            self._plotted.remove(vid)
        self._sync_plots()
        if self.engine.last:
            self._update_plots(self.engine.last)

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
        self.ctx.workspace.save_state({"recipe": self.engine.state.recipe,
                                       "auto_recipe": self.engine.state.auto_recipe})

    # --- acciones --------------------------------------------------------------
    def toggle_run(self) -> None:
        if self.engine.running:
            self.engine.stop()
            self.act_run.setText("▶ Iniciar")
            self._set_banner(None, "DETENIDO")
        else:
            if not self.ctx.config.variables:
                QMessageBox.information(self, "Sin variables",
                                        "Primero configura las variables a leer del HMI.")
                return
            self.engine.start()
            self.act_run.setText("■ Detener")

    def open_setup(self) -> None:
        from .setup_dialog import SetupDialog
        was_running = self.engine.running
        # Durante la configuración el monitoreo (y su recorrido con clics) se detiene.
        self.engine.stop()
        dlg = SetupDialog(self.ctx, self)
        accepted = dlg.exec()
        if accepted:
            if not self.ctx.demo and dlg.config.general.monitor != self.ctx.config.general.monitor:
                self.engine.source = ScreenSource(dlg.config.general.monitor)
                self.engine.clicker = make_clicker(self.engine.source)
            self.ctx.config = dlg.config
            self.engine.reconfigure(dlg.config, make_ocr(self.ctx))
            self.engine.save_profile()  # la receta activa guarda la configuración completa
            self.rebuild_table()
            self._update_title()
        if was_running:
            self.engine.start()

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
        QMessageBox.information(self, "Exportado", f"Se exportaron {n} registros.")

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
            self.lbl_tour.setText("Recorrido: desactivado")
            return
        if self.engine.tour_paused:
            self.lbl_tour.setText("Recorrido: EN PAUSA")
            return
        res = self.engine.last_tour_result
        if res is None:
            self.lbl_tour.setText(f"Recorridos: {len(tours)} activos, pendiente")
            return
        when = time.strftime("%H:%M:%S", time.localtime(res.started))
        state = "OK" if res.ok else ("pospuesto" if res.skipped else "FALLÓ")
        color = "#2e7d32" if res.ok else ("#9e9e9e" if res.skipped else "#c62828")
        detail = res.message.replace("pospuesto: ", "") if res.skipped else res.message
        t = self.ctx.config.get_tour(res.tour_id)
        name = f"«{t.name}» " if t and len(tours) > 1 else ""
        self.lbl_tour.setText(f"<span style='color:{color}'>Recorrido {name}{when}: {state}</span> · {detail}")

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
        self._update_table(snap)
        self._update_plots(snap)
        self._refresh_analysis()
        self._update_findings(snap)
        self._append_events(snap)
        counts = {lvl: sum(1 for f in snap.findings if f.level == lvl) for lvl in Level}
        if snap.error:
            self._set_banner(Level.ALARM, snap.error)
        elif self.engine.running:
            text = {Level.OK: "PROCESO OK", Level.INFO: "PROCESO OK",
                    Level.WARN: "AVISO", Level.ALARM: "ALARMA"}[snap.overall]
            detail = f"   ·   {counts[Level.ALARM]} alarmas · {counts[Level.WARN]} avisos"
            self._set_banner(snap.overall if snap.overall > Level.INFO else Level.OK, text + detail)
        pages = ", ".join(sorted(snap.pages)) or ("—" if self.ctx.config.pages else "sin páginas definidas")
        self.lbl_page.setText(f"Página HMI: {pages}")
        self._update_tour_label()
        self.lbl_ocr.setText(f"OCR: {snap.ocr_engine} · lecturas {snap.read_ok}/{snap.read_total}")
        self.lbl_cycle.setText(f"Ciclo: {snap.cycle_ms:.0f} ms · {time.strftime('%H:%M:%S', time.localtime(snap.ts))}")

    def open_behavior(self) -> None:
        from .behavior_dialog import BehaviorDialog
        BehaviorDialog(self.ctx, self, preselect=[v for v in self._plotted]).exec()
        self.engine.save_profile()
        self.behavior_panel.set_models()

    def _refresh_analysis(self, force: bool = False) -> None:
        w = self.analysis.currentWidget()
        if w is self.trends:
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
        rng = self.trends.range_s
        t, y = self.engine.series(vid)
        window = self.ctx.config.general.trend_window_min * 60
        if rng <= window or self.engine.historian is None:
            return t, y
        now = time.time()
        cached = self._hist_cache.get(vid)
        # El historial se consulta como máximo cada 15 s por variable (no carga la PC).
        if cached is None or cached[0] != rng or now - cached[1] > 15:
            rows = [r for r in self.engine.historian.samples(vid, now - rng, now + 60) if r[1] is not None]
            arr = np.asarray(rows, float) if rows else np.empty((0, 2))
            cached = (rng, now, arr[:, 0] if len(arr) else np.empty(0), arr[:, 1] if len(arr) else np.empty(0))
            self._hist_cache[vid] = cached
        ht, hy = cached[2], cached[3]
        if len(t):
            keep = ht < t[0]
            ht, hy = np.concatenate([ht[keep], t]), np.concatenate([hy[keep], y])
        return ht, hy

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
            vals = [time.strftime("%H:%M:%S", time.localtime(f.since)), f.level.label, f.rule, name, f.message]
            for c, text in enumerate(vals):
                it = QTableWidgetItem(text)
                if c == 1:
                    it.setBackground(QBrush(level_color(f.level)))
                    it.setForeground(QBrush(QColor("white")))
                self.findings.setItem(i, c, it)
        n_alarm = sum(1 for f in snap.findings if f.level >= Level.WARN)
        self.tabs.setTabText(0, f"Hallazgos activos ({n_alarm})" if n_alarm else "Hallazgos activos")

    def _append_events(self, snap: Snapshot) -> None:
        alarm = False
        for e in snap.events:
            item = QListWidgetItem(f"{time.strftime('%H:%M:%S', time.localtime(e.ts))}  "
                                   f"[{e.level.label}]  {e.message}")
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
        self.engine.stop()
        self._save_state()
        if self.engine.historian:
            self.engine.historian.close()
        super().closeEvent(event)


def start_timer_autorun(window: MainWindow, delay_ms: int = 300) -> None:
    QTimer.singleShot(delay_ms, window.toggle_run)
