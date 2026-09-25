@echo off
REM Construye dist\ExtrusionMonitor\ExtrusionMonitor.exe en una PC Windows con Python 3.11+
python -m venv .venv || goto :error
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -e .[dev] || goto :error
pyinstaller --noconfirm --distpath dist --workpath build packaging\extrusion_monitor.spec || goto :error
mkdir dist\ExtrusionMonitor\data 2>nul
echo.
echo Listo: dist\ExtrusionMonitor\ExtrusionMonitor.exe
exit /b 0
:error
echo Error en la construccion
exit /b 1
