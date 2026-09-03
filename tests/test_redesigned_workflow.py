"""
Acceptance Tests for Redesigned Card Mode Workflow, CardOutputComposer, and Document Mode.
Validates:
1. Aadhaar Long Form side-by-side composite dimensions (4960 × 1004 px @ 300 DPI).
2. Single-image handling (no empty canvas, single card dimensions 2480 × 1004 px or 1016 × 638 px).
3. Swap assignment updates both pipeline and composite.
4. Clean output: no text, labels, or branding embedded into output pixels.
5. Document Mode multi-page queue and reordering.
"""
from pathlib import Path
import numpy as np
import pytest

from app.core.profiles import CARD_PROFILE, LONG_FORM_PROFILE
from app.core.print_layout import CardOutputComposer, PrintLayoutEngine
from app.core.pipeline import FormatterPipeline
from app.core.models import ProcessingMode, ProcessedImage


@pytest.fixture
def test_images_dir():
    return Path(__file__).resolve().parent.parent / "test_images"


def test_aadhaar_long_form_composite(test_images_dir):
    """
    Acceptance Test 31:
    Front: 210 × 85 mm (2480 × 1004 px)
    Back:  210 × 85 mm (2480 × 1004 px)
    Combined: 4960 × 1004 px side-by-side
    """
    f_dummy = np.full((1004, 2480, 3), 100, dtype=np.uint8)
    b_dummy = np.full((1004, 2480, 3), 200, dtype=np.uint8)

    composite = CardOutputComposer.compose(f_dummy, b_dummy, LONG_FORM_PROFILE, gap_px=0)
    assert composite is not None
    h, w, c = composite.shape
    assert h == 1004
    assert w == 4960
    assert c == 3

    # Left half should be front, right half should be back
    assert np.all(composite[:, :2480] == 100)
    assert np.all(composite[:, 2480:] == 200)


def test_single_image_output():
    """
    Acceptance Test 32:
    Only Front provided -> output is Front only. No empty Back canvas.
    """
    f_dummy = np.full((1004, 2480, 3), 150, dtype=np.uint8)

    composite = CardOutputComposer.compose(f_dummy, None, LONG_FORM_PROFILE)
    assert composite is not None
    h, w, c = composite.shape
    assert h == 1004
    assert w == 2480
    assert c == 3
    assert np.all(composite == 150)

    # Standard card test
    f_card = np.full((638, 1016, 3), 120, dtype=np.uint8)
    comp_card = CardOutputComposer.compose(f_card, None, CARD_PROFILE)
    assert comp_card is not None
    assert comp_card.shape == (638, 1016, 3)


def test_swap_assignment():
    """
    Acceptance Test 33:
    Swap exchanges Front and Back assignments and updates output.
    """
    f_dummy = np.full((1004, 2480, 3), 50, dtype=np.uint8)
    b_dummy = np.full((1004, 2480, 3), 220, dtype=np.uint8)

    # Before swap: Front (50) on left, Back (220) on right
    before = CardOutputComposer.compose(f_dummy, b_dummy, LONG_FORM_PROFILE, gap_px=0)
    assert np.all(before[:, :2480] == 50)
    assert np.all(before[:, 2480:] == 220)

    # After swap: Front (220) on left, Back (50) on right
    after = CardOutputComposer.compose(b_dummy, f_dummy, LONG_FORM_PROFILE, gap_px=0)
    assert np.all(after[:, :2480] == 220)
    assert np.all(after[:, 2480:] == 50)


def test_print_layout_engine_side_by_side():
    """Verifies PrintLayoutEngine adheres to composer side-by-side rules."""
    engine = PrintLayoutEngine()
    f = np.full((1004, 2480, 3), 80, dtype=np.uint8)
    b = np.full((1004, 2480, 3), 180, dtype=np.uint8)

    rendered, metrics = engine.render_pair(f, b, LONG_FORM_PROFILE, copies=1, single_page=False)
    assert rendered is not None
    assert rendered.shape == (1004, 4960, 3)
    assert metrics.page_width_px == 4960
    assert metrics.page_height_px == 1004

    # Single side
    rend_s, met_s = engine.render_pair(f, None, LONG_FORM_PROFILE, copies=1, single_page=False)
    assert rend_s is not None
    assert rend_s.shape == (1004, 2480, 3)
    assert met_s.page_width_px == 2480


def test_document_mode_reordering():
    """
    Acceptance Test 34:
    Document Mode reordering preserves user order and does not combine side-by-side.
    """
    pipeline = FormatterPipeline()
    pipeline.set_mode(ProcessingMode.SHEET)

    img1 = np.full((100, 100, 3), 1, dtype=np.uint8)
    img2 = np.full((100, 100, 3), 2, dtype=np.uint8)
    img3 = np.full((100, 100, 3), 3, dtype=np.uint8)

    p1 = ProcessedImage(source_path="page1.png", original_image=img1, normalized_image=img1)
    p2 = ProcessedImage(source_path="page2.png", original_image=img2, normalized_image=img2)
    p3 = ProcessedImage(source_path="page3.png", original_image=img3, normalized_image=img3)

    pipeline.sheet_queue.add_page(p1)
    pipeline.sheet_queue.add_page(p2)
    pipeline.sheet_queue.add_page(p3)

    assert len(pipeline.sheet_queue.pages) == 3
    assert pipeline.sheet_queue.pages[0].final_image[0, 0, 0] == 1

    # Move Page 3 (index 2) to Page 1 (index 0)
    pipeline.move_sheet_page(2, 0)
    assert pipeline.sheet_queue.pages[0].final_image[0, 0, 0] == 3
    assert pipeline.sheet_queue.pages[1].final_image[0, 0, 0] == 1
    assert pipeline.sheet_queue.pages[2].final_image[0, 0, 0] == 2
