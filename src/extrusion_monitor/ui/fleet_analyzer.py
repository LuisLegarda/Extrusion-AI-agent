"""Dashboard global → Analizador de planta: conclusiones, OEE y pérdidas, tiempos muertos, fallas e Industria 5.0."""
from __future__ import annotations

import time
from pathlib import Path

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QComboBox, QFrame, QGridLayout, QHBoxLayout, QHeaderView, QLabel, QPushButton, QScrollArea,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from ..analysis.plant import PlantSummary, summarize
from ..fleet_data import FleetHistorian
from ..plant_settings import PlantSettings
from ..i18n import tr
from . import theme

PERIODS = [("Últimas 24 h", 86400), ("Últimos 7 días", 7 * 86400), ("Últimos 30 días", 30 * 86400)]
SEV = {3: ("critical", "⛔"), 2: ("warning_text", "⚠"), 1: ("info", "ℹ"), 0: ("good_text", "✔")}


def fit_height(t: QTableWidget) -> None:
    """Alto justo para las filas (sin espacio vacío debajo)."""
    t.resizeRowsToContents()
    h = t.horizontalHeader().height() + sum(t.rowHeight(i) for i in range(t.rowCount())) + 2 * t.frameWidth() + 2
    if t.horizontalHeader().length() > t.viewport().width() or t.columnCount() > 9:
        h += t.horizontalScrollBar().sizeHint().height()  # si hay muchas columnas, la barra no tapa la última fila
    t.setFixedHeight(h)
    t.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)


def _f(v, d=0, suffix=""):
    return "—" if v is None else f"{v:,.{d}f}{suffix}"


