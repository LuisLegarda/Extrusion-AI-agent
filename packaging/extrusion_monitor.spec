# PyInstaller: pyinstaller packaging/extrusion_monitor.spec
from PyInstaller.utils.hooks import collect_submodules

hidden = collect_submodules("winrt") + collect_submodules(
    "pyqtgraph", filter=lambda name: not name.startswith(("pyqtgraph.examples", "pyqtgraph.opengl")))

a = Analysis(
    ["run.py"],
    pathex=["../src"],
    hiddenimports=hidden,
    excludes=["tkinter", "matplotlib", "PySide6.QtWebEngineCore", "PySide6.Qt3DCore"],
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="ExtrusionMonitor",
    console=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name="ExtrusionMonitor")
