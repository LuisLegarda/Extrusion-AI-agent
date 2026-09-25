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

from ..analysis.rules import Level, fmt
from ..bootstrap import AppContext, make_ocr
from ..capture import ScreenSource
from ..engine import Snapshot
from .common import LEVEL_TEXT, SnapshotBridge, level_color

COLS = ["Ver", "Variable", "Grupo", "Valor", "Unidad", "Referencia", "Desv.", "Tol. ±",
        "Estado", "Tendencia /min", "Cpk", "Lectura"]
C_VIEW, C_NAME, C_GROUP, C_VALUE, C_UNIT, C_REF, C_DEV, C_TOL, C_STATE, C_TREND, C_CPK, C_READ = range(12)
MAX_PLOTS = 4


class TrendPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        pg.setConfigOptions(antialias=True)
        self.layout_ = QVBoxLayout(self)
        self.layout_.setContentsMargins(0, 0, 0, 0)
        self.plots: dict[str, dict] = {}
        self.placeholder = QLabel("Marca la casilla «Ver» de una variable para graficar su tendencia.")
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
            curve = w.plot(pen=pg.mkPen("#4fc3f7", width=2))
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
            self.plots[vid] = {"widget": w, "curve": curve, "lines": lines}
        self.placeholder.setVisible(not self.plots)

    def update_plot(self, vid: str, t, y, ref: Optional[float], warn: Optional[float],
                    alarm: Optional[float]) -> None:
        p = self.plots.get(vid)
        if not p:
            return
        p["curve"].setData(t, y)
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
        self._rows: dict[str, int] = {}
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
        self.table = QTableWidget(0, len(COLS))
        self.table.setHorizontalHeaderLabels(COLS)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.itemChanged.connect(self._item_changed)
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

        self.lbl_page = QLabel()
        self.lbl_ocr = QLabel()
        self.lbl_cycle = QLabel()
        for w in (self.lbl_page, self.lbl_ocr, self.lbl_cycle):
            self.statusBar().addPermanentWidget(w)

    def _update_title(self) -> None:
        demo = " — MODO DEMO (HMI simulado)" if self.ctx.demo else ""
        self.setWindowTitle(f"Monitor de extrusión · {self.ctx.config.machine_name}{demo}")

    def _set_banner(self, level: Optional[Level], text: str) -> None:
        self.banner.setText(text)
        self.banner.setStyleSheet(f"background:{level_color(level).name()};")

    def rebuild_table(self) -> None:
        cfg = self.ctx.config
        self.table.blockSignals(True)
        self.table.setRowCount(0)
        self._rows.clear()
        groups: list[str] = []
        for v in cfg.variables:
            if v.group not in groups:
                groups.append(v.group)
        index = {v.id: i for i, v in enumerate(cfg.variables)}
        order = sorted(cfg.variables, key=lambda v: (groups.index(v.group), index[v.id]))
        if not self._plotted:
            self._plotted = [v.id for v in cfg.variables if v.kind == "actual" and v.trend][:3]
        self._plotted = [vid for vid in self._plotted if cfg.variable(vid)]
        for row, var in enumerate(order):
            self.table.insertRow(row)
            self._rows[var.id] = row
            view = QTableWidgetItem()
            if var.kind != "text":
                view.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
                view.setCheckState(Qt.Checked if var.id in self._plotted else Qt.Unchecked)
            else:
                view.setFlags(Qt.ItemIsEnabled)
            view.setData(Qt.UserRole, var.id)
            self.table.setItem(row, C_VIEW, view)
            kind = {"actual": "", "setpoint": " (consigna)", "text": " (texto)"}[var.kind]
            self.table.setItem(row, C_NAME, QTableWidgetItem(var.name + kind))
            self.table.setItem(row, C_GROUP, QTableWidgetItem(var.group))
            self.table.setItem(row, C_UNIT, QTableWidgetItem(var.unit))
            for c in (C_VALUE, C_REF, C_DEV, C_TOL, C_STATE, C_TREND, C_CPK, C_READ):
                it = QTableWidgetItem("")
                if c in (C_VALUE, C_REF, C_DEV, C_TOL, C_TREND, C_CPK):
                    it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.table.setItem(row, c, it)
        self.table.blockSignals(False)
        self._sync_plots()

    def _sync_plots(self) -> None:
        cfg = self.ctx.config
        items = []
        for vid in self._plotted:
            v = cfg.variable(vid)
            if v:
                items.append((vid, f"{v.name} [{v.unit}]" if v.unit else v.name))
        self.trends.set_variables(items)

    def _item_changed(self, item: QTableWidgetItem) -> None:
        if item.column() != C_VIEW:
            return
        vid = item.data(Qt.UserRole)
        if item.checkState() == Qt.Checked:
            if vid not in self._plotted:
                self._plotted.append(vid)
                if len(self._plotted) > MAX_PLOTS:
                    dropped = self._plotted.pop(0)
                    row = self._rows.get(dropped)
                    if row is not None:
                        self.table.blockSignals(True)
                        self.table.item(row, C_VIEW).setCheckState(Qt.Unchecked)
                        self.table.blockSignals(False)
        elif vid in self._plotted:
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
        dlg = SetupDialog(self.ctx, self)
        if dlg.exec():
            self.engine.stop()
            if not self.ctx.demo and dlg.config.general.monitor != self.ctx.config.general.monitor:
                self.engine.source = ScreenSource(dlg.config.general.monitor)
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
        self.lbl_ocr.setText(f"OCR: {snap.ocr_engine} · lecturas {snap.read_ok}/{snap.read_total}")
        self.lbl_cycle.setText(f"Ciclo: {snap.cycle_ms:.0f} ms · {time.strftime('%H:%M:%S', time.localtime(snap.ts))}")

    def _update_table(self, snap: Snapshot) -> None:
        for vid, st in snap.statuses.items():
            row = self._rows.get(vid)
            if row is None:
                continue
            var, rd = st.var, st.reading
            if var.kind == "text":
                value = rd.text or ""
            else:
                value = fmt(rd.value, var) if rd.value is not None else ""
            tol = ""
            if st.warn_band is not None or st.alarm_band is not None:
                tol = f"{fmt(st.warn_band)} / {fmt(st.alarm_band)}"
            trend = ""
            if st.trend:
                arrow = "↑" if st.trend.slope_per_min > 0 else "↓"
                trend = f"{arrow} {st.trend.slope_per_min:+.3g}" if st.trend.slope_significant else "→ estable"
            ref = f"{fmt(st.reference, var)} ({st.ref_source})" if st.reference is not None else ""
            cells = {
                C_VALUE: value,
                C_REF: ref,
                C_DEV: f"{st.deviation:+.4g}" if st.deviation is not None else "",
                C_TOL: tol,
                C_STATE: LEVEL_TEXT[st.level] if st.fresh else ("no visible" if not rd.visible else "sin dato"),
                C_TREND: trend,
                C_CPK: f"{st.trend.cpk:.2f}" if st.trend and st.trend.cpk is not None else "",
                C_READ: "ok" if rd.ok else (rd.reason or "—"),
            }
            for c, text in cells.items():
                item = self.table.item(row, c)
                if item.text() != text:
                    item.setText(text)
            color = level_color(st.level if st.fresh else None)
            state_item = self.table.item(row, C_STATE)
            state_item.setBackground(QBrush(color))
            state_item.setForeground(QBrush(QColor("white")))
            val_item = self.table.item(row, C_VALUE)
            if st.level is not None and st.level >= Level.WARN and st.fresh:
                val_item.setForeground(QBrush(color))
            else:
                val_item.setForeground(self.table.palette().text())

    def _update_plots(self, snap: Snapshot) -> None:
        for vid in self._plotted:
            t, y = self.engine.series(vid)
            st = snap.statuses.get(vid)
            if st is None:
                continue
            self.trends.update_plot(vid, t, y, st.reference, st.warn_band, st.alarm_band)

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
