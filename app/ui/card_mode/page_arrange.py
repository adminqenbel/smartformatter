"""
Step 2 of 5: Arrange (Card Mode).
Dedicated review screen to confirm Front/Back assignment, swap sides, and select Output Format.
"""
from pathlib import Path
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
    QFileDialog,
    QScrollArea,
    QButtonGroup,
    QSizePolicy,
)

from app.core.profiles import FormatProfile, CARD_PROFILE, LONG_FORM_PROFILE
from app.utils.image_io import load_image_safe


class SidePreviewCard(QFrame):
    """Clean card showing one assigned side with replace action."""
    replace_requested = Signal()

    def __init__(self, side_label: str, parent=None):
        super().__init__(parent)
        self.side_label = side_label
        self.file_path: Optional[str] = None

        self.setFixedWidth(340)
        self.setFixedHeight(300)
        self._init_ui()

    def _init_ui(self):
        self.setStyleSheet("""
            SidePreviewCard {
                background-color: #14141A;
                border: 1px solid #24242E;
                border-radius: 14px;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 18)
        layout.setSpacing(12)
        layout.setAlignment(Qt.AlignCenter)

        self.lbl_title = QLabel(self.side_label)
        self.lbl_title.setStyleSheet("""
            font-size: 13px;
            font-weight: 800;
            letter-spacing: 1px;
            color: #94A3B8;
            background: transparent;
        """)
        self.lbl_title.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.lbl_title)

        self.lbl_thumb = QLabel("No image loaded")
        self.lbl_thumb.setAlignment(Qt.AlignCenter)
        self.lbl_thumb.setFixedSize(290, 160)
        self.lbl_thumb.setStyleSheet("""
            background-color: #0A0A0E;
            border-radius: 8px;
            border: 1px solid #1E1E26;
            color: #64748B;
            font-size: 12px;
        """)
        layout.addWidget(self.lbl_thumb, alignment=Qt.AlignCenter)

        self.lbl_name = QLabel("—")
        self.lbl_name.setStyleSheet("font-size: 12px; font-weight: 600; color: #E2E8F0; background: transparent;")
        self.lbl_name.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.lbl_name)

        self.btn_replace = QPushButton("Replace")
        self.btn_replace.setCursor(Qt.PointingHandCursor)
        self.btn_replace.setFixedHeight(32)
        self.btn_replace.setFixedWidth(110)
        self.btn_replace.setStyleSheet("""
            QPushButton {
                background-color: #1E293B;
                color: #E2E8F0;
                border: 1px solid #334155;
                border-radius: 6px;
                font-size: 12px;
                font-weight: 600;
            }
            QPushButton:hover {
                background-color: #334155;
                border-color: #475569;
            }
        """)
        self.btn_replace.clicked.connect(self.replace_requested.emit)
        layout.addWidget(self.btn_replace, alignment=Qt.AlignCenter)

    def set_file(self, path: Optional[str]):
        self.file_path = path
        if not path:
            self.lbl_thumb.setPixmap(QPixmap())
            self.lbl_thumb.setText("No image loaded")
            self.lbl_name.setText("—")
            self.btn_replace.setEnabled(False)
            return

        self.btn_replace.setEnabled(True)
        self.lbl_name.setText(Path(path).name)

        img = load_image_safe(path)
        if img is not None:
            rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
            h, w = rgb.shape[:2]
            qimg = QImage(rgb.data, w, h, w * 3, QImage.Format_RGB888)
            pix = QPixmap.fromImage(qimg).scaled(
                280, 150, Qt.KeepAspectRatio, Qt.SmoothTransformation
            )
            self.lbl_thumb.setPixmap(pix)


class PageArrange(QWidget):
    """
    Step 2: Arrange (Card Mode)
    Visual confirmation of Front and Back, Swap, and Output Format selection.
    """
    assignment_swapped = Signal()
    file_replaced = Signal(str, str)  # (side, new_path)
    profile_changed = Signal(FormatProfile)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.front_path: Optional[str] = None
        self.back_path: Optional[str] = None
        self.selected_profile: FormatProfile = CARD_PROFILE

        self._init_ui()

    def _init_ui(self):
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")

        container = QWidget()
        container.setStyleSheet("background: transparent;")
        main_layout = QVBoxLayout(container)
        main_layout.setContentsMargins(40, 20, 40, 24)
        main_layout.setSpacing(24)
        main_layout.setAlignment(Qt.AlignTop | Qt.AlignHCenter)

        # Header Title
        title_box = QVBoxLayout()
        title_box.setSpacing(4)
        title_box.setAlignment(Qt.AlignCenter)

        step_lbl = QLabel("STEP 2 OF 5")
        step_lbl.setStyleSheet("font-size: 12px; font-weight: 800; letter-spacing: 1.5px; color: #38BDF8; background: transparent;")
        step_lbl.setAlignment(Qt.AlignCenter)
        title_box.addWidget(step_lbl)

        heading = QLabel("Arrange & Format")
        heading.setStyleSheet("font-size: 26px; font-weight: 800; color: #FFFFFF; letter-spacing: -0.5px; background: transparent;")
        heading.setAlignment(Qt.AlignCenter)
        title_box.addWidget(heading)

        subheading = QLabel("Confirm front and back side assignments to prevent mistakes, then choose the output format.")
        subheading.setStyleSheet("font-size: 14px; color: #94A3B8; background: transparent;")
        subheading.setAlignment(Qt.AlignCenter)
        title_box.addWidget(subheading)

        main_layout.addLayout(title_box)

        # Front / Back Row
        sides_row = QHBoxLayout()
        sides_row.setSpacing(24)
        sides_row.setAlignment(Qt.AlignCenter)

        self.card_front = SidePreviewCard("FRONT")
        self.card_front.replace_requested.connect(lambda: self._on_replace("front"))
        sides_row.addWidget(self.card_front)

        # Center Swap Action
        swap_col = QVBoxLayout()
        swap_col.setAlignment(Qt.AlignCenter)
        self.btn_swap = QPushButton("⇄\nSwap")
        self.btn_swap.setCursor(Qt.PointingHandCursor)
        self.btn_swap.setFixedSize(70, 70)
        self.btn_swap.setStyleSheet("""
            QPushButton {
                background-color: #1E293B;
                color: #38BDF8;
                border: 2px solid #334155;
                border-radius: 35px;
                font-size: 14px;
                font-weight: 800;
            }
            QPushButton:hover {
                background-color: #2563EB;
                border-color: #60A5FA;
                color: #FFFFFF;
            }
        """)
        self.btn_swap.clicked.connect(self._on_swap)
        swap_col.addWidget(self.btn_swap)
        sides_row.addLayout(swap_col)

        self.card_back = SidePreviewCard("BACK")
        self.card_back.replace_requested.connect(lambda: self._on_replace("back"))
        sides_row.addWidget(self.card_back)

        main_layout.addLayout(sides_row)

        # ── Output Format Selection ──
        fmt_frame = QFrame()
        fmt_frame.setStyleSheet("""
            QFrame {
                background-color: #14141A;
                border: 1px solid #24242E;
                border-radius: 14px;
            }
        """)
        fmt_frame.setFixedWidth(540)
        fmt_layout = QVBoxLayout(fmt_frame)
        fmt_layout.setContentsMargins(24, 18, 24, 20)
        fmt_layout.setSpacing(14)

        fmt_head = QLabel("OUTPUT FORMAT")
        fmt_head.setStyleSheet("font-size: 12px; font-weight: 800; letter-spacing: 1px; color: #94A3B8; background: transparent;")
        fmt_head.setAlignment(Qt.AlignCenter)
        fmt_layout.addWidget(fmt_head)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(16)
        btn_row.setAlignment(Qt.AlignCenter)

        self.btn_card = QPushButton("Card\n86 × 54 mm")
        self.btn_card.setCheckable(True)
        self.btn_card.setChecked(True)
        self.btn_card.setCursor(Qt.PointingHandCursor)
        self.btn_card.setFixedHeight(64)
        self.btn_card.setMinimumWidth(180)

        self.btn_long = QPushButton("Long Form\n210 × 85 mm")
        self.btn_long.setCheckable(True)
        self.btn_long.setCursor(Qt.PointingHandCursor)
        self.btn_long.setFixedHeight(64)
        self.btn_long.setMinimumWidth(180)

        fmt_style = """
            QPushButton {
                background-color: #0F0F14;
                color: #94A3B8;
                border: 2px solid #24242E;
                border-radius: 10px;
                font-size: 14px;
                font-weight: 700;
                line-height: 1.3;
            }
            QPushButton:hover {
                border-color: #38BDF8;
                color: #FFFFFF;
            }
            QPushButton:checked {
                background-color: rgba(37, 99, 235, 0.15);
                border-color: #2563EB;
                color: #FFFFFF;
            }
        """
        self.btn_card.setStyleSheet(fmt_style)
        self.btn_long.setStyleSheet(fmt_style)

        self.btn_group = QButtonGroup(self)
        self.btn_group.setExclusive(True)
        self.btn_group.addButton(self.btn_card)
        self.btn_group.addButton(self.btn_long)

        self.btn_card.clicked.connect(lambda: self._on_format_selected(CARD_PROFILE))
        self.btn_long.clicked.connect(lambda: self._on_format_selected(LONG_FORM_PROFILE))

        btn_row.addWidget(self.btn_card)
        btn_row.addWidget(self.btn_long)
        fmt_layout.addLayout(btn_row)

        main_layout.addWidget(fmt_frame, alignment=Qt.AlignCenter)

        scroll.setWidget(container)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

    def set_data(self, front: Optional[str], back: Optional[str], profile: FormatProfile):
        self.front_path = front
        self.back_path = back
        self.selected_profile = profile

        self.card_front.set_file(front)
        self.card_back.set_file(back)

        # Enable/disable swap depending on whether both exist
        self.btn_swap.setEnabled(bool(front and back))

        if profile.id == LONG_FORM_PROFILE.id:
            self.btn_long.setChecked(True)
        else:
            self.btn_card.setChecked(True)

    def _on_swap(self):
        self.front_path, self.back_path = self.back_path, self.front_path
        self.card_front.set_file(self.front_path)
        self.card_back.set_file(self.back_path)
        self.assignment_swapped.emit()

    def _on_replace(self, side: str):
        path, _ = QFileDialog.getOpenFileName(
            self,
            f"Select {side.title()} Photo",
            "",
            "Image Files (*.jpg *.jpeg *.png *.webp);;All Files (*.*)",
        )
        if path:
            if side == "front":
                self.front_path = path
                self.card_front.set_file(path)
            else:
                self.back_path = path
                self.card_back.set_file(path)
            self.btn_swap.setEnabled(bool(self.front_path and self.back_path))
            self.file_replaced.emit(side, path)

    def _on_format_selected(self, profile: FormatProfile):
        self.selected_profile = profile
        self.profile_changed.emit(profile)
