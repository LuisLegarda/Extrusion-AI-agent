"""Idioma de la interfaz (español / inglés).

Los textos del programa están escritos en español. En inglés:
* `tr()` traduce textos dinámicos (plantillas con `{campo}`).
* `translate_widget()` recorre una ventana ya construida y traduce los textos fijos
  (etiquetas, botones, pestañas, menús, encabezados, listas desplegables…).
* `Translator` hace esto automáticamente cada vez que se muestra una ventana o un diálogo.
* Los textos con valores (mensajes del motor: hallazgos, eventos, recorridos; avisos de la interfaz) se
  traducen por plantilla (`EN_PATTERNS`): se generan en español y al mostrarlos se reconoce la plantilla.
"""
from __future__ import annotations

import re
from typing import Optional

from .i18n_en import EN, EN_PATTERNS

LANGS = {"es": "Español", "en": "English"}
_lang = "es"
_TAG = re.compile(r"(<[^>]+>|&nbsp;)")
_DECOR = re.compile(r"^(\s*)(.*?)([\s:…]*)$", re.S)


def set_lang(lang: str) -> None:
    global _lang
    _lang = lang if lang in LANGS else "es"


def lang() -> str:
    return _lang


def tr(text: str, **fields) -> str:
    """Traduce `text` (clave en español) al idioma activo y rellena `{campos}`."""
    out = EN.get(text, text) if _lang == "en" else text
    return out.format(**fields) if fields else out


_compiled: Optional[list] = None


def _patterns() -> list:
    """Plantillas con valores («{}» fuera de tolerancia: …): (texto fijo más largo, expresión regular, traducción).

    Las más largas primero, para que gane la más específica. El texto fijo sirve de filtro rápido: solo se
    evalúa la expresión regular si ese fragmento aparece en el texto.
    """
    global _compiled
    if _compiled is None:
        _compiled = []
        for es, en in sorted(EN_PATTERNS.items(), key=lambda kv: -len(kv[0])):
            chunks = es.split("{}")
            # Un valor entre «comillas» o 'apóstrofos' es un nombre propio (variable, recorrido…): no se traduce.
            names = [c[-1:] in ("«", "'") for c in chunks[:-1]]
            flags = re.S if "\n" in es else 0
            _compiled.append((max(chunks, key=len), re.compile(re.escape(es).replace(r"\{\}", "(.+?)"), flags),
                              en, names))
    return _compiled


def _group(g: str, depth: int) -> str:
    """Valor capturado: se traduce si es un texto conocido o una lista de textos («a; b», «a, b»)."""
    if len(g.strip()) < 4:  # un valor muy corto es un dato (un número, una unidad, «a»), no un texto
        return g
    t = _plain(g, depth)
    if t is not None:
        return t
    for sep in ("; ", ", "):
        if sep in g:
            parts = g.split(sep)
            out = [_plain(x, depth) if len(x.strip()) >= 4 else None for x in parts]
            if any(o is not None for o in out):
                return sep.join(o if o is not None else x for o, x in zip(out, parts))
    return g


def _by_pattern(core: str, depth: int) -> Optional[str]:
    if depth > 4 or len(core) > 2000 or not any(c.isalpha() for c in core):
        return None
    for literal, rx, en, names in _patterns():
        if literal in core:
            m = rx.fullmatch(core)
            if m:
                return en.format(*[g if name else _group(g, depth + 1) for g, name in zip(m.groups(), names)])
    return None


def _plain(s: str, depth: int = 0, patterns: bool = True) -> Optional[str]:
    if not s or not s.strip():
        return None
    t = EN.get(s)
    if t is not None:
        return t
    m = _DECOR.match(s)
    lead, core, tail = m.group(1), m.group(2), m.group(3)
    t = EN.get(core)
    if t is not None:
        return lead + t + tail
    # Iconos o viñetas al inicio (p. ej. «📋 Recetas», «• …»): se traduce el resto.
    m2 = re.match(r"^(\W+\s+)(.+)$", core, re.S)
    if m2 and m2.group(2) in EN:
        return lead + m2.group(1) + EN[m2.group(2)] + tail
    if not patterns:
        return None
    end = tail.rstrip()
    if end:  # con valores: la plantilla puede terminar en «:» o «…»
        t = _by_pattern(core + end, depth)
        if t is not None:
            return lead + t + tail[len(end):]
    t = _by_pattern(core, depth)
    if t is not None:
        return lead + t + tail
    if m2:
        t = _by_pattern(m2.group(2), depth)
        if t is not None:
            return lead + m2.group(1) + t + tail
    return None


def translate_message(s: str) -> str:
    """Mensaje del motor (hallazgos, eventos, recorridos) o texto con valores, en el idioma activo."""
    return translate_text(s)


def _lines(part: str) -> Optional[str]:
    """Traduce un fragmento; si tiene varios renglones, cada uno por separado."""
    if "\n" not in part:
        return _plain(part)
    if part in EN:
        return EN[part]
    rows = part.split("\n")
    out = [_plain(r) for r in rows]
    if all(o is None for o in out):
        return _plain(part)  # plantilla de varios renglones
    return "\n".join(o if o is not None else r for o, r in zip(out, rows))


