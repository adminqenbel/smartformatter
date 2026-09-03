"""
Mode Selection View (Card Mode vs Sheet Mode).
Provides visually striking cards with gradient accents and hover animations
for choosing the document intake workflow.
"""
from pathlib import Path
from PySide6.QtCore import Qt, Signal, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import QPixmap, QColor, QLinearGradient, QPainter, QPen
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QFrame,
    QSizePolicy,
    QGraphicsDropShadowEffect,
)

from app.core.models import ProcessingMode


class AccentLine(QWidget):
    """A thin animated accent line under mode cards."""

    def __init__(self, color: str, parent=None):
        super().__init__(parent)
        self._color = color
        self.setFixedHeight(3)
        self.setMinimumWidth(60)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        gradient = QLinearGradient(0, 0, self.width(), 0)
        gradient.setColorAt(0.0, QColor(self._color))
        gradient.setColorAt(1.0, QColor(self._color).lighter(140))
        painter.setPen(Qt.NoPen)
        painter.setBrush(gradient)
        painter.drawRoundedRect(0, 0, self.width(), 3, 1, 1)


class ModeCard(QFrame):
    """Interactive selectable card for a processing mode with gradient accents and hover glow."""

    selected = Signal(ProcessingMode)

    def __init__(self, mode, title, badge, description, icon_text,
                 accent_color, gradient_start, parent=None):
        super().__init__(parent)
        self.mode = mode
        self.accent_color = accent_color
        self.setProperty("class", "panel-card")
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(420, 380)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)

        # Hover glow effect
        self._shadow = QGraphicsDropShadowEffect(self)
        self._shadow.setBlurRadius(0)
        self._shadow.setColor(QColor(accent_color))
        self._shadow.setOffset(0, 0)
        self.setGraphicsEffect(self._shadow)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 28, 32, 24)
        layout.setSpacing(0)

        # ── Top Row: Icon + Badge ──
        top_row = QHBoxLayout()
        top_row.setSpacing(0)

        icon_label = QLabel(icon_text)
        icon_label.setStyleSheet("font-size: 32px; background: transparent;")
        top_row.addWidget(icon_label)
        top_row.addStretch()

        badge_label = QLabel(badge)
        badge_label.setStyleSheet(f"""
            background-color: rgba({self._hex_to_rgb(gradient_start)}, 0.15);
            color: {gradient_start};
            border: 1px solid rgba({self._hex_to_rgb(gradient_start)}, 0.3);
            border-radius: 6px;
            padding: 4px 10px;
            font-size: 10px;
            font-weight: 700;
            letter-spacing: 0.5px;
        """)
        top_row.addWidget(badge_label)
        layout.addLayout(top_row)

        layout.addSpacing(20)

        # ── Title ──
        title_label = QLabel(title)
        title_label.setStyleSheet("font-size: 26px; font-weight: 800; color: #FFFFFF; letter-spacing: -0.5px; background: transparent;")
        layout.addWidget(title_label)

        layout.addSpacing(12)

        # ── Accent Line ──
        accent_line = AccentLine(gradient_start)
        accent_line.setFixedWidth(80)
        layout.addWidget(accent_line)

        layout.addSpacing(16)

        # ── Description ──
        desc_label = QLabel(description)
        desc_label.setStyleSheet("font-size: 13px; color: #9A9AAA; line-height: 1.6; background: transparent;")
        desc_label.setWordWrap(True)
        layout.addWidget(desc_label)

        layout.addStretch()

        # ── Action Button ──
        btn_select = QPushButton(f"  Start {title}  →")
        btn_select.setFixedHeight(42)
        btn_select.setStyleSheet(f"""
            QPushButton {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 {gradient_start}, stop:1 {accent_color});
                color: #FFFFFF;
                border: none;
                border-radius: 10px;
                font-weight: 700;
                font-size: 14px;
                padding: 0 24px;
                letter-spacing: 0.2px;
            }}
            QPushButton:hover {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 {accent_color}, stop:1 {gradient_start});
            }}
            QPushButton:pressed {{
                background-color: {gradient_start};
            }}
        """)
        btn_select.clicked.connect(lambda: self.selected.emit(self.mode))
        layout.addWidget(btn_select)

    def _hex_to_rgb(self, hex_color):
        hex_color = hex_color.lstrip('#')
        r, g, b = int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16)
        return f"{r}, {g}, {b}"

    def enterEvent(self, event):
        self._shadow.setBlurRadius(40)
        self.setStyleSheet("QFrame.panel-card { border: 1px solid rgba(99, 102, 241, 0.2); }")

    def leaveEvent(self, event):
        self._shadow.setBlurRadius(0)
        self.setStyleSheet("QFrame.panel-card { border: 1px solid #2A2A32; }")

    def mousePressEvent(self, event):
        self.selected.emit(self.mode)
        super().mousePressEvent(event)


