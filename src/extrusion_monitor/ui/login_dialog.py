"""Quién entra: al empezar el turno (detectado por la hora) o al cambiar el usuario en la barra superior.

Según Configuración → Personal → Confirmación, pide el número de empleado y, si se eligió, la contraseña.
"""
from __future__ import annotations

from typing import Optional

from PySide6.QtWidgets import QComboBox, QDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton

from ..i18n import tr
from ..personnel import Personnel, Shift
from . import theme


class LoginDialog(QDialog):
    def __init__(self, personnel: Personnel, shift: Optional[Shift] = None, name: str = "", parent=None,
                 can_postpone: bool = False):
        super().__init__(parent)
        self.p = personnel
        self.shift = shift
        mode = personnel.login.confirm
        self.setWindowTitle(tr("Cambio de turno") if can_postpone else tr("Confirmar usuario"))
        self.setMinimumWidth(380)
        f = QFormLayout(self)
        head = (tr("Empieza el <b>{s}</b>. ¿Quién entra?", s=shift.label()) if can_postpone and shift
                else tr("Confirma quién está en turno."))
        lb = QLabel(head)
        lb.setWordWrap(True)
        f.addRow(lb)
        self.cmb = QComboBox()
        names = personnel.shift_people(shift) if shift is not None else personnel.names()
        if name and name not in names and personnel.find(name):
            names.insert(0, name)
        for n in names:
            person = personnel.find(n)
            self.cmb.addItem(f"{n} · {tr('Supervisor')}" if person and person.role == "supervisor" else n, n)
        self.cmb.setCurrentIndex(max(0, self.cmb.findData(name)))
        f.addRow(tr("Usuario"), self.cmb)
        self.ed_badge = QLineEdit()
        self.ed_badge.setPlaceholderText(tr("número de empleado"))
        self.ed_badge.textEdited.connect(self._badge_typed)
        self.ed_pw = QLineEdit()
        self.ed_pw.setEchoMode(QLineEdit.Password)
        if mode in ("badge", "badge_password"):
            f.addRow(tr("Núm. de empleado"), self.ed_badge)
        else:
            self.ed_badge.hide()
        if mode == "badge_password":
            f.addRow(tr("Contraseña"), self.ed_pw)
        else:
            self.ed_pw.hide()
        self.lbl = QLabel("")
        self.lbl.setWordWrap(True)
        self.lbl.setStyleSheet(f"color:{theme.c('critical')};")
        f.addRow(self.lbl)
        row = QHBoxLayout()
        row.addStretch(1)
        if can_postpone:
            later = QPushButton(tr("Más tarde"))
            later.clicked.connect(self.reject)
            row.addWidget(later)
        else:
            cancel = QPushButton(tr("Cancelar"))
            cancel.clicked.connect(self.reject)
            row.addWidget(cancel)
        ok = QPushButton(tr("Confirmar"))
        ok.setDefault(True)
        ok.clicked.connect(self.accept)
        row.addWidget(ok)
        f.addRow(row)
        if not names:
            self.lbl.setText(tr("No hay personal para este turno: agrégalo en Configuración → Personal."))
        (self.ed_badge if mode != "none" else self.cmb).setFocus()

    def _badge_typed(self, text: str) -> None:
        """Escribir el número de empleado elige a la persona en la lista."""
        p = next((x for x in self.p.people if x.active and x.badge and x.badge == text.strip()), None)
        if p is not None and self.cmb.findData(p.name) >= 0:
            self.cmb.setCurrentIndex(self.cmb.findData(p.name))

    @property
    def name(self) -> str:
        return self.cmb.currentData() or ""

    def accept(self) -> None:
        if not self.name:
            self.lbl.setText(tr("Elige a la persona que entra."))
            return
        err = self.p.verify(self.name, self.ed_badge.text(), self.ed_pw.text())
        if err:
            self.lbl.setText(tr(err))
            self.ed_pw.clear()
            return
        super().accept()
