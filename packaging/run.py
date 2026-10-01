import sys
from pathlib import Path

from extrusion_monitor.app import main

if __name__ == "__main__":
    args = sys.argv[1:]
    # DashboardGlobal.exe es el mismo programa: abre directamente el dashboard global de líneas.
    if Path(sys.executable).stem.lower().startswith("dashboard") and "--fleet" not in args:
        args = ["--fleet", *args]
    sys.exit(main(args))
