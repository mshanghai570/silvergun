"""Reusable retro-industrial visual language for Silvergun Qt surfaces."""

from __future__ import annotations

from PySide6.QtGui import QFont


# Kept as named tokens so future dialogs and panels can share one instrument language.
OLED_BLACK = "#070809"
CHARCOAL = "#101315"
PANEL = "#15191b"
PANEL_RAISED = "#1b2022"
METAL = "#a7afb1"
METAL_DIM = "#667073"
BORDER = "#384144"
RED = "#b52d35"
RED_BRIGHT = "#e04a4e"
RED_DEEP = "#581b20"
AMBER = "#d09a4c"
INK = "#e5e8e8"

CONSOLE_FONT = "DejaVu Sans Mono"
DISPLAY_FONT = "DejaVu Sans"

CONSOLE_STYLESHEET = f"""
QWidget#silvergunConsole, QDialog#silvergunProvider {{
    background-color: {OLED_BLACK};
    color: {INK};
    font-family: '{CONSOLE_FONT}';
    font-size: 11px;
}}
QFrame[role='panel'] {{
    background-color: {CHARCOAL};
    border: 1px solid {BORDER};
}}
QLabel[role='eyebrow'] {{
    color: {METAL_DIM};
    font-family: '{CONSOLE_FONT}';
    font-size: 9px;
    font-weight: bold;
    letter-spacing: 1px;
}}
QLabel[role='display'] {{
    color: {INK};
    font-family: '{DISPLAY_FONT}';
    font-size: 19px;
    font-weight: bold;
}}
QLabel[role='signal'] {{
    color: {RED_BRIGHT};
    font-family: '{CONSOLE_FONT}';
    font-size: 10px;
    font-weight: bold;
}}
QLabel[role='muted'] {{ color: {METAL_DIM}; }}
QLabel[role='value'] {{ color: {INK}; font-family: '{CONSOLE_FONT}'; }}
QLabel[role='status'] {{ color: {AMBER}; font-family: '{CONSOLE_FONT}'; font-size: 10px; }}
QLineEdit, QPlainTextEdit, QComboBox {{
    background-color: {PANEL};
    color: {INK};
    border: 1px solid {BORDER};
    border-radius: 0px;
    padding: 6px;
    selection-background-color: {RED_DEEP};
    selection-color: {INK};
}}
QPlainTextEdit {{ font-family: '{CONSOLE_FONT}'; font-size: 11px; }}
QLineEdit:focus, QPlainTextEdit:focus, QComboBox:focus {{ border: 1px solid {RED}; }}
QPushButton {{
    background-color: {PANEL_RAISED};
    color: {METAL};
    border: 1px solid {BORDER};
    border-radius: 0px;
    padding: 6px 10px;
    min-height: 20px;
    font-family: '{CONSOLE_FONT}';
    font-weight: bold;
}}
QPushButton:hover {{ color: {INK}; border-color: {RED}; background-color: {RED_DEEP}; }}
QPushButton:pressed {{ background-color: {RED}; color: {INK}; }}
QPushButton[role='fire'] {{ color: {INK}; border-color: {RED}; background-color: {RED_DEEP}; }}
QPushButton[role='fire']:hover {{ background-color: {RED}; }}
QToolButton {{ border: 1px solid {BORDER}; border-radius: 0px; color: {METAL}; }}
QScrollBar:vertical {{ background: {OLED_BLACK}; width: 10px; margin: 0; }}
QScrollBar::handle:vertical {{ background: {BORDER}; min-height: 24px; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QDialogButtonBox QPushButton {{ min-width: 80px; }}
QLabel[role='capability'] {{
    background-color: {PANEL};
    border-bottom: 1px solid {BORDER};
    color: {METAL};
    padding: 4px 6px;
    font-family: '{CONSOLE_FONT}';
    font-size: 10px;
}}
QLabel[role='capability'][active='true'] {{ color: {INK}; background-color: {RED_DEEP}; border-left: 2px solid {RED_BRIGHT}; }}
QLabel[role='capability'][available='false'] {{ color: {METAL_DIM}; }}
"""


def console_font(size: int = 11, bold: bool = False) -> QFont:
    """Return the preferred technical font with a safe Qt fallback."""
    font = QFont(CONSOLE_FONT, size)
    font.setBold(bold)
    return font


def mark(widget, role: str, **properties) -> None:
    """Set stylesheet properties and force a repaint after dynamic state changes."""
    widget.setProperty("role", role)
    for name, value in properties.items():
        widget.setProperty(name, value)
    widget.style().unpolish(widget)
    widget.style().polish(widget)
