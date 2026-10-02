"""Dock: barra compacta siempre visible que queda sobre el HMI al minimizar el programa.

* Flota encima del HMI (no cambia su tamaño) y se excluye de la captura, así que no afecta la lectura.
* Muestra el estado de la máquina y los indicadores elegidos (los mismos tipos que el tablero de Inicio).
* Al acercar el mouse se desvanece y deja pasar los clics al HMI; la agarradera (⠿) siempre responde:
  desde ahí se arrastra, y con doble clic o el botón ⤢ se restaura el programa.
* Al aparecer una alarma parpadea y muestra el mensaje.
* Durante los clics de un recorrido deja pasar el clic (no estorba aunque quede sobre un botón).
"""
from __future__ import annotations

import time
from typing import Optional

from PySide6.QtCore import QPoint, QRect, Qt, QTimer, Signal
from PySide6.QtGui import QCursor, QGuiApplication
from PySide6.QtWidgets import QBoxLayout, QFrame, QLabel, QToolButton, QVBoxLayout, QWidget

from .. import navigation
from ..analysis.kpis import KPIS, snapshot_kpis
from ..analysis.oee import STATE_LABELS
from ..analysis.rules import Level
from ..config import KPI_KINDS, DockSettings
from ..engine import MonitorEngine, Snapshot
from ..i18n import tr, translate_text
from . import theme
from .common import SeriesCache
from .home_page import BUILTIN_TILES, KPI_INFO, GaugeCard
from .home_tiles import KpiTrendTile, KpiValueTile, make_var_tile
from .kpi_dashboard import STATE_COLORS, Gauge

THICKNESS = {"small": 96, "medium": 132, "large": 184}  # grosor del dock (px)
UNIT = {"small": 118, "medium": 150, "large": 200}  # largo de un indicador de ancho 1 (px)
VALUE_PX = {"small": 21, "medium": 28, "large": 38}  # tamaño del número en los indicadores de valor
GHOST_OPACITY = 0.14
ALERT_S = 12.0