class ModeSelectionView(QWidget):
    """Main mode selection screen."""

    mode_chosen = Signal(ProcessingMode)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_ui()

    def setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(60, 50, 60, 50)
        main_layout.setSpacing(0)
        main_layout.setAlignment(Qt.AlignCenter)

        # ── Header Section ──
        header_container = QWidget()
        header_container.setStyleSheet("background: transparent;")
        header_layout = QVBoxLayout(header_container)
        header_layout.setSpacing(12)
        header_layout.setAlignment(Qt.AlignCenter)

        title = QLabel("Select Processing Mode")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("font-size: 36px; font-weight: 800; color: #FFFFFF; letter-spacing: -0.8px; background: transparent;")
        header_layout.addWidget(title)

        subtitle = QLabel("Choose how to format your customer photographs for precision printing.")
        subtitle.setAlignment(Qt.AlignCenter)
        subtitle.setStyleSheet("font-size: 15px; color: #66667A; background: transparent;")
        header_layout.addWidget(subtitle)

        main_layout.addWidget(header_container)

        main_layout.addSpacing(48)

        # ── Cards Container ──
        cards_container = QWidget()
        cards_container.setStyleSheet("background: transparent;")
        cards_layout = QHBoxLayout(cards_container)
        cards_layout.setSpacing(32)
        cards_layout.setAlignment(Qt.AlignCenter)

        card_mode_card = ModeCard(
            mode=ProcessingMode.CARD,
            title="Card Mode",
            badge="1-2 IMAGES",
            description=(
                "Specialized for physical ID cards, driver licenses, "
                "corporate badges, and business cards.\n\n"
                "•  Automatic front & back detection\n"
                "•  Identical output dimensions for duplex printing\n"
                "•  Perspective & skew correction\n"
                "•  ISO/IEC 7810 ID-1 normalization"
            ),
            icon_text="🪪",
            accent_color="#818CF8",
            gradient_start="#6366F1",
        )
        card_mode_card.selected.connect(self.mode_chosen.emit)
        cards_layout.addWidget(card_mode_card)

        sheet_mode_card = ModeCard(
            mode=ProcessingMode.SHEET,
            title="Sheet Mode",
            badge="MULTI-PAGE",
            description=(
                "Specialized for photographed paper documents, invoices, "
                "legal receipts, and bills.\n\n"
                "•  Multi-page batch processing\n"
                "•  Page reordering & orientation deskew\n"
                "•  Direct export to Word (.docx) and PDF\n"
                "•  A4/Letter normalization at 300 DPI"
            ),
            icon_text="📄",
            accent_color="#38BDF8",
            gradient_start="#0EA5E9",
        )
        sheet_mode_card.selected.connect(self.mode_chosen.emit)
        cards_layout.addWidget(sheet_mode_card)

        main_layout.addWidget(cards_container)

        # ── Footer Hint ──
        main_layout.addSpacing(48)

        footer = QLabel("Both modes support interactive 4-corner correction, quality evaluation, and print-ready export.")
        footer.setAlignment(Qt.AlignCenter)
        footer.setStyleSheet("font-size: 12px; color: #444455; background: transparent;")
        main_layout.addWidget(footer)
