"""Configuración → Guardado de datos: cuánto tiempo se conservan el historial de esta PC y lo que se publica
para el dashboard global (3 meses, 6 meses, 1 año o indefinido)."""
from __future__ import annotations

import time

from PySide6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QFormLayout, QGroupBox, QLabel, QMessageBox, QVBoxLayout,
)

from ..i18n import tr

RETENTION_CHOICES = [(91, "3 meses"), (182, "6 meses"), (365, "1 año"), (0, "Indefinido")]
DEFAULT_DAYS = 182


def retention_text(days: int) -> str:
    label = dict(RETENTION_CHOICES).get(days)
    return tr(label) if label else tr("{n} días", n=days)


def _size_text(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.0f} {unit}" if unit in ("B", "KB") else f"{n:.1f} {unit}"
        n /= 1024
    return ""


def _combo(days: int) -> QComboBox:
    cmb = QComboBox()
    for d, label in RETENTION_CHOICES:
        cmb.addItem(tr(label), d)
    if cmb.findData(days) < 0:  # un valor anterior que no está en la lista (p. ej. 30 días)
        cmb.addItem(retention_text(days), days)
    cmb.setCurrentIndex(cmb.findData(days))
    return cmb


class StorageDialog(QDialog):
    def __init__(self, exporter, historian=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("Guardado de datos"))
        self.setMinimumWidth(520)
        self.exporter = exporter
        self.historian = historian
        s = exporter.settings
        root = QVBoxLayout(self)

        box = QGroupBox(tr("Historial de esta PC"))
        f = QFormLayout(box)
        self.cmb_history = _combo(s.history_days)
        f.addRow(tr("Conservar lecturas, eventos y OEE:"), self.cmb_history)
        self.lbl_usage = QLabel()
        self.lbl_usage.setWordWrap(True)
        self.lbl_usage.setObjectName("muted")
        f.addRow(self.lbl_usage)
        root.addWidget(box)

        box = QGroupBox(tr("Dashboard global (carpeta compartida)"))
        f = QFormLayout(box)
        self.cmb_export = _combo(s.retention_days)
        f.addRow(tr("Conservar eventos y tendencias:"), self.cmb_export)
        root.addWidget(box)

        note = QLabel(tr("Lo más antiguo se borra solo, una vez por hora, sin detener el monitoreo. Las capturas de "
                         "paros y defectos, las recetas y la configuración no se borran."))
        note.setWordWrap(True)
        root.addWidget(note)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        root.addWidget(bb)
        self._usage()
        self.cmb_history.currentIndexChanged.connect(self._usage)

    def _usage(self) -> None:
        if self.historian is None or not hasattr(self.historian, "stats"):
            self.lbl_usage.setText("")
            return
        size, oldest = self.historian.stats()
        text = tr("Ocupa {s} en disco.", s=_size_text(size))
        days = (time.time() - oldest) / 86400 if oldest else 0
        if days >= 1 and size:
            per_day = size / days
            keep = self.history_days
            text += " " + tr("Crece unos {d} por día", d=_size_text(per_day))
            text += (" " + tr("(≈ {t} con lo elegido).", t=_size_text(per_day * keep)) if keep else
                     " " + tr("(sin límite: revisa el espacio libre del disco)."))
        self.lbl_usage.setText(text)

    @property
    def history_days(self) -> int:
        return int(self.cmb_history.currentData())

    @property
    def export_days(self) -> int:
        return int(self.cmb_export.currentData())

    def _shorter(self, old: int, new: int) -> bool:
        return bool(new) and (not old or new < old)

    def accept(self, confirm: bool = True) -> None:
        s = self.exporter.settings
        if confirm and (self._shorter(s.history_days, self.history_days) or
                        self._shorter(s.retention_days, self.export_days)):
            if QMessageBox.question(self, tr("Guardado de datos"),
                                    tr("Con el nuevo plazo se borrarán los datos más antiguos (en la próxima "
                                       "limpieza, dentro de una hora como máximo). ¿Continuar?")) != QMessageBox.Yes:
                return
        apply_storage(self.exporter, self.historian, self.history_days, self.export_days)
        super().accept()


def apply_storage(exporter, historian, history_days: int, export_days: int) -> None:
    """Guarda los plazos (station.json) y los aplica al historial y a la exportación sin reiniciar."""
    exporter.reconfigure(exporter.settings.model_copy(update={"history_days": history_days,
                                                              "retention_days": export_days}))
    if historian is not None and hasattr(historian, "retention_days"):
        historian.retention_days = history_days
        historian._last_purge = 0.0  # la próxima escritura del monitoreo aplica el plazo nuevo
    exporter._last_purge = 0.0
