"""Dashboard global: estado de todas las líneas a partir de la carpeta compartida."""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Optional

import pyqtgraph as pg
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (
    QApplication, QComboBox, QFileDialog, QFrame, QGridLayout, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
    QListWidget, QListWidgetItem, QMainWindow, QPushButton, QScrollArea, QSplitter, QTableWidget, QTableWidgetItem,
    QTabWidget, QVBoxLayout, QWidget,
)

from ..analysis.oee import STATE_LABELS
from ..fleet import FleetReader, LineState
from ..i18n import tr
from . import theme

POLL_MS = 5000
CARD_W = 270
LEVEL_KEYS = {"ALARM": "critical", "WARN": "warning", "OK": "good", "INFO": "info"}
STATE_KEYS = {"running": "good", "assumed": "good_soft", "slow": "warning", "microstop": "serious",
              "stopped": "critical", "unknown": "neutral"}
CONN_TEXT = {"online": "En línea", "stale": "Retrasada", "offline": "Sin comunicación", "closed": "Programa cerrado"}
FILTERS = [("all", "Todas"), ("alarm", "Con alarma o aviso"), ("stopped", "Detenidas"),
           ("offline", "Sin comunicación")]
SORTS = [("name", "Nombre"), ("status", "Gravedad"), ("oee", "OEE (menor primero)")]
TREND_RANGES = [("1 h", 3600), ("8 h", 8 * 3600), ("24 h", 86400), ("7 días", 7 * 86400)]


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


def natural(text: str) -> list:
    """Orden natural: «Línea 2» antes que «Línea 10»."""
    import re
    return [int(p) if p.isdigit() else p for p in re.split(r"(\d+)", text.lower())]


def severity(line: LineState, now: float) -> int:
    """0 = sin comunicación … 4 = alarma (para ordenar: lo más grave primero)."""
    conn = line.connection(now)
    st = line.status
    if conn in ("offline", "closed"):
        return 3
    if st.get("n_alarms"):
        return 4
    if (st.get("machine") or {}).get("state") in ("stopped", "microstop"):
        return 3
    if st.get("n_warnings"):
        return 2
    return 1


