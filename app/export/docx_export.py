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
        layout: str = "side_by_side"  # "side_by_side" or "stacked"
    ) -> bool:
        """
        Exports Front and Back cards to a print-ready Word document with standard physical dimensions.
        Calculates physical sizing dynamically from the active FormatProfile.
        """
        out_file = Path(output_path)
        out_file.parent.mkdir(parents=True, exist_ok=True)

        try:
            doc = Document()
            profile = card_pair.format_profile or CARD_PROFILE

            # Keep Word consistent with the card-mode contract: two sides are
            # placed horizontally. Long Form therefore uses a custom-wide
            # landscape page instead of silently falling back to stacked output.
            section = doc.sections[0]
            card_w_cm = profile.width_mm / 10.0
            card_h_cm = profile.height_mm / 10.0

            has_both_sides = card_pair.front is not None and card_pair.back is not None
            if has_both_sides and layout == "side_by_side":
                section.orientation = WD_ORIENT.LANDSCAPE
                section.page_width = Cm(max(29.7, card_w_cm * 2 + 1.0))
                section.page_height = Cm(max(21.0, card_h_cm + 1.0))
                section.top_margin = Inches(0.4)
                section.bottom_margin = Inches(0.4)
                section.left_margin = Inches(0.4)
                section.right_margin = Inches(0.4)
            else:
                section.top_margin = Inches(PrintConfig.DOCX_MARGIN_INCH)
                section.bottom_margin = Inches(PrintConfig.DOCX_MARGIN_INCH)
                section.left_margin = Inches(PrintConfig.DOCX_MARGIN_INCH)
                section.right_margin = Inches(PrintConfig.DOCX_MARGIN_INCH)

            # Document Header
            title_p = doc.add_paragraph()
            title_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            run = title_p.add_run(f"QenBel Smart Formatter — {profile.name} Print Sheet ({profile.dimensions_mm_str})")
            run.font.size = Pt(9.5)
            run.font.color.rgb = RGBColor(128, 128, 128)

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

                # Determine card dimensions from image orientation
                is_portrait = False
                if front_img is not None:
                    is_portrait = front_img.shape[0] > front_img.shape[1]
                elif back_img is not None:
                    is_portrait = back_img.shape[0] > back_img.shape[1]

                if is_portrait:
                    card_w = Cm(card_h_cm)
                    card_h = Cm(card_w_cm)
                else:
                    card_w = Cm(card_w_cm)
                    card_h = Cm(card_h_cm)

                # Export images
                if front_tmp and back_tmp:
                    if layout == "side_by_side" and not is_portrait:
                        # 2-column table for side-by-side presentation
                        table = doc.add_table(rows=1, cols=2)
                        table.alignment = WD_TABLE_ALIGNMENT.CENTER

                        cell_left = table.cell(0, 0)
                        p_left = cell_left.paragraphs[0]
                        p_left.alignment = WD_ALIGN_PARAGRAPH.CENTER
                        p_left.add_run("FRONT\n").bold = True
                        p_left.runs[0].font.size = Pt(9)
                        p_left.runs[0].font.color.rgb = RGBColor(100, 100, 100)
                        p_left.add_run().add_picture(str(front_tmp), width=card_w, height=card_h)

                        cell_right = table.cell(0, 1)
                        p_right = cell_right.paragraphs[0]
                        p_right.alignment = WD_ALIGN_PARAGRAPH.CENTER
                        p_right.add_run("BACK\n").bold = True
                        p_right.runs[0].font.size = Pt(9)
                        p_right.runs[0].font.color.rgb = RGBColor(100, 100, 100)
                        p_right.add_run().add_picture(str(back_tmp), width=card_w, height=card_h)

                    else:
                        # Stacked layout
                        p_f = doc.add_paragraph()
                        p_f.alignment = WD_ALIGN_PARAGRAPH.CENTER
                        p_f.add_run("FRONT\n").bold = True
                        p_f.runs[0].font.size = Pt(9)
                        p_f.runs[0].font.color.rgb = RGBColor(100, 100, 100)
                        p_f.add_run().add_picture(str(front_tmp), width=card_w, height=card_h)

                        p_b = doc.add_paragraph()
                        p_b.alignment = WD_ALIGN_PARAGRAPH.CENTER
                        p_b.add_run("\nBACK\n").bold = True
                        p_b.runs[0].font.size = Pt(9)
                        p_b.runs[0].font.color.rgb = RGBColor(100, 100, 100)
                        p_b.add_run().add_picture(str(back_tmp), width=card_w, height=card_h)

                elif front_tmp:
                    p = doc.add_paragraph()
                    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                    p.add_run("FRONT\n").bold = True
                    p.runs[0].font.size = Pt(9)
                    p.runs[0].font.color.rgb = RGBColor(100, 100, 100)
                    p.add_run().add_picture(str(front_tmp), width=card_w, height=card_h)

                elif back_tmp:
                    p = doc.add_paragraph()
                    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                    p.add_run("BACK\n").bold = True
                    p.runs[0].font.size = Pt(9)
                    p.runs[0].font.color.rgb = RGBColor(100, 100, 100)
                    p.add_run().add_picture(str(back_tmp), width=card_w, height=card_h)

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
