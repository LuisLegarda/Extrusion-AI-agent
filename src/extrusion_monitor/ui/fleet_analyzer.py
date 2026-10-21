"""Dashboard global → Analizador de planta: conclusiones, OEE y pérdidas, tiempos muertos, fallas e Industria 5.0."""
from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QComboBox, QDoubleSpinBox, QFrame, QGridLayout, QHBoxLayout, QHeaderView, QLabel, QPushButton, QScrollArea,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from ..analysis.plant import PlantSummary, summarize
from ..fleet_data import FleetHistorian
from ..i18n import tr
from . import theme

PERIODS = [("Últimas 24 h", 86400), ("Últimos 7 días", 7 * 86400), ("Últimos 30 días", 30 * 86400)]
SEV = {3: ("critical", "⛔"), 2: ("warning_text", "⚠"), 1: ("info", "ℹ"), 0: ("good_text", "✔")}


def fit_height(t: QTableWidget) -> None:
    """Alto justo para las filas (sin espacio vacío debajo)."""
    t.resizeRowsToContents()
    h = t.horizontalHeader().height() + sum(t.rowHeight(i) for i in range(t.rowCount())) + 2 * t.frameWidth() + 2
    t.setFixedHeight(h)
    t.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)


def _f(v, d=0, suffix=""):
    return "—" if v is None else f"{v:,.{d}f}{suffix}"


