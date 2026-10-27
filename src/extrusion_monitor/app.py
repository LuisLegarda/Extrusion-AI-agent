"""Punto de entrada de la aplicación de escritorio."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Monitor de extrusión")
    parser.add_argument("--demo", action="store_true", help="usar un HMI simulado")
    parser.add_argument("--home", type=Path, help="carpeta de datos (config, recetas, historial)")
    parser.add_argument("--autostart", action="store_true", help="iniciar el monitoreo al abrir")
    parser.add_argument("--fleet", nargs="?", const="", metavar="CARPETA",
                        help="abrir el dashboard global de varias líneas (carpeta compartida opcional)")
    args = parser.parse_args(argv)
    if args.fleet is not None:
        from .ui.fleet_window import run_fleet
        return run_fleet(args.fleet or None, args.home)

    from PySide6.QtWidgets import QApplication

    from .bootstrap import build
    from .config import default_home
    from .i18n import Translator
    from .ui.main_window import MainWindow, apply_ui_prefs, start_timer_autorun

    home = args.home
    if args.demo and home is None:
        home = default_home() / "demo"
    from .logsetup import setup_logging, show_startup_error
    home_dir = Path(home) if home else default_home()
    log_path = setup_logging(home_dir, "app")

    app = QApplication(sys.argv[:1])
    app.setApplicationName("Monitor de extrusión")
    try:
        ctx = build(home_dir, demo=args.demo)
        apply_ui_prefs(ctx.workspace.load_state().get("ui", {}))  # idioma y tema guardados
        translator = Translator()
        translator.install(app)
        if ctx.exporter is not None:
            ctx.exporter.start()  # no hace nada hasta que se configure la carpeta compartida
        win = MainWindow(ctx)
    except Exception as exc:  # configuración dañada, carpeta sin permisos…: que se vea por qué no abre
        show_startup_error(exc, log_path)
        return 1
    win.show()
    if ctx.recovered:
        from PySide6.QtWidgets import QMessageBox

        from .i18n import tr
        QMessageBox.warning(win, tr("Configuración recuperada"),
                            tr("La configuración guardada estaba dañada (por ejemplo, por un apagón al guardar) y se "
                               "recuperó del respaldo «{b}». La copia dañada quedó junto a ella como "
                               "«config.dañado-….json». Revisa los últimos cambios.", b=ctx.recovered))
    if args.autostart or args.demo:
        start_timer_autorun(win)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
