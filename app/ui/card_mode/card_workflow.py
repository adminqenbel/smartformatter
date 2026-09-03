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
    QDialog,
    QLabel,
    QMessageBox,
)

from app.core.pipeline import FormatterPipeline
from app.core.profiles import FormatProfile, CARD_PROFILE, LONG_FORM_PROFILE
from app.ui.components.step_indicator import StepIndicator
from app.ui.card_mode.page_add_photos import PageAddPhotos
from app.ui.card_mode.page_arrange import PageArrange
from app.ui.card_mode.page_process import PageProcess
from app.ui.card_mode.page_preview import PagePreview
from app.ui.card_mode.page_print import PagePrint
from app.ui.corner_editor import CornerEditorDialog
from app.utils.logger import get_logger

logger = get_logger("card_workflow")


class CardTypeDialog(QDialog):
    """
    Modal dialog that requires the operator to explicitly choose between
    Standard Card (86×54 mm) and Long Form (210×85 mm) before processing.
    Each card type uses a distinct CV detection strategy.
    """

    def __init__(self, current_profile: FormatProfile, parent=None):
        super().__init__(parent)
        self.selected_profile: FormatProfile = current_profile
        self.setWindowTitle("Select Card Type")
        self.setModal(True)
        self.setMinimumWidth(520)
        self.setWindowFlag(Qt.WindowContextHelpButtonHint, False)
        self.setStyleSheet("""
            QDialog {
                background-color: #0F0F14;
                color: #FFFFFF;
            }
        """)
        self._build_ui(current_profile)

    def _build_ui(self, current_profile: FormatProfile):
        root = QVBoxLayout(self)
        root.setContentsMargins(36, 32, 36, 32)
        root.setSpacing(24)

        # ── Header ──
        icon_lbl = QLabel("🪪")
        icon_lbl.setStyleSheet("font-size: 32px; background: transparent;")
        icon_lbl.setAlignment(Qt.AlignCenter)
        root.addWidget(icon_lbl)

        title = QLabel("What type of card are you processing?")
        title.setStyleSheet(
            "font-size: 18px; font-weight: 800; color: #FFFFFF;"
            " background: transparent; letter-spacing: -0.3px;"
        )
        title.setAlignment(Qt.AlignCenter)
        title.setWordWrap(True)
        root.addWidget(title)

        subtitle = QLabel(
            "This selection determines the detection strategy and output dimensions."
            " Each type uses a different algorithm — choosing correctly ensures the best result."
        )
        subtitle.setStyleSheet("font-size: 12px; color: #64748B; background: transparent;")
        subtitle.setAlignment(Qt.AlignCenter)
        subtitle.setWordWrap(True)
        root.addWidget(subtitle)

        # ── Separator ──
        sep = QFrame()
        sep.setFixedHeight(1)
        sep.setStyleSheet("background: #1E293B;")
        root.addWidget(sep)

        # ── Card Type Buttons ──
        btn_row = QHBoxLayout()
        btn_row.setSpacing(16)

        self.btn_standard = self._make_type_btn(
            "🪪  Standard Card",
            "86 × 54 mm",
            "CR80 / business card / ID card format.",
            accent="#2563EB",
        )
        self.btn_standard.setChecked(current_profile.id == CARD_PROFILE.id)
        self.btn_standard.clicked.connect(lambda: self._select(CARD_PROFILE))

        self.btn_long = self._make_type_btn(
            "📄  Long Form",
            "210 × 85 mm",
            "Extended card with header band (e.g. government ID top strip).",
            accent="#7C3AED",
        )
        self.btn_long.setChecked(current_profile.id == LONG_FORM_PROFILE.id)
        self.btn_long.clicked.connect(lambda: self._select(LONG_FORM_PROFILE))

        btn_row.addWidget(self.btn_standard)
        btn_row.addWidget(self.btn_long)
        root.addLayout(btn_row)

        # ── Confirm Button ──
        self.btn_confirm = QPushButton("Confirm \u0026 Start Processing  →")
        self.btn_confirm.setFixedHeight(48)
        self.btn_confirm.setCursor(Qt.PointingHandCursor)
        self.btn_confirm.setStyleSheet("""
            QPushButton {
                background-color: #2563EB;
                color: #FFFFFF;
                border: none;
                border-radius: 10px;
                font-size: 14px;
                font-weight: 800;
                letter-spacing: 0.2px;
            }
            QPushButton:hover { background-color: #1D4ED8; }
        """)
        self.btn_confirm.clicked.connect(self.accept)
        root.addWidget(self.btn_confirm)

    def _make_type_btn(self, name: str, dims: str, desc: str, accent: str) -> QPushButton:
        btn = QPushButton(f"{name}\n{dims}\n{desc}")
        btn.setCheckable(True)
        btn.setCursor(Qt.PointingHandCursor)
        btn.setFixedHeight(110)
        btn.setMinimumWidth(200)
        btn.setStyleSheet(f"""
            QPushButton {{
                background-color: #14141A;
                color: #94A3B8;
                border: 2px solid #24242E;
                border-radius: 12px;
                font-size: 13px;
                font-weight: 700;
                line-height: 1.5;
                text-align: center;
            }}
            QPushButton:hover {{
                border-color: {accent};
                color: #FFFFFF;
                background-color: #1A1A24;
            }}
            QPushButton:checked {{
                background-color: rgba(37, 99, 235, 0.12);
                border-color: {accent};
                border-width: 2px;
                color: #FFFFFF;
            }}
        """)
        return btn

    def _select(self, profile: FormatProfile):
        self.selected_profile = profile
        self.btn_standard.setChecked(profile.id == CARD_PROFILE.id)
        self.btn_long.setChecked(profile.id == LONG_FORM_PROFILE.id)


class CardWorkflow(QWidget):
    """Container managing the 5-step Card Mode experience."""
    mode_switch_requested = Signal()

    def __init__(self, pipeline: FormatterPipeline, parent=None):
        super().__init__(parent)
        self.pipeline = pipeline
        self.front_path: Optional[str] = None
        self.back_path: Optional[str] = None
        self.active_profile: FormatProfile = self.pipeline.active_card_profile

        # True once the operator has explicitly confirmed a card type for this job.
        self._profile_confirmed: bool = False
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
        if curr == 1 and not self._profile_confirmed:
            # Step 2 → Step 3: Always ask the operator to confirm the card type.
            # This is the gate that selects the correct CV detection strategy.
            dlg = CardTypeDialog(self.active_profile, parent=self)
            if dlg.exec() != QDialog.Accepted:
                return  # User cancelled – stay on Arrange.
            chosen = dlg.selected_profile
            if chosen.id != self.active_profile.id:
                self.active_profile = chosen
                self.pipeline.set_card_profile(chosen)
                # Keep the Arrange page UI in sync.
                self.page_2.set_data(self.front_path, self.back_path, chosen)
            self._profile_confirmed = True
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
        self._profile_confirmed = False  # require card-type selection on next job
        self.pipeline.reset()
        self.page_1.set_files(None, None)
        self._go_to_step(0)
