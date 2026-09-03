"""
Upload and Image Intake View.
Supports Drag & Drop, file browser, Card Front/Back slots, Sheet page queue,
physical output format profile selection (Card vs Long Form), and asynchronous processing.
"""
from pathlib import Path
from typing import List, Optional
import cv2
from PySide6.QtCore import Qt, Signal, QThread, QObject, QPropertyAnimation, QEasingCurve, QSize
from PySide6.QtGui import QPixmap, QImage, QDragEnterEvent, QDropEvent, QColor
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QFrame,
    QFileDialog,
    QProgressBar,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QButtonGroup,
    QSizePolicy,
    QGraphicsDropShadowEffect,
)

from app.core.profiles import FormatProfile, CARD_PROFILE, LONG_FORM_PROFILE, ProfileRegistry
from app.core.models import ProcessingMode, ProcessedImage
from app.core.pipeline import FormatterPipeline
from app.utils.logger import get_logger

logger = get_logger("upload_view")


class ProcessingWorker(QObject):
    """Background worker for non-blocking CV processing."""
    finished = Signal()
    progress = Signal(int, str)
    error = Signal(str)

    def __init__(self, pipeline: FormatterPipeline, files: List[str]):
        super().__init__()
        self.pipeline = pipeline
        self.files = files

    def run(self):
        try:
            total = len(self.files)
            if self.pipeline.mode == ProcessingMode.CARD:
                if len(self.files) >= 1:
                    self.progress.emit(25, f"Processing Front Document ({self.pipeline.active_card_profile.name})...")
                    self.pipeline.set_card_front(self.files[0])
                if len(self.files) >= 2:
                    self.progress.emit(65, f"Processing Back Document ({self.pipeline.active_card_profile.name})...")
                    self.pipeline.set_card_back(self.files[1])
                self.progress.emit(90, "Synchronizing Duplex dimensions...")
                self.pipeline.card_processor.synchronize_pair(self.pipeline.card_pair)
            else:
                for idx, f in enumerate(self.files):
                    pct = int(15 + 75 * (idx / float(total)))
                    self.progress.emit(pct, f"Processing Sheet Page {idx + 1} of {total}...")
                    self.pipeline.add_sheet_pages([f])

            self.progress.emit(100, "Processing Complete.")
            self.finished.emit()
        except Exception as e:
            logger.error(f"Processing worker encountered error: {e}", exc_info=True)
            self.error.emit(str(e))


class DropZoneFrame(QFrame):
    """Drag and drop intake frame with enhanced visual design."""
    files_dropped = Signal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setProperty("class", "drop-zone")
        self.setFixedHeight(170)

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)
        layout.setSpacing(8)

        icon_label = QLabel("📁")
        icon_label.setStyleSheet("font-size: 32px; background: transparent;")
        icon_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(icon_label)

        text_label = QLabel("Drag & Drop Customer Photographs Here")
        text_label.setStyleSheet("font-size: 16px; font-weight: 700; color: #F0F0F5; background: transparent;")
        text_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(text_label)

        sub_label = QLabel("or click Browse Files below")
        sub_label.setStyleSheet("font-size: 12px; color: #66667A; background: transparent;")
        sub_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(sub_label)

        hint_label = QLabel("Supports JPG, JPEG, PNG, WEBP — Direct from WhatsApp / Camera")
        hint_label.setStyleSheet("font-size: 11px; color: #444455; background: transparent;")
        hint_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(hint_label)

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            self.setProperty("class", "drop-zone drop-zone-active")
            self.style().polish(self)
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragLeaveEvent(self, event):
        self.setProperty("class", "drop-zone")
        self.style().polish(self)
        super().dragLeaveEvent(event)

    def dropEvent(self, event: QDropEvent):
        self.setProperty("class", "drop-zone")
        self.style().polish(self)
        urls = event.mimeData().urls()
        valid_extensions = {".jpg", ".jpeg", ".png", ".webp"}
        file_paths = []
        for url in urls:
            p = Path(url.toLocalFile())
            if p.suffix.lower() in valid_extensions:
                file_paths.append(str(p))

        if file_paths:
            self.files_dropped.emit(file_paths)
            event.acceptProposedAction()
        else:
            event.ignore()


