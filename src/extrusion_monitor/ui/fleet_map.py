"""Dashboard global → Mapa de planta: un mosaico por línea, agrupados por área (como Variables en vivo).

Cada mosaico muestra el estado de la máquina (barra de color y etiqueta), el OEE del turno, la producción del turno
contra su meta, la velocidad, la receta y las alarmas; parpadea si la línea está en alarma. Doble clic abre el
detalle de la línea. Es la vista para TV («Modo TV con el mapa de planta»).
"""
from __future__ import annotations

import time
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import QFrame, QGridLayout, QHBoxLayout, QLabel, QScrollArea, QVBoxLayout, QWidget

from ..i18n import tr
from ..plant_settings import PlantSettings
from . import theme
from .fleet_tiles import fmt_age

TILE_MIN_W = 280
STATE_KEYS = {"running": "good", "assumed": "good", "slow": "warning", "microstop": "serious", "stopped": "critical"}


class LineTile(QFrame):
    opened = Signal(str)

    def __init__(self, line_id: str, name: str):
        super().__init__()
        self.line_id, self.name = line_id, name
        self.alarm = False
        self.blink = False
        self.color = theme.c("neutral")
        self.setObjectName("card")
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumHeight(200)
        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 10, 8)
        outer.setSpacing(10)
        self.strip = QFrame()
        self.strip.setFixedWidth(8)
        outer.addWidget(self.strip)
        lay = QVBoxLayout()
        lay.setSpacing(3)
        lay.setContentsMargins(0, 8, 0, 0)
        head = QHBoxLayout()
        self.lbl_name = QLabel()
        head.addWidget(self.lbl_name, 1)
        self.pill = QLabel()
        head.addWidget(self.pill, 0, Qt.AlignTop)
        lay.addLayout(head)
        self.lbl_state = QLabel()
        lay.addWidget(self.lbl_state)
        self.lbl_value = QLabel()
        self.lbl_value.setAlignment(Qt.AlignCenter)
        lay.addWidget(self.lbl_value, 1)
        self.lbl_prod = QLabel()
        self.lbl_prod.setAlignment(Qt.AlignCenter)
        lay.addWidget(self.lbl_prod)
        self.lbl_info = QLabel()
        self.lbl_info.setAlignment(Qt.AlignCenter)
        self.lbl_info.setWordWrap(True)
        self.lbl_info.setStyleSheet(f"color:{theme.c('muted')}; font-size:11px;")
        lay.addWidget(self.lbl_info)
        outer.addLayout(lay, 1)

    def _style(self) -> None:
        border = theme.c("critical") if self.alarm and self.blink else theme.c("card_border")
        width = 3 if self.alarm and self.blink else 1
        self.setStyleSheet(f"QFrame#card {{ border: {width}px solid {border}; }}")
        self.strip.setStyleSheet(f"background:{self.color}; border-top-left-radius:10px; "
                                 "border-bottom-left-radius:10px;")

    def set_data(self, ln, now: float, offline_s, plant: PlantSettings) -> None:
        st = ln.status
        self.name = ln.name
        conn = ln.connection(now, offline_s)
        machine = st.get("machine") or {}
        oee_d = st.get("oee") or {}
        oee = (st.get("kpis") or {}).get("oee")
        self.lbl_name.setText(f"<b style='font-size:16px; color:{theme.c('title')}'>{ln.name}</b>")
        if conn in ("offline", "closed"):
            self.color = theme.c("neutral")
            pill, pill_c = (tr("SIN COMUNICACIÓN") if conn == "offline" else tr("CERRADO")), theme.c("neutral")
            state = tr("Última actualización: {a}", a=fmt_age(ln.age(now))) if ln.age(now) is not None else ""
            self.alarm = False
        else:
            key = STATE_KEYS.get(machine.get("state"), "info")
            self.color = theme.c(key)
            n_al = int(st.get("n_alarms") or 0)
            n_w = int(st.get("n_warnings") or 0)
            pill, pill_c = ((f"{n_al} " + tr("ALARMAS"), theme.c("critical")) if n_al else
                            ((f"{n_w} " + tr("AVISOS"), theme.c("warning")) if n_w else ("OK", theme.c("good"))))
            label = tr(machine.get("label") or (tr("Monitoreando") if st.get("monitoring") else "—"))
            since = machine.get("since")
            state = f"<b style='color:{self.color}'>● {label}</b>" + (
                f" · {tr('desde')} {fmt_age(now - since)}" if since else "")
            self.alarm = bool(n_al)
        self.pill.setText(pill)
        self.pill.setStyleSheet(f"background:{pill_c}; color:#ffffff; border-radius:8px; padding:1px 8px; "
                                "font-size:10px; font-weight:bold;")
        self.lbl_state.setText(state)
        oc = theme.c("muted") if oee is None else (theme.c("critical") if oee < 60 else
                                                   theme.c("warning_text") if oee < 75 else theme.c("good_text"))
        self.lbl_value.setText(f"<span style='font-size:34px; color:{oc}'><b>{'—' if oee is None else f'{oee:.0f}'}"
                               f"</b></span><span style='font-size:13px; color:{theme.c('muted')}'> % OEE</span>")
        total, unit = oee_d.get("length_total"), oee_d.get("unit") or ""
        target = plant.target(ln.name).production_shift
        if total is not None:
            prod = f"{tr('Producción del turno')}: <b>{total:,.0f} {unit}</b>"
            if target:
                shift_start = oee_d.get("shift_start") or now
                shift_len = 8 * 3600
                expected = target * min(1.0, max(0.0, (now - shift_start) / shift_len))
                pct = 100 * total / expected if expected else None
                if pct is not None:
                    pc = theme.c("good_text") if pct >= 100 else (theme.c("warning_text") if pct >= 90 else
                                                                  theme.c("critical"))
                    prod += f" · <b style='color:{pc}'>{pct:.0f} %</b> {tr('de la meta')}"
            self.lbl_prod.setText(prod)
        else:
            self.lbl_prod.setText("")
        info = []
        if st.get("recipe"):
            info.append(f"{tr('Receta')}: {st['recipe']}")
        if oee_d.get("avg_speed") is not None:
            info.append(f"{tr('Velocidad')}: {oee_d['avg_speed']:.4g}")
        if oee_d.get("n_stops") is not None:
            info.append(f"{tr('Paros')}: {oee_d['n_stops']}")
        self.lbl_info.setText(" · ".join(info))
        self._style()

    def mouseDoubleClickEvent(self, e) -> None:
        self.opened.emit(self.line_id)


