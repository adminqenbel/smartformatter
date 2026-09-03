"""
Step 1 of 5: Add Photos (Card Mode).
Provides spacious, prominent upload zones for Front and Back photographs.
"""
from pathlib import Path
from typing import Optional, List
import cv2
import numpy as np
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap, QImage, QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QFrame,
    QFileDialog,
    QScrollArea,
    QSizePolicy,
)

from app.utils.image_io import load_image_safe
from app.utils.logger import get_logger

logger = get_logger("page_add_photos")


class UploadSlot(QFrame):
    """Spacious upload card for either Front or Back photo."""
    file_selected = Signal(str)
    file_cleared = Signal()

    def __init__(self, title: str, subtitle: str, parent=None):
        super().__init__(parent)
        self.title_text = title
        self.subtitle_text = subtitle
        self.file_path: Optional[str] = None

        self.setAcceptDrops(True)
        self.setMinimumWidth(360)
        self.setFixedHeight(340)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        self._init_ui()

    def _init_ui(self):
        self.setStyleSheet("""
            UploadSlot {
                background-color: #14141A;
                border: 2px dashed #2E2E3A;
                border-radius: 16px;
            }
            UploadSlot:hover {
                border-color: #3B82F6;
                background-color: #161620;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(14)
        layout.setAlignment(Qt.AlignCenter)

        # Slot Header
        self.lbl_header = QLabel(self.title_text)
        self.lbl_header.setStyleSheet("""
            font-size: 14px;
            font-weight: 800;
            letter-spacing: 1px;
            color: #94A3B8;
            background: transparent;
        """)
        self.lbl_header.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.lbl_header)

        # Empty State Container
        self.empty_widget = QWidget()
        self.empty_widget.setStyleSheet("background: transparent;")
        empty_layout = QVBoxLayout(self.empty_widget)
        empty_layout.setContentsMargins(0, 8, 0, 8)
        empty_layout.setSpacing(10)
        empty_layout.setAlignment(Qt.AlignCenter)

        self.lbl_action = QLabel(f"+ Add {self.title_text}")
        self.lbl_action.setStyleSheet("""
            font-size: 18px;
            font-weight: 700;
            color: #FFFFFF;
            background: transparent;
        """)
        self.lbl_action.setAlignment(Qt.AlignCenter)
        empty_layout.addWidget(self.lbl_action)

        self.lbl_drag = QLabel("Drag & Drop or Browse")
        self.lbl_drag.setStyleSheet("""
            font-size: 13px;
            color: #64748B;
            background: transparent;
        """)
        self.lbl_drag.setAlignment(Qt.AlignCenter)
        empty_layout.addWidget(self.lbl_drag)

        empty_layout.addSpacing(6)

        self.btn_browse = QPushButton("Browse Files")
        self.btn_browse.setCursor(Qt.PointingHandCursor)
        self.btn_browse.setFixedHeight(44)
        self.btn_browse.setMinimumWidth(160)
        self.btn_browse.setStyleSheet("""
            QPushButton {
                background-color: #2563EB;
                color: #FFFFFF;
                border: none;
                border-radius: 10px;
                font-size: 14px;
                font-weight: 700;
                padding: 0 20px;
            }
            QPushButton:hover {
                background-color: #1D4ED8;
            }
            QPushButton:pressed {
                background-color: #1E40AF;
            }
        """)
        self.btn_browse.clicked.connect(self._on_browse)
        empty_layout.addWidget(self.btn_browse, alignment=Qt.AlignCenter)

        layout.addWidget(self.empty_widget)

        # Filled State Container
        self.filled_widget = QWidget()
        self.filled_widget.setStyleSheet("background: transparent;")
        filled_layout = QVBoxLayout(self.filled_widget)
        filled_layout.setContentsMargins(0, 0, 0, 0)
        filled_layout.setSpacing(10)
        filled_layout.setAlignment(Qt.AlignCenter)

        self.lbl_thumb = QLabel()
        self.lbl_thumb.setAlignment(Qt.AlignCenter)
        self.lbl_thumb.setFixedSize(300, 160)
        self.lbl_thumb.setStyleSheet("""
            background-color: #0A0A0E;
            border-radius: 8px;
            border: 1px solid #24242E;
        """)
        filled_layout.addWidget(self.lbl_thumb, alignment=Qt.AlignCenter)

        self.lbl_filename = QLabel("filename.jpg")
        self.lbl_filename.setStyleSheet("""
            font-size: 12px;
            font-weight: 600;
            color: #CBD5E1;
            background: transparent;
        """)
        self.lbl_filename.setAlignment(Qt.AlignCenter)
        filled_layout.addWidget(self.lbl_filename)

        filled_actions = QHBoxLayout()
        filled_actions.setAlignment(Qt.AlignCenter)
        filled_actions.setSpacing(12)

        self.btn_replace = QPushButton("Replace")
        self.btn_replace.setCursor(Qt.PointingHandCursor)
        self.btn_replace.setFixedHeight(34)
        self.btn_replace.setStyleSheet("""
            QPushButton {
                background-color: #1E293B;
                color: #E2E8F0;
                border: 1px solid #334155;
                border-radius: 8px;
                font-size: 12px;
                font-weight: 600;
                padding: 0 16px;
            }
            QPushButton:hover {
                background-color: #334155;
                border-color: #475569;
            }
        """)
        self.btn_replace.clicked.connect(self._on_browse)
        filled_actions.addWidget(self.btn_replace)

        self.btn_clear = QPushButton("Remove")
        self.btn_clear.setCursor(Qt.PointingHandCursor)
        self.btn_clear.setFixedHeight(34)
        self.btn_clear.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                color: #94A3B8;
                border: 1px solid #282834;
                border-radius: 8px;
                font-size: 12px;
                font-weight: 500;
                padding: 0 14px;
            }
            QPushButton:hover {
                color: #EF4444;
                border-color: #EF4444;
            }
        """)
        self.btn_clear.clicked.connect(self.clear_file)
        filled_actions.addWidget(self.btn_clear)

        filled_layout.addLayout(filled_actions)
        layout.addWidget(self.filled_widget)

        self.filled_widget.hide()

    def set_file(self, path: Optional[str]):
        self.file_path = path
        if not path:
            self.empty_widget.show()
            self.filled_widget.hide()
            self.lbl_thumb.setPixmap(QPixmap())
            self.lbl_header.setStyleSheet("""
                font-size: 14px;
                font-weight: 800;
                letter-spacing: 1px;
                color: #94A3B8;
                background: transparent;
            """)
            return

        img = load_image_safe(path)
        if img is None:
            logger.warning(f"Could not load thumbnail for {path}")
            return

        rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        h, w = rgb.shape[:2]
        qimg = QImage(rgb.data, w, h, w * 3, QImage.Format_RGB888)
        pix = QPixmap.fromImage(qimg).scaled(
            290, 150, Qt.KeepAspectRatio, Qt.SmoothTransformation
        )
        self.lbl_thumb.setPixmap(pix)
        self.lbl_filename.setText(Path(path).name)

        self.empty_widget.hide()
        self.filled_widget.show()
        self.lbl_header.setStyleSheet("""
            font-size: 14px;
            font-weight: 800;
            letter-spacing: 1px;
            color: #38BDF8;
            background: transparent;
        """)

    def clear_file(self):
        self.set_file(None)
        self.file_cleared.emit()

    def _on_browse(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            f"Select {self.title_text} Photo",
            "",
            "Image Files (*.jpg *.jpeg *.png *.webp);;All Files (*.*)",
        )
        if path:
            self.set_file(path)
            self.file_selected.emit(path)

    # ── Drag and Drop per slot ─────────────────────────────────────
    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent):
        urls = event.mimeData().urls()
        exts = {".jpg", ".jpeg", ".png", ".webp"}
        files = [u.toLocalFile() for u in urls if Path(u.toLocalFile()).suffix.lower() in exts]
        if files:
            self.set_file(files[0])
            self.file_selected.emit(files[0])
            event.acceptProposedAction()