class FleetAnalyzer(QWidget):
    def __init__(self, reader_fn, home: Path, on_notify=None, on_send_now=None):
        super().__init__()
        self.reader_fn = reader_fn
        self.home = Path(home)
        self.on_notify, self.on_send_now = on_notify, on_send_now
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
        for text, slot, tip in ((tr("🎯 Metas y costos…"), self.edit_plant, tr("Metas por línea, costos y reporte semanal")),
                                (tr("📄 Reporte PDF"), self.export_pdf, tr("Guardar este análisis como PDF"))):
            bt = QPushButton(text)
            bt.setToolTip(tip)
            bt.clicked.connect(slot)
            bar.addWidget(bt)
        b = QPushButton(tr("⟳ Actualizar"))
        b.clicked.connect(self.refresh)
        bar.addWidget(b)
        bar.addStretch(1)
        lay.addLayout(bar)
        self.area = QScrollArea()
        self.area.setWidgetResizable(True)
        self.area.setFrameShape(QFrame.NoFrame)
        lay.addWidget(self.area, 1)

    @property
    def plant(self) -> PlantSettings:
        return PlantSettings.load(self.home)

    def edit_plant(self) -> None:
        from .fleet_plant_dialog import PlantDialog
        lines = [ln.name for ln in sorted(self.reader_fn().lines.values(), key=lambda ln: ln.name)]
        if PlantDialog(self.home, lines, self.on_notify, self.on_send_now, self).exec():
            self.refresh()

    def export_pdf(self, path=None):
        from PySide6.QtWidgets import QFileDialog
        if path is None:
            path, _ = QFileDialog.getSaveFileName(self, tr("Guardar reporte PDF"), str(self.home / "reportes" /
                                                  time.strftime("Planta_%Y%m%d.pdf")), "PDF (*.pdf)")
        if not path:
            return None
        return self.write_pdf(Path(path))

    def write_pdf(self, path: Path, title: str = "") -> Path:
        from .stats_report import grab_widget, write_images_pdf
        self.refresh()
        body = self.area.widget()
        img = grab_widget(body, 1150)
        s = self.summary
        rng = time.strftime("%d/%m/%Y", time.localtime(s.since)) + " → " + time.strftime("%d/%m/%Y",
                                                                                          time.localtime(s.until))
        out = write_images_pdf([("", rng, img)], Path(path), title or tr("Reporte de planta"), tr("Dashboard global"))
        self.refresh()  # vuelve a mostrarse en la página
        return out

    # --- cálculo y dibujo -----------------------------------------------------------------------
    def refresh(self) -> None:
        now = time.time()
        span = float(self.cmb_period.currentData() or 7 * 86400)
        plant = self.plant
        self.summary = s = summarize(FleetHistorian(self.reader_fn()), now - span, now, plant=plant)
        self.cur = plant.currency
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
        g.addWidget(self._production(s, plant), 2, 0, 1, 2)
        g.addWidget(self._goals(plant), 3, 0, 1, 2)
        g.addWidget(self._oee_chart(s), 4, 0)
        g.addWidget(self._downtime_chart(s), 4, 1)
        g.addWidget(self._pareto(s), 5, 0)
        g.addWidget(self._trend(s, "oee", tr("OEE diario por línea")), 5, 1)
        g.addWidget(self._shifts_ops(s), 6, 0, 1, 2)
        g.addWidget(self._i50(s), 7, 0, 1, 2)
        g.addWidget(self._trend(s, "stability", tr("Estabilidad diaria por línea (%)")), 8, 0)
        g.addWidget(self._trend(s, "i5", tr("Índice 5.0 diario por línea")), 8, 1)
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
        cost = any(m.quality_cost for m in s.lines)
        if cost:
            heads += [tr("Costo del paro"), tr("Costo del desperdicio"), tr("Costo total")]
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
                vals += [f"{self.cur} {m.cost:,.0f}", f"{self.cur} {m.scrap_cost:,.0f}", f"{self.cur} {m.quality_cost:,.0f}"]
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
        fr, w = self._plot(tr("Tiempo muerto por línea (min)") + (f" · {self.cur} {s.cost:,.0f}" if s.cost else ""))
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


    # --- producción, metas del mes, turnos y operadores -----------------------------------------------------
    def _simple_table(self, heads: list[str], rows: list[list], colors: dict = None) -> QTableWidget:
        t = QTableWidget(len(rows), len(heads))
        t.setHorizontalHeaderLabels(heads)
        t.verticalHeader().setVisible(False)
        t.setEditTriggers(QTableWidget.NoEditTriggers)
        for r, vals in enumerate(rows):
            for c, v in enumerate(vals):
                it = QTableWidgetItem(str(v))
                if c:
                    it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                if colors and (r, c) in colors:
                    it.setForeground(QColor(colors[(r, c)]))
                t.setItem(r, c, it)
        hh = t.horizontalHeader()
        hh.setSectionResizeMode(QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(0, QHeaderView.Stretch)
        fit_height(t)
        return t

    def _production(self, s: PlantSummary, plant: PlantSettings) -> QFrame:
        fr, lay = self._card(tr("Producción contra meta"))
        rows, colors = [], {}
        for r, m in enumerate(s.lines):
            tg = plant.target(m.name).production_shift
            comp = m.compliance
            rows.append([m.name, f"{m.produced:,.0f} {s.unit}".strip(), f"{m.good:,.0f}", str(m.n_shifts),
                         f"{tg:,.0f}" if tg else "—", f"{m.expected:,.0f}" if m.expected else "—",
                         "—" if comp is None else f"{comp:.0f} %"])
            if comp is not None:
                colors[(r, 6)] = theme.c("good_text") if comp >= 100 else (
                    theme.c("warning_text") if comp >= 90 else theme.c("critical"))
        lay.addWidget(self._simple_table([tr("Línea"), tr("Producido"), tr("Conforme"), tr("Turnos"),
                                          tr("Meta por turno"), tr("Meta del periodo"), tr("Cumplimiento")], rows,
                                         colors))
        w = pg.PlotWidget()
        w.setMinimumHeight(220)
        w.setBackground(theme.c("plot_bg"))
        w.showGrid(x=False, y=True, alpha=0.2)
        w.setMouseEnabled(x=False, y=False)
        w.hideButtons()
        w.addLegend(offset=(-10, 10))
        days = sorted({d for m in s.lines for d, _ in m.prod_daily})
        idx = {d: i for i, d in enumerate(days)}
        n = max(1, len(s.lines))
        width = 0.8 / n
        for k, m in enumerate(s.lines):
            if not m.prod_daily:
                continue
            xs = np.array([idx[d] for d, _ in m.prod_daily]) + (k - (n - 1) / 2) * width
            item = pg.BarGraphItem(x=xs, height=[v for _, v in m.prod_daily], width=width * 0.9,
                                   brush=pg.mkBrush(theme.series(k)))
            w.addItem(item)
            w.getPlotItem().legend.addItem(item, m.name)
            tg = plant.target(m.name).production_shift
            if tg:
                per_day = tg * 3  # meta diaria con 3 turnos
                w.plot([-0.5, len(days) - 0.5], [per_day, per_day], pen=pg.mkPen(theme.series(k), width=1.5,
                                                                                  style=Qt.DashLine))
        w.getAxis("bottom").setTicks([[(i, d[5:]) for i, d in enumerate(days)]])
        lay.addWidget(QLabel(tr("Producción diaria por línea (líneas punteadas: meta diaria)")))
        lay.addWidget(w)
        if not any(m.produced for m in s.lines):
            note = QLabel(tr("Sin datos de producción: los monitores deben tener el OEE configurado y esta versión "
                             "(publica la producción del turno cada minuto)."))
            note.setWordWrap(True)
            note.setStyleSheet(f"color:{theme.c('muted')};")
            lay.addWidget(note)
        return fr

    def _goals(self, plant: PlantSettings) -> QFrame:
        """Semáforo del mes en curso contra el mes anterior y las metas."""
        import datetime as dt
        fr, lay = self._card(tr("Metas del mes (semáforo)"))
        now = dt.datetime.now()
        m0 = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        prev0 = (m0 - dt.timedelta(days=1)).replace(day=1)
        hist = FleetHistorian(self.reader_fn())
        cur = summarize(hist, m0.timestamp(), time.time(), plant=plant)
        prev = summarize(hist, prev0.timestamp(), m0.timestamp(), plant=plant)
        prev_by = {m.name: m for m in prev.lines}
        days_cur = max(1.0, (time.time() - m0.timestamp()) / 86400)
        days_prev = max(1.0, (m0.timestamp() - prev0.timestamp()) / 86400)
        rows, colors = [], {}
        for m in cur.lines:
            tg = plant.target(m.name)
            p = prev_by.get(m.name)
            checks = [("OEE", tg.oee, m.kpis.get("oee"), p.kpis.get("oee") if p else None, True, "%"),
                      (tr("Disponibilidad"), tg.availability, m.kpis.get("availability"),
                       p.kpis.get("availability") if p else None, True, "%"),
                      ("MTTR", tg.mttr_min, m.mttr_min, p.mttr_min if p else None, False, "min"),
                      (tr("Desperdicio por día"), tg.scrap_day, m.scrap / days_cur,
                       (p.scrap / days_prev) if p else None, False, cur.unit),
                      (tr("Cumplimiento de producción"), 100.0 if tg.production_shift else 0.0, m.compliance,
                       p.compliance if p else None, True, "%")]
            for name, target, val, before, higher, unit in checks:
                if not target:
                    continue
                r = len(rows)
                ok = val is not None and (val >= target if higher else val <= target)
                near = val is not None and (val >= 0.95 * target if higher else val <= 1.1 * target)
                state = "🟢" if ok else ("🟡" if near else "🔴")
                trend = "—" if val is None or before is None else ("▲" if val > before else ("▼" if val < before else "="))
                rows.append([f"{m.name} · {name}", f"{target:,.1f} {unit}".strip(), _f(val, 1, f" {unit}".rstrip()),
                             _f(before, 1, f" {unit}".rstrip()), trend, state])
                if trend in ("▲", "▼"):
                    colors[(r, 4)] = theme.c("good_text") if (val > before) == higher else theme.c("critical")
        if not rows:
            lay.addWidget(QLabel(tr("Define metas por línea en «🎯 Metas y costos» para ver el semáforo del mes.")))
            return fr
        lay.addWidget(self._simple_table([tr("Línea · indicador"), tr("Meta"), tr("Este mes"), tr("Mes anterior"),
                                          tr("Tendencia"), tr("Estado")], rows, colors))
        return fr

    def _shifts_ops(self, s: PlantSummary) -> QFrame:
        fr, lay = self._card(tr("Turnos y operadores: comparación entre líneas"))
        shifts = sorted({k for m in s.lines for k in m.by_shift})
        rows = []
        for sh in shifts:
            row = [sh]
            for m in s.lines:
                b = m.by_shift.get(sh)
                row.append("—" if not b or b.get("oee") is None else f"{b['oee']:.0f} % · {b['stop_min']:.0f} min")
            rows.append(row)
        if rows:
            lay.addWidget(QLabel(tr("OEE y minutos de paro por turno")))
            lay.addWidget(self._simple_table([tr("Turno")] + [m.name for m in s.lines], rows))
        # ranking de operadores (todas las líneas)
        ops: dict[str, dict] = {}
        for m in s.lines:
            for u, b in m.by_user.items():
                o = ops.setdefault(u, {"oee_sum": 0.0, "oee_n": 0, "minutes": 0, "stop_min": 0.0, "scrap": 0.0,
                                       "lines": set()})
                o["oee_sum"] += b["oee_sum"]
                o["oee_n"] += b["oee_n"]
                o["minutes"] += b["minutes"]
                o["stop_min"] += b["stop_min"]
                o["scrap"] += b["scrap"]
                if b["minutes"]:
                    o["lines"].add(m.name)
        ranked = sorted(((u, o) for u, o in ops.items() if o["oee_n"] >= 30),
                        key=lambda kv: -(kv[1]["oee_sum"] / kv[1]["oee_n"]))
        if ranked:
            rows = [[f"{i + 1}. {u}", f"{o['oee_sum'] / o['oee_n']:.0f} %", f"{o['minutes'] / 60:.1f} h",
                     f"{o['stop_min']:.0f}", f"{o['scrap']:.0f}", ", ".join(sorted(o["lines"]))]
                    for i, (u, o) in enumerate(ranked)]
            lay.addWidget(QLabel(tr("Ranking de operadores (OEE promedio en las horas que estuvieron en turno)")))
            lay.addWidget(self._simple_table([tr("Operador"), "OEE", tr("Tiempo en turno"), tr("Min paro"),
                                              tr("Desperdicio"), tr("Líneas")], rows))
        else:
            note = QLabel(tr("El ranking de operadores aparece cuando los monitores registran el usuario en turno "
                             "(barra superior del monitor)."))
            note.setStyleSheet(f"color:{theme.c('muted')};")
            note.setWordWrap(True)
            lay.addWidget(note)
        return fr
