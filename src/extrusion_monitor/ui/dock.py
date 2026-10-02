"""Dock: barra compacta siempre visible que queda sobre el HMI al minimizar el programa.

* Flota encima del HMI (no cambia su tamaño) y se excluye de la captura, así que no afecta la lectura.
* Muestra el estado de la máquina y los indicadores elegidos (los mismos tipos que el tablero de Inicio).
  Si el grosor es muy pequeño para gráficas, cada indicador pasa a «nombre + valor» con color según su rango.
* Son dos piezas pegadas: la agarradera (⠿ y ⤢), que SIEMPRE responde al mouse, y el cuerpo con los
  indicadores, que al acercar el mouse se desvanece y deja pasar los clics al HMI.
* Desde la agarradera se arrastra; con doble clic o ⤢ se restaura el programa.
* Al aparecer una alarma parpadea y muestra el mensaje.
* Durante los clics de un recorrido deja pasar el clic (no estorba aunque quede sobre un botón).
"""
from __future__ import annotations

import time
from typing import Optional

from PySide6.QtCore import QPoint, QRect, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QCursor, QFont, QFontMetrics, QGuiApplication
from PySide6.QtWidgets import QBoxLayout, QFrame, QLabel, QToolButton, QVBoxLayout, QWidget

from .. import navigation
from ..analysis.kpis import KPIS, snapshot_kpis
from ..analysis.oee import STATE_LABELS
from ..analysis.rules import Level, fmt
from ..config import KPI_KINDS, DockSettings
from ..engine import MonitorEngine, Snapshot
from ..i18n import tr, translate_text
from . import theme
from .common import SeriesCache
from .home_page import BUILTIN_TILES, KPI_INFO, GaugeCard
from .home_tiles import KpiTrendTile, KpiValueTile, kpi_color, kpi_fmt, make_var_tile, zone
from .kpi_dashboard import STATE_COLORS, Gauge

GHOST_OPACITY = 0.14
ALERT_S = 12.0
GAP = 2  # separación entre la agarradera y el cuerpo
FLAGS = Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.WindowDoesNotAcceptFocus


def unit_len(thick: int) -> int:
    """Largo de un indicador de ancho 1, proporcional al grosor."""
    return max(104, int(thick * 1.15))


def value_px(thick: int) -> int:
    return max(13, min(40, int(thick * 0.21)))


class CompactTile(QFrame):
    """Indicador en un dock delgado: nombre y valor, con color según su rango (sin gráfica)."""

    def __init__(self, tile, config, thick: int):
        super().__init__()
        self.tile = tile
        self.config = config
        self.one_line = thick < 56
        self.px = max(12, min(22, int(thick * 0.36))) if self.one_line else max(13, min(24, int(thick * 0.3)))
        self.setObjectName("card")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(6, 1, 6, 1)
        self.lbl = QLabel("—")
        self.lbl.setTextFormat(Qt.RichText)
        self.lbl.setAlignment(Qt.AlignCenter)
        lay.addWidget(self.lbl)
        self.var = config.variable(tile.var_ids[0]) if tile.kind == "var" and tile.var_ids else None
        if tile.kind == "var":
            self.title = tile.title or (self.var.name if self.var else tr("Variable"))
        else:
            self.title = tr(tile.title or BUILTIN_TILES[tile.kind])
        self.setToolTip(self.title)

    def preferred_width(self) -> int:
        """Ancho para que quepan el nombre y el valor más largo esperado (no cambia al cambiar el valor)."""
        small = QFont(self.font())
        small.setPixelSize(10)
        big = QFont(self.font())
        big.setPixelSize(self.px)
        big.setBold(True)
        if self.tile.kind != "var":
            sample, unit = "100.0", KPIS[self.tile.kind][1]
        elif self.var is not None and not self.var.numeric:
            sample, unit = max(list(self.var.states) + ["XXXXXX"], key=len), ""
        else:
            sample, unit = "0000.00", self.var.unit if self.var else ""
        w_title = QFontMetrics(small).horizontalAdvance(self.title)
        w_value = QFontMetrics(big).horizontalAdvance(sample) + QFontMetrics(small).horizontalAdvance(" " + unit)
        return (w_title + 6 + w_value if self.one_line else max(w_title, w_value)) + 22

    def _show(self, text: str, unit: str, color: str) -> None:
        sep = " " if self.one_line else "<br>"
        self.lbl.setText(f"<span style='font-size:10px; color:{theme.c('text2')}'>{self.title}</span>{sep}"
                         f"<b style='font-size:{self.px}px; color:{color}'>{text}</b>"
                         f"<span style='font-size:10px; color:{theme.c('muted')}'> {unit}</span>")

    def set(self, value: Optional[float], _sub: str = "") -> None:  # indicador (OEE, Cpk…)
        key = self.tile.kind
        self._show(kpi_fmt(key, value), KPIS[key][1], kpi_color(key, value))

    def update_snapshot(self, snap: Snapshot) -> None:  # variable
        st = snap.statuses.get(self.var.id) if self.var else None
        if st is None:
            self._show("—", "", theme.c("muted"))
            return
        if not st.var.numeric:
            text = st.reading.text or "—"
            key = ("good" if text == st.expected else "critical") if st.expected else "text"
            self._show(text, "", theme.c(key))
            return
        v = st.reading.value
        if st.level is not None and st.level >= Level.ALARM:
            key = "critical"
        elif st.level is not None and st.level >= Level.WARN:
            key = "warning"
        else:
            key = zone(v, st.bounds) if v is not None and st.bounds.any else "text"
        self._show(fmt(v, st.var, st.reading.decimals) if v is not None else "—", st.var.unit,
                   theme.c("text" if key == "neutral" else key))


