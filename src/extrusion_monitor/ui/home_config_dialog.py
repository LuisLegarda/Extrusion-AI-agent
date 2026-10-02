"""Personalizar el tablero de Inicio: qué mosaicos se muestran, con qué gráfico y de qué tamaño."""
from __future__ import annotations

import uuid
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QDoubleValidator
from PySide6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QMessageBox, QPushButton, QSpinBox, QVBoxLayout, QWidget,
)

from ..config import KPI_KINDS, MAX_TREND_VARS, SINGLE_KINDS, AppConfig, HomeSettings, HomeTile
from ..i18n import tr
from .home_page import BUILTIN_TILES
from .home_tiles import CHART_LABELS, charts_for, tile_title
from .main_window import RANGES

KPI_CHARTS = {"gauge": "Gauge", "value": "Valor actual", "trend": "Gráfica de tiempo"}
PERIODS = [("Turno actual", 0)] + RANGES


class HomeConfigDialog(QDialog):
    def __init__(self, config: AppConfig, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Personalizar tablero de Inicio")
        self.resize(900, 600)
        self.config = config
        self.home: HomeSettings = config.home.model_copy(deep=True)
        self._loading = False

        root = QVBoxLayout(self)
        top = QHBoxLayout()
        top.addWidget(QLabel("Columnas del tablero:"))
        self.sp_cols = QSpinBox()
        self.sp_cols.setRange(1, 12)
        self.sp_cols.setValue(self.home.columns)
        self.sp_cols.valueChanged.connect(self._cols_changed)
        top.addWidget(self.sp_cols)
        top.addStretch(1)
        root.addLayout(top)

        body = QHBoxLayout()
        left = QVBoxLayout()
        left.addWidget(QLabel("<b>Mosaicos</b> (en orden: de izquierda a derecha y de arriba abajo)"))
        self.lst = QListWidget()
        self.lst.currentRowChanged.connect(self._load)
        left.addWidget(self.lst, 1)
        btns = QHBoxLayout()
        for text, slot in (("+ Variable", self._add_var), ("+ Indicador", self._add_builtin), ("Quitar", self._remove),
                           ("▲", lambda: self._move(-1)), ("▼", lambda: self._move(1))):
            b = QPushButton(text)
            b.clicked.connect(slot)
            btns.addWidget(b)
        left.addLayout(btns)
        b = QPushButton("Restablecer tablero por defecto")
        b.clicked.connect(self._reset)
        left.addWidget(b)
        body.addLayout(left, 1)

        self.form_w = QWidget()
        form = QFormLayout(self.form_w)
        self.cmb_kind = QComboBox()
        self.cmb_kind.addItem("Variable", "var")
        for k, label in BUILTIN_TILES.items():
            self.cmb_kind.addItem(label, k)
        self.cmb_kind.currentIndexChanged.connect(self._kind_changed)
        form.addRow("Contenido:", self.cmb_kind)
        self.lst_vars = QListWidget()
        self.lst_vars.setMinimumHeight(160)
        self.lst_vars.itemChanged.connect(self._vars_changed)
        self.lbl_vars = QLabel("Variables:")
        form.addRow(self.lbl_vars, self.lst_vars)
        self.lbl_vars_hint = QLabel()
        self.lbl_vars_hint.setWordWrap(True)
        form.addRow("", self.lbl_vars_hint)
        self.cmb_chart = QComboBox()
        self.cmb_chart.currentIndexChanged.connect(self._store)
        self.lbl_chart = QLabel("Gráfico:")
        form.addRow(self.lbl_chart, self.cmb_chart)
        self.ed_title = QLineEdit()
        self.ed_title.setPlaceholderText("automático")
        self.ed_title.textChanged.connect(self._store)
        form.addRow("Título:", self.ed_title)
        size = QHBoxLayout()
        self.sp_w = QSpinBox()
        self.sp_w.setRange(1, 12)
        self.sp_w.setSuffix(" col.")
        self.sp_h = QSpinBox()
        self.sp_h.setRange(1, 4)
        self.sp_h.setSuffix(" filas")
        for sp in (self.sp_w, self.sp_h):
            sp.valueChanged.connect(self._store)
            size.addWidget(sp)
        size.addStretch(1)
        form.addRow("Tamaño (ancho × alto):", size)
        self.cmb_range = QComboBox()
        for label, secs in PERIODS:
            self.cmb_range.addItem(label, secs)
        self.cmb_range.currentIndexChanged.connect(self._store)
        self.lbl_range = QLabel("Rango de tiempo:")
        form.addRow(self.lbl_range, self.cmb_range)
        scale = QHBoxLayout()
        self.ed_min = QLineEdit()
        self.ed_max = QLineEdit()
        for ed in (self.ed_min, self.ed_max):
            ed.setPlaceholderText("auto")
            ed.setValidator(QDoubleValidator())
            ed.textChanged.connect(self._store)
            scale.addWidget(ed)
        self.lbl_scale = QLabel("Escala (mín. / máx.):")
        form.addRow(self.lbl_scale, scale)
        self.lbl_scale_hint = QLabel("Vacío = automática: límites de la receta con margen y datos recientes.")
        self.lbl_scale_hint.setWordWrap(True)
        form.addRow("", self.lbl_scale_hint)
        body.addWidget(self.form_w, 1)
        root.addLayout(body, 1)

        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText("Aceptar")
        bb.button(QDialogButtonBox.Cancel).setText("Cancelar")
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        root.addWidget(bb)
        self._fill_list()
        if self.home.tiles:
            self.lst.setCurrentRow(0)
        self._update_form()

    # --- lista -----------------------------------------------------------------------------
    def _item_text(self, t: HomeTile) -> str:
        if t.kind == "var":
            name = tile_title(t, self.config)
            what = tr(CHART_LABELS.get(t.chart, t.chart))
        elif t.kind in KPI_KINDS:
            name = t.title or tr(BUILTIN_TILES.get(t.kind, t.kind))
            what = tr(KPI_CHARTS[t.kpi_chart])
        else:
            name = t.title or tr(BUILTIN_TILES.get(t.kind, t.kind))
            what = tr("indicador")
        return f"{name} — {what}  ({min(t.width, self.home.columns)}×{t.height})"

    def _fill_list(self) -> None:
        row = self.lst.currentRow()
        self.lst.blockSignals(True)
        self.lst.clear()
        for t in self.home.tiles:
            self.lst.addItem(QListWidgetItem(self._item_text(t)))
        self.lst.blockSignals(False)
        if self.home.tiles:
            self.lst.setCurrentRow(min(max(row, 0), len(self.home.tiles) - 1))

    def _current(self) -> Optional[HomeTile]:
        r = self.lst.currentRow()
        return self.home.tiles[r] if 0 <= r < len(self.home.tiles) else None

    def _refresh_item(self) -> None:
        t = self._current()
        if t is not None:
            self.lst.currentItem().setText(self._item_text(t))

    def _numeric_vars(self):
        return [v for v in self.config.variables if v.numeric]

    def _add_var(self) -> None:
        vars_ = self._numeric_vars() or self.config.variables
        t = HomeTile(id=uuid.uuid4().hex[:8], kind="var", var_ids=[vars_[0].id] if vars_ else [], chart="gauge")
        self.home.tiles.append(t)
        self._fill_list()
        self.lst.setCurrentRow(len(self.home.tiles) - 1)

    def _add_builtin(self) -> None:
        # Los indicadores numéricos se pueden repetir (p. ej. OEE en gauge y en gráfica de tiempo).
        self.home.tiles.append(HomeTile(id=uuid.uuid4().hex[:8], kind="oee", kpi_chart="trend", width=2,
                                        range_s=0))
        self._fill_list()
        self.lst.setCurrentRow(len(self.home.tiles) - 1)

    def _remove(self) -> None:
        r = self.lst.currentRow()
        if 0 <= r < len(self.home.tiles):
            del self.home.tiles[r]
            self._fill_list()
            self._update_form()

    def _move(self, d: int) -> None:
        r = self.lst.currentRow()
        n = r + d
        if 0 <= r < len(self.home.tiles) and 0 <= n < len(self.home.tiles):
            tiles = self.home.tiles
            tiles[r], tiles[n] = tiles[n], tiles[r]
            self._fill_list()
            self.lst.setCurrentRow(n)

    def _reset(self) -> None:
        if QMessageBox.question(self, tr("Restablecer"), tr("¿Reemplazar el tablero por el diseño por defecto?")) \
                != QMessageBox.Yes:
            return
        self.home = HomeSettings()
        self.sp_cols.setValue(self.home.columns)
        self._fill_list()
        self._update_form()

    def _cols_changed(self, v: int) -> None:
        self.home.columns = v
        self._fill_list()

    # --- formulario ------------------------------------------------------------------------
    def _load(self, _row: int) -> None:
        t = self._current()
        self._loading = True
        try:
            if t is not None:
                self.cmb_kind.setCurrentIndex(max(0, self.cmb_kind.findData(t.kind)))
                self._fill_vars(t)
                self._fill_charts(t)
                self.ed_title.setText(t.title)
                self.sp_w.setValue(t.width)
                self.sp_h.setValue(t.height)
                idx = self.cmb_range.findData(int(t.range_s))
                self.cmb_range.setCurrentIndex(idx if idx >= 0 else self.cmb_range.findData(900))
                self.ed_min.setText("" if t.scale_min is None else f"{t.scale_min:g}")
                self.ed_max.setText("" if t.scale_max is None else f"{t.scale_max:g}")
        finally:
            self._loading = False
        self._update_form()

    def _fill_vars(self, t: HomeTile) -> None:
        self.lst_vars.blockSignals(True)
        self.lst_vars.clear()
        for v in self.config.variables:
            label = self.config.var_label(v) + (f" ({v.unit})" if v.unit else "")
            if not v.numeric:
                label += "  · " + tr("texto/selector")
            it = QListWidgetItem(label)
            it.setData(Qt.UserRole, v.id)
            it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
            it.setCheckState(Qt.Checked if v.id in t.var_ids else Qt.Unchecked)
            self.lst_vars.addItem(it)
        self.lst_vars.blockSignals(False)

    def _fill_charts(self, t: HomeTile) -> None:
        if t.kind in KPI_KINDS:
            self.cmb_chart.blockSignals(True)
            self.cmb_chart.clear()
            for c, label in KPI_CHARTS.items():
                self.cmb_chart.addItem(tr(label), c)
            self.cmb_chart.setCurrentIndex(max(0, self.cmb_chart.findData(t.kpi_chart)))
            self.cmb_chart.blockSignals(False)
            return
        first = self.config.variable(t.var_ids[0]) if t.var_ids else None
        allowed = charts_for(first)
        self.cmb_chart.blockSignals(True)
        self.cmb_chart.clear()
        for c in allowed:
            self.cmb_chart.addItem(tr(CHART_LABELS[c]), c)
        if t.chart not in allowed:
            t.chart = allowed[0]
        self.cmb_chart.setCurrentIndex(max(0, self.cmb_chart.findData(t.chart)))
        self.cmb_chart.blockSignals(False)

    def _update_form(self) -> None:
        t = self._current()
        self.form_w.setEnabled(t is not None)
        is_var = t is not None and t.kind == "var"
        is_kpi = t is not None and t.kind in KPI_KINDS
        chart = t.chart if is_var else ("kpi_" + t.kpi_chart if is_kpi else "")
        for w in (self.lbl_vars, self.lst_vars, self.lbl_vars_hint):
            w.setVisible(is_var)
        for w in (self.lbl_chart, self.cmb_chart):
            w.setVisible(is_var or is_kpi)
        for w in (self.lbl_range, self.cmb_range):
            w.setVisible(chart in ("trend", "histogram", "value", "kpi_trend"))
        for w in (self.lbl_scale, self.ed_min, self.ed_max, self.lbl_scale_hint):
            w.setVisible(chart in ("gauge", "bar"))
        self.lbl_vars_hint.setText(
            tr("Tendencia: hasta {n} variables en la misma gráfica.", n=MAX_TREND_VARS) if chart == "trend" else
            tr("Una variable. Los gráficos disponibles dependen de su tipo: las de texto y los selectores "
               "muestran su estado actual."))

    def _kind_changed(self, _i: int) -> None:
        t = self._current()
        if self._loading or t is None:
            return
        kind = self.cmb_kind.currentData()
        if kind in SINGLE_KINDS and any(o is not t and o.kind == kind for o in self.home.tiles):
            QMessageBox.information(self, tr("Indicadores"), tr("Ese indicador ya está en el tablero."))
            self._loading = True
            self.cmb_kind.setCurrentIndex(max(0, self.cmb_kind.findData(t.kind)))
            self._loading = False
            return
        t.kind = kind
        if kind == "var" and not t.var_ids:
            vars_ = self._numeric_vars()
            t.var_ids = [vars_[0].id] if vars_ else []
        self._load(self.lst.currentRow())
        self._refresh_item()

    def _vars_changed(self, item: QListWidgetItem) -> None:
        t = self._current()
        if self._loading or t is None:
            return
        vid = item.data(Qt.UserRole)
        on = item.checkState() == Qt.Checked
        if on:
            if t.chart == "trend":
                var = self.config.variable(vid)
                if var is not None and not var.numeric:
                    QMessageBox.information(self, tr("Tendencia"), tr("La tendencia solo admite variables numéricas."))
                    self._uncheck(vid)
                    return
                t.var_ids = [v for v in t.var_ids if v != vid] + [vid]
                if len(t.var_ids) > MAX_TREND_VARS:
                    self._uncheck(t.var_ids.pop(0))
            else:
                old = [v for v in t.var_ids if v != vid]
                t.var_ids = [vid]
                for o in old:
                    self._uncheck(o)
        else:
            t.var_ids = [v for v in t.var_ids if v != vid]
        self._fill_charts(t)
        self._update_form()
        self._refresh_item()

    def _uncheck(self, vid: str) -> None:
        self.lst_vars.blockSignals(True)
        for i in range(self.lst_vars.count()):
            it = self.lst_vars.item(i)
            if it.data(Qt.UserRole) == vid:
                it.setCheckState(Qt.Unchecked)
        self.lst_vars.blockSignals(False)

    def _store(self, *_):
        t = self._current()
        if self._loading or t is None:
            return
        if t.kind in KPI_KINDS:
            t.kpi_chart = self.cmb_chart.currentData() or t.kpi_chart
        if t.kind == "var":
            chart = self.cmb_chart.currentData()
            if chart and chart != t.chart:
                t.chart = chart
                if chart != "trend" and len(t.var_ids) > 1:
                    for o in t.var_ids[1:]:
                        self._uncheck(o)
                    t.var_ids = t.var_ids[:1]
        t.title = self.ed_title.text().strip()
        t.width, t.height = self.sp_w.value(), self.sp_h.value()
        t.range_s = float(self.cmb_range.currentData())

        def num(ed: QLineEdit) -> Optional[float]:
            try:
                return float(ed.text().replace(",", "."))
            except ValueError:
                return None

        t.scale_min, t.scale_max = num(self.ed_min), num(self.ed_max)
        self._update_form()
        self._refresh_item()

    def accept(self) -> None:
        bad = [t for t in self.home.tiles if t.kind == "var" and not t.var_ids]
        if bad:
            QMessageBox.warning(self, tr("Revisa el tablero"), tr("Hay mosaicos de variable sin variable elegida."))
            return
        for t in self.home.tiles:
            if t.scale_min is not None and t.scale_max is not None and t.scale_max <= t.scale_min:
                QMessageBox.warning(self, tr("Revisa el tablero"),
                                    tr("La escala máxima debe ser mayor que la mínima."))
                return
        super().accept()
