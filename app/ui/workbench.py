"""
Operator-Focused Workbench (Rock-solid Architecture).
Provides:
  - Multi-upload support: selecting or dropping multiple photos automatically assigns Front and Back.
  - Side-by-side comparison: ORIGINAL photograph on Left, NORMALIZED card on Right.
  - FRONT and BACK toggle pills with distinctive colors (Vibrant Blue for Front, Vibrant Purple for Back).
  - Optional Combined Sheet Preview toggle.
  - Full Microsoft Word (.docx) export support alongside PDF and PNG.
  - Safe, non-blocking CV processing with zero UI thread access in workers.
  - Seamless Card Mode and Document Mode integration.
"""
from pathlib import Path
from typing import List, Optional
import cv2
import numpy as np
from PySide6.QtCore import Qt, Signal, QThread, QObject, QSize
from PySide6.QtGui import QPixmap, QImage, QDragEnterEvent, QDropEvent, QColor
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QFrame,
    QFileDialog,
    QMessageBox,
    QScrollArea,
    QButtonGroup,
    QSizePolicy,
    QStackedWidget,
)

from app.core.config import AppPaths
from app.core.profiles import FormatProfile, CARD_PROFILE, LONG_FORM_PROFILE, ProfileRegistry
from app.core.models import ProcessingMode, ProcessedImage, ConfidenceLevel
from app.core.pipeline import FormatterPipeline
from app.core.print_layout import PrintLayoutEngine, CardOutputComposer
from app.export.docx_export import DocxExporter
from app.export.image_export import ImageExporter
from app.export.pdf_export import PdfExporter
from app.export.printing import PrintManager
from app.ui.corner_editor import CornerEditorDialog
from app.ui.document_mode.document_workflow import DocumentWorkflow
from app.utils.image_io import load_image_safe
from app.utils.logger import get_logger

logger = get_logger("workbench")


class ProcessingWorker(QObject):
    """Background worker for non-blocking CV processing of both card sides."""
    finished = Signal()
    error = Signal(str)

    def __init__(self, pipeline: FormatterPipeline, front: Optional[str], back: Optional[str],
                 profile: FormatProfile):
        super().__init__()
        self.pipeline = pipeline
        self.front = front
        self.back = back
        self.profile = profile

    def run(self):
        try:
            self.pipeline.set_card_images(self.front, self.back, profile=self.profile)
            self.finished.emit()
        except Exception as e:
            logger.error(f"Processing error: {e}", exc_info=True)
            self.error.emit(str(e))


class SlotImage(QWidget):
    """One clickable image slot (Front or Back) with drop & replace support."""
    files_dropped = Signal(list)

    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self.setFixedSize(300, 230)
        self.setAcceptDrops(True)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)

        lbl = QLabel(title)
        lbl.setStyleSheet("font-size: 13px; font-weight: 800; color: #F0F0F5;"
                          " letter-spacing: 0.5px; background: transparent;")
        lbl.setAlignment(Qt.AlignCenter)
        lay.addWidget(lbl)

        self.frame = QFrame()
        self.frame.setStyleSheet("""
            QFrame {
                background-color: #15151A;
                border: 2px dashed #3A3A46;
                border-radius: 12px;
            }
            QFrame:hover { border-color: #2563EB; background-color: #181822; }
        """)
        self.frame.setFixedSize(300, 180)
        inner = QVBoxLayout(self.frame)
        inner.setAlignment(Qt.AlignCenter)
        self.lbl_img = QLabel("Drop or Click to Browse")
        self.lbl_img.setStyleSheet("color: #66667A; font-size: 12px; background: transparent;")
        self.lbl_img.setAlignment(Qt.AlignCenter)
        inner.addWidget(self.lbl_img)
        lay.addWidget(self.frame)

    def set_image(self, bgr_img: Optional[np.ndarray]):
        if bgr_img is None:
            self.lbl_img.setText("Drop or Click to Browse")
            self.lbl_img.setPixmap(QPixmap())
            self.lbl_img.setStyleSheet("color: #66667A; font-size: 12px; background: transparent;")
            return
        rgb = cv2.cvtColor(bgr_img, cv2.COLOR_BGR2RGB)
        h, w = rgb.shape[:2]
        qimg = QImage(rgb.data, w, h, w * 3, QImage.Format_RGB888)
        pix = QPixmap.fromImage(qimg).scaled(
            286, 160, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.lbl_img.setPixmap(pix)
        self.lbl_img.setStyleSheet("background: transparent;")

    def set_file(self, path: str):
        img = load_image_safe(path)
        if img is not None:
            self.set_image(img)

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent):
        urls = event.mimeData().urls()
        exts = {".jpg", ".jpeg", ".png", ".webp"}
        files = [u.toLocalFile() for u in urls if Path(u.toLocalFile()).suffix.lower() in exts]
        if files:
            self.files_dropped.emit(files)
            event.acceptProposedAction()


