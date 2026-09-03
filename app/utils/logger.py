"""
Structured, Privacy-Preserving Logging for QenBel Smart Formatter.
"""
import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path
from app.core.config import AppPaths

_logger = None


def setup_logger(name: str = "qenbel") -> logging.Logger:
    """Configures and returns the application logger."""
    global _logger
    if _logger is not None:
        return _logger

    AppPaths.ensure_directories()
    log_file = AppPaths.LOGS_DIR / "qenbel_formatter.log"

    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)

    # Avoid duplicate handlers
    if not logger.handlers:
        # Formatter
        formatter = logging.Formatter(
            "[%(asctime)s] [%(levelname)s] [%(name)s:%(funcName)s:%(lineno)d] - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )

        # File Handler (Max 5MB, keep 3 backups)
        file_handler = RotatingFileHandler(
            log_file, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

        # Console Handler (INFO level)
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

    _logger = logger
    return logger


def get_logger(module_name: str = "") -> logging.Logger:
    """Get child logger with module prefix."""
    base_logger = setup_logger()
    if module_name:
        return base_logger.getChild(module_name)
    return base_logger
