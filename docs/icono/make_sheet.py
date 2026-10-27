"""Genera la hoja de propuestas de icono (propuestas.svg y propuestas.png). Solo referencia de diseño."""
from pathlib import Path

NAVY, NAVY2, BLUE, GREEN, AMBER, RED, LIGHT = "#1f4e79", "#163a5c", "#2a78d6", "#0ca30c", "#fab219", "#d03b3b", "#eef1f5"

# Cada icono en una caja de 128×128 (fondo redondeado incluido)
ICONS = {
    "A · Dado y perfil extruido": f"""
      <rect x="4" y="4" width="120" height="120" rx="26" fill="{NAVY}"/>
      <circle cx="40" cy="64" r="24" fill="none" stroke="#fff" stroke-width="8"/>
      <circle cx="40" cy="64" r="8" fill="#fff"/>
      <rect x="58" y="58" width="56" height="12" rx="6" fill="{LIGHT}"/>
      <polyline points="62,40 74,32 86,38 98,26 110,30" fill="none" stroke="{GREEN}" stroke-width="7"
        stroke-linecap="round" stroke-linejoin="round"/>""",
    "B · Manómetro con verificación": f"""
      <rect x="4" y="4" width="120" height="120" rx="26" fill="#ffffff" stroke="{NAVY}" stroke-width="6"/>
      <path d="M26 82 A40 40 0 0 1 102 82" fill="none" stroke="{LIGHT}" stroke-width="14" stroke-linecap="round"/>
      <path d="M26 82 A40 40 0 0 1 82 46" fill="none" stroke="{GREEN}" stroke-width="14" stroke-linecap="round"/>
      <line x1="64" y1="82" x2="86" y2="52" stroke="{NAVY}" stroke-width="8" stroke-linecap="round"/>
      <circle cx="64" cy="82" r="9" fill="{NAVY}"/>
      <polyline points="44,104 58,114 86,96" fill="none" stroke="{GREEN}" stroke-width="8" stroke-linecap="round"
        stroke-linejoin="round"/>""",
    "C · Corte de cable con pulso": f"""
      <rect x="4" y="4" width="120" height="120" rx="26" fill="{NAVY}"/>
      <circle cx="64" cy="64" r="42" fill="{BLUE}"/>
      <circle cx="64" cy="64" r="28" fill="{LIGHT}"/>
      <circle cx="64" cy="64" r="14" fill="{AMBER}"/>
      <polyline points="14,64 40,64 48,48 58,82 66,56 72,64 114,64" fill="none" stroke="#fff" stroke-width="6"
        stroke-linecap="round" stroke-linejoin="round"/>""",
    "D · Pantalla del HMI vigilada": f"""
      <rect x="4" y="4" width="120" height="120" rx="26" fill="{LIGHT}"/>
      <rect x="16" y="24" width="96" height="66" rx="8" fill="{NAVY}"/>
      <rect x="54" y="92" width="20" height="10" fill="{NAVY}"/>
      <rect x="40" y="102" width="48" height="8" rx="4" fill="{NAVY}"/>
      <polyline points="26,74 44,60 58,66 74,44 90,52 102,36" fill="none" stroke="{GREEN}" stroke-width="7"
        stroke-linecap="round" stroke-linejoin="round"/>
      <circle cx="102" cy="36" r="7" fill="{AMBER}"/>""",
    "E · Monograma «E» extruida": f"""
      <rect x="4" y="4" width="120" height="120" rx="26" fill="{NAVY}"/>
      <path d="M36 30 h52 v14 h-36 v13 h30 v14 h-30 v13 h36 v14 h-52 z" fill="#fff"/>
      <rect x="92" y="30" width="18" height="14" rx="3" fill="{GREEN}"/>
      <rect x="86" y="57" width="24" height="14" rx="3" fill="{AMBER}"/>
      <rect x="92" y="84" width="18" height="14" rx="3" fill="{BLUE}"/>""",
    "F · Dashboard global (pareja)": f"""
      <rect x="4" y="4" width="120" height="120" rx="26" fill="{NAVY}"/>
      <rect x="20" y="20" width="40" height="40" rx="8" fill="{GREEN}"/>
      <rect x="68" y="20" width="40" height="40" rx="8" fill="{GREEN}"/>
      <rect x="20" y="68" width="40" height="40" rx="8" fill="{AMBER}"/>
      <rect x="68" y="68" width="40" height="40" rx="8" fill="{RED}"/>
      <polyline points="26,48 36,38 44,44 54,30" fill="none" stroke="#fff" stroke-width="5" stroke-linecap="round"
        stroke-linejoin="round"/>""",
}

CELL_W, CELL_H, COLS = 300, 250, 3
rows = (len(ICONS) + COLS - 1) // COLS
W, H = CELL_W * COLS + 40, CELL_H * rows + 110
parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" '
         f'font-family="Segoe UI, Helvetica, Arial, sans-serif">',
         f'<rect width="{W}" height="{H}" fill="#f4f6f9"/>',
         f'<text x="20" y="44" font-size="24" font-weight="700" fill="#1f3b57">Monitor de extrusión · propuestas de icono</text>',
         f'<text x="20" y="72" font-size="14" fill="#52514e">Cada propuesta a 128, 32 y 16 px (como se ve en la barra '
         f'de tareas). Colores del tema del programa.</text>']
for i, (name, body) in enumerate(ICONS.items()):
    cx, cy = 20 + (i % COLS) * CELL_W, 100 + (i // COLS) * CELL_H
    parts.append(f'<rect x="{cx}" y="{cy}" width="{CELL_W - 20}" height="{CELL_H - 20}" rx="12" fill="#fff" '
                 f'stroke="#d5dbe3"/>')
    parts.append(f'<g transform="translate({cx + 20},{cy + 20})">{body}</g>')
    parts.append(f'<g transform="translate({cx + 170},{cy + 50}) scale(0.25)">{body}</g>')
    parts.append(f'<g transform="translate({cx + 222},{cy + 58}) scale(0.125)">{body}</g>')
    parts.append(f'<text x="{cx + 20}" y="{cy + 180}" font-size="15" font-weight="600" fill="#1b2430">{name}</text>')
parts.append("</svg>")
out = Path(__file__).with_name("propuestas.svg")
out.write_text("\n".join(parts), encoding="utf-8")

if __name__ == "__main__":
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QGuiApplication, QImage, QPainter
    from PySide6.QtSvg import QSvgRenderer
    app = QGuiApplication([])
    r = QSvgRenderer(str(out))
    img = QImage(W * 2, H * 2, QImage.Format_ARGB32)
    img.fill(Qt.white)
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing)
    r.render(p)
    p.end()
    img.save(str(out.with_suffix(".png")))
    print(out.with_suffix(".png"))
