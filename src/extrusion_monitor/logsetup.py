"""Registro del programa para producción: archivo con rotación y errores no atrapados.

* El registro rota (5 MB × 5 archivos): un programa que corre 24/7 no llena el disco.
* Una excepción no atrapada (en un botón, un temporizador o un hilo) queda en el registro en lugar de perderse:
  el programa empaquetado no tiene consola.
* Un cierre abrupto de bajo nivel (Qt, controladores) deja su rastro en `<nombre>-fallo.log` (faulthandler).
"""
from __future__ import annotations

import faulthandler
import logging
import sys
import threading
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional

MAX_BYTES = 5 * 1024 * 1024
BACKUPS = 5
_crash_file = None  # se mantiene abierto: faulthandler escribe en él al fallar

log = logging.getLogger("extrusion_monitor")


def setup_logging(home: Path, name: str = "app", level: int = logging.INFO) -> Path:
    """Configura el registro en `<home>/<name>.log` y los ganchos de errores. Devuelve la ruta del registro."""
    global _crash_file
    home = Path(home)
    home.mkdir(parents=True, exist_ok=True)
    path = home / f"{name}.log"
    root = logging.getLogger()
    root.setLevel(level)
    for h in list(root.handlers):  # una sola vez aunque se llame de nuevo (pruebas, reinicio de la ventana)
        if getattr(h, "_extrumon", False):
            root.removeHandler(h)
            h.close()
    handler = RotatingFileHandler(path, maxBytes=MAX_BYTES, backupCount=BACKUPS, encoding="utf-8", delay=True)
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    handler._extrumon = True
    root.addHandler(handler)

    def excepthook(exc_type, exc, tb) -> None:
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc, tb)
            return
        log.critical("Error no atrapado", exc_info=(exc_type, exc, tb))

    def thread_hook(args) -> None:
        if args.exc_type is SystemExit:
            return
        log.critical("Error no atrapado en el hilo «%s»", args.thread.name if args.thread else "?",
                     exc_info=(args.exc_type, args.exc_value, args.exc_traceback))

    sys.excepthook = excepthook
    threading.excepthook = thread_hook
    try:
        if _crash_file is None:
            _crash_file = open(home / f"{name}-fallo.log", "a", encoding="utf-8")
        faulthandler.enable(_crash_file)
    except (OSError, RuntimeError):
        pass
    return path


def show_startup_error(exc: BaseException, log_path: Optional[Path]) -> None:
    """Si el programa no puede abrir, lo dice en una ventana (sin consola no se vería nada)."""
    log.critical("No se pudo iniciar el programa", exc_info=exc)
    try:
        from PySide6.QtWidgets import QApplication, QMessageBox

        from .i18n import tr
        app = QApplication.instance() or QApplication(sys.argv[:1])  # noqa: F841 (debe existir para el diálogo)
        QMessageBox.critical(None, tr("No se pudo iniciar el programa"),
                             tr("Ocurrió un error al abrir el programa:\n\n{e}\n\nEl detalle quedó en:\n{p}",
                                e=f"{type(exc).__name__}: {exc}", p=str(log_path or "")))
    except Exception:  # sin interfaz gráfica: al menos queda en el registro
        pass
