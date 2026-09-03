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
        step_lbl.setStyleSheet("font-size: 11px; font-weight: 800; letter-spacing: 1.5px; color: #10B981; background: transparent;")
        title_box.addWidget(step_lbl)

        title = QLabel("Print & Export")
        title.setStyleSheet("font-size: 22px; font-weight: 800; color: #FFFFFF; letter-spacing: -0.3px; background: transparent;")
        title_box.addWidget(title)
        r_layout.addLayout(title_box)

        # Printer Selector
        p_box = QVBoxLayout()
        p_box.setSpacing(6)
        lbl_p = QLabel("Printer")
        lbl_p.setStyleSheet("font-size: 12px; font-weight: 700; color: #94A3B8; background: transparent;")
        p_box.addWidget(lbl_p)

        self.combo_printers = QComboBox()
        self.combo_printers.setFixedHeight(38)
        self.combo_printers.setStyleSheet(self._combo_style())
        self._populate_printers()
        p_box.addWidget(self.combo_printers)
        r_layout.addLayout(p_box)

        # Copies Selector
        c_box = QVBoxLayout()
        c_box.setSpacing(6)
        lbl_c = QLabel("Copies")
        lbl_c.setStyleSheet("font-size: 12px; font-weight: 700; color: #94A3B8; background: transparent;")
        c_box.addWidget(lbl_c)

        copies_row = QHBoxLayout()
        copies_row.setSpacing(8)

        btn_minus = QPushButton("−")
        btn_minus.setFixedSize(36, 36)
        btn_minus.setCursor(Qt.PointingHandCursor)
        btn_minus.setStyleSheet(self._stepper_style())
        btn_minus.clicked.connect(self._decrement_copies)
        copies_row.addWidget(btn_minus)

        self.lbl_copies = QLabel("1")
        self.lbl_copies.setAlignment(Qt.AlignCenter)
        self.lbl_copies.setFixedWidth(40)
        self.lbl_copies.setStyleSheet("font-size: 16px; font-weight: 700; color: #FFFFFF; background: transparent;")
        copies_row.addWidget(self.lbl_copies)

        btn_plus = QPushButton("＋")
        btn_plus.setFixedSize(36, 36)
        btn_plus.setCursor(Qt.PointingHandCursor)
        btn_plus.setStyleSheet(self._stepper_style())
        btn_plus.clicked.connect(self._increment_copies)
        copies_row.addWidget(btn_plus)

        copies_row.addStretch()
        c_box.addLayout(copies_row)
        r_layout.addLayout(c_box)

        # Paper Size & Scaling
        opt_box = QVBoxLayout()
        opt_box.setSpacing(6)
        lbl_opt = QLabel("Paper Size & Scaling")
        lbl_opt.setStyleSheet("font-size: 12px; font-weight: 700; color: #94A3B8; background: transparent;")
        opt_box.addWidget(lbl_opt)

        self.combo_paper = QComboBox()
        self.combo_paper.setFixedHeight(36)
        self.combo_paper.setStyleSheet(self._combo_style())
        self.combo_paper.addItems(["Printer Default", "A4 (210 × 297 mm)", "Letter (8.5 × 11 in)"])
        opt_box.addWidget(self.combo_paper)

        self.combo_scaling = QComboBox()
        self.combo_scaling.setFixedHeight(36)
        self.combo_scaling.setStyleSheet(self._combo_style())
        self.combo_scaling.addItems(["Actual Size (100% 300 DPI)", "Fit to Printable Area"])
        opt_box.addWidget(self.combo_scaling)
        r_layout.addLayout(opt_box)

        r_layout.addSpacing(6)

        # Primary PRINT Button
        self.btn_print = QPushButton("  🖨   PRINT  ")
        self.btn_print.setCursor(Qt.PointingHandCursor)
        self.btn_print.setFixedHeight(52)
        self.btn_print.setStyleSheet("""
            QPushButton {
                background-color: #10B981;
                color: #FFFFFF;
                border: none;
                border-radius: 12px;
                font-size: 16px;
                font-weight: 800;
                letter-spacing: 0.5px;
            }
            QPushButton:hover {
                background-color: #059669;
            }
            QPushButton:pressed {
                background-color: #047857;
            }
            QPushButton:disabled {
                background-color: #1E293B;
                color: #475569;
            }
        """)
        self.btn_print.clicked.connect(self._on_print)
        r_layout.addWidget(self.btn_print)

        # Secondary Actions
        sec_box = QVBoxLayout()
        sec_box.setSpacing(8)

        self.btn_save_img = QPushButton("Save Image (PNG)")
        self.btn_save_img.setCursor(Qt.PointingHandCursor)
        self.btn_save_img.setFixedHeight(40)
        self.btn_save_img.setStyleSheet(self._sec_btn_style())
        self.btn_save_img.clicked.connect(self._on_save_image)
        sec_box.addWidget(self.btn_save_img)

        self.btn_export_pdf = QPushButton("Export PDF")
        self.btn_export_pdf.setCursor(Qt.PointingHandCursor)
        self.btn_export_pdf.setFixedHeight(40)
        self.btn_export_pdf.setStyleSheet(self._sec_btn_style())
        self.btn_export_pdf.clicked.connect(self._on_export_pdf)
        sec_box.addWidget(self.btn_export_pdf)

        self.btn_more = QPushButton("More Export Options ▼")
        self.btn_more.setCursor(Qt.PointingHandCursor)
        self.btn_more.setFixedHeight(34)
        self.btn_more.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: #64748B;
                border: none;
                font-size: 12px;
                font-weight: 600;
            }
            QPushButton:hover { color: #94A3B8; }
        """)
        self.btn_more.clicked.connect(self._show_more_menu)
        sec_box.addWidget(self.btn_more, alignment=Qt.AlignCenter)

        r_layout.addLayout(sec_box)

        r_layout.addStretch()

        # Start New Card Button
        btn_new = QPushButton("⟲  Start New Card")
        btn_new.setCursor(Qt.PointingHandCursor)
        btn_new.setFixedHeight(36)
        btn_new.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                color: #38BDF8;
                border: 1px solid #1E293B;
                border-radius: 8px;
                font-size: 12px;
                font-weight: 600;
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
            self.btn_print.setEnabled(False)
            self.btn_save_img.setEnabled(False)
            self.btn_export_pdf.setEnabled(False)
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
                f"Output: {profile.name}  •  {metrics.page_width_mm:.0f} × {metrics.page_height_mm:.0f} mm  •  "
                f"{metrics.page_width_px} × {metrics.page_height_px} px @ 300 DPI"
            )

        self.btn_print.setEnabled(True)
        self.btn_save_img.setEnabled(True)
        self.btn_export_pdf.setEnabled(True)

    def _on_print(self):
        entry = self.pipeline.card_entry
        if not entry or entry.is_empty():
            return

        printer_name = self.combo_printers.currentText()
        if printer_name == "Default System Printer":
            printer_name = None

        ok = PrintManager.print_card_pair(
            self.pipeline.card_pair,
            parent_widget=self,
            copies=self.copies,
            printer_name=printer_name,
            show_dialog=False,
            single_page=False,
        )
        if ok:
            QMessageBox.information(self, "Print Sent", "The document was sent directly to the printer.")
        else:
            # Fallback to system dialog
            PrintManager.print_card_pair(
                self.pipeline.card_pair,
                parent_widget=self,
                copies=self.copies,
                show_dialog=True,
                single_page=False,
            )

    def _on_save_image(self):
        entry = self.pipeline.card_entry
        if not entry or entry.is_empty():
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Card Image", "card_output.png", "PNG Image (*.png);;JPEG Image (*.jpg)"
        )
        if not path:
            return
        ok = ImageExporter.export_card_pair(
            self.pipeline.card_pair, path, copies=self.copies, single_page=False
        )
        if ok:
            QMessageBox.information(self, "Image Saved", f"Image saved successfully to:\n{path}")
        else:
            QMessageBox.critical(self, "Save Failed", "Could not save the image.")

    def _on_export_pdf(self):
        entry = self.pipeline.card_entry
        if not entry or entry.is_empty():
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Export PDF", "card_output.pdf", "PDF Document (*.pdf)"
        )
        if not path:
            return
        ok = PdfExporter.export_card_pair(
            self.pipeline.card_pair, path, copies=self.copies, single_page=False
        )
        if ok:
            QMessageBox.information(self, "PDF Exported", f"PDF exported successfully to:\n{path}")
        else:
            QMessageBox.critical(self, "Export Failed", "Could not export PDF.")

    def _show_more_menu(self):
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background-color: #1E293B;
                color: #FFFFFF;
                border: 1px solid #334155;
                padding: 4px;
            }
            QMenu::item:selected {
                background-color: #2563EB;
            }
        """)
        action_docx = menu.addAction("Export Microsoft Word (.docx)")
        action_tiled = menu.addAction("Export Tiled A4 Sheet (PNG)")
        action = menu.exec(self.btn_more.mapToGlobal(self.btn_more.rect().bottomLeft()))

        if action == action_docx:
            self._on_export_docx()
        elif action == action_tiled:
            self._on_export_tiled_sheet()

    def _on_export_docx(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Word Document", "card_output.docx", "Word Document (*.docx)"
        )
        if not path:
            return
        ok = DocxExporter.export_card_pair(self.pipeline.card_pair, path)
        if ok:
            QMessageBox.information(self, "Word Exported", f"Document exported successfully to:\n{path}")
        else:
            QMessageBox.critical(self, "Export Failed", "Could not export Word document.")

    def _on_export_tiled_sheet(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Tiled Sheet", "cards_sheet.png", "PNG Image (*.png)"
        )
        if not path:
            return
        ok = ImageExporter.export_card_pair(
            self.pipeline.card_pair, path, copies=self.copies, single_page=True
        )
        if ok:
            QMessageBox.information(self, "Sheet Exported", f"Tiled sheet exported successfully to:\n{path}")
        else:
            QMessageBox.critical(self, "Export Failed", "Could not export tiled sheet.")
