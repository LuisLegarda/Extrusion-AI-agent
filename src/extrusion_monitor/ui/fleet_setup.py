"""Configuración del dashboard global: carpeta de datos, indicadores por línea (plantilla y excepciones),
áreas, avisos y modo TV."""
from __future__ import annotations

import uuid
from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QFileDialog, QFormLayout, QHBoxLayout,
    QLabel, QLineEdit, QListWidget, QListWidgetItem, QMessageBox, QPushButton, QSpinBox, QTabWidget, QVBoxLayout,
    QWidget,
)

from ..analysis.kpis import KPIS
from ..fleet import MAX_LINE_TILES, FleetSettings, FleetTile, default_fleet_tiles
from ..i18n import tr, translate_widget
from .fleet_tiles import tile_title

KINDS = [("kpi", "Indicador (OEE, calidad, Cpk…)"), ("var", "Variable"), ("production", "Producción del turno"),
         ("alarms", "Alarmas activas")]
CHARTS = {"value": "Valor actual", "gauge": "Gauge", "bar": "Barra", "trend": "Gráfica de tiempo"}
PERIODS = [("Turno actual", 0), ("1 h", 3600), ("8 h", 8 * 3600), ("24 h", 86400)]


def charts_for(tile: FleetTile, var_kinds: dict[str, str]) -> list[str]:
    if tile.kind in ("production", "alarms"):
        return ["value"]
    if tile.kind == "var" and var_kinds.get(tile.var) in ("text", "selector"):
        return ["value"]
    return list(CHARTS)


