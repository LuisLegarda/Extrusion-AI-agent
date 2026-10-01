"""Punto de entrada de la aplicación de escritorio."""
from __future__ import annotations

import argparse
import logging
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
    home_dir = Path(home) if home else default_home()
    home_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(level=logging.INFO, filename=str(home_dir / "app.log"),
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    app = QApplication(sys.argv[:1])
    app.setApplicationName("Monitor de extrusión")
    ctx = build(home_dir, demo=args.demo)
    apply_ui_prefs(ctx.workspace.load_state().get("ui", {}))  # idioma y tema guardados
    translator = Translator()
    translator.install(app)
    if ctx.exporter is not None:
        ctx.exporter.start()  # no hace nada hasta que se configure la carpeta compartida
    win = MainWindow(ctx)
    win.show()
    if args.autostart or args.demo:
        start_timer_autorun(win)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
