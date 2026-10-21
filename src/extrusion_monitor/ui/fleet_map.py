"""Dashboard global → Mapa de planta: cada línea en su ubicación física con el color de su estado (ideal para TV).

Se puede poner el plano de la planta de fondo y acomodar las líneas arrastrándolas (modo «Acomodar»). Doble clic
en una línea abre su detalle en «Líneas».
"""
from __future__ import annotations

import time
from pathlib import Path

from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QCheckBox, QFileDialog, QGraphicsItem, QGraphicsObject, QGraphicsPixmapItem, QGraphicsScene, QGraphicsView,
    QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget,
)

from ..i18n import tr
from ..plant_settings import PlantSettings
from . import theme

W, H = 200, 92
STATE_KEYS = {"running": "good", "assumed": "good", "slow": "warning", "microstop": "serious", "stopped": "critical"}


class LineItem(QGraphicsObject):
    moved = Signal(str, float, float)
    opened = Signal(str)

    def __init__(self, line_id: str, name: str):
        super().__init__()
        self.line_id, self.name = line_id, name
        self.color = QColor(theme.c("neutral"))
        self.lines = ["", ""]
        self.alarm = False
        self.blink = False
        self.setFlag(QGraphicsItem.ItemSendsGeometryChanges, True)
        self.setCursor(Qt.PointingHandCursor)
        self.setAcceptHoverEvents(True)

    def boundingRect(self) -> QRectF:
        return QRectF(-4, -4, W + 8, H + 8)

    def set_editable(self, on: bool) -> None:
        self.setFlag(QGraphicsItem.ItemIsMovable, on)
        self.setCursor(Qt.SizeAllCursor if on else Qt.PointingHandCursor)

    def paint(self, p: QPainter, _opt, _w=None) -> None:
        p.setRenderHint(QPainter.Antialiasing)
        border = QColor(theme.c("critical")) if self.alarm and not self.blink else self.color.darker(130)
        p.setPen(QPen(border, 4 if self.alarm else 2))
        fill = QColor(theme.c("surface"))
        p.setBrush(QBrush(fill))
        p.drawRoundedRect(QRectF(0, 0, W, H), 12, 12)
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(self.color))
        p.drawRoundedRect(QRectF(0, 0, 14, H), 7, 7)
        p.setPen(QColor(theme.c("title")))
        f = QFont()
        f.setPointSizeF(12)
        f.setBold(True)
        p.setFont(f)
        p.drawText(QRectF(22, 6, W - 28, 26), Qt.AlignLeft | Qt.AlignVCenter, self.name)
        f.setBold(False)
        f.setPointSizeF(10)
        p.setFont(f)
        p.setPen(self.color.darker(120))
        p.drawText(QRectF(22, 34, W - 28, 24), Qt.AlignLeft | Qt.AlignVCenter, self.lines[0])
        p.setPen(QColor(theme.c("text2")))
        p.drawText(QRectF(22, 60, W - 28, 24), Qt.AlignLeft | Qt.AlignVCenter, self.lines[1])

    def mouseReleaseEvent(self, e) -> None:
        super().mouseReleaseEvent(e)
        if self.flags() & QGraphicsItem.ItemIsMovable:
            self.moved.emit(self.line_id, self.pos().x(), self.pos().y())

    def mouseDoubleClickEvent(self, e) -> None:
        self.opened.emit(self.line_id)