class TileListEditor(QWidget):
    """Lista de 1 a 5 indicadores con su formulario (tipo, gráfico, tamaño, periodo)."""

    changed = Signal()

    def __init__(self, tiles: list[FleetTile], variables: dict[str, tuple[str, str]], columns: int):
        super().__init__()
        self.tiles = [t.model_copy(deep=True) for t in tiles]
        self.variables = variables  # id -> (etiqueta, tipo)
        self.columns = columns
        self._loading = False
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        left = QVBoxLayout()
        left.addWidget(QLabel(tr("<b>Indicadores de la tarjeta</b> (1 a {n}, en orden)", n=MAX_LINE_TILES)))
        self.lst = QListWidget()
        self.lst.currentRowChanged.connect(self._load)
        left.addWidget(self.lst, 1)
        row = QHBoxLayout()
        for text, slot in (("+ Agregar", self._add), ("Quitar", self._remove), ("▲", lambda: self._move(-1)),
                           ("▼", lambda: self._move(1))):
            b = QPushButton(text)
            b.clicked.connect(slot)
            row.addWidget(b)
        left.addLayout(row)
        root.addLayout(left, 1)
        self.form_w = QWidget()
        form = QFormLayout(self.form_w)
        self.cmb_kind = QComboBox()
        for k, label in KINDS:
            self.cmb_kind.addItem(label, k)
        self.cmb_kind.currentIndexChanged.connect(self._store)
        form.addRow("Contenido:", self.cmb_kind)
        self.cmb_kpi = QComboBox()
        for k, v in KPIS.items():
            self.cmb_kpi.addItem(v[0], k)
        self.cmb_kpi.currentIndexChanged.connect(self._store)
        self.lbl_kpi = QLabel("Indicador:")
        form.addRow(self.lbl_kpi, self.cmb_kpi)
        self.cmb_var = QComboBox()
        self.cmb_var.setEditable(True)
        self.cmb_var.setToolTip(tr("Variable por su ID (o nombre). Las líneas del mismo tipo la comparten; "
                                   "si una línea no la tiene, el indicador lo indica."))
        for vid, (label, _kind) in sorted(variables.items(), key=lambda x: x[1][0].lower()):
            self.cmb_var.addItem(f"{label}  [{vid}]", vid)
        self.cmb_var.currentIndexChanged.connect(self._store)
        self.cmb_var.lineEdit().editingFinished.connect(self._store)
        self.lbl_var = QLabel("Variable:")
        form.addRow(self.lbl_var, self.cmb_var)
        self.cmb_chart = QComboBox()
        self.cmb_chart.currentIndexChanged.connect(self._store)
        self.lbl_chart = QLabel("Gráfico:")
        form.addRow(self.lbl_chart, self.cmb_chart)
        size = QHBoxLayout()
        self.sp_w = QSpinBox()
        self.sp_w.setRange(1, max(1, columns))
        self.sp_w.setSuffix(" col.")
        self.sp_h = QSpinBox()
        self.sp_h.setRange(1, 3)
        self.sp_h.setSuffix(" filas")
        for sp in (self.sp_w, self.sp_h):
            sp.valueChanged.connect(self._store)
            size.addWidget(sp)
        size.addStretch(1)
        form.addRow("Tamaño (ancho × alto):", size)
        self.cmb_period = QComboBox()
        for label, secs in PERIODS:
            self.cmb_period.addItem(label, secs)
        self.cmb_period.currentIndexChanged.connect(self._store)
        self.lbl_period = QLabel("Periodo:")
        form.addRow(self.lbl_period, self.cmb_period)
        self.ed_title = QLineEdit()
        self.ed_title.setPlaceholderText("automático")
        self.ed_title.textChanged.connect(self._store)
        form.addRow("Título:", self.ed_title)
        root.addWidget(self.form_w, 1)
        self._fill()
        if self.tiles:
            self.lst.setCurrentRow(0)
        self._update_form()

    def set_columns(self, columns: int) -> None:
        self.columns = columns
        self.sp_w.setMaximum(columns)
        self._fill()

    def _var_kinds(self) -> dict[str, str]:
        return {k: v[1] for k, v in self.variables.items()}

    def _text(self, t: FleetTile) -> str:
        what = tr(CHARTS[t.chart]) if t.kind in ("kpi", "var") else ""
        return f"{tile_title(t)}{' — ' + what if what else ''}  ({min(t.width, self.columns)}×{t.height})"

    def _fill(self) -> None:
        row = self.lst.currentRow()
        self.lst.blockSignals(True)
        self.lst.clear()
        for t in self.tiles:
            self.lst.addItem(QListWidgetItem(self._text(t)))
        self.lst.blockSignals(False)
        if self.tiles:
            self.lst.setCurrentRow(min(max(row, 0), len(self.tiles) - 1))

    def _current(self) -> Optional[FleetTile]:
        r = self.lst.currentRow()
        return self.tiles[r] if 0 <= r < len(self.tiles) else None

    def _add(self) -> None:
        if len(self.tiles) >= MAX_LINE_TILES:
            QMessageBox.information(self, tr("Indicadores"),
                                    tr("Cada línea admite hasta {n} indicadores.", n=MAX_LINE_TILES))
            return
        self.tiles.append(FleetTile(id=uuid.uuid4().hex[:8], kind="kpi", kpi="oee", chart="value"))
        self._fill()
        self.lst.setCurrentRow(len(self.tiles) - 1)
        self.changed.emit()

    def _remove(self) -> None:
        r = self.lst.currentRow()
        if len(self.tiles) <= 1:
            QMessageBox.information(self, tr("Indicadores"), tr("La tarjeta necesita al menos un indicador."))
            return
        if 0 <= r < len(self.tiles):
            del self.tiles[r]
            self._fill()
            self._update_form()
            self.changed.emit()

    def _move(self, d: int) -> None:
        r = self.lst.currentRow()
        n = r + d
        if 0 <= r < len(self.tiles) and 0 <= n < len(self.tiles):
            self.tiles[r], self.tiles[n] = self.tiles[n], self.tiles[r]
            self._fill()
            self.lst.setCurrentRow(n)
            self.changed.emit()

    def _load(self, _row: int) -> None:
        t = self._current()
        if t is None:
            self._update_form()
            return
        self._loading = True
        try:
            self.cmb_kind.setCurrentIndex(max(0, self.cmb_kind.findData(t.kind)))
            self.cmb_kpi.setCurrentIndex(max(0, self.cmb_kpi.findData(t.kpi)))
            idx = self.cmb_var.findData(t.var)
            if idx >= 0:
                self.cmb_var.setCurrentIndex(idx)
            else:
                self.cmb_var.setEditText(t.var)
            self._fill_charts(t)
            self.sp_w.setMaximum(self.columns)
            self.sp_w.setValue(min(t.width, self.columns))
            self.sp_h.setValue(t.height)
            self.cmb_period.setCurrentIndex(max(0, self.cmb_period.findData(int(t.range_s))))
            self.ed_title.setText(t.title)
        finally:
            self._loading = False
        self._update_form()

    def _fill_charts(self, t: FleetTile) -> None:
        allowed = charts_for(t, self._var_kinds())
        self.cmb_chart.blockSignals(True)
        self.cmb_chart.clear()
        for c in allowed:
            self.cmb_chart.addItem(tr(CHARTS[c]), c)
        if t.chart not in allowed:
            t.chart = allowed[0]
        self.cmb_chart.setCurrentIndex(max(0, self.cmb_chart.findData(t.chart)))
        self.cmb_chart.blockSignals(False)

    def _update_form(self) -> None:
        t = self._current()
        self.form_w.setEnabled(t is not None)
        kind = t.kind if t else ""
        for w in (self.lbl_kpi, self.cmb_kpi):
            w.setVisible(kind == "kpi")
        for w in (self.lbl_var, self.cmb_var):
            w.setVisible(kind == "var")
        for w in (self.lbl_chart, self.cmb_chart):
            w.setVisible(kind in ("kpi", "var"))
        for w in (self.lbl_period, self.cmb_period):
            w.setVisible(t is not None and t.chart == "trend" and kind in ("kpi", "var"))

    def _store(self, *_):
        t = self._current()
        if self._loading or t is None:
            return
        t.kind = self.cmb_kind.currentData()
        t.kpi = self.cmb_kpi.currentData() or t.kpi
        text = self.cmb_var.currentText().strip()
        data = self.cmb_var.currentData()
        t.var = data if data and text == self.cmb_var.itemText(self.cmb_var.currentIndex()) else text
        chart = self.cmb_chart.currentData()
        if chart in charts_for(t, self._var_kinds()):
            t.chart = chart
        self._fill_charts(t)  # opciones según el tipo (texto y selectores: solo valor actual)
        t.width, t.height = self.sp_w.value(), self.sp_h.value()
        t.range_s = float(self.cmb_period.currentData())
        t.title = self.ed_title.text().strip()
        self._update_form()
        it = self.lst.currentItem()
        if it is not None:
            it.setText(self._text(t))
        self.changed.emit()


