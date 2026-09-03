"""
Card Mode Multi-Step Workflow Orchestrator.
Coordinates:
  ① Add Photos → ② Arrange → ③ Process → ④ Preview → ⑤ Print
With persistent navigation and corner correction dialog integration.
"""
from typing import Optional
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QStackedWidget,
    QPushButton,
    QFrame,
    QMessageBox,
)

from app.core.pipeline import FormatterPipeline
from app.core.profiles import FormatProfile, CARD_PROFILE
from app.ui.components.step_indicator import StepIndicator
from app.ui.card_mode.page_add_photos import PageAddPhotos
from app.ui.card_mode.page_arrange import PageArrange
from app.ui.card_mode.page_process import PageProcess
from app.ui.card_mode.page_preview import PagePreview
from app.ui.card_mode.page_print import PagePrint
from app.ui.corner_editor import CornerEditorDialog
from app.utils.logger import get_logger

logger = get_logger("card_workflow")


class CardWorkflow(QWidget):
    """Container managing the 5-step Card Mode experience."""
    mode_switch_requested = Signal()

    def __init__(self, pipeline: FormatterPipeline, parent=None):
        super().__init__(parent)
        self.pipeline = pipeline
        self.front_path: Optional[str] = None
        self.back_path: Optional[str] = None
        self.active_profile: FormatProfile = self.pipeline.active_card_profile

        self._init_ui()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ── Step Indicator ──
        step_names = ["Add Photos", "Arrange", "Process", "Preview", "Print"]
        self.step_indicator = StepIndicator(step_names, current_index=0)
        self.step_indicator.step_clicked.connect(self._go_to_step)
        main_layout.addWidget(self.step_indicator)

        # ── Stacked Pages ──
        self.pages_stack = QStackedWidget()

        self.page_1 = PageAddPhotos(self)
        self.page_2 = PageArrange(self)
        self.page_3 = PageProcess(self.pipeline, self)
        self.page_4 = PagePreview(self.pipeline, self)
        self.page_5 = PagePrint(self.pipeline, self)

        self.pages_stack.addWidget(self.page_1)  # Index 0
        self.pages_stack.addWidget(self.page_2)  # Index 1
        self.pages_stack.addWidget(self.page_3)  # Index 2
        self.pages_stack.addWidget(self.page_4)  # Index 3
        self.pages_stack.addWidget(self.page_5)  # Index 4

        main_layout.addWidget(self.pages_stack, stretch=1)

        # ── Bottom Navigation Bar ──
        nav_bar = QFrame()
        nav_bar.setFixedHeight(64)
        nav_bar.setStyleSheet("""
            QFrame {
                background-color: #121217;
                border-top: 1px solid #24242E;
            }
        """)
        nav_layout = QHBoxLayout(nav_bar)
        nav_layout.setContentsMargins(36, 0, 36, 0)

        self.btn_back = QPushButton("←  Back")
        self.btn_back.setCursor(Qt.PointingHandCursor)
        self.btn_back.setFixedHeight(42)
        self.btn_back.setMinimumWidth(120)
        self.btn_back.setStyleSheet("""
            QPushButton {
                background-color: #1E293B;
                color: #CBD5E1;
                border: 1px solid #334155;
                border-radius: 8px;
                font-size: 13px;
                font-weight: 700;
            }
            QPushButton:hover {
                background-color: #334155;
                color: #FFFFFF;
            }
            QPushButton:disabled {
                background-color: #16161E;
                color: #475569;
                border-color: #24242E;
            }
        """)
        self.btn_back.clicked.connect(self._on_back_clicked)
        nav_layout.addWidget(self.btn_back)

        nav_layout.addStretch()

        self.btn_continue = QPushButton("Continue  →")
        self.btn_continue.setCursor(Qt.PointingHandCursor)
        self.btn_continue.setFixedHeight(44)
        self.btn_continue.setMinimumWidth(160)
        self.btn_continue.setStyleSheet("""
            QPushButton {
                background-color: #2563EB;
                color: #FFFFFF;
                border: none;
                border-radius: 8px;
                font-size: 14px;
                font-weight: 700;
                padding: 0 20px;
            }
            QPushButton:hover {
                background-color: #1D4ED8;
            }
            QPushButton:disabled {
                background-color: #1E293B;
                color: #475569;
            }
        """)
        self.btn_continue.clicked.connect(self._on_continue_clicked)
        nav_layout.addWidget(self.btn_continue)

        main_layout.addWidget(nav_bar)

        # ── Signals Wiring ──
        self.page_1.selection_changed.connect(self._on_selection_changed)
        self.page_2.assignment_swapped.connect(self._on_sides_swapped)
        self.page_2.file_replaced.connect(self._on_file_replaced)
        self.page_2.profile_changed.connect(self._on_profile_changed)

        self.page_3.processing_completed.connect(self._on_processing_finished)
        self.page_3.review_side_requested.connect(self._on_edit_side_corners)

        self.page_4.edit_corners_requested.connect(self._on_edit_side_corners)
        self.page_4.swap_requested.connect(self._on_sides_swapped)
        self.page_4.refresh_needed.connect(self._on_pipeline_refreshed)

        self.page_5.start_new_card.connect(self.reset_all)

        self._update_nav_state()

    def _on_selection_changed(self, front: Optional[str], back: Optional[str]):
        self.front_path = front
        self.back_path = back
        self._update_nav_state()

    def _on_sides_swapped(self):
        self.front_path, self.back_path = self.back_path, self.front_path
        self.page_1.set_files(self.front_path, self.back_path)
        self.page_2.set_data(self.front_path, self.back_path, self.active_profile)
        # Also sync pipeline card_entry/pair if processed
        if not self.pipeline.card_entry.is_empty():
            self.page_4.refresh_preview()
            self.page_5.refresh_preview()

    def _on_file_replaced(self, side: str, new_path: str):
        if side == "front":
            self.front_path = new_path
        else:
            self.back_path = new_path
        self.page_1.set_files(self.front_path, self.back_path)

    def _on_profile_changed(self, profile: FormatProfile):
        self.active_profile = profile
        self.pipeline.set_card_profile(profile)

    def _on_processing_finished(self, success: bool):
        self._update_nav_state()

    def _on_edit_side_corners(self, side: str):
        entry = self.pipeline.card_entry
        if entry is None or entry.is_empty():
            return
        side_img = entry.front if side == "front" else entry.back
        if side_img is None:
            return

        dialog = CornerEditorDialog(side_img, self)
        if dialog.exec():
            new_corners = dialog.get_result_corners()
            self.pipeline.update_item_corners(side_img, new_corners)
            self.page_4.refresh_preview()
            self.page_5.refresh_preview()

    def _on_pipeline_refreshed(self):
        self.page_5.refresh_preview()

    def _go_to_step(self, step_idx: int):
        self.pages_stack.setCurrentIndex(step_idx)
        self.step_indicator.set_current_step(step_idx)
        self._on_entered_step(step_idx)
        self._update_nav_state()

    def _on_entered_step(self, step_idx: int):
        if step_idx == 1:  # Arrange
            self.page_2.set_data(self.front_path, self.back_path, self.active_profile)
        elif step_idx == 2:  # Process
            self.page_3.start_processing(self.front_path, self.back_path, self.active_profile)
        elif step_idx == 3:  # Preview
            self.page_4.refresh_preview()
        elif step_idx == 4:  # Print
            self.page_5.refresh_preview()

    def _on_back_clicked(self):
        curr = self.pages_stack.currentIndex()
        if curr > 0:
            self._go_to_step(curr - 1)

    def _on_continue_clicked(self):
        curr = self.pages_stack.currentIndex()
        if curr < 4:
            self._go_to_step(curr + 1)

    def _update_nav_state(self):
        curr = self.pages_stack.currentIndex()
        self.btn_back.setEnabled(curr > 0)

        if curr == 0:
            # Step 1: Add Photos
            has_photo = bool(self.front_path or self.back_path)
            self.btn_continue.setEnabled(has_photo)
            self.btn_continue.setText("Continue  →")
            self.btn_continue.show()
        elif curr == 1:
            # Step 2: Arrange
            self.btn_continue.setEnabled(True)
            self.btn_continue.setText("Process Card  →")
            self.btn_continue.show()
        elif curr == 2:
            # Step 3: Process
            self.btn_continue.setEnabled(self.page_3._is_done)
            self.btn_continue.setText("Inspect Preview  →")
            self.btn_continue.show()
        elif curr == 3:
            # Step 4: Preview
            self.btn_continue.setEnabled(True)
            self.btn_continue.setText("Continue to Print  →")
            self.btn_continue.show()
        elif curr == 4:
            # Step 5: Print
            # On the final page, the primary PRINT button is inside page_print
            self.btn_continue.hide()

    def reset_all(self):
        """Resets the Card Mode workflow to clean initial state."""
        self.front_path = None
        self.back_path = None
        self.pipeline.reset()
        self.page_1.set_files(None, None)
        self._go_to_step(0)
