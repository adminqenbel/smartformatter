"""
Unit tests for SheetProcessor and Page Queue Management.
"""
from pathlib import Path
import pytest

from app.core.config import PrintConfig
from app.processing.sheet_processor import SheetProcessor
from app.core.models import EnhancementMode


@pytest.fixture
def sheet_processor():
    return SheetProcessor()


@pytest.fixture
def test_images_dir():
    return Path(__file__).resolve().parent.parent / "test_images"


def test_sheet_queue_processing(sheet_processor, test_images_dir):
    s1 = test_images_dir / "sheets" / "sheet_01_invoice_p1.jpg"
    s2 = test_images_dir / "sheets" / "sheet_02_invoice_p2.jpg"

    queue = sheet_processor.process_queue([s1, s2], enhancement_mode=EnhancementMode.ORIGINAL)

    assert len(queue.pages) == 2
    assert queue.pages[0].normalized_image is not None
    assert queue.pages[1].normalized_image is not None

    # Check A4 normalization (Portrait or Landscape)
    w_norm = queue.pages[0].normalized_image.shape[1]
    h_norm = queue.pages[0].normalized_image.shape[0]
    assert {w_norm, h_norm} == {PrintConfig.A4_WIDTH_PX, PrintConfig.A4_HEIGHT_PX}


def test_sheet_page_reordering(sheet_processor, test_images_dir):
    s1 = test_images_dir / "sheets" / "sheet_01_invoice_p1.jpg"
    s2 = test_images_dir / "sheets" / "sheet_02_invoice_p2.jpg"

    queue = sheet_processor.process_queue([s1, s2])
    assert queue.pages[0].source_path == str(s1)

    # Move page 1 down
    queue.move_page_down(0)
    assert queue.pages[0].source_path == str(s2)
    assert queue.pages[1].source_path == str(s1)