class DockWindow(QWidget):
    restore = Signal()

    def __init__(self, engine: MonitorEngine, workspace=None):
        super().__init__(None, Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
                         | Qt.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WA_ShowWithoutActivating)  # no le quita el foco al HMI
        self.setObjectName("dock")
        self.engine = engine
        self.workspace = workspace
        self.series = SeriesCache(engine)
        self._ghost = False
        self._drag: Optional[QPoint] = None
        self._last = 0.0
        self._alarm_keys: Optional[set] = None
        self._alert_until = 0.0
        self._alert_msg = ""
        self._blink = False
        self._screen_geo: Optional[QRect] = None
        self.kpi_widgets: dict[str, list] = {}
        self.var_tiles: list = []
        self._outer = QVBoxLayout(self)
        self._outer.setContentsMargins(0, 0, 0, 0)
        self.frame: Optional[QFrame] = None
        self.rebuild()
        self.poll = QTimer(self)
        self.poll.timeout.connect(self._poll)
        self.poll.start(150)
        self.blink = QTimer(self)
        self.blink.timeout.connect(self._blink_tick)
        self.blink.start(500)

    @property
    def cfg(self) -> DockSettings:
        return self.engine.config.dock

    @property
    def horizontal(self) -> bool:
        return self.cfg.edge in ("top", "bottom")

    # --- construcción ---------------------------------------------------------------------
    def rebuild(self) -> None:
        cfg = self.cfg
        if self.frame is not None:
            self._outer.removeWidget(self.frame)
            self.frame.deleteLater()
        self.kpi_widgets, self.var_tiles = {}, []
        thick, unit = THICKNESS[cfg.size], UNIT[cfg.size]
        self.frame = QFrame()
        self.frame.setObjectName("dockFrame")
        lay = QBoxLayout(QBoxLayout.LeftToRight if self.horizontal else QBoxLayout.TopToBottom, self.frame)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.setSpacing(4)

        # agarradera: siempre responde al mouse (arrastrar, restaurar)
        self.handle = QFrame()
        hl = QBoxLayout(QBoxLayout.TopToBottom if self.horizontal else QBoxLayout.LeftToRight, self.handle)
        hl.setContentsMargins(2, 2, 2, 2)
        grip = QLabel("⠿")
        grip.setAlignment(Qt.AlignCenter)
        grip.setStyleSheet(f"font-size:20px; color:{theme.c('muted')};")
        grip.setCursor(Qt.SizeAllCursor)
        hl.addWidget(grip, 1)
        btn = QToolButton()
        btn.setText("⤢")
        btn.setToolTip("Restaurar el programa")
        btn.clicked.connect(self.restore.emit)
        hl.addWidget(btn)
        self.handle.setToolTip("Arrastra para mover el dock · doble clic para restaurar el programa")
        self.handle.setFixedSize(*((34, thick - 8) if self.horizontal else (unit - 8, 34)))
        lay.addWidget(self.handle)

        # estado de la máquina, receta y alarmas (siempre)
        self.chip = QLabel("—")
        self.chip.setTextFormat(Qt.RichText)
        self.chip.setWordWrap(True)
        self.chip.setAlignment(Qt.AlignCenter)
        self.chip.setObjectName("dockChip")  # fondo propio: se lee también cuando el dock parpadea en rojo
        self.chip.setStyleSheet(f"#dockChip {{ background:{theme.c('surface')}; border-radius:6px; }}")
        self.chip.setFixedSize(*((max(150, unit), thick - 8) if self.horizontal else (unit - 8, 78)))
        lay.addWidget(self.chip)

        for tile in cfg.tiles:
            w = self._make_tile(tile)
            if w is None:
                continue
            # Horizontal: el ancho del indicador son sus unidades. Vertical: una columna de mosaicos iguales.
            length = unit * max(1, min(tile.width, 4))
            w.setFixedSize(*((length, thick - 8) if self.horizontal else (unit - 8, thick - 8)))
            w.setCursor(Qt.ArrowCursor)
            lay.addWidget(w)
        self._outer.addWidget(self.frame)
        self._style()
        self.adjustSize()
        if self.isVisible():
            self.place()
            if self.engine.last is not None:
                self.update_snapshot(self.engine.last, force=True)

    def _make_tile(self, tile) -> Optional[QWidget]:
        compact = self.cfg.size == "small"
        k = tile.kind
        if k == "var":
            w = make_var_tile(tile, self.engine.config, self.series)
            if w.plot is not None:
                w.plot.setMinimumHeight(30)
            if w.gauge is not None:
                w.gauge.setMinimumSize(40, 40)
            if w.lbl_info is not None and (compact or w.gauge is not None):
                w.lbl_info.hide()  # el gauge ya muestra valor y referencia: se le deja todo el espacio
            self.var_tiles.append(w)
        elif k in KPI_KINDS:
            title = tr(tile.title or BUILTIN_TILES[k])
            if tile.kpi_chart == "gauge":
                _t, unit, (low, high), (vmin, vmax), dec = KPIS[k]
                w = GaugeCard("", title, Gauge(low, high, vmin=vmin, vmax=vmax, unit=unit, decimals=dec,
                                               needle=False), KPI_INFO[k][1])
                w.gauge.setMinimumSize(40, 40)
                w.setToolTip("")
            elif tile.kpi_chart == "value":
                w = KpiValueTile(tile, title, "")
            else:
                w = KpiTrendTile(tile, title, "", self.engine)
                w.plot.setMinimumHeight(30)
            if compact or tile.kpi_chart == "gauge":
                w.sub.hide()
            self.kpi_widgets.setdefault(k, []).append(w)
        else:
            return None  # el dock solo lleva indicadores y variables
        w.layout().setContentsMargins(5, 3, 5, 3)
        w.value_px = VALUE_PX[self.cfg.size]
        title = w.findChild(QLabel)  # título más chico que en el tablero
        if title is not None:
            title.setText(title.text().replace("font-size:14px", "font-size:11px"))
        return w

    def _style(self, alert: bool = False) -> None:
        snap = self.engine.last
        level = snap.overall if snap is not None else Level.OK
        if alert:
            border, bg = theme.c("critical"), (theme.c("critical") if self._blink else theme.c("surface"))
            width = 3
        else:
            border = theme.c("critical" if level >= Level.ALARM else ("warning" if level >= Level.WARN else "accent"))
            bg, width = theme.c("surface"), 2
        self.frame.setStyleSheet(f"#dockFrame {{ background:{bg}; border:{width}px solid {border}; "
                                 f"border-radius:8px; }}")

    # --- posición ---------------------------------------------------------------------------
    def _saved_pos(self) -> Optional[tuple[int, int]]:
        if self.workspace is None:
            return None
        pos = self.workspace.load_state().get("dock_pos")
        return (int(pos[0]), int(pos[1])) if isinstance(pos, list) and len(pos) == 2 else None

    def _save_pos(self, pos: Optional[tuple[int, int]]) -> None:
        if self.workspace is None:
            return
        state = self.workspace.load_state()
        if pos is None:
            state.pop("dock_pos", None)
        else:
            state["dock_pos"] = [int(pos[0]), int(pos[1])]
        self.workspace.save_state(state)

    def edge_pos(self, geo: QRect) -> QPoint:
        """Posición por defecto: centrado en el borde elegido."""
        w, h = self.width(), self.height()
        edge = self.cfg.edge
        if edge == "top":
            return QPoint(geo.x() + (geo.width() - w) // 2, geo.y())
        if edge == "bottom":
            return QPoint(geo.x() + (geo.width() - w) // 2, geo.y() + geo.height() - h)
        if edge == "left":
            return QPoint(geo.x(), geo.y() + (geo.height() - h) // 2)
        return QPoint(geo.x() + geo.width() - w, geo.y() + (geo.height() - h) // 2)

    def place(self, geo: Optional[QRect] = None) -> None:
        if geo is not None:
            self._screen_geo = geo
        geo = self._screen_geo or QGuiApplication.primaryScreen().availableGeometry()
        self.adjustSize()
        saved = self._saved_pos()
        if saved is not None:
            x = min(max(saved[0], geo.x()), geo.x() + geo.width() - 40)
            y = min(max(saved[1], geo.y()), geo.y() + geo.height() - 40)
            self.move(x, y)
        else:
            self.move(self.edge_pos(geo))

    def reset_position(self) -> None:
        self._save_pos(None)
        if self.isVisible():
            self.place()

    # --- datos ------------------------------------------------------------------------------
    def update_snapshot(self, snap: Snapshot, force: bool = False) -> None:
        now = time.monotonic()
        if not force and now - self._last < 1.0:
            return
        self._last = now
        eng = self.engine
        kp = dict(eng.kpis or {})
        try:
            kp.update(snapshot_kpis(eng, snap))  # los que salen del ciclo actual, al momento
        except Exception:
            pass
        for key, widgets in self.kpi_widgets.items():
            for w in widgets:
                w.set(kp.get(key), "")
        for w in self.var_tiles:
            w.update_snapshot(snap)
        self._alarms(snap)
        self._chip(snap)

    def _alarms(self, snap: Snapshot) -> None:
        alarms = {(f.rule, f.var_id): f for f in snap.findings if f.level >= Level.ALARM}
        keys = set(alarms)
        if self._alarm_keys is not None and self.cfg.alarm_alert:
            new = keys - self._alarm_keys
            if new:
                self._alert_msg = alarms[next(iter(new))].message
                self._alert_until = time.monotonic() + ALERT_S
        self._alarm_keys = keys

    def alerting(self) -> bool:
        return time.monotonic() < self._alert_until

    def _chip(self, snap: Snapshot) -> None:
        eng = self.engine
        if self.alerting():
            self.chip.setText(f"<b style='color:{theme.c('critical')}'>▲ {tr('ALARMA')}</b><br>"
                              f"<span style='font-size:11px'>{translate_text(self._alert_msg)[:110]}</span>")
            return
        res = eng.kpi_oee
        cur = res.intervals[-1] if res is not None and res.intervals else None
        if cur is not None:
            state = (f"<b style='font-size:15px; color:{STATE_COLORS[cur.state]}'>● "
                     f"{tr(STATE_LABELS[cur.state])}</b>")
        elif eng.running:
            state = f"<b style='font-size:14px; color:{theme.c('good')}'>● {tr('Monitoreando')}</b>"
        else:
            state = f"<b style='font-size:14px; color:{theme.c('muted')}'>● {tr('Monitoreo detenido')}</b>"
        na = sum(f.level >= Level.ALARM for f in snap.findings)
        nw = sum(f.level == Level.WARN for f in snap.findings)
        if na or nw:
            alarms = (f"<b style='color:{theme.c('critical')}'>▲ {na}</b> · "
                      f"<b style='color:{theme.c('warning_text')}'>{nw}</b>")
        else:
            alarms = f"<span style='color:{theme.c('good_text')}'>✔</span>"
        lines = [state, f"<span style='font-size:11px; color:{theme.c('text2')}'>{snap.recipe or '—'}</span>", alarms]
        if snap.error:
            lines.append(f"<span style='font-size:10px; color:{theme.c('critical')}'>"
                         f"{translate_text(snap.error)[:60]}</span>")
        self.chip.setText("<br>".join(lines))

    def _blink_tick(self) -> None:
        if not self.isVisible():
            return
        if self.alerting():
            self._blink = not self._blink
            self._style(alert=True)
        else:
            if self._blink or self._alert_msg:
                self._blink, self._alert_msg = False, ""
                if self.engine.last is not None:
                    self._chip(self.engine.last)
            self._style()

    # --- mouse: fantasma al acercarse, arrastre desde la agarradera --------------------------
    def _in_handle(self, gpos: QPoint) -> bool:
        return QRect(self.handle.mapToGlobal(QPoint(0, 0)), self.handle.size()).contains(gpos)

    def _poll(self) -> None:
        if not self.isVisible():
            return
        pos = QCursor.pos()
        hold = time.monotonic() < navigation.overlay_hold_until  # un recorrido está haciendo clic
        over = self.frameGeometry().contains(pos) and not self._in_handle(pos)
        ghost = hold or (self.cfg.ghost_on_hover and over and self._drag is None)
        self.set_ghost(ghost)

    def set_ghost(self, on: bool) -> None:
        """Casi transparente y deja pasar los clics a lo que está debajo."""
        if on == self._ghost:
            return
        self._ghost = on
        self.setWindowOpacity(GHOST_OPACITY if on else 1.0)
        if not navigation.set_click_through(int(self.winId()), on):
            self.setAttribute(Qt.WA_TransparentForMouseEvents, on)  # fuera de Windows: solo dentro del programa

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton and self._in_handle(event.globalPosition().toPoint()):
            self._drag = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self._drag is not None:
            self.move(event.globalPosition().toPoint() - self._drag)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        self.end_drag()
        super().mouseReleaseEvent(event)

    def end_drag(self) -> None:
        if self._drag is None:
            return
        self._drag = None
        geo = self._screen_geo or QGuiApplication.primaryScreen().availableGeometry()
        home = self.edge_pos(geo)
        # Soltarlo cerca de su lugar en el borde lo vuelve a anclar ahí; si no, recuerda la posición.
        if (self.pos() - home).manhattanLength() < 40:
            self._save_pos(None)
            self.move(home)
        else:
            self._save_pos((self.x(), self.y()))

    def mouseDoubleClickEvent(self, event) -> None:
        self.restore.emit()

    # --- ciclo de vida ----------------------------------------------------------------------
    def showEvent(self, event) -> None:
        super().showEvent(event)
        hwnd = int(self.winId())
        navigation.exclude_window_from_capture(hwnd)  # el dock no aparece en la lectura del HMI
        navigation.OVERLAY_HWNDS.add(hwnd)
        self._ghost = False
        self.setWindowOpacity(1.0)

    def hideEvent(self, event) -> None:
        navigation.OVERLAY_HWNDS.discard(int(self.winId()))
        super().hideEvent(event)

    def closeEvent(self, event) -> None:
        self.poll.stop()
        self.blink.stop()
        navigation.OVERLAY_HWNDS.discard(int(self.winId()))
        super().closeEvent(event)
