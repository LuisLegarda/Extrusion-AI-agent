"""Dashboard global: estado de todas las líneas a partir de la carpeta compartida.

Cada línea se muestra en una tarjeta con 1 a 5 indicadores configurables (plantilla común con excepciones
por línea), agrupadas por área. Avisa con sonido y parpadeo cuando una línea entra en alarma, se detiene o
pierde comunicación. Tiene modo TV (pantalla completa con páginas que rotan) y exportación a CSV.
"""
from __future__ import annotations

import csv
import json
import time
from pathlib import Path
from typing import Optional

import pyqtgraph as pg
from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QActionGroup, QBrush, QColor, QDesktopServices, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication, QComboBox, QFileDialog, QFrame, QGridLayout, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
    QListWidget, QListWidgetItem, QMainWindow, QMenu, QMessageBox, QPushButton, QScrollArea, QSplitter, QTableWidget,
    QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget,
)

from .. import version_label
from ..fleet import FleetReader, FleetSettings, LineState, load_fleet_settings, save_fleet_settings
from ..i18n import LANGS, lang as i18n_lang, tr, translate_text
from . import theme
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


class SummaryTile(QFrame):
    def __init__(self, title: str):
        super().__init__()
        self.setObjectName("card")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 6, 10, 6)
        t = QLabel(tr(title))
        t.setStyleSheet(f"color:{theme.c('muted')};")
        lay.addWidget(t)
        self.val = QLabel("—")
        lay.addWidget(self.val)

    def set(self, text: str, color: Optional[str] = None) -> None:
        self.val.setText(f"<span style='font-size:22px; color:{color or theme.c('text')}'><b>{text}</b></span>")


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
        root = QVBoxLayout(central)
        self.top = QWidget()
        top = QHBoxLayout(self.top)
        top.setContentsMargins(0, 0, 0, 0)
        self.lbl_dir = QLabel()
        top.addWidget(self.lbl_dir, 1)
        for text, slot, tip in (("⚙ Configuración", self.open_setup, "Carpeta de datos, indicadores, áreas y avisos"),
                                ("✔ Reconocer avisos", self.acknowledge_all, "Detiene el parpadeo de las tarjetas (Ctrl+K)"),
                                ("⤓ Exportar CSV", self.export_csv, "Estado y OEE de todas las líneas"),
                                ("📺 Modo TV (F11)", self.toggle_tv, "Pantalla completa con páginas que rotan")):
            b = QPushButton(text)
            b.setToolTip(tip)
            b.clicked.connect(slot)
            top.addWidget(b)
        self.ed_search = QLineEdit()
        self.ed_search.setPlaceholderText("Buscar línea…")
        self.ed_search.setMinimumWidth(150)
        self.ed_search.setMaximumWidth(220)
        self.ed_search.textChanged.connect(lambda _: self.refresh(rescan=False))
        top.addWidget(self.ed_search)
        self.cmb_filter = QComboBox()
        for k, label in FILTERS:
            self.cmb_filter.addItem(label, k)
        self.cmb_filter.currentIndexChanged.connect(lambda _: self.refresh(rescan=False))
        top.addWidget(self.cmb_filter)
        top.addWidget(QLabel("Orden:"))
        self.cmb_sort = QComboBox()
        for k, label in SORTS:
            self.cmb_sort.addItem(label, k)
        self.cmb_sort.currentIndexChanged.connect(lambda _: self.refresh(rescan=False))
        top.addWidget(self.cmb_sort)
        root.addWidget(self.top)

        summary = QHBoxLayout()
        self.tiles = {k: SummaryTile(t) for k, t in (
            ("lines", "Líneas"), ("running", "En marcha"), ("stopped", "Detenidas"), ("alarm", "Con alarma"),
            ("offline", "Sin comunicación"), ("oee", "OEE promedio (turno)"))}
        for t in self.tiles.values():
            summary.addWidget(t)
        self.lbl_page = QLabel()
        summary.addWidget(self.lbl_page)
        root.addLayout(summary)

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
        root.addWidget(self.split, 1)
        self.setCentralWidget(central)
        self._build_menus()

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

    # --- menús: archivo, vista, idioma y tema ------------------------------------------------
    def _build_menus(self) -> None:
        """Solo lo que no está ya a la vista: Archivo · Configuración · Ver · Ayuda (mismo orden que el monitor).

        Filtro, orden, búsqueda, reconocer avisos, exportar y modo TV están en la barra superior; sonido y
        agrupar por área, en la configuración.
        """
        mb = self.menuBar()
        m = mb.addMenu("&Archivo")
        act = m.addAction("⤓ Exportar resumen a CSV…", self.export_csv)
        act.setShortcut("Ctrl+E")
        m.addSeparator()
        act = m.addAction("Salir", self.close)
        act.setShortcut("Ctrl+Q")

        m = mb.addMenu("C&onfiguración")
        m.addAction("⚙ Carpeta de datos y avisos…", lambda: self.open_setup(0))
        m.addAction("Indicadores de las tarjetas…", lambda: self.open_setup(1))
        m.addAction("Líneas y áreas…", lambda: self.open_setup(2))
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
        for t in (self.timer, self.trend_timer, self.tv_timer, self.blink):
            t.stop()
        super().closeEvent(event)

    # --- configuración ---------------------------------------------------------------------
    def _set_dir_label(self) -> None:
        d = self.settings.dir
        self.lbl_dir.setText(f"<b>{tr('Carpeta')}:</b> {d or tr('(sin elegir)')}")

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

    def choose_folder(self) -> None:
        d = QFileDialog.getExistingDirectory(self, tr("Carpeta de datos de las líneas"), self.settings.dir)
        if d:
            self.set_folder(d)

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
        if self.reader.error:
            self.empty.setText(tr("No se puede leer la carpeta: {e}", e=self.reader.error))
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
        for c in self.cards.values():
            c.acknowledge()

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
        self.tiles["alarm"].set(str(sum(bool(ln.status.get("n_alarms")) for ln in online)), theme.c("critical"))
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
    def toggle_tv(self) -> None:
        self.tv = not self.tv
        self.top.setVisible(not self.tv)
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

    def export_csv(self, path: Optional[str] = None) -> Optional[str]:
        if not path:
            path, _ = QFileDialog.getSaveFileName(self, tr("Exportar resumen de líneas"),
                                                  f"lineas_{time.strftime('%Y%m%d_%H%M')}.csv", "CSV (*.csv)")
        if not path:
            return None
        now = time.time()
        s = self.settings
        cols = ["linea", "id", "area", "comunicacion", "estado", "receta", "oee_%", "disponibilidad_%",
                "rendimiento_%", "calidad_%", "producido", "conforme", "unidad", "paros", "alarmas", "avisos",
                "actualizado"]
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f, delimiter=";")
            w.writerow([tr(c) for c in cols])
            for lid in sorted(self.reader.lines, key=lambda k: natural(self.reader.lines[k].name)):
                ln = self.reader.lines[lid]
                st = ln.status
                k = st.get("kpis") or {}
                o = st.get("oee") or {}

                def num(v, d=1):
                    return "" if v is None else f"{v:.{d}f}".replace(".", ",")

                w.writerow([ln.name, lid, s.area_of(ln), tr(CONN_TEXT[ln.connection(now, s.offline_s)]),
                            (st.get("machine") or {}).get("label", ""), st.get("recipe") or "",
                            num(k.get("oee")), num(k.get("availability")), num(k.get("performance")),
                            num(k.get("quality")), num(o.get("length_total"), 0), num(o.get("length_good"), 0),
                            o.get("unit", ""), o.get("n_stops", ""), st.get("n_alarms", 0), st.get("n_warnings", 0),
                            time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(st["ts"])) if st.get("ts") else ""])
        return path

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._layout_key = None
        if self.cards:
            QTimer.singleShot(0, lambda: self.refresh(rescan=False))


rebuilt_fleet_windows: list = []  # referencia a la ventana nueva tras cambiar idioma o tema


def run_fleet(folder: Optional[str], home: Optional[Path] = None) -> int:
    import logging
    import sys

    from ..config import default_home
    from ..i18n import Translator
    from .main_window import apply_ui_prefs

    home_dir = Path(home) if home else default_home()
    home_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(level=logging.INFO, filename=str(home_dir / "fleet.log"),
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    app = QApplication.instance() or QApplication(sys.argv[:1])
    app.setApplicationName("Dashboard global de líneas")
    try:
        state = json.loads((home_dir / "state.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        state = {}
    apply_ui_prefs(state.get("ui", {}))
    Translator().install(app)
    win = FleetWindow(folder, home_dir / "fleet.json", home_dir / "state.json")
    win.show()
    if not win.settings.dir:
        QTimer.singleShot(300, win.open_setup)  # primera vez: pedir la carpeta de datos
    return app.exec()
