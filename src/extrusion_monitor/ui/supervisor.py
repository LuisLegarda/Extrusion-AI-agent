"""Acciones protegidas: solo se permiten con la sesión de un supervisor iniciada (número de empleado y contraseña).

Sin sesión, la acción simplemente no se hace (no se abre la lista ni el diálogo). La sesión se inicia desde la
barra superior (🔒 Supervisor) o al entrar un supervisor con contraseña; dura `session_min` minutos desde el
último uso, se cierra desde la barra superior y al cambiar el usuario en turno.
La protección está activa en cuanto hay un supervisor con número de empleado y contraseña; sin ninguno
(equipo nuevo), todo se permite como antes.
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Callable, Optional

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton

from ..i18n import tr
from ..personnel import PROTECTABLE, Personnel
from . import theme


class SupervisorDialog(QDialog):
    def __init__(self, people: Personnel, reason: str, parent=None):
        super().__init__(parent)
        self.p = people
        self.person = None
        self.setWindowTitle(tr("Inicio de sesión de supervisor"))
        self.setMinimumWidth(380)
        f = QFormLayout(self)
        lb = QLabel(tr("Se necesita un supervisor para: <b>{r}</b>", r=tr(reason)) if reason else
                    tr("Inicia la sesión de supervisor para hacer cambios protegidos."))
        lb.setWordWrap(True)
        f.addRow(lb)
        self.ed_badge = QLineEdit()
        self.ed_badge.setPlaceholderText(tr("número de empleado"))
        self.ed_pw = QLineEdit()
        self.ed_pw.setEchoMode(QLineEdit.Password)
        f.addRow(tr("Núm. de empleado"), self.ed_badge)
        f.addRow(tr("Contraseña"), self.ed_pw)
        self.lbl = QLabel("")
        self.lbl.setWordWrap(True)
        self.lbl.setStyleSheet(f"color:{theme.c('critical')};")
        f.addRow(self.lbl)
        row = QHBoxLayout()
        row.addStretch(1)
        cancel = QPushButton(tr("Cancelar"))
        cancel.clicked.connect(self.reject)
        ok = QPushButton(tr("Iniciar sesión"))
        ok.setDefault(True)
        ok.clicked.connect(self.accept)
        row.addWidget(cancel)
        row.addWidget(ok)
        f.addRow(row)
        self.ed_badge.setFocus()

    def accept(self) -> None:
        person = self.p.supervisor_login(self.ed_badge.text(), self.ed_pw.text())
        if person is None:
            self.lbl.setText(tr("Número de empleado o contraseña incorrectos (o no es supervisor)."))
            self.ed_pw.clear()
            return
        self.person = person
        super().accept()


class SupervisorGate(QObject):
    """`allow(clave)` decide si una acción protegida puede hacerse ahora (y pide la sesión si hace falta)."""

    changed = Signal()  # sesión iniciada o cerrada
    denied = Signal(str)  # acción negada (descripción) para avisar sin bloquear

    def __init__(self, home: Path, parent=None, clock: Callable[[], float] = time.monotonic):
        super().__init__(parent)
        self.home = Path(home)
        self.parent_widget = parent
        self.clock = clock
        self.user: Optional[str] = None
        self.until = 0.0
        self.ask: Callable[[Personnel, str], Optional[str]] = self._ask  # se reemplaza en las pruebas
        self.offer: Callable[[str], bool] = self._offer  # aviso «se requiere supervisor» con opción de iniciar sesión

    def people(self) -> Personnel:
        return Personnel.load(self.home)

    def active(self) -> bool:
        if self.user is not None and self.clock() >= self.until:
            self.end()
        return self.user is not None

    def remaining_min(self) -> int:
        return max(0, int((self.until - self.clock() + 59) // 60)) if self.active() else 0

    def start(self, name: str, minutes: int) -> None:
        self.user, self.until = name, self.clock() + 60 * minutes
        self.changed.emit()

    def end(self) -> None:
        if self.user is not None:
            self.user, self.until = None, 0.0
            self.changed.emit()

    def protected(self, key: str) -> bool:
        return self.people().protects(key)

    def locked(self, key: str) -> bool:
        """Protegida y sin sesión de supervisor (para deshabilitar controles)."""
        return self.protected(key) and not self.active()

    def allow(self, key: str) -> bool:
        people = self.people()
        lg = people.login
        if not people.protects(key):
            return True
        if self.active():
            self.until = self.clock() + 60 * lg.session_min  # cada uso alarga la sesión
            return True
        reason = PROTECTABLE.get(key, key)
        self.denied.emit(reason)
        if self.offer(reason) and self.login():  # «Iniciar sesión de supervisor» en el mismo aviso
            return True
        return False

    def _offer(self, reason: str) -> bool:
        from PySide6.QtWidgets import QMessageBox
        box = QMessageBox(self.parent_widget)
        box.setIcon(QMessageBox.Warning)
        box.setWindowTitle(tr("Se requiere supervisor"))
        box.setText(tr("Para modificar esto se requiere la sesión de un supervisor."))
        box.setInformativeText(tr(reason))
        login = box.addButton(tr("🔓 Iniciar sesión de supervisor"), QMessageBox.AcceptRole)
        box.addButton(tr("Cancelar"), QMessageBox.RejectRole)
        box.setDefaultButton(login)
        box.exec()
        return box.clickedButton() is login

    def guard(self, widget, key: str, keys: bool = True) -> None:
        """Clic (o tecla) en un control protegido sin sesión: se muestra el aviso en lugar de abrir o cambiar."""
        target = widget.viewport() if hasattr(widget, "viewport") else widget
        target.installEventFilter(_Guard(self, key, keys, target))
        if target is not widget and keys:
            widget.installEventFilter(_Guard(self, key, keys, widget))

    def login(self) -> bool:
        """Botón 🔒 Supervisor de la barra superior."""
        people = self.people()
        name = self.ask(people, "")
        if name:
            self.start(name, people.login.session_min)
        return bool(name)

    def _ask(self, people: Personnel, reason: str) -> Optional[str]:
        dlg = SupervisorDialog(people, reason, self.parent_widget)
        return dlg.person.name if dlg.exec() and dlg.person is not None else None


class _Guard(QObject):
    def __init__(self, gate: SupervisorGate, key: str, keys: bool, parent):
        super().__init__(parent)
        self.gate, self.key, self.keys = gate, key, keys

    def eventFilter(self, obj, event) -> bool:
        from PySide6.QtCore import QEvent, Qt
        et = event.type()
        if et in (QEvent.MouseButtonPress, QEvent.MouseButtonDblClick):
            pass
        elif et == QEvent.KeyPress and self.keys and event.key() not in (Qt.Key_Tab, Qt.Key_Backtab, Qt.Key_Up,
                                                                       Qt.Key_Down, Qt.Key_PageUp, Qt.Key_PageDown):
            pass
        else:
            return False
        if not self.gate.locked(self.key):
            return False
        self.gate.allow(self.key)  # aviso; si inicia sesión, el siguiente clic ya funciona
        return True
