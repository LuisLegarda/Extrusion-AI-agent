"""Configuración → Notificaciones: canales (correo, Telegram, Teams / Slack / webhook) y alertas a enviar."""
from __future__ import annotations

import time
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QFormLayout, QGroupBox,
    QHBoxLayout, QHeaderView, QLabel, QLineEdit, QListWidget, QMessageBox, QPushButton, QSpinBox, QTableWidget,
    QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget,
)

from ..i18n import tr
from ..notify import RULES, WEBHOOK_KINDS, NotifySettings
from . import theme

KEEP = "••••••••"  # el campo muestra esto si ya hay una contraseña guardada


class NotifyDialog(QDialog):
    def __init__(self, notifier, parent=None):
        super().__init__(parent)
        self.notifier = notifier
        self.home = notifier.home
        s = NotifySettings.load(self.home)
        self.s = s
        self.setWindowTitle(tr("Notificaciones (correo y mensajes)"))
        self.resize(760, 640)
        root = QVBoxLayout(self)
        intro = QLabel(tr("Envía un aviso por correo, Telegram o un canal de Teams / Slack / Google Chat cuando ocurra "
                          "alguna de las alertas elegidas. Es de esta estación (no de la receta). Los avisos salen "
                          "aparte del monitoreo y se reintentan si no hay red."))
        intro.setWordWrap(True)
        root.addWidget(intro)
        self.tabs = QTabWidget()
        root.addWidget(self.tabs, 1)

        # --- canales ---
        w = QWidget()
        lay = QVBoxLayout(w)
        g = QGroupBox(tr("Correo (SMTP)"))
        g.setCheckable(True)
        g.setChecked(s.email.enabled)
        self.g_email = g
        f = QFormLayout(g)
        self.ed_host = QLineEdit(s.email.host)
        self.ed_host.setPlaceholderText("smtp.office365.com · smtp.gmail.com")
        self.sp_port = QSpinBox()
        self.sp_port.setRange(1, 65535)
        self.sp_port.setValue(s.email.port)
        self.cmb_sec = QComboBox()
        for k, lb in (("starttls", "STARTTLS (puerto 587)"), ("ssl", "SSL/TLS (puerto 465)"), ("none", "Sin cifrado")):
            self.cmb_sec.addItem(tr(lb), k)
        self.cmb_sec.setCurrentIndex(max(0, self.cmb_sec.findData(s.email.security)))
        row = QHBoxLayout()
        row.addWidget(self.ed_host, 1)
        row.addWidget(QLabel(tr("Puerto")))
        row.addWidget(self.sp_port)
        row.addWidget(self.cmb_sec)
        f.addRow(tr("Servidor"), row)
        self.ed_user = QLineEdit(s.email.user)
        self.ed_pw = QLineEdit(KEEP if s.email.password else "")
        self.ed_pw.setEchoMode(QLineEdit.Password)
        self.ed_pw.setPlaceholderText(tr("contraseña o contraseña de aplicación"))
        row = QHBoxLayout()
        row.addWidget(self.ed_user, 1)
        row.addWidget(self.ed_pw, 1)
        f.addRow(tr("Usuario y contraseña"), row)
        self.ed_from = QLineEdit(s.email.sender)
        self.ed_from.setPlaceholderText(tr("(el mismo usuario)"))
        f.addRow(tr("Remitente"), self.ed_from)
        self.ed_to = QLineEdit(", ".join(s.email.to))
        self.ed_to.setPlaceholderText("supervisor@empresa.com, mantenimiento@empresa.com")
        f.addRow(tr("Destinatarios"), self.ed_to)
        lay.addWidget(g)

        g = QGroupBox(tr("Telegram"))
        g.setCheckable(True)
        g.setChecked(s.telegram.enabled)
        self.g_tg = g
        f = QFormLayout(g)
        self.ed_token = QLineEdit(KEEP if s.telegram.token else "")
        self.ed_token.setEchoMode(QLineEdit.Password)
        self.ed_token.setPlaceholderText(tr("token del bot (de @BotFather)"))
        f.addRow(tr("Token"), self.ed_token)
        self.ed_chats = QLineEdit(", ".join(s.telegram.chat_ids))
        self.ed_chats.setPlaceholderText(tr("ID del chat o grupo, separados por coma"))
        f.addRow(tr("Chats"), self.ed_chats)
        hint = QLabel(tr("Crea un bot con @BotFather, agrégalo al grupo y escribe ahí cualquier mensaje; el ID del chat "
                         "aparece en https://api.telegram.org/bot<token>/getUpdates."))
        hint.setWordWrap(True)
        hint.setStyleSheet(f"color:{theme.c('muted')}; font-size:11px;")
        f.addRow(hint)
        lay.addWidget(g)

        g = QGroupBox(tr("Teams / Slack / Google Chat (webhook)"))
        g.setCheckable(True)
        g.setChecked(s.webhook.enabled)
        self.g_wh = g
        f = QFormLayout(g)
        self.cmb_kind = QComboBox()
        for k, lb in WEBHOOK_KINDS.items():
            self.cmb_kind.addItem(tr(lb), k)
        self.cmb_kind.setCurrentIndex(max(0, self.cmb_kind.findData(s.webhook.kind)))
        f.addRow(tr("Tipo"), self.cmb_kind)
        self.ed_url = QLineEdit(KEEP if s.webhook.url else "")
        self.ed_url.setEchoMode(QLineEdit.Password)
        self.ed_url.setPlaceholderText(tr("URL del webhook entrante del canal"))
        f.addRow(tr("URL"), self.ed_url)
        lay.addWidget(g)
        row = QHBoxLayout()
        self.btn_test = QPushButton(tr("✉ Enviar prueba"))
        self.btn_test.clicked.connect(self.send_test)
        row.addWidget(self.btn_test)
        self.lbl_test = QLabel("")
        self.lbl_test.setWordWrap(True)
        row.addWidget(self.lbl_test, 1)
        lay.addLayout(row)
        lay.addStretch(1)
        self.tabs.addTab(w, tr("📡 Canales"))

        # --- alertas ---
        w = QWidget()
        lay = QVBoxLayout(w)
        self.tbl = QTableWidget(len(RULES), 3)
        self.tbl.setHorizontalHeaderLabels([tr("Enviar aviso cuando…"), tr("Límite"), ""])
        self.tbl.verticalHeader().setVisible(False)
        hh = self.tbl.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.Stretch)
        hh.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.spins: dict[str, QDoubleSpinBox] = {}
        for r, (key, (label, unit, default, _on)) in enumerate(RULES.items()):
            it = QTableWidgetItem(tr(label))
            it.setFlags(Qt.ItemIsEnabled | Qt.ItemIsUserCheckable)
            it.setCheckState(Qt.Checked if s.on(key) else Qt.Unchecked)
            it.setData(Qt.UserRole, key)
            self.tbl.setItem(r, 0, it)
            if default is not None:
                sp = QDoubleSpinBox()
                sp.setRange(0, 1e6)
                sp.setDecimals(2 if key == "low_cpk" else 0)
                sp.setSingleStep(0.1 if key == "low_cpk" else 1)
                sp.setValue(float(s.th(key) or default))
                self.tbl.setCellWidget(r, 1, sp)
                self.spins[key] = sp
                u = QTableWidgetItem(tr(unit))
                u.setFlags(Qt.ItemIsEnabled)
                self.tbl.setItem(r, 2, u)
        lay.addWidget(self.tbl, 1)
        note = QLabel(tr("El mismo aviso no se repite antes del tiempo de espera; cuando la condición se normaliza, un "
                         "nuevo evento vuelve a avisar. El paro avisa también cuando la línea reanuda."))
        note.setWordWrap(True)
        note.setStyleSheet(f"color:{theme.c('muted')};")
        lay.addWidget(note)
        self.tabs.addTab(w, tr("🔔 Alertas"))

        # --- opciones e historial ---
        w = QWidget()
        lay = QVBoxLayout(w)
        f = QFormLayout()
        self.sp_cool = QDoubleSpinBox()
        self.sp_cool.setRange(0, 1440)
        self.sp_cool.setSuffix(" min")
        self.sp_cool.setValue(s.cooldown_min)
        f.addRow(tr("Tiempo de espera entre avisos iguales"), self.sp_cool)
        self.chk_quiet = QCheckBox(tr("Pausar todos los avisos (mantenimiento, pruebas)"))
        self.chk_quiet.setChecked(s.quiet)
        f.addRow(self.chk_quiet)
        lay.addLayout(f)
        lay.addWidget(QLabel(f"<b>{tr('Últimos envíos')}</b>"))
        self.lst_hist = QListWidget()
        for ts, ch, status, subject in reversed(list(notifier.history)):
            self.lst_hist.addItem(f"{time.strftime('%d/%m %H:%M:%S', time.localtime(ts))} · {ch} · "
                                  f"{'✔' if status == 'ok' else '✗ ' + status} · {subject}")
        if not self.lst_hist.count():
            self.lst_hist.addItem(tr("(todavía no se ha enviado nada en esta sesión)"))
        lay.addWidget(self.lst_hist, 1)
        self.tabs.addTab(w, tr("⚙ Opciones"))

        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText(tr("Guardar"))
        bb.button(QDialogButtonBox.Cancel).setText(tr("Cancelar"))
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        root.addWidget(bb)

    def settings(self) -> NotifySettings:
        s = NotifySettings.load(self.home)  # conserva contraseñas guardadas si el campo no se tocó
        s.email.enabled = self.g_email.isChecked()
        s.email.host = self.ed_host.text().strip()
        s.email.port = self.sp_port.value()
        s.email.security = self.cmb_sec.currentData()
        s.email.user = self.ed_user.text().strip()
        s.email.sender = self.ed_from.text().strip()
        s.email.to = [x.strip() for x in self.ed_to.text().replace(";", ",").split(",") if x.strip()]
        s.telegram.enabled = self.g_tg.isChecked()
        s.telegram.chat_ids = [x.strip() for x in self.ed_chats.text().split(",") if x.strip()]
        s.webhook.enabled = self.g_wh.isChecked()
        s.webhook.kind = self.cmb_kind.currentData()
        for which, ed in (("email", self.ed_pw), ("telegram", self.ed_token), ("webhook", self.ed_url)):
            if ed.text() != KEEP:
                s.set_secret(which, ed.text().strip())
        for r in range(self.tbl.rowCount()):
            it = self.tbl.item(r, 0)
            key = it.data(Qt.UserRole)
            rs = s.rules[key]
            rs.enabled = it.checkState() == Qt.Checked
            if key in self.spins:
                rs.threshold = self.spins[key].value()
        s.cooldown_min = self.sp_cool.value()
        s.quiet = self.chk_quiet.isChecked()
        return s

    def _settings_or_warn(self) -> Optional[NotifySettings]:
        from ..secrets_store import SecretError
        try:
            return self.settings()
        except SecretError as e:  # la contraseña o el token no se pudieron cifrar: no se guardan legibles
            QMessageBox.warning(self, tr("Notificaciones"),
                                tr("No se pudo cifrar la contraseña o el token en este equipo, así que no se guardó "
                                   "({e}). Revisa que la sesión de Windows tenga perfil de usuario.", e=e))
            return None

    def send_test(self) -> None:
        s = self._settings_or_warn()
        if s is None:
            return
        if not s.channels():
            self.lbl_test.setText(tr("Activa y completa al menos un canal."))
            return
        prev = self.notifier.settings
        self.notifier.settings = s
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            res = self.notifier.test()
        finally:
            QApplication.restoreOverrideCursor()
            self.notifier.settings = prev
        ok = all(v == "ok" for v in res.values())
        self.lbl_test.setText(" · ".join(f"{k}: {'✔' if v == 'ok' else '✗ ' + v}" for k, v in res.items()))
        self.lbl_test.setStyleSheet(f"color:{theme.c('good_text') if ok else theme.c('critical')};")

    def accept(self) -> None:
        s = self._settings_or_warn()
        if s is None:
            return
        if s.email.enabled and (not s.email.host or not s.email.to):
            QMessageBox.information(self, tr("Notificaciones"), tr("Para el correo falta el servidor o los destinatarios."))
            return
        s.save(self.home)
        self.notifier.reload()
        super().accept()
