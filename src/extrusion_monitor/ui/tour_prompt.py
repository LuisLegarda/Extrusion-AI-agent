"""Aviso con cuenta regresiva antes de ejecutar un recorrido (no modal, siempre visible)."""
from __future__ import annotations

from typing import Callable

from PySide6.QtCore import Qt, QTimer
from ..i18n import tr
from . import theme
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout


class TourPrompt(QDialog):
    def __init__(self, name: str, reason: str, deadline: float, clock: Callable[[], float],
                 on_run: Callable[[], None], on_snooze: Callable[[], None], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Recorrido automático")
        self.setWindowFlag(Qt.WindowStaysOnTopHint, True)
        self.setModal(False)
        self.deadline = deadline
        self.clock = clock
        self._on_run, self._on_snooze = on_run, on_snooze
        self._done = False
        lay = QVBoxLayout(self)
        title = QLabel(tr("<b>Se ejecutará el recorrido «{n}»</b><br>{r}", n=name, r=reason))
        title.setWordWrap(True)
        lay.addWidget(title)
        self.lbl = QLabel()
        self.lbl.setStyleSheet("font-size: 22px; font-weight: bold;")
        self.lbl.setAlignment(Qt.AlignCenter)
        lay.addWidget(self.lbl)
        hint = QLabel("Si no respondes, se ejecuta al terminar la cuenta.")
        hint.setStyleSheet(f"color: {theme.c('muted')};")
        lay.addWidget(hint)
        row = QHBoxLayout()
        b = QPushButton("▶ Ejecutar ahora")
        b.clicked.connect(self._run)
        row.addWidget(b)
        b = QPushButton("⏸ Posponer")
        b.clicked.connect(self._snooze)
        row.addWidget(b)
        lay.addLayout(row)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(250)
        self._tick()

    def _tick(self) -> None:
        left = max(0.0, self.deadline - self.clock())
        self.lbl.setText(f"{left:.0f} s")

    def _finish(self, action: Callable[[], None]) -> None:
        if not self._done:
            self._done = True
            self.timer.stop()
            action()
        self.hide()
        self.deleteLater()

    def _run(self) -> None:
        self._finish(self._on_run)

    def _snooze(self) -> None:
        self._finish(self._on_snooze)

    def dismiss(self) -> None:
        """El aviso ya no está pendiente (se ejecutó o cambió la configuración)."""
        self._finish(lambda: None)

    def reject(self) -> None:  # Esc / cerrar la ventana = posponer
        self._snooze()