class LineCard(QFrame):
    clicked = Signal(str)

    def __init__(self, line_id: str):
        super().__init__()
        self.line_id = line_id
        self.setObjectName("card")
        self.setFixedWidth(CARD_W)
        self.setMinimumHeight(150)
        self.setCursor(Qt.PointingHandCursor)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 8, 10, 8)
        lay.setSpacing(3)
        self.lbl_name = QLabel()
        self.lbl_state = QLabel()
        self.lbl_recipe = QLabel()
        self.lbl_kpi = QLabel()
        self.lbl_alarm = QLabel()
        self.lbl_age = QLabel()
        for w in (self.lbl_name, self.lbl_state, self.lbl_recipe, self.lbl_kpi, self.lbl_alarm, self.lbl_age):
            w.setTextFormat(Qt.RichText)
            lay.addWidget(w)
        self.lbl_recipe.setStyleSheet(f"color:{theme.c('text2')};")
        self.lbl_age.setStyleSheet(f"color:{theme.c('muted')}; font-size:11px;")
        self._sel = False

    def set_selected(self, on: bool) -> None:
        self._sel = on

    def update_line(self, line: LineState, now: float) -> None:
        st = line.status
        conn = line.connection(now)
        sev = severity(line, now)
        border = {4: "critical", 3: "neutral" if conn in ("offline", "closed") else "critical", 2: "warning",
                  1: "good"}[sev]
        width = 3 if self._sel else 2
        style = f"#card {{ border: {width}px solid {theme.c(border)}; border-radius: 8px; }}"
        if style != self.styleSheet():  # solo si cambió (recalcular estilos de 100 tarjetas es costoso)
            self.setStyleSheet(style)
        dot = theme.c({"online": "good", "stale": "warning"}.get(conn, "neutral"))
        self.lbl_name.setText(f"<span style='color:{dot}'>●</span> <span style='font-size:15px; "
                              f"color:{theme.c('title')}'><b>{line.name}</b></span>")
        machine = st.get("machine") or {}
        if conn in ("offline", "closed"):
            state = f"<span style='font-size:18px; color:{theme.c('muted')}'><b>{tr(CONN_TEXT[conn])}</b></span>"
        elif machine.get("state"):
            color = theme.c(STATE_KEYS.get(machine["state"], "neutral"))
            since = machine.get("since")
            dur = f" · {fmt_age(now - since).replace(tr('hace') + ' ', '')}" if since else ""
            state = (f"<span style='font-size:18px; color:{color}'><b>{tr(STATE_LABELS.get(machine['state'], ''))}"
                     f"</b></span><span style='color:{theme.c('muted')}'>{dur}</span>")
        else:
            mon = tr("Monitoreando") if st.get("monitoring") else tr("Monitoreo detenido")
            state = f"<span style='font-size:16px'><b>{mon}</b></span>"
        self.lbl_state.setText(state)
        self.lbl_recipe.setText(tr("Receta: {r}", r=st.get("recipe") or "—"))
        o = st.get("oee") or {}
        if o:
            self.lbl_kpi.setText(f"OEE <b style='font-size:15px'>{pct(o.get('oee'))}</b> &nbsp; "
                                 f"<span style='color:{theme.c('muted')}; font-size:11px'>"
                                 f"D {pct(o.get('availability'))} · R {pct(o.get('performance'))} · "
                                 f"C {pct(o.get('quality'))}</span>")
        else:
            self.lbl_kpi.setText(f"<span style='color:{theme.c('muted')}'>{tr('OEE sin configurar')}</span>")
        na, nw = st.get("n_alarms") or 0, st.get("n_warnings") or 0
        if na or nw:
            first = (st.get("alarms") or [{}])[0].get("msg", "")
            self.lbl_alarm.setText(
                f"<b style='color:{theme.c('critical')}'>{tr('{n} alarmas', n=na)}</b> · "
                f"<b style='color:{theme.c('warning_text')}'>{tr('{n} avisos', n=nw)}</b><br>"
                f"<span style='font-size:11px'>{first[:70]}</span>")
        else:
            self.lbl_alarm.setText(f"<span style='color:{theme.c('good_text')}'>{tr('✔ Sin alarmas')}</span>"
                                   if conn == "online" else "")
        self.lbl_age.setText(tr("Actualizado {a}", a=fmt_age(line.age(now))) +
                             (f" · {st.get('error')}" if st.get("error") else ""))
        self.setToolTip(f"{line.line_id}\n{line.path}")

    def mousePressEvent(self, event) -> None:
        self.clicked.emit(self.line_id)
        super().mousePressEvent(event)


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
            it = QListWidgetItem(f"{time.strftime('%H:%M:%S', time.localtime(a['since']))}  {a['msg']}")
            it.setForeground(QBrush(QColor(theme.c(LEVEL_KEYS.get(a.get("level"), "neutral")))))
            self.lst_alarms.addItem(it)
        if not self.lst_alarms.count():
            self.lst_alarms.addItem(tr("✔ Sin alarmas ni avisos activos"))
        self.lst_events.clear()
        for e in reversed(line.events[-200:]):
            it = QListWidgetItem(f"{time.strftime('%d/%m %H:%M:%S', time.localtime(e.get('ts', 0)))}  "
                                 f"[{e.get('level', '')}]  {e.get('msg', '')}")
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
    def __init__(self, folder: Optional[str], settings_file: Path):
        super().__init__()
        self.settings_file = settings_file
        self.setWindowTitle(tr("Dashboard global de líneas"))
        self.resize(1500, 900)
        self.reader = FleetReader(folder or "")
        self.cards: dict[str, LineCard] = {}
        self.selected: Optional[str] = None
        self.plant_events: list[dict] = []
        self._order: list[str] = []
        self._cols = 0

        central = QWidget()
        root = QVBoxLayout(central)
        top = QHBoxLayout()
        self.lbl_dir = QLabel()
        top.addWidget(self.lbl_dir, 1)
        b = QPushButton("📂 Carpeta compartida…")
        b.clicked.connect(self.choose_folder)
        top.addWidget(b)
        self.ed_search = QLineEdit()
        self.ed_search.setPlaceholderText("Buscar línea…")
        self.ed_search.setMaximumWidth(220)
        self.ed_search.textChanged.connect(lambda _: self.refresh(rescan=False))
        top.addWidget(self.ed_search)
        self.cmb_filter = QComboBox()
        for k, label in FILTERS:
            self.cmb_filter.addItem(label, k)
        self.cmb_filter.currentIndexChanged.connect(lambda _: self.refresh(rescan=False))
        top.addWidget(self.cmb_filter)
        self.cmb_sort = QComboBox()
        for k, label in SORTS:
            self.cmb_sort.addItem(label, k)
        self.cmb_sort.currentIndexChanged.connect(lambda _: self.refresh(rescan=False))
        top.addWidget(QLabel("Orden:"))
        top.addWidget(self.cmb_sort)
        root.addLayout(top)

        summary = QHBoxLayout()
        self.tiles = {k: SummaryTile(t) for k, t in (
            ("lines", "Líneas"), ("running", "En marcha"), ("stopped", "Detenidas"), ("alarm", "Con alarma"),
            ("offline", "Sin comunicación"), ("oee", "OEE promedio (turno)"))}
        for t in self.tiles.values():
            summary.addWidget(t)
        root.addLayout(summary)

        split = QSplitter(Qt.Horizontal)
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
        vsplit = QSplitter(Qt.Vertical)
        vsplit.addWidget(left)
        ev = QWidget()
        el = QVBoxLayout(ev)
        el.setContentsMargins(0, 0, 0, 0)
        el.addWidget(QLabel("<b>Alarmas y avisos recientes de la planta</b>"))
        self.lst_plant = QListWidget()
        self.lst_plant.itemDoubleClicked.connect(lambda it: self.select(it.data(Qt.UserRole)))
        el.addWidget(self.lst_plant, 1)
        vsplit.addWidget(ev)
        vsplit.setSizes([650, 200])
        split.addWidget(vsplit)
        self.detail = LineDetail(self.reader)
        split.addWidget(self.detail)
        split.setSizes([950, 550])
        root.addWidget(split, 1)
        self.setCentralWidget(central)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(POLL_MS)
        self.trend_timer = QTimer(self)
        self.trend_timer.timeout.connect(self.detail.refresh_trend)
        self.trend_timer.start(60000)  # la tendencia llega por minuto
        self._set_dir_label()
        QTimer.singleShot(0, self.refresh)

    # --- carpeta ---------------------------------------------------------------------------
    def _set_dir_label(self) -> None:
        d = str(self.reader.root) if str(self.reader.root) not in ("", ".") else ""
        self.lbl_dir.setText(f"<b>{tr('Carpeta')}:</b> {d or tr('(sin elegir)')}")

    def choose_folder(self) -> None:
        d = QFileDialog.getExistingDirectory(self, tr("Carpeta compartida de las líneas"), str(self.reader.root))
        if not d:
            return
        self.set_folder(d)

    def set_folder(self, d: str) -> None:
        self.reader = FleetReader(d)
        self.detail.reader = self.reader
        self.plant_events.clear()
        for c in self.cards.values():
            c.deleteLater()
        self.cards.clear()
        self._order = []
        self._set_dir_label()
        try:
            self.settings_file.write_text(json.dumps({"dir": d}, ensure_ascii=False), encoding="utf-8")
        except OSError:
            pass
        self.refresh()

    # --- actualización ---------------------------------------------------------------------
    def refresh(self, rescan: bool = True) -> None:
        now = time.time()
        if str(self.reader.root) in ("", "."):
            self.empty.setText(tr("Elige la carpeta compartida donde escriben las líneas (📂 Carpeta compartida…)."))
            self.empty.setVisible(True)
            return
        if rescan:
            new = self.reader.scan()
            self.plant_events = (self.plant_events + [e for e in new if e.get("level") in ("WARN", "ALARM")])[-500:]
            if new:
                self._fill_plant_events()
        lines = self.reader.lines
        for lid in lines:
            if lid not in self.cards:
                card = LineCard(lid)
                card.clicked.connect(self.select)
                self.cards[lid] = card
        for lid in [k for k in self.cards if k not in lines]:
            self.cards.pop(lid).deleteLater()
        shown = self._visible(now)
        for lid in shown:
            self.cards[lid].update_line(lines[lid], now)
        self._layout(shown)
        self._summary(now)
        if self.reader.error:
            self.empty.setText(tr("No se puede leer la carpeta: {e}", e=self.reader.error))
        elif not lines:
            self.empty.setText(tr("Ninguna línea ha escrito todavía en esta carpeta."))
        self.empty.setVisible(bool(self.reader.error) or not lines)
        if self.selected:
            self.detail.refresh(now)

    def _visible(self, now: float) -> list[str]:
        lines = self.reader.lines
        q = self.ed_search.text().strip().lower()
        flt = self.cmb_filter.currentData()
        out = []
        for lid, ln in lines.items():
            if q and q not in ln.name.lower() and q not in lid.lower():
                continue
            st = ln.status
            conn = ln.connection(now)
            if flt == "alarm" and not (st.get("n_alarms") or st.get("n_warnings")):
                continue
            if flt == "stopped" and (st.get("machine") or {}).get("state") not in ("stopped", "microstop"):
                continue
            if flt == "offline" and conn not in ("offline", "closed", "stale"):
                continue
            out.append(lid)
        key = self.cmb_sort.currentData()
        if key == "status":
            out.sort(key=lambda k: (-severity(lines[k], now), natural(lines[k].name)))
        elif key == "oee":
            out.sort(key=lambda k: ((lines[k].status.get("oee") or {}).get("oee") is None,
                                    (lines[k].status.get("oee") or {}).get("oee") or 0, natural(lines[k].name)))
        else:
            out.sort(key=lambda k: natural(lines[k].name))
        return out

    def _layout(self, order: list[str]) -> None:
        cols = max(1, (self.scroll.viewport().width() - 10) // (CARD_W + 10))
        if order == self._order and cols == self._cols:
            return
        self._order, self._cols = list(order), cols
        while self.grid.count():
            self.grid.takeAt(0)
        for c in self.cards.values():
            c.setVisible(False)
        for i, lid in enumerate(order):
            card = self.cards[lid]
            self.grid.addWidget(card, i // cols, i % cols)
            card.setVisible(True)

    def _summary(self, now: float) -> None:
        lines = list(self.reader.lines.values())
        conn = [ln.connection(now) for ln in lines]
        online = [ln for ln, c in zip(lines, conn) if c in ("online", "stale")]
        states = [(ln.status.get("machine") or {}).get("state") for ln in online]
        self.tiles["lines"].set(str(len(lines)))
        self.tiles["running"].set(str(sum(s in ("running", "slow", "assumed") for s in states)), theme.c("good"))
        self.tiles["stopped"].set(str(sum(s in ("stopped", "microstop") for s in states)), theme.c("critical"))
        self.tiles["alarm"].set(str(sum(bool(ln.status.get("n_alarms")) for ln in online)), theme.c("critical"))
        off = sum(c in ("offline", "closed") for c in conn)
        self.tiles["offline"].set(str(off), theme.c("neutral") if off else None)
        oees = [(ln.status.get("oee") or {}).get("oee") for ln in online]
        oees = [x for x in oees if x is not None]
        self.tiles["oee"].set(pct(sum(oees) / len(oees)) if oees else "—")

    def _fill_plant_events(self) -> None:
        self.lst_plant.clear()
        lines = self.reader.lines
        for e in reversed(self.plant_events[-200:]):
            name = lines[e["line_id"]].name if e["line_id"] in lines else e["line_id"]
            it = QListWidgetItem(f"{time.strftime('%d/%m %H:%M:%S', time.localtime(e.get('ts', 0)))}  "
                                 f"{name}  ·  {e.get('msg', '')}")
            it.setData(Qt.UserRole, e["line_id"])
            it.setForeground(QBrush(QColor(theme.c(LEVEL_KEYS.get(e.get("level"), "neutral")))))
            self.lst_plant.addItem(it)

    def select(self, line_id: str) -> None:
        if self.selected in self.cards:
            self.cards[self.selected].set_selected(False)
        self.selected = line_id
        if line_id in self.cards:
            self.cards[line_id].set_selected(True)
        self.detail.show_line(line_id)
        self.refresh(rescan=False)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self._order:
            self._layout(list(self._order))


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
    settings = home_dir / "fleet.json"
    if folder is None:
        try:
            folder = json.loads(settings.read_text(encoding="utf-8")).get("dir")
        except (OSError, ValueError):
            folder = None
    app = QApplication.instance() or QApplication(sys.argv[:1])
    app.setApplicationName("Dashboard global de líneas")
    try:
        state = json.loads((home_dir / "state.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        state = {}
    apply_ui_prefs(state.get("ui", {}))
    Translator().install(app)
    win = FleetWindow(folder, settings)
    if folder:
        try:
            settings.write_text(json.dumps({"dir": folder}, ensure_ascii=False), encoding="utf-8")
        except OSError:
            pass
    win.show()
    return app.exec()
