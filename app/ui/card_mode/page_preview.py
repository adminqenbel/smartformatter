"""
Step 4 of 5: Print Preview (Card Mode).
Renders the 100% REAL composite image that will be printed.
Provides clean controls: Zoom, Edit Front/Back, Rotate, and Swap.
"""
from typing import Optional
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
    QScrollArea,
    QSizePolicy,
    QGraphicsDropShadowEffect,
    QComboBox,
)

from app.core.pipeline import FormatterPipeline
from app.core.print_layout import PrintLayoutEngine, CardOutputComposer
from app.utils.logger import get_logger

logger = get_logger("page_preview")


class CardCanvas(QScrollArea):
    """Scrollable canvas with smooth zoom and real output display."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setStyleSheet("QScrollArea { background-color: #0A0A0E; border: 1px solid #1E1E26; border-radius: 12px; }")

        self.container = QWidget()
        self.container.setStyleSheet("background-color: #0A0A0E;")
        self.layout = QVBoxLayout(self.container)
        self.layout.setAlignment(Qt.AlignCenter)
        self.layout.setContentsMargins(20, 20, 20, 20)

        # Image display container with shadow
        self.card_frame = QFrame()
        self.card_frame.setStyleSheet("background-color: #FFFFFF; border-radius: 4px;")
        cf_lay = QVBoxLayout(self.card_frame)
        cf_lay.setContentsMargins(0, 0, 0, 0)

        self.lbl_image = QLabel()
        self.lbl_image.setAlignment(Qt.AlignCenter)
        self.lbl_image.setStyleSheet("background: transparent;")
        cf_lay.addWidget(self.lbl_image)

        self.layout.addWidget(self.card_frame)
        self.setWidget(self.container)

        self._raw_pixmap: Optional[QPixmap] = None
        self._zoom: float = 1.0

    clicked = Signal()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)

    def set_image(self, bgr_img: Optional[np.ndarray]):
        if bgr_img is None:
            self._raw_pixmap = None
            self.lbl_image.setPixmap(QPixmap())
            self.card_frame.hide()
            return

        rgb = cv2.cvtColor(bgr_img, cv2.COLOR_BGR2RGB)
        h, w = rgb.shape[:2]
        qimg = QImage(rgb.data, w, h, w * 3, QImage.Format_RGB888)
        self._raw_pixmap = QPixmap.fromImage(qimg)
        self.card_frame.show()
        self.fit_to_view()

    def _apply_zoom(self):
        if self._raw_pixmap is None:
            return
        base_w = self._raw_pixmap.width()
        base_h = self._raw_pixmap.height()
        target_w = max(1, int(base_w * self._zoom))
        target_h = max(1, int(base_h * self._zoom))
        scaled = self._raw_pixmap.scaled(
            target_w, target_h, Qt.KeepAspectRatio, Qt.SmoothTransformation
        )
        self.lbl_image.setPixmap(scaled)

    def zoom_in(self):
        self._zoom = min(3.0, self._zoom + 0.2)
        self._apply_zoom()

    def zoom_out(self):
        self._zoom = max(0.15, self._zoom - 0.2)
        self._apply_zoom()

    def fit_to_view(self):
        if self._raw_pixmap is None:
            return
        viewport_w = max(200, self.viewport().width() - 80)
        viewport_h = max(200, self.viewport().height() - 80)
        scale_w = viewport_w / self._raw_pixmap.width()
        scale_h = viewport_h / self._raw_pixmap.height()
        self._zoom = min(1.0, scale_w, scale_h)
        self._apply_zoom()


class PagePreview(QWidget):
    """
    Step 4: Print Preview (Card Mode)
    Displays the true composite image with essential controls:
    Zoom, Rotate, Edit Corners, and Swap.
    """
    edit_corners_requested = Signal(str)  # "front" or "back"
    swap_requested = Signal()
    rotate_requested = Signal(str, int)   # (side, angle_deg)
    refresh_needed = Signal()

    def __init__(self, pipeline: FormatterPipeline, parent=None):
        super().__init__(parent)
        self.pipeline = pipeline
        self.layout_engine = PrintLayoutEngine()
        self._active_preview_side = "front"
        self._active_edit_side = "front"

        self._init_ui()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(32, 16, 32, 16)
        main_layout.setSpacing(12)

        # Header Title
        top_row = QHBoxLayout()
        title_box = QVBoxLayout()
        title_box.setSpacing(2)

        step_lbl = QLabel("STEP 4 OF 5")
        step_lbl.setStyleSheet("font-size: 11px; font-weight: 800; letter-spacing: 1.5px; color: #38BDF8; background: transparent;")
        title_box.addWidget(step_lbl)

        heading = QLabel("Print Preview")
        heading.setStyleSheet("font-size: 22px; font-weight: 800; color: #FFFFFF; letter-spacing: -0.3px; background: transparent;")
        title_box.addWidget(heading)

        top_row.addLayout(title_box)
        top_row.addStretch()

        self.btn_toggle_side = QPushButton("👁  Preview: FRONT  ⇄")
        self.btn_toggle_side.setCursor(Qt.PointingHandCursor)
        self.btn_toggle_side.setFixedHeight(34)
        self.btn_toggle_side.setMinimumWidth(160)
        self.btn_toggle_side.setStyleSheet("""
            QPushButton {
                background-color: #1E293B;
                color: #38BDF8;
                border: 1px solid #334155;
                border-radius: 8px;
                padding: 0 14px;
                font-size: 12px;
                font-weight: 700;
            }
            QPushButton:hover {
                background-color: #2563EB;
                border-color: #38BDF8;
                color: #FFFFFF;
            }
            QPushButton:disabled {
                background-color: #14141A;
                color: #64748B;
                border-color: #24242E;
            }
        """)
        self.btn_toggle_side.clicked.connect(self._on_toggle_side_clicked)
        top_row.addWidget(self.btn_toggle_side)

        self.lbl_metrics = QLabel("—")
        self.lbl_metrics.setStyleSheet("font-size: 12px; font-weight: 600; color: #94A3B8; background: transparent;")
        top_row.addWidget(self.lbl_metrics)

        main_layout.addLayout(top_row)

        # ── Compact Control Bar ──
        ctrl_bar = QFrame()
        ctrl_bar.setStyleSheet("""
            QFrame {
                background-color: #14141A;
                border: 1px solid #24242E;
                border-radius: 10px;
            }
        """)
        ctrl_bar.setFixedHeight(48)
        c_layout = QHBoxLayout(ctrl_bar)
        c_layout.setContentsMargins(14, 0, 14, 0)
        c_layout.setSpacing(10)

        # Zoom Controls
        btn_zoom_out = QPushButton("－")
        btn_zoom_out.setFixedSize(32, 32)
        btn_zoom_out.setCursor(Qt.PointingHandCursor)
        btn_zoom_out.setStyleSheet(self._btn_style())
        btn_zoom_out.clicked.connect(lambda: self.canvas.zoom_out())
        c_layout.addWidget(btn_zoom_out)

        btn_fit = QPushButton("Fit")
        btn_fit.setFixedHeight(32)
        btn_fit.setCursor(Qt.PointingHandCursor)
        btn_fit.setStyleSheet(self._btn_style())
        btn_fit.clicked.connect(lambda: self.canvas.fit_to_view())
        c_layout.addWidget(btn_fit)

        btn_zoom_in = QPushButton("＋")
        btn_zoom_in.setFixedSize(32, 32)
        btn_zoom_in.setCursor(Qt.PointingHandCursor)
        btn_zoom_in.setStyleSheet(self._btn_style())
        btn_zoom_in.clicked.connect(lambda: self.canvas.zoom_in())
        c_layout.addWidget(btn_zoom_in)

        c_layout.addSpacing(16)
        c_layout.addWidget(self._divider())
        c_layout.addSpacing(16)

        # Edit Corners Controls
        self.btn_edit_front = QPushButton("Edit Front Corners")
        self.btn_edit_front.setFixedHeight(32)
        self.btn_edit_front.setCursor(Qt.PointingHandCursor)
        self.btn_edit_front.setStyleSheet(self._btn_style())
        self.btn_edit_front.clicked.connect(lambda: self.edit_corners_requested.emit("front"))
        c_layout.addWidget(self.btn_edit_front)

        self.btn_edit_back = QPushButton("Edit Back Corners")
        self.btn_edit_back.setFixedHeight(32)
        self.btn_edit_back.setCursor(Qt.PointingHandCursor)
        self.btn_edit_back.setStyleSheet(self._btn_style())
        self.btn_edit_back.clicked.connect(lambda: self.edit_corners_requested.emit("back"))
        c_layout.addWidget(self.btn_edit_back)

        c_layout.addSpacing(16)
        c_layout.addWidget(self._divider())
        c_layout.addSpacing(16)

        # Rotation applies to one side at a time so a correction on one
        # photograph cannot unexpectedly change the other side.
        self.combo_rotate_side = QComboBox()
        self.combo_rotate_side.addItem("Front", "front")
        self.combo_rotate_side.addItem("Back", "back")
        self.combo_rotate_side.setFixedHeight(32)
        self.combo_rotate_side.setStyleSheet("""
            QComboBox {
                background-color: #1E1E26; color: #E2E8F0;
                border: 1px solid #2E2E3A; border-radius: 6px;
                padding: 0 8px; font-size: 12px; font-weight: 600;
            }
            QComboBox::drop-down { border: none; width: 20px; }
            QComboBox QAbstractItemView {
                background-color: #1E293B; color: #FFFFFF;
                selection-background-color: #2563EB;
            }
        """)
        c_layout.addWidget(self.combo_rotate_side)

        # Rotation Controls
        btn_rot_left = QPushButton("↶ Rotate Left")
        btn_rot_left.setFixedHeight(32)
        btn_rot_left.setCursor(Qt.PointingHandCursor)
        btn_rot_left.setStyleSheet(self._btn_style())
        btn_rot_left.clicked.connect(self._rotate_active_left)
        c_layout.addWidget(btn_rot_left)

        btn_rot_right = QPushButton("↷ Rotate Right")
        btn_rot_right.setFixedHeight(32)
        btn_rot_right.setCursor(Qt.PointingHandCursor)
        btn_rot_right.setStyleSheet(self._btn_style())
        btn_rot_right.clicked.connect(self._rotate_active_right)
        c_layout.addWidget(btn_rot_right)

        c_layout.addStretch()

        # Swap Button
        self.btn_swap = QPushButton("⇄ Swap Sides")
        self.btn_swap.setFixedHeight(32)
        self.btn_swap.setCursor(Qt.PointingHandCursor)
        self.btn_swap.setStyleSheet("""
            QPushButton {
                background-color: #1E293B;
                color: #38BDF8;
                border: 1px solid #334155;
                border-radius: 6px;
                padding: 0 14px;
                font-size: 12px;
                font-weight: 700;
            }
            QPushButton:hover {
                background-color: #2563EB;
                color: #FFFFFF;
            }
        """)
        self.btn_swap.clicked.connect(self._on_swap)
        c_layout.addWidget(self.btn_swap)

        main_layout.addWidget(ctrl_bar)

        # ── Canvas Area ──
        self.canvas = CardCanvas(self)
        self.canvas.clicked.connect(self._on_toggle_side_clicked)
        main_layout.addWidget(self.canvas, stretch=1)

    def _btn_style(self):
        return """
            QPushButton {
                background-color: #1E1E26;
                color: #E2E8F0;
                border: 1px solid #2E2E3A;
                border-radius: 6px;
                padding: 0 12px;
                font-size: 12px;
                font-weight: 600;
            }
            QPushButton:hover {
                background-color: #2E2E3A;
                border-color: #4B4B5A;
            }
        """

    def _divider(self):
        d = QFrame()
        d.setFrameShape(QFrame.VLine)
        d.setFixedSize(1, 22)
        d.setStyleSheet("background-color: #2A2A36; border: none;")
        return d

    def _on_toggle_side_clicked(self):
        """Toggles between previewing Front and Back side on a single click."""
        entry = self.pipeline.card_entry
        if not entry or entry.is_empty():
            return
        f_proc = entry.front
        b_proc = entry.back
        if f_proc is not None and b_proc is not None:
            self._active_preview_side = "back" if self._active_preview_side == "front" else "front"
        elif f_proc is not None:
            self._active_preview_side = "front"
        elif b_proc is not None:
            self._active_preview_side = "back"

        rot_idx = 0 if self._active_preview_side == "front" else 1
        if self.combo_rotate_side.count() > rot_idx:
            self.combo_rotate_side.setCurrentIndex(rot_idx)
        self.refresh_preview()

    def refresh_preview(self):
        entry = self.pipeline.card_entry
        if entry is None or entry.is_empty():
            self.canvas.set_image(None)
            self.lbl_metrics.setText("No document loaded")
            self.btn_edit_front.setEnabled(False)
            self.btn_edit_back.setEnabled(False)
            self.btn_swap.setEnabled(False)
            self.btn_toggle_side.setEnabled(False)
            self.combo_rotate_side.setEnabled(False)
            return

        f_proc = entry.front
        b_proc = entry.back
        f_img = f_proc.final_image if f_proc is not None else None
        b_img = b_proc.final_image if b_proc is not None else None
        profile = entry.format_profile or self.pipeline.active_card_profile

        # Fallback if selected side has no image
        if self._active_preview_side == "front" and f_img is None and b_img is not None:
            self._active_preview_side = "back"
        elif self._active_preview_side == "back" and b_img is None and f_img is not None:
            self._active_preview_side = "front"

        side_label = "FRONT" if self._active_preview_side == "front" else "BACK"
        has_both = bool(f_img is not None and b_img is not None)
        self.btn_toggle_side.setEnabled(has_both)
        if has_both:
            self.btn_toggle_side.setText(f"👁  Preview: {side_label}  ⇄")
            self.btn_toggle_side.setToolTip("Click to toggle preview between Front and Back sides")
        else:
            self.btn_toggle_side.setText(f"👁  Preview: {side_label}")

        preview_img = f_img if self._active_preview_side == "front" else b_img

        # Render the selected normalized side at its exact physical size.
        rendered, metrics = self.layout_engine.render_pair(
            preview_img, None, profile, copies=1, single_page=False
        )
        self.canvas.set_image(rendered)

        if metrics is not None:
            self.lbl_metrics.setText(
                f"{profile.name}  •  {metrics.page_width_mm:.0f} × {metrics.page_height_mm:.0f} mm  •  "
                f"{metrics.page_width_px} × {metrics.page_height_px} px @ {metrics.dpi} DPI"
            )

        self.btn_edit_front.setEnabled(bool(f_proc and f_proc.final_image is not None))
        self.btn_edit_back.setEnabled(bool(b_proc and b_proc.final_image is not None))
        self.btn_swap.setEnabled(has_both)
        self.combo_rotate_side.setEnabled(bool(f_proc or b_proc))
        self.combo_rotate_side.model().item(0).setEnabled(f_proc is not None)
        self.combo_rotate_side.model().item(1).setEnabled(b_proc is not None)
        rot_idx = 0 if self._active_preview_side == "front" else 1
        if self.combo_rotate_side.count() > rot_idx:
            self.combo_rotate_side.setCurrentIndex(rot_idx)

    def _rotate_active_left(self):
        self._apply_rotation(-90)

    def _rotate_active_right(self):
        self._apply_rotation(90)

    def _apply_rotation(self, angle: int):
        entry = self.pipeline.card_entry
        if not entry:
            return
        side = self.combo_rotate_side.currentData() or self._active_preview_side
        side_img = entry.front if side == "front" else entry.back
        if side_img is not None:
            self.pipeline.rotate_item(side_img, angle)
        self.refresh_preview()
        self.refresh_needed.emit()

    def _on_swap(self):
        self.pipeline.swap_card_sides()
        self.refresh_preview()
        self.swap_requested.emit()