class ImageComparisonCard(QFrame):
    """
    Displays either the Original Capture or the Formatted Card image
    with clean headers, dimension tags, and optional correction actions.
    """
    edit_corners_clicked = Signal()
    rotate_clicked = Signal(int)

    def __init__(self, badge_text: str, badge_color: str, is_editable: bool = False, parent=None):
        super().__init__(parent)
        self.badge_text = badge_text
        self.badge_color = badge_color
        self.is_editable = is_editable
        self._pixmap: Optional[QPixmap] = None
        self._init_ui()

    def _init_ui(self):
        self.setStyleSheet("""
            ImageComparisonCard {
                background-color: #14141A;
                border: 1px solid #24242E;
                border-radius: 12px;
            }
        """)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 12, 16, 14)
        lay.setSpacing(10)

        # Header: Badge label + Dimensions info
        head = QHBoxLayout()
        self.lbl_badge = QLabel(self.badge_text)
        self.lbl_badge.setStyleSheet(f"font-size: 13px; font-weight: 800; color: {self.badge_color};"
                                     " letter-spacing: 0.5px; background: transparent;")
        head.addWidget(self.lbl_badge)
        head.addStretch()

        self.lbl_dims = QLabel("—")
        self.lbl_dims.setStyleSheet("font-size: 11px; color: #94A3B8; font-weight: 600; background: transparent;")
        head.addWidget(self.lbl_dims)
        lay.addLayout(head)

        # Image display container
        self.img_frame = QFrame()
        self.img_frame.setStyleSheet("""
            background-color: #0A0A0E;
            border: 1px solid #1E1E26;
            border-radius: 8px;
        """)
        self.img_frame.setFixedHeight(230)
        img_lay = QVBoxLayout(self.img_frame)
        img_lay.setContentsMargins(8, 8, 8, 8)
        img_lay.setAlignment(Qt.AlignCenter)

        self.lbl_img = QLabel("No image loaded")
        self.lbl_img.setAlignment(Qt.AlignCenter)
        self.lbl_img.setStyleSheet("color: #64748B; font-size: 12px; background: transparent;")
        img_lay.addWidget(self.lbl_img)
        lay.addWidget(self.img_frame)

        # Actions Row (for Formatted card)
        act_row = QHBoxLayout()
        act_row.setSpacing(8)

        if self.is_editable:
            self.btn_edit = QPushButton("✏  Edit Corners")
            self.btn_edit.setFixedHeight(34)
            self.btn_edit.setCursor(Qt.PointingHandCursor)
            self.btn_edit.setStyleSheet("""
                QPushButton {
                    background-color: #1E293B;
                    color: #CBD5E1;
                    border: 1px solid #334155;
                    border-radius: 6px;
                    font-size: 12px;
                    font-weight: 700;
                    padding: 0 12px;
                }
                QPushButton:hover {
                    background-color: #2563EB;
                    color: #FFFFFF;
                    border-color: #3B82F6;
                }
                QPushButton:disabled {
                    background-color: #14141A;
                    color: #475569;
                    border-color: #1E1E26;
                }
            """)
            self.btn_edit.setEnabled(False)
            self.btn_edit.clicked.connect(self.edit_corners_clicked.emit)
            act_row.addWidget(self.btn_edit, stretch=1)

            self.btn_rot_left = QPushButton("↶ 90°")
            self.btn_rot_left.setFixedSize(54, 34)
            self.btn_rot_left.setCursor(Qt.PointingHandCursor)
            self.btn_rot_left.setStyleSheet("""
                QPushButton {
                    background-color: #1E293B;
                    color: #94A3B8;
                    border: 1px solid #334155;
                    border-radius: 6px;
                    font-size: 12px;
                    font-weight: 700;
                }
                QPushButton:hover { color: #FFFFFF; background-color: #334155; }
                QPushButton:disabled { color: #475569; border-color: #1E1E26; }
            """)
            self.btn_rot_left.setEnabled(False)
            self.btn_rot_left.clicked.connect(lambda: self.rotate_clicked.emit(270))
            act_row.addWidget(self.btn_rot_left)

            self.btn_rot_right = QPushButton("↷ 90°")
            self.btn_rot_right.setFixedSize(54, 34)
            self.btn_rot_right.setCursor(Qt.PointingHandCursor)
            self.btn_rot_right.setStyleSheet("""
                QPushButton {
                    background-color: #1E293B;
                    color: #94A3B8;
                    border: 1px solid #334155;
                    border-radius: 6px;
                    font-size: 12px;
                    font-weight: 700;
                }
                QPushButton:hover { color: #FFFFFF; background-color: #334155; }
                QPushButton:disabled { color: #475569; border-color: #1E1E26; }
            """)
            self.btn_rot_right.setEnabled(False)
            self.btn_rot_right.clicked.connect(lambda: self.rotate_clicked.emit(90))
            act_row.addWidget(self.btn_rot_right)
        else:
            # Placeholder label for Original photo
            lbl_desc = QLabel("Raw camera capture prior to perspective warping")
            lbl_desc.setStyleSheet("font-size: 11px; color: #64748B; font-weight: 600; background: transparent;")
            lbl_desc.setFixedHeight(34)
            lbl_desc.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)
            act_row.addWidget(lbl_desc)

        lay.addLayout(act_row)

    def set_badge_text(self, text: str, color: Optional[str] = None):
        self.lbl_badge.setText(text)
        if color:
            self.badge_color = color
            self.lbl_badge.setStyleSheet(f"font-size: 13px; font-weight: 800; color: {color};"
                                         " letter-spacing: 0.5px; background: transparent;")

    def set_image(self, bgr_img: Optional[np.ndarray], dims_text: str = "", empty_msg: str = "No image loaded"):
        if bgr_img is None:
            self._pixmap = None
            self.lbl_img.setPixmap(QPixmap())
            self.lbl_img.setText(empty_msg)
            self.lbl_dims.setText("—")
            if self.is_editable:
                self.btn_edit.setEnabled(False)
                self.btn_rot_left.setEnabled(False)
                self.btn_rot_right.setEnabled(False)
            return

        rgb = cv2.cvtColor(bgr_img, cv2.COLOR_BGR2RGB)
        h, w = rgb.shape[:2]
        qimg = QImage(rgb.data, w, h, w * 3, QImage.Format_RGB888)
        self._pixmap = QPixmap.fromImage(qimg)
        self.lbl_dims.setText(dims_text or f"{w} × {h} px")
        if self.is_editable:
            self.btn_edit.setEnabled(True)
            self.btn_rot_left.setEnabled(True)
            self.btn_rot_right.setEnabled(True)

        scaled = self._pixmap.scaled(
            max(50, self.img_frame.width() - 20),
            max(50, self.img_frame.height() - 20),
            Qt.KeepAspectRatio, Qt.SmoothTransformation
        )
        self.lbl_img.setPixmap(scaled)
        self.lbl_img.setText("")

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._pixmap is not None:
            scaled = self._pixmap.scaled(
                max(50, self.img_frame.width() - 20),
                max(50, self.img_frame.height() - 20),
                Qt.KeepAspectRatio, Qt.SmoothTransformation
            )
            self.lbl_img.setPixmap(scaled)


