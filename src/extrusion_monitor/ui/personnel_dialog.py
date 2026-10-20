"""Configuración → Personal: operadores y supervisores, turnos y confirmación del usuario en turno."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QTime
from PySide6.QtWidgets import (
    QButtonGroup, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout, QHeaderView, QLabel,
    QLineEdit, QMessageBox, QPushButton, QRadioButton, QSpinBox, QTableWidget, QTableWidgetItem, QTabWidget,
    QTimeEdit, QVBoxLayout, QWidget,
)

from ..i18n import tr
from ..personnel import CONFIRM_MODES, PROTECTABLE, ROLES, LoginSettings, Person, Personnel, Shift, hash_password

COLS = ("Nombre", "Puesto", "Núm. de empleado", "Turno", "Contraseña", "Activo")
C_NAME, C_ROLE, C_BADGE, C_SHIFT, C_PW, C_ACTIVE = range(len(COLS))
PW_ROLE = Qt.UserRole + 1  # huella de la contraseña guardada en la celda del nombre
MIN_PASSWORD = 4


class PasswordDialog(QDialog):
    def __init__(self, name: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("Contraseña de {n}", n=name))
        f = QFormLayout(self)
        self.ed1, self.ed2 = QLineEdit(), QLineEdit()
        for ed in (self.ed1, self.ed2):
            ed.setEchoMode(QLineEdit.Password)
        f.addRow(tr("Contraseña nueva"), self.ed1)
        f.addRow(tr("Repetir"), self.ed2)
        self.lbl = QLabel(tr("Mínimo {n} caracteres. Se guarda cifrada (no se puede leer, solo reemplazar).",
                             n=MIN_PASSWORD))
        self.lbl.setWordWrap(True)
        f.addRow(self.lbl)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        f.addRow(bb)

    def accept(self) -> None:
        if len(self.ed1.text()) < MIN_PASSWORD:
            self.lbl.setText(tr("La contraseña debe tener al menos {n} caracteres.", n=MIN_PASSWORD))
            return
        if self.ed1.text() != self.ed2.text():
            self.lbl.setText(tr("Las dos contraseñas no coinciden."))
            return
        super().accept()


class PersonnelDialog(QDialog):
    def __init__(self, home: Path, recipe_operators=(), parent=None, shift_starts=()):
        super().__init__(parent)
        self.setWindowTitle("Personal (operadores y supervisores)")
        self.resize(820, 520)
        self.home = Path(home)
        self.shift_starts = list(shift_starts)
        data = Personnel.load(home)
        root = QVBoxLayout(self)
        self.tabs = QTabWidget()
        root.addWidget(self.tabs, 1)

        # --- personas ---
        w = QWidget()
        lay = QVBoxLayout(w)
        intro = QLabel("Las personas de esta estación. Aparecen en la barra superior (quién está en turno) y al "
                       "capturar paros y defectos. Son de este equipo, no de la receta; una persona inactiva se "
                       "conserva en las capturas anteriores pero ya no aparece en las listas.")
        intro.setWordWrap(True)
        lay.addWidget(intro)
        self.table = QTableWidget(0, len(COLS))
        self.table.setHorizontalHeaderLabels([tr(c) for c in COLS])
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(C_NAME, QHeaderView.Stretch)
        for i in range(1, len(COLS)):
            hh.setSectionResizeMode(i, QHeaderView.ResizeToContents)
        self.table.verticalHeader().setVisible(False)
        lay.addWidget(self.table, 1)
        row = QHBoxLayout()
        for text, slot in (("+ Usuario", lambda: self._new("operator")), ("Quitar", self._remove)):
            b = QPushButton(text)
            b.clicked.connect(slot)
            row.addWidget(b)
        row.addStretch(1)
        lay.addLayout(row)
        self.tabs.addTab(w, "👷 Personas")

        # --- turnos ---
        w = QWidget()
        lay = QVBoxLayout(w)
        intro = QLabel("Turnos con su horario. Asigna a cada persona su turno en la pestaña Personas (sin turno = "
                       "puede entrar en cualquiera). Un turno que termina antes de empezar cruza la medianoche "
                       "(p. ej. 22:00–06:00).")
        intro.setWordWrap(True)
        lay.addWidget(intro)
        self.shifts = QTableWidget(0, 3)
        self.shifts.setHorizontalHeaderLabels([tr("Turno"), tr("Inicio"), tr("Fin")])
        self.shifts.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.shifts.verticalHeader().setVisible(False)
        lay.addWidget(self.shifts, 1)
        row = QHBoxLayout()
        for text, slot in (("+ Turno", self._new_shift), ("Quitar", self._remove_shift),
                           ("Crear desde los inicios del OEE", self._shifts_from_oee)):
            b = QPushButton(text)
            b.clicked.connect(slot)
            row.addWidget(b)
        row.addStretch(1)
        lay.addLayout(row)
        self.tabs.addTab(w, "🕒 Turnos")

        # --- confirmación ---
        w = QWidget()
        lay = QVBoxLayout(w)
        self.chk_auto = QCheckBox("Detectar el turno por la hora y, al empezar cada turno, pedir quién entra")
        self.chk_auto.setChecked(data.login.auto_shift)
        lay.addWidget(self.chk_auto)
        lay.addSpacing(8)
        lay.addWidget(QLabel("<b>" + tr("Confirmación del usuario que entra (también al cambiarlo en la barra superior)")
                             + "</b>"))
        self.grp = QButtonGroup(self)
        self.rb: dict[str, QRadioButton] = {}
        for key, label in CONFIRM_MODES.items():
            rb = QRadioButton(tr(label))
            rb.setChecked(key == data.login.confirm)
            self.grp.addButton(rb)
            self.rb[key] = rb
            lay.addWidget(rb)
        lay.addSpacing(10)
        self.chk_lock = QCheckBox("Pedir el inicio de sesión de un supervisor (número de empleado y contraseña) para:")
        self.chk_lock.setChecked(data.login.lock)
        self.chk_lock.setStyleSheet("font-weight: bold;")
        lay.addWidget(self.chk_lock)
        self.chk_protect: dict[str, QCheckBox] = {}
        for key, label in PROTECTABLE.items():
            cb = QCheckBox(tr(label))
            cb.setChecked(key == "personnel" or key in data.login.protect)
            cb.setEnabled(key != "personnel")  # si no, cualquiera podría quitar la protección
            cb.setStyleSheet("margin-left: 22px;")
            self.chk_protect[key] = cb
            lay.addWidget(cb)
        row = QHBoxLayout()
        row.addSpacing(22)
        row.addWidget(QLabel(tr("La sesión de supervisor se cierra tras")))
        self.sp_session = QSpinBox()
        self.sp_session.setRange(1, 240)
        self.sp_session.setSuffix(" min")
        self.sp_session.setValue(data.login.session_min)
        row.addWidget(self.sp_session)
        row.addWidget(QLabel(tr("sin usarse (o al cerrarla en la barra superior).")))
        row.addStretch(1)
        lay.addLayout(row)
        note = QLabel("Todo es opcional. Con confirmación, cada persona necesita su número de empleado (y su "
                      "contraseña, si se pide). Las contraseñas se guardan cifradas; si alguien la olvida, asígnale "
                      "una nueva en la pestaña Personas.")
        note.setWordWrap(True)
        lay.addWidget(note)
        lay.addStretch(1)
        self.tabs.addTab(w, "🔐 Confirmación y supervisor")

        for s in data.shifts:
            self.add_shift(s)
        people = data.people
        known = {p.name for p in people}
        # La lista anterior (por receta) se ofrece como punto de partida
        people += [Person(n) for n in recipe_operators if n and n not in known]
        for p in people:
            self.add_person(p)
        self.tabs.currentChanged.connect(lambda _i: self._refresh_shift_combos())

        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText("Guardar")
        bb.button(QDialogButtonBox.Cancel).setText("Cancelar")
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        root.addWidget(bb)

    # --- personas -----------------------------------------------------------------------
    def add_person(self, p: Person) -> int:
        r = self.table.rowCount()
        self.table.insertRow(r)
        it = QTableWidgetItem(p.name)
        it.setData(PW_ROLE, p.password)
        self.table.setItem(r, C_NAME, it)
        cmb = QComboBox()
        for key, label in ROLES.items():
            cmb.addItem(tr(label), key)
        cmb.setCurrentIndex(max(0, cmb.findData(p.role)))
        self.table.setCellWidget(r, C_ROLE, cmb)
        self.table.setItem(r, C_BADGE, QTableWidgetItem(p.badge))
        sh = QComboBox()
        self.table.setCellWidget(r, C_SHIFT, sh)
        self._fill_shift_combo(sh, p.shift)
        btn = QPushButton()
        btn.clicked.connect(lambda _=False, it=it: self._set_password(it))
        self.table.setCellWidget(r, C_PW, btn)
        self._pw_button(it)
        act = QTableWidgetItem()
        act.setFlags(Qt.ItemIsEnabled | Qt.ItemIsUserCheckable)
        act.setCheckState(Qt.Checked if p.active else Qt.Unchecked)
        self.table.setItem(r, C_ACTIVE, act)
        return r

    def _pw_button(self, it: QTableWidgetItem) -> None:
        btn = self.table.cellWidget(it.row(), C_PW)
        btn.setText(tr("🔒 Cambiar…") if it.data(PW_ROLE) else tr("Asignar…"))

    def _set_password(self, it: QTableWidgetItem) -> None:
        dlg = PasswordDialog(it.text(), self)
        if dlg.exec():
            self.set_password(it.row(), dlg.ed1.text())

    def set_password(self, row: int, password: str) -> None:
        it = self.table.item(row, C_NAME)
        it.setData(PW_ROLE, hash_password(password) if password else "")
        self._pw_button(it)

    def _new(self, role: str) -> None:
        r = self.add_person(Person(tr("Nuevo usuario"), role))  # operador por defecto; el puesto se cambia en la lista
        self.tabs.setCurrentIndex(0)
        self.table.setCurrentCell(r, 0)
        self.table.editItem(self.table.item(r, 0))

    def _remove(self) -> None:
        r = self.table.currentRow()
        if r >= 0:
            self.table.removeRow(r)

    # --- turnos -------------------------------------------------------------------------
    def add_shift(self, s: Shift) -> int:
        r = self.shifts.rowCount()
        self.shifts.insertRow(r)
        self.shifts.setItem(r, 0, QTableWidgetItem(s.name))
        for col, val in ((1, s.start), (2, s.end)):
            ed = QTimeEdit(QTime.fromString(val, "HH:mm") if QTime.fromString(val, "HH:mm").isValid() else QTime(6, 0))
            ed.setDisplayFormat("HH:mm")
            self.shifts.setCellWidget(r, col, ed)
        return r

    def _new_shift(self) -> None:
        n = self.shifts.rowCount() + 1
        r = self.add_shift(Shift(tr("Turno {n}", n=n), "06:00", "14:00"))
        self.shifts.setCurrentCell(r, 0)
        self.shifts.editItem(self.shifts.item(r, 0))

    def _remove_shift(self) -> None:
        r = self.shifts.currentRow()
        if r >= 0:
            self.shifts.removeRow(r)

    def _shifts_from_oee(self) -> None:
        starts = sorted(s for s in self.shift_starts if s)
        if not starts:
            QMessageBox.information(self, tr("Turnos"), tr("La receta no tiene inicios de turno en KPI / OEE."))
            return
        if self.shifts.rowCount() and QMessageBox.question(
                self, tr("Turnos"), tr("¿Reemplazar los turnos por los del OEE?")) != QMessageBox.Yes:
            return
        self.shifts.setRowCount(0)
        for i, a in enumerate(starts):
            self.add_shift(Shift(tr("Turno {n}", n=i + 1), a, starts[(i + 1) % len(starts)]))

    def shift_list(self) -> list[Shift]:
        out, seen = [], set()
        for r in range(self.shifts.rowCount()):
            name = (self.shifts.item(r, 0).text() if self.shifts.item(r, 0) else "").strip()
            if name and name not in seen:
                seen.add(name)
                out.append(Shift(name, self.shifts.cellWidget(r, 1).time().toString("HH:mm"),
                                 self.shifts.cellWidget(r, 2).time().toString("HH:mm")))
        return out

    def _fill_shift_combo(self, cmb: QComboBox, current: str) -> None:
        cmb.blockSignals(True)
        cmb.clear()
        cmb.addItem(tr("Cualquiera"), "")
        names = [s.name for s in self.shift_list()]
        if current and current not in names:
            names.append(current)
        for n in names:
            cmb.addItem(n, n)
        cmb.setCurrentIndex(max(0, cmb.findData(current)))
        cmb.blockSignals(False)

    def _refresh_shift_combos(self) -> None:
        for r in range(self.table.rowCount()):
            cmb = self.table.cellWidget(r, C_SHIFT)
            self._fill_shift_combo(cmb, cmb.currentData() or "")

    # --- guardar ------------------------------------------------------------------------
    def personnel(self) -> Personnel:
        out, seen = [], set()
        for r in range(self.table.rowCount()):
            it = self.table.item(r, C_NAME)
            name = (it.text() if it else "").strip()
            if not name or name in seen:
                continue
            seen.add(name)
            badge = self.table.item(r, C_BADGE)
            out.append(Person(name, self.table.cellWidget(r, C_ROLE).currentData(),
                              badge.text().strip() if badge else "",
                              self.table.item(r, C_ACTIVE).checkState() == Qt.Checked,
                              self.table.cellWidget(r, C_SHIFT).currentData() or "", it.data(PW_ROLE) or ""))
        confirm = next((k for k, rb in self.rb.items() if rb.isChecked()), "none")
        protect = [k for k, cb in self.chk_protect.items() if cb.isChecked()]
        return Personnel(out, self.shift_list(), LoginSettings(self.chk_auto.isChecked(), confirm,
                                                                self.chk_lock.isChecked(), protect,
                                                                self.sp_session.value()))

    def problems(self, p: Personnel) -> list[str]:
        """Lo que falta para que la confirmación elegida funcione."""
        msgs = []
        if p.login.auto_shift and not p.shifts:
            msgs.append(tr("Para detectar el turno por la hora, agrega los turnos y su horario."))
        badges = [x.badge for x in p.people if x.active and x.badge]
        if len(badges) != len(set(badges)):
            msgs.append(tr("Hay números de empleado repetidos."))
        if p.login.confirm != "none":
            no_badge = [x.name for x in p.people if x.active and not x.badge]
            if no_badge:
                msgs.append(tr("Sin número de empleado: {n}", n=", ".join(no_badge)))
            if p.login.confirm == "badge_password":
                no_pw = [x.name for x in p.people if x.active and not x.password]
                if no_pw:
                    msgs.append(tr("Sin contraseña: {n}", n=", ".join(no_pw)))
        return msgs

    def blocking(self, p: Personnel) -> list[str]:
        """Lo que impide guardar: la protección sin un supervisor que pueda entrar dejaría todo bloqueado."""
        if p.login.lock and not p.supervisors_ready():
            return [tr("Para pedir el inicio de sesión de supervisor, al menos un supervisor activo necesita número "
                       "de empleado y contraseña.")]
        return []

    def accept(self) -> None:
        p = self.personnel()
        stop = self.blocking(p)
        if stop:
            QMessageBox.warning(self, tr("Personal"), "\n".join(stop))
            return
        msgs = self.problems(p)
        if msgs and QMessageBox.question(
                self, tr("Personal"), "\n".join(msgs) + "\n\n" + tr("¿Guardar de todos modos?")) != QMessageBox.Yes:
            return
        p.save(self.home)
        super().accept()
