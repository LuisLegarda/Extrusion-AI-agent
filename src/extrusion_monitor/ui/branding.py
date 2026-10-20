"""Identidad de la estación: logo de la empresa, texto propio y número de línea (esquina superior izquierda).

Es propia del equipo (no de la receta): se guarda en `<datos>/branding/` y viaja con los respaldos.
"""
from __future__ import annotations

import json
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout,
    QWidget,
)

from ..i18n import tr
from . import theme

LOGO_MAX_W, LOGO_MAX_H = 190, 80


@dataclass
class Branding:
    logo: str = ""  # nombre del archivo dentro de branding/
    text: str = ""  # p. ej. el nombre de la planta o del área
    line: str = ""  # p. ej. «Línea 3»

    @staticmethod
    def folder(home: Path) -> Path:
        return Path(home) / "branding"

    @classmethod
    def load(cls, home: Path) -> "Branding":
        try:
            data = json.loads((cls.folder(home) / "branding.json").read_text(encoding="utf-8"))
            return cls(**{k: str(v) for k, v in data.items() if k in ("logo", "text", "line")})
        except (OSError, ValueError, TypeError):
            return cls()

    def save(self, home: Path) -> None:
        d = self.folder(home)
        d.mkdir(parents=True, exist_ok=True)
        tmp = d / "branding.json.tmp"
        tmp.write_text(json.dumps(asdict(self), ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(d / "branding.json")

    def logo_path(self, home: Path) -> Optional[Path]:
        if not self.logo:
            return None
        p = self.folder(home) / self.logo
        return p if p.exists() else None


def header_widget(home: Path) -> QWidget:
    """Encabezado de la barra lateral: logo (o el nombre del programa), texto propio y línea."""
    b = Branding.load(home)
    w = QWidget()
    w.setObjectName("brand")
    lay = QVBoxLayout(w)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(2)
    logo = b.logo_path(home)
    pm = QPixmap(str(logo)) if logo else QPixmap()
    if not pm.isNull():
        img = QLabel()
        img.setPixmap(pm.scaled(LOGO_MAX_W, LOGO_MAX_H, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        img.setAlignment(Qt.AlignCenter)
        lay.addWidget(img)
    else:
        lay.addWidget(_center(QLabel(f"<div style='font-size:20px; color:{theme.c('accent')}'><b>⫶⫶ Extrusion</b>"
                                     "</div>")))
    sub = b.text or ("" if not pm.isNull() else tr("Monitor de línea"))
    if sub:
        lab = _center(QLabel(sub))
        lab.setWordWrap(True)
        lab.setStyleSheet(f"color:{theme.c('muted')};")
        lay.addWidget(lab)
    if b.line:
        lab = _center(QLabel(f"<b style='font-size:16px; color:{theme.c('title')}'>{b.line}</b>"))
        lay.addWidget(lab)
    return w


def _center(lbl: QLabel) -> QLabel:
    lbl.setAlignment(Qt.AlignCenter)
    return lbl


class BrandingDialog(QDialog):
    def __init__(self, home: Path, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Identidad de la estación")
        self.home = Path(home)
        self.b = Branding.load(home)
        self._new_logo: Optional[str] = None  # archivo elegido (se copia al aceptar)
        self._remove_logo = False
        root = QVBoxLayout(self)
        intro = QLabel("Logo de la empresa, un texto propio (p. ej. la planta o el área) y el número de línea. "
                       "Se muestran arriba a la izquierda del programa. Son de este equipo, no de la receta.")
        intro.setWordWrap(True)
        root.addWidget(intro)
        f = QFormLayout()
        self.preview = QLabel()
        self.preview.setFixedSize(LOGO_MAX_W + 10, LOGO_MAX_H + 10)
        self.preview.setAlignment(Qt.AlignCenter)
        self.preview.setStyleSheet("border:1px dashed #888;")
        row = QHBoxLayout()
        row.addWidget(self.preview)
        col = QVBoxLayout()
        b1 = QPushButton("Elegir imagen…")
        b1.clicked.connect(self._choose)
        b2 = QPushButton("Quitar logo")
        b2.clicked.connect(self._clear)
        col.addWidget(b1)
        col.addWidget(b2)
        col.addStretch()
        row.addLayout(col)
        f.addRow("Logo", row)
        self.ed_text = QLineEdit(self.b.text)
        self.ed_text.setPlaceholderText(tr("p. ej. Planta Monterrey · Extrusión"))
        f.addRow("Texto", self.ed_text)
        self.ed_line = QLineEdit(self.b.line)
        self.ed_line.setPlaceholderText(tr("p. ej. Línea 3"))
        f.addRow("Número de línea", self.ed_line)
        root.addLayout(f)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText("Guardar")
        bb.button(QDialogButtonBox.Cancel).setText("Cancelar")
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        root.addWidget(bb)
        self._show(self.b.logo_path(self.home))

    def _show(self, path: Optional[Path]) -> None:
        pm = QPixmap(str(path)) if path else QPixmap()
        if pm.isNull():
            self.preview.setPixmap(QPixmap())
            self.preview.setText(tr("sin logo"))
        else:
            self.preview.setPixmap(pm.scaled(LOGO_MAX_W, LOGO_MAX_H, Qt.KeepAspectRatio, Qt.SmoothTransformation))

    def _choose(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, tr("Logo de la empresa"), "",
                                              tr("Imágenes (*.png *.jpg *.jpeg *.bmp *.svg)"))
        if path:
            self.set_logo(path)

    def set_logo(self, path: str) -> None:
        self._new_logo, self._remove_logo = path, False
        self._show(Path(path))

    def _clear(self) -> None:
        self._new_logo, self._remove_logo = None, True
        self._show(None)

    def accept(self) -> None:
        d = Branding.folder(self.home)
        d.mkdir(parents=True, exist_ok=True)
        if self._remove_logo:
            self.b.logo = ""
        if self._new_logo:
            name = "logo" + Path(self._new_logo).suffix.lower()
            for old in d.glob("logo.*"):
                old.unlink(missing_ok=True)
            shutil.copy2(self._new_logo, d / name)
            self.b.logo = name
        self.b.text = self.ed_text.text().strip()
        self.b.line = self.ed_line.text().strip()
        self.b.save(self.home)
        super().accept()
