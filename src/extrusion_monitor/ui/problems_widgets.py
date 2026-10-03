"""Componentes de Problemas de proceso: línea de tiempo con selección, Pareto y panel de análisis.

Los usan la pantalla de captura del monitor y el análisis del dashboard global.
"""
from __future__ import annotations

import time
from typing import Optional

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFileDialog, QHBoxLayout, QHeaderView, QLabel, QPushButton, QSizePolicy, QSplitter,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from ..analysis.oee import STATE_LABELS
from ..analysis.problems import export_csv, pareto, summary
from ..i18n import tr
from . import theme
from .kpi_dashboard import STATE_COLORS

QUALITY_COLOR = "#8e44ad"


def category_color(name: str, planned: bool = False) -> str:
    if planned:
        return theme.c("info")
    return theme.series(abs(hash(name)) % 8)


def fmt_min(m: float) -> str:
    return f"{m:.0f} min" if m < 120 else f"{m / 60:.1f} h"


# --- línea de tiempo del estado de la máquina con selección inicio-fin -------------------------------
class TimelineSelect(QWidget):
    """Estado de la máquina en el periodo, capturas encima y un rango seleccionado con dos manijas.

    Clic sobre un paro lo selecciona completo; las manijas (o las barras deslizables de la pantalla) ajustan
    el inicio y el fin.
    """

    selectionChanged = Signal(float, float)
    stopClicked = Signal(float, float)

    def __init__(self):
        super().__init__()
        self.a = self.b = 0.0
        self.intervals: list = []
        self.records: list[dict] = []
        self.sel: Optional[tuple[float, float]] = None
        self._drag: Optional[str] = None
        self.setMinimumHeight(118)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setMouseTracking(True)

    def set_data(self, a: float, b: float, intervals: list, records: list[dict]) -> None:
        self.a, self.b, self.intervals, self.records = a, b, intervals, records
        self.update()

    def set_selection(self, sa: Optional[float], sb: Optional[float]) -> None:
        self.sel = None if sa is None else (sa, sb)
        self.update()

    # geometría
    def _x(self, t: float) -> float:
        w = self.width() - 20
        return 10 + w * (t - self.a) / ((self.b - self.a) or 1.0)

    def _t(self, x: float) -> float:
        w = self.width() - 20
        return self.a + (x - 10) / (w or 1) * (self.b - self.a)

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w = self.width()
        rec_y, rec_h = 6, 18  # capturas
        st_y, st_h = 30, 48  # estado de la máquina
        p.fillRect(QRectF(10, st_y, w - 20, st_h), QColor(theme.c("track")))
        for iv in self.intervals:
            x0, x1 = self._x(max(iv.start, self.a)), self._x(min(iv.end, self.b))
            if x1 > x0:
                p.fillRect(QRectF(x0, st_y, max(1.0, x1 - x0), st_h), QColor(STATE_COLORS.get(iv.state, theme.c("neutral"))))
        for r in self.records:
            x0, x1 = self._x(max(r["start"], self.a)), self._x(min(r["end"], self.b))
            if x1 <= x0:
                continue
            color = QColor(QUALITY_COLOR if r["kind"] == "quality" else category_color(r.get("category") or "",
                                                                                         r.get("planned")))
            p.fillRect(QRectF(x0, rec_y, max(2.0, x1 - x0), rec_h), color)
            if x1 - x0 > 50:
                p.setPen(QColor("#ffffff"))
                f = QFont(self.font())
                f.setPixelSize(10)
                p.setFont(f)
                p.drawText(QRectF(x0 + 2, rec_y, x1 - x0 - 4, rec_h), Qt.AlignVCenter | Qt.AlignLeft,
                           p.fontMetrics().elidedText(r.get("reason") or "", Qt.ElideRight, int(x1 - x0 - 4)))
        if self.sel is not None:
            sa, sb = self.sel
            x0, x1 = self._x(sa), self._x(sb)
            sel = QColor(theme.c("accent"))
            sel.setAlpha(60)
            p.fillRect(QRectF(x0, 2, max(2.0, x1 - x0), st_y + st_h), sel)
            for x in (x0, x1):
                p.setPen(QPen(QColor(theme.c("accent")), 3))
                p.drawLine(QPointF(x, 2), QPointF(x, st_y + st_h + 4))
                p.setBrush(QColor(theme.c("accent")))
                p.drawRect(QRectF(x - 5, st_y + st_h + 2, 10, 10))
        # eje de tiempo
        p.setPen(QColor(theme.c("muted")))
        f = QFont(self.font())
        f.setPixelSize(10)
        p.setFont(f)
        span = self.b - self.a
        if span > 0:
            ticks = 6
            for k in range(ticks + 1):
                t = self.a + span * k / ticks
                x = self._x(t)
                fmt = "%H:%M" if span <= 86400 else "%d/%m %H:%M"
                align = Qt.AlignLeft if k == 0 else (Qt.AlignRight if k == ticks else Qt.AlignHCenter)
                box = QRectF(x - (0 if k == 0 else (90 if k == ticks else 45)), st_y + st_h + 16, 90, 14)
                p.drawText(box, align, time.strftime(fmt, time.localtime(t)))
        p.end()

    # mouse: arrastrar manijas o elegir un paro
    def _near_handle(self, x: float) -> Optional[str]:
        if self.sel is None:
            return None
        da, db = abs(x - self._x(self.sel[0])), abs(x - self._x(self.sel[1]))
        if min(da, db) <= 8:
            return "a" if da <= db else "b"
        return None

    def mousePressEvent(self, event) -> None:
        x = event.position().x()
        self._drag = self._near_handle(x)
        if self._drag is None:
            t = self._t(x)
            iv = next((iv for iv in self.intervals if iv.start <= t <= iv.end), None)
            if iv is not None and iv.state in ("stopped", "microstop"):
                self.stopClicked.emit(max(iv.start, self.a), min(iv.end, self.b))
            elif self.sel is None:  # sin paro: empieza un rango nuevo en ese punto
                self.sel = (t, min(self.b, t + 300))
                self.selectionChanged.emit(*self.sel)
        self.update()

    def mouseMoveEvent(self, event) -> None:
        x = event.position().x()
        if self._drag is None:
            self.setCursor(Qt.SizeHorCursor if self._near_handle(x) else Qt.PointingHandCursor)
            return
        t = min(max(self._t(x), self.a), self.b)
        sa, sb = self.sel
        if self._drag == "a":
            sa = min(t, sb - 1)
        else:
            sb = max(t, sa + 1)
        self.sel = (sa, sb)
        self.selectionChanged.emit(sa, sb)
        self.update()

    def mouseReleaseEvent(self, event) -> None:
        self._drag = None


