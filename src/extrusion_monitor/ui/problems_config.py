"""Receta → Causas de paro y defectos: catálogos de dos niveles (categoría → causa) y lista de operadores."""
from __future__ import annotations

import re
import uuid
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QFormLayout, QHBoxLayout, QLabel, QListWidget,
    QListWidgetItem, QPushButton, QTabWidget, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
)

from ..config import ProblemCategory, ProblemReason, ProblemSettings
from ..i18n import tr

ROLE = Qt.UserRole


def _new_id(prefix: str, name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")[:20] or prefix
    return f"{slug}_{uuid.uuid4().hex[:4]}"


class CatalogTree(QWidget):
    """Árbol editable: categorías (con «planeado» si aplica) y sus causas o defectos."""

    def __init__(self, cats: list[ProblemCategory], planned: bool, cat_label: str, item_label: str, parent=None):
        super().__init__(parent)
        self.planned = planned
        self.item_label = item_label
        lay = QVBoxLayout(self)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels([tr("Nombre"), tr("Paro planeado") if planned else ""])
        self.tree.setColumnWidth(0, 360)
        if not planned:
            self.tree.setColumnHidden(1, True)
        self.tree.setEditTriggers(QTreeWidget.DoubleClicked | QTreeWidget.EditKeyPressed | QTreeWidget.SelectedClicked)
        lay.addWidget(self.tree)
        row = QHBoxLayout()
        for text, slot in ((f"+ {cat_label}", self._add_cat), (f"+ {item_label}", self._add_item),
                           ("Quitar", self._remove), ("▲", lambda: self._move(-1)), ("▼", lambda: self._move(1))):
            b = QPushButton(text)
            b.clicked.connect(slot)
            row.addWidget(b)
        lay.addLayout(row)
        hint = tr("Doble clic para cambiar un nombre.")
        if planned:
            hint += " " + tr("Los paros planeados (cambio de producto, comida…) no cuentan contra la "
                             "Disponibilidad del OEE.")
        lb = QLabel(hint)
        lb.setWordWrap(True)
        lay.addWidget(lb)
        for c in cats:
            self._cat_item(c)
        self.tree.expandAll()

    def _cat_item(self, c: ProblemCategory) -> QTreeWidgetItem:
        it = QTreeWidgetItem([c.name, ""])
        it.setData(0, ROLE, ("cat", c.id))
        it.setFlags(it.flags() | Qt.ItemIsEditable)
        f = it.font(0)
        f.setBold(True)
        it.setFont(0, f)
        if self.planned:
            it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
            it.setCheckState(1, Qt.Checked if c.planned else Qt.Unchecked)
        self.tree.addTopLevelItem(it)
        for r in c.reasons:
            self._reason_item(it, r)
        return it

    def _reason_item(self, parent: QTreeWidgetItem, r: ProblemReason) -> QTreeWidgetItem:
        it = QTreeWidgetItem([r.name])
        it.setData(0, ROLE, ("reason", r.id))
        it.setFlags(it.flags() | Qt.ItemIsEditable)
        parent.addChild(it)
        return it

    def _current_cat(self) -> Optional[QTreeWidgetItem]:
        it = self.tree.currentItem()
        if it is None:
            return None
        return it if it.parent() is None else it.parent()

    def _add_cat(self) -> None:
        name = tr("Nueva categoría")
        it = self._cat_item(ProblemCategory(id=_new_id("cat", name), name=name))
        self.tree.setCurrentItem(it)
        self.tree.editItem(it, 0)

    def _add_item(self) -> None:
        cat = self._current_cat()
        if cat is None:
            if self.tree.topLevelItemCount() == 0:
                self._add_cat()
            cat = self.tree.topLevelItem(self.tree.topLevelItemCount() - 1)
        name = tr("Nueva causa") if self.planned else tr("Nuevo defecto")
        it = self._reason_item(cat, ProblemReason(id=_new_id("r", name), name=name))
        cat.setExpanded(True)
        self.tree.setCurrentItem(it)
        self.tree.editItem(it, 0)

    def _remove(self) -> None:
        it = self.tree.currentItem()
        if it is None:
            return
        (it.parent() or self.tree.invisibleRootItem()).removeChild(it)

    def _move(self, d: int) -> None:
        it = self.tree.currentItem()
        if it is None:
            return
        parent = it.parent() or self.tree.invisibleRootItem()
        i = parent.indexOfChild(it)
        j = i + d
        if not 0 <= j < parent.childCount():
            return
        expanded = it.isExpanded()
        parent.takeChild(i)
        parent.insertChild(j, it)
        it.setExpanded(expanded)
        self.tree.setCurrentItem(it)

    def categories(self) -> list[ProblemCategory]:
        out = []
        for i in range(self.tree.topLevelItemCount()):
            c = self.tree.topLevelItem(i)
            name = c.text(0).strip()
            if not name:
                continue
            reasons = []
            for k in range(c.childCount()):
                r = c.child(k)
                if r.text(0).strip():
                    reasons.append(ProblemReason(id=r.data(0, ROLE)[1], name=r.text(0).strip()))
            out.append(ProblemCategory(id=c.data(0, ROLE)[1], name=name, reasons=reasons,
                                       planned=self.planned and c.checkState(1) == Qt.Checked))
        return out


class ProblemsConfigDialog(QDialog):
    def __init__(self, settings: ProblemSettings, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Causas de paro y defectos")
        self.resize(720, 620)
        root = QVBoxLayout(self)
        intro = QLabel("Catálogos que el operador usa para clasificar los paros y los problemas de calidad. Se guardan "
                       "con la receta activa. Cambiar un nombre no altera las capturas ya hechas.")
        intro.setWordWrap(True)
        root.addWidget(intro)
        tabs = QTabWidget()
        self.down = CatalogTree(settings.downtime, True, tr("Categoría"), tr("Causa"))
        self.defects = CatalogTree(settings.defects, False, tr("Categoría"), tr("Defecto"))
        tabs.addTab(self.down, "⏸ Causas de paro")
        tabs.addTab(self.defects, "✗ Defectos de calidad")
        ops = QWidget()
        ol = QVBoxLayout(ops)
        ol.addWidget(QLabel("Operadores que pueden capturar (aparecen en una lista al capturar):"))
        self.lst_ops = QListWidget()
        for name in settings.operators:
            self._op_item(name)
        ol.addWidget(self.lst_ops)
        row = QHBoxLayout()
        for text, slot in (("+ Operador", self._add_op), ("Quitar", self._del_op)):
            b = QPushButton(text)
            b.clicked.connect(slot)
            row.addWidget(b)
        row.addStretch()
        ol.addLayout(row)
        form = QFormLayout()
        self.chk_prompt = QCheckBox("Al reanudar la línea, avisar para clasificar el paro")
        self.chk_prompt.setChecked(settings.prompt)
        form.addRow(self.chk_prompt)
        self.sp_min = QDoubleSpinBox()
        self.sp_min.setRange(0, 1440)
        self.sp_min.setSuffix(" min")
        self.sp_min.setValue(settings.prompt_min_s / 60)
        form.addRow("Solo paros de al menos", self.sp_min)
        ol.addLayout(form)
        tabs.addTab(ops, "👷 Operadores y aviso")
        root.addWidget(tabs)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText("Guardar")
        bb.button(QDialogButtonBox.Cancel).setText("Cancelar")
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        root.addWidget(bb)

    def _op_item(self, name: str) -> None:
        it = QListWidgetItem(name)
        it.setFlags(it.flags() | Qt.ItemIsEditable)
        self.lst_ops.addItem(it)

    def _add_op(self) -> None:
        self._op_item(tr("Nuevo operador"))
        it = self.lst_ops.item(self.lst_ops.count() - 1)
        self.lst_ops.setCurrentItem(it)
        self.lst_ops.editItem(it)

    def _del_op(self) -> None:
        row = self.lst_ops.currentRow()
        if row >= 0:
            self.lst_ops.takeItem(row)

    def settings(self) -> ProblemSettings:
        ops = [self.lst_ops.item(i).text().strip() for i in range(self.lst_ops.count())]
        return ProblemSettings(downtime=self.down.categories(), defects=self.defects.categories(),
                               operators=[o for o in dict.fromkeys(ops) if o], prompt=self.chk_prompt.isChecked(),
                               prompt_min_s=self.sp_min.value() * 60)
