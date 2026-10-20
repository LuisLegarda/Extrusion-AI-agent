"""Configuración → Personal: alta y baja de operadores y supervisores de la estación."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QHBoxLayout, QHeaderView, QLabel, QPushButton, QTableWidget,
    QTableWidgetItem, QVBoxLayout,
)

from ..i18n import tr
from ..personnel import ROLES, Person, Personnel

COLS = ("Nombre", "Puesto", "Núm. de empleado", "Activo")


class PersonnelDialog(QDialog):
    def __init__(self, home: Path, recipe_operators=(), parent=None):
        super().__init__(parent)
        self.setWindowTitle("Personal (operadores y supervisores)")
        self.resize(640, 480)
        self.home = Path(home)
        root = QVBoxLayout(self)
        intro = QLabel("Las personas de esta estación. Aparecen en la barra superior (quién está en turno) y al "
                       "capturar paros y defectos. Son de este equipo, no de la receta; una persona inactiva se "
                       "conserva en las capturas anteriores pero ya no aparece en las listas.")
        intro.setWordWrap(True)
        root.addWidget(intro)
        self.table = QTableWidget(0, len(COLS))
        self.table.setHorizontalHeaderLabels([tr(c) for c in COLS])
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.Stretch)
        for i in (1, 2, 3):
            hh.setSectionResizeMode(i, QHeaderView.ResizeToContents)
        self.table.verticalHeader().setVisible(False)
        root.addWidget(self.table, 1)
        people = Personnel.load(home).people
        known = {p.name for p in people}
        # La lista anterior (por receta) se ofrece como punto de partida
        people += [Person(n) for n in recipe_operators if n and n not in known]
        for p in people:
            self.add_person(p)
        row = QHBoxLayout()
        for text, slot in (("+ Operador", lambda: self._new("operator")), ("+ Supervisor", lambda: self._new("supervisor")),
                           ("Quitar", self._remove)):
            b = QPushButton(text)
            b.clicked.connect(slot)
            row.addWidget(b)
        row.addStretch(1)
        root.addLayout(row)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText("Guardar")
        bb.button(QDialogButtonBox.Cancel).setText("Cancelar")
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        root.addWidget(bb)

    def add_person(self, p: Person) -> int:
        r = self.table.rowCount()
        self.table.insertRow(r)
        self.table.setItem(r, 0, QTableWidgetItem(p.name))
        cmb = QComboBox()
        for key, label in ROLES.items():
            cmb.addItem(tr(label), key)
        cmb.setCurrentIndex(max(0, cmb.findData(p.role)))
        self.table.setCellWidget(r, 1, cmb)
        self.table.setItem(r, 2, QTableWidgetItem(p.badge))
        act = QTableWidgetItem()
        act.setFlags(Qt.ItemIsEnabled | Qt.ItemIsUserCheckable)
        act.setCheckState(Qt.Checked if p.active else Qt.Unchecked)
        self.table.setItem(r, 3, act)
        return r

    def _new(self, role: str) -> None:
        r = self.add_person(Person(tr("Nuevo supervisor") if role == "supervisor" else tr("Nuevo operador"), role))
        self.table.setCurrentCell(r, 0)
        self.table.editItem(self.table.item(r, 0))

    def _remove(self) -> None:
        r = self.table.currentRow()
        if r >= 0:
            self.table.removeRow(r)

    def personnel(self) -> Personnel:
        out, seen = [], set()
        for r in range(self.table.rowCount()):
            name = (self.table.item(r, 0).text() if self.table.item(r, 0) else "").strip()
            if not name or name in seen:
                continue
            seen.add(name)
            badge = self.table.item(r, 2)
            out.append(Person(name, self.table.cellWidget(r, 1).currentData(),
                              badge.text().strip() if badge else "",
                              self.table.item(r, 3).checkState() == Qt.Checked))
        return Personnel(out)

    def accept(self) -> None:
        self.personnel().save(self.home)
        super().accept()
