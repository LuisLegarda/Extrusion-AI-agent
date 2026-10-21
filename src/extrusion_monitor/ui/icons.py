"""Íconos de línea (trazo de 2 px, 24×24) para la barra lateral, la barra superior y las tarjetas de estado.

Se dibujan desde SVG con el color del tema, así se ven igual en Windows sin depender de las fuentes de emoji.
"""
from __future__ import annotations

from functools import lru_cache

from PySide6.QtCore import QByteArray, QRectF, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap

PATHS = {
    "home": '<path d="M3 10.5 12 3l9 7.5"/><path d="M5 9.5V21h14V9.5"/><path d="M10 21v-6h4v6"/>',
    "variables": '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M7 9h4M7 13h6M7 17h3"/>'
                 '<path d="M15 9h2M15 13h2M15 17h2"/>',
    "trends": '<path d="M3 3v18h18"/><path d="m7 15 4-4 3 3 5-6"/>',
    "kpi": '<path d="M4 20a8 8 0 1 1 16 0"/><path d="m12 20 4-6"/><path d="M12 8v1M6.5 11l.7.7M17.5 11l-.7.7"/>',
    "problems": '<path d="M10.3 3.9 2.4 18a2 2 0 0 0 1.7 3h15.8a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0Z"/>'
                '<path d="M12 9v4M12 17h.01"/>',
    "control": '<path d="M4 6h10M18 6h2M4 12h4M12 12h8M4 18h12M20 18h0"/>'
               '<circle cx="16" cy="6" r="2"/><circle cx="10" cy="12" r="2"/><circle cx="18" cy="18" r="2"/>',
    "spc": '<path d="M3 20h18"/><rect x="5" y="11" width="3" height="9"/><rect x="10.5" y="5" width="3" height="15"/>'
           '<rect x="16" y="8" width="3" height="12"/>',
    "corr": '<circle cx="6" cy="17" r="1.5"/><circle cx="10" cy="13" r="1.5"/><circle cx="13" cy="14" r="1.5"/>'
            '<circle cx="17" cy="8" r="1.5"/><path d="M3 21 21 4" stroke-dasharray="2 3"/>',
    "behavior": '<path d="M3 12h4l2-6 4 12 2-6h6"/>',
    "events": '<path d="M6 8a6 6 0 1 1 12 0c0 7 3 9 3 9H3s3-2 3-9"/><path d="M10.3 21a1.9 1.9 0 0 0 3.4 0"/>',
    "recipes": '<rect x="5" y="3" width="14" height="18" rx="2"/><path d="M9 3v2h6V3"/><path d="M9 11h6M9 15h4"/>',
    "reports": '<path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9Z"/><path d="M14 3v6h6"/>'
               '<path d="M8 13h8M8 17h5"/>',
    "setup": '<circle cx="12" cy="12" r="3"/><path d="M12 2v3M12 19v3M4.9 4.9 7 7M17 17l2.1 2.1M2 12h3M19 12h3'
             'M4.9 19.1 7 17M17 7l2.1-2.1"/>',
    "analysis": '<path d="M3 20h18"/><path d="M4 18c3 0 4-12 8-12s5 12 8 12"/><path d="M12 6v12" '
                'stroke-dasharray="2 2"/>',
    "search": '<circle cx="11" cy="11" r="7"/><path d="m21 21-4.3-4.3"/>',
    "user": '<circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/>',
    "shield": '<path d="M12 3 4 6v6c0 5 3.5 8 8 9 4.5-1 8-4 8-9V6Z"/><path d="m9 12 2 2 4-4"/>',
    "clock": '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
    "play": '<circle cx="12" cy="12" r="9"/><path d="m10 8.5 5.5 3.5-5.5 3.5Z"/>',
    "pause": '<circle cx="12" cy="12" r="9"/><path d="M10 9v6M14 9v6"/>',
    "alert": '<path d="M10.3 3.9 2.4 18a2 2 0 0 0 1.7 3h15.8a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0Z"/>'
             '<path d="M12 9v4M12 17h.01"/>',
    "check": '<circle cx="12" cy="12" r="9"/><path d="m8 12 3 3 5-6"/>',
    "oee": '<circle cx="12" cy="12" r="9"/><path d="M12 3a9 9 0 0 1 9 9h-9Z"/>',
    "stop": '<circle cx="12" cy="12" r="9"/><rect x="9" y="9" width="6" height="6"/>',
    "page": '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M3 9h18"/>',
    "action": '<path d="M13 3 4 14h7l-1 7 9-11h-7Z"/>',
}


def svg(name: str, color: str) -> bytes:
    body = PATHS.get(name, PATHS["page"])
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{color}" '
            f'stroke-width="2" stroke-linecap="round" stroke-linejoin="round">{body}</svg>').encode()


@lru_cache(maxsize=256)
def pixmap(name: str, color: str, size: int = 18) -> QPixmap:
    from PySide6.QtSvg import QSvgRenderer
    scale = 2  # nítido en pantallas de alta densidad
    pm = QPixmap(size * scale, size * scale)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    QSvgRenderer(QByteArray(svg(name, color))).render(p, QRectF(0, 0, size * scale, size * scale))
    p.end()
    pm.setDevicePixelRatio(scale)
    return pm


def icon(name: str, color: str, selected_color: str = "", size: int = 18) -> QIcon:
    """Ícono con su color normal y (opcional) el de la fila seleccionada."""
    ic = QIcon(pixmap(name, color, size))
    if selected_color:
        ic.addPixmap(pixmap(name, selected_color, size), QIcon.Selected)
        ic.addPixmap(pixmap(name, selected_color, size), QIcon.Active, QIcon.On)
    return ic
