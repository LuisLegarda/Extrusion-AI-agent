# PyInstaller: pyinstaller packaging/extrusion_monitor.spec
import os

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

RES = os.path.join(SPECPATH, "..", "src", "extrusion_monitor", "resources")  # iconos (SPECPATH lo define PyInstaller)

hidden = collect_submodules("winrt") + collect_submodules(
    "pyqtgraph", filter=lambda name: not name.startswith(("pyqtgraph.examples", "pyqtgraph.opengl"))) + \
    collect_submodules("reportlab.pdfbase") + collect_submodules("reportlab.graphics.charts")

a = Analysis(
    ["run.py"],
    pathex=["../src"],
    hiddenimports=hidden,
    # fuentes de los reportes PDF y mapas de color de las gráficas de contorno (análisis estadístico)
    datas=collect_data_files("reportlab") + collect_data_files("pyqtgraph", includes=["colors/maps/*.csv"])
    + [(RES, "extrusion_monitor/resources")],  # iconos de las ventanas
    excludes=["tkinter", "matplotlib", "PySide6.QtWebEngineCore", "PySide6.Qt3DCore"],
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="ExtrusionMonitor",
    console=False,
    icon=os.path.join(RES, "monitor.ico"),
)
# Segundo ejecutable en la misma carpeta (comparte bibliotecas): abre el dashboard global de líneas.
fleet = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="DashboardGlobal",
    console=False,
    icon=os.path.join(RES, "dashboard.ico"),
)
coll = COLLECT(exe, fleet, a.binaries, a.datas, name="ExtrusionMonitor")
