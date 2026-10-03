import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pytest


@pytest.fixture(autouse=True)
def _backups_in_tmp(tmp_path_factory, monkeypatch):
    """Los respaldos automáticos de las pruebas no van a la carpeta real del usuario."""
    monkeypatch.setenv("EXTRUMON_BACKUPS", str(tmp_path_factory.mktemp("respaldos")))
