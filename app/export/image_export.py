"""
Image File Exporter.

Saves the unified side-by-side FRONT|BACK print layout (rendered by
PrintLayoutEngine) as lossless PNG or JPG. The exported image contains ONLY
the two card images — no text, labels, or metadata.
"""
from pathlib import Path
from typing import Union, List, Optional
import cv2
import numpy as np

from app.core.models import SheetQueue, ProcessedImage, CardPair
from app.core.profiles import FormatProfile, CARD_PROFILE
from app.core.print_layout import PrintLayoutEngine
from app.utils.image_io import save_image_safe
from app.utils.logger import get_logger

logger = get_logger("image_export")


class ImageExporter:
    """Exports the unified print layout / processed images to disk."""

    @classmethod
    def export_card_pair(
        cls,
        card_pair: CardPair,
        output_path: Union[str, Path],
        copies: int = 1,
        single_page: bool = False,
        format_ext: str = ".png",
        quality: int = 95,
    ) -> List[Path]:
        """
        Saves the side-by-side FRONT|BACK (or tiled) print layout to a single image.
        """
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        saved: List[Path] = []

        front = card_pair.front
        back = card_pair.back
        front_img = front.final_image if front is not None else None
        back_img = back.final_image if back is not None else None

        if front_img is None and back_img is None:
            logger.warning("No card images to export.")
            return saved

        engine = PrintLayoutEngine()
        rendered, _ = engine.render_pair(
            front_img, back_img, card_pair.format_profile,
            copies=copies, single_page=single_page,
        )
        if rendered is not None:
            if save_image_safe(rendered, out, quality=quality):
                saved.append(out)

        logger.info(f"Exported {len(saved)} card layout image(s) to {out.parent}")
        return saved

    @classmethod
    def export_single_card(
        cls,
        processed: ProcessedImage,
        output_path: Union[str, Path],
        format_ext: str = ".png",
        quality: int = 95,
    ) -> bool:
        """Exports a single processed card image (individual side)."""
        img = processed.final_image if processed is not None else None
        if img is None:
            return False
        return save_image_safe(img, output_path, quality=quality)

    @classmethod
    def export_sheet_queue(
        cls,
        queue: SheetQueue,
        output_dir: Union[str, Path],
        file_prefix: str = "page",
        format_ext: str = ".png",
        quality: int = 95,
    ) -> List[Path]:
        """Saves all pages in the sheet queue to output directory."""
        out_dir = Path(output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        saved_paths: List[Path] = []
        for idx, page in enumerate(queue.pages):
            img = page.final_image
            if img is not None:
                page_file = out_dir / f"{file_prefix}_{idx + 1:02d}{format_ext}"
                if save_image_safe(img, page_file, quality=quality):
                    saved_paths.append(page_file)
        logger.info(f"Exported {len(saved_paths)} sheet images to {out_dir}")
        return saved_paths