class FleetSetupDialog(QDialog):
    def __init__(self, settings: FleetSettings, lines: dict, parent=None):
        """`lines`: id de línea -> LineState (para conocer nombres, áreas y variables)."""
        super().__init__(parent)
        self.setWindowTitle("Configuración del dashboard global")
        self.resize(980, 640)
        self.settings = settings.model_copy(deep=True)
        self.lines = lines
        variables: dict[str, tuple[str, str]] = {}
        for ln in lines.values():
            for v in ln.status.get("variables") or []:
                variables.setdefault(v["id"], (v.get("label") or v.get("name") or v["id"], v.get("kind", "")))
        self.variables = variables
        root = QVBoxLayout(self)
        self.tabs = QTabWidget()
        root.addWidget(self.tabs, 1)
        self.tabs.addTab(self._general_tab(), "General")
        self.template = TileListEditor(self.settings.tiles, variables, self.settings.card_columns)
        tw = QWidget()
        tl = QVBoxLayout(tw)
        info = QLabel(tr("Estos indicadores se muestran en la tarjeta de todas las líneas. Si una línea es distinta, "
                         "dale indicadores propios en la pestaña «Por línea»."))
        info.setWordWrap(True)
        tl.addWidget(info)
        tl.addWidget(self.template, 1)
        b = QPushButton("Restablecer indicadores por defecto")
        b.clicked.connect(self._reset_template)
        tl.addWidget(b)
        self.tabs.addTab(tw, "Indicadores (todas las líneas)")
        self.tabs.addTab(self._lines_tab(), "Por línea")
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText("Aceptar")
        bb.button(QDialogButtonBox.Cancel).setText("Cancelar")
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        root.addWidget(bb)

    # --- general ---------------------------------------------------------------------------
    def _general_tab(self) -> QWidget:
        s = self.settings
        w = QWidget()
        form = QFormLayout(w)
        row = QHBoxLayout()
        self.ed_dir = QLineEdit(s.dir)
        self.ed_dir.setPlaceholderText(r"\\SERVIDOR\lineas")
        row.addWidget(self.ed_dir, 1)
        b = QPushButton("Examinar…")
        b.clicked.connect(self._browse)
        row.addWidget(b)
        form.addRow("Carpeta de datos de las líneas:", row)
        self.sp_poll = QDoubleSpinBox()
        self.sp_poll.setRange(1, 60)
        self.sp_poll.setSuffix(" s")
        self.sp_poll.setValue(s.poll_s)
        form.addRow("Actualizar cada:", self.sp_poll)
        self.sp_off = QDoubleSpinBox()
        self.sp_off.setRange(10, 3600)
        self.sp_off.setSuffix(" s")
        self.sp_off.setValue(s.offline_s)
        form.addRow("«Sin comunicación» después de:", self.sp_off)
        self.sp_cols = QSpinBox()
        self.sp_cols.setRange(1, 12)
        self.sp_cols.setValue(s.card_columns)
        self.sp_cols.setToolTip(tr("Columnas de indicadores de cada tarjeta. El tamaño de las tarjetas y de sus indicadores se ajusta "
                                   "solo al ancho de la ventana."))
        form.addRow("Columnas por tarjeta:", self.sp_cols)
        self.chk_group = QCheckBox("Agrupar las líneas por área")
        self.chk_group.setChecked(s.group_by_area)
        form.addRow(self.chk_group)
        form.addRow(QLabel("<b>Avisos</b> (la tarjeta parpadea hasta que se le da clic)"))
        self.chk_sound = QCheckBox("Sonido")
        self.chk_sound.setChecked(s.sound)
        form.addRow(self.chk_sound)
        self.chk_alarm = QCheckBox("Cuando una línea entra en alarma")
        self.chk_alarm.setChecked(s.notify_alarm)
        self.chk_stop = QCheckBox("Cuando una línea se detiene")
        self.chk_stop.setChecked(s.notify_stop)
        self.chk_off = QCheckBox("Cuando una línea pierde comunicación")
        self.chk_off.setChecked(s.notify_offline)
        for c in (self.chk_alarm, self.chk_stop, self.chk_off):
            form.addRow(c)
        self.sp_tv = QDoubleSpinBox()
        self.sp_tv.setRange(5, 600)
        self.sp_tv.setSuffix(" s")
        self.sp_tv.setValue(s.tv_rotate_s)
        form.addRow("Modo TV: cambiar de página cada:", self.sp_tv)
        self.sp_cols.valueChanged.connect(lambda v: [e.set_columns(v) for e in self._editors()])
        return w

    def _browse(self) -> None:
        d = QFileDialog.getExistingDirectory(self, tr("Carpeta de datos de las líneas"), self.ed_dir.text())
        if d:
            self.ed_dir.setText(d)

    def _reset_template(self) -> None:
        self.template.tiles = default_fleet_tiles()
        self.template._fill()
        self.template._update_form()

    # --- por línea ---------------------------------------------------------------------------
    def _lines_tab(self) -> QWidget:
        w = QWidget()
        lay = QHBoxLayout(w)
        left = QVBoxLayout()
        left.addWidget(QLabel("<b>Líneas</b>"))
        self.lst_lines = QListWidget()
        for lid, ln in sorted(self.lines.items(), key=lambda x: x[1].name.lower()):
            it = QListWidgetItem(f"{ln.name}  [{lid}]")
            it.setData(Qt.UserRole, lid)
            self.lst_lines.addItem(it)
        if not self.lines:
            self.lst_lines.addItem(tr("(ninguna línea ha escrito en la carpeta todavía)"))
        self.lst_lines.currentRowChanged.connect(self._line_selected)
        left.addWidget(self.lst_lines, 1)
        lay.addLayout(left, 1)
        right = QVBoxLayout()
        form = QFormLayout()
        self.ed_area = QLineEdit()
        self.ed_area.setPlaceholderText("(la que publica la línea)")
        self.ed_area.textChanged.connect(self._store_line)
        form.addRow("Área:", self.ed_area)
        self.chk_own = QCheckBox("Indicadores propios para esta línea")
        self.chk_own.toggled.connect(self._own_toggled)
        form.addRow(self.chk_own)
        right.addLayout(form)
        self.own_host = QVBoxLayout()
        right.addLayout(self.own_host, 1)
        lay.addLayout(right, 2)
        self._own_editors: dict[str, TileListEditor] = {}
        self._line: Optional[str] = None
        for k in ("ed_area", "chk_own"):
            getattr(self, k).setEnabled(False)
        return w

    def _editors(self) -> list[TileListEditor]:
        return [self.template] + list(self._own_editors.values())

    def _line_selected(self, row: int) -> None:
        it = self.lst_lines.item(row)
        lid = it.data(Qt.UserRole) if it else None
        self._line = lid
        for k in ("ed_area", "chk_own"):
            getattr(self, k).setEnabled(lid is not None)
        for e in self._own_editors.values():
            e.setVisible(False)
        if lid is None:
            return
        self.ed_area.blockSignals(True)
        self.ed_area.setText(self.settings.areas.get(lid, ""))
        self.ed_area.setPlaceholderText(self.lines[lid].status.get("area") or tr("(sin área)"))
        self.ed_area.blockSignals(False)
        e = self._own_editors.get(lid)
        own = e.isEnabled() if e is not None else lid in self.settings.overrides
        self.chk_own.blockSignals(True)
        self.chk_own.setChecked(own)
        self.chk_own.blockSignals(False)
        if self.chk_own.isChecked():
            self._editor_for(lid).setVisible(True)

    def _editor_for(self, lid: str) -> TileListEditor:
        e = self._own_editors.get(lid)
        if e is None:
            base = self.settings.overrides.get(lid) or self.template.tiles
            e = TileListEditor(base, self.variables, self.sp_cols.value())
            self._own_editors[lid] = e
            self.own_host.addWidget(e)
            translate_widget(e)  # se crea con la ventana ya abierta
        return e

    def _own_toggled(self, on: bool) -> None:
        lid = self._line
        if lid is None:
            return
        e = self._editor_for(lid)
        e.setEnabled(on)
        e.setVisible(on)

    def _store_line(self, *_):
        if self._line is None:
            return
        text = self.ed_area.text().strip()
        if text:
            self.settings.areas[self._line] = text
        else:
            self.settings.areas.pop(self._line, None)

    # --- resultado ---------------------------------------------------------------------------
    def result_settings(self) -> FleetSettings:
        s = self.settings
        s.dir = self.ed_dir.text().strip()
        s.poll_s, s.offline_s = self.sp_poll.value(), self.sp_off.value()
        s.card_columns = self.sp_cols.value()
        s.group_by_area = self.chk_group.isChecked()
        s.sound = self.chk_sound.isChecked()
        s.notify_alarm, s.notify_stop = self.chk_alarm.isChecked(), self.chk_stop.isChecked()
        s.notify_offline = self.chk_off.isChecked()
        s.tv_rotate_s = self.sp_tv.value()
        s.tiles = [t.model_copy(deep=True) for t in self.template.tiles]
        for lid, e in self._own_editors.items():
            if e.isEnabled():
                s.overrides[lid] = [t.model_copy(deep=True) for t in e.tiles]
            else:
                s.overrides.pop(lid, None)
        return FleetSettings.model_validate(s.model_dump())

    def accept(self) -> None:
        if not self.ed_dir.text().strip():
            QMessageBox.warning(self, tr("Falta la carpeta"), tr("Indica la carpeta donde escriben las líneas."))
            self.tabs.setCurrentIndex(0)
            return
        super().accept()
