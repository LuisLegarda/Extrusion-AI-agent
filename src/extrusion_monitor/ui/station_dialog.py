"""Configuración de la exportación de esta línea al dashboard global."""
from __future__ import annotations

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QCheckBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QFileDialog, QFormLayout, QGroupBox, QHBoxLayout,
    QInputDialog, QLabel, QLineEdit, QPushButton, QSpinBox, QVBoxLayout,
)

from ..fleet import StationSettings, line_slug
from ..i18n import tr


class StationDialog(QDialog):
    def __init__(self, exporter, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Dashboard global (exportación)")
        self.resize(680, 640)
        self.exporter = exporter
        s = exporter.settings
        machine = exporter.engine.config.machine_name
        root = QVBoxLayout(self)
        intro = QLabel(
            "Esta línea escribe su estado, alarmas, eventos y tendencias en una carpeta compartida. "
            "El dashboard global (DashboardGlobal.exe) lee esa carpeta y muestra todas las líneas.\n"
            "La escritura va en un proceso aparte: si la red falla, el monitoreo sigue y los datos se envían "
            "al volver.")
        intro.setWordWrap(True)
        root.addWidget(intro)
        form = QFormLayout()
        self.chk = QCheckBox("Exportar al dashboard global")
        self.chk.setChecked(s.enabled)
        form.addRow(self.chk)
        self.ed_dir = QLineEdit(s.export_dir)
        self.ed_dir.setPlaceholderText(r"\\SERVIDOR\lineas")
        row = QHBoxLayout()
        row.addWidget(self.ed_dir, 1)
        b = QPushButton("Examinar…")
        b.clicked.connect(self._browse)
        row.addWidget(b)
        form.addRow("Carpeta compartida:", row)
        self.ed_name = QLineEdit(s.line_name)
        self.ed_name.setPlaceholderText(machine)
        form.addRow("Nombre de la línea:", self.ed_name)
        self.ed_area = QLineEdit(s.area)
        self.ed_area.setPlaceholderText("p. ej. Nave 2")
        form.addRow("Área / nave:", self.ed_area)
        self.ed_id = QLineEdit(s.line_id)
        self.ed_id.setPlaceholderText(line_slug(machine))
        self.ed_name.textChanged.connect(lambda t: self.ed_id.setPlaceholderText(line_slug(t or machine)))
        self.ed_id.setToolTip("Nombre de la carpeta de esta línea; debe ser único en la planta.")
        form.addRow("ID de la línea (carpeta):", self.ed_id)
        self.sp_int = QDoubleSpinBox()
        self.sp_int.setRange(1, 60)
        self.sp_int.setSuffix(" s")
        self.sp_int.setValue(s.interval_s)
        form.addRow("Actualizar el estado cada:", self.sp_int)
        self.sp_trend = QDoubleSpinBox()
        self.sp_trend.setRange(10, 600)
        self.sp_trend.setSuffix(" s")
        self.sp_trend.setValue(s.trend_interval_s)
        form.addRow("Un punto de tendencia cada:", self.sp_trend)
        self.sp_ret = QSpinBox()
        self.sp_ret.setRange(1, 3650)
        self.sp_ret.setSuffix(" días")
        self.sp_ret.setValue(s.retention_days)
        form.addRow("Conservar eventos y tendencias:", self.sp_ret)
        root.addLayout(form)
        root.addWidget(self._server_box(s))
        self.lbl = QLabel()
        self.lbl.setWordWrap(True)
        root.addWidget(self.lbl)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText("Aceptar")
        bb.button(QDialogButtonBox.Cancel).setText("Cancelar")
        test = bb.addButton("Probar escritura", QDialogButtonBox.ActionRole)
        test.clicked.connect(self._test)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        root.addWidget(bb)
        self._show_status()

    def _server_box(self, s: StationSettings) -> QGroupBox:
        box = QGroupBox("Servidor propio (nube o servidor de planta)")
        f = QFormLayout(box)
        self.chk_srv = QCheckBox("Enviar también al servidor")
        self.chk_srv.setChecked(s.server_enabled)
        f.addRow(self.chk_srv)
        self.ed_url = QLineEdit(s.server_url)
        self.ed_url.setPlaceholderText("https://monitor.miempresa.com")
        f.addRow("Dirección del servidor:", self.ed_url)
        self.ed_token = QLineEdit(s.server_token)
        self.ed_token.setEchoMode(QLineEdit.Password)
        self.ed_token.setPlaceholderText("se obtiene con «Registrar esta línea…»")
        row = QHBoxLayout()
        row.addWidget(self.ed_token, 1)
        b = QPushButton("Registrar esta línea…")
        b.setToolTip("Pide la clave de registro del servidor (la tiene el administrador) y obtiene la clave de esta línea")
        b.clicked.connect(self._register)
        row.addWidget(b)
        f.addRow("Clave de la línea:", row)
        self.sp_srv = QDoubleSpinBox()
        self.sp_srv.setRange(2, 300)
        self.sp_srv.setSuffix(" s")
        self.sp_srv.setValue(s.server_interval_s)
        f.addRow("Enviar el estado cada:", self.sp_srv)
        self.chk_tls = QCheckBox("Verificar el certificado HTTPS (desactívalo solo con certificados internos de prueba)")
        self.chk_tls.setChecked(s.server_verify_tls)
        f.addRow(self.chk_tls)
        self.lbl_srv = QLabel()
        self.lbl_srv.setWordWrap(True)
        b2 = QPushButton("Probar conexión")
        b2.clicked.connect(self._test_server)
        f.addRow(b2, self.lbl_srv)
        f.addRow(QLabel("Primero se guarda en disco y luego se envía: si la red falla, los datos esperan y se "
                        "envían al volver. El servidor nunca envía órdenes a esta PC."))
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._server_status)
        self._timer.start(2000)
        self._server_status()
        return box

    def _line_id(self) -> str:
        machine = self.exporter.engine.config.machine_name
        return line_slug(self.ed_id.text().strip() or self.ed_name.text().strip() or machine)

    def _register(self) -> None:
        from ..cloud import ServerError, register
        url = self.ed_url.text().strip()
        if not url:
            self.lbl_srv.setText(tr("Indica la dirección del servidor."))
            return
        key, ok = QInputDialog.getText(self, tr("Registrar esta línea"),
                                       tr("Clave de registro del servidor:"), QLineEdit.Password)
        if not ok or not key.strip():
            return
        try:
            token = register(url, key.strip(), self._line_id(), self.ed_name.text().strip() or
                             self.exporter.engine.config.machine_name, self.ed_area.text().strip(),
                             verify=self.chk_tls.isChecked())
        except ServerError as exc:
            self.lbl_srv.setText(f"<span style='color:#d03b3b'><b>{tr('Error')}</b>: {exc}</span>")
            return
        self.ed_token.setText(token)
        self.chk_srv.setChecked(True)
        self.lbl_srv.setText(f"<span style='color:#0ca30c'><b>OK</b></span> · " +
                             tr("Línea registrada como «{p}». Pulsa Aceptar para empezar a enviar.", p=self._line_id()))

    def _test_server(self) -> None:
        from ..cloud import ServerError, request
        url, token = self.ed_url.text().strip(), self.ed_token.text().strip()
        if not url:
            self.lbl_srv.setText(tr("Indica la dirección del servidor."))
            return
        try:
            h = request(url, "/api/v1/health", verify=self.chk_tls.isChecked(), timeout=8)
            msg = tr("Servidor en línea (versión {p}).", p=h.get("version", "?"))
            if token:
                me = request(url, "/api/v1/me", token=token, verify=self.chk_tls.isChecked(), timeout=8)
                msg += " " + tr("Clave válida para la línea «{p}».", p=me.get("line_id", ""))
            self.lbl_srv.setText(f"<span style='color:#0ca30c'><b>OK</b></span> · {msg}")
        except ServerError as exc:
            self.lbl_srv.setText(f"<span style='color:#d03b3b'><b>{tr('Error')}</b>: {exc}</span>")

    def _server_status(self) -> None:
        c = self.exporter.cloud
        if not self.exporter.settings.server_ready:
            return
        n = len(c.pending())
        if c.last_error:
            txt = f"<span style='color:#d03b3b'>{tr('Sin enviar')}: {c.last_error}</span>"
        elif c.last_ok:
            import time
            txt = tr("Último envío hace {p} s", p=f"{time.time() - c.last_ok:.0f}")
        else:
            txt = tr("Conectando…")
        if n:
            txt += " · " + tr("{p} lotes en espera", p=n)
        self.lbl_srv.setText(txt)

    def settings(self) -> StationSettings:
        return StationSettings(enabled=self.chk.isChecked(), export_dir=self.ed_dir.text().strip(),
                               line_name=self.ed_name.text().strip(), line_id=self.ed_id.text().strip(),
                               area=self.ed_area.text().strip(),
                               interval_s=self.sp_int.value(), trend_interval_s=self.sp_trend.value(),
                               retention_days=self.sp_ret.value(), server_enabled=self.chk_srv.isChecked(),
                               server_url=self.ed_url.text().strip().rstrip("/"),
                               server_token=self.ed_token.text().strip(),
                               server_verify_tls=self.chk_tls.isChecked(), server_interval_s=self.sp_srv.value())

    def _browse(self) -> None:
        d = QFileDialog.getExistingDirectory(self, tr("Carpeta compartida"), self.ed_dir.text())
        if d:
            self.ed_dir.setText(d)

    def _show_status(self) -> None:
        ex = self.exporter
        if ex.line_dir is None:
            self.lbl.setText(tr("Exportación desactivada."))
        elif ex.last_error:
            self.lbl.setText(f"<span style='color:#d03b3b'>{tr('Error')}: {ex.last_error}</span>")
        else:
            self.lbl.setText(tr("Escribiendo en: {p}", p=str(ex.line_dir)))

    def _test(self) -> None:
        st = self.settings()
        if not st.export_dir:
            self.lbl.setText(tr("Indica la carpeta compartida."))
            return
        st.enabled = True
        old = self.exporter.settings
        self.exporter.settings = st
        try:
            self.exporter.write_once()
            self.lbl.setText(f"<span style='color:#0ca30c'><b>OK</b></span> · " +
                             tr("Escribiendo en: {p}", p=str(self.exporter.line_dir)))
        except Exception as exc:
            self.lbl.setText(f"<span style='color:#d03b3b'><b>{tr('Error')}</b>: {exc}</span>")
        finally:
            self.exporter.settings = old
