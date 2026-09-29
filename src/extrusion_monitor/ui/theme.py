"""Tema claro / oscuro de la interfaz y de las gráficas.

Los colores de las series, estados y ejes siguen una paleta validada para daltonismo y
contraste en ambos modos (el modo oscuro usa sus propios tonos, no una inversión).
"""
from __future__ import annotations

from dataclasses import dataclass

LIGHT = {
    "dark": False,
    # superficies y texto
    "page": "#f4f6f9", "surface": "#ffffff", "surface2": "#eef1f5", "border": "#d5dbe3",
    "text": "#1b2430", "text2": "#52514e", "muted": "#7d7b76", "title": "#1f3b57",
    "accent": "#1f4e79", "accent_hover": "#2a6299", "accent_text": "#ffffff", "selection": "#cfe0f5",
    "sidebar": "#e8f0fa", "sidebar_hover": "#d3e2f4", "sidebar_border": "#c7d3e3",
    "menubar": "#2f343b", "menubar_text": "#ffffff", "menubar_hover": "#44505e",
    "track": "#e6e9ee", "input": "#ffffff",
    # gráficas
    "plot_bg": "#fcfcfb", "plot_fg": "#52514e", "grid": "#e1e0d9", "axis": "#c3c2b7",
    "series": ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#4a3aa7", "#e34948"],
    "measure": "#2a78d6", "setpoint": "#4a3aa7", "projection": "#eb6834", "reference": "#898781",
    # estados (fijos)
    "good": "#0ca30c", "good_soft": "#8fd18f", "warning": "#fab219", "serious": "#ec835a", "critical": "#d03b3b",
    "info": "#2a78d6", "neutral": "#898781", "good_text": "#006300", "warning_text": "#8a5a00",
    "hist": "#86b6ef",
}

DARK = {
    "dark": True,
    "page": "#0f1114", "surface": "#1a1a19", "surface2": "#24272c", "border": "#34383f",
    "text": "#f2f3f5", "text2": "#c3c2b7", "muted": "#9a988f", "title": "#9ec5f4",
    "accent": "#3987e5", "accent_hover": "#5598e7", "accent_text": "#ffffff", "selection": "#1c5cab",
    "sidebar": "#15181c", "sidebar_hover": "#242a33", "sidebar_border": "#2a2f36",
    "menubar": "#0b0c0e", "menubar_text": "#f2f3f5", "menubar_hover": "#2a2f36",
    "track": "#2c3139", "input": "#202328",
    "plot_bg": "#1a1a19", "plot_fg": "#c3c2b7", "grid": "#2c2c2a", "axis": "#383835",
    "series": ["#3987e5", "#d95926", "#199e70", "#c98500", "#d55181", "#008300", "#9085e9", "#e66767"],
    "measure": "#3987e5", "setpoint": "#9085e9", "projection": "#d95926", "reference": "#898781",
    "good": "#0ca30c", "good_soft": "#2f6b2f", "warning": "#fab219", "serious": "#ec835a", "critical": "#d03b3b",
    "info": "#3987e5", "neutral": "#898781", "good_text": "#0ca30c", "warning_text": "#fab219",
    "hist": "#1c5cab",
}

THEMES = {"light": LIGHT, "dark": DARK}
_current = "light"


def set_theme(name: str) -> None:
    global _current
    _current = name if name in THEMES else "light"


def name() -> str:
    return _current


def c(key: str) -> str:
    """Color del tema activo."""
    return THEMES[_current][key]


def is_dark() -> bool:
    return THEMES[_current]["dark"]


def series(i: int) -> str:
    s = THEMES[_current]["series"]
    return s[i % len(s)]


def qcolor(key: str):
    from PySide6.QtGui import QColor
    return QColor(c(key))


