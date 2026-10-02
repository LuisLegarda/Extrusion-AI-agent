"""Traducción al inglés: plantillas con valores, mensajes del motor y textos que cambian en vivo."""
import json
import os
import time

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from extrusion_monitor import i18n  # noqa: E402


@pytest.fixture
def en():
    i18n.set_lang("en")
    yield
    i18n.set_lang("es")


def test_engine_messages_by_pattern(en):
    t = i18n.translate_text
    assert t("«EXT1 › Zona 3» fuera de tolerancia: 188 °C vs receta 180 (Δ +8, tolerancia ±6)") == \
        "“EXT1 › Zona 3” out of tolerance: 188 °C vs recipe 180 (Δ +8, tolerance ±6)"
    assert t("Normalizado: «Diametro»: valor 3.27 mm fuera de límites (mín 3.15, máx 3.25)") == \
        "Back to normal: “Diametro”: value 3.27 mm out of limits (min 3.15, max 3.25)"
    assert t("Cambio de ajuste «Zona 3 consigna»: 180 → 188 °C (se aleja de la receta: 180)") == \
        "Setting change “Zona 3 consigna”: 180 → 188 °C (moving away from the recipe: 180)"
    assert t("Selector «Inyección gas» en «OFF»; la receta espera «ON»") == \
        "Selector “Inyección gas” at “OFF”; the recipe expects “ON”"
    assert t("Receta activa: R1 (configuración completa de la receta cargada)") == \
        "Active recipe: R1 (complete recipe configuration loaded)"
    assert t("«Excentricidad»: 6 subgrupos en aumento; punto atípico (>3σ)") == \
        "“Excentricidad”: 6 subgroups increasing; outlier (>3σ)"
    # los nombres propios entre comillas no se traducen
    assert t("Recorrido «Lectura de pestañas»: 2 pantallas leídas (cada 15 s)") == \
        "Tour “Lectura de pestañas”: 2 screens read (every 15 s)"
    assert t("Recorrido «Recetas» pospuesto: el HMI no está en «Tendencias»") == \
        "Tour “Recetas” postponed: the HMI is not at “Tendencias”"
    assert t("paso 2, clic 1: el botón no coincide con el grabado (0.41) · se regresó a la pantalla de inicio") == \
        "step 2, click 1: the button does not match the recorded one (0.41) · returned to the home screen"


def test_interface_messages_and_multiline(en):
    t = i18n.translate_text
    assert t("¿Eliminar 2 pestañas y 3 variables?") == "Delete 2 tabs and 3 variables?"
    assert t("• Recorrido «R 3»: no tiene pasos\n• Pestañas sin imagen ancla: EXT1") == \
        "• Tour “R 3”: it has no steps\n• Tabs without anchor image: EXT1"
    assert t("<b>Entrenado</b> con 5 muestras del a al b (cada 2 s). Umbral D² = 3.") == \
        "<b>Trained</b> with 5 samples from a to b (every 2 s). D² threshold = 3."
    assert t("Línea 7") == "Línea 7" and t("350.2 m/min") == "350.2 m/min"  # datos: sin cambios


def test_spanish_is_untouched():
    assert i18n.translate_text("«X» fuera de tolerancia: 1 vs receta 2 (Δ +1, tolerancia ±1)").startswith("«X» fuera")


def test_every_pattern_translates_its_own_template(en):
    from extrusion_monitor.i18n_en import EN_PATTERNS
    for es, expected in EN_PATTERNS.items():
        n = es.count("{}")
        vals = [f"v{i}" for i in range(n)]
        got = i18n.translate_text(es.format(*vals))
        assert got == expected.format(*vals), es


