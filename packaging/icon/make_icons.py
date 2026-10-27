"""Iconos del programa a partir del diseño (anillo con tendencia y punto verde).

Genera en src/extrusion_monitor/resources/: monitor.svg/.png/.ico y dashboard.svg/.png/.ico.
El .ico lleva los tamaños estándar de Windows; de 16 a 32 px se usa un dibujo simplificado (trazos más
gruesos, menos ondas) para que se lea en la barra de tareas.

Uso:  python packaging/icon/make_icons.py
"""
from __future__ import annotations

import io
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "src" / "extrusion_monitor" / "resources"
ICO_SIZES = [16, 20, 24, 32, 40, 48, 64, 96, 128, 256]
SMALL = 32  # hasta este tamaño: dibujo simplificado

BG, HALO, GREEN = "#071c2e", "#0c2a3a", "#34e36f"

DEFS = """<defs>
  <linearGradient id="ring" x1="0.15" y1="0.1" x2="0.85" y2="0.9">
    <stop offset="0" stop-color="#53c9f2"/><stop offset="0.55" stop-color="#2f8fdc"/>
    <stop offset="1" stop-color="#1857c4"/></linearGradient>
  <linearGradient id="line" x1="0" y1="1" x2="1" y2="0">
    <stop offset="0" stop-color="#27d3b4"/><stop offset="1" stop-color="#43f1ef"/></linearGradient>
</defs>"""


def svg(kind: str = "monitor", small: bool = False) -> str:
    ring_w = 34 if small else 30
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 256 256" width="256" height="256">', DEFS,
             f'<rect width="256" height="256" rx="46" fill="{BG}"/>',
             f'<circle cx="128" cy="140" r="{92 if small else 90}" fill="none" stroke="url(#ring)" '
             f'stroke-width="{ring_w}"/>']
    if kind == "monitor":
        if small:  # una sola onda, trazo grueso
            d = "M70 176 C90 150 102 138 116 142 C130 146 138 124 156 112 L188 80"
            w = 26
        else:
            d = ("M66 178 C78 162 88 146 100 142 C112 138 114 154 127 150 C140 146 146 126 158 122 "
                 "C170 118 172 130 182 122 L196 84")
            w = 22
        parts.append(f'<path d="{d}" fill="none" stroke="url(#line)" stroke-width="{w}" '
                     'stroke-linecap="butt" stroke-linejoin="round"/>')
    else:  # dashboard global: tablero de líneas dentro del anillo (pareja del monitor)
        g = 34 if small else 30
        for i, (x, y) in enumerate(((88, 100), (88 + g + 8, 100), (88, 100 + g + 8), (88 + g + 8, 100 + g + 8))):
            fill = "url(#line)" if i < 3 else "#f0b429"
            parts.append(f'<rect x="{x}" y="{y}" width="{g}" height="{g}" rx="8" fill="{fill}"/>')
    parts.append(f'<circle cx="200" cy="64" r="{40 if small else 38}" fill="{HALO}"/>')
    parts.append(f'<circle cx="200" cy="64" r="{28 if small else 25}" fill="{GREEN}"/>')
    parts.append("</svg>")
    return "\n".join(parts)


def render(text: str, size: int):
    from PIL import Image
    from PySide6.QtCore import QByteArray, Qt
    from PySide6.QtGui import QImage, QPainter
    from PySide6.QtSvg import QSvgRenderer
    r = QSvgRenderer(QByteArray(text.encode("utf-8")))
    img = QImage(size, size, QImage.Format_ARGB32)
    img.fill(Qt.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing)
    r.render(p)
    p.end()
    buf = QByteArray()
    from PySide6.QtCore import QBuffer, QIODevice
    b = QBuffer(buf)
    b.open(QIODevice.WriteOnly)
    img.save(b, "PNG")
    return Image.open(io.BytesIO(bytes(buf))).convert("RGBA")


def main() -> None:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtGui import QGuiApplication
    QGuiApplication.instance() or QGuiApplication(sys.argv[:1])
    OUT.mkdir(parents=True, exist_ok=True)
    for kind in ("monitor", "dashboard"):
        big, small = svg(kind), svg(kind, small=True)
        (OUT / f"{kind}.svg").write_text(big, encoding="utf-8")
        render(big, 512).save(OUT / f"{kind}.png")
        imgs = [render(small if s <= SMALL else big, s) for s in ICO_SIZES]
        imgs[-1].save(OUT / f"{kind}.ico", format="ICO", sizes=[(s, s) for s in ICO_SIZES],
                      append_images=imgs[:-1])
        print(OUT / f"{kind}.ico")


if __name__ == "__main__":
    main()
