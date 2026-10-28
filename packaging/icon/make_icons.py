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

BG, HALO, GREEN = "#061c2f", "#03202f", "#36e86e"

# Medidas tomadas del diseño original (lienzo de 256): anillo centrado, punto verde con halo arriba a la
# derecha (encima del anillo) y la tendencia: tramos a 45° con dos «jorobas», que empieza en el borde interior
# del anillo y termina debajo del halo.
CX, CY, R_OUT, R_IN = 126.8, 128.4, 107.0, 78.5
DOT = (194.4, 64.0)
TREND = ("M44 186 L81.5 148 C84 145.4 86.4 143.2 89 143.3 C93.4 143.5 96 148.7 100.2 148.7 "
         "C102.6 148.7 104.6 147.6 106.2 146 L124.8 126.4 C127 124.1 129.2 122.3 131.6 122.4 "
         "C136.2 122.6 139.2 125.8 143.4 125.7 C146 125.6 148 124.6 149.6 123.4 L190 82")

DEFS = """<defs>
  <linearGradient id="ring" x1="0.12" y1="0.08" x2="0.88" y2="0.92">
    <stop offset="0" stop-color="#4fcff0"/><stop offset="0.5" stop-color="#2f97dc"/>
    <stop offset="0.8" stop-color="#1663c8"/><stop offset="1" stop-color="#145dc4"/></linearGradient>
  <linearGradient id="line" x1="0" y1="1" x2="0.55" y2="0">
    <stop offset="0" stop-color="#32cdb2"/><stop offset="1" stop-color="#3ef2f6"/></linearGradient>
</defs>"""


def svg(kind: str = "monitor", small: bool = False) -> str:
    width = R_OUT - R_IN + (4 if small else 0)  # en tamaños chicos el anillo y la línea engrosan un poco
    mid = (R_OUT + R_IN) / 2
    parts = ['<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 256 256" width="256" height="256">', DEFS,
             f'<rect width="256" height="256" rx="34" fill="{BG}"/>']
    ring = f'<circle cx="{CX}" cy="{CY}" r="{mid}" fill="none" stroke="url(#ring)" stroke-width="{width}"/>'
    if kind == "monitor":
        # la tendencia va debajo del anillo: el anillo corta su inicio justo en el borde interior y el halo
        # tapa su final (QtSvg no aplica clipPath)
        parts.append(f'<path d="{TREND}" fill="none" stroke="url(#line)" stroke-width="{24 if small else 20.5}" '
                     'stroke-linecap="butt" stroke-linejoin="round"/>')
    parts.append(ring)
    if kind != "monitor":  # dashboard global: tablero de líneas dentro del anillo (pareja del monitor)
        g, gap = (36, 8) if small else (32, 8)
        x0, y0 = CX - g - gap / 2, CY - g - gap / 2 + 4
        for i, (dx, dy) in enumerate(((0, 0), (1, 0), (0, 1), (1, 1))):
            fill = "url(#line)" if i < 3 else "#f0b429"
            parts.append(f'<rect x="{x0 + dx * (g + gap)}" y="{y0 + dy * (g + gap)}" width="{g}" height="{g}" '
                         f'rx="7" fill="{fill}"/>')
    parts.append(f'<circle cx="{DOT[0]}" cy="{DOT[1]}" r="{38 if small else 36.8}" fill="{HALO}"/>')
    parts.append(f'<circle cx="{DOT[0]}" cy="{DOT[1]}" r="{26 if small else 23.7}" fill="{GREEN}"/>')
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
