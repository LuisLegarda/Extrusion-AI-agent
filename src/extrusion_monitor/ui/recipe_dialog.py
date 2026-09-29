"""Editor de recetas: nominales y tolerancias por variable."""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QHBoxLayout, QHeaderView,
    QInputDialog, QLabel, QLineEdit, QListWidget, QMessageBox, QPushButton, QSplitter, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)

from ..bootstrap import AppContext
from ..recipes import Limit, Recipe, recipe_from_csv, recipe_to_csv

COLS = ["Variable", "Tipo", "Nominal", "Modo", "Aviso ±", "Alarma ±", "Aviso mín", "Aviso máx", "Alarma mín",
        "Alarma máx", "Comparar contra"]
C_VAR, C_KIND, C_NOM, C_MODE, C_WARN, C_ALARM, C_WMIN, C_WMAX, C_AMIN, C_AMAX, C_REF = range(11)
PM_COLS = (C_WARN, C_ALARM)
RANGE_COLS = (C_WMIN, C_WMAX, C_AMIN, C_AMAX)
NUM_FIELDS = {C_NOM: "nominal", C_WARN: "warn", C_ALARM: "alarm", C_WMIN: "warn_min", C_WMAX: "warn_max",
              C_AMIN: "alarm_min", C_AMAX: "alarm_max"}
KIND_TEXT = {"actual": "real", "setpoint": "consigna", "selector": "selector"}


def _num(text: str) -> Optional[float]:
    text = text.strip().replace(",", ".")
    return float(text) if text else None


