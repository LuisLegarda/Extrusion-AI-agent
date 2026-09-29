"""Idioma de la interfaz (español / inglés).

Los textos del programa están escritos en español. En inglés:
* `tr()` traduce textos dinámicos (plantillas con `{campo}`).
* `translate_widget()` recorre una ventana ya construida y traduce los textos fijos
  (etiquetas, botones, pestañas, menús, encabezados, listas desplegables…).
* `Translator` hace esto automáticamente cada vez que se muestra una ventana o un diálogo.
Los mensajes del motor (hallazgos y eventos) se mantienen en español.
"""
from __future__ import annotations

import re
from typing import Optional

from .i18n_en import EN

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


def _plain(s: str) -> Optional[str]:
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
    # Iconos al inicio (p. ej. «📋 Recetas»): se traduce el resto.
    m2 = re.match(r"^(\W+\s+)(.+)$", core)
    if m2 and m2.group(2) in EN:
        return lead + m2.group(1) + EN[m2.group(2)] + tail
    return None


def translate_text(s: str) -> str:
    """Traducción de un texto fijo; en texto enriquecido se traduce cada fragmento entre marcas."""
    if _lang != "en" or not s:
        return s
    direct = _plain(s)
    if direct is not None:
        return direct
    if "<" not in s and "\n" not in s:
        return s
    parts = _TAG.split(s) if "<" in s else s.split("\n")
    changed = False
    for i, part in enumerate(parts):
        if not part or part.startswith("<") or part == "&nbsp;":
            continue
        t = _plain(part)
        if t is not None:
            parts[i] = t
            changed = True
    if not changed:
        return s
    return "".join(parts) if "<" in s else "\n".join(parts)


def translate_widget(root) -> None:
    """Traduce los textos fijos de `root` y de todos sus hijos."""
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

    widgets = [root] + root.findChildren(QWidget)
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
                        if obj.isWidgetType() and obj.isWindow():
                            translate_widget(obj)
                    except RuntimeError:
                        pass
                return False

        self.filter = _Filter()

    def install(self, app) -> None:
        app.installEventFilter(self.filter)
        app._i18n_translator = self  # mantiene vivo el filtro mientras exista la aplicación
