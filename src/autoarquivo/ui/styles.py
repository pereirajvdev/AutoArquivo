"""Folha de estilos (QSS) e paleta corporativa sóbria."""

from __future__ import annotations

from string import Template

PALETTE = {
    "bg": "#F1F5F9",
    "surface": "#FFFFFF",
    "border": "#E2E8F0",
    "border_strong": "#CBD5E1",
    "text": "#0F172A",
    "muted": "#64748B",
    "primary": "#1D4ED8",
    "primary_hover": "#1E40AF",
    "primary_soft": "#DBEAFE",
    "danger": "#B91C1C",
    "danger_soft": "#FEF2F2",
    "danger_border": "#FCA5A5",
    "success": "#15803D",
    "sidebar": "#0F1E3D",
    "sidebar_hover": "#182B52",
    "sidebar_active": "#1F3A6E",
    "sidebar_text": "#B6C2D9",
    "row_alt": "#F8FAFC",
}

_QSS = Template("""
QWidget { color: $text; font-size: 13px; }
QMainWindow, QDialog, QWidget#root, QWidget#page, QWidget#pageBody { background: $bg; }
QLabel { background: transparent; }
QToolTip { background: $text; color: #FFFFFF; border: none; padding: 5px 8px; }

/* ---------- estrutura ---------- */
QFrame#card { background: $surface; border: 1px solid $border; border-radius: 10px; }
QFrame#topbar { background: $surface; border: none; border-bottom: 1px solid $border; }
QFrame#sidebar { background: $sidebar; border: none; }
QSplitter::handle { background: transparent; }
QScrollArea { border: none; background: transparent; }
QStatusBar { background: $surface; color: $muted; border-top: 1px solid $border; }

/* ---------- textos ---------- */
QLabel#brand { color: #FFFFFF; font-size: 18px; font-weight: 700; }
QLabel#brandSub { color: $sidebar_text; font-size: 11px; }
QLabel#version { color: $sidebar_text; font-size: 11px; }
QLabel#pageTitle { font-size: 22px; font-weight: 700; }
QLabel#cardTitle { font-size: 14px; font-weight: 600; }
QLabel#muted { color: $muted; }
QLabel#sectionLabel { color: $muted; font-size: 11px; font-weight: 700; }
QLabel#iconBadge { background: $primary_soft; border-radius: 10px; }
QLabel#feedback[kind="error"] { color: $danger; }
QLabel#feedback[kind="ok"] { color: $success; }
QLabel#chip { border-radius: 10px; padding: 3px 12px; font-weight: 600; background: $border; color: $muted; }
QLabel#chip[state="running"] { background: $primary_soft; color: $primary; }
QLabel#chip[state="success"] { background: #DCFCE7; color: $success; }
QLabel#chip[state="error"] { background: #FEE2E2; color: $danger; }
QLabel#chip[state="cancelled"] { background: #FEF3C7; color: #92400E; }

/* ---------- navegação ---------- */
QPushButton#nav {
    background: transparent; color: $sidebar_text; border: none; border-left: 3px solid transparent;
    border-radius: 0; text-align: left; padding: 13px 18px; font-size: 14px; font-weight: 500;
}
QPushButton#nav:hover { background: $sidebar_hover; color: #FFFFFF; }
QPushButton#nav:checked { background: $sidebar_active; color: #FFFFFF; border-left: 3px solid #60A5FA; }
QPushButton#navFooter {
    background: transparent; color: $sidebar_text; border: none; text-align: left;
    padding: 12px 18px; font-size: 13px;
}
QPushButton#navFooter:hover { background: $sidebar_hover; color: #FFFFFF; }

/* ---------- campos ---------- */
QLineEdit {
    background: $surface; border: 1px solid $border_strong; border-radius: 6px;
    padding: 7px 10px; selection-background-color: $primary_soft; selection-color: $text;
}
QLineEdit:focus { border: 1px solid $primary; }
QLineEdit:read-only { background: $row_alt; }
QLineEdit[invalid="true"] { border: 1px solid $danger; background: $danger_soft; }
QLineEdit:disabled { background: $bg; color: $muted; }

/* ---------- botões ---------- */
QPushButton {
    background: $surface; color: $text; border: 1px solid $border_strong; border-radius: 6px;
    padding: 7px 14px; font-weight: 500;
}
QPushButton:hover { background: $bg; }
QPushButton:pressed { background: $border; }
QPushButton:disabled { color: #94A3B8; background: $row_alt; border-color: $border; }
QPushButton#primary { background: $primary; color: #FFFFFF; border: 1px solid $primary; font-weight: 600; padding: 8px 18px; }
QPushButton#primary:hover { background: $primary_hover; border-color: $primary_hover; }
QPushButton#primary:disabled { background: #94A3B8; border-color: #94A3B8; color: #F1F5F9; }
QPushButton#danger { color: $danger; border: 1px solid $danger_border; }
QPushButton#danger:hover { background: $danger_soft; }
QPushButton#danger:disabled { color: #94A3B8; border-color: $border; background: $row_alt; }
QPushButton#ghost { background: transparent; border: none; color: $muted; padding: 5px 8px; }
QPushButton#ghost:hover { background: $border; color: $text; }
QPushButton#ghost:disabled { color: #CBD5E1; background: transparent; }

/* ---------- tabelas ---------- */
QTableView {
    background: $surface; alternate-background-color: $row_alt; border: 1px solid $border;
    border-radius: 6px; gridline-color: transparent; selection-background-color: $primary_soft;
    selection-color: $text; outline: 0;
}
QTableView::item { padding: 4px 8px; border: none; }
QHeaderView::section {
    background: $bg; color: #475569; border: none; border-bottom: 1px solid $border;
    padding: 7px 8px; font-weight: 600;
}
QTableCornerButton::section { background: $bg; border: none; }

/* ---------- log ---------- */
QPlainTextEdit#log {
    background: #0B1220; color: #E2E8F0; border: 1px solid #1E293B; border-radius: 8px;
    padding: 8px; font-family: Consolas, "Cascadia Mono", "DejaVu Sans Mono", monospace; font-size: 12px;
}
QProgressBar { background: $border; border: none; border-radius: 2px; max-height: 4px; min-height: 4px; }
QProgressBar::chunk { background: $primary; border-radius: 2px; }

/* ---------- barras de rolagem ---------- */
QScrollBar:vertical { background: transparent; width: 10px; margin: 2px; }
QScrollBar::handle:vertical { background: $border_strong; border-radius: 4px; min-height: 30px; }
QScrollBar::handle:vertical:hover { background: #94A3B8; }
QScrollBar:horizontal { background: transparent; height: 10px; margin: 2px; }
QScrollBar::handle:horizontal { background: $border_strong; border-radius: 4px; min-width: 30px; }
QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; }
QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }
""")


def build_stylesheet() -> str:
    return _QSS.substitute(PALETTE)
