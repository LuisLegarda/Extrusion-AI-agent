"""Página de reportes: lista de PDF/CSV generados, generar ahora y abrir."""
from __future__ import annotations

import time
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QHBoxLayout, QHeaderView, QLabel, QPushButton, QTableWidget, QTableWidgetItem, QToolButton, QVBoxLayout,
    QWidget,
)

from ..i18n import tr
from . import theme

if TYPE_CHECKING:
    from ..bootstrap import AppContext

MAX_FILES = 300


class ReportsPage(QWidget):
    def __init__(self, ctx: "AppContext", win):
        super().__init__()
        self.ctx = ctx
        self.win = win
        lay = QVBoxLayout(self)
        row = QHBoxLayout()
        row.addWidget(QLabel("<span style='font-size:16px'><b>Reportes generados</b></span>"))
        row.addStretch(1)
        self.btn_gen = QToolButton()
        self.btn_gen.setText("📄 Generar ahora")
        self.btn_gen.setPopupMode(QToolButton.InstantPopup)
        self.btn_gen.setMenu(win._report_menu)
        row.addWidget(self.btn_gen)
        for text, slot in (("⟳ Actualizar", self.refresh), ("📂 Abrir carpeta", self._open_dir),
                           ("⚙ Configurar reportes", lambda: win.open_setup("Reportes"))):
            b = QPushButton(text)
            b.clicked.connect(slot)
            row.addWidget(b)
        lay.addLayout(row)
        self.lbl = QLabel()
        self.lbl.setStyleSheet(f"color:{theme.c('muted')};")
        lay.addWidget(self.lbl)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Fecha", "Archivo", "Tipo", "Carpeta"])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.cellDoubleClicked.connect(self._open_row)
        lay.addWidget(self.table, 1)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(15000)

    def dirs(self) -> list[Path]:
        out = [Path(r.output_dir) for r in self.ctx.config.reports if r.output_dir]
        out.append(self.ctx.workspace.default_reports_dir())
        seen, res = set(), []
        for d in out:
            key = str(d.resolve()) if d.exists() else str(d)
            if key not in seen:
                seen.add(key)
                res.append(d)
        return res

    def refresh(self) -> None:
        if not self.isVisible():
            return
        files = []
        for d in self.dirs():
            if d.is_dir():
                files += [f for f in d.iterdir() if f.suffix.lower() in (".pdf", ".csv") and ".tmp" not in f.name]
        files.sort(key=lambda f: f.stat().st_mtime, reverse=True)
        files = files[:MAX_FILES]
        self.table.setRowCount(len(files))
        for i, f in enumerate(files):
            vals = [time.strftime("%Y-%m-%d %H:%M", time.localtime(f.stat().st_mtime)), f.name,
                    f.suffix[1:].upper(), str(f.parent)]
            for c, v in enumerate(vals):
                it = QTableWidgetItem(v)
                it.setData(Qt.UserRole, str(f))
                self.table.setItem(i, c, it)
        self.lbl.setText(tr("{n} archivos · doble clic para abrir · carpetas: {d}", n=len(files),
                            d=", ".join(str(d) for d in self.dirs())))

    def _open_row(self, row: int, _col: int) -> None:
        it = self.table.item(row, 0)
        if it is not None:
            QDesktopServices.openUrl(QUrl.fromLocalFile(it.data(Qt.UserRole)))

    def _open_dir(self) -> None:
        d = self.dirs()[0]
        d.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(d)))

    def showEvent(self, event) -> None:
        super().showEvent(event)
        QTimer.singleShot(0, self.refresh)
