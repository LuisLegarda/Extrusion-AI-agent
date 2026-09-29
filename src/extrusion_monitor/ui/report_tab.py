"""Pestaña del configurador: reportes PDF automáticos."""
from __future__ import annotations

import time
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog, QFormLayout, QGroupBox, QHBoxLayout, QHeaderView, QLabel,
    QLineEdit, QListWidget, QListWidgetItem, QMessageBox, QPushButton, QScrollArea, QTableWidget, QVBoxLayout,
    QWidget,
)

from ..i18n import translate_widget
from ..config import ReportDef, ReportTrigger, ReportVar

if TYPE_CHECKING:
    from .setup_dialog import SetupDialog

KINDS = [("cross", "Variable cruza un valor"), ("decrease", "Valor pasa a uno menor"),
         ("change", "Valor / texto cambia"),
         ("selector", "Selector cambia de estado"), ("tour", "Se ejecuta un recorrido")]


class ReportTab(QWidget):
    def __init__(self, dlg: "SetupDialog"):
        super().__init__()
        self.dlg = dlg
        self.report: Optional[ReportDef] = None
        self._loading = False
        self._build()
        self.reload()

    # --- construcción ---------------------------------------------------------
    def _build(self) -> None:
        outer = QVBoxLayout(self)
        intro = QLabel(
            "El reporte PDF se genera solo cuando ocurre alguno de sus disparadores y abarca desde el fin del "
            "reporte anterior hasta ese momento. Cada variable se evalúa por especificación (todas las lecturas "
            "dentro de los límites de la receta) o por Cpk mínimo; el resultado general es conforme si todas lo son.")
        intro.setWordWrap(True)
        outer.addWidget(intro)
        row = QHBoxLayout()
        row.addWidget(QLabel("Reporte:"))
        self.cmb_rep = QComboBox()
        self.cmb_rep.currentIndexChanged.connect(self._selected)
        row.addWidget(self.cmb_rep, 1)
        for text, slot in (("+ Nuevo", self._new), ("Duplicar", self._dup), ("Eliminar", self._delete)):
            b = QPushButton(text)
            b.clicked.connect(slot)
            row.addWidget(b)
        outer.addLayout(row)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        body = QWidget()
        scroll.setWidget(body)
        outer.addWidget(scroll, 1)
        lay = QVBoxLayout(body)

        gen = QGroupBox("General")
        f = QFormLayout(gen)
        self.ed_name = QLineEdit()
        self.ed_name.editingFinished.connect(self._commit)
        f.addRow("Nombre", self.ed_name)
        self.chk_enabled = QCheckBox("Activado")
        f.addRow(self.chk_enabled)
        self.sp_min = QDoubleSpinBox()
        self.sp_min.setRange(0, 86400)
        self.sp_min.setSuffix(" s")
        f.addRow("Tiempo mínimo entre reportes", self.sp_min)
        self.sp_max = QDoubleSpinBox()
        self.sp_max.setRange(0.1, 24 * 31)
        self.sp_max.setSuffix(" h")
        f.addRow("Periodo máximo (primer reporte)", self.sp_max)
        self.chk_reset = QCheckBox("Reiniciar tendencias, estadística y comportamiento al generarlo")
        f.addRow(self.chk_reset)
        lay.addWidget(gen)

        trg = QGroupBox("Disparadores (cualquiera genera el reporte)")
        tl = QVBoxLayout(trg)
        self.tbl_trg = QTableWidget(0, 4)
        self.tbl_trg.setHorizontalHeaderLabels(["Tipo", "Variable / recorrido", "Condición", "Valor / estado"])
        hh = self.tbl_trg.horizontalHeader()
        hh.setSectionResizeMode(QHeaderView.Stretch)
        hh.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.tbl_trg.verticalHeader().setVisible(False)
        self.tbl_trg.setMinimumHeight(110)
        tl.addWidget(self.tbl_trg)
        row = QHBoxLayout()
        b = QPushButton("+ Disparador")
        b.clicked.connect(self._add_trigger)
        row.addWidget(b)
        b = QPushButton("Quitar")
        b.clicked.connect(lambda: self._remove_row(self.tbl_trg, self.report.triggers if self.report else None))
        row.addWidget(b)
        row.addStretch(1)
        tl.addLayout(row)
        lay.addWidget(trg)

        var = QGroupBox("Variables y estados del reporte")
        vl = QVBoxLayout(var)
        self.tbl_var = QTableWidget(0, 6)
        self.tbl_var.setHorizontalHeaderLabels(["Variable", "Evaluación", "Cpk mín.", "Gráfica", "Eventos", "CSV"])
        hh = self.tbl_var.horizontalHeader()
        hh.setSectionResizeMode(QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(0, QHeaderView.Stretch)
        self.tbl_var.verticalHeader().setVisible(False)
        self.tbl_var.setMinimumHeight(150)
        vl.addWidget(self.tbl_var)
        row = QHBoxLayout()
        self.cmb_add_var = QComboBox()
        row.addWidget(self.cmb_add_var, 1)
        b = QPushButton("+ Agregar")
        b.clicked.connect(self._add_var)
        row.addWidget(b)
        b = QPushButton("Quitar")
        b.clicked.connect(lambda: self._remove_row(self.tbl_var, self.report.variables if self.report else None))
        row.addWidget(b)
        vl.addLayout(row)
        lay.addWidget(var)

        beh = QGroupBox("Gráfica de comportamiento (modelos entrenados)")
        bl = QVBoxLayout(beh)
        self.lst_beh = QListWidget()
        self.lst_beh.setMaximumHeight(90)
        self.lst_beh.itemChanged.connect(lambda _: self._commit())
        bl.addWidget(self.lst_beh)
        lay.addWidget(beh)

        out = QGroupBox("Salida")
        f = QFormLayout(out)
        self.chk_general = QCheckBox("Incluir también eventos generales (recetas, recorridos, reportes)")
        f.addRow(self.chk_general)
        self.chk_csv = QCheckBox("Exportar los datos de las variables marcadas en CSV")
        f.addRow(self.chk_csv)
        self.cmb_name = QComboBox()
        f.addRow("Nombre del archivo", self.cmb_name)
        row = QHBoxLayout()
        self.ed_dir = QLineEdit()
        self.ed_dir.setPlaceholderText(str(self.dlg.ctx.workspace.default_reports_dir()))
        self.ed_dir.editingFinished.connect(self._commit)
        row.addWidget(self.ed_dir, 1)
        b = QPushButton("…")
        b.clicked.connect(self._browse)
        row.addWidget(b)
        b = QPushButton("Abrir carpeta")
        b.clicked.connect(self._open_dir)
        row.addWidget(b)
        f.addRow("Carpeta", row)
        lay.addWidget(out)

        for w in (self.chk_enabled, self.chk_reset, self.chk_general, self.chk_csv):
            w.toggled.connect(self._commit)
        for w in (self.sp_min, self.sp_max):
            w.valueChanged.connect(self._commit)
        self.cmb_name.currentIndexChanged.connect(self._commit)

        row = QHBoxLayout()
        b = QPushButton("📄 Generar vista previa ahora")
        b.setToolTip("Genera el reporte con los datos desde el último reporte, sin mover el inicio del siguiente")
        b.clicked.connect(self._preview)
        row.addWidget(b)
        row.addStretch(1)
        lay.addLayout(row)
        self.lbl_status = QLabel()
        self.lbl_status.setWordWrap(True)
        lay.addWidget(self.lbl_status)

    # --- lista de reportes --------------------------------------------------------------
    def reload(self) -> None:
        reps = self.dlg.config.reports
        keep = self.report.id if any(r is self.report for r in reps) else None
        self._loading = True
        self.cmb_rep.clear()
        for r in reps:
            self.cmb_rep.addItem(r.name, r.id)
        self._loading = False
        self.cmb_rep.setCurrentIndex(max(0, self.cmb_rep.findData(keep) if keep else 0))
        self._selected()

    def _selected(self) -> None:
        if self._loading:
            return
        rid = self.cmb_rep.currentData()
        self.report = next((r for r in self.dlg.config.reports if r.id == rid), None)
        self.refresh()

    def _new(self) -> None:
        r = ReportDef(id=uuid.uuid4().hex[:10], name=f"Reporte {len(self.dlg.config.reports) + 1}")
        self.dlg.config.reports.append(r)
        self.report = r
        self.reload()

    def _dup(self) -> None:
        if self.report is None:
            return
        r = self.report.model_copy(deep=True)
        r.id = uuid.uuid4().hex[:10]
        r.name = f"{self.report.name} (copia)"
        self.dlg.config.reports.append(r)
        self.report = r
        self.reload()

    def _delete(self) -> None:
        if self.report is None:
            return
        if QMessageBox.question(self, "Eliminar", f"¿Eliminar el reporte «{self.report.name}»?") != QMessageBox.Yes:
            return
        self.dlg.config.reports.remove(self.report)
        self.report = None
        self.reload()

    # --- estado ---------------------------------------------------------------------
    def refresh(self) -> None:
        cfg = self.dlg.config
        r = self.report
        for w in self.findChildren(QGroupBox):
            w.setEnabled(r is not None)
        self._loading = True
        self.cmb_add_var.clear()
        for v in cfg.variables:
            self.cmb_add_var.addItem(cfg.var_label(v), v.id)
        self.cmb_name.clear()
        self.cmb_name.addItem("Fecha y hora", None)
        for v in cfg.variables:
            if v.kind in ("text", "selector", "actual", "setpoint", "formula"):
                self.cmb_name.addItem(f"Valor de «{cfg.var_label(v)}»", v.id)
        self.lst_beh.clear()
        self.tbl_trg.setRowCount(0)
        self.tbl_var.setRowCount(0)
        if r is not None:
            self.ed_name.setText(r.name)
            self.chk_enabled.setChecked(r.enabled)
            self.sp_min.setValue(r.min_interval_s)
            self.sp_max.setValue(r.max_period_h)
            self.chk_reset.setChecked(r.reset_analysis)
            self.chk_general.setChecked(r.include_general_events)
            self.chk_csv.setChecked(r.export_csv)
            self.cmb_name.setCurrentIndex(max(0, self.cmb_name.findData(r.name_var)))
            self.ed_dir.setText(r.output_dir or "")
            for m in self.dlg.ctx.engine.behaviors.store.models:
                it = QListWidgetItem(m.name + ("" if m.trained else "  (sin entrenar)"))
                it.setData(Qt.UserRole, m.id)
                it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
                it.setCheckState(Qt.Checked if m.id in r.behavior_models else Qt.Unchecked)
                self.lst_beh.addItem(it)
            for tr in r.triggers:
                self._trigger_row(tr)
            for rv in r.variables:
                self._var_row(rv)
        translate_widget(self)  # filas creadas después de mostrar el diálogo
        self._loading = False

    def _var_combo(self, kinds: Optional[tuple], value: Optional[str]) -> QComboBox:
        cfg = self.dlg.config
        cmb = QComboBox()
        for v in cfg.variables:
            if kinds is None or v.kind in kinds:
                cmb.addItem(cfg.var_label(v), v.id)
        cmb.setCurrentIndex(max(0, cmb.findData(value)))
        return cmb

    def _trigger_row(self, tr: ReportTrigger) -> None:
        cfg = self.dlg.config
        i = self.tbl_trg.rowCount()
        self.tbl_trg.insertRow(i)
        kind = QComboBox()
        for k, label in KINDS:
            kind.addItem(label, k)
        kind.setCurrentIndex(max(0, kind.findData(tr.kind)))
        self.tbl_trg.setCellWidget(i, 0, kind)
        if tr.kind == "tour":
            target = QComboBox()
            target.addItem("cualquier recorrido", None)
            for t in cfg.tours:
                target.addItem(t.name, t.id)
            target.setCurrentIndex(max(0, target.findData(tr.tour_id)))
            target.currentIndexChanged.connect(lambda _=0, tr=tr, w=target: self._set(tr, "tour_id", w.currentData()))
        else:
            kinds = {"cross": ("actual", "setpoint", "formula"), "decrease": ("actual", "setpoint", "formula"),
                     "selector": ("selector", "text")}.get(tr.kind)
            target = self._var_combo(kinds, tr.var_id)
            if tr.var_id is None and target.count():
                tr.var_id = target.currentData()
            target.currentIndexChanged.connect(lambda _=0, tr=tr, w=target: self._trigger_var(tr, w.currentData()))
        self.tbl_trg.setCellWidget(i, 1, target)
        if tr.kind == "cross":
            op = QComboBox()
            for o in (">", ">=", "<", "<="):
                op.addItem(o, o)
            op.setCurrentIndex(max(0, op.findData(tr.op)))
            op.currentIndexChanged.connect(lambda _=0, tr=tr, w=op: self._set(tr, "op", w.currentData()))
            self.tbl_trg.setCellWidget(i, 2, op)
        elif tr.kind == "change":
            self.tbl_trg.setCellWidget(i, 2, QLabel(" cambio mayor a"))
        elif tr.kind == "decrease":
            lbl = QLabel(" baja más de")
            lbl.setToolTip("Se dispara cuando el valor es menor que la lectura anterior por más de esta cantidad "
                           "(0 = cualquier baja). Útil para contadores que se reinician, como la longitud del carrete.")
            self.tbl_trg.setCellWidget(i, 2, lbl)
        if tr.kind in ("cross", "change", "decrease"):
            sp = QDoubleSpinBox()
            sp.setRange(-1e9, 1e9)
            sp.setDecimals(3)
            sp.setValue(tr.value)
            sp.valueChanged.connect(lambda v, tr=tr: self._set(tr, "value", v))
            self.tbl_trg.setCellWidget(i, 3, sp)
        elif tr.kind == "selector":
            st = QComboBox()
            st.addItem("cualquier estado", None)
            var = cfg.variable(tr.var_id) if tr.var_id else None
            for s in (var.states if var else []):
                st.addItem(s, s)
            st.setCurrentIndex(max(0, st.findData(tr.state)))
            st.currentIndexChanged.connect(lambda _=0, tr=tr, w=st: self._set(tr, "state", w.currentData()))
            self.tbl_trg.setCellWidget(i, 3, st)
        kind.currentIndexChanged.connect(lambda _=0, tr=tr, w=kind: self._trigger_kind(tr, w.currentData()))

    def _set(self, obj, attr: str, value) -> None:
        if not self._loading:
            setattr(obj, attr, value)

    def _trigger_kind(self, tr: ReportTrigger, kind: str) -> None:
        if self._loading:
            return
        tr.kind = kind
        tr.var_id = tr.state = tr.tour_id = None
        self.refresh()

    def _trigger_var(self, tr: ReportTrigger, var_id: Optional[str]) -> None:
        if self._loading:
            return
        tr.var_id = var_id
        if tr.kind == "selector":
            tr.state = None
            self.refresh()

    def _var_row(self, rv: ReportVar) -> None:
        cfg = self.dlg.config
        i = self.tbl_var.rowCount()
        self.tbl_var.insertRow(i)
        var = cfg.variable(rv.var_id)
        self.tbl_var.setCellWidget(i, 0, QLabel(" " + (cfg.var_label(var) if var else rv.var_id)))
        crit = QComboBox()
        crit.addItem("En especificación", "spec")
        crit.addItem("Cpk mínimo", "cpk")
        crit.addItem("Spec + Cpk mínimo", "both")
        crit.setCurrentIndex(max(0, crit.findData(rv.criterion)))
        crit.currentIndexChanged.connect(lambda _=0, rv=rv, w=crit: self._set(rv, "criterion", w.currentData()))
        self.tbl_var.setCellWidget(i, 1, crit)
        sp = QDoubleSpinBox()
        sp.setRange(0, 10)
        sp.setDecimals(2)
        sp.setValue(rv.cpk_min)
        sp.valueChanged.connect(lambda v, rv=rv: self._set(rv, "cpk_min", v))
        self.tbl_var.setCellWidget(i, 2, sp)
        for col, attr in ((3, "chart"), (4, "events"), (5, "csv")):
            chk = QCheckBox()
            chk.setChecked(getattr(rv, attr))
            chk.toggled.connect(lambda on, rv=rv, attr=attr: self._set(rv, attr, on))
            self.tbl_var.setCellWidget(i, col, chk)

    def _add_trigger(self) -> None:
        if self.report is None:
            self._new()
        self.report.triggers.append(ReportTrigger(kind="tour"))
        self.refresh()

    def _add_var(self) -> None:
        vid = self.cmb_add_var.currentData()
        if not vid:
            return
        if self.report is None:
            self._new()
        if any(rv.var_id == vid for rv in self.report.variables):
            return
        var = self.dlg.config.variable(vid)
        self.report.variables.append(ReportVar(var_id=vid, chart=var.kind not in ("text", "selector")))
        self.refresh()

    def _remove_row(self, table: QTableWidget, items: Optional[list]) -> None:
        i = table.currentRow()
        if items is None or not (0 <= i < len(items)):
            return
        items.pop(i)
        self.refresh()

    def _browse(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "Carpeta de reportes", self.ed_dir.text() or
                                             self.ed_dir.placeholderText())
        if d:
            self.ed_dir.setText(d)
            self._commit()

    def _out_dir(self) -> Path:
        return Path(self.ed_dir.text().strip() or self.ed_dir.placeholderText())

    def _open_dir(self) -> None:
        d = self._out_dir()
        d.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(d)))

    def _commit(self) -> None:
        r = self.report
        if r is None or self._loading:
            return
        r.name = self.ed_name.text().strip() or r.name
        r.enabled = self.chk_enabled.isChecked()
        r.min_interval_s = self.sp_min.value()
        r.max_period_h = self.sp_max.value()
        r.reset_analysis = self.chk_reset.isChecked()
        r.include_general_events = self.chk_general.isChecked()
        r.export_csv = self.chk_csv.isChecked()
        r.name_var = self.cmb_name.currentData()
        r.output_dir = self.ed_dir.text().strip() or None
        r.behavior_models = [self.lst_beh.item(i).data(Qt.UserRole) for i in range(self.lst_beh.count())
                             if self.lst_beh.item(i).checkState() == Qt.Checked]
        i = self.cmb_rep.currentIndex()
        if i >= 0 and self.cmb_rep.itemText(i) != r.name:
            self.cmb_rep.setItemText(i, r.name)

    def commit(self) -> list[str]:
        self._commit()
        return [f"Reporte «{r.name}»: no tiene variables" for r in self.dlg.config.reports
                if r.enabled and not r.variables]

    # --- vista previa -----------------------------------------------------------------
    def _preview(self) -> None:
        from ..reports import ReportJob, generate
        self._commit()
        r = self.report
        engine = self.dlg.ctx.engine
        if r is None or not r.variables or engine.historian is None:
            QMessageBox.information(self, "Reporte", "Agrega al menos una variable al reporte.")
            return
        now = time.time()
        since = engine.reports.last_end(r.id) or now - r.max_period_h * 3600
        snap = engine.last
        limits = engine._report_limits(snap) if snap is not None else {}
        models = [m for mid in r.behavior_models if (m := engine.behaviors.store.get(mid)) is not None and m.trained]
        job = ReportJob(r, self.dlg.config, max(since, now - r.max_period_h * 3600), now, "vista previa",
                        engine.state.recipe, limits, models, "vista_previa_" + time.strftime("%Y%m%d_%H%M%S"),
                        self._out_dir())
        try:
            out = generate(job, engine.historian)
        except Exception as exc:
            QMessageBox.warning(self, "Reporte", f"No se pudo generar: {exc}")
            return
        self.lbl_status.setText(f"Generado: {out.pdf}")
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(out.pdf)))
