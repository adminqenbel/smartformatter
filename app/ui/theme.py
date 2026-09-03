"""
QenBel Smart Formatter — Modern Glass-Dark Theme.
A refined, depth-aware dark UI system with subtle gradients, glass-morphism effects,
smooth hover transitions, and a cohesive visual language for professional print-shop software.
"""


# ── Color Palette ──────────────────────────────────────────────
# Base surfaces (darkest to lightest)
_BG_ROOT       = "#0D0D0D"
_BG_BASE       = "#121212"
_BG_RAISED     = "#1A1A1E"
_BG_SURFACE    = "#202026"
_BG_OVERLAY    = "#27272E"
_BG_ELEVATED   = "#2E2E36"

# Borders
_BORDER_SUBTLE = "#2A2A32"
_BORDER_DEFAULT= "#34343E"
_BORDER_STRONG = "#44444F"
_BORDER_FOCUS  = "#6366F1"

# Text
_TEXT_PRIMARY   = "#F0F0F5"
_TEXT_SECONDARY = "#9A9AAA"
_TEXT_MUTED     = "#66667A"
_TEXT_DISABLED  = "#444455"

# Accent — Indigo-Violet
_ACCENT         = "#6366F1"
_ACCENT_HOVER   = "#818CF8"
_ACCENT_PRESSED = "#4F46E5"
_ACCENT_GLOW    = "rgba(99, 102, 241, 0.15)"

# Success — Emerald
_SUCCESS        = "#10B981"
_SUCCESS_BG     = "#062E20"
_SUCCESS_BORDER = "#10B981"

# Warning — Amber
_WARNING        = "#F59E0B"
_WARNING_BG     = "#2E2206"
_WARNING_BORDER = "#F59E0B"

# Danger — Rose
_DANGER         = "#EF4444"
_DANGER_BG      = "#2E0A0A"
_DANGER_BORDER  = "#EF4444"

# Info / Word export — Sky
_INFO           = "#38BDF8"
_INFO_BG        = "#0C2340"
_INFO_BORDER    = "#38BDF8"