# --- Pareto ------------------------------------------------------------------------------------------
class ParetoChart(QWidget):
    """Barras de mayor a menor con la línea del % acumulado (eje derecho)."""

    def __init__(self):
        super().__init__()
        self.rows: list = []
        self.unit = ""
        self.empty_text = "Sin datos en el periodo"
        self.setMinimumHeight(240)

    def set_rows(self, rows: list, unit: str) -> None:
        self.rows, self.unit = rows[:15], unit
        self.update()

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        f = QFont(self.font())
        f.setPixelSize(10)
        p.setFont(f)
        if not self.rows:
            p.setPen(QColor(theme.c("muted")))
            p.drawText(self.rect(), Qt.AlignCenter, tr(self.empty_text))
            p.end()
            return
        left, right, top, bottom = 48, 40, 14, 74
        pw, ph = w - left - right, h - top - bottom
        vmax = max(r.value for r in self.rows) or 1.0
        p.setPen(QPen(QColor(theme.c("grid"))))
        for k in range(5):
            y = top + ph * k / 4
            p.drawLine(QPointF(left, y), QPointF(left + pw, y))
        p.setPen(QColor(theme.c("muted")))
        for k in range(5):
            y = top + ph * k / 4
            p.drawText(QRectF(0, y - 7, left - 4, 14), Qt.AlignRight | Qt.AlignVCenter, f"{vmax * (1 - k / 4):.4g}")
            p.drawText(QRectF(left + pw + 4, y - 7, right, 14), Qt.AlignLeft | Qt.AlignVCenter, f"{100 - 25 * k}%")
        n = len(self.rows)
        slot = pw / n
        bw = slot * 0.62
        path = QPainterPath()
        pts = []
        for i, r in enumerate(self.rows):
            x = left + slot * i + (slot - bw) / 2
            bh = ph * r.value / vmax
            color = QColor(theme.c("info") if r.planned else theme.c("measure"))
            p.fillRect(QRectF(x, top + ph - bh, bw, bh), color)
            cx = left + slot * (i + 0.5)
            cy = top + ph * (1 - r.cum_pct / 100)
            pts.append(QPointF(cx, cy))
            (path.moveTo if i == 0 else path.lineTo)(QPointF(cx, cy))
            p.save()  # etiqueta inclinada bajo la barra
            p.translate(cx, top + ph + 6)
            p.rotate(35)
            p.setPen(QColor(theme.c("text")))
            p.drawText(QRectF(0, -6, 110, 14), Qt.AlignLeft | Qt.AlignVCenter,
                       p.fontMetrics().elidedText(r.label, Qt.ElideRight, 108))
            p.restore()
        p.setPen(QPen(QColor(theme.c("text")), 2))
        p.setBrush(Qt.NoBrush)
        p.drawPath(path)
        p.setBrush(QColor(theme.c("text")))
        for pt in pts:
            p.drawEllipse(pt, 3, 3)
        p.setPen(QColor(theme.c("muted")))
        p.drawText(QRectF(0, 0, left + 60, 12), Qt.AlignLeft, self.unit)
        p.end()