class CardSlotPanel(QFrame):
    """A visually refined card slot for front/back image selection."""

    def __init__(self, title: str, is_front: bool, parent=None):
        super().__init__(parent)
        self.setProperty("class", "panel-card")
        self.setFixedWidth(340)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        # Header
        header_row = QHBoxLayout()
        header_row.setSpacing(8)

        dot = QLabel()
        dot.setFixedSize(8, 8)
        dot_color = "#6366F1" if is_front else "#818CF8"
        dot.setStyleSheet(f"background-color: {dot_color}; border-radius: 4px;")
        header_row.addWidget(dot, alignment=Qt.AlignVCenter)

        header = QLabel(title)
        header.setStyleSheet("font-size: 13px; font-weight: 700; color: #F0F0F5; background: transparent; letter-spacing: 0.3px;")
        header_row.addWidget(header)
        header_row.addStretch()
        layout.addLayout(header_row)

        # Image Preview
        self.img_label = QLabel()
        self.img_label.setFixedHeight(160)
        self.img_label.setStyleSheet("""
            background-color: #121212;
            border: 1px dashed #2A2A32;
            border-radius: 12px;
            color: #444455;
            font-size: 13px;
        """)
        self.img_label.setAlignment(Qt.AlignCenter)
        self.img_label.setText("Drop Image Here")
        layout.addWidget(self.img_label)

        # Filename
        self.file_label = QLabel("—")
        self.file_label.setStyleSheet("font-size: 11px; color: #66667A; background: transparent;")
        self.file_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.file_label)

    def set_preview(self, file_path: str):
        p = Path(file_path)
        self.file_label.setText(p.name)
        pix = QPixmap(str(p)).scaled(300, 155, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.img_label.setPixmap(pix)

    def clear_preview(self, hint_text: str = "Drop Image Here"):
        self.file_label.setText("—")
        self.img_label.setText(hint_text)
        self.img_label.setPixmap(QPixmap())


class UploadView(QWidget):
    """View managing image file intake, queues, slots, format profile selection, and launching processing."""

    processing_completed = Signal()
    back_to_mode = Signal()

    def __init__(self, pipeline: FormatterPipeline, parent=None):
        super().__init__(parent)
        self.pipeline = pipeline
        self.pending_files: List[str] = []
        self.thread: Optional[QThread] = None
        self.worker: Optional[ProcessingWorker] = None

        self.setup_ui()

    def setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(32, 16, 32, 20)
        main_layout.setSpacing(14)

        # ── 1. Top Navigation Bar ──
        top_bar = QHBoxLayout()
        top_bar.setSpacing(12)

        btn_back = QPushButton("← Change Mode")
        btn_back.setProperty("class", "btn-ghost")
        btn_back.setFixedHeight(34)
        top_bar.addWidget(btn_back)

        top_bar.addSpacing(4)

        self.lbl_mode_title = QLabel("Card Mode Intake")
        self.lbl_mode_title.setStyleSheet("font-size: 18px; font-weight: 700; color: #F0F0F5; background: transparent;")
        top_bar.addWidget(self.lbl_mode_title)

        top_bar.addStretch()

        # Format Profile Selector
        self.format_selector_widget = QWidget()
        self.format_selector_widget.setStyleSheet("background: transparent;")
        fmt_layout = QHBoxLayout(self.format_selector_widget)
        fmt_layout.setContentsMargins(0, 0, 0, 0)
        fmt_layout.setSpacing(8)

        lbl_fmt = QLabel("Output Format:")
        lbl_fmt.setStyleSheet("font-size: 12px; font-weight: 600; color: #66667A; background: transparent;")
        fmt_layout.addWidget(lbl_fmt)

        self.fmt_group = QButtonGroup(self)
        self.fmt_group.setExclusive(True)

        self.btn_fmt_card = QPushButton(f"Card  ({CARD_PROFILE.dimensions_mm_str})")
        self.btn_fmt_card.setProperty("class", "chip-filter")
        self.btn_fmt_card.setCheckable(True)
        self.btn_fmt_card.setChecked(True)
        self.btn_fmt_card.clicked.connect(lambda: self.on_format_changed(CARD_PROFILE))
        self.fmt_group.addButton(self.btn_fmt_card)
        fmt_layout.addWidget(self.btn_fmt_card)

        self.btn_fmt_long = QPushButton(f"Long Form  ({LONG_FORM_PROFILE.dimensions_mm_str})")
        self.btn_fmt_long.setProperty("class", "chip-filter")
        self.btn_fmt_long.setCheckable(True)
        self.btn_fmt_long.clicked.connect(lambda: self.on_format_changed(LONG_FORM_PROFILE))
        self.fmt_group.addButton(self.btn_fmt_long)
        fmt_layout.addWidget(self.btn_fmt_long)

        top_bar.addWidget(self.format_selector_widget)

        btn_browse = QPushButton("  Browse Files...  ")
        btn_browse.setFixedHeight(34)
        btn_browse.clicked.connect(self.on_browse_files)
        top_bar.addWidget(btn_browse)

        main_layout.addLayout(top_bar)

        # ── 2. Drop Zone ──
        self.drop_zone = DropZoneFrame(self)
        self.drop_zone.files_dropped.connect(self.on_files_added)
        main_layout.addWidget(self.drop_zone)

        # ── 3. Slots / Queue Container ──
        self.queue_container = QWidget()
        self.queue_container.setStyleSheet("background: transparent;")
        self.queue_layout = QVBoxLayout(self.queue_container)
        self.queue_layout.setContentsMargins(0, 0, 0, 0)
        self.queue_layout.setSpacing(12)
        main_layout.addWidget(self.queue_container, stretch=1)

        # Card Mode UI
        self.card_slots_widget = QWidget()
        self.card_slots_widget.setStyleSheet("background: transparent;")
        card_slots_layout = QHBoxLayout(self.card_slots_widget)
        card_slots_layout.setSpacing(24)
        card_slots_layout.setAlignment(Qt.AlignCenter)

        self.slot_front = CardSlotPanel("FRONT SIDE", is_front=True)
        self.slot_back = CardSlotPanel("BACK SIDE", is_front=False)
        card_slots_layout.addWidget(self.slot_front)

        # Swap Button
        swap_container = QWidget()
        swap_container.setStyleSheet("background: transparent;")
        swap_layout = QVBoxLayout(swap_container)
        swap_layout.setAlignment(Qt.AlignCenter)
        swap_layout.setSpacing(0)

        self.btn_swap = QPushButton("⇄")
        self.btn_swap.setFixedSize(44, 44)
        self.btn_swap.setToolTip("Swap Front and Back")
        self.btn_swap.setStyleSheet("""
            QPushButton {
                background-color: #202026;
                border: 1px solid #34343E;
                border-radius: 22px;
                font-size: 18px;
                color: #9A9AAA;
            }
            QPushButton:hover {
                background-color: #2E2E36;
                border-color: #6366F1;
                color: #FFFFFF;
            }
            QPushButton:pressed {
                background-color: #6366F1;
            }
        """)
        self.btn_swap.clicked.connect(self.on_swap_cards)
        swap_layout.addWidget(self.btn_swap)
        card_slots_layout.addWidget(swap_container)

        card_slots_layout.addWidget(self.slot_back)
        self.queue_layout.addWidget(self.card_slots_widget)

        # Sheet Mode List
        self.sheet_list = QListWidget()
        self.sheet_list.hide()
        self.queue_layout.addWidget(self.sheet_list)

        # Sheet Action Bar
        self.sheet_toolbar = QWidget()
        self.sheet_toolbar.setStyleSheet("background: transparent;")
        sheet_tool_layout = QHBoxLayout(self.sheet_toolbar)
        sheet_tool_layout.setContentsMargins(0, 0, 0, 0)
        sheet_tool_layout.setSpacing(8)

        self.btn_move_up = QPushButton("↑ Move Up")
        self.btn_move_up.setFixedHeight(34)
        sheet_tool_layout.addWidget(self.btn_move_up)

        self.btn_move_down = QPushButton("↓ Move Down")
        self.btn_move_down.setFixedHeight(34)
        sheet_tool_layout.addWidget(self.btn_move_down)

        sheet_tool_layout.addSpacing(12)

        self.btn_remove_sheet = QPushButton("✕ Remove Page")
        self.btn_remove_sheet.setProperty("class", "btn-danger")
        self.btn_remove_sheet.setFixedHeight(34)
        sheet_tool_layout.addWidget(self.btn_remove_sheet)

        sheet_tool_layout.addStretch()
        self.sheet_toolbar.hide()
        self.queue_layout.addWidget(self.sheet_toolbar)

        # ── 4. Progress Bar ──
        progress_container = QWidget()
        progress_container.setStyleSheet("background: transparent;")
        progress_layout = QVBoxLayout(progress_container)
        progress_layout.setContentsMargins(0, 0, 0, 0)
        progress_layout.setSpacing(6)

        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        self.progress_bar.setFixedHeight(8)
        self.progress_bar.hide()
        progress_layout.addWidget(self.progress_bar)

        self.lbl_progress_status = QLabel("")
        self.lbl_progress_status.setStyleSheet("font-size: 12px; color: #66667A; background: transparent;")
        self.lbl_progress_status.setAlignment(Qt.AlignCenter)
        self.lbl_progress_status.hide()
        progress_layout.addWidget(self.lbl_progress_status)

        self._progress_container = progress_container
        main_layout.addWidget(progress_container)

        # ── 5. Bottom Action Bar ──
        bottom_bar = QHBoxLayout()
        bottom_bar.setSpacing(12)

        self.btn_clear = QPushButton("Clear All")
        self.btn_clear.setProperty("class", "btn-ghost")
        self.btn_clear.setFixedHeight(42)
        bottom_bar.addWidget(self.btn_clear)

        bottom_bar.addStretch()

        file_count_label = QLabel("")
        file_count_label.setStyleSheet("font-size: 12px; color: #444455; background: transparent;")
        bottom_bar.addWidget(file_count_label)
        self._file_count_label = file_count_label

        self.btn_process = QPushButton("   Process & Format →   ")
        self.btn_process.setProperty("class", "btn-primary")
        self.btn_process.setFixedHeight(46)
        self.btn_process.setMinimumWidth(220)
        self.btn_process.setEnabled(False)
        self.btn_process.clicked.connect(self.start_processing)
        bottom_bar.addWidget(self.btn_process)

        main_layout.addLayout(bottom_bar)

        # Connect
        btn_back.clicked.connect(self.back_to_mode.emit)

    def on_format_changed(self, profile: FormatProfile):
        self.pipeline.set_card_profile(profile)
        self.btn_fmt_card.setChecked(profile.id == CARD_PROFILE.id)
        self.btn_fmt_long.setChecked(profile.id == LONG_FORM_PROFILE.id)
        logger.info(f"Format profile changed in UploadView: {profile.name}")

    def refresh_mode(self):
        """Refreshes UI layout based on active pipeline mode."""
        self.pending_files.clear()
        self.pipeline.reset()
        if self.pipeline.mode == ProcessingMode.CARD:
            self.lbl_mode_title.setText("Card & Long-Form Intake")
            self.format_selector_widget.show()
            self.card_slots_widget.show()
            self.sheet_list.hide()
            self.sheet_toolbar.hide()
            self.btn_fmt_card.setChecked(self.pipeline.active_card_profile.id == CARD_PROFILE.id)
            self.btn_fmt_long.setChecked(self.pipeline.active_card_profile.id == LONG_FORM_PROFILE.id)
        else:
            self.lbl_mode_title.setText("Sheet Mode — Multi-Page Intake")
            self.format_selector_widget.hide()
            self.card_slots_widget.hide()
            self.sheet_list.show()
            self.sheet_toolbar.show()
        self._update_display()

    def on_browse_files(self):
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "Select Document / Card Images",
            "",
            "Image Files (*.jpg *.jpeg *.png *.webp)"
        )
        if files:
            self.on_files_added(files)

    def on_files_added(self, new_files: List[str]):
        if self.pipeline.mode == ProcessingMode.CARD:
            combined = (self.pending_files + new_files)[:2]
            self.pending_files = combined
        else:
            self.pending_files.extend(new_files)

        self._update_display()

    def on_swap_cards(self):
        if len(self.pending_files) == 2:
            self.pending_files[0], self.pending_files[1] = self.pending_files[1], self.pending_files[0]
            self._update_display()

    def on_sheet_move_up(self):
        row = self.sheet_list.currentRow()
        if row > 0:
            self.pending_files[row - 1], self.pending_files[row] = self.pending_files[row], self.pending_files[row - 1]
            self._update_display()
            self.sheet_list.setCurrentRow(row - 1)

    def on_sheet_move_down(self):
        row = self.sheet_list.currentRow()
        if 0 <= row < len(self.pending_files) - 1:
            self.pending_files[row], self.pending_files[row + 1] = self.pending_files[row + 1], self.pending_files[row]
            self._update_display()
            self.sheet_list.setCurrentRow(row + 1)

    def on_sheet_remove(self):
        row = self.sheet_list.currentRow()
        if 0 <= row < len(self.pending_files):
            self.pending_files.pop(row)
            self._update_display()

    def on_clear_all(self):
        self.pending_files.clear()
        self.pipeline.reset()
        self._update_display()

    def _update_display(self):
        has_files = len(self.pending_files) > 0
        self.btn_process.setEnabled(has_files)

        count = len(self.pending_files)
        if count > 0:
            self._file_count_label.setText(f"{count} file{'s' if count != 1 else ''} selected")
        else:
            self._file_count_label.setText("")

        if self.pipeline.mode == ProcessingMode.CARD:
            if len(self.pending_files) >= 1:
                self.slot_front.set_preview(self.pending_files[0])
            else:
                self.slot_front.clear_preview("Drop Front Image Here")

            if len(self.pending_files) >= 2:
                self.slot_back.set_preview(self.pending_files[1])
            else:
                self.slot_back.clear_preview("Drop Back Image (Optional)")
        else:
            self.sheet_list.clear()
            for idx, f in enumerate(self.pending_files):
                p = Path(f)
                size_kb = p.stat().st_size // 1024
                item = QListWidgetItem(f"  Page {idx + 1:02d}     {p.name}     ({size_kb} KB)")
                item.setSizeHint(QSize(0, 44))
                self.sheet_list.addItem(item)

    def start_processing(self):
        if not self.pending_files:
            return

        self.progress_bar.setValue(0)
        self.progress_bar.show()
        self.lbl_progress_status.setText("Initializing CV Pipeline...")
        self.lbl_progress_status.show()
        self.btn_process.setEnabled(False)

        self.thread = QThread()
        self.worker = ProcessingWorker(self.pipeline, self.pending_files)
        self.worker.moveToThread(self.thread)

        self.thread.started.connect(self.worker.run)
        self.worker.progress.connect(self.on_worker_progress)
        self.worker.finished.connect(self.on_worker_finished)
        self.worker.error.connect(self.on_worker_error)

        self.thread.start()

    def on_worker_progress(self, val: int, msg: str):
        self.progress_bar.setValue(val)
        self.lbl_progress_status.setText(msg)

    def on_worker_finished(self):
        self.thread.quit()
        self.thread.wait()
        self.progress_bar.hide()
        self.lbl_progress_status.hide()
        self.btn_process.setEnabled(True)
        self.processing_completed.emit()

    def on_worker_error(self, err_msg: str):
        self.thread.quit()
        self.thread.wait()
        self.progress_bar.hide()
        self.lbl_progress_status.hide()
        self.btn_process.setEnabled(True)
        QMessageBox.critical(self, "Processing Error", f"Failed to process images:\n{err_msg}")
