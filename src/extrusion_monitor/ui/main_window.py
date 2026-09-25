"""Ventana principal: estado de variables, tendencias, hallazgos y registro."""
from __future__ import annotations

import time
from typing import Optional

import pyqtgraph as pg
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction, QBrush, QColor
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QFileDialog, QHeaderView, QLabel, QListWidget,
    QListWidgetItem, QMainWindow, QMessageBox, QSplitter, QTableWidget, QTableWidgetItem,
    QTabWidget, QToolBar, QVBoxLayout, QWidget,
)

from ..analysis.rules import Level
from ..bootstrap import AppContext, make_clicker, make_ocr
from ..capture import ScreenSource
from ..navigation import exclude_window_from_capture
from ..engine import Snapshot
from .common import SnapshotBridge, level_color
from .variable_tree import VariableTree

MAX_PLOTS = 4


class TrendPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        pg.setConfigOptions(antialias=True)
        self.layout_ = QVBoxLayout(self)
        self.layout_.setContentsMargins(0, 0, 0, 0)
        self.plots: dict[str, dict] = {}
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
            w.showGrid(x=True, y=True, alpha=0.3)
            curve = w.plot(pen=pg.mkPen("#4fc3f7", width=2), name="medición")
            sp_curve = w.plot(pen=pg.mkPen("#1e88e5", width=2, style=Qt.DashLine), name="consigna")
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
            self.plots[vid] = {"widget": w, "curve": curve, "sp": sp_curve, "lines": lines}
        self.placeholder.setVisible(not self.plots)

    def update_plot(self, vid: str, t, y, ref: Optional[float], warn: Optional[float],
                    alarm: Optional[float], sp_series=None) -> None:
        p = self.plots.get(vid)
        if not p:
            return
        p["curve"].setData(t, y)
        if sp_series is not None and len(sp_series[0]):
            # La consigna es escalonada: se prolonga hasta el último instante de la medición.
            st, sy = sp_series
            if len(t) and t[-1] > st[-1]:
                import numpy as np
                st, sy = np.append(st, t[-1]), np.append(sy, sy[-1])
            p["sp"].setData(st, sy)
        lines = p["lines"]
        for key, val in (("ref", ref),
                         ("wl", ref - warn if ref is not None and warn is not None else None),
                         ("wh", ref + warn if ref is not None and warn is not None else None),
                         ("al", ref - alarm if ref is not None and alarm is not None else None),
                         ("ah", ref + alarm if ref is not None and alarm is not None else None)):
            lines[key].setVisible(val is not None)
            if val is not None:
                lines[key].setValue(val)


class MainWindow(QMainWindow):
    def __init__(self, ctx: AppContext):
        super().__init__()
        self.ctx = ctx
        self.engine = ctx.engine
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
        act_export = QAction("⤓ Exportar CSV", self)
        act_export.triggered.connect(self.export_csv)
        tb.addAction(act_export)
        tb.addSeparator()
        self.act_tour_pause = QAction("⏸ Pausar recorrido", self, checkable=True)
        self.act_tour_pause.setToolTip("Detiene los clics automáticos en el HMI (se siguen leyendo los datos visibles)")
        self.act_tour_pause.toggled.connect(self._tour_pause)
        tb.addAction(self.act_tour_pause)
        act = QAction("⟳ Recorrer ahora", self)
        act.triggered.connect(self.engine.run_tour_now)
        tb.addAction(act)
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
        self.table.plotToggled.connect(self._plot_toggled)
        hsplit.addWidget(self.table)
        self.trends = TrendPanel()
        hsplit.addWidget(self.trends)
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
        lay.addWidget(vsplit)
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
            self._plotted = [v.id for v in cfg.variables if v.kind == "actual" and v.trend][:3]
        self._plotted = [vid for vid in self._plotted if cfg.variable(vid)]
        self.table.rebuild(cfg, self._plotted)
        self._sync_plots()

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

    def _update_tour_label(self) -> None:
        t = self.ctx.config.tour
        if not t.enabled or not t.steps:
            self.lbl_tour.setText("Recorrido: desactivado")
            return
        if self.engine.tour_paused:
            self.lbl_tour.setText("Recorrido: EN PAUSA")
            return
        res = self.engine.tour.last_result
        if res is None:
            self.lbl_tour.setText("Recorrido: pendiente")
            return
        when = time.strftime("%H:%M:%S", time.localtime(res.started))
        state = "OK" if res.ok else ("pospuesto" if res.skipped else "FALLÓ")
        color = "#2e7d32" if res.ok else ("#9e9e9e" if res.skipped else "#c62828")
        detail = res.message.replace("pospuesto: ", "") if res.skipped else res.message
        self.lbl_tour.setText(f"<span style='color:{color}'>Recorrido {when}: {state}</span> · {detail}")

    def _always_on_top(self, on: bool) -> None:
        self.setWindowFlag(Qt.WindowStaysOnTopHint, on)
        self.show()

    # --- actualización -----------------------------------------------------------
    def on_snapshot(self, snap: Snapshot) -> None:
        if snap.recipe != self.cmb_recipe.currentData():
            self.refresh_recipes()
        self._update_table(snap)
        self._update_plots(snap)
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

    def _update_table(self, snap: Snapshot) -> None:
        self.table.update_snapshot(snap)

    def _update_plots(self, snap: Snapshot) -> None:
        for vid in self._plotted:
            t, y = self.engine.series(vid)
            st = snap.statuses.get(vid)
            if st is None:
                continue
            sp_id = self.table.setpoint_of(vid)
            sp_series = self.engine.series(sp_id) if sp_id else None
            self.trends.update_plot(vid, t, y, st.reference, st.warn_band, st.alarm_band, sp_series)

    def _update_findings(self, snap: Snapshot) -> None:
        self.findings.setRowCount(len(snap.findings))
        for i, f in enumerate(snap.findings):
            var = self.ctx.config.variable(f.var_id)
            vals = [time.strftime("%H:%M:%S", time.localtime(f.since)), f.level.label, f.rule,
                    var.name if var else "", f.message]
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
