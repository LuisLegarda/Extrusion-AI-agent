"""Inicio: tarjetas de estado compactas (marcha, paros, por identificar, alarmas, calidad, OEE) y dona de causas de paro."""
from __future__ import annotations

import math
from typing import Optional

from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QFrame, QGridLayout, QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget

from ..i18n import tr
from . import icons, theme

ICON_PX = 16  # ícono dentro de un recuadro de 28 px (la mitad de la referencia)
BADGE_PX = 28


def soft(color: str, alpha: int = 38) -> str:
    c = QColor(color)
    return f"rgba({c.red()},{c.green()},{c.blue()},{alpha})"


class StatusTile(QFrame):
    """Tarjeta compacta: ícono en recuadro suave, valor y descripción; un clic lleva al detalle."""

    clicked = Signal(str)

    def __init__(self, key: str, icon: str, label: str, target: str, color_key: str = "accent"):
        super().__init__()
        self.key, self.target, self.icon_name = key, target, icon
        self.setObjectName("statusTile")
        self.setCursor(Qt.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setFixedHeight(66)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 8, 12, 8)
        lay.setSpacing(10)
        self.badge = QLabel()
        self.badge.setFixedSize(BADGE_PX, BADGE_PX)
        self.badge.setAlignment(Qt.AlignCenter)
        lay.addWidget(self.badge, 0, Qt.AlignVCenter)
        col = QVBoxLayout()
        col.setSpacing(0)
        self.value = QLabel("—")
        self.value.setObjectName("statusValue")
        self.label = QLabel(tr(label))
        self.label.setObjectName("statusLabel")
        self.sub = QLabel("")
        self.sub.setObjectName("statusSub")
        col.addWidget(self.value)
        col.addWidget(self.label)
        col.addWidget(self.sub)
        lay.addLayout(col, 1)
        self.set_color(theme.c(color_key))

    def set_color(self, color: str) -> None:
        self.color = color
        self.badge.setPixmap(icons.pixmap(self.icon_name, color, ICON_PX))
        self.badge.setStyleSheet(f"background:{soft(color)}; border-radius:7px;")
        self.value.setStyleSheet(f"color:{color};")

    def set(self, value: str, sub: str = "", color: Optional[str] = None, icon: Optional[str] = None,
            label: Optional[str] = None) -> None:
        self.value.setText(value)
        self.sub.setText(sub)
        if label is not None:
            self.label.setText(label)
        if icon is not None:
            self.icon_name = icon
        self.set_color(color or self.color)

    def mousePressEvent(self, event) -> None:
        self.clicked.emit(self.target)
        super().mousePressEvent(event)


class StatusBar(QWidget):
    """Fila de tarjetas de estado arriba del tablero de Inicio."""

    navigate = Signal(str)

    def __init__(self):
        super().__init__()
        lay = QGridLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setHorizontalSpacing(10)
        self.tiles = {
            "state": StatusTile("state", "play", "Estado de la línea", "kpi", "neutral"),
            "stops": StatusTile("stops", "pause", "Paros en el turno", "problems", "serious"),
            "pending": StatusTile("pending", "clock", "Paros por identificar", "problems", "warning_text"),
            "alarms": StatusTile("alarms", "alert", "Alarmas activas", "events", "critical"),
            "quality": StatusTile("quality", "check", "Calidad del turno", "kpi", "good_text"),
            "oee": StatusTile("oee", "oee", "OEE del turno", "kpi", "accent"),
        }
        for i, t in enumerate(self.tiles.values()):
            t.clicked.connect(self.navigate.emit)
            lay.addWidget(t, 0, i)
            lay.setColumnStretch(i, 1)

    def __getitem__(self, key: str) -> StatusTile:
        return self.tiles[key]