class RecipeDialog(QDialog):
    def __init__(self, ctx: AppContext, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Recetas")
        self.resize(1100, 700)
        self.ctx = ctx
        self.recipes: dict[str, Recipe] = {n: ctx.recipes.get(n).model_copy(deep=True)
                                           for n in ctx.recipes.names()}
        self.deleted: set[str] = set()
        # Perfiles a crear al guardar: receta -> receta de la que se copia (None = configuración actual)
        self.profile_from: dict[str, Optional[str]] = {}
        self.current: Optional[str] = None
        self._build()
        self._refresh_list()

    def _build(self) -> None:
        root = QVBoxLayout(self)
        split = QSplitter(Qt.Horizontal)
        left = QWidget()
        ll = QVBoxLayout(left)
        self.lst = QListWidget()
        self.lst.currentTextChanged.connect(self._select)
        ll.addWidget(self.lst)
        for text, slot in (("Nueva", self._new), ("Duplicar", self._duplicate), ("Renombrar", self._rename),
                           ("Eliminar", self._delete), ("Importar CSV…", self._import), ("Exportar CSV…", self._export)):
            b = QPushButton(text)
            b.clicked.connect(slot)
            ll.addWidget(b)
        split.addWidget(left)

        right = QWidget()
        rl = QVBoxLayout(right)
        form = QFormLayout()
        self.ed_desc = QLineEdit()
        self.ed_meta = QLineEdit()
        self.ed_meta.setPlaceholderText("calibre=12 AWG; material=PVC; color=negro")
        form.addRow("Descripción", self.ed_desc)
        form.addRow("Datos del producto", self.ed_meta)
        rl.addLayout(form)
        hint = QLabel("Modo <b>±</b>: nominal y tolerancias de aviso/alarma (en unidades o en %). "
                      "Modo <b>mín / máx</b>: límites absolutos; deja vacío un lado para un límite de un solo lado "
                      "(p. ej. solo máximo). Sin nominal ni límites la variable no se verifica. "
                      "«Comparar contra consigna» evalúa el valor real frente a la consigna leída del HMI (modo ±).")
        hint.setWordWrap(True)
        rl.addWidget(hint)
        self.table = QTableWidget(0, len(COLS))
        self.table.setHorizontalHeaderLabels(COLS)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(C_VAR, QHeaderView.Stretch)
        rl.addWidget(self.table)
        row = QHBoxLayout()
        b = QPushButton("Tomar valores actuales del HMI como nominales")
        b.clicked.connect(self._from_live)
        row.addWidget(b)
        b = QPushButton("📦 Guardar la configuración actual en esta receta")
        b.setToolTip("La receta guarda todo: variables, pantallas, recorridos, OEE, reportes y comportamientos. "
                     "Al cargarla se restaura esa configuración.")
        b.clicked.connect(self._snapshot)
        row.addWidget(b)
        row.addStretch()
        rl.addLayout(row)
        split.addWidget(right)
        split.setSizes([260, 840])
        root.addWidget(split)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Save).setText("Guardar")
        buttons.button(QDialogButtonBox.Cancel).setText("Cancelar")
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def _refresh_list(self, select: Optional[str] = None) -> None:
        self.lst.blockSignals(True)
        self.lst.clear()
        for n in sorted(self.recipes):
            self.lst.addItem(n)
        self.lst.blockSignals(False)
        target = select or self.current or (sorted(self.recipes)[0] if self.recipes else None)
        items = self.lst.findItems(target, Qt.MatchExactly) if target else []
        self.current = None
        if items:
            self.lst.setCurrentItem(items[0])
        else:
            self._select("")

    def _numeric_vars(self):
        return [v for v in self.ctx.config.variables if v.kind != "text"]

    def _select(self, name: str) -> None:
        self._commit()
        self.current = name or None
        recipe = self.recipes.get(name) if name else None
        self.table.setRowCount(0)
        self.ed_desc.setText(recipe.description if recipe else "")
        self.ed_meta.setText("; ".join(f"{k}={v}" for k, v in recipe.meta.items()) if recipe else "")
        if recipe is None:
            return
        for row, var in enumerate(self._numeric_vars()):
            lim = recipe.limits.get(var.id, Limit())
            self.table.insertRow(row)
            it = QTableWidgetItem(f"{var.name} [{var.unit}]" if var.unit else var.name)
            it.setFlags(Qt.ItemIsEnabled)
            it.setData(Qt.UserRole, var.id)
            self.table.setItem(row, C_VAR, it)
            it = QTableWidgetItem(KIND_TEXT.get(var.kind, var.kind))
            it.setFlags(Qt.ItemIsEnabled)
            self.table.setItem(row, C_KIND, it)
            if var.kind == "selector":
                exp = QComboBox()
                exp.addItem("— no verificar —", None)
                for st in var.states:
                    exp.addItem(f"esperado: {st}", st)
                exp.setCurrentIndex(max(0, exp.findData(lim.expected)))
                self.table.setCellWidget(row, C_NOM, exp)
                for c in range(C_MODE, len(COLS)):
                    cell = QTableWidgetItem("")
                    cell.setFlags(Qt.ItemIsEnabled)
                    self.table.setItem(row, c, cell)
                continue
            for c, attr in NUM_FIELDS.items():
                val = getattr(lim, attr)
                cell = QTableWidgetItem("" if val is None else f"{val:g}")
                cell.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.table.setItem(row, c, cell)
            mode = QComboBox()
            mode.addItem("± absoluta", "abs")
            mode.addItem("± % de la referencia", "pct")
            mode.addItem("mín / máx", "range")
            mode.setCurrentIndex(max(0, mode.findData(lim.mode)))
            mode.currentIndexChanged.connect(lambda _=0, r=row: self._mode_changed(r))
            self.table.setCellWidget(row, C_MODE, mode)
            ref = QComboBox()
            ref.addItem("receta", "recipe")
            if var.kind == "actual" and var.setpoint_var:
                ref.addItem("consigna del HMI", "setpoint")
            ref.setCurrentIndex(max(0, ref.findData(lim.reference)))
            self.table.setCellWidget(row, C_REF, ref)
            self._mode_changed(row)

    def _mode_changed(self, row: int) -> None:
        """Habilita las columnas del modo elegido (± o mín/máx) y atenúa las otras."""
        mode = self.table.cellWidget(row, C_MODE)
        if mode is None:
            return
        is_range = mode.currentData() == "range"
        for cols, on in ((PM_COLS, not is_range), (RANGE_COLS, is_range)):
            for c in cols:
                it = self.table.item(row, c)
                if it is None:
                    continue
                flags = Qt.ItemIsEnabled | Qt.ItemIsSelectable | (Qt.ItemIsEditable if on else Qt.NoItemFlags)
                it.setFlags(flags)
                it.setForeground(QBrush(QColor("#000000" if on else "#b0b0b0")))
        ref = self.table.cellWidget(row, C_REF)
        if ref is not None:
            ref.setEnabled(not is_range)

    def _commit(self) -> bool:
        recipe = self.recipes.get(self.current) if self.current else None
        if recipe is None:
            return True
        recipe.description = self.ed_desc.text().strip()
        meta = {}
        for part in self.ed_meta.text().split(";"):
            if "=" in part:
                k, v = part.split("=", 1)
                if k.strip():
                    meta[k.strip()] = v.strip()
        recipe.meta = meta
        limits: dict[str, Limit] = {}
        for row in range(self.table.rowCount()):
            vid = self.table.item(row, C_VAR).data(Qt.UserRole)
            var = self.ctx.config.variable(vid)
            if var is not None and var.kind == "selector":
                expected = self.table.cellWidget(row, C_NOM).currentData()
                if expected:
                    limits[vid] = Limit(expected=expected)
                continue
            try:
                vals = {attr: _num(self.table.item(row, c).text()) for c, attr in NUM_FIELDS.items()}
                lim = Limit(**vals, mode=self.table.cellWidget(row, C_MODE).currentData(),
                            reference=self.table.cellWidget(row, C_REF).currentData())
            except ValueError as exc:
                QMessageBox.warning(self, "Valor inválido",
                                    f"{self.table.item(row, C_VAR).text()}: {exc}")
                return False
            problem = lim.check()
            if problem:
                QMessageBox.warning(self, "Tolerancias", f"{self.table.item(row, C_VAR).text()}: {problem}.")
                return False
            if lim.active:
                limits[vid] = lim
        # Conserva límites de variables que no están en la configuración actual.
        known = {v.id for v in self._numeric_vars()}
        limits.update({k: v for k, v in recipe.limits.items() if k not in known})
        recipe.limits = limits
        return True

    def _ask_name(self, title: str, default: str = "") -> Optional[str]:
        name, ok = QInputDialog.getText(self, title, "Nombre de la receta (igual al que muestra el HMI):",
                                        text=default)
        name = name.strip()
        if not ok or not name:
            return None
        if name in self.recipes:
            QMessageBox.warning(self, "Nombre en uso", f"Ya existe la receta «{name}».")
            return None
        return name

    def _new(self) -> None:
        name = self._ask_name("Nueva receta")
        if name:
            self._commit()
            self.recipes[name] = Recipe(name=name)
            self.profile_from[name] = None
            self.deleted.discard(name)
            self._refresh_list(name)

    def _duplicate(self) -> None:
        if not self.current or not self._commit():
            return
        name = self._ask_name("Duplicar receta", self.current + " copia")
        if name:
            copy = self.recipes[self.current].model_copy(deep=True)
            copy.name = name
            self.recipes[name] = copy
            self.profile_from[name] = self.profile_from.get(self.current, self.current)
            self.deleted.discard(name)
            self._refresh_list(name)

    def _rename(self) -> None:
        if not self.current or not self._commit():
            return
        name = self._ask_name("Renombrar receta", self.current)
        if name:
            r = self.recipes.pop(self.current)
            self.deleted.add(self.current)
            self.profile_from[name] = self.profile_from.pop(self.current, self.current)
            r.name = name
            self.recipes[name] = r
            self.current = None
            self._refresh_list(name)

    def _delete(self) -> None:
        if not self.current:
            return
        if QMessageBox.question(self, "Eliminar", f"¿Eliminar la receta «{self.current}»?") != QMessageBox.Yes:
            return
        self.recipes.pop(self.current, None)
        self.deleted.add(self.current)
        self.current = None
        self._refresh_list()

    def _import(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Importar receta", "", "CSV (*.csv)")
        if not path:
            return
        name = self._ask_name("Importar receta", Path(path).stem)
        if not name:
            return
        try:
            text = Path(path).read_text(encoding="utf-8-sig")
            recipe = recipe_from_csv(name, text)
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, "Error al importar", str(exc))
            return
        self._commit()
        self.recipes[name] = recipe
        self.profile_from[name] = None
        self.deleted.discard(name)
        self._refresh_list(name)

    def _export(self) -> None:
        if not self.current or not self._commit():
            return
        path, _ = QFileDialog.getSaveFileName(self, "Exportar receta", f"{self.current}.csv", "CSV (*.csv)")
        if path:
            Path(path).write_text(recipe_to_csv(self.recipes[self.current]), encoding="utf-8-sig")

    def _snapshot(self) -> None:
        if not self.current:
            return
        self.profile_from[self.current] = None
        QMessageBox.information(self, "Configuración", f"Al guardar, «{self.current}» tendrá la configuración "
                                "actual completa (variables, pantallas, recorridos, OEE, reportes y comportamientos).")

    def _from_live(self) -> None:
        snap = self.ctx.engine.last
        if snap is None or not self.current:
            QMessageBox.information(self, "Sin datos", "Inicia el monitoreo para tener valores actuales.")
            return
        for row in range(self.table.rowCount()):
            vid = self.table.item(row, C_VAR).data(Qt.UserRole)
            st = snap.statuses.get(vid)
            if st and st.var.kind == "selector":
                combo = self.table.cellWidget(row, C_NOM)
                if st.fresh and st.reading.text:
                    combo.setCurrentIndex(max(0, combo.findData(st.reading.text)))
            elif st and st.reading.value is not None and st.fresh:
                self.table.item(row, C_NOM).setText(f"{st.reading.value:g}")

    def _save(self) -> None:
        if not self._commit():
            return
        from .. import profiles
        ws = self.ctx.workspace
        # Primero se copian los perfiles (renombrar/duplicar usan el perfil de origen) y luego se borran.
        for name, src in self.profile_from.items():
            if name not in self.recipes:
                continue
            if src is not None and profiles.has_profile(ws, src):
                profiles.copy_profile(ws, src, name)
            else:
                profiles.save_profile(ws, name, self.ctx.config)
        store = self.ctx.recipes
        for name in self.deleted:
            if name not in self.recipes:
                store.delete(name)
        for recipe in self.recipes.values():
            store.save(recipe)
            if not profiles.has_profile(ws, recipe.name):
                profiles.save_profile(ws, recipe.name, self.ctx.config)
        self.accept()
