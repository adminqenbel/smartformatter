"""
Step 5 of 5: Print & Export (Card Mode).
Dedicated print page with printer selection, copies, paper settings,
prominent PRINT button, and secondary Save Image / Export PDF options.
"""
from typing import Optional
from pathlib import Path
import cv2
import numpy as np
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap, QImage
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QFrame,
    QComboBox,
    QFileDialog,
    QMessageBox,
    QScrollArea,
    QSizePolicy,
    QMenu,
)
try:
    from PySide6.QtPrintSupport import QPrinterInfo
    _PRINT_SUPPORT = True
except Exception:
    _PRINT_SUPPORT = False

from app.core.pipeline import FormatterPipeline
from app.core.print_layout import PrintLayoutEngine
from app.export.image_export import ImageExporter
from app.export.pdf_export import PdfExporter
from app.export.docx_export import DocxExporter
from app.export.printing import PrintManager
from app.utils.logger import get_logger

logger = get_logger("page_print")


class PagePrint(QWidget):
    """
    Step 5: Print & Export (Card Mode)
    Final action screen providing direct Windows printing and file exports.
    """
    start_new_card = Signal()

    def __init__(self, pipeline: FormatterPipeline, parent=None):
        super().__init__(parent)
        self.pipeline = pipeline
        self.layout_engine = PrintLayoutEngine()
        self.copies: int = 1
        self._preview_pixmap: Optional[QPixmap] = None

        self._init_ui()

    def _init_ui(self):
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(32, 20, 32, 24)
        main_layout.setSpacing(28)

        # ── Left Column: Final Visual Preview ──
        left_col = QVBoxLayout()
        left_col.setSpacing(12)

        p_header = QLabel("FINAL PRINT LAYOUT")
        p_header.setStyleSheet("font-size: 12px; font-weight: 800; letter-spacing: 1px; color: #94A3B8; background: transparent;")
        left_col.addWidget(p_header)

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setStyleSheet("""
            QScrollArea {
                background-color: #0A0A0E;
                border: 1px solid #1E1E26;
                border-radius: 12px;
            }
        """)

        self.preview_container = QWidget()
        self.preview_container.setStyleSheet("background-color: #0A0A0E;")
        pc_lay = QVBoxLayout(self.preview_container)
        pc_lay.setAlignment(Qt.AlignCenter)
        pc_lay.setContentsMargins(16, 16, 16, 16)

        self.lbl_preview = QLabel()
        self.lbl_preview.setAlignment(Qt.AlignCenter)
        self.lbl_preview.setStyleSheet("background: transparent;")
        pc_lay.addWidget(self.lbl_preview)

        self.scroll_area.setWidget(self.preview_container)
        left_col.addWidget(self.scroll_area, stretch=1)

        self.lbl_doc_info = QLabel("—")
        self.lbl_doc_info.setStyleSheet("font-size: 12px; color: #64748B; background: transparent;")
        left_col.addWidget(self.lbl_doc_info)

        main_layout.addLayout(left_col, stretch=3)

        # ── Right Column: Print & Export Control Panel ──
        right_panel = QFrame()
        right_panel.setStyleSheet("""
            QFrame {
                background-color: #14141A;
                border: 1px solid #24242E;
                border-radius: 16px;
            }
        """)
        right_panel.setFixedWidth(360)
        r_layout = QVBoxLayout(right_panel)
        r_layout.setContentsMargins(24, 24, 24, 24)
        r_layout.setSpacing(18)

        # Title
        title_box = QVBoxLayout()
        title_box.setSpacing(2)

        step_lbl = QLabel("STEP 5 OF 5")
        step_lbl.setStyleSheet("font-size: 11px; font-weight: 800; letter-spacing: 1.5px; color: #38BDF8; background: transparent;")
        title_box.addWidget(step_lbl)

        title = QLabel("Export Word Document")
        title.setStyleSheet("font-size: 22px; font-weight: 800; color: #FFFFFF; letter-spacing: -0.3px; background: transparent;")
        title_box.addWidget(title)
        r_layout.addLayout(title_box)

        # Word Document Info Card
        info_card = QFrame()
        info_card.setStyleSheet("""
            QFrame {
                background-color: #0F0F14;
                border: 1px solid #1E293B;
                border-radius: 12px;
                padding: 16px;
            }
        """)
        info_lay = QVBoxLayout(info_card)
        info_lay.setSpacing(10)

        info_title = QLabel("📄 Microsoft Word (.docx)")
        info_title.setStyleSheet("font-size: 15px; font-weight: 800; color: #FFFFFF; background: transparent;")
        info_lay.addWidget(info_title)

        info_desc = QLabel(
            "Exports a print-ready Word document on standard A4 paper with Front and Back "
            "sides arranged side-by-side at exact physical dimensions (occupying only respective space)."
        )
        info_desc.setWordWrap(True)
        info_desc.setStyleSheet("font-size: 12px; color: #94A3B8; line-height: 1.4; background: transparent;")
        info_lay.addWidget(info_desc)

        r_layout.addWidget(info_card)

        r_layout.addSpacing(10)

        # Single Primary Action: EXPORT AS WORD (.DOCX)
        self.btn_export_docx = QPushButton("  📄   EXPORT AS WORD (.DOCX)  ")
        self.btn_export_docx.setCursor(Qt.PointingHandCursor)
        self.btn_export_docx.setFixedHeight(56)
        self.btn_export_docx.setStyleSheet("""
            QPushButton {
                background-color: #185ABD;
                color: #FFFFFF;
                border: none;
                border-radius: 12px;
                font-size: 15px;
                font-weight: 800;
                letter-spacing: 0.5px;
            }
            QPushButton:hover {
                background-color: #10458C;
            }
            QPushButton:pressed {
                background-color: #0B336B;
            }
            QPushButton:disabled {
                background-color: #1E293B;
                color: #475569;
            }
        """)
        self.btn_export_docx.clicked.connect(self._on_export_docx)
        r_layout.addWidget(self.btn_export_docx)

        r_layout.addStretch()

        # Start New Card Button
        btn_new = QPushButton("⟲  Start New Card")
        btn_new.setCursor(Qt.PointingHandCursor)
        btn_new.setFixedHeight(40)
        btn_new.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                color: #38BDF8;
                border: 1px solid #1E293B;
                border-radius: 8px;
                font-size: 13px;
                font-weight: 700;
            }
            QPushButton:hover {
                background-color: #1E293B;
                border-color: #38BDF8;
                color: #FFFFFF;
            }
        """)
        btn_new.clicked.connect(self.start_new_card.emit)
        r_layout.addWidget(btn_new)

        main_layout.addWidget(right_panel)

    def _combo_style(self):
        return """
            QComboBox {
                background-color: #0F0F14;
                color: #E2E8F0;
                border: 1px solid #24242E;
                border-radius: 8px;
                padding: 4px 12px;
                font-size: 13px;
                font-weight: 500;
            }
            QComboBox:hover { border-color: #38BDF8; }
            QComboBox::drop-down { border: none; }
            QComboBox QAbstractItemView {
                background-color: #14141A;
                color: #FFFFFF;
                selection-background-color: #2563EB;
                border: 1px solid #24242E;
            }
        """

    def _stepper_style(self):
        return """
            QPushButton {
                background-color: #1E1E26;
                color: #FFFFFF;
                border: 1px solid #2E2E3A;
                border-radius: 8px;
                font-size: 16px;
                font-weight: 700;
            }
            QPushButton:hover { background-color: #2E2E3A; }
        """

    def _sec_btn_style(self):
        return """
            QPushButton {
                background-color: #1E293B;
                color: #E2E8F0;
                border: 1px solid #334155;
                border-radius: 8px;
                font-size: 13px;
                font-weight: 600;
            }
            QPushButton:hover {
                background-color: #334155;
                border-color: #475569;
                color: #FFFFFF;
            }
        """

    def _populate_printers(self):
        self.combo_printers.clear()
        if _PRINT_SUPPORT:
            printers = QPrinterInfo.availablePrinterNames()
            default_p = QPrinterInfo.defaultPrinterName()
            if printers:
                for p in printers:
                    self.combo_printers.addItem(p)
                if default_p in printers:
                    self.combo_printers.setCurrentText(default_p)
                return
        self.combo_printers.addItem("Default System Printer")

    def _decrement_copies(self):
        self.copies = max(1, self.copies - 1)
        self.lbl_copies.setText(str(self.copies))

    def _increment_copies(self):
        self.copies = min(99, self.copies + 1)
        self.lbl_copies.setText(str(self.copies))

    def refresh_preview(self):
        entry = self.pipeline.card_entry
        if entry is None or entry.is_empty():
            self.lbl_preview.setPixmap(QPixmap())
            self.lbl_doc_info.setText("No card loaded.")
            self.btn_export_docx.setEnabled(False)
            return

        f_proc = entry.front
        b_proc = entry.back
        f_img = f_proc.final_image if f_proc is not None else None
        b_img = b_proc.final_image if b_proc is not None else None
        profile = entry.format_profile or self.pipeline.active_card_profile

        rendered, metrics = self.layout_engine.render_pair(
            f_img, b_img, profile, copies=1, single_page=False
        )
        if rendered is not None:
            rgb = cv2.cvtColor(rendered, cv2.COLOR_BGR2RGB)
            h, w = rgb.shape[:2]
            qimg = QImage(rgb.data, w, h, w * 3, QImage.Format_RGB888)
            self._preview_pixmap = QPixmap.fromImage(qimg)
            # Scale to fit scroll viewport
            scaled = self._preview_pixmap.scaled(
                600, 360, Qt.KeepAspectRatio, Qt.SmoothTransformation
            )
            self.lbl_preview.setPixmap(scaled)

        if metrics:
            self.lbl_doc_info.setText(
                f"Output: {profile.name}  •  {profile.dimensions_mm_str}  •  "
                f"Formatted on A4 Sheet ready for printing"
            )

        self.btn_export_docx.setEnabled(True)

    def _on_export_docx(self):
        entry = self.pipeline.card_entry
        if not entry or entry.is_empty():
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Word Document", "Formatted_Print_Document.docx", "Word Document (*.docx)"
        )
        if not path:
            return
        ok = DocxExporter.export_card_pair(self.pipeline.card_pair, path)
        if ok:
            msg_box = QMessageBox(self)
            msg_box.setWindowTitle("Word Document Ready")
            msg_box.setText(f"Print-ready document exported successfully:\n\n{path}")
            msg_box.setIcon(QMessageBox.Information)
            btn_open = msg_box.addButton("Open Document", QMessageBox.ActionRole)
            msg_box.addButton(QMessageBox.Ok)
            msg_box.exec()

            if msg_box.clickedButton() == btn_open:
                import os
                try:
                    os.startfile(path)
                except Exception as e:
                    logger.error(f"Failed to open exported file {path}: {e}")
        else:
            QMessageBox.critical(self, "Export Failed", "Could not export Word document.")

