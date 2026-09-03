"""
Document Mode Workflow: Multi-Page Document Management.
Each image represents one page. Allows page reordering, rotation,
deletion, adding pages, processing, previewing, and exporting multi-page PDF.
"""
from typing import List, Optional
from pathlib import Path
import cv2
import numpy as np
from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QPixmap, QImage, QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QFrame,
    QScrollArea,
    QFileDialog,
    QMessageBox,
    QGridLayout,
    QSizePolicy,
)

from app.core.pipeline import FormatterPipeline
from app.core.models import ProcessingMode, ProcessedImage
from app.export.pdf_export import PdfExporter
from app.export.printing import PrintManager
from app.export.docx_export import DocxExporter
from app.ui.corner_editor import CornerEditorDialog
from app.utils.image_io import load_image_safe
from app.utils.logger import get_logger

logger = get_logger("document_workflow")


class PageItemCard(QFrame):
    """Card representing one document page in the queue."""
    move_left = Signal(int)
    move_right = Signal(int)
    delete_page = Signal(int)
    rotate_page = Signal(int)
    edit_page = Signal(int)

    def __init__(self, index: int, source_path: str, processed: Optional[ProcessedImage] = None, parent=None):
        super().__init__(parent)
        self.page_index = index
        self.source_path = source_path
        self.processed = processed

        self.setFixedSize(200, 310)
        self._init_ui()

    def _init_ui(self):
        self.setStyleSheet("""
            PageItemCard {
                background-color: #14141A;
                border: 1px solid #24242E;
                border-radius: 12px;
            }
            PageItemCard:hover {
                border-color: #38BDF8;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        # Header with Page Number
        head = QHBoxLayout()
        self.lbl_num = QLabel(f"Page {self.page_index + 1}")
        self.lbl_num.setStyleSheet("font-size: 13px; font-weight: 800; color: #38BDF8; background: transparent;")
        head.addWidget(self.lbl_num)
        head.addStretch()

        btn_del = QPushButton("✕")
        btn_del.setCursor(Qt.PointingHandCursor)
        btn_del.setFixedSize(22, 22)
        btn_del.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: #64748B;
                border: none;
                font-weight: 800;
                font-size: 12px;
            }
            QPushButton:hover { color: #EF4444; }
        """)
        btn_del.clicked.connect(lambda: self.delete_page.emit(self.page_index))
        head.addWidget(btn_del)
        layout.addLayout(head)

        # Thumbnail
        self.lbl_thumb = QLabel()
        self.lbl_thumb.setFixedSize(176, 190)
        self.lbl_thumb.setAlignment(Qt.AlignCenter)
        self.lbl_thumb.setStyleSheet("""
            background-color: #0A0A0E;
            border: 1px solid #1E1E26;
            border-radius: 6px;
        """)
        self._update_thumb()
        layout.addWidget(self.lbl_thumb, alignment=Qt.AlignCenter)

        # Page filename
        lbl_name = QLabel(Path(self.source_path).name)
        lbl_name.setStyleSheet("font-size: 11px; color: #94A3B8; background: transparent;")
        lbl_name.setAlignment(Qt.AlignCenter)
        layout.addWidget(lbl_name)

        # Bottom Actions: Move Left, Rotate, Move Right
        action_row = QHBoxLayout()
        action_row.setSpacing(6)
        action_row.setAlignment(Qt.AlignCenter)

        btn_left = QPushButton("◀")
        btn_left.setCursor(Qt.PointingHandCursor)
        btn_left.setFixedSize(28, 28)
        btn_left.setStyleSheet(self._btn_style())
        btn_left.clicked.connect(lambda: self.move_left.emit(self.page_index))
        action_row.addWidget(btn_left)

        btn_rot = QPushButton("↻")
        btn_rot.setCursor(Qt.PointingHandCursor)
        btn_rot.setFixedSize(28, 28)
        btn_rot.setStyleSheet(self._btn_style())
        btn_rot.clicked.connect(lambda: self.rotate_page.emit(self.page_index))
        action_row.addWidget(btn_rot)

        btn_edit = QPushButton("✏")
        btn_edit.setCursor(Qt.PointingHandCursor)
        btn_edit.setFixedSize(28, 28)
        btn_edit.setStyleSheet(self._btn_style())
        btn_edit.clicked.connect(lambda: self.edit_page.emit(self.page_index))
        action_row.addWidget(btn_edit)

        btn_right = QPushButton("▶")
        btn_right.setCursor(Qt.PointingHandCursor)
        btn_right.setFixedSize(28, 28)
        btn_right.setStyleSheet(self._btn_style())
        btn_right.clicked.connect(lambda: self.move_right.emit(self.page_index))
        action_row.addWidget(btn_right)

        layout.addLayout(action_row)

    def _btn_style(self):
        return """
            QPushButton {
                background-color: #1E1E26;
                color: #CBD5E1;
                border: 1px solid #2E2E3A;
                border-radius: 6px;
                font-weight: 700;
                font-size: 11px;
            }
            QPushButton:hover {
                background-color: #2E2E3A;
                color: #FFFFFF;
                border-color: #38BDF8;
            }
        """

    def _update_thumb(self):
        img = None
        if self.processed and self.processed.final_image is not None:
            img = self.processed.final_image
        else:
            img = load_image_safe(self.source_path)

        if img is not None:
            rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
            h, w = rgb.shape[:2]
            qimg = QImage(rgb.data, w, h, w * 3, QImage.Format_RGB888)
            pix = QPixmap.fromImage(qimg).scaled(
                170, 184, Qt.KeepAspectRatio, Qt.SmoothTransformation
            )
            self.lbl_thumb.setPixmap(pix)


