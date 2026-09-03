"""
Step 3 of 5: Processing (Card Mode).
Displays clean, non-technical step checklist, review prompts if needed,
and hides technical diagnostic details under an expandable drawer.
"""
from typing import Optional, List
from PySide6.QtCore import Qt, Signal, QThread, QObject
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QFrame,
    QProgressBar,
    QScrollArea,
    QSizePolicy,
)

from app.core.pipeline import FormatterPipeline
from app.core.profiles import FormatProfile
from app.utils.logger import get_logger

logger = get_logger("page_process")


class ProcessingWorker(QObject):
    """Background worker for non-blocking CV processing."""
    progress_step = Signal(str, str)  # (status, message)
    finished = Signal(bool, str)       # (success, error_msg)

    def __init__(self, pipeline: FormatterPipeline, front: Optional[str], back: Optional[str], profile: FormatProfile):
        super().__init__()
        self.pipeline = pipeline
        self.front = front
        self.back = back
        self.profile = profile

    def run(self):
        try:
            if self.front is not None:
                self.progress_step.emit("done", "Front image loaded")
                self.progress_step.emit("active", "Detecting Front boundary...")
                # Pipeline processing
                self.pipeline.set_card_images(self.front, None, profile=self.profile)
                self.progress_step.emit("done", "Front boundary detected & corrected")
                self.progress_step.emit("done", "Front normalized")

            if self.back is not None:
                self.progress_step.emit("active", "Processing Back side...")
                # Both sides processed
                self.pipeline.set_card_images(self.front, self.back, profile=self.profile)
                self.progress_step.emit("done", "Back boundary detected & corrected")
                self.progress_step.emit("done", "Back normalized")

            self.progress_step.emit("done", "Processing complete")
            self.finished.emit(True, "")
        except Exception as e:
            logger.error(f"Processing error: {e}", exc_info=True)
            self.finished.emit(False, str(e))