def translate_text(s: str) -> str:
    """Traducción de un texto; en texto enriquecido se traduce cada fragmento entre marcas y cada renglón."""
    if _lang != "en" or not s:
        return s
    if "<" not in s and "\n" not in s:
        return _plain(s) or s
    if s in EN:
        return EN[s]
    if "<" not in s:
        return _lines(s) or s
    direct = _plain(s, patterns=False)  # texto con formato: las plantillas se aplican por fragmento
    if direct is not None:
        return direct
    parts = _TAG.split(s) if "<" in s else [s]
    changed = False
    for i, part in enumerate(parts):
        if not part or part.startswith("<") or part == "&nbsp;":
            continue
        t = _lines(part)
        if t is not None:
            parts[i] = t
            changed = True
    return "".join(parts) if changed else s


def translate_widget(root, children: bool = True) -> None:
    """Traduce los textos fijos de `root` y, con `children`, de todos sus hijos."""
    if _lang != "en" or root is None:
        return
    from PySide6.QtWidgets import (
        QAbstractButton, QComboBox, QDoubleSpinBox, QGroupBox, QLabel, QLineEdit, QListWidget, QMenu, QMenuBar,
        QSpinBox, QTableWidget, QTabWidget, QTreeWidget, QWidget,
    )

    def actions(w) -> None:
        for act in w.actions():
            if act.text():
                act.setText(translate_text(act.text()))
            if act.toolTip() and act.toolTip() != act.text():
                act.setToolTip(translate_text(act.toolTip()))
            if act.menu() is not None:
                m = act.menu()
                m.setTitle(translate_text(m.title()))
                actions(m)

    widgets = [root] + (root.findChildren(QWidget) if children else [])
    for w in widgets:
        if w.isWindow() and w.windowTitle():
            w.setWindowTitle(translate_text(w.windowTitle()))
        if w.toolTip():
            w.setToolTip(translate_text(w.toolTip()))
        if isinstance(w, QLabel):
            w.setText(translate_text(w.text()))
        elif isinstance(w, QAbstractButton):
            w.setText(translate_text(w.text()))
        elif isinstance(w, QGroupBox):
            w.setTitle(translate_text(w.title()))
        elif isinstance(w, QLineEdit) and w.placeholderText():
            w.setPlaceholderText(translate_text(w.placeholderText()))
        elif isinstance(w, QComboBox):
            for i in range(w.count()):
                w.setItemText(i, translate_text(w.itemText(i)))
        elif isinstance(w, (QSpinBox, QDoubleSpinBox)):
            w.setSuffix(translate_text(w.suffix()))
            w.setPrefix(translate_text(w.prefix()))
        elif isinstance(w, QTabWidget):
            for i in range(w.count()):
                w.setTabText(i, translate_text(w.tabText(i)))
        elif isinstance(w, QTableWidget):
            for i in range(w.columnCount()):
                it = w.horizontalHeaderItem(i)
                if it is not None:
                    it.setText(translate_text(it.text()))
        elif isinstance(w, QTreeWidget):
            hdr = w.headerItem()
            for i in range(w.columnCount()):
                hdr.setText(i, translate_text(hdr.text(i)))
        elif isinstance(w, QListWidget):
            for i in range(w.count()):
                it = w.item(i)
                it.setText(translate_text(it.text()))
        if isinstance(w, (QMenu, QMenuBar)) or w.actions():
            actions(w)
        plot = getattr(w, "getPlotItem", None)
        if plot is not None:  # títulos de las gráficas (pyqtgraph)
            try:
                pi = plot()
                title = pi.titleLabel.text if pi.titleLabel.isVisible() else ""
                if title:
                    new = translate_text(re.sub(r"<[^>]+>", "", title))
                    if new != re.sub(r"<[^>]+>", "", title):
                        pi.setTitle(new)
            except (AttributeError, RuntimeError):
                pass


class Translator:
    """Filtro de eventos de la aplicación: traduce cada ventana o diálogo al mostrarse."""

    def __init__(self):
        from PySide6.QtCore import QEvent, QObject

        class _Filter(QObject):
            def eventFilter(self, obj, event):  # noqa: N802 (API de Qt)
                if event.type() == QEvent.Show and _lang == "en":
                    try:
                        if obj.isWidgetType():
                            # Una ventana se traduce completa; un elemento que aparece después (un panel
                            # creado al vuelo, una tarjeta nueva) se traduce a sí mismo al mostrarse.
                            translate_widget(obj, children=obj.isWindow())
                    except RuntimeError:
                        pass
                return False

        self.filter = _Filter()

    def install(self, app) -> None:
        app.installEventFilter(self.filter)
        app._i18n_translator = self  # mantiene vivo el filtro mientras exista la aplicación
        install_live_translation()


_live_installed = False


def install_live_translation() -> None:
    """Traduce también los textos que se ponen después de mostrar la ventana (etiquetas, botones, avisos).

    En español no hace nada. En inglés cada `setText`, `setToolTip`… hecho desde el programa pasa por
    `translate_text`; un texto que ya está en inglés (o es un dato) queda igual.
    """
    global _live_installed
    if _live_installed:
        return
    _live_installed = True
    from PySide6.QtWidgets import QAbstractButton, QLabel, QListWidgetItem, QTableWidgetItem, QWidget

    def wrap(cls, name: str) -> None:
        orig = getattr(cls, name)

        def setter(self, text, *args, _orig=orig):
            if _lang == "en" and isinstance(text, str):
                text = translate_text(text)
            return _orig(self, text, *args)

        try:
            setattr(cls, name, setter)
        except TypeError:  # la clase no admite reemplazar el método: esos textos se traducen al mostrarse
            pass

    for cls, name in ((QLabel, "setText"), (QAbstractButton, "setText"), (QWidget, "setToolTip"),
                      (QWidget, "setWindowTitle"), (QListWidgetItem, "setText"), (QTableWidgetItem, "setText")):
        wrap(cls, name)
