"""Diagnóstico de lectura: prueba todas las variables visibles con todas las variantes de OCR."""
from __future__ import annotations

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (
    QApplication, QDialog, QDialogButtonBox, QHeaderView, QLabel, QTableWidget, QTableWidgetItem, QVBoxLayout,
)

from ..capture import crop
from ..config import AppConfig
from ..ocr.robust import RobustReader


class DiagnosisDialog(QDialog):
    def __init__(self, config: AppConfig, frame: np.ndarray, engine, visible: set, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Diagnóstico de lectura")
        self.resize(1000, 640)
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("Cada variable visible se lee con todas las variantes de preprocesado. "
                             "Un acuerdo alto significa lectura estable; bajo, que conviene ajustar la región."))
        cols = ["Variable", "Valor", "Acuerdo", "Otras lecturas", "Estado", "Recomendación"]
        tbl = QTableWidget(0, len(cols))
        tbl.setHorizontalHeaderLabels(cols)
        tbl.verticalHeader().setVisible(False)
        tbl.setEditTriggers(QTableWidget.NoEditTriggers)
        tbl.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        tbl.horizontalHeader().setStretchLastSection(True)
        lay.addWidget(tbl)
        self.summary = QLabel()
        lay.addWidget(self.summary)
        bb = QDialogButtonBox(QDialogButtonBox.Close)
        bb.button(QDialogButtonBox.Close).setText("Cerrar")
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)
        reader = RobustReader(engine)
        counts = {"OK": 0, "Débil": 0, "Falla": 0}
        for v in config.variables:
            if not v.numeric or not (v.page is None or v.page in visible):
                continue
            QApplication.processEvents()
            res = reader.read_number(crop(frame, v.region), v, None, lambda _: True, exhaustive=True)
            total = sum(res.candidates.values())
            agree = res.candidates.get(res.value, 0) if res.value is not None else 0
            pct = 100 * agree / max(res.tried, 1)
            if res.value is None:
                state, color, tip = "Falla", "#e53935", "Ninguna variante leyó un número: revisa que la región cubra el número."
            elif pct < 35 or total - agree > agree:
                state, color, tip = "Débil", "#f9a825", "Ajusta la región solo al número (sin unidad ni marco)."
            else:
                state, color, tip = "OK", "#43a047", ""
            if res.value is not None and v.valid_min is None and v.valid_max is None:
                tip = (tip + " " if tip else "") + "Define un rango válido para descartar lecturas imposibles."
            counts[state] += 1
            others = ", ".join(f"{k:g}×{n}" for k, n in res.candidates.items() if k != res.value)
            row = tbl.rowCount()
            tbl.insertRow(row)
            vals = [config.var_label(v), "—" if res.value is None else f"{res.value:g}",
                    f"{agree}/{res.tried} ({pct:.0f} %)", others, state, tip]
            for c, text in enumerate(vals):
                it = QTableWidgetItem(text)
                if c == 4:
                    it.setBackground(QBrush(QColor(color)))
                    it.setForeground(QBrush(QColor("white")))
                    it.setTextAlignment(Qt.AlignCenter)
                tbl.setItem(row, c, it)
        self.summary.setText(f"<b>{counts['OK']}</b> OK · <b>{counts['Débil']}</b> débiles · "
                             f"<b>{counts['Falla']}</b> sin lectura (solo variables de las pestañas visibles)")
