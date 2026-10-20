"""Búsqueda de la barra superior: variables, páginas, acciones, recetas, horas, paros capturados y alarmas.

Escribir abre una lista bajo la caja; ↑/↓ eligen, Enter ejecuta y Esc cierra. No distingue acentos ni
mayúsculas y tolera errores de tecleo. Solo lee: lo que cambia algo (receta) pide confirmación.
"""
from __future__ import annotations

import re
import time
import unicodedata
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Callable, Optional

from PySide6.QtCore import QEvent, QPoint, QSize, Qt, QTimer
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QFrame, QLabel, QLineEdit, QListWidget, QListWidgetItem, QVBoxLayout, QWidget,
)

from ..analysis.oee import shift_start
from ..analysis.rules import Level
from ..i18n import tr, translate_text
from . import icons, theme
from .common import level_color

MAX_RESULTS = 14
HISTORY_DAYS = 30  # paros y alarmas: cuánto hacia atrás se busca
RECENT_MAX = 6


def normalize(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", re.sub(r"[^\w:/.,\- ]", " ", s.lower())).strip()


def match_score(query: str, text: str) -> float:
    """0 = no coincide. Cada palabra buscada debe aparecer (prefijo, parte o parecida) en el texto."""
    q = normalize(query).split()
    if not q:
        return 0.0
    t = normalize(text)
    words = t.split()
    total = 0.0
    for tok in q:
        if any(w.startswith(tok) for w in words):
            total += 3.0
        elif tok in t:
            total += 2.0
        elif len(tok) >= 4 and any(SequenceMatcher(None, tok, w[:len(tok) + 1]).ratio() >= 0.75 for w in words):
            total += 1.0  # error de tecleo
        else:
            return 0.0
    if t.startswith(normalize(query)):
        total += 2.0
    return total


_UNITS = {"s": 1, "seg": 1, "segundo": 1, "segundos": 1, "m": 60, "min": 60, "mins": 60, "minuto": 60,
          "minutos": 60, "minute": 60, "minutes": 60, "h": 3600, "hr": 3600, "hrs": 3600, "hora": 3600,
          "horas": 3600, "hour": 3600, "hours": 3600, "d": 86400, "dia": 86400, "dias": 86400, "day": 86400,
          "days": 86400}


def parse_time(query: str, now: float, shift_starts=None) -> Optional[tuple[float, str]]:
    """Una hora escrita: «14:30», «ayer 14:30», «12/10 08:00», «hace 2 h», «2 h ago», «turno», «turno anterior»."""
    q = normalize(query)
    lt = time.localtime(now)

    def at(day_offset: int, h: int, mi: int, sec: int = 0, month=None, mday=None) -> Optional[float]:
        try:
            base = time.mktime((lt.tm_year, month or lt.tm_mon, mday or lt.tm_mday, h, mi, sec, 0, 0, -1))
        except (OverflowError, ValueError):
            return None
        return base + day_offset * 86400

    m = re.fullmatch(r"(?:(ayer|anteayer|hoy|yesterday|today)\s+)?(?:a las\s+|at\s+)?(\d{1,2}):(\d{2})(?::(\d{2}))?", q)
    if m:
        h, mi, sec = int(m[2]), int(m[3]), int(m[4] or 0)
        if h > 23 or mi > 59 or sec > 59:
            return None
        off = {"ayer": -1, "yesterday": -1, "anteayer": -2}.get(m[1] or "", 0)
        ts = at(off, h, mi, sec)
        if ts is not None and not m[1] and ts > now:
            ts -= 86400  # «14:30» cuando todavía no son las 14:30: la de ayer
        return (ts, time.strftime("%d/%m %H:%M:%S", time.localtime(ts))) if ts is not None and ts <= now else None
    m = re.fullmatch(r"(\d{1,2})/(\d{1,2})\s+(\d{1,2}):(\d{2})(?::(\d{2}))?", q)
    if m:
        d, mo, h, mi, sec = int(m[1]), int(m[2]), int(m[3]), int(m[4]), int(m[5] or 0)
        if not (1 <= d <= 31 and 1 <= mo <= 12 and h <= 23 and mi <= 59 and sec <= 59):
            return None
        ts = at(0, h, mi, sec, month=mo, mday=d)
        if ts is not None and ts > now:
            ts = time.mktime((lt.tm_year - 1, mo, d, h, mi, sec, 0, 0, -1))
        return (ts, time.strftime("%d/%m %H:%M:%S", time.localtime(ts))) if ts is not None else None
    m = (re.fullmatch(r"hace\s+(\d+(?:[.,]\d+)?)\s*([a-z]+)", q)
         or re.fullmatch(r"(\d+(?:[.,]\d+)?)\s*([a-z]+)\s+ago", q))
    if m and m[2] in _UNITS:
        ts = now - float(m[1].replace(",", ".")) * _UNITS[m[2]]
        return ts, time.strftime("%d/%m %H:%M:%S", time.localtime(ts))
    if q in ("turno", "inicio de turno", "inicio del turno", "shift", "shift start"):
        ts = shift_start(now, shift_starts or [])
        return ts, tr("inicio del turno") + " · " + time.strftime("%H:%M", time.localtime(ts))
    if q in ("turno anterior", "previous shift", "last shift"):
        cur = shift_start(now, shift_starts or [])
        ts = shift_start(cur - 1, shift_starts or [])
        return ts, tr("turno anterior") + " · " + time.strftime("%d/%m %H:%M", time.localtime(ts))
    return None


def clean_action_text(text: str) -> str:
    """«🛟 Crear &respaldo…» → «Crear respaldo»."""
    text = text.replace("&", "").replace("…", "").strip()
    return re.sub(r"^[^\w¿¡(]+", "", text).strip()


@dataclass
class Result:
    kind: str  # var | sub | page | action | recipe | time | problem | event
    title: str
    subtitle: str = ""
    icon: str = "page"
    run: Optional[Callable[[], None]] = None
    score: float = 0.0
    color: Optional[str] = None
    key: str = ""  # para las búsquedas recientes


KIND_LABEL = {"var": "Variable", "page": "Página", "action": "Acción", "recipe": "Receta", "time": "Hora",
              "problem": "Captura", "event": "Alarma / evento"}


@dataclass
class SearchProvider:
    """Arma los resultados a partir de la ventana principal (receta, menús, historial)."""

    win: object
    recent: list[str] = field(default_factory=list)

    @property
    def engine(self):
        return self.win.engine

    def results(self, query: str) -> list[Result]:
        query = query.strip()
        if not query:
            return self._recent_results()
        out: list[Result] = []
        now = self.engine.clock()
        t = parse_time(query, now, self.engine.config.oee.shift_starts)
        if t is not None:
            ts, label = t
            out.append(Result("time", tr("Ver tendencias en {t}", t=label), tr("Marca esa hora en las gráficas"),
                              "trends", lambda ts=ts: self.win.goto_time(ts), 100))
            out.append(Result("time", tr("Capturar paro o defecto desde {t}", t=label),
                              tr("Problemas de proceso"), "problems", lambda ts=ts: self.win.capture_at(ts), 99))
        head = list(out)  # horas primero
        vars_ = self._variables(query)
        if vars_:  # la mejor variable y lo que se puede hacer con ella
            head += [vars_[0]] + self._var_actions(vars_[0].key)
        rest = vars_[1:] + self._pages(query) + self._actions(query) + self._recipes(query)
        rest += self._problems(query, now) + self._events(query, now)
        rest.sort(key=lambda r: -r.score)
        return (head + rest)[:MAX_RESULTS]

    # --- fuentes ---------------------------------------------------------------------
    def _variables(self, query: str) -> list[Result]:
        cfg = self.engine.config
        snap = self.engine.last
        res = []
        for v in cfg.variables:
            label = cfg.var_label(v)
            sc = match_score(query, f"{v.name} {label} {v.id} {v.unit}")
            if not sc:
                continue
            sub = tr("sin lectura")
            color = None
            st = snap.statuses.get(v.id) if snap is not None else None
            if st is not None and (st.reading.value is not None or st.reading.text):
                val = f"{st.reading.value:g}" if st.reading.value is not None else str(st.reading.text)
                sub = f"{val} {v.unit}".strip()
                b = st.bounds
                if b.al is not None or b.ah is not None:
                    lo = "—" if b.al is None else f"{b.al:.6g}"
                    hi = "—" if b.ah is None else f"{b.ah:.6g}"
                    sub += f"  ({lo} … {hi})"
                if st.level is not None:
                    color = level_color(st.level).name() if st.level >= Level.WARN else theme.c("good_text")
            res.append(Result("var", label, sub, "variables", lambda vid=v.id: self.win.search_plot(vid),
                              50 + sc, color, key=f"var:{v.id}"))
        return sorted(res, key=lambda r: -r.score)[:6]

    def _var_actions(self, key: str) -> list[Result]:
        vid = key.split(":", 1)[1]
        v = self.engine.config.variable(vid)
        out = [Result("sub", tr("Ver en Variables en vivo"), "", "variables", lambda: self.win.search_live(vid))]
        if v is not None and v.numeric:
            out = [Result("sub", tr("Agregar a SPC"), "", "spc", lambda: self.win.search_spc(vid)),
                   Result("sub", tr("Agregar a Correlación"), "", "corr", lambda: self.win.search_corr(vid))] + out
        return out

    def _pages(self, query: str) -> list[Result]:
        from .main_window import NAV_ITEMS, NAV_TOOLS
        out = []
        for key, label, _ in NAV_ITEMS + NAV_TOOLS:
            sc = match_score(query, tr(label) + " " + label)
            if sc:
                run = (lambda k=key: self.win.show_page(k)) if key in self.win.pages else \
                      (lambda k=key: self.win.run_tool(k))
                out.append(Result("page", tr(label), tr("Página"), key, run, 40 + sc, key=f"page:{key}"))
        return out

    def _actions(self, query: str) -> list[Result]:
        out = []
        for path, act in self.menu_actions():
            text = clean_action_text(act.text())
            sc = match_score(query, f"{text} {path}")
            if sc:
                sub = path + (f"  ·  {act.shortcut().toString()}" if not act.shortcut().isEmpty() else "")
                out.append(Result("action", text, sub, "action", act.trigger, 30 + sc, key=f"act:{path}›{text}"))
        return sorted(out, key=lambda r: -r.score)[:5]

    def menu_actions(self):
        """(ruta del menú, acción) de todos los menús, salvo las que se arman al abrirlos y «Salir»."""
        found = []

        def walk(menu, path):
            for act in menu.actions():
                if act.isSeparator() or not act.isVisible():
                    continue
                sub = act.menu()
                text = clean_action_text(act.text())
                if sub is not None:
                    walk(sub, f"{path} › {text}" if path else text)
                elif text and act.isEnabled() and text not in (tr("Salir"), "Salir"):
                    found.append((path, act))

        for act in self.win.menuBar().actions():
            if act.menu() is not None:
                walk(act.menu(), clean_action_text(act.text()))
        return found

    def _recipes(self, query: str) -> list[Result]:
        out = []
        current = self.engine.state.recipe
        for name in self.win.ctx.recipes.names():
            sc = match_score(query, name)
            if sc:
                sub = tr("receta activa") if name == current else tr("Cambiar a esta receta (pide confirmación)")
                out.append(Result("recipe", name, sub, "recipes", lambda n=name: self.win.search_recipe(n),
                                  35 + sc, key=f"recipe:{name}"))
        return out[:4]

    def _problems(self, query: str, now: float) -> list[Result]:
        hist = self.engine.historian
        if hist is None or len(normalize(query)) < 3:
            return []
        out = []
        for r in hist.problems(now - HISTORY_DAYS * 86400, now):
            text = " ".join(str(r.get(k) or "") for k in ("category", "reason", "operator", "comment", "recipe"))
            sc = match_score(query, text)
            if sc:
                kind = tr("Paro") if r.get("kind") == "downtime" else tr("Calidad")
                when = time.strftime("%d/%m %H:%M", time.localtime(r["start"]))
                mins = (r.get("duration_s") or 0) / 60
                out.append(Result("problem", f"{r.get('reason') or ''} · {when}",
                                  f"{kind} · {r.get('category') or ''} · {mins:.0f} min"
                                  + (f" · {r['operator']}" if r.get("operator") else ""),
                                  "problems", lambda r=r: self.win.open_problem(r), 20 + sc + r["start"] / 1e12))
        return sorted(out, key=lambda r: -r.score)[:4]

    def _events(self, query: str, now: float) -> list[Result]:
        hist = self.engine.historian
        if hist is None or len(normalize(query)) < 3:
            return []
        out, seen = [], set()
        for ts, _kind, level, _rule, var, message, _recipe in reversed(
                hist.events_between(now - HISTORY_DAYS * 86400, now)):
            msg = translate_text(message or "")
            if msg in seen:
                continue
            sc = match_score(query, f"{msg} {var or ''}")
            if sc:
                seen.add(msg)
                try:
                    lvl = Level(level)
                except (TypeError, ValueError):
                    lvl = None
                out.append(Result("event", msg, time.strftime("%d/%m %H:%M", time.localtime(ts)), "events",
                                  lambda: self.win.show_page("events"), 15 + sc,
                                  level_color(lvl).name() if lvl is not None and lvl >= Level.WARN else None))
            if len(out) >= 4:
                break
        return out

    # --- recientes -------------------------------------------------------------------
    def remember(self, r: Result) -> None:
        if r.key:
            self.recent = [r.key] + [k for k in self.recent if k != r.key][:RECENT_MAX - 1]

    def _recent_results(self) -> list[Result]:
        out = []
        for key in self.recent:
            kind, _, ident = key.partition(":")
            if kind == "var":
                v = self.engine.config.variable(ident)
                if v is not None:
                    out += [r for r in self._variables(v.id) if r.key == key][:1]
            elif kind == "page":
                out += [r for r in self._pages(ident) if r.key == key][:1] or \
                       [r for r in self._pages_all() if r.key == key]
            elif kind == "recipe":
                out += [r for r in self._recipes(ident) if r.key == key]
            elif kind == "act":
                out += [r for r in self._actions(ident.split("›")[-1]) if r.key == key][:1]
        for r in out:
            r.subtitle = (r.subtitle + "  ·  " if r.subtitle else "") + tr("reciente")
        if not out:
            out.append(Result("hint", tr("Escribe una variable, página, acción, receta, paro o una hora"),
                              tr("p. ej. «diámetro», «exportar», «ayer 14:30», «hace 2 h», «turno»"), "search"))
        return out

    def _pages_all(self) -> list[Result]:
        from .main_window import NAV_ITEMS, NAV_TOOLS
        return [Result("page", tr(label), tr("Página"), key, lambda k=key: self.win.show_page(k), key=f"page:{key}")
                for key, label, _ in NAV_ITEMS + NAV_TOOLS]


class SearchPopup(QFrame):
    """Lista de resultados bajo la caja de búsqueda (no le quita el foco al teclado)."""

    def __init__(self, parent: QWidget):
        super().__init__(parent, Qt.Tool | Qt.FramelessWindowHint | Qt.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setObjectName("searchPopup")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 4, 4, 4)
        self.list = QListWidget()
        self.list.setObjectName("searchList")
        self.list.setFocusPolicy(Qt.NoFocus)
        self.list.setIconSize(QSize(18, 18))
        self.list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        lay.addWidget(self.list)
        self.hint = QLabel(tr("↑ ↓ elegir · Enter abrir · Esc cerrar"))
        self.hint.setStyleSheet(f"color:{theme.c('muted')}; font-size:11px; padding: 2px 6px;")
        lay.addWidget(self.hint)


class SearchBox(QLineEdit):
    """Caja de búsqueda de la barra superior (Ctrl+K o un toque la activan)."""

    def __init__(self, win, parent=None):
        super().__init__(parent)
        self.win = win
        self.setObjectName("search")
        self.setPlaceholderText(tr("Buscar variable, acción, paro u hora…  (Ctrl+K)"))
        self.setClearButtonEnabled(True)
        self.addAction(icons.icon("search", theme.c("muted")), QLineEdit.LeadingPosition)
        self.provider = SearchProvider(win)
        self.popup = SearchPopup(self)
        self.popup.list.itemClicked.connect(self._activate)
        self.results: list[Result] = []
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(120)
        self._timer.timeout.connect(self.refresh)
        self.textEdited.connect(lambda _: self._timer.start())
        self.installEventFilter(self)

    # --- resultados --------------------------------------------------------------------
    def refresh(self) -> None:
        self.results = self.provider.results(self.text())
        lst = self.popup.list
        lst.clear()
        for r in self.results:
            sub = r.kind == "sub"
            title = ("      ↳ " if sub else "") + r.title
            it = QListWidgetItem(title if not r.subtitle else f"{title}\n{'      ' if sub else ''}{r.subtitle}")
            color = r.color or (theme.c("muted") if sub else theme.c("accent"))
            it.setIcon(icons.icon(r.icon, color))
            if r.kind in KIND_LABEL:
                it.setToolTip(tr(KIND_LABEL[r.kind]))
            if r.run is None:
                it.setFlags(Qt.ItemIsEnabled)
                it.setForeground(QColor(theme.c("muted")))
            lst.addItem(it)
        if self.results and self.results[0].run is not None:
            lst.setCurrentRow(0)
        self._place()

    def _place(self) -> None:
        if not self.results:
            self.popup.hide()
            return
        w = max(self.width(), 460)
        rows = sum(self.popup.list.sizeHintForRow(i) for i in range(self.popup.list.count()))
        h = min(rows + 34, 520)
        self.popup.resize(w, h)
        self.popup.move(self.mapToGlobal(QPoint(0, self.height() + 2)))
        self.popup.show()
        self.popup.raise_()

    def _activate(self, item=None) -> None:
        row = self.popup.list.row(item) if item is not None else self.popup.list.currentRow()
        if not 0 <= row < len(self.results):
            return
        r = self.results[row]
        if r.run is None:
            return
        self.provider.remember(r)
        self.popup.hide()
        self.clear()
        self.clearFocus()
        r.run()

    def _move(self, d: int) -> None:
        lst = self.popup.list
        n = lst.count()
        if not n:
            return
        row = lst.currentRow()
        for _ in range(n):
            row = (row + d) % n
            if self.results[row].run is not None:
                break
        lst.setCurrentRow(row)

    def eventFilter(self, obj, event) -> bool:
        et = event.type()
        if et == QEvent.FocusIn:
            QTimer.singleShot(0, self.refresh)
        elif et == QEvent.FocusOut:
            QTimer.singleShot(150, lambda: None if self.hasFocus() else self.popup.hide())
        elif et == QEvent.KeyPress:
            k = event.key()
            if k == Qt.Key_Down:
                self._move(1)
                return True
            if k == Qt.Key_Up:
                self._move(-1)
                return True
            if k in (Qt.Key_Return, Qt.Key_Enter):
                self._activate()
                return True
            if k == Qt.Key_Escape:
                self.popup.hide()
                self.clear()
                self.clearFocus()
                return True
        return super().eventFilter(obj, event)

    def open(self) -> None:
        self.setFocus(Qt.ShortcutFocusReason)
        self.selectAll()
        self.refresh()
