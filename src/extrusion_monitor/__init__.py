"""Monitor de parámetros, recetas y tendencias para líneas de extrusión (Fase 1)."""

# Única fuente del número de versión (pyproject.toml lo lee de aquí). Ver CHANGELOG.md y docs/DESARROLLO.md.
__version__ = "0.2.0"

try:  # lo genera GitHub Actions al construir el .exe: canal (estable / prueba / rama), commit y fecha
    from ._build import BUILD
except ImportError:  # pragma: no cover - ejecución desde el código fuente
    BUILD = {}


def version_label() -> str:
    """«0.2.0», «0.2.0 · prueba (develop a1b2c3d, 2026-10-03)» o «0.2.0 · código fuente»."""
    if not BUILD:
        return f"{__version__} · código fuente"
    if BUILD.get("channel") == "estable":
        return __version__
    return f"{__version__} · {BUILD.get('channel', '')} ({BUILD.get('ref', '')} {BUILD.get('commit', '')}, " \
           f"{BUILD.get('date', '')})"
