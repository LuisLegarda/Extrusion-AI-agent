"""Auditoría de traducciones: textos en español que en inglés quedarían sin traducir.

Uso (desde la raíz del repositorio):

    python tools/i18n_audit.py            # barrido del código (cadenas y f-strings)
    python tools/i18n_audit.py --ui       # además abre las ventanas, diálogos y páginas en inglés

El barrido del código lista:
* cadenas en llamadas de interfaz (setText, QLabel, QMessageBox, addItem, tr…) sin traducción;
* f-strings con texto en español que no coinciden con ninguna plantilla de `EN_PATTERNS`.
Los datos del usuario (nombres de variables, líneas, recetas…) no se traducen y pueden aparecer en el barrido
de ventanas: se revisan a mano.
"""
from __future__ import annotations

import ast
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "tests")]

from extrusion_monitor import i18n  # noqa: E402
from extrusion_monitor.i18n_en import EN, EN_PATTERNS  # noqa: E402

SRC = ROOT / "src" / "extrusion_monitor"
SPANISH = re.compile(r"[áéíóúñ¿¡]|\b(de|del|las|los|con|sin|para|por|una|que|el|la|en|se|es|no|al|cada|línea|"
                     r"receta|datos|guardar|abrir|exportar|cerrar|agregar|eliminar|nuevo|nueva|turno|paro)\b", re.I)
UI_CALLS = {"tr", "setText", "setToolTip", "setWindowTitle", "setPlaceholderText", "addAction", "addMenu", "addItem",
            "addItems", "addTab", "setTitle", "QLabel", "QPushButton", "QCheckBox", "QRadioButton", "QGroupBox",
            "QAction", "information", "warning", "question", "critical", "about", "setHorizontalHeaderLabels",
            "setHeaderLabels", "addRow", "showMessage", "setStatusTip", "setSpecialValueText", "setSuffix",
            "setPrefix", "QToolButton", "setTabText", "insertItem", "getText", "getItem", "getInt", "getDouble",
            "getSaveFileName", "getOpenFileName", "getExistingDirectory", "setLabelText", "QMessageBox",
            "addButton", "setInformativeText", "QListWidgetItem", "QTableWidgetItem", "QTreeWidgetItem"}
LOG_NAMES = {"log", "logger", "logging", "_log"}
SKIP_FILES = {"i18n_en.py", "simulator.py", "icons.py"}


def _parents(tree):
    return {c: p for p in ast.walk(tree) for c in ast.iter_child_nodes(p)}


def _context(node, parents) -> tuple[bool, bool]:
    """(está en un mensaje de registro, está en una llamada de interfaz)."""
    q, in_log, in_ui = node, False, False
    while q in parents:
        q = parents[q]
        if isinstance(q, ast.Call):
            fn = q.func
            name = fn.attr if isinstance(fn, ast.Attribute) else (fn.id if isinstance(fn, ast.Name) else "")
            if isinstance(fn, ast.Attribute) and getattr(fn.value, "id", "") in LOG_NAMES:
                in_log = True
            if name in UI_CALLS:
                in_ui = True
        if isinstance(q, (ast.FunctionDef, ast.ClassDef)):
            break
    return in_log, in_ui


def scan_code() -> list[str]:
    i18n.set_lang("en")
    out = []
    for f in sorted(SRC.rglob("*.py")):
        if f.name in SKIP_FILES:
            continue
        tree = ast.parse(f.read_text("utf-8"))
        parents = _parents(tree)
        for node in ast.walk(tree):
            where = f"{f.relative_to(ROOT)}:{getattr(node, 'lineno', 0)}"
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                p = parents.get(node)
                if isinstance(p, (ast.Expr, ast.JoinedStr)):
                    continue
                s = node.value.strip()
                if len(s) < 3 or not SPANISH.search(s) or not re.search(r"[A-Za-zÁ-ú]{3}", s):
                    continue
                in_log, in_ui = _context(node, parents)
                if in_log or not in_ui:
                    continue
                if i18n.translate_text(node.value) == node.value:
                    out.append(f"{where}  «{node.value[:120]}»")
            elif isinstance(node, ast.JoinedStr) and not isinstance(parents.get(node), ast.JoinedStr):
                in_log, in_ui = _context(node, parents)
                if in_log or not in_ui:
                    continue
                parts = [v.value if isinstance(v, ast.Constant) else "Xy7" for v in node.values]
                lit = re.sub(r"<[^>]+>", " ", "".join(v.value for v in node.values if isinstance(v, ast.Constant)))
                if not SPANISH.search(lit) or len(re.findall(r"[A-Za-zÁ-ú]{3,}", lit)) < 2:
                    continue
                sample = "".join(parts)
                if i18n.translate_text(sample) == sample:
                    out.append(f"{where}  f«{sample[:120]}»")
    i18n.set_lang("es")
    return out