class FleetMap(QWidget):
    open_line = Signal(str)

    def __init__(self, reader_fn, home: Path, settings_fn=None, allow=None):
        super().__init__()
        self.reader_fn = reader_fn
        self.home = Path(home)
        self.settings_fn = settings_fn  # FleetSettings: áreas y tiempo sin comunicación
        self.items: dict[str, LineTile] = {}
        self._blink = False
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        bar = QHBoxLayout()
        bar.addWidget(QLabel(f"<b style='font-size:16px; color:{theme.c('title')}'>{tr('Mapa de planta')}</b>"))
        bar.addStretch(1)
        bar.addWidget(QLabel(" ".join(f"<span style='color:{theme.c(k)}'>■</span> {tr(t)}&nbsp;&nbsp;" for k, t in (
            ("good", "En marcha"), ("warning", "Lento"), ("critical", "Detenida"), ("neutral", "Sin comunicación")))))
        lay.addLayout(bar)
        self.area = QScrollArea()
        self.area.setWidgetResizable(True)
        self.area.setFrameShape(QFrame.NoFrame)
        self.inner = QWidget()
        self.inner.setObjectName("content")
        self.grid = QGridLayout(self.inner)
        self.grid.setSpacing(12)
        self.grid.setContentsMargins(0, 0, 4, 0)
        self.area.setWidget(self.inner)
        lay.addWidget(self.area, 1)
        self._cols = 0
        self._layout_key = None
        self._resize = QTimer(self)
        self._resize.setSingleShot(True)
        self._resize.setInterval(150)
        self._resize.timeout.connect(lambda: self.refresh(relayout=True))

    def _columns(self) -> int:
        return max(1, (self.area.viewport().width() - 4) // TILE_MIN_W)

    def refresh(self, relayout: bool = False) -> None:
        reader = self.reader_fn()
        fs = self.settings_fn() if self.settings_fn else None
        offline_s = getattr(fs, "offline_s", None)
        plant = PlantSettings.load(self.home)
        now = time.time()
        lines = sorted(reader.lines.values(), key=lambda ln: ln.name)
        for lid in [k for k in self.items if k not in reader.lines]:
            self.items.pop(lid).deleteLater()
        for ln in lines:
            it = self.items.get(ln.line_id)
            if it is None:
                it = self.items[ln.line_id] = LineTile(ln.line_id, ln.name)
                it.opened.connect(self.open_line.emit)
            it.set_data(ln, now, offline_s, plant)
        areas = {ln.line_id: (fs.area_of(ln) if fs is not None else "") or tr("Sin área") for ln in lines}
        key = (tuple((areas[ln.line_id], ln.line_id) for ln in lines), self._columns())
        if relayout or key != self._layout_key:
            self._layout_key = key
            self._place(lines, areas)

    def _place(self, lines, areas: dict) -> None:
        while self.grid.count():
            item = self.grid.takeAt(0)
            w = item.widget()
            if w is not None and not isinstance(w, LineTile):
                w.deleteLater()
        cols = self._cols = self._columns()
        row = 0
        groups: dict[str, list] = {}
        for ln in lines:
            groups.setdefault(areas[ln.line_id], []).append(ln)
        for area, lns in sorted(groups.items()):
            if len(groups) > 1 or area != tr("Sin área"):
                head = QLabel(f"<b style='color:{theme.c('title')}; font-size:14px'>{area}</b>")
                self.grid.addWidget(head, row, 0, 1, cols)
                row += 1
            for i, ln in enumerate(lns):
                self.grid.addWidget(self.items[ln.line_id], row + i // cols, i % cols)
            row += (len(lns) + cols - 1) // cols
        for c in range(cols):
            self.grid.setColumnStretch(c, 1)
        self.grid.setRowStretch(row, 1)

    def fit(self) -> None:  # compatibilidad: la cuadrícula ya se ajusta sola
        self.refresh(relayout=True)

    def blink_tick(self) -> None:
        self._blink = not self._blink
        for it in self.items.values():
            if it.alarm:
                it.blink = self._blink
                it._style()

    def resizeEvent(self, e) -> None:
        super().resizeEvent(e)
        self._resize.start()