CHATGPT_DARK_STYLESHEET = f"""
/* ═══════════════════════════════════════════════════════════════
   ROOT & GLOBAL RESET
   ═══════════════════════════════════════════════════════════════ */
* {{
    margin: 0;
    padding: 0;
}}

QWidget {{
    background-color: {_BG_ROOT};
    color: {_TEXT_PRIMARY};
    font-family: "Segoe UI Variable", "Segoe UI", "Inter", system-ui, -apple-system, sans-serif;
    font-size: 13px;
    selection-background-color: {_ACCENT};
    selection-color: #FFFFFF;
}}

/* ═══════════════════════════════════════════════════════════════
   WINDOW & CONTAINERS
   ═══════════════════════════════════════════════════════════════ */
QMainWindow, QDialog {{
    background-color: {_BG_ROOT};
}}

QFrame {{
    border: none;
}}

/* ═══════════════════════════════════════════════════════════════
   SCROLLBARS — Minimal pill style
   ═══════════════════════════════════════════════════════════════ */
QScrollBar:vertical {{
    border: none;
    background: transparent;
    width: 10px;
    margin: 4px 2px;
}}

QScrollBar::handle:vertical {{
    background: {_BG_ELEVATED};
    min-height: 32px;
    border-radius: 5px;
    border: 2px solid transparent;
}}

QScrollBar::handle:vertical:hover {{
    background: {_BORDER_STRONG};
    border: 2px solid transparent;
}}

QScrollBar::handle:vertical:pressed {{
    background: {_ACCENT};
}}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0px;
    background: none;
    border: none;
}}

QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
    background: none;
}}

QScrollBar:horizontal {{
    border: none;
    background: transparent;
    height: 10px;
    margin: 2px 4px;
}}

QScrollBar::handle:horizontal {{
    background: {_BG_ELEVATED};
    min-width: 32px;
    border-radius: 5px;
}}

QScrollBar::handle:horizontal:hover {{
    background: {_BORDER_STRONG};
}}

QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0px;
    background: none;
    border: none;
}}

/* ═══════════════════════════════════════════════════════════════
   CARD / PANEL COMPONENTS
   ═══════════════════════════════════════════════════════════════ */
QFrame.panel-card {{
    background-color: {_BG_RAISED};
    border: 1px solid {_BORDER_SUBTLE};
    border-radius: 14px;
}}

QFrame.panel-card-hover:hover {{
    background-color: {_BG_SURFACE};
    border: 1px solid {_BORDER_DEFAULT};
}}

/* ═══════════════════════════════════════════════════════════════
   HEADER BAR
   ═══════════════════════════════════════════════════════════════ */
QFrame.header-bar {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 {_BG_BASE}, stop:0.5 {_BG_RAISED}, stop:1 {_BG_BASE});
    border-bottom: 1px solid {_BORDER_SUBTLE};
}}

/* ═══════════════════════════════════════════════════════════════
   TYPOGRAPHY
   ═══════════════════════════════════════════════════════════════ */
QLabel {{
    color: {_TEXT_PRIMARY};
    background: transparent;
}}

QLabel.title-huge {{
    font-size: 32px;
    font-weight: 800;
    color: #FFFFFF;
    letter-spacing: -0.8px;
}}

QLabel.title-large {{
    font-size: 22px;
    font-weight: 700;
    color: #FFFFFF;
    letter-spacing: -0.4px;
}}

QLabel.title-medium {{
    font-size: 17px;
    font-weight: 600;
    color: {_TEXT_PRIMARY};
    letter-spacing: -0.2px;
}}

QLabel.subtitle {{
    font-size: 13px;
    color: {_TEXT_SECONDARY};
    line-height: 1.5;
}}

QLabel.caption {{
    font-size: 11px;
    color: {_TEXT_MUTED};
    letter-spacing: 0.3px;
    text-transform: uppercase;
}}

/* ── Confidence Badges ── */
QLabel.badge-high {{
    background-color: {_SUCCESS_BG};
    color: {_SUCCESS};
    border: 1px solid rgba(16, 185, 129, 0.3);
    border-radius: 8px;
    padding: 5px 14px;
    font-weight: 700;
    font-size: 11px;
    letter-spacing: 0.4px;
}}

QLabel.badge-review {{
    background-color: {_WARNING_BG};
    color: {_WARNING};
    border: 1px solid rgba(245, 158, 11, 0.3);
    border-radius: 8px;
    padding: 5px 14px;
    font-weight: 700;
    font-size: 11px;
    letter-spacing: 0.4px;
}}

QLabel.badge-manual {{
    background-color: {_DANGER_BG};
    color: {_DANGER};
    border: 1px solid rgba(239, 68, 68, 0.3);
    border-radius: 8px;
    padding: 5px 14px;
    font-weight: 700;
    font-size: 11px;
    letter-spacing: 0.4px;
}}

/* ═══════════════════════════════════════════════════════════════
   BUTTONS — Multi-tier system
   ═══════════════════════════════════════════════════════════════ */
QPushButton {{
    background-color: {_BG_OVERLAY};
    color: {_TEXT_PRIMARY};
    border: 1px solid {_BORDER_DEFAULT};
    border-radius: 10px;
    padding: 9px 20px;
    font-weight: 500;
    font-size: 13px;
    min-height: 18px;
}}

QPushButton:hover {{
    background-color: {_BG_ELEVATED};
    border-color: {_BORDER_STRONG};
    color: #FFFFFF;
}}

QPushButton:pressed {{
    background-color: {_BG_SURFACE};
    border-color: {_ACCENT};
}}

QPushButton:disabled {{
    background-color: {_BG_BASE};
    color: {_TEXT_DISABLED};
    border-color: {_BORDER_SUBTLE};
}}

/* ── Primary Button (Filled accent) ── */
QPushButton.btn-primary {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 {_ACCENT_HOVER}, stop:1 {_ACCENT});
    color: #FFFFFF;
    border: 1px solid {_ACCENT};
    border-radius: 10px;
    font-weight: 700;
    font-size: 14px;
    padding: 10px 28px;
    letter-spacing: 0.2px;
}}

QPushButton.btn-primary:hover {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 #9399FC, stop:1 {_ACCENT_HOVER});
    border-color: {_ACCENT_HOVER};
    color: #FFFFFF;
}}

QPushButton.btn-primary:pressed {{
    background-color: {_ACCENT_PRESSED};
    border-color: {_ACCENT_PRESSED};
}}

QPushButton.btn-primary:disabled {{
    background-color: {_BG_OVERLAY};
    color: {_TEXT_DISABLED};
    border-color: {_BORDER_SUBTLE};
}}

/* ── Word / Docx Button ── */
QPushButton.btn-docx {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 #1E40AF, stop:1 #1D4ED8);
    color: #BFDBFE;
    border: 1px solid #2563EB;
    border-radius: 10px;
    font-weight: 700;
    font-size: 13px;
    padding: 10px 24px;
}}

QPushButton.btn-docx:hover {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 #2563EB, stop:1 #3B82F6);
    border-color: #60A5FA;
    color: #DBEAFE;
}}

QPushButton.btn-docx:pressed {{
    background-color: #1E3A8A;
}}

/* ── Ghost / Subtle Button ── */
QPushButton.btn-ghost {{
    background-color: transparent;
    border: 1px solid transparent;
    color: {_TEXT_SECONDARY};
    border-radius: 8px;
}}

QPushButton.btn-ghost:hover {{
    background-color: {_BG_OVERLAY};
    border: 1px solid {_BORDER_DEFAULT};
    color: {_TEXT_PRIMARY};
}}

/* ── Danger Button ── */
QPushButton.btn-danger {{
    background-color: {_DANGER_BG};
    color: {_DANGER};
    border: 1px solid rgba(239, 68, 68, 0.3);
    border-radius: 10px;
    font-weight: 600;
}}

QPushButton.btn-danger:hover {{
    background-color: #3D1111;
    border-color: {_DANGER};
}}

/* ── Success Button ── */
QPushButton.btn-success {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 #059669, stop:1 #047857);
    color: #FFFFFF;
    border: 1px solid #10B981;
    border-radius: 10px;
    font-weight: 700;
}}

QPushButton.btn-success:hover {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 #10B981, stop:1 #059669);
}}

/* ═══════════════════════════════════════════════════════════════
   CHIP / SEGMENTED FILTER CONTROLS
   ═══════════════════════════════════════════════════════════════ */
QPushButton.chip-filter {{
    background-color: {_BG_SURFACE};
    border: 1px solid {_BORDER_DEFAULT};
    border-radius: 20px;
    padding: 7px 18px;
    font-size: 12px;
    font-weight: 500;
    color: {_TEXT_SECONDARY};
    min-height: 14px;
}}

QPushButton.chip-filter:checked {{
    background-color: {_ACCENT};
    color: #FFFFFF;
    border-color: {_ACCENT};
    font-weight: 700;
}}

QPushButton.chip-filter:hover:!checked {{
    background-color: {_BG_ELEVATED};
    border-color: {_BORDER_STRONG};
    color: {_TEXT_PRIMARY};
}}

QPushButton.chip-filter:disabled {{
    background-color: {_BG_BASE};
    color: {_TEXT_DISABLED};
    border-color: {_BORDER_SUBTLE};
}}

/* ═══════════════════════════════════════════════════════════════
   DROP ZONE
   ═══════════════════════════════════════════════════════════════ */
QFrame.drop-zone {{
    background-color: {_BG_BASE};
    border: 2px dashed {_BORDER_DEFAULT};
    border-radius: 18px;
}}

QFrame.drop-zone:hover {{
    border-color: {_BORDER_STRONG};
    background-color: {_BG_RAISED};
}}

QFrame.drop-zone-active {{
    background-color: rgba(99, 102, 241, 0.06);
    border: 2px dashed {_ACCENT};
    border-radius: 18px;
}}

/* ═══════════════════════════════════════════════════════════════
   PROGRESS BAR
   ═══════════════════════════════════════════════════════════════ */
QProgressBar {{
    background-color: {_BG_SURFACE};
    border: 1px solid {_BORDER_SUBTLE};
    border-radius: 8px;
    text-align: center;
    color: {_TEXT_PRIMARY};
    height: 10px;
    font-size: 0px;
}}

QProgressBar::chunk {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 {_ACCENT}, stop:1 {_ACCENT_HOVER});
    border-radius: 7px;
    border: none;
}}

/* ═══════════════════════════════════════════════════════════════
   LINE EDIT & COMBO BOX
   ═══════════════════════════════════════════════════════════════ */
QLineEdit, QComboBox {{
    background-color: {_BG_SURFACE};
    border: 1px solid {_BORDER_DEFAULT};
    border-radius: 10px;
    padding: 8px 14px;
    color: {_TEXT_PRIMARY};
    selection-background-color: {_ACCENT};
    font-size: 13px;
}}

QLineEdit:focus, QComboBox:focus {{
    border: 1px solid {_ACCENT};
    background-color: {_BG_RAISED};
}}

QComboBox::drop-down {{
    border: none;
    padding-right: 10px;
    width: 20px;
}}

QComboBox::down-arrow {{
    image: none;
    border: none;
}}

QComboBox QAbstractItemView {{
    background-color: {_BG_SURFACE};
    border: 1px solid {_BORDER_DEFAULT};
    border-radius: 10px;
    selection-background-color: {_ACCENT};
    selection-color: #FFFFFF;
    padding: 4px;
    outline: none;
}}

/* ═══════════════════════════════════════════════════════════════
   LIST WIDGET
   ═══════════════════════════════════════════════════════════════ */
QListWidget {{
    background-color: {_BG_BASE};
    border: 1px solid {_BORDER_SUBTLE};
    border-radius: 12px;
    padding: 6px;
    outline: none;
}}

QListWidget::item {{
    background-color: {_BG_RAISED};
    border: 1px solid {_BORDER_SUBTLE};
    border-radius: 10px;
    margin: 4px 2px;
    padding: 10px 14px;
    color: {_TEXT_PRIMARY};
}}

QListWidget::item:selected {{
    background-color: {_BG_ELEVATED};
    border-color: {_ACCENT};
}}

QListWidget::item:hover:!selected {{
    background-color: {_BG_SURFACE};
    border-color: {_BORDER_DEFAULT};
}}

/* ═══════════════════════════════════════════════════════════════
   TAB WIDGET
   ═══════════════════════════════════════════════════════════════ */
QTabWidget::pane {{
    background-color: {_BG_RAISED};
    border: 1px solid {_BORDER_SUBTLE};
    border-radius: 10px;
}}

QTabBar::tab {{
    background-color: {_BG_SURFACE};
    color: {_TEXT_SECONDARY};
    border: 1px solid {_BORDER_SUBTLE};
    border-bottom: none;
    border-top-left-radius: 8px;
    border-top-right-radius: 8px;
    padding: 8px 20px;
    font-weight: 500;
}}

QTabBar::tab:selected {{
    background-color: {_BG_RAISED};
    color: {_TEXT_PRIMARY};
    font-weight: 700;
}}

/* ═══════════════════════════════════════════════════════════════
   MESSAGE BOX
   ═══════════════════════════════════════════════════════════════ */
QMessageBox {{
    background-color: {_BG_RAISED};
}}

QMessageBox QLabel {{
    color: {_TEXT_PRIMARY};
    font-size: 13px;
}}

/* ═══════════════════════════════════════════════════════════════
   TOOLTIP
   ═══════════════════════════════════════════════════════════════ */
QToolTip {{
    background-color: {_BG_ELEVATED};
    color: {_TEXT_PRIMARY};
    border: 1px solid {_BORDER_DEFAULT};
    border-radius: 8px;
    padding: 6px 12px;
    font-size: 12px;
}}

/* ═══════════════════════════════════════════════════════════════
   SPLITTER & STRETCH
   ═══════════════════════════════════════════════════════════════ */
QSplitter::handle {{
    background-color: {_BORDER_SUBTLE};
    width: 1px;
}}

QSplitter::handle:hover {{
    background-color: {_ACCENT};
}}

/* ═══════════════════════════════════════════════════════════════
   STATUS BAR
   ═══════════════════════════════════════════════════════════════ */
QStatusBar {{
    background-color: {_BG_BASE};
    border-top: 1px solid {_BORDER_SUBTLE};
    color: {_TEXT_SECONDARY};
    font-size: 11px;
}}
"""
