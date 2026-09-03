"""
Preview, Comparison, Format Selection, and Quality Inspection View.
Provides side-by-side before/after review, dynamic format profile selection,
format mismatch advisory, granular quality pills, enhancement filter chips, and action toolbar.
"""
from typing import Optional
from pathlib import Path
import cv2
import numpy as np
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap, QImage, QColor
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QFrame,
    QButtonGroup,
    QScrollArea,
    QMessageBox,
    QFileDialog,
    QGraphicsDropShadowEffect,
    QSizePolicy,
)

from app.core.profiles import FormatProfile, CARD_PROFILE, LONG_FORM_PROFILE, ProfileRegistry
from app.core.models import (
    ProcessingMode,
    ProcessedImage,
    EnhancementMode,
    ConfidenceLevel,
)
from app.core.pipeline import FormatterPipeline
from app.ui.corner_editor import CornerEditorDialog
from app.export.docx_export import DocxExporter
from app.export.pdf_export import PdfExporter
from app.export.image_export import ImageExporter
from app.utils.logger import get_logger

logger = get_logger("preview_view")


class ImageDisplayPanel(QFrame):
    """Panel displaying an image with title, shadow, and zoom-to-fit."""

    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self.setProperty("class", "panel-card")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        # Title with accent indicator
        title_row = QHBoxLayout()
        title_row.setSpacing(8)

        indicator = QLabel()
        indicator.setFixedSize(4, 16)
        indicator.setStyleSheet("background-color: #6366F1; border-radius: 2px;")
        title_row.addWidget(indicator)

        self.lbl_title = QLabel(title)
        self.lbl_title.setStyleSheet("font-size: 12px; font-weight: 700; color: #9A9AAA; letter-spacing: 0.5px; background: transparent;")
        title_row.addWidget(self.lbl_title)
        title_row.addStretch()
        layout.addLayout(title_row)

        # Image display area
        self.lbl_image = QLabel("No Image")
        self.lbl_image.setAlignment(Qt.AlignCenter)
        self.lbl_image.setMinimumHeight(280)
        self.lbl_image.setStyleSheet("""
            background-color: #0D0D0D;
            border: 1px solid #1A1A1E;
            border-radius: 12px;
            color: #444455;
            font-size: 14px;
        """)
        layout.addWidget(self.lbl_image, stretch=1)

        # Metadata
        self.lbl_meta = QLabel("—")
        self.lbl_meta.setStyleSheet("font-size: 11px; color: #444455; background: transparent;")
        self.lbl_meta.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.lbl_meta)

    def set_image(self, bgr_img: Optional[np.ndarray], meta_text: str = ""):
        if bgr_img is None:
            self.lbl_image.setText("No Image")
            self.lbl_meta.setText("—")
            return

        h, w = bgr_img.shape[:2]
        rgb = cv2.cvtColor(bgr_img, cv2.COLOR_BGR2RGB)
        qimg = QImage(rgb.data, w, h, w * 3, QImage.Format_RGB888)
        pix = QPixmap.fromImage(qimg)

        scaled_pix = pix.scaled(520, 380, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.lbl_image.setPixmap(scaled_pix)
        self.lbl_meta.setText(meta_text or f"{w} × {h} px")


class QualityIndicatorBar(QFrame):
    """A refined quality status display with gradient background."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setProperty("class", "panel-card")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 10, 16, 10)
        layout.setSpacing(16)

        # Status icon
        self.status_dot = QLabel()
        self.status_dot.setFixedSize(10, 10)
        self.status_dot.setStyleSheet("background-color: #10B981; border-radius: 5px;")
        layout.addWidget(self.status_dot, alignment=Qt.AlignVCenter)

        # Issues text
        self.lbl_issues = QLabel("Quality Status: Pending")
        self.lbl_issues.setStyleSheet("font-size: 12px; color: #9A9AAA; background: transparent;")
        self.lbl_issues.setWordWrap(True)
        layout.addWidget(self.lbl_issues, stretch=1)

    def set_status(self, color: str, text: str):
        self.status_dot.setStyleSheet(f"background-color: {color}; border-radius: 5px;")
        self.lbl_issues.setText(text)


class PreviewView(QWidget):
    """Main preview, format profile selection, and quality inspection screen."""

    back_to_upload = Signal()

    def __init__(self, pipeline: FormatterPipeline, parent=None):
        super().__init__(parent)
        self.pipeline = pipeline
        self.active_sheet_index = 0
        self.active_card_side = "front"

        self.setup_ui()

    def setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(24, 12, 24, 16)
        main_layout.setSpacing(12)

        # ── 1. Top Navigation & Selector Bar ──
        top_bar = QHBoxLayout()
        top_bar.setSpacing(10)

        btn_back = QPushButton("← Intake Queue")
        btn_back.setProperty("class", "btn-ghost")
        btn_back.setFixedHeight(34)
        top_bar.addWidget(btn_back)

        top_bar.addSpacing(8)

        # Card Side Selector
        self.card_selector_widget = QWidget()
        self.card_selector_widget.setStyleSheet("background: transparent;")
        card_sel_layout = QHBoxLayout(self.card_selector_widget)
        card_sel_layout.setContentsMargins(0, 0, 0, 0)
        card_sel_layout.setSpacing(6)

        self.btn_sel_front = QPushButton("Front Card")
        self.btn_sel_front.setProperty("class", "chip-filter")
        self.btn_sel_front.setCheckable(True)
        self.btn_sel_front.setChecked(True)
        self.btn_sel_front.clicked.connect(lambda: self.set_active_card_side("front"))
        card_sel_layout.addWidget(self.btn_sel_front)

        self.btn_sel_back = QPushButton("Back Card")
        self.btn_sel_back.setProperty("class", "chip-filter")
        self.btn_sel_back.setCheckable(True)
        self.btn_sel_back.clicked.connect(lambda: self.set_active_card_side("back"))
        card_sel_layout.addWidget(self.btn_sel_back)

        top_bar.addWidget(self.card_selector_widget)

        # Format Profile Switcher
        self.format_switcher_widget = QWidget()
        self.format_switcher_widget.setStyleSheet("background: transparent;")
        fmt_sw_layout = QHBoxLayout(self.format_switcher_widget)
        fmt_sw_layout.setContentsMargins(0, 0, 0, 0)
        fmt_sw_layout.setSpacing(6)

        lbl_profile = QLabel("Profile:")
        lbl_profile.setStyleSheet("color: #66667A; font-weight: 600; font-size: 11px; background: transparent;")
        fmt_sw_layout.addWidget(lbl_profile)

        self.btn_fmt_card = QPushButton("Card  (86×54 mm)")
        self.btn_fmt_card.setProperty("class", "chip-filter")
        self.btn_fmt_card.setCheckable(True)
        self.btn_fmt_card.clicked.connect(lambda: self.on_switch_profile(CARD_PROFILE))
        fmt_sw_layout.addWidget(self.btn_fmt_card)

        self.btn_fmt_long = QPushButton("Long Form  (210×85 mm)")
        self.btn_fmt_long.setProperty("class", "chip-filter")
        self.btn_fmt_long.setCheckable(True)
        self.btn_fmt_long.clicked.connect(lambda: self.on_switch_profile(LONG_FORM_PROFILE))
        fmt_sw_layout.addWidget(self.btn_fmt_long)

        top_bar.addWidget(self.format_switcher_widget)

        # Page Carousel
        self.sheet_carousel_widget = QWidget()
        self.sheet_carousel_widget.setStyleSheet("background: transparent;")
        sheet_sel_layout = QHBoxLayout(self.sheet_carousel_widget)
        sheet_sel_layout.setContentsMargins(0, 0, 0, 0)
        sheet_sel_layout.setSpacing(10)

        self.btn_prev_page = QPushButton("◀")
        self.btn_prev_page.setFixedSize(32, 32)
        self.btn_prev_page.clicked.connect(self.on_prev_page)
        sheet_sel_layout.addWidget(self.btn_prev_page)

        self.lbl_page_counter = QLabel("Page 1 of 1")
        self.lbl_page_counter.setStyleSheet("font-weight: 600; font-size: 12px; color: #9A9AAA; background: transparent; padding: 0 4px;")
        sheet_sel_layout.addWidget(self.lbl_page_counter)

        self.btn_next_page = QPushButton("▶")
        self.btn_next_page.setFixedSize(32, 32)
        self.btn_next_page.clicked.connect(self.on_next_page)
        sheet_sel_layout.addWidget(self.btn_next_page)

        top_bar.addWidget(self.sheet_carousel_widget)

        top_bar.addStretch()

        # Quality Badge
        self.lbl_quality_badge = QLabel("● HIGH CONFIDENCE")
        self.lbl_quality_badge.setProperty("class", "badge-high")
        top_bar.addWidget(self.lbl_quality_badge)

        main_layout.addLayout(top_bar)

        # ── 2. Format Mismatch Banner ──
        self.mismatch_banner = QFrame()
        self.mismatch_banner.setStyleSheet("""
            QFrame {
                background-color: rgba(245, 158, 11, 0.08);
                border: 1px solid rgba(245, 158, 11, 0.3);
                border-radius: 12px;
                padding: 4px 12px;
            }
        """)
        mismatch_layout = QHBoxLayout(self.mismatch_banner)
        mismatch_layout.setContentsMargins(12, 8, 12, 8)
        mismatch_layout.setSpacing(16)

        mismatch_icon = QLabel("⚠")
        mismatch_icon.setStyleSheet("font-size: 16px; background: transparent;")
        mismatch_layout.addWidget(mismatch_icon)

        self.lbl_mismatch_msg = QLabel("Possible Format Mismatch detected.")
        self.lbl_mismatch_msg.setStyleSheet("color: #F59E0B; font-weight: 600; font-size: 12px; background: transparent;")
        self.lbl_mismatch_msg.setWordWrap(True)
        mismatch_layout.addWidget(self.lbl_mismatch_msg, stretch=1)

        self.btn_mismatch_switch = QPushButton("Switch Profile")
        self.btn_mismatch_switch.setFixedHeight(30)
        self.btn_mismatch_switch.setStyleSheet("""
            QPushButton {
                background-color: #F59E0B;
                color: #000000;
                font-weight: 700;
                font-size: 11px;
                padding: 4px 14px;
                border: none;
                border-radius: 8px;
            }
            QPushButton:hover { background-color: #FBBF24; }
        """)
        self.btn_mismatch_switch.clicked.connect(self.on_apply_suggested_profile)
        mismatch_layout.addWidget(self.btn_mismatch_switch)

        self.btn_mismatch_dismiss = QPushButton("Keep Current")
        self.btn_mismatch_dismiss.setProperty("class", "btn-ghost")
        self.btn_mismatch_dismiss.setFixedHeight(30)
        self.btn_mismatch_dismiss.clicked.connect(lambda: self.mismatch_banner.hide())
        mismatch_layout.addWidget(self.btn_mismatch_dismiss)

        self.mismatch_banner.hide()
        main_layout.addWidget(self.mismatch_banner)

        # ── 3. Main Comparison Display ──
        display_layout = QHBoxLayout()
        display_layout.setSpacing(16)

        self.panel_before = ImageDisplayPanel("ORIGINAL INPUT")
        self.panel_after = ImageDisplayPanel("PROCESSED OUTPUT")

        display_layout.addWidget(self.panel_before, stretch=1)
        display_layout.addWidget(self.panel_after, stretch=1)

        main_layout.addLayout(display_layout, stretch=1)

        # ── 4. Quality Advisory Bar ──
        self.quality_bar = QualityIndicatorBar()
        main_layout.addWidget(self.quality_bar)

        # ── 5. Filter Chips & Quick Corrections ──
        ctrl_bar = QHBoxLayout()
        ctrl_bar.setSpacing(8)

        lbl_filters = QLabel("Print Filter:")
        lbl_filters.setStyleSheet("font-weight: 600; color: #66667A; font-size: 12px; background: transparent;")
        ctrl_bar.addWidget(lbl_filters)

        self.filter_group = QButtonGroup(self)
        self.filter_group.setExclusive(True)

        filters = [
            ("Original", EnhancementMode.ORIGINAL),
            ("Document Crisp", EnhancementMode.DOCUMENT_CRISP),
            ("Auto Levels", EnhancementMode.AUTO_LEVELS),
            ("High Contrast B&W", EnhancementMode.HIGH_CONTRAST_BW),
        ]

        for name, mode in filters:
            btn = QPushButton(name)
            btn.setProperty("class", "chip-filter")
            btn.setCheckable(True)
            if mode == EnhancementMode.DOCUMENT_CRISP:
                btn.setChecked(True)
            btn.clicked.connect(lambda checked, m=mode: self.on_enhancement_changed(m))
            self.filter_group.addButton(btn)
            ctrl_bar.addWidget(btn)

        ctrl_bar.addSpacing(20)

        # Separator
        sep = QFrame()
        sep.setFrameShape(QFrame.VLine)
        sep.setFixedSize(1, 24)
        sep.setStyleSheet("background-color: #2A2A32; border: none;")
        ctrl_bar.addWidget(sep)

        btn_edit_corners = QPushButton("✏ Edit Corners")
        btn_edit_corners.setFixedHeight(32)
        btn_edit_corners.clicked.connect(self.on_edit_corners)
        ctrl_bar.addWidget(btn_edit_corners)

        btn_rot_90 = QPushButton("↻ 90°")
        btn_rot_90.setFixedSize(50, 32)
        btn_rot_90.clicked.connect(lambda: self.on_rotate_relative(90))
        ctrl_bar.addWidget(btn_rot_90)

        btn_rot_180 = QPushButton("↻ 180°")
        btn_rot_180.setFixedSize(54, 32)
        btn_rot_180.clicked.connect(lambda: self.on_rotate_relative(180))
        ctrl_bar.addWidget(btn_rot_180)

        btn_rot_270 = QPushButton("↻ 270°")
        btn_rot_270.setFixedSize(54, 32)
        btn_rot_270.clicked.connect(lambda: self.on_rotate_relative(270))
        ctrl_bar.addWidget(btn_rot_270)

        btn_rot_reset = QPushButton("Reset")
        btn_rot_reset.setFixedHeight(32)
        btn_rot_reset.setProperty("class", "btn-ghost")
        btn_rot_reset.clicked.connect(self.on_reset_rotation)
        ctrl_bar.addWidget(btn_rot_reset)

        ctrl_bar.addStretch()
        main_layout.addLayout(ctrl_bar)

        # ── 6. Bottom Export Action Bar ──
        export_bar = QHBoxLayout()
        export_bar.setSpacing(10)

        export_bar.addStretch()

        self.btn_export_images = QPushButton("  Export Images (PNG/JPG)  ")
        self.btn_export_images.setFixedHeight(40)
        self.btn_export_images.clicked.connect(self.on_export_images)
        export_bar.addWidget(self.btn_export_images)

        self.btn_export_pdf = QPushButton("  Export PDF  ")
        self.btn_export_pdf.setFixedHeight(40)
        self.btn_export_pdf.clicked.connect(self.on_export_pdf)
        export_bar.addWidget(self.btn_export_pdf)

        self.btn_export_word = QPushButton("  Export to Word (.docx)  ")
        self.btn_export_word.setProperty("class", "btn-primary")
        self.btn_export_word.setFixedHeight(44)
        self.btn_export_word.clicked.connect(self.on_export_word)
        export_bar.addWidget(self.btn_export_word)

        main_layout.addLayout(export_bar)

        # ── Connect signals ──
        btn_back.clicked.connect(self.back_to_upload.emit)

    def refresh_view(self):
        """Refreshes the active preview."""
        if self.pipeline.mode == ProcessingMode.CARD:
            self.card_selector_widget.show()
            self.format_switcher_widget.show()
            self.sheet_carousel_widget.hide()
            has_back = self.pipeline.card_pair.back is not None
            self.btn_sel_back.setEnabled(has_back)
            if self.active_card_side == "back" and not has_back:
                self.active_card_side = "front"
            self.btn_sel_front.setChecked(self.active_card_side == "front")
            self.btn_sel_back.setChecked(self.active_card_side == "back")

            is_card = self.pipeline.active_card_profile.id == CARD_PROFILE.id
            self.btn_fmt_card.setChecked(is_card)
            self.btn_fmt_long.setChecked(not is_card)

        else:
            self.card_selector_widget.hide()
            self.format_switcher_widget.hide()
            self.mismatch_banner.hide()
            self.sheet_carousel_widget.show()
            total_pages = len(self.pipeline.sheet_queue.pages)
            if total_pages == 0:
                return
            self.active_sheet_index = max(0, min(self.active_sheet_index, total_pages - 1))
            self.lbl_page_counter.setText(f"Page {self.active_sheet_index + 1} of {total_pages}")
            self.btn_prev_page.setEnabled(self.active_sheet_index > 0)
            self.btn_next_page.setEnabled(self.active_sheet_index < total_pages - 1)

        self._update_current_display()

    def get_current_item(self) -> Optional[ProcessedImage]:
        if self.pipeline.mode == ProcessingMode.CARD:
            return self.pipeline.card_pair.front if self.active_card_side == "front" else self.pipeline.card_pair.back
        else:
            if 0 <= self.active_sheet_index < len(self.pipeline.sheet_queue.pages):
                return self.pipeline.sheet_queue.pages[self.active_sheet_index]
        return None

    def _update_current_display(self):
        item = self.get_current_item()
        if item is None:
            self.panel_before.set_image(None)
            self.panel_after.set_image(None)
            self.mismatch_banner.hide()
            return

        # 1. Before Image with 4-Corner Overlay
        before_overlay = item.original_image.copy()
        if item.current_corners is not None:
            pts = item.current_corners.to_numpy().astype(np.int32)
            cv2.polylines(before_overlay, [pts], True, (99, 102, 241), 3)
            for pt in pts:
                cv2.circle(before_overlay, (pt[0], pt[1]), 8, (255, 255, 255), -1)
                cv2.circle(before_overlay, (pt[0], pt[1]), 5, (99, 102, 241), -1)

        h_orig, w_orig = item.original_image.shape[:2]
        self.panel_before.set_image(before_overlay, f"Original Capture  •  {w_orig} × {h_orig} px")

        # 2. After Image
        final_img = item.final_image
        if final_img is not None:
            h_fin, w_fin = final_img.shape[:2]
            prof = item.format_profile
            profile_desc = f"{prof.name}  •  {prof.dimensions_mm_str} @ {prof.dpi} DPI  •  {w_fin} × {h_fin} px"
            rot_info = f"  •  Rotated {item.total_rotation_deg}°"
            self.panel_after.set_image(final_img, f"{profile_desc}{rot_info}")

        # 3. Quality Evaluation
        if item.quality_report is not None:
            qr = item.quality_report

            # Format Mismatch Banner
            if qr.format_mismatch and self.pipeline.mode == ProcessingMode.CARD:
                suggested_prof = ProfileRegistry.get_profile(qr.suggested_profile)
                self.lbl_mismatch_msg.setText(
                    f"Format mismatch: detected ratio ({qr.detected_aspect_ratio:.2f}:1) differs "
                    f"from active {item.format_profile.name} ({qr.expected_aspect_ratio:.2f}:1)."
                )
                self.btn_mismatch_switch.setText(f"Switch to {suggested_prof.name}")
                self.mismatch_banner.show()
            else:
                self.mismatch_banner.hide()

            # Status Badge
            if qr.format_mismatch:
                self.lbl_quality_badge.setText(f"● FORMAT REVIEW  ({qr.overall_confidence:.0%})")
                self.lbl_quality_badge.setProperty("class", "badge-review")
            elif qr.orientation_confidence < 0.60:
                self.lbl_quality_badge.setText(f"● ORIENTATION REVIEW  ({qr.overall_confidence:.0%})")
                self.lbl_quality_badge.setProperty("class", "badge-manual")
            elif qr.boundary_confidence < 0.45 or (qr.issues and "boundary" in " ".join(qr.issues).lower()):
                self.lbl_quality_badge.setText(f"● CORNER REVIEW  ({qr.overall_confidence:.0%})")
                self.lbl_quality_badge.setProperty("class", "badge-manual")
            elif qr.status_level == ConfidenceLevel.HIGH_CONFIDENCE:
                self.lbl_quality_badge.setText(f"● HIGH CONFIDENCE  ({qr.overall_confidence:.0%})")
                self.lbl_quality_badge.setProperty("class", "badge-high")
            elif qr.status_level == ConfidenceLevel.REVIEW_RECOMMENDED:
                self.lbl_quality_badge.setText(f"● REVIEW RECOMMENDED  ({qr.overall_confidence:.0%})")
                self.lbl_quality_badge.setProperty("class", "badge-review")
            else:
                self.lbl_quality_badge.setText(f"● MANUAL REVIEW REQUIRED  ({qr.overall_confidence:.0%})")
                self.lbl_quality_badge.setProperty("class", "badge-manual")

            self.lbl_quality_badge.style().polish(self.lbl_quality_badge)

            # Quality Bar
            issues_list = list(qr.issues)
            conf_str = (
                f"Boundary {qr.boundary_confidence:.0%}  •  "
                f"Corner {qr.corner_confidence:.0%}  •  "
                f"Format {qr.format_confidence:.0%}  •  "
                f"Orientation {qr.orientation_confidence:.0%}"
            )

            if qr.status_level == ConfidenceLevel.HIGH_CONFIDENCE:
                self.quality_bar.set_status("#10B981", f"{issues_list[0]}  |  {conf_str}")
            elif qr.status_level == ConfidenceLevel.REVIEW_RECOMMENDED:
                self.quality_bar.set_status("#F59E0B", f"{issues_list[0]}  |  {conf_str}")
            else:
                self.quality_bar.set_status("#EF4444", f"{issues_list[0]}  |  {conf_str}")

    def on_switch_profile(self, profile: FormatProfile):
        self.pipeline.set_card_profile(profile)
        self.refresh_view()

    def on_apply_suggested_profile(self):
        item = self.get_current_item()
        if item and item.quality_report and item.quality_report.suggested_profile:
            sug_prof = ProfileRegistry.get_profile(item.quality_report.suggested_profile)
            self.on_switch_profile(sug_prof)

    def set_active_card_side(self, side: str):
        self.active_card_side = side
        self.refresh_view()

    def on_prev_page(self):
        if self.active_sheet_index > 0:
            self.active_sheet_index -= 1
            self.refresh_view()

    def on_next_page(self):
        if self.active_sheet_index < len(self.pipeline.sheet_queue.pages) - 1:
            self.active_sheet_index += 1
            self.refresh_view()

    def on_enhancement_changed(self, mode: EnhancementMode):
        self.pipeline.set_global_enhancement(mode)
        self.refresh_view()

    def on_rotate_relative(self, angle: int):
        item = self.get_current_item()
        if item is not None:
            self.pipeline.rotate_item(item, angle)
            self.refresh_view()

    def on_reset_rotation(self):
        item = self.get_current_item()
        if item is not None:
            self.pipeline.set_item_rotation(item, 0)
            self.refresh_view()

    def on_edit_corners(self):
        item = self.get_current_item()
        if item is None:
            return

        dialog = CornerEditorDialog(item, self)
        if dialog.exec():
            new_corners = dialog.get_result_corners()
            self.pipeline.update_item_corners(item, new_corners)
            self.refresh_view()

    def on_export_word(self):
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Save Word Document", "Formatted_Print_Document.docx", "Word Documents (*.docx)"
        )
        if not file_path:
            return

        if self.pipeline.mode == ProcessingMode.CARD:
            success = DocxExporter.export_card_pair(self.pipeline.card_pair, file_path)
        else:
            success = DocxExporter.export_sheet_queue(self.pipeline.sheet_queue, file_path)

        if success:
            QMessageBox.information(
                self, "Export Successful",
                f"Word document exported successfully!\n\n{file_path}\n\nReady for printing with Ctrl+P."
            )
        else:
            QMessageBox.critical(self, "Export Failed", "Failed to export Word document.")

    def on_export_pdf(self):
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Save PDF Document", "Formatted_Document.pdf", "PDF Documents (*.pdf)"
        )
        if not file_path:
            return

        if self.pipeline.mode == ProcessingMode.CARD:
            success = PdfExporter.export_card_pair(self.pipeline.card_pair, file_path)
        else:
            success = PdfExporter.export_sheet_queue(self.pipeline.sheet_queue, file_path)

        if success:
            QMessageBox.information(self, "Export Successful", f"PDF exported to:\n{file_path}")
        else:
            QMessageBox.critical(self, "Export Failed", "Failed to export PDF.")

    def on_export_images(self):
        out_dir = QFileDialog.getExistingDirectory(self, "Select Output Directory")
        if not out_dir:
            return

        if self.pipeline.mode == ProcessingMode.CARD:
            paths = ImageExporter.export_card_pair(self.pipeline.card_pair, out_dir)
        else:
            paths = ImageExporter.export_sheet_queue(self.pipeline.sheet_queue, out_dir)

        if paths:
            QMessageBox.information(self, "Export Successful", f"Exported {len(paths)} image(s) to:\n{out_dir}")
        else:
            QMessageBox.critical(self, "Export Failed", "Failed to export images.")
