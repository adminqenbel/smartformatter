"""
Main Application Window for QenBel Smart Formatter.
Integrates the clean Header, Mode Switcher ([ Card Mode ] | [ Document Mode ]),
and the multi-step Card and Document workflows.
"""
from pathlib import Path
from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap, QIcon
from PySide6.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QStackedWidget,
    QFrame,
    QMessageBox,
    QButtonGroup,
)

from app.core.config import AppPaths
from app.core.models import ProcessingMode
from app.core.pipeline import FormatterPipeline
from app.ui.theme import CHATGPT_DARK_STYLESHEET
from app.ui.mode_selection import ModeSelectionView
from app.ui.card_mode.card_workflow import CardWorkflow
from app.ui.document_mode.document_workflow import DocumentWorkflow


class GlobalHeaderBar(QFrame):
    """Header bar with QenBel branding, mode selector, and about button."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(64)
        self.setStyleSheet("""
            GlobalHeaderBar {
                background-color: #0F0F14;
                border-bottom: 1px solid #1E1E26;
            }
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(28, 0, 28, 0)
        layout.setSpacing(20)

        # ── Logo & Title ──
        brand_box = QHBoxLayout()
        brand_box.setSpacing(12)

        if AppPaths.LOGO_LIGHT.exists():
            logo_container = QFrame()
            logo_container.setStyleSheet("""
                background-color: #FFFFFF;
                border-radius: 6px;
                padding: 2px;
            """)
            logo_container.setFixedHeight(32)
            lc_lay = QHBoxLayout(logo_container)
            lc_lay.setContentsMargins(6, 2, 6, 2)

            lbl_logo = QLabel()
            pix = QPixmap(str(AppPaths.LOGO_LIGHT))
            lbl_logo.setPixmap(pix.scaledToHeight(22, Qt.SmoothTransformation))
            lc_lay.addWidget(lbl_logo)
            brand_box.addWidget(logo_container)

        app_title = QLabel("QenBel Smart Formatter")
        app_title.setStyleSheet("""
            font-size: 16px;
            font-weight: 800;
            color: #FFFFFF;
            letter-spacing: -0.3px;
            background: transparent;
        """)
        brand_box.addWidget(app_title)

        layout.addLayout(brand_box)
        layout.addSpacing(16)

        # ── Mode Switcher Pills ──
        mode_frame = QFrame()
        mode_frame.setStyleSheet("""
            QFrame {
                background-color: #14141A;
                border: 1px solid #24242E;
                border-radius: 20px;
            }
        """)
        mode_frame.setFixedHeight(40)
        mf_layout = QHBoxLayout(mode_frame)
        mf_layout.setContentsMargins(4, 3, 4, 3)
        mf_layout.setSpacing(4)

        self.btn_card_mode = QPushButton("Card Mode")
        self.btn_card_mode.setCheckable(True)
        self.btn_card_mode.setChecked(True)
        self.btn_card_mode.setCursor(Qt.PointingHandCursor)
        self.btn_card_mode.setFixedHeight(32)

        self.btn_doc_mode = QPushButton("Document Mode")
        self.btn_doc_mode.setCheckable(True)
        self.btn_doc_mode.setCursor(Qt.PointingHandCursor)
        self.btn_doc_mode.setFixedHeight(32)

        pill_style = """
            QPushButton {
                background-color: transparent;
                color: #94A3B8;
                border: none;
                border-radius: 16px;
                font-size: 13px;
                font-weight: 700;
                padding: 0 16px;
            }
            QPushButton:hover {
                color: #FFFFFF;
            }
            QPushButton:checked {
                background-color: #2563EB;
                color: #FFFFFF;
            }
        """
        self.btn_card_mode.setStyleSheet(pill_style)
        self.btn_doc_mode.setStyleSheet(pill_style)

        self.mode_group = QButtonGroup(self)
        self.mode_group.setExclusive(True)
        self.mode_group.addButton(self.btn_card_mode)
        self.mode_group.addButton(self.btn_doc_mode)

        mf_layout.addWidget(self.btn_card_mode)
        mf_layout.addWidget(self.btn_doc_mode)
        layout.addWidget(mode_frame)

        layout.addStretch()

        # ── About Button ──
        btn_about = QPushButton("About")
        btn_about.setCursor(Qt.PointingHandCursor)
        btn_about.setFixedHeight(32)
        btn_about.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: #64748B;
                border: 1px solid #24242E;
                border-radius: 6px;
                font-size: 12px;
                font-weight: 600;
                padding: 0 12px;
            }
            QPushButton:hover {
                color: #94A3B8;
                border-color: #38BDF8;
            }
        """)
        btn_about.clicked.connect(self._show_about)
        layout.addWidget(btn_about)

    def _show_about(self):
        QMessageBox.about(
            self,
            "About QenBel Smart Formatter",
            "<div style='font-family: Segoe UI, sans-serif; font-size: 13px;'>"
            "<h2 style='color: #F8FAFC; margin-bottom: 4px;'>QenBel Smart Formatter</h2>"
            "<p style='color: #38BDF8; font-weight: bold; margin-bottom: 12px;'>Version 1.0.0</p>"
            "<p style='color: #94A3B8; line-height: 1.6;'>"
            "Professional print-shop utility to prepare, perspective-correct, normalize, "
            "and format customer card and document photos for direct printing.</p>"
            "<ul style='color: #94A3B8; line-height: 1.8;'>"
            "<li><b>Card Mode:</b> Standard Card (86×54 mm) & Aadhaar Long Form (210×85 mm)</li>"
            "<li><b>Document Mode:</b> Multi-page document management and PDF export</li>"
            "<li><b>Duplex Side-by-Side:</b> Seamless print output without borders or text</li>"
            "<li><b>100% Local & Offline:</b> Total customer privacy with zero cloud dependencies</li>"
            "</ul>"
            "<p style='color: #64748B; margin-top: 14px;'>&copy; 2026 QenBel Technologies. All rights reserved.</p>"
            "</div>"
        )


class MainWindow(QMainWindow):
    """Main desktop application window."""

    def __init__(self, pipeline: FormatterPipeline = None):
        super().__init__()
        self.setWindowTitle("QenBel Smart Formatter")
        self.resize(1280, 820)
        self.setMinimumSize(1000, 680)

        self.setStyleSheet(CHATGPT_DARK_STYLESHEET)

        self.pipeline = pipeline or FormatterPipeline()

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        root_layout = QVBoxLayout(central_widget)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # The first screen is deliberately a mode choice.  The header and
        # workflow controls appear only after the operator chooses a mode.
        self.header = GlobalHeaderBar(self)
        root_layout.addWidget(self.header)
        self.header.hide()

        # Stacked Views for Modes
        self.mode_stack = QStackedWidget()

        self.mode_selection = ModeSelectionView(self)
        self.card_workflow = CardWorkflow(self.pipeline, self)
        self.doc_workflow = DocumentWorkflow(self.pipeline, self)

        self.mode_stack.addWidget(self.mode_selection)  # Index 0: landing page
        self.mode_stack.addWidget(self.card_workflow)  # Index 1: Card Mode
        self.mode_stack.addWidget(self.doc_workflow)   # Index 2: Document Mode

        root_layout.addWidget(self.mode_stack, stretch=1)

        self.mode_selection.mode_chosen.connect(self._on_mode_selected)
        self.header.btn_card_mode.clicked.connect(self._on_card_mode_selected)
        self.header.btn_doc_mode.clicked.connect(self._on_doc_mode_selected)

    def _on_mode_selected(self, mode: ProcessingMode):
        """Enter a workflow from the first-page mode chooser."""
        self.header.show()
        self._show_mode(mode)

    def _show_mode(self, mode: ProcessingMode):
        self.pipeline.set_mode(mode)
        if mode == ProcessingMode.CARD:
            self.mode_stack.setCurrentIndex(1)
            self.header.btn_card_mode.setChecked(True)
            self.header.btn_doc_mode.setChecked(False)
        else:
            self.mode_stack.setCurrentIndex(2)
            self.header.btn_card_mode.setChecked(False)
            self.header.btn_doc_mode.setChecked(True)

    def _on_card_mode_selected(self):
        self._on_mode_selected(ProcessingMode.CARD)

    def _on_doc_mode_selected(self):
        self._on_mode_selected(ProcessingMode.SHEET)
