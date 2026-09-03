"""
PDF Document Generator.

Builds a print-ready PDF using the SAME PrintLayoutEngine as the preview,
image export, and direct printing. The side-by-side FRONT|BACK arrangement is
therefore identical in every output path, and no textual metadata is added.
"""
from pathlib import Path
from typing import Union, List, Optional
from PIL import Image

from app.core.print_layout import PrintLayoutEngine
from app.core.models import CardPair, SheetQueue
from app.utils.image_io import bgr_to_pil
from app.utils.logger import get_logger

logger = get_logger("pdf_export")


class PdfExporter:
    """Exports the unified print layout to PDF."""

    @classmethod
    def export_card_pair(
        cls,
        card_pair: CardPair,
        output_path: Union[str, Path],
        copies: int = 1,
        single_page: bool = False,
    ) -> bool:
        """Exports the side-by-side FRONT|BACK layout into a clean PDF."""
        out_file = Path(output_path)
        out_file.parent.mkdir(parents=True, exist_ok=True)

        front = card_pair.front
        back = card_pair.back
        front_img = front.final_image if front is not None else None
        back_img = back.final_image if back is not None else None

        if front_img is None and back_img is None:
            logger.warning("No card images to export to PDF.")
            return False

        engine = PrintLayoutEngine()
        rendered, metrics = engine.render_pair(
            front_img, back_img, card_pair.format_profile,
            copies=copies, single_page=single_page,
        )
        if rendered is None:
            return False

        pil_page = bgr_to_pil(rendered)
        dpi = metrics.dpi if metrics else card_pair.format_profile.dpi

        try:
            pil_page.save(str(out_file), "PDF", resolution=int(dpi))
            logger.info(f"Successfully exported card pair PDF to {out_file}")
            return True
        except Exception as e:
            logger.error(f"Failed to export card pair to PDF: {e}", exc_info=True)
            return False

    @classmethod
    def export_sheet_queue(
        cls,
        queue: SheetQueue,
        output_path: Union[str, Path],
    ) -> bool:
        """Exports all sheet pages into a multi-page PDF."""
        out_file = Path(output_path)
        out_file.parent.mkdir(parents=True, exist_ok=True)

        pil_pages: List[Image.Image] = []
        for page in queue.pages:
            img = page.final_image
            if img is not None:
                pil_pages.append(bgr_to_pil(img))

        if not pil_pages:
            logger.warning("No sheet pages to export to PDF.")
            return False

        try:
            first_page = pil_pages[0]
            other_pages = pil_pages[1:] if len(pil_pages) > 1 else []
            first_page.save(
                str(out_file),
                "PDF",
                resolution=300,
                save_all=True,
                append_images=other_pages,
            )
            logger.info(f"Successfully exported Sheet PDF to {out_file}")
            return True
        except Exception as e:
            logger.error(f"Failed to export sheet queue to PDF: {e}", exc_info=True)
            return False