# --- análisis --------------------------------------------------------------------------------------
TABLE_COLS = ["Línea", "Tipo", "Inicio", "Fin", "Min", "Categoría", "Causa / defecto", "Scrap", "Operador",
              "Comentario"]


class ProblemsAnalysis(QWidget):
    """Resumen, Pareto (por causa, categoría u operador; por tiempo, frecuencia o scrap), tabla y CSV."""

    deleteRequested = Signal(int)

    def __init__(self, show_line: bool = False, can_delete: bool = False):
        super().__init__()
        self.records: list[dict] = []
        self.events: list = []
        self.unit = "m"
        self.show_line = show_line
        self.can_delete = can_delete
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        bar = QHBoxLayout()
        self.cmb_kind = QComboBox()
        self.cmb_kind.addItem("Paros", "downtime")
        self.cmb_kind.addItem("Problemas de calidad", "quality")
        self.cmb_by = QComboBox()
        for k, label in (("reason", "Por causa / defecto"), ("category", "Por categoría"), ("operator", "Por operador")):
            self.cmb_by.addItem(label, k)
        self.cmb_metric = QComboBox()
        for k, label in (("time", "Tiempo"), ("count", "Frecuencia"), ("scrap", "Scrap")):
            self.cmb_metric.addItem(label, k)
        self.chk_planned = QCheckBox("Incluir paros planeados")
        self.chk_planned.setChecked(False)
        for wdg in (self.cmb_kind, self.cmb_by, self.cmb_metric):
            wdg.currentIndexChanged.connect(self.refresh)
            bar.addWidget(wdg)
        self.chk_planned.toggled.connect(self.refresh)
        bar.addWidget(self.chk_planned)
        bar.addStretch(1)
        self.btn_csv = QPushButton("⤓ Exportar CSV…")
        self.btn_csv.clicked.connect(self.export)
        bar.addWidget(self.btn_csv)
        if can_delete:
            self.btn_del = QPushButton("Eliminar captura")
            self.btn_del.setToolTip("Borra la captura seleccionada en la tabla (por ejemplo, si se capturó mal)")
            self.btn_del.clicked.connect(self._delete)
            bar.addWidget(self.btn_del)
        lay.addLayout(bar)
        self.lbl_sum = QLabel()
        self.lbl_sum.setTextFormat(Qt.RichText)
        self.lbl_sum.setWordWrap(True)
        lay.addWidget(self.lbl_sum)
        split = QSplitter(Qt.Vertical)
        self.chart = ParetoChart()
        split.addWidget(self.chart)
        self.tbl = QTableWidget(0, len(TABLE_COLS))
        self.tbl.setHorizontalHeaderLabels(TABLE_COLS)
        self.tbl.verticalHeader().setVisible(False)
        self.tbl.setEditTriggers(QTableWidget.NoEditTriggers)
        self.tbl.setSelectionBehavior(QTableWidget.SelectRows)
        self.tbl.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.tbl.horizontalHeader().setStretchLastSection(True)
        self.tbl.setColumnHidden(0, not show_line)
        split.addWidget(self.tbl)
        split.setSizes([320, 260])
        lay.addWidget(split, 1)

    def set_data(self, records: list[dict], events: Optional[list] = None, unit: str = "m") -> None:
        self.records, self.events, self.unit = records, events or [], unit
        self.refresh()

    def _filtered(self) -> list[dict]:
        kind = self.cmb_kind.currentData()
        planned = self.chk_planned.isChecked()
        return [r for r in self.records if r.get("kind") == kind and (planned or not r.get("planned"))]

    def refresh(self, *_):
        kind = self.cmb_kind.currentData()
        metric = self.cmb_metric.currentData()
        self.chk_planned.setVisible(kind == "downtime")
        s = summary(self.records, self.events)
        pend = (f" · <b style='color:{theme.c('warning_text')}'>{tr('{n} paros sin clasificar', n=s.pending_n)}"
                f"</b> ({fmt_min(s.pending_min)})") if s.pending_n else ""
        self.lbl_sum.setText(
            tr("Paros capturados: <b>{n}</b> · <b>{t}</b> (no planeados {u}, planeados {p})",
               n=s.n_downtime, t=fmt_min(s.stop_min), u=fmt_min(s.unplanned_min), p=fmt_min(s.planned_min))
            + pend + "<br>" + tr("Problemas de calidad: <b>{n}</b> · scrap total <b>{s}</b> {u}",
                                 n=s.n_quality, s=f"{s.scrap:,.0f}", u=self.unit))
        rows = pareto(self.records, kind, self.cmb_by.currentData(), metric,
                      include_planned=self.chk_planned.isChecked() or kind != "downtime")
        unit = {"time": tr("minutos"), "count": tr("eventos"), "scrap": self.unit}[metric]
        self.chart.set_rows(rows, unit)
        recs = sorted(self._filtered(), key=lambda r: -(r.get("start") or 0))
        self.tbl.setRowCount(len(recs))
        for i, r in enumerate(recs):
            vals = [r.get("line_name") or r.get("line") or "", tr("Paro") if r["kind"] == "downtime" else tr("Calidad"),
                    time.strftime("%d/%m %H:%M", time.localtime(r["start"])),
                    time.strftime("%H:%M", time.localtime(r["end"])), f"{(r.get('duration_s') or 0) / 60:.1f}",
                    (r.get("category") or "") + (" ★" if r.get("planned") else ""), r.get("reason") or "",
                    f"{r.get('scrap') or 0:g}", r.get("operator") or "", r.get("comment") or ""]
            for c, text in enumerate(vals):
                it = QTableWidgetItem(text)
                if c == 0:
                    it.setData(Qt.UserRole, r.get("id"))
                if c == 5:
                    it.setForeground(QBrush(QColor(QUALITY_COLOR if r["kind"] == "quality"
                                                   else category_color(r.get("category") or "", r.get("planned")))))
                self.tbl.setItem(i, c, it)

    def _delete(self) -> None:
        row = self.tbl.currentRow()
        it = self.tbl.item(row, 0) if row >= 0 else None
        if it is not None and it.data(Qt.UserRole) is not None:
            self.deleteRequested.emit(int(it.data(Qt.UserRole)))

    def export(self, path: Optional[str] = None) -> Optional[str]:
        if not path:
            path, _ = QFileDialog.getSaveFileName(self, tr("Exportar problemas de proceso"),
                                                  f"problemas_{time.strftime('%Y%m%d_%H%M')}.csv", "CSV (*.csv)")
        if not path:
            return None
        from ..analysis.problems import CSV_COLUMNS
        export_csv(path, self.records, headers=[tr(c) for c in CSV_COLUMNS])
        return path