class Donut(QWidget):
    """Dona con leyenda: reparto de un total (p. ej. minutos de paro por causa)."""

    def __init__(self):
        super().__init__()
        self.rows: list[tuple[str, float, str]] = []  # (nombre, valor, color)
        self.center = ""
        self.center_sub = ""
        self.empty = tr("Sin paros en el turno")
        self.setMinimumHeight(150)

    def set_data(self, rows: list[tuple[str, float, str]], center: str, center_sub: str = "") -> None:
        self.rows = [r for r in rows if r[1] > 0]
        self.center, self.center_sub = center, center_sub
        self.update()

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        if not self.rows:
            p.setPen(QColor(theme.c("muted")))
            p.drawText(self.rect(), Qt.AlignCenter | Qt.TextWordWrap, self.empty)
            p.end()
            return
        side = min(h - 8, w * 0.45)
        ring = max(12.0, side * 0.16)
        rect = QRectF(4 + ring / 2, (h - side) / 2 + ring / 2, side - ring, side - ring)
        total = sum(v for _, v, _ in self.rows)
        start = 90 * 16
        for _name, v, color in self.rows:
            span = -int(round(360 * 16 * v / total))
            p.setPen(QPen(QColor(color), ring, Qt.SolidLine, Qt.FlatCap))
            p.drawArc(rect, start, span)
            start += span
        p.setPen(QColor(theme.c("title")))
        f = p.font()
        f.setPointSizeF(max(9.0, side / 9))
        f.setBold(True)
        p.setFont(f)
        p.drawText(rect.adjusted(0, -side * 0.08, 0, -side * 0.08), Qt.AlignCenter, self.center)
        f.setPointSizeF(max(7.5, side / 16))
        f.setBold(False)
        p.setFont(f)
        p.setPen(QColor(theme.c("muted")))
        p.drawText(rect.adjusted(0, side * 0.18, 0, side * 0.18), Qt.AlignCenter, self.center_sub)
        # leyenda
        x0 = 4 + side + 14
        lw = w - x0 - 4
        f.setPointSizeF(9)
        p.setFont(f)
        row_h = min(22.0, h / max(1, len(self.rows)))
        y = (h - row_h * len(self.rows)) / 2
        fm = p.fontMetrics()
        for name, v, color in self.rows:
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(color))
            p.drawEllipse(QRectF(x0, y + row_h / 2 - 4.5, 9, 9))
            pct = f"{100 * v / total:.0f} %"
            p.setPen(QColor(theme.c("text")))
            p.drawText(QRectF(x0 + 15, y, lw - 60, row_h), Qt.AlignLeft | Qt.AlignVCenter,
                       fm.elidedText(name, Qt.ElideRight, int(max(10, lw - 64))))
            p.setPen(QColor(theme.c("text2")))
            p.drawText(QRectF(x0, y, lw, row_h), Qt.AlignRight | Qt.AlignVCenter, pct)
            y += row_h
        p.end()


def fmt_hm(seconds: float) -> str:
    m = int(round(seconds / 60))
    return f"{m // 60}h {m % 60:02d}m" if m >= 60 else f"{m} min"


def downtime_rows(records: list[dict], stop_s: float, max_rows: int = 6) -> tuple[list[tuple[str, float, str]], float]:
    """Minutos de paro por causa en el turno (los planeados aparte) más lo que falta identificar."""
    by: dict[str, float] = {}
    for r in records:
        if r.get("kind") != "downtime":
            continue
        name = (r.get("reason") or r.get("category") or tr("Otra")) + (tr(" (planeado)") if r.get("planned") else "")
        by[name] = by.get(name, 0.0) + float(r.get("duration_s") or 0)
    items = sorted(by.items(), key=lambda kv: -kv[1])
    if len(items) > max_rows - 1:
        other = sum(v for _, v in items[max_rows - 2:])
        items = items[:max_rows - 2] + [(tr("Otras"), other)]
    classified = sum(by.values())
    unknown = max(0.0, stop_s - classified)
    rows = [(n, v, theme.series(i)) for i, (n, v) in enumerate(items)]
    if unknown >= 30:
        rows.append((tr("Sin identificar"), unknown, theme.c("neutral")))
    return rows, max(stop_s, classified)


def fmt_pct(v: Optional[float]) -> str:
    return "—" if v is None or (isinstance(v, float) and math.isnan(v)) else f"{100 * v:.0f} %"
