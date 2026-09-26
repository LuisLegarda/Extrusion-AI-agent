"""Entrenamiento de comportamiento normal (variación y correlación entre variables)."""
from __future__ import annotations

import time
import uuid
from typing import Optional

import numpy as np
from PySide6.QtCore import QDateTime, Qt
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDateTimeEdit, QDialog, QDialogButtonBox, QDoubleSpinBox, QFormLayout, QGroupBox,
    QHBoxLayout, QHeaderView, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMessageBox, QPushButton,
    QRadioButton, QSpinBox, QSplitter, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from ..analysis.behavior import BehaviorModel, TrainingError, train
from ..bootstrap import AppContext
from ..config import AppConfig


def corr_color(r: float) -> QColor:
    """Azul (negativa) → blanco → rojo (positiva)."""
    r = max(-1.0, min(1.0, r))
    if r >= 0:
        return QColor(255, int(255 * (1 - r)), int(255 * (1 - r)))
    return QColor(int(255 * (1 + r)), int(255 * (1 + r)), 255)


def fill_corr_table(table: QTableWidget, labels: list[str], corr) -> None:
    n = len(labels)
    table.clear()
    table.setRowCount(n)
    table.setColumnCount(n)
    short = [lb.split(" › ")[-1] for lb in labels]
    table.setHorizontalHeaderLabels(short)
    table.setVerticalHeaderLabels(short)
    for i in range(n):
        for j in range(n):
            r = float(corr[i][j]) if corr is not None and not np.isnan(corr[i][j]) else 0.0
            it = QTableWidgetItem(f"{r:+.2f}")
            it.setTextAlignment(Qt.AlignCenter)
            it.setBackground(QBrush(corr_color(r)))
            it.setForeground(QBrush(QColor("black")))
            it.setToolTip(f"{labels[i]} ↔ {labels[j]}: r = {r:+.2f}")
            table.setItem(i, j, it)
    table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)