class PageProcess(QWidget):
    """
    Step 3: Processing (Card Mode)
    Clean progress feedback without exposing raw technical numbers.
    """
    processing_completed = Signal(bool)
    review_side_requested = Signal(str)  # "front" or "back"

    def __init__(self, pipeline: FormatterPipeline, parent=None):
        super().__init__(parent)
        self.pipeline = pipeline
        self.front_path: Optional[str] = None
        self.back_path: Optional[str] = None
        self.profile: Optional[FormatProfile] = None

        self.thread: Optional[QThread] = None
        self.worker: Optional[ProcessingWorker] = None
        self._is_done = False

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

        step_lbl = QLabel("STEP 3 OF 5")
        step_lbl.setStyleSheet("font-size: 12px; font-weight: 800; letter-spacing: 1.5px; color: #38BDF8; background: transparent;")
        step_lbl.setAlignment(Qt.AlignCenter)
        title_box.addWidget(step_lbl)

        self.heading = QLabel("Processing Card")
        self.heading.setStyleSheet("font-size: 26px; font-weight: 800; color: #FFFFFF; letter-spacing: -0.5px; background: transparent;")
        self.heading.setAlignment(Qt.AlignCenter)
        title_box.addWidget(self.heading)

        self.subheading = QLabel("Straightening perspective, removing shadows, and standardizing physical dimensions.")
        self.subheading.setStyleSheet("font-size: 14px; color: #94A3B8; background: transparent;")
        self.subheading.setAlignment(Qt.AlignCenter)
        title_box.addWidget(self.subheading)

        main_layout.addLayout(title_box)

        # ── Progress Checklist Box ──
        self.box_progress = QFrame()
        self.box_progress.setStyleSheet("""
            QFrame {
                background-color: #14141A;
                border: 1px solid #24242E;
                border-radius: 14px;
            }
        """)
        self.box_progress.setFixedWidth(560)
        prog_layout = QVBoxLayout(self.box_progress)
        prog_layout.setContentsMargins(28, 24, 28, 24)
        prog_layout.setSpacing(14)

        self.lbl_progress_bar = QProgressBar()
        self.lbl_progress_bar.setRange(0, 0)  # Indeterminate animation
        self.lbl_progress_bar.setFixedHeight(6)
        self.lbl_progress_bar.setTextVisible(False)
        self.lbl_progress_bar.setStyleSheet("""
            QProgressBar {
                background-color: #1E1E26;
                border: none;
                border-radius: 3px;
            }
            QProgressBar::chunk {
                background-color: #38BDF8;
                border-radius: 3px;
            }
        """)
        prog_layout.addWidget(self.lbl_progress_bar)

        self.steps_container = QVBoxLayout()
        self.steps_container.setSpacing(10)
        prog_layout.addLayout(self.steps_container)

        main_layout.addWidget(self.box_progress, alignment=Qt.AlignCenter)

        # ── Review Required Warning Banner ──
        self.review_banner = QFrame()
        self.review_banner.setStyleSheet("""
            QFrame {
                background-color: rgba(245, 158, 11, 0.12);
                border: 1px solid rgba(245, 158, 11, 0.4);
                border-radius: 12px;
            }
        """)
        self.review_banner.setFixedWidth(560)
        rev_layout = QVBoxLayout(self.review_banner)
        rev_layout.setContentsMargins(20, 16, 20, 16)
        rev_layout.setSpacing(10)

        self.lbl_warning = QLabel("⚠ One or more card sides need boundary review")
        self.lbl_warning.setStyleSheet("font-size: 14px; font-weight: 700; color: #FBBF24; background: transparent;")
        rev_layout.addWidget(self.lbl_warning)

        rev_btns = QHBoxLayout()
        rev_btns.setSpacing(12)

        self.btn_rev_front = QPushButton("Review Front")
        self.btn_rev_front.setCursor(Qt.PointingHandCursor)
        self.btn_rev_front.setFixedHeight(36)
        self.btn_rev_front.setStyleSheet("""
            QPushButton {
                background-color: #D97706;
                color: #FFFFFF;
                border: none;
                border-radius: 8px;
                font-weight: 700;
                font-size: 13px;
                padding: 0 16px;
            }
            QPushButton:hover { background-color: #B45309; }
        """)
        self.btn_rev_front.clicked.connect(lambda: self.review_side_requested.emit("front"))
        rev_btns.addWidget(self.btn_rev_front)

        self.btn_rev_back = QPushButton("Review Back")
        self.btn_rev_back.setCursor(Qt.PointingHandCursor)
        self.btn_rev_back.setFixedHeight(36)
        self.btn_rev_back.setStyleSheet("""
            QPushButton {
                background-color: #D97706;
                color: #FFFFFF;
                border: none;
                border-radius: 8px;
                font-weight: 700;
                font-size: 13px;
                padding: 0 16px;
            }
            QPushButton:hover { background-color: #B45309; }
        """)
        self.btn_rev_back.clicked.connect(lambda: self.review_side_requested.emit("back"))
        rev_btns.addWidget(self.btn_rev_back)

        rev_btns.addStretch()
        rev_layout.addLayout(rev_btns)

        self.review_banner.hide()
        main_layout.addWidget(self.review_banner, alignment=Qt.AlignCenter)

        # ── Collapsible Details Section ──
        details_box = QVBoxLayout()
        details_box.setAlignment(Qt.AlignCenter)

        self.btn_toggle_details = QPushButton("View Details ▼")
        self.btn_toggle_details.setCursor(Qt.PointingHandCursor)
        self.btn_toggle_details.setFixedHeight(30)
        self.btn_toggle_details.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: #64748B;
                border: none;
                font-size: 12px;
                font-weight: 600;
            }
            QPushButton:hover { color: #94A3B8; }
        """)
        self.btn_toggle_details.clicked.connect(self._toggle_details)
        details_box.addWidget(self.btn_toggle_details, alignment=Qt.AlignCenter)

        self.lbl_details = QLabel()
        self.lbl_details.setFixedWidth(560)
        self.lbl_details.setStyleSheet("""
            background-color: #0F0F14;
            color: #94A3B8;
            border: 1px solid #1E1E26;
            border-radius: 8px;
            padding: 12px;
            font-family: Consolas, monospace;
            font-size: 11px;
        """)
        self.lbl_details.hide()
        details_box.addWidget(self.lbl_details, alignment=Qt.AlignCenter)

        main_layout.addLayout(details_box)

        scroll.setWidget(container)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

    def start_processing(self, front: Optional[str], back: Optional[str], profile: FormatProfile):
        self.front_path = front
        self.back_path = back
        self.profile = profile
        self._is_done = False

        self.heading.setText("Processing Card")
        self.subheading.setText("Straightening perspective, removing shadows, and standardizing physical dimensions.")
        self.lbl_progress_bar.show()
        self.review_banner.hide()
        self.lbl_details.hide()
        self.btn_toggle_details.setText("View Details ▼")

        # Clear steps container
        while self.steps_container.count():
            item = self.steps_container.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        # Add initial steps
        if front is not None:
            self._add_step_item("Loading Front photograph...", "active")
        if back is not None:
            self._add_step_item("Waiting for Back photograph...", "pending")

        # Launch Thread
        self.thread = QThread()
        self.worker = ProcessingWorker(self.pipeline, front, back, profile)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.progress_step.connect(self._on_worker_step)
        self.worker.finished.connect(self._on_worker_finished)
        self.thread.start()

    def _add_step_item(self, text: str, status: str):
        row = QHBoxLayout()
        row.setSpacing(10)
        icon = QLabel()
        icon.setFixedSize(18, 18)
        lbl = QLabel(text)
        lbl.setStyleSheet("font-size: 13px; background: transparent;")

        if status == "done":
            icon.setText("✓")
            icon.setStyleSheet("color: #10B981; font-weight: 800; font-size: 14px; background: transparent;")
            lbl.setStyleSheet("font-size: 13px; color: #E2E8F0; font-weight: 600; background: transparent;")
        elif status == "active":
            icon.setText("●")
            icon.setStyleSheet("color: #38BDF8; font-weight: 800; font-size: 12px; background: transparent;")
            lbl.setStyleSheet("font-size: 13px; color: #38BDF8; font-weight: 600; background: transparent;")
        else:
            icon.setText("○")
            icon.setStyleSheet("color: #475569; font-size: 12px; background: transparent;")
            lbl.setStyleSheet("font-size: 13px; color: #64748B; background: transparent;")

        row.addWidget(icon)
        row.addWidget(lbl)
        row.addStretch()
        w = QWidget()
        w.setLayout(row)
        self.steps_container.addWidget(w)

    def _on_worker_step(self, status: str, message: str):
        self._add_step_item(message, status)

    def _on_worker_finished(self, success: bool, error_msg: str):
        if self.thread:
            self.thread.quit()
            self.thread.wait()

        self.lbl_progress_bar.hide()
        self._is_done = success

        if success:
            self.heading.setText("Processing Complete")
            self.subheading.setText("Card normalized successfully. Click Continue to inspect the print preview.")
            self._check_for_reviews()
        else:
            self.heading.setText("Processing Issue")
            self.subheading.setText("Could not automatically locate the card boundaries. Please review manual corners.")
            self._add_step_item(f"Error: {error_msg}", "active")
            self.review_banner.show()

        self._populate_details()
        self.processing_completed.emit(success)

    def _check_for_reviews(self):
        entry = self.pipeline.card_entry
        if entry is None:
            return

        need_front = False
        need_back = False

        if entry.front and entry.front.quality_report:
            qr = entry.front.quality_report
            if qr.boundary_confidence < 0.65 or qr.is_blurry:
                need_front = True

        if entry.back and entry.back.quality_report:
            qr = entry.back.quality_report
            if qr.boundary_confidence < 0.65 or qr.is_blurry:
                need_back = True

        if need_front or need_back:
            self.btn_rev_front.setVisible(bool(entry.front))
            self.btn_rev_back.setVisible(bool(entry.back))
            self.review_banner.show()
        else:
            self.review_banner.hide()

    def _populate_details(self):
        entry = self.pipeline.card_entry
        lines = []
        if entry:
            for name, side in [("Front", entry.front), ("Back", entry.back)]:
                if side:
                    lines.append(f"[{name.upper()}]")
                    if side.quality_report:
                        qr = side.quality_report
                        lines.append(f"  Boundary Conf:    {qr.boundary_confidence:.1%}")
                        lines.append(f"  Orientation Conf: {qr.orientation_confidence:.1%}")
                        lines.append(f"  Format Conf:      {qr.format_confidence:.1%}")
                        if qr.issues:
                            lines.append(f"  Notes:            {', '.join(qr.issues)}")
                    if side.orientation_result:
                        lines.append(f"  Orientation Angle: {side.orientation_result.best_angle}°")
                    lines.append("")
        self.lbl_details.setText("\n".join(lines) if lines else "No diagnostics available.")

    def _toggle_details(self):
        if self.lbl_details.isVisible():
            self.lbl_details.hide()
            self.btn_toggle_details.setText("View Details ▼")
        else:
            self.lbl_details.show()
            self.btn_toggle_details.setText("Hide Details ▲")
