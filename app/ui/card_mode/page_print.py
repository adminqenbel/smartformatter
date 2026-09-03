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
    QDoubleSpinBox,
    QCheckBox,
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
        right_panel.setFixedWidth(380)
        r_layout = QVBoxLayout(right_panel)
        r_layout.setContentsMargins(22, 20, 22, 20)
        r_layout.setSpacing(14)

        # Title
        title_box = QVBoxLayout()
        title_box.setSpacing(2)

        step_lbl = QLabel("STEP 5 OF 5")
        step_lbl.setStyleSheet("font-size: 11px; font-weight: 800; letter-spacing: 1.5px; color: #38BDF8; background: transparent;")
        title_box.addWidget(step_lbl)

        title = QLabel("Export Word Document")
        title.setStyleSheet("font-size: 21px; font-weight: 800; color: #FFFFFF; letter-spacing: -0.3px; background: transparent;")
        title_box.addWidget(title)
        r_layout.addLayout(title_box)

        # Output Layout & Size Configuration Card
        cfg_card = QFrame()
        cfg_card.setStyleSheet("""
            QFrame {
                background-color: #0F0F14;
                border: 1px solid #1E293B;
                border-radius: 12px;
                padding: 12px;
            }
        """)
        cfg_lay = QVBoxLayout(cfg_card)
        cfg_lay.setSpacing(10)

        cfg_head = QLabel("📏 CARD SIZING & LAYOUT")
        cfg_head.setStyleSheet("font-size: 11px; font-weight: 800; letter-spacing: 1px; color: #94A3B8; background: transparent;")
        cfg_lay.addWidget(cfg_head)

        # Layout selector
        lay_row = QVBoxLayout()
        lay_row.setSpacing(4)
        lbl_lay = QLabel("Placement Layout")
        lbl_lay.setStyleSheet("font-size: 12px; font-weight: 700; color: #CBD5E1; background: transparent;")
        lay_row.addWidget(lbl_lay)

        self.combo_layout = QComboBox()
        self.combo_layout.setFixedHeight(34)
        self.combo_layout.setStyleSheet(self._combo_style())
        self.combo_layout.addItems([
            "Auto (Recommended)",
            "Stacked (Top / Bottom — Full Size)",
            "Side-by-Side (Horizontal)"
        ])
        lay_row.addWidget(self.combo_layout)
        cfg_lay.addLayout(lay_row)

        # Width and Height spinboxes
        size_box = QHBoxLayout()
        size_box.setSpacing(12)

        # Width
        w_col = QVBoxLayout()
        w_col.setSpacing(4)
        lbl_w = QLabel("Card Width")
        lbl_w.setStyleSheet("font-size: 12px; font-weight: 700; color: #CBD5E1; background: transparent;")
        w_col.addWidget(lbl_w)

        self.spin_width = QDoubleSpinBox()
        self.spin_width.setFixedHeight(34)
        self.spin_width.setRange(2.0, 20.5)
        self.spin_width.setSingleStep(0.1)
        self.spin_width.setDecimals(1)
        self.spin_width.setSuffix(" cm")
        self.spin_width.setValue(8.6)
        self.spin_width.setStyleSheet(self._spin_style())
        self.spin_width.valueChanged.connect(self._on_width_changed)
        w_col.addWidget(self.spin_width)
        size_box.addLayout(w_col)

        # Height
        h_col = QVBoxLayout()
        h_col.setSpacing(4)
        lbl_h = QLabel("Card Height")
        lbl_h.setStyleSheet("font-size: 12px; font-weight: 700; color: #CBD5E1; background: transparent;")
        h_col.addWidget(lbl_h)

        self.spin_height = QDoubleSpinBox()
        self.spin_height.setFixedHeight(34)
        self.spin_height.setRange(2.0, 28.0)
        self.spin_height.setSingleStep(0.1)
        self.spin_height.setDecimals(1)
        self.spin_height.setSuffix(" cm")
        self.spin_height.setValue(5.4)
        self.spin_height.setStyleSheet(self._spin_style())
        h_col.addWidget(self.spin_height)
        size_box.addLayout(h_col)

        cfg_lay.addLayout(size_box)

        # Lock aspect ratio & reset buttons
        aspect_row = QHBoxLayout()
        self.chk_lock_aspect = QCheckBox("Lock aspect ratio")
        self.chk_lock_aspect.setChecked(True)
        self.chk_lock_aspect.setStyleSheet("color: #94A3B8; font-size: 11px; font-weight: 600; background: transparent;")
        aspect_row.addWidget(self.chk_lock_aspect)

        btn_reset_sz = QPushButton("↺ Reset")
        btn_reset_sz.setCursor(Qt.PointingHandCursor)
        btn_reset_sz.setFixedHeight(26)
        btn_reset_sz.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: #38BDF8;
                border: none;
                font-size: 11px;
                font-weight: 700;
            }
            QPushButton:hover { text-decoration: underline; }
        """)
        btn_reset_sz.clicked.connect(self._reset_default_size)
        aspect_row.addWidget(btn_reset_sz, alignment=Qt.AlignRight)

        cfg_lay.addLayout(aspect_row)
        r_layout.addWidget(cfg_card)

        r_layout.addSpacing(4)

        # Single Primary Action: EXPORT AS WORD (.DOCX)
        self.btn_export_docx = QPushButton("  📄   EXPORT AS WORD (.DOCX)  ")
        self.btn_export_docx.setCursor(Qt.PointingHandCursor)
        self.btn_export_docx.setFixedHeight(54)
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
        btn_new.setFixedHeight(38)
        btn_new.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                color: #38BDF8;
                border: 1px solid #1E293B;
                border-radius: 8px;
                font-size: 12px;
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

    def _spin_style(self):
        return """
            QDoubleSpinBox {
                background-color: #0F0F14;
                color: #FFFFFF;
                border: 1px solid #24242E;
                border-radius: 8px;
                padding: 4px 8px;
                font-size: 13px;
                font-weight: 700;
            }
            QDoubleSpinBox:focus { border-color: #38BDF8; }
        """

    def _on_width_changed(self, new_w: float):
        if not self.chk_lock_aspect.isChecked():
            return
        entry = self.pipeline.card_entry
        ref_img = None
        if entry and entry.front and entry.front.final_image is not None:
            ref_img = entry.front.final_image
        elif entry and entry.back and entry.back.final_image is not None:
            ref_img = entry.back.final_image

        if ref_img is not None:
            ih, iw = ref_img.shape[:2]
            asp = iw / max(ih, 1)
        else:
            profile = (entry.format_profile if entry else None) or self.pipeline.active_card_profile
            asp = max(profile.aspect_ratio, 1e-3)

        calc_h = round(new_w / max(asp, 1e-3), 1)
        self.spin_height.blockSignals(True)
        self.spin_height.setValue(calc_h)
        self.spin_height.blockSignals(False)

    def _reset_default_size(self):
        entry = self.pipeline.card_entry
        profile = (entry.format_profile if entry else None) or self.pipeline.active_card_profile
        is_long = (profile.id == "long_form" or profile.aspect_ratio >= 2.0)
        is_port = False
        if entry and entry.front and entry.front.final_image is not None:
            f = entry.front.final_image
            is_port = f.shape[0] > f.shape[1]
        elif entry and entry.back and entry.back.final_image is not None:
            b = entry.back.final_image
            is_port = b.shape[0] > b.shape[1]

        self.spin_width.blockSignals(True)
        self.spin_height.blockSignals(True)
        if is_long:
            if is_port:
                # Vertical Aadhaar cut-slip (8.5 cm wide x 21.0 cm high)
                self.spin_width.setValue(8.5)
                self.spin_height.setValue(21.0)
                self.combo_layout.setCurrentIndex(2)  # Side-by-side fits naturally on A4!
            else:
                # Horizontal Aadhaar cut-slip (21.0 cm wide x 8.5 cm high)
                self.spin_width.setValue(18.5)
                self.spin_height.setValue(round(18.5 / max(profile.aspect_ratio, 1e-3), 1))
                self.combo_layout.setCurrentIndex(1)  # Stacked fits full width!
        elif is_port:
            self.spin_width.setValue(5.4)
            self.spin_height.setValue(8.6)
            self.combo_layout.setCurrentIndex(2)  # Side-by-side
        else:
            self.spin_width.setValue(8.6)
            self.spin_height.setValue(5.4)
            self.combo_layout.setCurrentIndex(2)  # Side-by-side
        self.spin_width.blockSignals(False)
        self.spin_height.blockSignals(False)

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

        # Reset sizing controls to match active profile defaults
        self._reset_default_size()

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

        lay_idx = self.combo_layout.currentIndex()
        if lay_idx == 0:
            layout_mode = "auto"
        elif lay_idx == 1:
            layout_mode = "stacked"
        else:
            layout_mode = "side_by_side"

        ok = DocxExporter.export_card_pair(
            self.pipeline.card_pair,
            path,
            layout=layout_mode,
            custom_width_cm=self.spin_width.value(),
            custom_height_cm=self.spin_height.value(),
        )
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

