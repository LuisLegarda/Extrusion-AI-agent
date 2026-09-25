"""Árbol de estado en vivo: pestañas del HMI → variables, con consigna y medición en la misma fila."""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont
from PySide6.QtWidgets import QHeaderView, QTreeWidget, QTreeWidgetItem

from ..analysis.rules import Level, VarStatus, fmt
from ..config import AppConfig, Variable
from ..engine import Snapshot
from .common import LEVEL_TEXT, level_color

COLS = ["Variable", "Consigna", "Medición", "Unidad", "Referencia", "Desv.", "Tol. aviso / alarma",
        "Estado", "Tendencia /min", "Cpk", "Lectura"]
C_NAME, C_SP, C_PV, C_UNIT, C_REF, C_DEV, C_TOL, C_STATE, C_TREND, C_CPK, C_READ = range(len(COLS))
ROLE = Qt.UserRole
SP_COLOR = QColor("#1e88e5")


class VariableTree(QTreeWidget):
    plotToggled = Signal(str, bool)  # var_id, activado

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setColumnCount(len(COLS))
        self.setHeaderLabels(COLS)
        self.setAlternatingRowColors(True)
        self.setUniformRowHeights(True)
        self.header().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.header().setStretchLastSection(True)
        self.itemChanged.connect(self._changed)
        self._rows: dict[str, QTreeWidgetItem] = {}  # id de la fila (medición o consigna suelta)
        self._pages: dict[Optional[str], QTreeWidgetItem] = {}
        self._pair_sp: dict[str, str] = {}  # medición -> consigna
        self.config: Optional[AppConfig] = None

    # --- construcción ----------------------------------------------------------
    def rebuild(self, config: AppConfig, plotted: list[str]) -> None:
        self.config = config
        self.blockSignals(True)
        self.clear()
        self._rows.clear()
        self._pages.clear()
        self._pair_sp.clear()
        bold = QFont()
        bold.setBold(True)

        def page_item(pid: Optional[str]) -> QTreeWidgetItem:
            if pid in self._pages:
                return self._pages[pid]
            page = config.page(pid) if pid else None
            if pid and page is None:
                return page_item(None)
            it = QTreeWidgetItem([page.name if page else "General"])
            it.setFont(C_NAME, bold)
            it.setFirstColumnSpanned(False)
            it.setData(C_NAME, ROLE, ("page", pid))
            if page and page.parent:
                page_item(page.parent).addChild(it)
            else:
                self.addTopLevelItem(it)
            self._pages[pid] = it
            return it

        linked = {v.setpoint_var: v.id for v in config.variables if v.kind == "actual" and v.setpoint_var}
        for v in config.variables:
            if v.kind == "setpoint" and v.id in linked:
                continue
            parent = page_item(v.page)
            it = QTreeWidgetItem([v.name])
            it.setData(C_NAME, ROLE, ("var", v.id))
            if v.kind != "text":
                it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
                it.setCheckState(C_NAME, Qt.Checked if v.id in plotted else Qt.Unchecked)
                it.setToolTip(C_NAME, "Marca la casilla para graficar la tendencia")
            it.setText(C_UNIT, v.unit)
            for c in (C_SP, C_PV, C_REF, C_DEV, C_TOL, C_TREND, C_CPK):
                it.setTextAlignment(c, Qt.AlignRight | Qt.AlignVCenter)
            it.setForeground(C_SP, QBrush(SP_COLOR))
            bold_value = QFont()
            bold_value.setBold(True)
            it.setFont(C_PV, bold_value)
            parent.addChild(it)
            self._rows[v.id] = it
            if v.kind == "actual" and v.setpoint_var:
                self._pair_sp[v.id] = v.setpoint_var
        self.expandAll()
        self.blockSignals(False)

    def set_checked(self, var_id: str, on: bool) -> None:
        it = self._rows.get(var_id)
        if it is not None:
            self.blockSignals(True)
            it.setCheckState(C_NAME, Qt.Checked if on else Qt.Unchecked)
            self.blockSignals(False)

    def _changed(self, item: QTreeWidgetItem, column: int) -> None:
        key = item.data(C_NAME, ROLE)
        if column == C_NAME and key and key[0] == "var":
            self.plotToggled.emit(key[1], item.checkState(C_NAME) == Qt.Checked)

    # --- actualización -----------------------------------------------------------
    def update_snapshot(self, snap: Snapshot) -> None:
        page_levels: dict[Optional[str], Optional[Level]] = {}
        for vid, it in self._rows.items():
            st = snap.statuses.get(vid)
            if st is None:
                continue
            sp = snap.statuses.get(self._pair_sp.get(vid, ""))
            level = self._fill(it, st, sp)
            pid = st.var.page
            while True:
                cur = page_levels.get(pid)
                if level is not None and (cur is None or level > cur):
                    page_levels[pid] = level
                page = self.config.page(pid) if (self.config and pid) else None
                if page is None or not page.parent:
                    break
                pid = page.parent
        for pid, it in self._pages.items():
            level = page_levels.get(pid)
            text = LEVEL_TEXT[level] if level is not None else ""
            if pid is not None and pid not in snap.pages and self.config and self.config.page(pid):
                note = "vía recorrido" if pid in self.config.toured_pages() else "no visible"
                text = (text + " · " if text else "") + note
            it.setText(C_STATE, text)
            it.setForeground(C_STATE, QBrush(level_color(level)))

    def _fill(self, it: QTreeWidgetItem, st: VarStatus, sp: Optional[VarStatus]) -> Optional[Level]:
        var, rd = st.var, st.reading
        if var.kind == "text":
            cells = {C_PV: rd.text or ""}
        else:
            val = fmt(rd.value, var, rd.decimals) if rd.value is not None else ""
            cells = {C_SP: val if var.kind == "setpoint" else "", C_PV: val if var.kind == "actual" else ""}
            if sp is not None:
                cells[C_SP] = (fmt(sp.reading.value, sp.var, sp.reading.decimals)
                               if sp.reading.value is not None else "")
        tol = ""
        if st.warn_band is not None or st.alarm_band is not None:
            tol = f"{fmt(st.warn_band)} / {fmt(st.alarm_band)}"
        trend = ""
        if st.trend:
            arrow = "↑" if st.trend.slope_per_min > 0 else "↓"
            trend = f"{arrow} {st.trend.slope_per_min:+.3g}" if st.trend.slope_significant else "→ estable"
        levels = [x.level for x in (st, sp) if x is not None and x.fresh and x.level is not None]
        level = max(levels) if levels else None
        fresh = st.fresh or (sp is not None and sp.fresh)
        state = LEVEL_TEXT[level] if level is not None else (
            "no visible" if not rd.visible else ("sin dato" if not fresh else LEVEL_TEXT[None]))
        reasons = [f"{'consigna' if x is sp else 'medición'}: {x.reading.reason}"
                   for x in (st, sp) if x is not None and not x.reading.ok and x.reading.reason]
        ref_dec = sp.reading.decimals if sp is not None and st.ref_source == "consigna" else rd.decimals
        ref = f"{fmt(st.reference, var, ref_dec)} ({st.ref_source})" if st.reference is not None else ""
        if sp is not None and sp.reference is not None and st.ref_source != "receta":
            ref += f" · receta SP {fmt(sp.reference, sp.var)}"
        cells.update({
            C_REF: ref,
            C_DEV: f"{st.deviation:+.4g}" if st.deviation is not None else "",
            C_TOL: tol,
            C_STATE: state,
            C_TREND: trend,
            C_CPK: f"{st.trend.cpk:.2f}" if st.trend and st.trend.cpk is not None else "",
            C_READ: "ok" if not reasons else "; ".join(reasons),
        })
        for c, text in cells.items():
            if it.text(c) != text:
                it.setText(c, text)
        color = level_color(level)
        it.setBackground(C_STATE, QBrush(color))
        it.setForeground(C_STATE, QBrush(QColor("white")))
        pv_bad = st.level is not None and st.level >= Level.WARN and st.fresh
        sp_bad = sp is not None and sp.level is not None and sp.level >= Level.WARN and sp.fresh
        it.setForeground(C_PV, QBrush(level_color(st.level)) if pv_bad else self.palette().text())
        it.setForeground(C_SP, QBrush(level_color(sp.level)) if sp_bad else QBrush(SP_COLOR))
        if var.kind == "setpoint" and st.level is not None and st.level >= Level.WARN and st.fresh:
            it.setForeground(C_SP, QBrush(level_color(st.level)))
        return level

    def setpoint_of(self, var_id: str) -> Optional[str]:
        return self._pair_sp.get(var_id)

    @staticmethod
    def title(var: Variable, config: AppConfig) -> str:
        label = config.var_label(var)
        return f"{label} [{var.unit}]" if var.unit else label