class DockHandle(QFrame):
    """Agarradera del dock: ventana propia que nunca se vuelve «fantasma», así siempre se puede usar."""

    def __init__(self, dock: "DockWindow"):
        super().__init__(None, FLAGS)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setObjectName("dockHandle")
        self.dock = dock
        self.lay = QBoxLayout(QBoxLayout.TopToBottom, self)
        self.lay.setContentsMargins(2, 2, 2, 2)
        self.lay.setSpacing(1)
        self.grip = QLabel("⠿")
        self.grip.setAlignment(Qt.AlignCenter)
        self.grip.setCursor(Qt.SizeAllCursor)
        self.lay.addWidget(self.grip, 1)
        self.btn = QToolButton()
        self.btn.setText("⤢")
        self.btn.setToolTip("Restaurar el programa")
        self.btn.clicked.connect(dock.restore.emit)
        self.lay.addWidget(self.btn)
        self.setToolTip("Arrastra para mover el dock · doble clic para restaurar el programa")

    def setup(self, size: QSize, stacked: bool) -> None:
        self.lay.setDirection(QBoxLayout.TopToBottom if stacked else QBoxLayout.LeftToRight)
        self.grip.setStyleSheet(f"font-size:{18 if min(size.width(), size.height()) >= 30 else 13}px; "
                                f"color:{theme.c('muted')};")
        side = max(16, min(26, min(size.width(), size.height()) - 6))
        self.btn.setFixedSize(side, side)
        self.btn.setStyleSheet(f"QToolButton {{ padding:0px; font-size:{max(11, side - 10)}px; }}")
        self.setFixedSize(size)
        self.setStyleSheet(f"#dockHandle {{ background:{theme.c('surface')}; border:2px solid {theme.c('accent')}; "
                           f"border-radius:6px; }}")

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self.dock.begin_drag(event.globalPosition().toPoint())

    def mouseMoveEvent(self, event) -> None:
        self.dock.drag_to(event.globalPosition().toPoint())

    def mouseReleaseEvent(self, event) -> None:
        self.dock.end_drag()

    def mouseDoubleClickEvent(self, event) -> None:
        self.dock.restore.emit()


