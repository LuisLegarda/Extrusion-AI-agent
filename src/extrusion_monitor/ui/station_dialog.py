"""Configuración de la exportación de esta línea al dashboard global."""
from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QFileDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QSpinBox, QVBoxLayout,
)

from ..fleet import StationSettings, line_slug
from ..i18n import tr


class StationDialog(QDialog):
    def __init__(self, exporter, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Dashboard global (exportación)")
        self.resize(620, 420)
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

    def settings(self) -> StationSettings:
        return StationSettings(enabled=self.chk.isChecked(), export_dir=self.ed_dir.text().strip(),
                               line_name=self.ed_name.text().strip(), line_id=self.ed_id.text().strip(),
                               area=self.ed_area.text().strip(),
                               interval_s=self.sp_int.value(), trend_interval_s=self.sp_trend.value(),
                               retention_days=self.sp_ret.value())

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
