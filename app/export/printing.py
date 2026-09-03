"""
Direct Printing.

Uses the SAME PrintLayoutEngine as the preview/image/PDF exports so that what
is printed is exactly what the user sees in the print preview. The printed
output contains ONLY the card images — no UI labels, text, or metadata.
"""
from typing import Optional, Tuple
from pathlib import Path

from app.core.models import CardPair, SheetQueue
from app.core.profiles import FormatProfile
from app.core.print_layout import PrintLayoutEngine
from app.utils.image_io import bgr_to_pil
from app.utils.logger import get_logger

logger = get_logger("printing")

try:
    from PySide6.QtPrintSupport import QPrinter, QPrintDialog
    from PySide6.QtGui import QImage, QPixmap, QPainter
    from PySide6.QtCore import QSize, QRect
    _QT_AVAILABLE = True
except Exception:  # pragma: no cover - non-GUI env
    _QT_AVAILABLE = False


class PrintManager:
    """Prints the unified card layout through the system print dialog."""

    @staticmethod
    def _render_layout(card_pair: CardPair, copies: int, profile: FormatProfile, single_page: bool = False):
        front = card_pair.front
        back = card_pair.back
        front_img = front.final_image if front is not None else None
        back_img = back.final_image if back is not None else None
        engine = PrintLayoutEngine()
        return engine.render_pair(
            front_img, back_img, profile, copies=copies, single_page=single_page,
        )

    @classmethod
    def print_card_pair(
        cls,
        card_pair: CardPair,
        parent_widget=None,
        copies: int = 1,
        printer_name: Optional[str] = None,
        show_dialog: bool = False,
        single_page: bool = False,
    ) -> bool:
        """
        Prints the side-by-side card layout to the selected or default printer.
        """
        if not _QT_AVAILABLE:
            logger.error("Qt printing support is not available.")
            return False

        rendered, metrics = cls._render_layout(
            card_pair, copies, card_pair.format_profile, single_page=single_page
        )
        if rendered is None:
            logger.warning("Nothing to print (no card images).")
            return False

        pil_img = bgr_to_pil(rendered)
        w, h = pil_img.size
        qimg = QImage(pil_img.tobytes(), w, h, w * 3, QImage.Format_RGB888).rgbSwapped()
        pixmap = QPixmap.fromImage(qimg)

        printer = QPrinter(QPrinter.HighResolution)
        if printer_name:
            printer.setPrinterName(printer_name)
        printer.setColorMode(QPrinter.Color)
        printer.setFullPage(True)
        if copies > 1:
            printer.setCopyCount(copies)
        dpi = metrics.dpi if metrics else card_pair.format_profile.dpi
        printer.setResolution(int(dpi))

        if show_dialog:
            dialog = QPrintDialog(printer, parent_widget)
            if dialog.exec() != QPrintDialog.Accepted:
                return False

        painter = QPainter(printer)
        try:
            page_rect = printer.pageRect(QPrinter.DevicePixel)
            pw = page_rect.width()
            ph = page_rect.height()
            painter.drawPixmap(0, 0, pw, ph, pixmap)
            painter.end()
            logger.info("Printed card pair layout successfully.")
            return True
        except Exception as e:
            logger.error(f"Printing failed: {e}", exc_info=True)
            painter.end()
            return False

    @classmethod
    def print_sheet_queue(cls, queue: SheetQueue, parent_widget=None) -> bool:
        """Prints sheet pages (documents) through the system print dialog."""
        if not _QT_AVAILABLE:
            logger.error("Qt printing support is not available.")
            return False
        pages = [p.final_image for p in queue.pages if p.final_image is not None]
        if not pages:
            return False

        printer = QPrinter(QPrinter.HighResolution)
        printer.setColorMode(QPrinter.Color)
        dialog = QPrintDialog(printer, parent_widget)
        if dialog.exec() != QPrintDialog.Accepted:
            return False

        painter = QPainter(printer)
        try:
            page_rect = printer.pageRect(QPrinter.DevicePixel)
            pw, ph = page_rect.width(), page_rect.height()
            for i, img in enumerate(pages):
                if i > 0:
                    printer.newPage()
                pil_img = bgr_to_pil(img)
                w, h = pil_img.size
                qimg = QImage(pil_img.tobytes(), w, h, w * 3, QImage.Format_RGB888).rgbSwapped()
                painter.drawPixmap(0, 0, pw, ph, QPixmap.fromImage(qimg))
            painter.end()
            logger.info("Printed sheet queue successfully.")
            return True
        except Exception as e:
            logger.error(f"Printing failed: {e}", exc_info=True)
            painter.end()
            return False
