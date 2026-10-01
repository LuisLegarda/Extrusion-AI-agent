# PyInstaller: pyinstaller packaging/extrusion_monitor.spec
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

hidden = collect_submodules("winrt") + collect_submodules(
    "pyqtgraph", filter=lambda name: not name.startswith(("pyqtgraph.examples", "pyqtgraph.opengl"))) + \
    collect_submodules("reportlab.pdfbase") + collect_submodules("reportlab.graphics.charts")

a = Analysis(
    ["run.py"],
    pathex=["../src"],
    hiddenimports=hidden,
    datas=collect_data_files("reportlab"),  # fuentes de los reportes PDF
    excludes=["tkinter", "matplotlib", "PySide6.QtWebEngineCore", "PySide6.Qt3DCore"],
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="ExtrusionMonitor",
    console=False,
)
# Segundo ejecutable en la misma carpeta (comparte bibliotecas): abre el dashboard global de líneas.
fleet = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="DashboardGlobal",
    console=False,
)
coll = COLLECT(exe, fleet, a.binaries, a.datas, name="ExtrusionMonitor")
