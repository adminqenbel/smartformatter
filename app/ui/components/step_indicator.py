"""
Step Indicator Widget for Multi-Step Workflows.
Renders clean, spacious steps:
  ① Add Photos → ② Arrange → ③ Process → ④ Preview → ⑤ Print
"""
from typing import List
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel, QPushButton, QFrame


class StepIndicator(QFrame):
    """Clean, spacious step indicator for operator workflows."""
    step_clicked = Signal(int)

    def __init__(self, steps: List[str], current_index: int = 0, parent=None):
        super().__init__(parent)
        self.steps = steps
        self.current_index = current_index
        self.step_buttons: List[QPushButton] = []
        self._max_unlocked_step = current_index

        self.setFixedHeight(56)
        self.setStyleSheet("""
            QFrame {
                background-color: #121217;
                border-bottom: 1px solid #24242E;
            }
        """)

        self.layout = QHBoxLayout(self)
        self.layout.setContentsMargins(32, 0, 32, 0)
        self.layout.setSpacing(16)
        self.layout.setAlignment(Qt.AlignCenter)

        self._build_steps()

    def _build_steps(self):
        # Clear existing
        while self.layout.count():
            item = self.layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        self.step_buttons.clear()

        circled_nums = ["①", "②", "③", "④", "⑤", "⑥", "⑦", "⑧", "⑨"]

        for idx, name in enumerate(self.steps):
            num_symbol = circled_nums[idx] if idx < len(circled_nums) else f"({idx + 1})"
            btn = QPushButton(f"{num_symbol}  {name}")
            btn.setCursor(Qt.PointingHandCursor if idx <= self._max_unlocked_step else Qt.ArrowCursor)
            btn.setEnabled(idx <= self._max_unlocked_step)
            
            # Styles for current, completed, and upcoming
            if idx == self.current_index:
                btn.setStyleSheet("""
                    QPushButton {
                        background-color: #2563EB;
                        color: #FFFFFF;
                        border: none;
                        border-radius: 18px;
                        padding: 8px 18px;
                        font-size: 13px;
                        font-weight: 700;
                        letter-spacing: 0.3px;
                    }
                """)
            elif idx < self.current_index:
                btn.setStyleSheet("""
                    QPushButton {
                        background-color: rgba(37, 99, 235, 0.12);
                        color: #93C5FD;
                        border: 1px solid rgba(37, 99, 235, 0.3);
                        border-radius: 18px;
                        padding: 7px 16px;
                        font-size: 12px;
                        font-weight: 600;
                    }
                    QPushButton:hover {
                        background-color: rgba(37, 99, 235, 0.22);
                        color: #BFDBFE;
                    }
                """)
            else:
                btn.setStyleSheet("""
                    QPushButton {
                        background-color: transparent;
                        color: #555566;
                        border: none;
                        padding: 7px 14px;
                        font-size: 12px;
                        font-weight: 500;
                    }
                """)

            btn.clicked.connect(lambda checked=False, i=idx: self._on_clicked(i))
            self.layout.addWidget(btn)
            self.step_buttons.append(btn)

            if idx < len(self.steps) - 1:
                sep = QLabel("→")
                sep.setStyleSheet("color: #383846; font-size: 15px; font-weight: 700; background: transparent;")
                self.layout.addWidget(sep)

    def _on_clicked(self, index: int):
        if index <= self._max_unlocked_step:
            self.step_clicked.emit(index)

    def set_current_step(self, index: int):
        self.current_index = index
        self._max_unlocked_step = max(self._max_unlocked_step, index)
        self._build_steps()

    def unlock_step(self, index: int):
        self._max_unlocked_step = max(self._max_unlocked_step, index)
        self._build_steps()