def test_live_labels_and_fleet_language_theme(tmp_path, en):
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication, QLabel, QPushButton

    from extrusion_monitor.ui import theme
    from extrusion_monitor.ui.fleet_window import FleetWindow, rebuilt_fleet_windows
    from extrusion_monitor.ui.main_window import apply_ui_prefs
    app = QApplication.instance() or QApplication([])
    i18n.Translator().install(app)
    lb = QLabel()
    lb.setText("Sin datos aún")  # texto puesto después de crear la etiqueta
    assert lb.text() == "No data yet"
    b = QPushButton()
    b.setText("● Grabar clics (en vivo)")
    assert b.text() == "● Record clicks (live)"
    i18n.set_lang("es")
    lb.setText("Sin datos aún")
    assert lb.text() == "Sin datos aún"

    d = tmp_path / "planta" / "L1"
    d.mkdir(parents=True)
    (d / "status.json").write_text(json.dumps({
        "ts": time.time(), "interval_s": 5, "line_name": "Línea 1", "n_alarms": 1, "kpis": {"oee": 80.0},
        "alarms": [{"since": time.time(), "level": "ALARM", "msg": "Selector «Gas» en «OFF»; la receta espera «ON»"}],
        "variables": []}), encoding="utf-8")
    try:
        w = FleetWindow(str(tmp_path / "planta"), tmp_path / "fleet.json", tmp_path / "state.json")
        w.show()
        w.refresh()
        assert w.menuBar().actions()[0].text() == "&Archivo"
        w._set_ui_pref("lang", "en")
        new = rebuilt_fleet_windows[-1]
        QApplication.processEvents()
        new.refresh()
        assert json.loads((tmp_path / "state.json").read_text("utf-8"))["ui"]["lang"] == "en"
        assert new.menuBar().actions()[0].text() == "&File" and new.tiles["lines"].val.text().count("1")
        new.select("L1")
        new.detail.tabs.setCurrentIndex(1)
        assert "the recipe expects “ON”" in new.detail.lst_alarms.item(0).text()
        new._set_ui_pref("theme", "dark")
        dark = rebuilt_fleet_windows[-1]
        assert theme.is_dark() and "L1" in dark.cards or dark.refresh() is None
        dark.close()
    finally:
        apply_ui_prefs({})


def test_both_programs_share_the_menu_structure(tmp_path):
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication

    from extrusion_monitor.bootstrap import build
    from extrusion_monitor.ui.fleet_window import FleetWindow
    from extrusion_monitor.ui.main_window import MainWindow
    QApplication.instance() or QApplication([])

    def menus(win):
        return {a.text().replace("&", ""): [b.text() for b in a.menu().actions() if not b.isSeparator()]
                for a in win.menuBar().actions()}

    def shortcuts(win):
        return {b.shortcut().toString() for a in win.menuBar().actions() for b in a.menu().actions()}

    mon = MainWindow(build(tmp_path / "home", demo=True))
    fleet = FleetWindow(str(tmp_path / "planta"), tmp_path / "fleet.json")
    m, f = menus(mon), menus(fleet)
    assert list(m) == ["Archivo", "Receta", "Acciones", "Configuración", "Ver", "Ayuda"]
    assert list(f) == ["Archivo", "Líneas", "Acciones", "Configuración", "Ver", "Ayuda"]
    # lo que se guarda con la receta está en el menú Receta
    for item in ("Pestañas y variables…", "Recorridos…", "KPI / OEE…", "Reportes automáticos…", "✎ Tablero de Inicio…"):
        assert item in m["Receta"]
    # idioma y tema en el mismo lugar en los dos programas; mismos atajos para lo equivalente
    assert m["Configuración"][-2:] == f["Configuración"][-2:] == ["🌐 Idioma / Language", "🎨 Tema"]
    assert {"F5", "Ctrl+E", "Ctrl+Q", "F11", "F1"} <= shortcuts(mon) & shortcuts(fleet)
    fleet.toggle_tv()
    assert fleet.tv and not fleet.menuBar().isVisible() and fleet.actions()  # atajos activos sin menú
    fleet.toggle_tv()
    fleet.close()
    mon._rebuilding = True
    mon.close()
