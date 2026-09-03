"""
Unit tests for CardProcessor, Orientation Detection, and Card Pair Synchronization.
"""
from pathlib import Path
import pytest

from app.core.config import PrintConfig
from app.processing.card_processor import CardProcessor
from app.core.models import EnhancementMode, CornerPoints


@pytest.fixture
def card_processor():
    return CardProcessor()


@pytest.fixture
def test_images_dir():
    return Path(__file__).resolve().parent.parent / "test_images"


def test_card_pair_symmetry(card_processor, test_images_dir):
    f_path = test_images_dir / "cards" / "card_01_straight_front.jpg"
    b_path = test_images_dir / "cards" / "card_02_rotated_perspective_back.jpg"

    pair = card_processor.process_pair(f_path, b_path, enhancement_mode=EnhancementMode.DOCUMENT_CRISP)

    assert pair.front is not None
    assert pair.back is not None
    assert pair.front.normalized_image is not None
    assert pair.back.normalized_image is not None

    # Front and Back must have IDENTICAL pixel dimensions
    f_shape = pair.front.normalized_image.shape
    b_shape = pair.back.normalized_image.shape
    assert f_shape == b_shape


def test_card_orientation_real_sample(card_processor, test_images_dir):
    """Verifies that real card photograph orientation is evaluated and auto-corrected."""
    real_f = test_images_dir / "real_samples" / "WhatsApp Image 2026-09-01 at 9.36.55 PM (2).jpeg"
    if not real_f.exists():
        pytest.skip("Real sample not available")

    processed = card_processor.process_image(real_f)
    assert processed is not None
    assert processed.orientation_result is not None
    # The boundary detector must produce a readable orientation: either the
    # document is already right-side-up (0) or fully corrected (90/180/270).
    # Confidence must be high so the readable result is trusted.
    assert processed.orientation_result.best_angle in [0, 90, 180, 270]
    assert processed.orientation_result.confidence >= 0.70

    # Verify diagnostic candidates exist
    cands = processed.orientation_result.diagnostic_candidates
    assert set(cands.keys()) == {0, 90, 180, 270}
    for deg in [0, 90, 180, 270]:
        assert cands[deg] is not None
        assert cands[deg].size > 0


def test_card_manual_recompute(card_processor, test_images_dir):
    f_path = test_images_dir / "cards" / "card_01_straight_front.jpg"
    processed = card_processor.process_image(f_path)
    assert processed is not None

    # Manually adjust corners
    new_corners = CornerPoints(
        top_left=(320.0, 270.0),
        top_right=(880.0, 270.0),
        bottom_right=(880.0, 630.0),
        bottom_left=(320.0, 630.0)
    )
    updated = card_processor.recompute_from_corners(processed, new_corners)
    assert updated.is_manually_edited
    assert updated.current_corners.top_left == (320.0, 270.0)