def stylesheet() -> str:
    t = THEMES[_current]
    return f"""
QWidget {{ font-size: 13px; color: {t['text']}; }}
QMainWindow, QDialog, QWidget#content {{ background: {t['page']}; }}
QMenuBar {{ background: {t['menubar']}; color: {t['menubar_text']}; padding: 2px 6px; font-size: 14px;
           font-weight: bold; }}
QMenuBar::item {{ background: transparent; padding: 6px 12px; color: {t['menubar_text']}; }}
QMenuBar::item:selected {{ background: {t['menubar_hover']}; border-radius: 4px; }}
QMenu {{ background: {t['surface']}; border: 1px solid {t['border']}; }}
QMenu::item {{ padding: 6px 24px 6px 18px; }}
QMenu::item:selected {{ background: {t['accent']}; color: {t['accent_text']}; }}
QMenu::separator {{ height: 1px; background: {t['border']}; margin: 4px 8px; }}
QWidget#sidebar {{ background: {t['sidebar']}; border-right: 1px solid {t['sidebar_border']}; }}
QListWidget#nav {{ background: transparent; border: none; font-size: 14px; outline: 0; }}
QListWidget#nav::item {{ padding: 8px 10px; border-radius: 6px; margin: 1px 0; color: {t['title']}; }}
QListWidget#nav::item:hover {{ background: {t['sidebar_hover']}; }}
QListWidget#nav::item:selected {{ background: {t['accent']}; color: {t['accent_text']}; font-weight: bold; }}
QToolButton#run {{ background: {t['accent']}; color: {t['accent_text']}; font-weight: bold; padding: 7px 16px;
                  border-radius: 6px; }}
QToolButton#run:hover {{ background: {t['accent_hover']}; }}
QFrame#card {{ background: {t['surface']}; border: 1px solid {t['border']}; border-radius: 8px; }}
QFrame#card QLabel {{ border: none; background: transparent; }}
QTabWidget::pane {{ border: 1px solid {t['border']}; background: {t['surface']}; border-radius: 4px; }}
QTabBar::tab {{ padding: 6px 14px; background: {t['surface2']}; border: 1px solid {t['border']};
               border-bottom: none; border-top-left-radius: 4px; border-top-right-radius: 4px; margin-right: 2px; }}
QTabBar::tab:selected {{ background: {t['surface']}; font-weight: bold; color: {t['accent']}; }}
QTableWidget, QTreeWidget, QListWidget {{ background: {t['surface']}; alternate-background-color: {t['surface2']};
                                          border: 1px solid {t['border']}; }}
QTableWidget {{ gridline-color: {t['grid']}; }}
QHeaderView::section {{ padding: 4px; font-weight: bold; background: {t['surface2']}; border: none;
                       border-bottom: 1px solid {t['border']}; color: {t['title']}; }}
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QDateTimeEdit, QPlainTextEdit, QTextEdit {{
    background: {t['input']}; border: 1px solid {t['border']}; border-radius: 4px; padding: 3px 5px; }}
QComboBox QAbstractItemView {{ background: {t['surface']}; selection-background-color: {t['accent']};
                               selection-color: {t['accent_text']}; }}
QPushButton, QToolButton {{ padding: 5px 12px; background: {t['surface2']}; border: 1px solid {t['border']};
                           border-radius: 4px; }}
QPushButton:hover, QToolButton:hover {{ border-color: {t['accent']}; }}
QPushButton:pressed {{ background: {t['selection']}; }}
QGroupBox {{ border: 1px solid {t['border']}; border-radius: 6px; margin-top: 10px; padding-top: 6px; }}
QGroupBox::title {{ subcontrol-origin: margin; left: 8px; padding: 0 4px; color: {t['title']}; font-weight: bold; }}
QLabel#banner {{ font-size: 18px; font-weight: bold; padding: 6px 14px; border-radius: 6px; color: #ffffff; }}
QStatusBar {{ background: {t['surface2']}; color: {t['text2']}; }}
QScrollArea {{ border: none; }}
QToolTip {{ background: {t['surface']}; color: {t['text']}; border: 1px solid {t['border']}; }}
"""


def palette():
    """Paleta de Qt (Fusion) coherente con el tema: diálogos y controles nativos."""
    from PySide6.QtGui import QColor, QPalette
    t = THEMES[_current]
    p = QPalette()
    roles = {
        QPalette.Window: t["page"], QPalette.WindowText: t["text"], QPalette.Base: t["surface"],
        QPalette.AlternateBase: t["surface2"], QPalette.ToolTipBase: t["surface"], QPalette.ToolTipText: t["text"],
        QPalette.Text: t["text"], QPalette.Button: t["surface2"], QPalette.ButtonText: t["text"],
        QPalette.BrightText: "#ffffff", QPalette.Highlight: t["accent"], QPalette.HighlightedText: t["accent_text"],
        QPalette.Link: t["accent"], QPalette.PlaceholderText: t["muted"], QPalette.Mid: t["border"],
        QPalette.Dark: t["border"], QPalette.Light: t["surface"], QPalette.Midlight: t["surface2"],
    }
    for role, col in roles.items():
        p.setColor(role, QColor(col))
    for role in (QPalette.WindowText, QPalette.Text, QPalette.ButtonText):
        p.setColor(QPalette.Disabled, role, QColor(t["muted"]))
    return p


def apply(app) -> None:
    """Aplica el tema a la aplicación y a las gráficas que se creen desde ahora."""
    import pyqtgraph as pg
    app.setStyle("Fusion")
    app.setPalette(palette())
    app.setStyleSheet(stylesheet())
    pg.setConfigOptions(antialias=True, background=c("plot_bg"), foreground=c("plot_fg"))


@dataclass
class Pens:
    """Plumas de uso frecuente en las gráficas."""

    @staticmethod
    def get(key: str, width: float = 2, dash: bool = False, dot: bool = False):
        import pyqtgraph as pg
        from PySide6.QtCore import Qt
        style = Qt.DashLine if dash else (Qt.DotLine if dot else Qt.SolidLine)
        return pg.mkPen(c(key), width=width, style=style)