class FleetMap(QWidget):
    open_line = Signal(str)

    def __init__(self, reader_fn, home: Path, settings_fn=None, allow=None):
        super().__init__()
        self.reader_fn = reader_fn
        self.home = Path(home)
        self.settings_fn = settings_fn  # FleetSettings (desconexión)
        self.allow = allow or (lambda _k: True)
        self.items: dict[str, LineItem] = {}
        self._blink = False
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        bar = QHBoxLayout()
        bar.addWidget(QLabel(f"<b style='font-size:16px; color:{theme.c('title')}'>{tr('Mapa de planta')}</b>"))
        bar.addSpacing(16)
        self.chk_edit = QCheckBox(tr("Acomodar (arrastra las líneas)"))
        self.chk_edit.toggled.connect(self._edit_toggled)
        bar.addWidget(self.chk_edit)
        self.btn_bg = QPushButton(tr("🗺 Plano de fondo…"))
        self.btn_bg.clicked.connect(self.choose_background)
        bar.addWidget(self.btn_bg)
        self.btn_fit = QPushButton(tr("⤢ Ajustar a la pantalla"))
        self.btn_fit.clicked.connect(self.fit)
        bar.addWidget(self.btn_fit)
        bar.addStretch(1)
        self.legend = QLabel(" ".join(f"<span style='color:{theme.c(k)}'>■</span> {tr(t)}&nbsp;&nbsp;" for k, t in (
            ("good", "En marcha"), ("warning", "Lento"), ("critical", "Detenida"), ("neutral", "Sin comunicación"))))
        bar.addWidget(self.legend)
        lay.addLayout(bar)
        self.scene = QGraphicsScene(self)
        self.view = QGraphicsView(self.scene)
        self.view.setRenderHint(QPainter.Antialiasing)
        self.view.setBackgroundBrush(QBrush(QColor(theme.c("page"))))
        lay.addWidget(self.view, 1)
        self.bg: QGraphicsPixmapItem | None = None
        self._load_background()

    def _load_background(self) -> None:
        if self.bg is not None:
            self.scene.removeItem(self.bg)
            self.bg = None
        path = PlantSettings.load(self.home).map_image
        pm = QPixmap(path) if path else QPixmap()
        if not pm.isNull():
            self.bg = self.scene.addPixmap(pm)
            self.bg.setZValue(-10)
            self.bg.setOpacity(0.55)

    def choose_background(self) -> None:
        if not self.allow("map"):
            return
        path, _ = QFileDialog.getOpenFileName(self, tr("Plano de la planta"), "", tr("Imágenes (*.png *.jpg *.jpeg *.bmp)"))
        if path:
            s = PlantSettings.load(self.home)
            s.map_image = path
            s.save(self.home)
            self._load_background()
            self.fit()

    def _edit_toggled(self, on: bool) -> None:
        if on and not self.allow("map"):
            self.chk_edit.setChecked(False)
            return
        for it in self.items.values():
            it.set_editable(on)

    def _moved(self, line_id: str, x: float, y: float) -> None:
        s = PlantSettings.load(self.home)
        name = self.items[line_id].name
        s.map_pos[name] = [x, y]
        s.save(self.home)

    def fit(self) -> None:
        rect = self.scene.itemsBoundingRect().adjusted(-30, -30, 30, 30)
        if rect.isValid():
            self.view.fitInView(rect, Qt.KeepAspectRatio)

    def refresh(self) -> None:
        reader = self.reader_fn()
        s = PlantSettings.load(self.home)
        now = time.time()
        offline_s = getattr(self.settings_fn() if self.settings_fn else None, "offline_s", None)
        lines = sorted(reader.lines.values(), key=lambda ln: ln.name)
        for lid in [k for k in self.items if k not in reader.lines]:
            self.scene.removeItem(self.items.pop(lid))
        new = False
        for i, ln in enumerate(lines):
            it = self.items.get(ln.line_id)
            if it is None:
                it = self.items[ln.line_id] = LineItem(ln.line_id, ln.name)
                it.moved.connect(self._moved)
                it.opened.connect(self.open_line.emit)
                it.set_editable(self.chk_edit.isChecked())
                self.scene.addItem(it)
                pos = s.map_pos.get(ln.name)
                it.setPos(*(pos if pos else (40 + (i % 4) * (W + 40), 40 + (i // 4) * (H + 40))))
                new = True
            it.name = ln.name
            conn = ln.connection(now, offline_s)
            st = ln.status
            state = (st.get("machine") or {}).get("state")
            oee = (st.get("kpis") or {}).get("oee")
            if conn in ("offline", "closed"):
                it.color = QColor(theme.c("neutral"))
                it.lines = [tr("Sin comunicación") if conn == "offline" else tr("Programa cerrado"), ""]
                it.alarm = False
            else:
                it.color = QColor(theme.c(STATE_KEYS.get(state, "info")))
                label = (st.get("machine") or {}).get("label") or (tr("Monitoreando") if st.get("monitoring") else "")
                it.lines = [tr(label) if label else "—",
                            (f"OEE {oee:.0f} %" if oee is not None else "OEE —")
                            + (f" · {st.get('n_alarms')} " + tr("alarmas") if st.get("n_alarms") else "")]
                it.alarm = bool(st.get("n_alarms"))
            it.update()
        if new:
            self.fit()

    def blink_tick(self) -> None:
        self._blink = not self._blink
        for it in self.items.values():
            if it.alarm:
                it.blink = self._blink
                it.update()

    def resizeEvent(self, e) -> None:
        super().resizeEvent(e)
        self.fit()
