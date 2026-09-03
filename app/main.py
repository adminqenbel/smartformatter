"""
Main Application Window for QenBel Smart Formatter.

Simplified single-screen workflow:
  CARD / DOCUMENT mode toggle  →  Card Input  →  Print Preview  →  PRINT / EXPORT
"""
import sys
import os
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt

from app.core.config import AppPaths
from app.core.pipeline import FormatterPipeline
from app.utils.logger import setup_logger
from app.ui.main_window import MainWindow
from app.ui.theme import CHATGPT_DARK_STYLESHEET


def main():
    # Ensure app directories exist
    AppPaths.ensure_directories()

    # Initialize Logger
    logger = setup_logger("qenbel_main")
    logger.info("Launching QenBel Smart Formatter...")

    # Enable High DPI Scaling
    os.environ["QT_ENABLE_HIGHDPI_SCALING"] = "1"
    os.environ["QT_AUTO_SCREEN_SCALE_FACTOR"] = "1"

    app = QApplication(sys.argv)
    app.setApplicationName("QenBel Smart Formatter")
    app.setOrganizationName("QenBel Technologies")

    # Global Theme
    app.setStyleSheet(CHATGPT_DARK_STYLESHEET)

    # Initialize central pipeline
    pipeline = FormatterPipeline()

    # Launch the mode-selection shell.  The shell owns the dedicated Card and
    # Document workflows; keeping this as the entry point avoids the legacy
    # all-in-one workbench bypassing the intended navigation architecture.
    window = MainWindow(pipeline=pipeline)
    window.setWindowTitle("QenBel Smart Formatter")
    window.resize(1280, 850)
    window.setMinimumSize(1000, 720)
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