class BehaviorDialog(QDialog):
    def __init__(self, ctx: AppContext, parent=None, preselect: Optional[list[str]] = None,
                 config: Optional[AppConfig] = None):
        super().__init__(parent)
        self.setWindowTitle("Entrenar comportamiento normal")
        self.resize(1250, 780)
        self.ctx = ctx
        self.config = config or ctx.config
        self.store = ctx.engine.behaviors.store
        self.store.load()
        self.current: Optional[BehaviorModel] = None
        self._build()
        self._refresh_models()
        if preselect or not self.store.models:
            self._new(preselect or [])
        else:
            self.lst_models.setCurrentRow(0)

    # --- construcción -----------------------------------------------------------------
    def _build(self) -> None:
        root = QVBoxLayout(self)
        intro = QLabel(
            "Elige un periodo en que el proceso trabajó bien. La app aprende la <b>variación normal</b> de cada "
            "variable y, si eliges 2 o más, <b>cómo se mueven juntas</b> (correlación). En vivo avisa cuando "
            "una variable o una relación entre ellas se sale de lo aprendido, aunque siga dentro de tolerancia.")
        intro.setWordWrap(True)
        root.addWidget(intro)
        split = QSplitter(Qt.Horizontal)

        left = QWidget()
        ll = QVBoxLayout(left)
        ll.addWidget(QLabel("Modelos"))
        self.lst_models = QListWidget()
        self.lst_models.currentRowChanged.connect(self._model_selected)
        ll.addWidget(self.lst_models)
        row = QHBoxLayout()
        for text, slot in (("Nuevo", lambda: self._new([])), ("Eliminar", self._delete)):
            b = QPushButton(text)
            b.clicked.connect(slot)
            row.addWidget(b)
        ll.addLayout(row)
        split.addWidget(left)

        mid = QWidget()
        ml = QVBoxLayout(mid)
        form = QFormLayout()
        self.ed_name = QLineEdit()
        form.addRow("Nombre", self.ed_name)
        self.chk_enabled = QCheckBox("Activo (evaluar en el monitoreo)")
        form.addRow("", self.chk_enabled)
        ml.addLayout(form)
        ml.addWidget(QLabel("Variables de referencia"))
        self.lst_vars = QListWidget()
        ml.addWidget(self.lst_vars, 1)

        period = QGroupBox("Periodo de entrenamiento (del historial)")
        pf = QFormLayout(period)
        self.rb_last = QRadioButton("Últimos")
        self.rb_last.setChecked(True)
        row = QHBoxLayout()
        self.sp_last = QSpinBox()
        self.sp_last.setRange(1, 100000)
        self.sp_last.setValue(60)
        self.cmb_unit = QComboBox()
        self.cmb_unit.addItem("minutos", 60)
        self.cmb_unit.addItem("horas", 3600)
        self.cmb_unit.addItem("días", 86400)
        row.addWidget(self.sp_last)
        row.addWidget(self.cmb_unit)
        pf.addRow(self.rb_last, row)
        self.rb_range = QRadioButton("Rango")
        row = QHBoxLayout()
        now = QDateTime.currentDateTime()
        self.dt_from = QDateTimeEdit(now.addSecs(-3600))
        self.dt_to = QDateTimeEdit(now)
        for d in (self.dt_from, self.dt_to):
            d.setCalendarPopup(True)
            d.setDisplayFormat("dd/MM/yyyy HH:mm")
            row.addWidget(d)
        pf.addRow(self.rb_range, row)
        self.sp_step = QDoubleSpinBox()
        self.sp_step.setRange(1, 3600)
        self.sp_step.setValue(10)
        self.sp_step.setSuffix(" s")
        pf.addRow("Resolución", self.sp_step)
        ml.addWidget(period)

        sens = QGroupBox("Sensibilidad")
        sf = QFormLayout(sens)
        self.sp_sens = QDoubleSpinBox()
        self.sp_sens.setRange(0.3, 5.0)
        self.sp_sens.setSingleStep(0.1)
        self.sp_sens.setToolTip("1 = umbral aprendido; mayor = menos avisos; menor = más sensible")
        sf.addRow("Margen del umbral", self.sp_sens)
        self.sp_z = QDoubleSpinBox()
        self.sp_z.setRange(1.5, 10)
        self.sp_z.setSingleStep(0.5)
        self.sp_z.setSuffix(" σ")
        sf.addRow("Variación normal por variable", self.sp_z)
        self.chk_recipe = QCheckBox()
        sf.addRow("Solo con la receta", self.chk_recipe)
        ml.addWidget(sens)
        b = QPushButton("🧠 Entrenar")
        b.clicked.connect(self._train)
        ml.addWidget(b)
        split.addWidget(mid)

        right = QWidget()
        rl = QVBoxLayout(right)
        self.lbl_summary = QLabel("Sin entrenar")
        self.lbl_summary.setWordWrap(True)
        rl.addWidget(self.lbl_summary)
        rl.addWidget(QLabel("Variación normal aprendida"))
        self.tbl_stats = QTableWidget(0, 6)
        self.tbl_stats.setHorizontalHeaderLabels(["Variable", "Media", "σ", "Mín", "Máx", "Rango normal"])
        self.tbl_stats.verticalHeader().setVisible(False)
        self.tbl_stats.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.tbl_stats.setEditTriggers(QTableWidget.NoEditTriggers)
        rl.addWidget(self.tbl_stats, 1)
        rl.addWidget(QLabel("Correlación entre variables (rojo = suben juntas, azul = una sube y otra baja)"))
        self.tbl_corr = QTableWidget()
        self.tbl_corr.setEditTriggers(QTableWidget.NoEditTriggers)
        rl.addWidget(self.tbl_corr, 1)
        split.addWidget(right)
        split.setSizes([220, 460, 570])
        root.addWidget(split)

        bb = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Close)
        bb.button(QDialogButtonBox.Save).setText("Guardar modelo")
        bb.button(QDialogButtonBox.Close).setText("Cerrar")
        bb.accepted.connect(self._save)
        bb.rejected.connect(self.reject)
        root.addWidget(bb)

    # --- modelos ---------------------------------------------------------------------------
    def _refresh_models(self, select: Optional[str] = None) -> None:
        self.lst_models.blockSignals(True)
        self.lst_models.clear()
        for m in self.store.models:
            state = "entrenado" if m.trained else "sin entrenar"
            it = QListWidgetItem(f"{m.name}  ({len(m.variables)} var., {state})")
            it.setData(Qt.UserRole, m.id)
            self.lst_models.addItem(it)
        self.lst_models.blockSignals(False)
        if select:
            for i in range(self.lst_models.count()):
                if self.lst_models.item(i).data(Qt.UserRole) == select:
                    self.lst_models.setCurrentRow(i)

    def _label(self, vid: str) -> str:
        v = self.config.variable(vid)
        return self.config.var_label(v) if v else vid

    def _load(self, m: BehaviorModel) -> None:
        self.current = m
        self.ed_name.setText(m.name)
        self.chk_enabled.setChecked(m.enabled)
        self.lst_vars.clear()
        for v in self.config.variables:
            if not v.numeric:
                continue
            it = QListWidgetItem(self.config.var_label(v) + (f" [{v.unit}]" if v.unit else ""))
            it.setData(Qt.UserRole, v.id)
            it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
            it.setCheckState(Qt.Checked if v.id in m.variables else Qt.Unchecked)
            self.lst_vars.addItem(it)
        self.sp_sens.setValue(m.sensitivity)
        self.sp_z.setValue(m.z_limit)
        self.sp_step.setValue(m.step_s)
        recipe = m.recipe or self.ctx.engine.state.recipe
        self.chk_recipe.setText(recipe or "(no hay receta activa)")
        self.chk_recipe.setEnabled(bool(recipe))
        self.chk_recipe.setChecked(m.recipe is not None)
        if m.trained:
            self.rb_range.setChecked(True)
            self.dt_from.setDateTime(QDateTime.fromSecsSinceEpoch(int(m.trained_from)))
            self.dt_to.setDateTime(QDateTime.fromSecsSinceEpoch(int(m.trained_to)))
        self._show_results(m)

    def _model_selected(self, row: int) -> None:
        if row < 0:
            return
        m = self.store.get(self.lst_models.item(row).data(Qt.UserRole))
        if m:
            self._load(m.model_copy(deep=True))

    def _new(self, preselect: list[str]) -> None:
        self.lst_models.clearSelection()
        self._load(BehaviorModel(id=uuid.uuid4().hex[:10], name="Comportamiento normal", variables=preselect))
        self.rb_last.setChecked(True)

    def _delete(self) -> None:
        if self.current and self.store.get(self.current.id):
            if QMessageBox.question(self, "Eliminar", f"¿Eliminar el modelo «{self.current.name}»?") \
                    == QMessageBox.Yes:
                self.store.delete(self.current.id)
                self.ctx.engine.reload_behaviors()
                self._refresh_models()
                self._new([])

    def _commit(self) -> BehaviorModel:
        m = self.current
        m.name = self.ed_name.text().strip() or m.name
        m.enabled = self.chk_enabled.isChecked()
        m.sensitivity = self.sp_sens.value()
        m.z_limit = self.sp_z.value()
        m.recipe = self.chk_recipe.text() if self.chk_recipe.isChecked() and self.chk_recipe.isEnabled() else None
        chosen = [self.lst_vars.item(i).data(Qt.UserRole) for i in range(self.lst_vars.count())
                  if self.lst_vars.item(i).checkState() == Qt.Checked]
        if chosen != m.variables:
            m.variables = chosen
            m.n_samples = 0  # cambiar variables obliga a reentrenar
        return m

    # --- entrenamiento -----------------------------------------------------------------------
    def _period(self) -> tuple[float, float]:
        if self.rb_last.isChecked():
            end = time.time()
            return end - self.sp_last.value() * self.cmb_unit.currentData(), end
        return float(self.dt_from.dateTime().toSecsSinceEpoch()), float(self.dt_to.dateTime().toSecsSinceEpoch())

    def _train(self) -> None:
        m = self._commit()
        if not m.variables:
            QMessageBox.information(self, "Variables", "Marca al menos una variable.")
            return
        start, end = self._period()
        if end <= start:
            QMessageBox.warning(self, "Periodo", "El inicio debe ser anterior al fin.")
            return
        hist = self.ctx.engine.historian
        series = {}
        for vid in m.variables:
            rows = hist.samples(vid, start, end)
            series[vid] = (np.array([r[0] for r in rows], float), np.array([r[1] for r in rows], float))
        rules = self.ctx.engine.rules
        gap = max(rules.stale_limit(self.config.variable(v)) for v in m.variables if self.config.variable(v))
        try:
            train(m, series, start, end, self.sp_step.value(), gap)
        except TrainingError as exc:
            QMessageBox.warning(self, "No se pudo entrenar", str(exc))
            return
        self._show_results(m)

    def _show_results(self, m: BehaviorModel) -> None:
        if not m.trained:
            self.lbl_summary.setText("Sin entrenar: elige variables y periodo y pulsa «Entrenar».")
            self.tbl_stats.setRowCount(0)
            self.tbl_corr.clear()
            self.tbl_corr.setRowCount(0)
            self.tbl_corr.setColumnCount(0)
            return
        fmt = "%d/%m/%Y %H:%M"
        strong = []
        for i in range(len(m.variables)):
            for j in range(i + 1, len(m.variables)):
                r = m.corr[i][j]
                if abs(r) >= 0.6:
                    strong.append(f"{self._label(m.variables[i]).split(' › ')[-1]} ↔ "
                                  f"{self._label(m.variables[j]).split(' › ')[-1]} ({r:+.2f})")
        self.lbl_summary.setText(
            f"<b>Entrenado</b> con {m.n_samples} muestras del "
            f"{time.strftime(fmt, time.localtime(m.trained_from))} al "
            f"{time.strftime(fmt, time.localtime(m.trained_to))} (cada {m.step_s:g} s). "
            f"Umbral D² = {m.d2_threshold:.1f}."
            + (f"<br>Relaciones fuertes: {'; '.join(strong)}" if strong else
               ("<br>Sin relaciones fuertes entre las variables." if len(m.variables) > 1 else "")))
        self.tbl_stats.setRowCount(len(m.variables))
        for i, vid in enumerate(m.variables):
            lo, hi = m.mean[i] - m.z_limit * m.std[i], m.mean[i] + m.z_limit * m.std[i]
            vals = [self._label(vid), f"{m.mean[i]:.4g}", f"{m.std[i]:.3g}", f"{m.minimum[i]:.4g}",
                    f"{m.maximum[i]:.4g}", f"{lo:.4g} … {hi:.4g}"]
            for c, text in enumerate(vals):
                self.tbl_stats.setItem(i, c, QTableWidgetItem(text))
        fill_corr_table(self.tbl_corr, [self._label(v) for v in m.variables], m.corr)

    def _save(self) -> None:
        m = self._commit()
        if not m.trained:
            QMessageBox.information(self, "Sin entrenar", "Entrena el modelo antes de guardarlo.")
            return
        self.store.upsert(m.model_copy(deep=True))
        self.ctx.engine.reload_behaviors()
        self._refresh_models(m.id)
        self.lbl_summary.setText(self.lbl_summary.text() + "<br><b style='color:#43a047'>Guardado.</b>")