W = re.compile(r"[A-Za-zÁÉÍÓÚÑáéíóúñü]+")


def _spanish_vocab() -> set[str]:
    en_words = {w.lower() for v in list(EN.values()) + list(EN_PATTERNS.values()) for w in W.findall(v)}
    es = {w.lower() for k in list(EN) + list(EN_PATTERNS) for w in W.findall(k)} - en_words
    es |= {"de", "del", "las", "los", "con", "sin", "para", "por", "una", "que", "el", "la", "en", "se", "es"}
    return {w for w in es if len(w) >= 2} - {"no", "id", "pid", "cpk", "oee", "hmi", "spc", "ok", "pdf", "csv", "mm"}


DEMO_DATA = re.compile(r"Línea \d|Turno \d|Juan Pérez|María López|Demo línea|Inyección|Receta en HMI|Andon|Ámbar|"
                       r"Metros por vuelta|Presión de cabezal|Nivel de tolva|Temperaturas de zona|Diámetro|Diametro|"
                       r"Velocidad|Lectura de pestañas|Reporte de producción|Cámara del tablero|Principal|EXT1|"
                       r"Linea|Cambio de dado|Falta de material|Mecánico|Eléctrico|Ajuste de proceso|consigna|"
                       r"Cambio de producto|Paro programado|Rotura|Falla de|Espesor|Marcado|Arranque|Junta|Zona \d|"
                       r"Material húmedo|Cambio de carrete|Falta de compuesto|Español|Carga motor|Agua enfriam|"
                       r"tornillo|NEGRO|rojo|verde|empresa|SERVIDOR|Cuello|Cabezal|Dado|Husillo|Cambio$|Atasco")