class PageAddPhotos(QWidget):
    """
    Step 1: Add Photos (Card Mode)
    Spacious two-slot layout with Browse Files, Drag & Drop, and Swap Front/Back.
    """
    selection_changed = Signal(object, object)  # (front_path, back_path)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.front_path: Optional[str] = None
        self.back_path: Optional[str] = None

        self.setAcceptDrops(True)
        self._init_ui()

    def _init_ui(self):
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")

        container = QWidget()
        container.setStyleSheet("background: transparent;")
        main_layout = QVBoxLayout(container)
        main_layout.setContentsMargins(40, 24, 40, 24)
        main_layout.setSpacing(24)
        main_layout.setAlignment(Qt.AlignTop | Qt.AlignHCenter)

        # Header Title
        title_box = QVBoxLayout()
        title_box.setSpacing(4)
        title_box.setAlignment(Qt.AlignCenter)

        step_lbl = QLabel("STEP 1 OF 5")
        step_lbl.setStyleSheet("""
            font-size: 12px;
            font-weight: 800;
            letter-spacing: 1.5px;
            color: #38BDF8;
            background: transparent;
        """)
        step_lbl.setAlignment(Qt.AlignCenter)
        title_box.addWidget(step_lbl)

        heading = QLabel("Add Photos")
        heading.setStyleSheet("""
            font-size: 26px;
            font-weight: 800;
            color: #FFFFFF;
            letter-spacing: -0.5px;
            background: transparent;
        """)
        heading.setAlignment(Qt.AlignCenter)
        title_box.addWidget(heading)

        subheading = QLabel(
            "Add photos for the front and back sides. One image is accepted if only one side is needed."
        )
        subheading.setStyleSheet("""
            font-size: 14px;
            color: #94A3B8;
            background: transparent;
        """)
        subheading.setAlignment(Qt.AlignCenter)
        title_box.addWidget(subheading)

        main_layout.addLayout(title_box)
        main_layout.addSpacing(10)

        # Upload Cards Row
        slots_row = QHBoxLayout()
        slots_row.setSpacing(28)
        slots_row.setAlignment(Qt.AlignCenter)

        self.slot_front = UploadSlot("FRONT SIDE", "Add Front Photo")
        self.slot_front.file_selected.connect(self._on_front_selected)
        self.slot_front.file_cleared.connect(self._on_front_cleared)
        slots_row.addWidget(self.slot_front)

        self.slot_back = UploadSlot("BACK SIDE", "Add Back Photo")
        self.slot_back.file_selected.connect(self._on_back_selected)
        self.slot_back.file_cleared.connect(self._on_back_cleared)
        slots_row.addWidget(self.slot_back)

        main_layout.addLayout(slots_row)

        # Swap Button between slots
        swap_box = QHBoxLayout()
        swap_box.setAlignment(Qt.AlignCenter)

        self.btn_swap = QPushButton("  ⇄  Swap Front & Back  ")
        self.btn_swap.setCursor(Qt.PointingHandCursor)
        self.btn_swap.setFixedHeight(40)
        self.btn_swap.setStyleSheet("""
            QPushButton {
                background-color: #1E293B;
                color: #38BDF8;
                border: 1px solid #334155;
                border-radius: 20px;
                font-size: 13px;
                font-weight: 700;
                padding: 0 20px;
            }
            QPushButton:hover {
                background-color: #334155;
                border-color: #38BDF8;
                color: #FFFFFF;
            }
        """)
        self.btn_swap.clicked.connect(self.swap_sides)
        self.btn_swap.hide()
        swap_box.addWidget(self.btn_swap)

        main_layout.addLayout(swap_box)

        scroll.setWidget(container)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

    def _on_front_selected(self, path: str):
        self.front_path = path
        self._check_swap_visible()
        self.selection_changed.emit(self.front_path, self.back_path)

    def _on_front_cleared(self):
        self.front_path = None
        self._check_swap_visible()
        self.selection_changed.emit(self.front_path, self.back_path)

    def _on_back_selected(self, path: str):
        self.back_path = path
        self._check_swap_visible()
        self.selection_changed.emit(self.front_path, self.back_path)

    def _on_back_cleared(self):
        self.back_path = None
        self._check_swap_visible()
        self.selection_changed.emit(self.front_path, self.back_path)

    def _check_swap_visible(self):
        if self.front_path and self.back_path:
            self.btn_swap.show()
        else:
            self.btn_swap.hide()

    def swap_sides(self):
        """Swaps Front and Back file assignments."""
        self.front_path, self.back_path = self.back_path, self.front_path
        self.slot_front.set_file(self.front_path)
        self.slot_back.set_file(self.back_path)
        self._check_swap_visible()
        self.selection_changed.emit(self.front_path, self.back_path)

    def set_files(self, front: Optional[str], back: Optional[str]):
        self.front_path = front
        self.back_path = back
        self.slot_front.set_file(front)
        self.slot_back.set_file(back)
        self._check_swap_visible()

    # ── Page-level Drag and Drop (handles dropping two files at once) ──
    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent):
        urls = event.mimeData().urls()
        exts = {".jpg", ".jpeg", ".png", ".webp"}
        files = [u.toLocalFile() for u in urls if Path(u.toLocalFile()).suffix.lower() in exts]
        if not files:
            return

        if len(files) >= 2:
            self.front_path = files[0]
            self.back_path = files[1]
            self.slot_front.set_file(self.front_path)
            self.slot_back.set_file(self.back_path)
        elif len(files) == 1:
            if not self.front_path:
                self.front_path = files[0]
                self.slot_front.set_file(self.front_path)
            else:
                self.back_path = files[0]
                self.slot_back.set_file(self.back_path)

        self._check_swap_visible()
        self.selection_changed.emit(self.front_path, self.back_path)
        event.acceptProposedAction()