class PrintPreviewWidget(QScrollArea):
    """Renders the combined full-sheet printable layout with zoom/fit controls."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setStyleSheet("QScrollArea { background: #0A0A0E; border: 1px solid #1E1E26; border-radius: 8px; }")

        self.container = QWidget()
        self.container.setStyleSheet("background: #0A0A0E;")
        self.lay = QVBoxLayout(self.container)
        self.lay.setAlignment(Qt.AlignCenter)

        self.lbl_preview = QLabel()
        self.lbl_preview.setAlignment(Qt.AlignCenter)
        self.lbl_preview.setStyleSheet("background: transparent;")
        self.lay.addWidget(self.lbl_preview)
        self.setWidget(self.container)

        self._preview_pixmap: Optional[QPixmap] = None
        self._zoom = 1.0

    def set_rendered(self, bgr_img: Optional[np.ndarray], page_mm=None):
        if bgr_img is None:
            self._preview_pixmap = None
            self.lbl_preview.setPixmap(QPixmap())
            self.lbl_preview.setText("No layout generated yet")
            self.lbl_preview.setStyleSheet("color: #64748B; font-size: 12px; background: transparent;")
            return
        rgb = cv2.cvtColor(bgr_img, cv2.COLOR_BGR2RGB)
        h, w = rgb.shape[:2]
        qimg = QImage(rgb.data, w, h, w * 3, QImage.Format_RGB888)
        self._preview_pixmap = QPixmap.fromImage(qimg)
        self.lbl_preview.setText("")
        self._apply_zoom()

    def _apply_zoom(self):
        if self._preview_pixmap is None:
            return
        base_w = self._preview_pixmap.width()
        base_h = self._preview_pixmap.height()
        bw = max(1, int(base_w * self._zoom))
        bh = max(1, int(base_h * self._zoom))
        self.lbl_preview.setPixmap(
            self._preview_pixmap.scaled(bw, bh, Qt.KeepAspectRatio, Qt.SmoothTransformation))

    def zoom_in(self):
        self._zoom = min(3.0, self._zoom + 0.25)
        self._apply_zoom()

    def zoom_out(self):
        self._zoom = max(0.25, self._zoom - 0.25)
        self._apply_zoom()

    def fit(self):
        self._zoom = 1.0
        self._apply_zoom()


class WorkbenchView(QWidget):
    """
    Primary Operator Workbench.
    Features:
      - Automatic multi-upload for 2 files into Front and Back.
      - Side-by-side comparison: ORIGINAL photograph vs NORMALIZED card.
      - Front/Back toggle pills with distinct colors (Blue for Front, Purple for Back).
      - Full Word (.docx) export support alongside PDF and PNG.
      - Combined Sheet view toggle.
      - Safe, rock-solid processing and direct printing.
    """

    def __init__(self, pipeline: FormatterPipeline, parent=None):
        super().__init__(parent)
        self.pipeline = pipeline
        self.front_path: Optional[str] = None
        self.back_path: Optional[str] = None
        self.thread: Optional[QThread] = None
        self.worker: Optional[ProcessingWorker] = None
        self.copies: int = 1
        self.single_page: bool = False
        self.active_preview_side = "front"

        self.setAcceptDrops(True)
        self.layout_engine = PrintLayoutEngine()
        self.setup_ui()

    # ── UI construction ────────────────────────────────────────────
    def setup_ui(self):
        root_lay = QVBoxLayout(self)
        root_lay.setContentsMargins(0, 0, 0, 0)
        root_lay.setSpacing(0)

        # Header Bar with Logo and Mode Toggle
        header = QFrame()
        header.setFixedHeight(64)
        header.setStyleSheet("background-color: #0F0F14; border-bottom: 1px solid #1E1E26;")
        head_lay = QHBoxLayout(header)
        head_lay.setContentsMargins(28, 0, 28, 0)
        head_lay.setSpacing(16)

        # Logo
        if AppPaths.LOGO_LIGHT.exists():
            logo_container = QFrame()
            logo_container.setStyleSheet("background-color: #FFFFFF; border-radius: 6px; padding: 2px;")
            logo_container.setFixedHeight(32)
            lc_lay = QHBoxLayout(logo_container)
            lc_lay.setContentsMargins(6, 2, 6, 2)
            lbl_logo = QLabel()
            pix = QPixmap(str(AppPaths.LOGO_LIGHT))
            lbl_logo.setPixmap(pix.scaledToHeight(22, Qt.SmoothTransformation))
            lc_lay.addWidget(lbl_logo)
            head_lay.addWidget(logo_container)

        title = QLabel("QenBel Smart Formatter")
        title.setStyleSheet("font-size: 16px; font-weight: 800; color: #FFFFFF; background: transparent;")
        head_lay.addWidget(title)

        head_lay.addSpacing(20)

        # Mode Toggle Pills (CARD / DOCUMENT)
        mode_frame = QFrame()
        mode_frame.setStyleSheet("background-color: #14141A; border: 1px solid #24242E; border-radius: 20px;")
        mode_frame.setFixedHeight(40)
        mf_layout = QHBoxLayout(mode_frame)
        mf_layout.setContentsMargins(4, 3, 4, 3)
        mf_layout.setSpacing(4)

        self.btn_card_mode = QPushButton("CARD MODE")
        self.btn_card_mode.setCheckable(True)
        self.btn_card_mode.setChecked(True)
        self.btn_card_mode.setCursor(Qt.PointingHandCursor)
        self.btn_card_mode.setFixedHeight(32)

        self.btn_doc_mode = QPushButton("DOCUMENT MODE")
        self.btn_doc_mode.setCheckable(True)
        self.btn_doc_mode.setCursor(Qt.PointingHandCursor)
        self.btn_doc_mode.setFixedHeight(32)

        pill_style = """
            QPushButton {
                background-color: transparent;
                color: #94A3B8;
                border: none;
                border-radius: 16px;
                font-size: 12px;
                font-weight: 700;
                padding: 0 16px;
            }
            QPushButton:hover { color: #FFFFFF; }
            QPushButton:checked { background-color: #2563EB; color: #FFFFFF; }
        """
        self.btn_card_mode.setStyleSheet(pill_style)
        self.btn_doc_mode.setStyleSheet(pill_style)

        group = QButtonGroup(self)
        group.setExclusive(True)
        group.addButton(self.btn_card_mode)
        group.addButton(self.btn_doc_mode)
        mf_layout.addWidget(self.btn_card_mode)
        mf_layout.addWidget(self.btn_doc_mode)
        head_lay.addWidget(mode_frame)

        self.btn_card_mode.clicked.connect(lambda: self.on_mode(ProcessingMode.CARD))
        self.btn_doc_mode.clicked.connect(lambda: self.on_mode(ProcessingMode.SHEET))

        head_lay.addStretch()

        # Status chip (Ready to Print / Review Required)
        self.btn_status = QPushButton()
        self.btn_status.setEnabled(True)
        self.btn_status.setCursor(Qt.PointingHandCursor)
        head_lay.addWidget(self.btn_status)
        self._set_status("idle", "No card loaded")
        self.btn_status.clicked.connect(self.on_status_clicked)

        root_lay.addWidget(header)

        # Mode Stack Widget
        self.mode_stack = QStackedWidget()

        # ── View 0: Card Mode Workbench ──
        card_widget = QWidget()
        main = QVBoxLayout(card_widget)
        main.setContentsMargins(28, 16, 28, 20)
        main.setSpacing(14)

        # ── Card Input panel ──
        input_panel = QFrame()
        input_panel.setStyleSheet("""
            QFrame {
                background-color: #101014;
                border: 1px solid #1E1E26;
                border-radius: 12px;
            }
        """)
        input_lay = QVBoxLayout(input_panel)
        input_lay.setContentsMargins(20, 14, 20, 16)
        input_lay.setSpacing(12)

        input_head = QHBoxLayout()
        in_title = QLabel("CARD INPUT")
        in_title.setStyleSheet("font-size: 13px; font-weight: 800; color: #9A9AAA;"
                               " letter-spacing: 1px; background: transparent;")
        input_head.addWidget(in_title)
        input_head.addStretch()

        lbl_hint = QLabel("Select or drop 2 images to automatically populate Front & Back")
        lbl_hint.setStyleSheet("font-size: 12px; color: #64748B; background: transparent;")
        input_head.addWidget(lbl_hint)
        input_lay.addLayout(input_head)

        # Slots row with Swap button in center
        slots_row = QHBoxLayout()
        slots_row.setAlignment(Qt.AlignCenter)
        slots_row.setSpacing(20)

        self.slot_front = SlotImage("FRONT")
        self.slot_back = SlotImage("BACK")
        self.slot_front.frame.mousePressEvent = lambda e: self.on_slot_clicked("front")
        self.slot_back.frame.mousePressEvent = lambda e: self.on_slot_clicked("back")
        self.slot_front.files_dropped.connect(self.assign_files)
        self.slot_back.files_dropped.connect(self.assign_files)

        slots_row.addWidget(self.slot_front)

        # Swap button in the center
        self.btn_swap_input = QPushButton("⇄\nSwap")
        self.btn_swap_input.setToolTip("Swap Front and Back photographs")
        self.btn_swap_input.setFixedSize(60, 50)
        self.btn_swap_input.setCursor(Qt.PointingHandCursor)
        self.btn_swap_input.setStyleSheet("""
            QPushButton {
                background-color: #1E293B;
                color: #38BDF8;
                border: 1px solid #334155;
                border-radius: 8px;
                font-size: 12px;
                font-weight: 800;
            }
            QPushButton:hover {
                background-color: #2563EB;
                color: #FFFFFF;
                border-color: #3B82F6;
            }
        """)
        self.btn_swap_input.clicked.connect(self.on_swap_inputs)
        slots_row.addWidget(self.btn_swap_input)

        slots_row.addWidget(self.slot_back)
        input_lay.addLayout(slots_row)

        input_actions = QHBoxLayout()
        input_actions.setAlignment(Qt.AlignCenter)
        input_actions.setSpacing(14)

        self.btn_select = QPushButton("  Select Images (Front & Back)  ")
        self.btn_select.setFixedHeight(44)
        self.btn_select.setMinimumWidth(240)
        self.btn_select.setCursor(Qt.PointingHandCursor)
        self.btn_select.setStyleSheet("""
            QPushButton {
                background-color: #1E293B;
                color: #FFFFFF;
                border: 1px solid #334155;
                border-radius: 8px;
                font-size: 13px;
                font-weight: 700;
            }
            QPushButton:hover {
                background-color: #334155;
                border-color: #475569;
            }
        """)
        self.btn_select.clicked.connect(self.on_select_images)
        input_actions.addWidget(self.btn_select)

        self.btn_process = QPushButton("  PROCESS  ")
        self.btn_process.setFixedHeight(46)
        self.btn_process.setMinimumWidth(220)
        self.btn_process.setCursor(Qt.PointingHandCursor)
        self.btn_process.setStyleSheet("""
            QPushButton {
                background-color: #2563EB;
                color: #FFFFFF;
                border: none;
                border-radius: 8px;
                font-size: 14px;
                font-weight: 800;
                letter-spacing: 0.5px;
            }
            QPushButton:hover { background-color: #1D4ED8; }
            QPushButton:disabled { background-color: #1E293B; color: #475569; }
        """)
        self.btn_process.setEnabled(False)
        self.btn_process.clicked.connect(self.on_process)
        input_actions.addWidget(self.btn_process)
        input_lay.addLayout(input_actions)

        main.addWidget(input_panel)

        # ── PRINT PREVIEW PANEL (ORIGINAL VS FORMATTED SIDE-BY-SIDE + FRONT/BACK TOGGLE) ──
        preview_panel = QFrame()
        preview_panel.setStyleSheet("""
            QFrame {
                background-color: #101014;
                border: 1px solid #1E1E26;
                border-radius: 12px;
            }
        """)
        preview_lay = QVBoxLayout(preview_panel)
        preview_lay.setContentsMargins(20, 14, 20, 16)
        preview_lay.setSpacing(12)

        # Preview Header: Title + Distinct Front/Back Toggle Pills + Combined Toggle
        preview_head = QHBoxLayout()
        preview_head.setSpacing(12)
        p_title = QLabel("PRINT PREVIEW")
        p_title.setStyleSheet("font-size: 13px; font-weight: 800; color: #9A9AAA;"
                              " letter-spacing: 1px; background: transparent;")
        preview_head.addWidget(p_title)
        preview_head.addSpacing(14)

        # Front / Back Toggle Pills with DISTINCT Colors
        side_toggle_frame = QFrame()
        side_toggle_frame.setStyleSheet("background-color: #14141A; border: 1px solid #24242E; border-radius: 8px;")
        side_toggle_frame.setFixedHeight(36)
        stf_lay = QHBoxLayout(side_toggle_frame)
        stf_lay.setContentsMargins(3, 3, 3, 3)
        stf_lay.setSpacing(6)

        # Front button: Vibrant Royal Blue / Cyan theme
        self.btn_side_front = QPushButton("● FRONT SIDE")
        self.btn_side_front.setCheckable(True)
        self.btn_side_front.setChecked(True)
        self.btn_side_front.setCursor(Qt.PointingHandCursor)
        self.btn_side_front.setFixedHeight(28)
        self.btn_side_front.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                color: #94A3B8;
                border: none;
                border-radius: 6px;
                font-size: 11px;
                font-weight: 800;
                padding: 0 14px;
            }
            QPushButton:hover { color: #38BDF8; }
            QPushButton:checked {
                background-color: #2563EB;
                color: #FFFFFF;
                border: 1px solid #38BDF8;
            }
        """)

        # Back button: Vibrant Purple / Violet theme (Different Color)
        self.btn_side_back = QPushButton("● BACK SIDE")
        self.btn_side_back.setCheckable(True)
        self.btn_side_back.setChecked(False)
        self.btn_side_back.setCursor(Qt.PointingHandCursor)
        self.btn_side_back.setFixedHeight(28)
        self.btn_side_back.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                color: #94A3B8;
                border: none;
                border-radius: 6px;
                font-size: 11px;
                font-weight: 800;
                padding: 0 14px;
            }
            QPushButton:hover { color: #C084FC; }
            QPushButton:checked {
                background-color: #7C3AED;
                color: #FFFFFF;
                border: 1px solid #C084FC;
            }
        """)

        self.side_button_group = QButtonGroup(self)
        self.side_button_group.setExclusive(True)
        self.side_button_group.addButton(self.btn_side_front)
        self.side_button_group.addButton(self.btn_side_back)
        stf_lay.addWidget(self.btn_side_front)
        stf_lay.addWidget(self.btn_side_back)
        preview_head.addWidget(side_toggle_frame)

        self.btn_side_front.clicked.connect(lambda: self.on_select_preview_side("front"))
        self.btn_side_back.clicked.connect(lambda: self.on_select_preview_side("back"))

        preview_head.addSpacing(10)

        # View mode toggle: Side-by-Side (Original vs Formatted) vs Combined Sheet
        self.btn_view_comparison = QPushButton("Side-by-Side View")
        self.btn_view_comparison.setCheckable(True)
        self.btn_view_comparison.setChecked(True)
        self.btn_view_comparison.setCursor(Qt.PointingHandCursor)
        self.btn_view_comparison.setFixedHeight(32)

        self.btn_view_combined = QPushButton("Combined Sheet")
        self.btn_view_combined.setCheckable(True)
        self.btn_view_combined.setCursor(Qt.PointingHandCursor)
        self.btn_view_combined.setFixedHeight(32)

        view_toggle_style = """
            QPushButton {
                background-color: #1E293B;
                color: #94A3B8;
                border: 1px solid #334155;
                border-radius: 6px;
                font-size: 11px;
                font-weight: 700;
                padding: 0 12px;
            }
            QPushButton:hover { color: #FFFFFF; }
            QPushButton:checked {
                background-color: #1E40AF;
                color: #FFFFFF;
                border-color: #3B82F6;
            }
        """
        self.btn_view_comparison.setStyleSheet(view_toggle_style)
        self.btn_view_combined.setStyleSheet(view_toggle_style)

        view_group = QButtonGroup(self)
        view_group.setExclusive(True)
        view_group.addButton(self.btn_view_comparison)
        view_group.addButton(self.btn_view_combined)
        preview_head.addWidget(self.btn_view_comparison)
        preview_head.addWidget(self.btn_view_combined)

        self.btn_view_comparison.clicked.connect(lambda: self.preview_stack.setCurrentIndex(0))
        self.btn_view_combined.clicked.connect(lambda: self.preview_stack.setCurrentIndex(1))

        preview_head.addStretch()

        self.lbl_page_info = QLabel("—")
        self.lbl_page_info.setStyleSheet("font-size: 11px; color: #94A3B8; font-weight: 600; background: transparent;")
        preview_head.addWidget(self.lbl_page_info)

        preview_lay.addLayout(preview_head)

        # Stacked Preview: Index 0 = Side-by-Side Comparison, Index 1 = Combined Sheet
        self.preview_stack = QStackedWidget()

        # ── Index 0: Original Photo (Left) vs Formatted Card (Right) ──
        comparison_widget = QWidget()
        comp_lay = QHBoxLayout(comparison_widget)
        comp_lay.setContentsMargins(0, 0, 0, 0)
        comp_lay.setSpacing(16)

        # Left: Original Photograph Card
        self.card_original = ImageComparisonCard(
            badge_text="ORIGINAL CAPTURE (FRONT)",
            badge_color="#94A3B8",
            is_editable=False
        )

        # Right: Formatted / Normalized Card (Editable with corners and rotation)
        self.card_formatted = ImageComparisonCard(
            badge_text="FORMATTED & PRINT-READY (FRONT)",
            badge_color="#38BDF8",
            is_editable=True
        )
        self.card_formatted.edit_corners_clicked.connect(self.on_edit_active_corners)
        self.card_formatted.rotate_clicked.connect(self.on_rotate_active_side)

        comp_lay.addWidget(self.card_original, stretch=1)
        comp_lay.addWidget(self.card_formatted, stretch=1)
        self.preview_stack.addWidget(comparison_widget)

        # ── Index 1: Combined Sheet Preview ──
        self.combined_preview = PrintPreviewWidget()
        self.combined_preview.setFixedHeight(310)
        self.preview_stack.addWidget(self.combined_preview)

        preview_lay.addWidget(self.preview_stack)

        # Profile + copies row
        opts = QHBoxLayout()
        opts.setSpacing(12)

        lblp = QLabel("Profile:")
        lblp.setStyleSheet("font-weight: 700; color: #94A3B8; font-size: 12px; background: transparent;")
        opts.addWidget(lblp)

        self.profile_combo_group = QButtonGroup(self)
        self.profile_combo_group.setExclusive(True)

        self.btn_prof_card = QPushButton("Card (86×54 mm)")
        self.btn_prof_card.setCheckable(True)
        self.btn_prof_card.setChecked(True)
        self.btn_prof_card.setFixedHeight(34)
        self.btn_prof_card.setStyleSheet(view_toggle_style)
        self.btn_prof_card.clicked.connect(lambda: self.on_change_profile(CARD_PROFILE))
        self.profile_combo_group.addButton(self.btn_prof_card)
        opts.addWidget(self.btn_prof_card)

        self.btn_prof_long = QPushButton("Long Form (210×85 mm)")
        self.btn_prof_long.setCheckable(True)
        self.btn_prof_long.setFixedHeight(34)
        self.btn_prof_long.setStyleSheet(view_toggle_style)
        self.btn_prof_long.clicked.connect(lambda: self.on_change_profile(LONG_FORM_PROFILE))
        self.profile_combo_group.addButton(self.btn_prof_long)
        opts.addWidget(self.btn_prof_long)

        opts.addSpacing(24)

        lblc = QLabel("Copies:")
        lblc.setStyleSheet("font-weight: 700; color: #94A3B8; font-size: 12px; background: transparent;")
        opts.addWidget(lblc)

        btn_cm = QPushButton("－")
        btn_cm.setFixedSize(30, 30)
        btn_cm.setStyleSheet("QPushButton { background-color: #1E293B; color: #FFF; border: 1px solid #334155; border-radius: 6px; font-weight: 800; }")
        btn_cm.clicked.connect(self.on_copies_minus)
        opts.addWidget(btn_cm)

        self.lbl_copies = QLabel(str(self.copies))
        self.lbl_copies.setStyleSheet("font-weight: 800; color: #FFFFFF; font-size: 14px; background: transparent;")
        self.lbl_copies.setFixedWidth(24)
        self.lbl_copies.setAlignment(Qt.AlignCenter)
        opts.addWidget(self.lbl_copies)

        btn_cp = QPushButton("＋")
        btn_cp.setFixedSize(30, 30)
        btn_cp.setStyleSheet("QPushButton { background-color: #1E293B; color: #FFF; border: 1px solid #334155; border-radius: 6px; font-weight: 800; }")
        btn_cp.clicked.connect(self.on_copies_plus)
        opts.addWidget(btn_cp)

        opts.addStretch()
        preview_lay.addLayout(opts)

        main.addWidget(preview_panel)

        # ── Single Output Action: Export as Word (.docx) ──
        actions = QHBoxLayout()
        actions.setSpacing(16)

        self.btn_export_docx = QPushButton("  📄   Export as Word (.docx)  ")
        self.btn_export_docx.setFixedHeight(50)
        self.btn_export_docx.setMinimumWidth(220)
        self.btn_export_docx.setCursor(Qt.PointingHandCursor)
        self.btn_export_docx.setStyleSheet("""
            QPushButton {
                background-color: #185ABD;
                color: #FFFFFF;
                border: none;
                border-radius: 10px;
                font-size: 14px;
                font-weight: 800;
                letter-spacing: 0.3px;
                padding: 0 24px;
            }
            QPushButton:hover { background-color: #10458C; }
            QPushButton:disabled { background-color: #1E293B; color: #475569; }
        """)
        self.btn_export_docx.setEnabled(False)
        self.btn_export_docx.clicked.connect(self.on_export_docx)
        actions.addWidget(self.btn_export_docx)

        # Placeholders for compatibility if referenced
        self.btn_print = QPushButton()
        self.btn_print.hide()
        self.btn_export_pdf = QPushButton()
        self.btn_export_pdf.hide()
        self.btn_export_img = QPushButton()
        self.btn_export_img.hide()

        actions.addStretch()

        # Reset button
        btn_reset = QPushButton("Clear / Reset")
        btn_reset.setFixedHeight(46)
        btn_reset.setCursor(Qt.PointingHandCursor)
        btn_reset.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                color: #EF4444;
                border: 1px solid #7F1D1D;
                border-radius: 8px;
                font-size: 12px;
                font-weight: 700;
                padding: 0 16px;
            }
            QPushButton:hover { background-color: rgba(239, 68, 68, 0.1); }
        """)
        btn_reset.clicked.connect(self.on_reset)
        actions.addWidget(btn_reset)

        main.addLayout(actions)

        # Add Views to Mode Stack
        self.mode_stack.addWidget(card_widget)  # Index 0: Card Mode

        # Index 1: Document Mode
        self.doc_view = DocumentWorkflow(self.pipeline, self)
        self.mode_stack.addWidget(self.doc_view)

        root_lay.addWidget(self.mode_stack)

    # ── Mode switching ─────────────────────────────────────────────
    def on_mode(self, mode: ProcessingMode):
        self.pipeline.set_mode(mode)
        if mode == ProcessingMode.CARD:
            self.mode_stack.setCurrentIndex(0)
            self.btn_card_mode.setChecked(True)
            self.btn_doc_mode.setChecked(False)
        else:
            self.mode_stack.setCurrentIndex(1)
            self.btn_card_mode.setChecked(False)
            self.btn_doc_mode.setChecked(True)

    # ── Drag & drop multi-upload ───────────────────────────────────
    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent):
        urls = event.mimeData().urls()
        exts = {".jpg", ".jpeg", ".png", ".webp"}
        files = [u.toLocalFile() for u in urls if Path(u.toLocalFile()).suffix.lower() in exts]
        if files:
            self.assign_files(files)
            event.acceptProposedAction()

    def assign_files(self, files: List[str]):
        """
        Auto-assign dropped or selected files to front/back.
        Supports multi-upload: 2 files automatically populate Front and Back.
        """
        if not files:
            return
        if len(files) >= 2:
            self.front_path = files[0]
            self.back_path = files[1]
        elif len(files) == 1:
            if not self.front_path:
                self.front_path = files[0]
            elif not self.back_path:
                self.back_path = files[0]
            else:
                self.front_path = files[0]

        self._refresh_slots()
        self._update_ready()

    def on_slot_clicked(self, side: str):
        files, _ = QFileDialog.getOpenFileNames(
            self, f"Select Card Images", "",
            "Image Files (*.jpg *.jpeg *.png *.webp)")
        if files:
            if len(files) >= 2:
                self.front_path = files[0]
                self.back_path = files[1]
            elif len(files) == 1:
                if side == "front":
                    self.front_path = files[0]
                else:
                    self.back_path = files[0]
            self._refresh_slots()
            self._update_ready()

    def on_select_images(self):
        files, _ = QFileDialog.getOpenFileNames(
            self, "Select Card Images (Front & Back)", "",
            "Image Files (*.jpg *.jpeg *.png *.webp)")
        if files:
            self.assign_files(files)

    def on_swap_inputs(self):
        self.front_path, self.back_path = self.back_path, self.front_path
        self._refresh_slots()
        if self.pipeline.card_entry and not self.pipeline.card_entry.is_empty():
            self.pipeline.card_entry.swap_sides()
            self.pipeline.card_pair.swap_sides()
            self._update_preview()
            self._update_status()

    def _refresh_slots(self):
        if self.front_path:
            self.slot_front.set_file(self.front_path)
        else:
            self.slot_front.set_image(None)
        if self.back_path:
            self.slot_back.set_file(self.back_path)
        else:
            self.slot_back.set_image(None)

    def _update_ready(self):
        has_front = self.front_path is not None
        has_back = self.back_path is not None
        self.btn_process.setEnabled(has_front or has_back)
        has_output = self.pipeline.card_entry is not None and (
            self.pipeline.card_entry.front is not None or self.pipeline.card_entry.back is not None)
        if not has_output:
            self.btn_print.setEnabled(False)
            self.btn_export_docx.setEnabled(False)
            self.btn_export_img.setEnabled(False)
            self.btn_export_pdf.setEnabled(False)

    # ── Safe Processing without Crashing ───────────────────────────
    def on_process(self):
        if self.front_path is None and self.back_path is None:
            return
        self.btn_process.setEnabled(False)
        self.btn_process.setText("Processing…")

        self.thread = QThread()
        self.worker = ProcessingWorker(self.pipeline, self.front_path, self.back_path,
                                       self.pipeline.active_card_profile)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.finished.connect(self.on_worker_finished)
        self.worker.error.connect(self.on_worker_error)
        self.thread.start()

    def on_worker_finished(self):
        if self.thread:
            self.thread.quit()
        self.btn_process.setEnabled(True)
        self.btn_process.setText("  PROCESS  ")
        self._update_preview()
        self._update_status()
        self.btn_print.setEnabled(True)
        self.btn_export_docx.setEnabled(True)
        self.btn_export_img.setEnabled(True)
        self.btn_export_pdf.setEnabled(True)

    def on_worker_error(self, msg: str):
        if self.thread:
            self.thread.quit()
        self.btn_process.setEnabled(True)
        self.btn_process.setText("  PROCESS  ")
        QMessageBox.critical(
            self, "Processing Failed",
            f"Card boundary could not be detected:\n{msg}\nPlease replace the images or adjust corners.",
            QMessageBox.Ok)

    # ── Preview Navigation & Update (ORIGINAL VS FORMATTED SIDE-BY-SIDE) ──
    def on_select_preview_side(self, side: str):
        self.active_preview_side = side
        if side == "front":
            self.btn_side_front.setChecked(True)
            self.btn_side_back.setChecked(False)
        else:
            self.btn_side_front.setChecked(False)
            self.btn_side_back.setChecked(True)
        self._update_preview()

    def _update_preview(self):
        entry = self.pipeline.card_entry
        if entry is None or entry.is_empty():
            self.card_original.set_image(None)
            self.card_formatted.set_image(None)
            self.combined_preview.set_rendered(None)
            self.lbl_page_info.setText("—")
            return

        profile = entry.format_profile or self.pipeline.active_card_profile
        dims_str = f"{profile.width_mm:.0f} × {profile.height_mm:.0f} mm @ {profile.dpi} DPI"

        side_name = self.active_preview_side.upper()
        active_color = "#38BDF8" if self.active_preview_side == "front" else "#C084FC"

        # Update card badge headers
        self.card_original.set_badge_text(f"ORIGINAL CAPTURE ({side_name})", "#94A3B8")
        self.card_formatted.set_badge_text(f"FORMATTED & PRINT-READY ({side_name})", active_color)

        # Get active side processed data
        active_item = entry.front if self.active_preview_side == "front" else entry.back

        if active_item is not None:
            # Original raw image
            orig_bgr = active_item.original_image
            orig_dims = f"Raw: {orig_bgr.shape[1]} × {orig_bgr.shape[0]} px"
            self.card_original.set_image(orig_bgr, orig_dims)

            # Formatted normalized image
            final_bgr = active_item.final_image
            self.card_formatted.set_image(final_bgr, dims_str)
        else:
            empty_msg = f"No {side_name.lower()} photo uploaded (Single-sided card)"
            self.card_original.set_image(None, "", empty_msg)
            self.card_formatted.set_image(None, "", empty_msg)

        # Update Combined Sheet Preview
        front_img = entry.front.final_image if entry.front is not None else None
        back_img = entry.back.final_image if entry.back is not None else None
        rendered, metrics = self.layout_engine.render_pair(
            front_img, back_img, profile, copies=max(1, self.copies),
            single_page=self.single_page
        )
        if rendered is not None:
            self.combined_preview.set_rendered(rendered)
            if metrics is not None:
                self.lbl_page_info.setText(
                    f"{metrics.page_width_mm:.1f} × {metrics.page_height_mm:.1f} mm  "
                    f"@ {metrics.dpi} DPI  •  {metrics.page_width_px} × {metrics.page_height_px} px"
                )

    def on_change_profile(self, profile: FormatProfile):
        self.pipeline.set_card_profile(profile)
        if profile == CARD_PROFILE:
            self.btn_prof_card.setChecked(True)
            self.btn_prof_long.setChecked(False)
        else:
            self.btn_prof_card.setChecked(False)
            self.btn_prof_long.setChecked(True)
        self._update_preview()

    # ── Status Handling ────────────────────────────────────────────
    def _set_status(self, kind: str, text: str):
        self.btn_status.setText(f"● {text}")
        colors = {
            "ready": ("#10B981", "rgba(16,185,129,0.15)", "1px solid rgba(16,185,129,0.4)"),
            "review": ("#F59E0B", "rgba(245,158,11,0.12)", "1px solid rgba(245,158,11,0.4)"),
            "idle": ("#66667A", "rgba(102,102,122,0.1)", "1px solid rgba(102,102,122,0.3)"),
        }
        fg, bg, bd = colors.get(kind, colors["idle"])
        self.btn_status.setStyleSheet(
            f"color:{fg}; background-color:{bg}; border:{bd}; border-radius:16px;"
            f"padding:6px 16px; font-weight:700; font-size:12px;")

    def _update_status(self):
        entry = self.pipeline.card_entry
        if entry is None or entry.is_empty() or (entry.front is None and entry.back is None):
            self._set_status("idle", "No card loaded")
            return
        fronts = []
        for side in (entry.front, entry.back):
            if side is not None and getattr(side, "quality_report", None) is not None:
                fronts.append(side.quality_report)
        if not fronts:
            self._set_status("idle", "Process to continue")
            return
        worst = min(getattr(q, "overall_confidence", 1.0) for q in fronts)
        if worst < 0.60:
            self._set_status("review", "Review Suggested")
        else:
            self._set_status("ready", "Ready to Print")

    def on_status_clicked(self):
        entry = self.pipeline.card_entry
        if entry is None:
            return
        lines = []
        for name, side in (("FRONT", entry.front), ("BACK", entry.back)):
            if side is None:
                continue
            lines.append(f"[{name}]")
            qr = getattr(side, "quality_report", None)
            if qr:
                lines.append(f"  Boundary Conf:    {getattr(qr, 'boundary_confidence', 1.0):.0%}")
                lines.append(f"  Orientation Conf: {getattr(qr, 'orientation_confidence', 1.0):.0%}")
                lines.append(f"  Blur Score:       {getattr(qr, 'blur_score', 0):.1f}")
            lines.append("")
        QMessageBox.information(self, "Quality Diagnostics", "\n".join(lines) if lines else "No diagnostics available.")

    def on_copies_minus(self):
        self.copies = max(1, self.copies - 1)
        self.lbl_copies.setText(str(self.copies))
        self._update_preview()

    def on_copies_plus(self):
        self.copies = min(30, self.copies + 1)
        self.lbl_copies.setText(str(self.copies))
        self._update_preview()

    # ── Print / Export ─────────────────────────────────────────────
    def on_print(self):
        entry = self.pipeline.card_entry
        if entry is None or entry.is_empty():
            return
        PrintManager.print_card_pair(self.pipeline.card_pair, self, copies=max(1, self.copies))

    def on_export_docx(self):
        """Exports card pair directly into Microsoft Word (.docx) using DocxExporter."""
        entry = self.pipeline.card_entry
        if entry is None or entry.is_empty():
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Word Document", "card_print.docx", "Word Documents (*.docx)")
        if not path:
            return
        ok = DocxExporter.export_card_pair(self.pipeline.card_pair, path)
        if ok:
            QMessageBox.information(self, "Export Successful", f"Word document exported to:\n{path}")
        else:
            QMessageBox.critical(self, "Export Failed", "Could not export Word document.")

    def on_export_image(self):
        entry = self.pipeline.card_entry
        if entry is None or entry.is_empty():
            return
        fmt = "PNG File (*.png)"
        path, _ = QFileDialog.getSaveFileName(self, "Export Print Layout", "card_pair.png", fmt)
        if not path:
            return
        ok = ImageExporter.export_card_pair(
            self.pipeline.card_pair, path, copies=max(1, self.copies), single_page=False)
        if ok:
            QMessageBox.information(self, "Export Successful", f"Image exported to:\n{path}")
        else:
            QMessageBox.critical(self, "Export Failed", "Could not export image.")

    def on_export_pdf(self):
        entry = self.pipeline.card_entry
        if entry is None or entry.is_empty():
            return
        path, _ = QFileDialog.getSaveFileName(self, "Export PDF", "card_pair.pdf", "PDF (*.pdf)")
        if not path:
            return
        ok = PdfExporter.export_card_pair(
            self.pipeline.card_pair, path, copies=max(1, self.copies), single_page=False)
        if ok:
            QMessageBox.information(self, "Export Successful", f"PDF exported to:\n{path}")
        else:
            QMessageBox.critical(self, "Export Failed", "Could not export PDF.")

    # ── Corner / Rotation Correction ────────────────────────────────
    def on_edit_active_corners(self):
        entry = self.pipeline.card_entry
        if entry is None or entry.is_empty():
            return
        side_img = entry.front if self.active_preview_side == "front" else entry.back
        if side_img is None:
            return
        dialog = CornerEditorDialog(side_img, self)
        if dialog.exec():
            new_corners = dialog.get_result_corners()
            self.pipeline.update_item_corners(side_img, new_corners)
            self._update_preview()
            self._update_status()

    def on_rotate_active_side(self, angle_deg: int):
        entry = self.pipeline.card_entry
        if entry is None or entry.is_empty():
            return
        side_img = entry.front if self.active_preview_side == "front" else entry.back
        if side_img is None:
            return
        self.pipeline.rotate_item(side_img, angle_deg)
        self._update_preview()
        self._update_status()

    def on_reset(self):
        self.front_path = None
        self.back_path = None
        self.pipeline.reset()
        self._refresh_slots()
        self._update_ready()
        self._update_preview()
        self._update_status()