class DocumentWorkflow(QWidget):
    """
    Document Mode Workflow.
    Manages multi-page document queues: reordering, rotation, processing,
    and multi-page PDF generation.
    """
    def __init__(self, pipeline: FormatterPipeline, parent=None):
        super().__init__(parent)
        self.pipeline = pipeline
        self.page_paths: List[str] = []

        self.setAcceptDrops(True)
        self._init_ui()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(36, 24, 36, 24)
        main_layout.setSpacing(20)

        # Top Header Bar
        top_bar = QHBoxLayout()
        title_box = QVBoxLayout()
        title_box.setSpacing(2)

        mode_lbl = QLabel("DOCUMENT MODE")
        mode_lbl.setStyleSheet("font-size: 11px; font-weight: 800; letter-spacing: 1.5px; color: #818CF8; background: transparent;")
        title_box.addWidget(mode_lbl)

        title = QLabel("Page Management")
        title.setStyleSheet("font-size: 24px; font-weight: 800; color: #FFFFFF; letter-spacing: -0.5px; background: transparent;")
        title_box.addWidget(title)

        desc = QLabel("Each uploaded image is treated as a separate page. Reorder, rotate, or correct before exporting.")
        desc.setStyleSheet("font-size: 13px; color: #94A3B8; background: transparent;")
        title_box.addWidget(desc)
        top_bar.addLayout(title_box)

        top_bar.addStretch()

        # Top Actions: Add Pages & Process All
        btn_add = QPushButton("＋  Add Pages")
        btn_add.setCursor(Qt.PointingHandCursor)
        btn_add.setFixedHeight(40)
        btn_add.setStyleSheet("""
            QPushButton {
                background-color: #2563EB;
                color: #FFFFFF;
                border: none;
                border-radius: 8px;
                font-weight: 700;
                font-size: 13px;
                padding: 0 18px;
            }
            QPushButton:hover { background-color: #1D4ED8; }
        """)
        btn_add.clicked.connect(self._on_add_pages)
        top_bar.addWidget(btn_add)

        main_layout.addLayout(top_bar)

        # ── Scrollable Grid of Pages ──
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { background-color: #0F0F14; border: 1px solid #1E1E26; border-radius: 12px; }")

        self.grid_container = QWidget()
        self.grid_container.setStyleSheet("background-color: #0F0F14;")
        self.grid_layout = QGridLayout(self.grid_container)
        self.grid_layout.setContentsMargins(24, 24, 24, 24)
        self.grid_layout.setSpacing(20)
        self.grid_layout.setAlignment(Qt.AlignTop | Qt.AlignLeft)

        scroll.setWidget(self.grid_container)
        main_layout.addWidget(scroll, stretch=1)

        # ── Bottom Action Bar ──
        bot_bar = QFrame()
        bot_bar.setFixedHeight(64)
        bot_bar.setStyleSheet("""
            QFrame {
                background-color: #14141A;
                border: 1px solid #24242E;
                border-radius: 12px;
            }
        """)
        b_layout = QHBoxLayout(bot_bar)
        b_layout.setContentsMargins(24, 0, 24, 0)
        b_layout.setSpacing(16)

        self.lbl_status = QLabel("0 pages loaded")
        self.lbl_status.setStyleSheet("font-size: 13px; font-weight: 600; color: #94A3B8; background: transparent;")
        b_layout.addWidget(self.lbl_status)

        b_layout.addStretch()

        self.btn_clear_all = QPushButton("Clear All")
        self.btn_clear_all.setCursor(Qt.PointingHandCursor)
        self.btn_clear_all.setFixedHeight(38)
        self.btn_clear_all.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: #EF4444;
                border: 1px solid #7F1D1D;
                border-radius: 8px;
                font-weight: 600;
                font-size: 12px;
                padding: 0 14px;
            }
            QPushButton:hover { background-color: #450A0A; }
        """)
        self.btn_clear_all.clicked.connect(self.clear_all)
        b_layout.addWidget(self.btn_clear_all)

        self.btn_export_pdf = QPushButton("Export Multi-Page PDF")
        self.btn_export_pdf.setCursor(Qt.PointingHandCursor)
        self.btn_export_pdf.setFixedHeight(42)
        self.btn_export_pdf.setStyleSheet("""
            QPushButton {
                background-color: #10B981;
                color: #FFFFFF;
                border: none;
                border-radius: 8px;
                font-weight: 700;
                font-size: 13px;
                padding: 0 20px;
            }
            QPushButton:hover { background-color: #059669; }
            QPushButton:disabled { background-color: #1E293B; color: #475569; }
        """)
        self.btn_export_pdf.clicked.connect(self._on_export_pdf)
        b_layout.addWidget(self.btn_export_pdf)

        main_layout.addWidget(bot_bar)

        self._refresh_grid()

    def _on_add_pages(self):
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "Select Document Pages",
            "",
            "Image Files (*.jpg *.jpeg *.png *.webp);;All Files (*.*)",
        )
        if files:
            self.add_files(files)

    def add_files(self, files: List[str]):
        self.pipeline.set_mode(ProcessingMode.SHEET)
        new_processed = self.pipeline.add_sheet_pages(files)
        self.page_paths.extend(files)
        self._refresh_grid()

    def _refresh_grid(self):
        # Clear existing cards
        while self.grid_layout.count():
            item = self.grid_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        pages = self.pipeline.sheet_queue.pages
        cols = 4

        for idx, path in enumerate(self.page_paths):
            proc = pages[idx] if idx < len(pages) else None
            card = PageItemCard(idx, path, proc, self)
            card.move_left.connect(self._on_move_left)
            card.move_right.connect(self._on_move_right)
            card.delete_page.connect(self._on_delete_page)
            card.rotate_page.connect(self._on_rotate_page)
            card.edit_page.connect(self._on_edit_page)

            row = idx // cols
            col = idx % cols
            self.grid_layout.addWidget(card, row, col)

        count = len(self.page_paths)
        self.lbl_status.setText(f"{count} page{'s' if count != 1 else ''} loaded in document sequence")
        self.btn_export_pdf.setEnabled(count > 0)
        self.btn_clear_all.setEnabled(count > 0)

    def _on_move_left(self, idx: int):
        if idx > 0:
            # Swap with previous
            self.page_paths[idx - 1], self.page_paths[idx] = self.page_paths[idx], self.page_paths[idx - 1]
            self.pipeline.move_sheet_page(idx, idx - 1)
            self._refresh_grid()

    def _on_move_right(self, idx: int):
        if idx < len(self.page_paths) - 1:
            # Swap with next
            self.page_paths[idx + 1], self.page_paths[idx] = self.page_paths[idx], self.page_paths[idx + 1]
            self.pipeline.move_sheet_page(idx, idx + 1)
            self._refresh_grid()

    def _on_delete_page(self, idx: int):
        if 0 <= idx < len(self.page_paths):
            self.page_paths.pop(idx)
            self.pipeline.remove_sheet_page(idx)
            self._refresh_grid()

    def _on_rotate_page(self, idx: int):
        pages = self.pipeline.sheet_queue.pages
        if 0 <= idx < len(pages):
            page = pages[idx]
            self.pipeline.rotate_item(page, 90)
            self._refresh_grid()

    def _on_edit_page(self, idx: int):
        pages = self.pipeline.sheet_queue.pages
        if 0 <= idx < len(pages):
            page = pages[idx]
            dialog = CornerEditorDialog(page, self)
            if dialog.exec():
                new_corners = dialog.get_result_corners()
                self.pipeline.update_item_corners(page, new_corners)
                self._refresh_grid()

    def _on_export_pdf(self):
        if not self.pipeline.sheet_queue.pages:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Document PDF", "document_output.pdf", "PDF Document (*.pdf)"
        )
        if not path:
            return
        ok = PdfExporter.export_sheet_queue(self.pipeline.sheet_queue, path)
        if ok:
            QMessageBox.information(self, "PDF Exported", f"Multi-page PDF exported successfully to:\n{path}")
        else:
            QMessageBox.critical(self, "Export Failed", "Could not export document PDF.")

    def clear_all(self):
        self.page_paths.clear()
        self.pipeline.reset()
        self._refresh_grid()

    # ── Drag & Drop support for document mode ──
    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent):
        urls = event.mimeData().urls()
        exts = {".jpg", ".jpeg", ".png", ".webp"}
        files = [u.toLocalFile() for u in urls if Path(u.toLocalFile()).suffix.lower() in exts]
        if files:
            self.add_files(files)
            event.acceptProposedAction()
