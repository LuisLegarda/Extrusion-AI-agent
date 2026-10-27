"""Diálogo «Exportar»: elige el formato (CSV, Excel o software estadístico) y, si aplica, qué se exporta.

Todos los botones de exportar tablas del monitor y del dashboard pasan por `export_table()`.
"""
from __future__ import annotations

import time
from typing import Callable, Optional, Sequence

from PySide6.QtWidgets import (
    QApplication, QButtonGroup, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QLabel,
    QRadioButton, QVBoxLayout,
)

from ..i18n import lang, tr
from ..tabular import FORMATS, stat_text, with_suffix, write_table

FORMAT_HELP = {
    "csv": "Texto separado por «;» con coma decimal; se abre con Excel u otras hojas de cálculo.",
    "xlsx": "Libro de Excel con números y fechas reales, encabezado fijo y filtros.",
    "stat": "Separado por tabulaciones, punto decimal y «*» en los datos faltantes, con nombres de columna "
            "válidos. Se pega directo en la hoja de Minitab (Ctrl+V) o se abre con Archivo › Abrir.",
}
_last = {"fmt": "csv", "clip": True}  # lo último elegido en esta sesión

Build = Callable[[str], tuple[Sequence[str], list]]  # contenido -> (encabezados, filas)


class ExportDialog(QDialog):
    def __init__(self, parent=None, title: str = "Exportar", contents: Optional[list[tuple[str, str]]] = None):
        super().__init__(parent)
        self.setWindowTitle(tr(title))
        lay = QVBoxLayout(self)
        form = QFormLayout()
        self.cmb_content = QComboBox()
        for key, label in contents or []:
            self.cmb_content.addItem(tr(label), key)
        if contents and len(contents) > 1:
            form.addRow(tr("Exportar:"), self.cmb_content)
        lay.addLayout(form)
        lay.addWidget(QLabel(f"<b>{tr('Formato')}</b>"))
        self.group = QButtonGroup(self)
        self.radios: dict[str, QRadioButton] = {}
        for key, (label, _ext, _flt) in FORMATS.items():
            rb = QRadioButton(tr(label))
            rb.setToolTip(tr(FORMAT_HELP[key]))
            self.group.addButton(rb)
            self.radios[key] = rb
            lay.addWidget(rb)
            hint = QLabel(tr(FORMAT_HELP[key]))
            hint.setWordWrap(True)
            hint.setObjectName("muted")
            hint.setContentsMargins(24, 0, 0, 4)
            lay.addWidget(hint)
        self.chk_clip = QCheckBox(tr("Copiar también al portapapeles para pegarlo en Minitab"))
        self.chk_clip.setChecked(_last["clip"])
        self.chk_clip.setContentsMargins(24, 0, 0, 0)
        lay.addWidget(self.chk_clip)
        self.radios.get(_last["fmt"], self.radios["csv"]).setChecked(True)
        self.group.buttonToggled.connect(lambda *_: self._sync())
        self._sync()
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText(tr("Exportar…"))
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)
        self.setMinimumWidth(460)

    def _sync(self) -> None:
        self.chk_clip.setEnabled(self.fmt == "stat")

    @property
    def fmt(self) -> str:
        return next((k for k, rb in self.radios.items() if rb.isChecked()), "csv")

    @property
    def content(self) -> str:
        return self.cmb_content.currentData() or ""


def export_table(parent, title: str, base_name: str, build: Build, contents: Optional[list[tuple[str, str]]] = None,
                 path: Optional[str] = None, fmt: Optional[str] = None, content: Optional[str] = None,
                 clipboard: Optional[bool] = None) -> Optional[str]:
    """Pregunta formato (y contenido), luego dónde guardar, y escribe la tabla. Devuelve la ruta o None.

    `path`, `fmt`, `content` y `clipboard` permiten llamarla sin diálogos (pruebas y exportaciones automáticas).
    """
    if fmt is None:
        dlg = ExportDialog(parent, title, contents)
        if dlg.exec() != QDialog.Accepted:
            return None
        fmt, content, clipboard = dlg.fmt, dlg.content, dlg.chk_clip.isChecked()
        _last.update(fmt=fmt, clip=clipboard)
    if content is None:
        content = contents[0][0] if contents else ""
    if not path:
        name = f"{base_name}_{time.strftime('%Y%m%d_%H%M')}{FORMATS[fmt][1]}"
        path, _ = QFileDialog.getSaveFileName(parent, tr(title), name, tr(FORMATS[fmt][2]))
        if not path:
            return None
    path = with_suffix(path, fmt)
    header, rows = build(content)
    write_table(path, header, rows, fmt, lang(), sheet=tr(title)[:31])
    if fmt == "stat" and clipboard:
        app = QApplication.instance()
        if app is not None:
            app.clipboard().setText(stat_text(header, rows))
    return path
