"""Número de versión, CHANGELOG y respaldos automáticos de la configuración."""
import json
import re
import zipfile
from pathlib import Path

import extrusion_monitor
from extrusion_monitor import __version__, backup

ROOT = Path(__file__).resolve().parents[1]


def test_version_is_semver_and_in_changelog():
    assert re.fullmatch(r"\d+\.\d+\.\d+", __version__)
    text = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    assert f"## [{__version__}]" in text
    assert "## [Sin publicar]" in text


def test_pyproject_reads_version_from_package():
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert 'dynamic = ["version"]' in text and "extrusion_monitor.__version__" in text


def test_version_label(monkeypatch):
    monkeypatch.setattr(extrusion_monitor, "BUILD", {})
    assert extrusion_monitor.version_label().endswith("código fuente")
    monkeypatch.setattr(extrusion_monitor, "BUILD", {"channel": "estable"})
    assert extrusion_monitor.version_label() == __version__
    monkeypatch.setattr(extrusion_monitor, "BUILD", {"channel": "prueba", "ref": "develop", "commit": "abc1234",
                                                     "date": "2026-10-03"})
    assert "prueba" in extrusion_monitor.version_label() and "abc1234" in extrusion_monitor.version_label()


def _home(tmp_path):
    home = tmp_path / "data"
    (home / "recipes").mkdir(parents=True)
    (home / "reports").mkdir()
    (home / "config.json").write_text("{}", encoding="utf-8")
    (home / "recipes" / "A.json").write_text("{}", encoding="utf-8")
    (home / "history.sqlite").write_bytes(b"x" * 100)
    (home / "reports" / "r.pdf").write_bytes(b"pdf")
    return home


def test_auto_backup_on_new_version_and_weekly(tmp_path, monkeypatch):
    monkeypatch.setenv("EXTRUMON_BACKUPS", str(tmp_path / "resp"))
    home = _home(tmp_path)
    first = backup.auto_backup(home, now=1000.0)
    assert first is not None and "inicial" in first.name
    names = zipfile.ZipFile(first).namelist()
    assert "datos/config.json" in names and "datos/recipes/A.json" in names
    assert not any("sqlite" in n or "reports" in n for n in names)
    assert backup.auto_backup(home, now=2000.0) is None  # misma versión, menos de una semana
    week = backup.auto_backup(home, now=1000.0 + 8 * 86400)
    assert week is not None and "semanal" in week.name
    (home / backup.MARKER).write_text(json.dumps({"version": "0.0.1", "backup_ts": 1e12}), encoding="utf-8")
    upd = backup.auto_backup(home, now=1000.0 + 9 * 86400)
    assert upd is not None and "desde-v0.0.1" in upd.name


def test_no_backup_without_configuration(tmp_path, monkeypatch):
    monkeypatch.setenv("EXTRUMON_BACKUPS", str(tmp_path / "resp"))
    home = tmp_path / "vacio"
    home.mkdir()
    assert backup.auto_backup(home) is None


def test_restore_and_prune(tmp_path, monkeypatch):
    monkeypatch.setenv("EXTRUMON_BACKUPS", str(tmp_path / "resp"))
    home = _home(tmp_path)
    z = backup.create_backup(home, "manual")
    (home / "config.json").write_text('{"roto": true}', encoding="utf-8")
    assert backup.restore_backup(z, home) >= 2
    assert (home / "config.json").read_text(encoding="utf-8") == "{}"
    for i in range(5):
        (tmp_path / "resp" / f"respaldo-2000010{i}-000000-v0-x.zip").write_bytes(b"")
    backup.prune(home, keep=3)
    assert len(backup.list_backups(home)) == 3