def scan_ui() -> list[str]:
    """Abre el monitor (con lecturas), sus páginas y diálogos, y el dashboard, en inglés."""
    import importlib
    import inspect
    import pkgutil
    import tempfile
    import time

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import (QAbstractButton, QApplication, QComboBox, QDialog, QGroupBox, QLabel, QLineEdit,
                                   QListWidget, QMainWindow, QTableWidget, QTabWidget, QTreeWidget, QWidget)
    app = QApplication.instance() or QApplication([])
    i18n.set_lang("en")
    i18n.Translator().install(app)
    vocab = _spanish_vocab()
    found: dict[str, str] = {}

    def add(text: str, where: str) -> None:
        plain = re.sub(r"<[^>]+>|&nbsp;", " ", text or "")
        words = {w.lower() for w in W.findall(plain)}
        bad = [w for w in words if w in vocab]
        if bad and not (DEMO_DATA.search(plain) and len(bad) <= 3):
            found.setdefault(text[:200], where)

    def scan(w, where):
        for x in [w] + w.findChildren(QWidget):
            add(x.toolTip(), where)
            if isinstance(x, (QMainWindow, QDialog)):
                add(x.windowTitle(), where)
            if isinstance(x, (QLabel, QAbstractButton)):
                add(x.text(), where)
            elif isinstance(x, QGroupBox):
                add(x.title(), where)
            elif isinstance(x, QLineEdit):
                add(x.placeholderText(), where)
            elif isinstance(x, QComboBox):
                for i in range(x.count()):
                    add(x.itemText(i), where)
            elif isinstance(x, QTabWidget):
                for i in range(x.count()):
                    add(x.tabText(i), where)
            elif isinstance(x, QTableWidget):
                for c in range(x.columnCount()):
                    h = x.horizontalHeaderItem(c)
                    add(h.text() if h else "", where)
                for r in range(min(x.rowCount(), 40)):
                    for c in range(x.columnCount()):
                        it = x.item(r, c)
                        add(it.text() if it else "", where + " (celda)")
            elif isinstance(x, QTreeWidget):
                for c in range(x.columnCount()):
                    add(x.headerItem().text(c), where)
                stack = [x.topLevelItem(i) for i in range(x.topLevelItemCount())]
                while stack:
                    it = stack.pop()
                    for c in range(x.columnCount()):
                        add(it.text(c), where + " (árbol)")
                    stack += [it.child(i) for i in range(it.childCount())]
            elif isinstance(x, QListWidget):
                for i in range(min(x.count(), 60)):
                    add(x.item(i).text(), where)
        if isinstance(w, QMainWindow):
            def menus(acts):
                for a in acts:
                    add(a.text(), where + " (menú)")
                    if a.menu():
                        menus(a.menu().actions())
            menus(w.menuBar().actions())

    tmp = Path(tempfile.mkdtemp())
    from extrusion_monitor.bootstrap import build
    from extrusion_monitor.ui.main_window import NAV_ITEMS, MainWindow
    ctx = build(tmp / "home", demo=True)
    ctx.engine.sleep = lambda s: None
    win = MainWindow(ctx)
    win.show()
    for _ in range(25):
        ctx.engine.step()
        win.on_snapshot(ctx.engine.last)
    app.processEvents()
    for key, *_ in NAV_ITEMS:
        win.show_page(key)
        app.processEvents()
        scan(win, f"monitor:{key}")
    import extrusion_monitor.ui as uip
    simple = {"ctx": ctx, "engine": ctx.engine, "config": ctx.engine.config, "parent": None, "home": tmp / "home",
              "workspace": ctx.workspace, "cfg": ctx.engine.config}
    for m in pkgutil.iter_modules(uip.__path__):
        mod = importlib.import_module(f"extrusion_monitor.ui.{m.name}")
        for name, cls in inspect.getmembers(mod, inspect.isclass):
            if cls.__module__ != mod.__name__ or not issubclass(cls, QDialog):
                continue
            params = [p for p in list(inspect.signature(cls.__init__).parameters.values())[1:]
                      if p.default is inspect._empty and p.kind not in (p.VAR_POSITIONAL, p.VAR_KEYWORD)]
            if any(p.name not in simple for p in params):
                continue
            try:
                d = cls(*[simple[p.name] for p in params])
                d.show()
                app.processEvents()
                tabs = getattr(d, "tabs", None)
                if isinstance(tabs, QTabWidget):
                    for i in range(tabs.count()):
                        tabs.setCurrentIndex(i)
                        app.processEvents()
                        scan(d, f"diálogo:{name}")
                scan(d, f"diálogo:{name}")
                d.close()
            except Exception as exc:  # un diálogo que necesita más contexto: se omite
                print(f"  (omitido {name}: {type(exc).__name__})")
    win.close()
    from test_fleet_pages import make_plant
    from extrusion_monitor.ui.fleet_window import FleetWindow
    make_plant(tmp / "planta", time.time())
    fw = FleetWindow(str(tmp / "planta"), tmp / "fleet.json", tmp / "fstate.json")
    fw.show()
    fw.refresh()
    for key in ("lines", "map", "analyzer", "problems", "analysis", "maintenance"):
        fw.show_page(key)
        app.processEvents()
        scan(fw, f"dashboard:{key}")
    fw.close()
    i18n.set_lang("es")
    return [f"{where}  «{text}»" for text, where in sorted(found.items(), key=lambda kv: kv[1])]


def main() -> int:
    found = scan_code()
    print(f"Código: {len(found)} textos de interfaz sin traducción")
    for line in found:
        print("  " + line)
    if "--ui" in sys.argv:
        ui = scan_ui()
        print(f"Ventanas: {len(ui)} textos visibles en español (revisar: pueden ser datos del usuario)")
        for line in ui:
            print("  " + line)
        found += ui
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
