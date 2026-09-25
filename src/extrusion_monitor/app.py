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
    args = parser.parse_args(argv)

    from PySide6.QtWidgets import QApplication

    from .bootstrap import build
    from .config import default_home
    from .ui.common import STYLE
    from .ui.main_window import MainWindow, start_timer_autorun

    home = args.home
    if args.demo and home is None:
        home = default_home() / "demo"
    home_dir = Path(home) if home else default_home()
    home_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(level=logging.INFO, filename=str(home_dir / "app.log"),
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    app = QApplication(sys.argv[:1])
    app.setApplicationName("Monitor de extrusión")
    app.setStyle("Fusion")
    app.setStyleSheet(STYLE)
    ctx = build(home_dir, demo=args.demo)
    win = MainWindow(ctx)
    win.show()
    if args.autostart or args.demo:
        start_timer_autorun(win)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
