"""
Microsoft Word (.docx) Document Generator.
Places cropped and normalized cards and document sheets into ready-to-print Word files
with exact physical dimensions dynamically calculated from the active FormatProfile.
"""
from pathlib import Path
from typing import Union, List, Optional
import tempfile
import cv2
import numpy as np
from docx import Document
from docx.shared import Inches, Cm, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.section import WD_ORIENT

from app.core.config import PrintConfig
from app.core.profiles import FormatProfile, CARD_PROFILE, LONG_FORM_PROFILE
from app.core.models import CardPair, SheetQueue, ProcessedImage
from app.utils.logger import get_logger

logger = get_logger("docx_export")


class DocxExporter:
    """Exports processed documents and cards to Microsoft Word (.docx)."""

    @classmethod
    def export_card_pair(
        cls,
        card_pair: CardPair,
        output_path: Union[str, Path],
        layout: str = "side_by_side"
    ) -> bool:
        """
        Exports Front and Back cards to a print-ready Microsoft Word (.docx) document.
        Always uses standard A4 portrait page layout (210 x 297 mm).
        Cards occupy strictly their respective physical/proportional dimensions at the top
        of the page (side-by-side), leaving the remaining page blank (NOT stretched full page).
        """
        out_file = Path(output_path)
        out_file.parent.mkdir(parents=True, exist_ok=True)

        try:
            doc = Document()
            profile = card_pair.format_profile or CARD_PROFILE

            # Standard A4 Portrait Page Setup (210 mm x 297 mm)
            section = doc.sections[0]
            section.orientation = WD_ORIENT.PORTRAIT
            section.page_width = Cm(21.0)
            section.page_height = Cm(29.7)
            section.top_margin = Cm(1.5)
            section.bottom_margin = Cm(1.5)
            section.left_margin = Cm(1.2)
            section.right_margin = Cm(1.2)

            usable_w_cm = 21.0 - 2.4  # 18.6 cm

            with tempfile.TemporaryDirectory() as tmpdir:
                tmp_path = Path(tmpdir)

                front_img = card_pair.front.final_image if card_pair.front is not None else None
                back_img = card_pair.back.final_image if card_pair.back is not None else None

                front_tmp = None
                back_tmp = None

                if front_img is not None:
                    front_tmp = tmp_path / "front_card.png"
                    cv2.imwrite(str(front_tmp), front_img)

                if back_img is not None:
                    back_tmp = tmp_path / "back_card.png"
                    cv2.imwrite(str(back_tmp), back_img)

                # Determine card dimensions based on active profile:
                # - Standard Card: 86 x 54 mm (exact real-world size: 8.6 cm x 5.4 cm)
                # - Long Form: 210 x 85 mm (aspect 2.47:1) -> fits side-by-side across A4 at 9.1 cm x 3.68 cm each
                is_long_form = (profile.id == "long_form" or profile.aspect_ratio >= 2.0)
                is_portrait = False
                if front_img is not None:
                    is_portrait = front_img.shape[0] > front_img.shape[1]
                elif back_img is not None:
                    is_portrait = back_img.shape[0] > back_img.shape[1]

                if front_tmp and back_tmp:
                    if is_long_form:
                        # Long Form side-by-side: each takes half usable width (9.1 cm x 3.68 cm)
                        card_w = Cm(9.1)
                        card_h = Cm(round(9.1 / max(profile.aspect_ratio, 1e-3), 2))
                    elif is_portrait:
                        card_w = Cm(profile.height_mm / 10.0)
                        card_h = Cm(profile.width_mm / 10.0)
                    else:
                        # Standard Card: exact physical size 8.6 cm x 5.4 cm
                        card_w = Cm(profile.width_mm / 10.0)
                        card_h = Cm(profile.height_mm / 10.0)

                    # 2-column borderless table for side-by-side layout (NO text/labels)
                    table = doc.add_table(rows=1, cols=2)
                    table.alignment = WD_TABLE_ALIGNMENT.CENTER
                    table.autofit = False

                    # Left cell: FRONT image only
                    cell_left = table.cell(0, 0)
                    cell_left.width = Cm(usable_w_cm / 2.0)
                    p_left = cell_left.paragraphs[0]
                    p_left.alignment = WD_ALIGN_PARAGRAPH.CENTER
                    p_left.paragraph_format.space_before = Pt(0)
                    p_left.paragraph_format.space_after = Pt(0)
                    p_left.add_run().add_picture(str(front_tmp), width=card_w, height=card_h)

                    # Right cell: BACK image only
                    cell_right = table.cell(0, 1)
                    cell_right.width = Cm(usable_w_cm / 2.0)
                    p_right = cell_right.paragraphs[0]
                    p_right.alignment = WD_ALIGN_PARAGRAPH.CENTER
                    p_right.paragraph_format.space_before = Pt(0)
                    p_right.paragraph_format.space_after = Pt(0)
                    p_right.add_run().add_picture(str(back_tmp), width=card_w, height=card_h)

                elif front_tmp or back_tmp:
                    # Single side present (NO text/labels)
                    active_tmp = front_tmp or back_tmp

                    if is_long_form:
                        card_w = Cm(18.5)
                        card_h = Cm(round(18.5 / max(profile.aspect_ratio, 1e-3), 2))
                    elif is_portrait:
                        card_w = Cm(profile.height_mm / 10.0)
                        card_h = Cm(profile.width_mm / 10.0)
                    else:
                        card_w = Cm(profile.width_mm / 10.0)
                        card_h = Cm(profile.height_mm / 10.0)

                    p = doc.add_paragraph()
                    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                    p.paragraph_format.space_before = Pt(0)
                    p.paragraph_format.space_after = Pt(0)
                    p.add_run().add_picture(str(active_tmp), width=card_w, height=card_h)

            doc.save(str(out_file))
            logger.info(f"Successfully exported Word document to {out_file}")
            return True

        except Exception as e:
            logger.error(f"Failed to export card pair to Word docx: {e}", exc_info=True)
            return False

    @classmethod
    def export_sheet_queue(
        cls,
        queue: SheetQueue,
        output_path: Union[str, Path]
    ) -> bool:
        """
        Exports multi-page sheet documents to Word (.docx), placing each page on a separate page.
        """
        out_file = Path(output_path)
        out_file.parent.mkdir(parents=True, exist_ok=True)

        if not queue.pages:
            logger.warning("No pages in sheet queue to export.")
            return False

        try:
            doc = Document()

            for section in doc.sections:
                section.top_margin = Inches(PrintConfig.DOCX_MARGIN_INCH)
                section.bottom_margin = Inches(PrintConfig.DOCX_MARGIN_INCH)
                section.left_margin = Inches(PrintConfig.DOCX_MARGIN_INCH)
                section.right_margin = Inches(PrintConfig.DOCX_MARGIN_INCH)

            with tempfile.TemporaryDirectory() as tmpdir:
                tmp_path = Path(tmpdir)

                for idx, page in enumerate(queue.pages):
                    img = page.final_image
                    if img is None:
                        continue

                    page_tmp = tmp_path / f"page_{idx + 1}.png"
                    cv2.imwrite(str(page_tmp), img)

                    h, w = img.shape[:2]
                    is_landscape = w > h

                    if is_landscape:
                        target_width = Inches(7.5)
                    else:
                        target_width = Inches(7.0)

                    p = doc.add_paragraph()
                    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                    p.add_run().add_picture(str(page_tmp), width=target_width)

                    if idx < len(queue.pages) - 1:
                        doc.add_page_break()

            doc.save(str(out_file))
            logger.info(f"Successfully exported Sheet document to {out_file}")
            return True

        except Exception as e:
            logger.error(f"Failed to export sheets to Word docx: {e}", exc_info=True)
            return False