class DockWindow(QWidget):
    restore = Signal()

    def __init__(self, engine: MonitorEngine, workspace=None):
        super().__init__(None, FLAGS)
        self.setAttribute(Qt.WA_ShowWithoutActivating)  # no le quita el foco al HMI
        self.setObjectName("dock")
        self.engine = engine
        self.workspace = workspace
        self.series = SeriesCache(engine)
        self._ghost = False
        self._hold = False
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
        self.handle = DockHandle(self)
        self.rebuild()
        self.poll = QTimer(self)
        self.poll.timeout.connect(self._poll)
        self.poll.start(120)
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
        origin = self.origin() if self.isVisible() else None
        if self.frame is not None:
            self._outer.removeWidget(self.frame)
            self.frame.deleteLater()
        self.kpi_widgets, self.var_tiles = {}, []
        thick, unit = cfg.thickness, unit_len(cfg.thickness)
        margin = 2 if cfg.compact else 4
        inner = thick - 2 * margin - 4  # el grosor total incluye margen y borde (2 px por lado)
        self.frame = QFrame()
        self.frame.setObjectName("dockFrame")
        lay = QBoxLayout(QBoxLayout.LeftToRight if self.horizontal else QBoxLayout.TopToBottom, self.frame)
        lay.setContentsMargins(margin, margin, margin, margin)
        lay.setSpacing(4)

        # agarradera: junto al inicio del dock; apilada (⠿ sobre ⤢) si hay grosor, en línea si es delgado
        if self.horizontal:
            self.handle.setup(QSize(34, thick) if thick >= 62 else QSize(54, thick), stacked=thick >= 62)
        else:
            self.handle.setup(QSize(unit, 30), stacked=False)

        # estado de la máquina, receta y alarmas (siempre)
        self.chip = QLabel("—")
        self.chip.setTextFormat(Qt.RichText)
        self.chip.setWordWrap(not cfg.compact)
        self.chip.setAlignment(Qt.AlignCenter)
        self.chip.setObjectName("dockChip")  # fondo propio: se lee también cuando el dock parpadea en rojo
        self.chip.setStyleSheet(f"#dockChip {{ background:{theme.c('surface')}; border-radius:6px; }}")
        chip_len = max(150, unit) if not cfg.compact else 190
        self.chip.setFixedSize(*((chip_len, inner) if self.horizontal else (unit - 8, max(inner, 44))))
        lay.addWidget(self.chip)

        made = [w for w in (self._make_tile(t) for t in cfg.tiles) if w is not None]
        if cfg.compact and not self.horizontal and made:  # columna tan ancha como el indicador más largo
            unit = min(max(max(w.preferred_width() for w in made) + 8, unit), 330)
            self.handle.setup(QSize(unit, 30), stacked=False)
            self.chip.setFixedSize(unit - 8, max(inner, 44))
        for tile, w in zip([t for t in cfg.tiles if t.kind == "var" or t.kind in KPI_KINDS], made):
            # Horizontal: el ancho del indicador son sus unidades. Vertical: una columna de mosaicos iguales.
            if cfg.compact:
                length = min(max(w.preferred_width(), 70), 320)
            else:
                length = unit * max(1, min(tile.width, 4))
            w.setFixedSize(*((length, inner) if self.horizontal else (unit - 8, inner)))
            w.setCursor(Qt.ArrowCursor)
            lay.addWidget(w)
        # Tamaño exacto: el grosor configurado en un sentido y lo que ocupen los indicadores en el otro.
        if self.horizontal:
            self.frame.setFixedHeight(thick)
        else:
            self.frame.setFixedWidth(unit - 8 + 2 * margin + 4)
        self._outer.addWidget(self.frame)
        self._style()
        self.setMinimumSize(0, 0)
        self.setMaximumSize(16777215, 16777215)
        self.setFixedSize(self.frame.sizeHint().width() if self.horizontal else self.frame.width(),
                          thick if self.horizontal else self.frame.sizeHint().height())
        if self.isVisible():
            self.place()
            if origin is not None and self._saved_pos() is not None:
                self.move_to(origin)
            if self.engine.last is not None:
                self.update_snapshot(self.engine.last, force=True)

    def _make_tile(self, tile) -> Optional[QWidget]:
        cfg = self.cfg
        k = tile.kind
        if k != "var" and k not in KPI_KINDS:
            return None  # el dock solo lleva indicadores y variables
        if cfg.compact:
            # Muy delgado para gráficas: solo el valor, con color según su rango.
            w = CompactTile(tile, self.engine.config, cfg.thickness)
            (self.var_tiles if k == "var" else self.kpi_widgets.setdefault(k, [])).append(w)
            return w
        small = cfg.thickness < 110
        if k == "var":
            w = make_var_tile(tile, self.engine.config, self.series)
            if w.plot is not None:
                w.plot.setMinimumHeight(30)
            if w.gauge is not None:
                w.gauge.setMinimumSize(40, 40)
            if w.lbl_info is not None and (small or w.gauge is not None):
                w.lbl_info.hide()  # el gauge ya muestra valor y referencia: se le deja todo el espacio
            self.var_tiles.append(w)
        else:
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
            if small or tile.kpi_chart == "gauge":
                w.sub.hide()
            self.kpi_widgets.setdefault(k, []).append(w)
        w.layout().setContentsMargins(5, 3, 5, 3)
        w.value_px = value_px(cfg.thickness)
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

    # --- posición: el origen es la esquina de la agarradera; el cuerpo va pegado a ella ---------
    def total_size(self) -> QSize:
        h, b = self.handle.size(), self.size()
        if self.horizontal:
            return QSize(h.width() + GAP + b.width(), max(h.height(), b.height()))
        return QSize(max(h.width(), b.width()), h.height() + GAP + b.height())

    def origin(self) -> QPoint:
        return self.handle.pos()

    def move_to(self, origin: QPoint) -> None:
        self.handle.move(origin)
        if self.horizontal:
            self.move(origin.x() + self.handle.width() + GAP, origin.y())
        else:
            self.move(origin.x(), origin.y() + self.handle.height() + GAP)

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
        size = self.total_size()
        w, h = size.width(), size.height()
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
        saved = self._saved_pos()
        if saved is not None:
            x = min(max(saved[0], geo.x()), geo.x() + geo.width() - 40)
            y = min(max(saved[1], geo.y()), geo.y() + geo.height() - 40)
            self.move_to(QPoint(x, y))
        else:
            self.move_to(self.edge_pos(geo))

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
        compact = self.cfg.compact
        if self.alerting():
            msg = translate_text(self._alert_msg)
            if compact:
                self.chip.setText(f"<b style='color:{theme.c('critical')}'>▲ {msg[:34]}</b>")
            else:
                self.chip.setText(f"<b style='color:{theme.c('critical')}'>▲ {tr('ALARMA')}</b><br>"
                                  f"<span style='font-size:11px'>{msg[:110]}</span>")
            self.chip.setToolTip(msg)
            return
        self.chip.setToolTip("")
        res = eng.kpi_oee
        cur = res.intervals[-1] if res is not None and res.intervals else None
        px = 12 if compact else 15
        if cur is not None:
            state = (f"<b style='font-size:{px}px; color:{STATE_COLORS[cur.state]}'>● "
                     f"{tr(STATE_LABELS[cur.state])}</b>")
        elif eng.running:
            state = f"<b style='font-size:{px}px; color:{theme.c('good')}'>● {tr('Monitoreando')}</b>"
        else:
            state = f"<b style='font-size:{px}px; color:{theme.c('muted')}'>● {tr('Monitoreo detenido')}</b>"
        na = sum(f.level >= Level.ALARM for f in snap.findings)
        nw = sum(f.level == Level.WARN for f in snap.findings)
        if na or nw:
            alarms = (f"<b style='color:{theme.c('critical')}'>▲ {na}</b> · "
                      f"<b style='color:{theme.c('warning_text')}'>{nw}</b>")
        else:
            alarms = f"<span style='color:{theme.c('good_text')}'>✔</span>"
        if compact:  # una sola línea
            self.chip.setText(f"{state} &nbsp;{alarms}")
            self.chip.setToolTip(snap.recipe or "")
            return
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

    # --- mouse: el cuerpo se vuelve fantasma al acercarse; la agarradera siempre responde -------
    def _poll(self) -> None:
        if not self.isVisible():
            return
        hold = time.monotonic() < navigation.overlay_hold_until  # un recorrido está haciendo clic
        over = self.frameGeometry().contains(QCursor.pos())
        self.set_ghost(hold or (self.cfg.ghost_on_hover and over and self._drag is None))
        if hold != self._hold:  # durante el clic de un recorrido también la agarradera deja pasar el clic
            self._hold = hold
            navigation.set_click_through(int(self.handle.winId()), hold)

    def set_ghost(self, on: bool) -> None:
        """Cuerpo casi transparente que deja pasar los clics a lo que está debajo."""
        if on == self._ghost:
            return
        self._ghost = on
        self.setWindowOpacity(GHOST_OPACITY if on else 1.0)
        if not navigation.set_click_through(int(self.winId()), on):
            self.setAttribute(Qt.WA_TransparentForMouseEvents, on)  # fuera de Windows: solo dentro del programa

    def begin_drag(self, gpos: QPoint) -> None:
        self._drag = gpos - self.origin()

    def drag_to(self, gpos: QPoint) -> None:
        if self._drag is not None:
            self.move_to(gpos - self._drag)

    def end_drag(self) -> None:
        if self._drag is None:
            return
        self._drag = None
        geo = self._screen_geo or QGuiApplication.primaryScreen().availableGeometry()
        home = self.edge_pos(geo)
        # Soltarlo cerca de su lugar en el borde lo vuelve a anclar ahí; si no, recuerda la posición.
        if (self.origin() - home).manhattanLength() < 40:
            self._save_pos(None)
            self.move_to(home)
        else:
            self._save_pos((self.origin().x(), self.origin().y()))

    def mouseDoubleClickEvent(self, event) -> None:
        self.restore.emit()

    # --- ciclo de vida ----------------------------------------------------------------------
    def _hwnds(self) -> list[int]:
        return [int(self.winId()), int(self.handle.winId())]

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self.handle.show()
        for hwnd in self._hwnds():
            navigation.exclude_window_from_capture(hwnd)  # el dock no aparece en la lectura del HMI
            navigation.OVERLAY_HWNDS.add(hwnd)
        self._ghost = False
        self.setWindowOpacity(1.0)

    def hideEvent(self, event) -> None:
        for hwnd in self._hwnds():
            navigation.OVERLAY_HWNDS.discard(hwnd)
        self.handle.hide()
        super().hideEvent(event)

    def closeEvent(self, event) -> None:
        self.poll.stop()
        self.blink.stop()
        for hwnd in self._hwnds():
            navigation.OVERLAY_HWNDS.discard(hwnd)
        self.handle.close()
        super().closeEvent(event)