class FleetAnalyzer(QWidget):
    def __init__(self, reader_fn, home: Path):
        super().__init__()
        self.reader_fn = reader_fn
        self.state_file = Path(home) / "analizador.json"
        self.summary: PlantSummary | None = None
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        bar = QHBoxLayout()
        bar.addWidget(QLabel(f"<b style='font-size:16px; color:{theme.c('title')}'>{tr('Analizador de planta')}</b>"))
        bar.addSpacing(16)
        bar.addWidget(QLabel(tr("Periodo:")))
        self.cmb_period = QComboBox()
        for label, secs in PERIODS:
            self.cmb_period.addItem(tr(label), secs)
        self.cmb_period.setCurrentIndex(1)
        self.cmb_period.currentIndexChanged.connect(lambda _: self.refresh())
        bar.addWidget(self.cmb_period)
        bar.addWidget(QLabel(tr("Costo de una hora de paro:")))
        self.sp_cost = QDoubleSpinBox()
        self.sp_cost.setRange(0, 1e7)
        self.sp_cost.setPrefix("$ ")
        self.sp_cost.setDecimals(0)
        self.sp_cost.setValue(self._load().get("cost_per_h", 0.0))
        self.sp_cost.setToolTip(tr("Para estimar cuánto cuesta el tiempo muerto (0 = no mostrar)"))
        self.sp_cost.editingFinished.connect(self._cost_changed)
        bar.addWidget(self.sp_cost)
        b = QPushButton(tr("⟳ Actualizar"))
        b.clicked.connect(self.refresh)
        bar.addWidget(b)
        bar.addStretch(1)
        lay.addLayout(bar)
        self.area = QScrollArea()
        self.area.setWidgetResizable(True)
        self.area.setFrameShape(QFrame.NoFrame)
        lay.addWidget(self.area, 1)

    def _load(self) -> dict:
        try:
            return json.loads(self.state_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def _cost_changed(self) -> None:
        try:
            self.state_file.write_text(json.dumps({"cost_per_h": self.sp_cost.value()}), encoding="utf-8")
        except OSError:
            pass
        self.refresh()

    # --- cálculo y dibujo -----------------------------------------------------------------------
    def refresh(self) -> None:
        now = time.time()
        span = float(self.cmb_period.currentData() or 7 * 86400)
        self.summary = s = summarize(FleetHistorian(self.reader_fn()), now - span, now, self.sp_cost.value())
        body = QWidget()
        g = QGridLayout(body)
        g.setSpacing(10)
        if not s.lines:
            msg = QLabel(tr("No hay líneas en la carpeta de datos todavía."))
            msg.setAlignment(Qt.AlignCenter)
            g.addWidget(msg, 0, 0)
            self.area.setWidget(body)
            return
        g.addWidget(self._insights(s), 0, 0, 1, 2)
        g.addWidget(self._table(s), 1, 0, 1, 2)
        g.addWidget(self._oee_chart(s), 2, 0)
        g.addWidget(self._downtime_chart(s), 2, 1)
        g.addWidget(self._pareto(s), 3, 0)
        g.addWidget(self._trend(s, "oee", tr("OEE diario por línea")), 3, 1)
        g.addWidget(self._i50(s), 4, 0, 1, 2)
        g.addWidget(self._trend(s, "stability", tr("Estabilidad diaria por línea (%)")), 5, 0)
        g.addWidget(self._trend(s, "i5", tr("Índice 5.0 diario por línea")), 5, 1)
        self.area.setWidget(body)

    def _card(self, title: str) -> tuple[QFrame, QVBoxLayout]:
        fr = QFrame()
        fr.setObjectName("card")
        lay = QVBoxLayout(fr)
        lay.addWidget(QLabel(f"<b style='font-size:14px; color:{theme.c('title')}'>{title}</b>"))
        return fr, lay

    def _insights(self, s: PlantSummary) -> QFrame:
        fr, lay = self._card(tr("Conclusiones del periodo"))
        if not s.insights:
            lay.addWidget(QLabel(tr("Sin hallazgos importantes: las líneas operan dentro de lo normal.")))
        for ins in s.insights[:12]:
            key, icon = SEV[ins.severity]
            lb = QLabel(f"<span style='color:{theme.c(key)}'>{icon}</span> {tr(ins.text)}")
            lb.setWordWrap(True)
            lay.addWidget(lb)
        return fr

    def _table(self, s: PlantSummary) -> QFrame:
        fr, lay = self._card(tr("Indicadores por línea"))
        heads = [tr("Línea"), "OEE", tr("Disp."), tr("Rend."), tr("Cal."), tr("Δ OEE"), tr("Estabilidad"),
                 tr("Índice 5.0"), "Cpk", tr("Paros"), tr("Min paro"), "MTTR", "MTBF", tr("Desperdicio"),
                 tr("Alarmas/h")]
        cost = self.sp_cost.value() > 0
        if cost:
            heads.append(tr("Costo del paro"))
        t = QTableWidget(len(s.lines), len(heads))
        t.setHorizontalHeaderLabels(heads)
        t.verticalHeader().setVisible(False)
        t.setEditTriggers(QTableWidget.NoEditTriggers)
        for r, m in enumerate(s.lines):
            k = m.kpis
            d_oee = (k["oee"] - m.prev_oee) if k.get("oee") is not None and m.prev_oee is not None else None
            vals = [m.name, _f(k.get("oee"), 0, " %"), _f(k.get("availability"), 0, " %"),
                    _f(k.get("performance"), 0, " %"), _f(k.get("quality"), 0, " %"),
                    "—" if d_oee is None else f"{d_oee:+.0f}", _f(k.get("stability"), 0, " %"), _f(k.get("i5"), 0),
                    _f(k.get("cpk"), 2), str(m.n_stops), _f(m.stop_min, 0), _f(m.mttr_min, 0, " min"),
                    _f(m.mtbf_h, 1, " h"), _f(m.scrap, 0, f" {s.unit}".rstrip()), _f(m.alarms_h, 1)]
            if cost:
                vals.append(f"$ {m.cost:,.0f}")
            for c, v in enumerate(vals):
                it = QTableWidgetItem(v)
                if c:
                    it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                if c == 1 and k.get("oee") is not None:
                    it.setForeground(QColor(theme.c("critical") if k["oee"] < 60 else
                                            theme.c("warning_text") if k["oee"] < 75 else theme.c("good_text")))
                if c == 5 and d_oee is not None:
                    it.setForeground(QColor(theme.c("good_text") if d_oee >= 0 else theme.c("critical")))
                t.setItem(r, c, it)
        hh = t.horizontalHeader()
        hh.setSectionResizeMode(QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(0, QHeaderView.Stretch)
        fit_height(t)
        lay.addWidget(t)
        note = QLabel(tr("Δ OEE: contra el periodo anterior de la misma duración. MTTR: duración promedio de un paro. "
                         "MTBF: tiempo de operación entre paros. Paros planeados no cuentan."))
        note.setWordWrap(True)
        note.setStyleSheet(f"color:{theme.c('muted')}; font-size:11px;")
        lay.addWidget(note)
        return fr

    def _plot(self, title: str, h: int = 280) -> tuple[QFrame, pg.PlotWidget]:
        fr, lay = self._card(title)
        w = pg.PlotWidget()
        w.setMinimumHeight(h)
        w.showGrid(x=False, y=True, alpha=0.2)
        w.setBackground(theme.c("plot_bg"))
        w.setMouseEnabled(x=False, y=False)
        w.hideButtons()
        lay.addWidget(w)
        return fr, w

    def _oee_chart(self, s: PlantSummary) -> QFrame:
        fr, w = self._plot(tr("OEE y sus pérdidas por línea (%)"))
        names = [m.name for m in s.lines]
        keys = [("oee", "OEE", theme.c("accent")), ("availability", tr("Disponibilidad"), theme.series(1)),
                ("performance", tr("Rendimiento"), theme.series(2)), ("quality", tr("Calidad"), theme.series(3))]
        w.addLegend(offset=(-10, 10))
        width = 0.2
        for j, (k, label, color) in enumerate(keys):
            xs = np.arange(len(names)) + (j - 1.5) * width
            hs = [m.kpis.get(k) or 0 for m in s.lines]
            item = pg.BarGraphItem(x=xs, height=hs, width=width * 0.95, brush=pg.mkBrush(color))
            w.addItem(item)
            w.getPlotItem().legend.addItem(item, label)
        w.getAxis("bottom").setTicks([[(i, n) for i, n in enumerate(names)]])
        w.setYRange(0, 125)  # espacio arriba para la leyenda
        return fr

    def _downtime_chart(self, s: PlantSummary) -> QFrame:
        fr, w = self._plot(tr("Tiempo muerto por línea (min)") + (f" · $ {s.cost:,.0f}" if s.cost else ""))
        names = [m.name for m in s.lines]
        for i, m in enumerate(s.lines):
            w.addItem(pg.BarGraphItem(x=[i], height=[m.stop_min], width=0.6, brush=pg.mkBrush(theme.c("critical"))))
            if m.planned_min:
                w.addItem(pg.BarGraphItem(x=[i], y0=[m.stop_min], height=[m.planned_min], width=0.6,
                                          brush=pg.mkBrush(theme.c("neutral"))))
            t = pg.TextItem(f"{m.n_stops} {tr('paros')}", color=theme.c("text"), anchor=(0.5, 1))
            t.setPos(i, m.stop_min + m.planned_min)
            w.addItem(t)
        w.getAxis("bottom").setTicks([[(i, n) for i, n in enumerate(names)]])
        return fr

    def _pareto(self, s: PlantSummary) -> QFrame:
        fr, w = self._plot(tr("Principales causas de paro de la planta (min)"))
        items = sorted(s.causes.items(), key=lambda kv: -kv[1])[:10]
        if not items:
            w.addItem(pg.TextItem(tr("Sin paros capturados"), color=theme.c("muted")))
            return fr
        ys = np.arange(len(items))[::-1]
        w.addItem(pg.BarGraphItem(x0=0, y=ys, height=0.6, width=[v for _, v in items],
                                  brush=pg.mkBrush(theme.series(0))))
        w.getAxis("left").setTicks([[(y, n) for y, (n, _) in zip(ys, items)]])
        w.getAxis("left").setWidth(150)
        return fr

    def _trend(self, s: PlantSummary, key: str, title: str) -> QFrame:
        fr, w = self._plot(title, 240)
        w.addLegend(offset=(-10, 10))
        days = sorted({d for m in s.lines for d, _ in m.daily.get(key, [])})
        idx = {d: i for i, d in enumerate(days)}
        for i, m in enumerate(s.lines):
            pts = m.daily.get(key, [])
            if pts:
                w.plot([idx[d] for d, _ in pts], [v for _, v in pts], pen=pg.mkPen(theme.series(i), width=2),
                       symbol="o", symbolSize=5, symbolBrush=theme.series(i), name=m.name)
        w.getAxis("bottom").setTicks([[(i, d[5:]) for i, d in enumerate(days)]])
        return fr

    def _i50(self, s: PlantSummary) -> QFrame:
        fr, lay = self._card(tr("Industria 5.0: personas, resiliencia y sostenibilidad"))
        rows = []
        for m in s.lines:
            k = m.kpis
            rows.append((m.name, k.get("i5"), m.alarms_h, k.get("stability"), m.slope.get("stability"), m.scrap))
        t = QTableWidget(len(rows), 6)
        t.setHorizontalHeaderLabels([tr("Línea"), tr("Índice 5.0"), tr("Alarmas/h\n(carga del operador)"),
                                     tr("Estabilidad\n(resiliencia)"), tr("Tendencia de\nestabilidad"),
                                     tr("Desperdicio\n(sostenibilidad)")])
        t.verticalHeader().setVisible(False)
        t.setEditTriggers(QTableWidget.NoEditTriggers)
        for r, (n, i5, ah, stab, slope, scrap) in enumerate(rows):
            vals = [n, _f(i5, 0), _f(ah, 1), _f(stab, 0, " %"),
                    "—" if slope is None else f"{slope:+.1f} {tr('pts/día')}", _f(scrap, 0, f" {s.unit}".rstrip())]
            for c, v in enumerate(vals):
                it = QTableWidgetItem(v)
                if c:
                    it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                t.setItem(r, c, it)
        hh = t.horizontalHeader()
        hh.setSectionResizeMode(QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(0, QHeaderView.Stretch)
        fit_height(t)
        lay.addWidget(t)
        note = QLabel(tr("Índice 5.0 (0–100): combina la carga de alarmas para el operador, la estabilidad del proceso "
                         "y su recuperación tras los paros. Más alto es mejor."))
        note.setWordWrap(True)
        note.setStyleSheet(f"color:{theme.c('muted')}; font-size:11px;")
        lay.addWidget(note)
        return fr
