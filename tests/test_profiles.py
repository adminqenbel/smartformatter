"""
Unit and Regression Tests for Physical Format Profiles (Card vs Long Form) and Mismatch Validation.
"""
from pathlib import Path
import pytest
import numpy as np

from app.core.profiles import (
    FormatProfile,
    CARD_PROFILE,
    LONG_FORM_PROFILE,
    A4_PROFILE,
    ProfileRegistry,
)
from app.core.models import EnhancementMode, ConfidenceLevel
from app.processing.card_processor import CardProcessor
from app.processing.normalizer import ImageNormalizer


@pytest.fixture
def card_processor():
    return CardProcessor()


@pytest.fixture
def test_images_dir():
    return Path(__file__).resolve().parent.parent / "test_images"


def test_format_profile_dynamic_dimensions():
    """Validates that pixel dimensions are calculated dynamically from physical_mm / 25.4 * DPI."""
    card = CARD_PROFILE
    assert card.width_mm == 86.0
    assert card.height_mm == 54.0
    assert card.dpi == 300
    assert card.width_px == int(round((86.0 / 25.4) * 300))  # 1016 px
    assert card.height_px == int(round((54.0 / 25.4) * 300)) # 638 px
    assert abs(card.aspect_ratio - (86.0 / 54.0)) < 0.01

    long_form = LONG_FORM_PROFILE
    assert long_form.width_mm == 210.0
    assert long_form.height_mm == 85.0
    assert long_form.dpi == 300
    assert long_form.width_px == int(round((210.0 / 25.4) * 300))  # 2480 px
    assert long_form.height_px == int(round((85.0 / 25.4) * 300)) # 1004 px
    assert abs(long_form.aspect_ratio - (210.0 / 85.0)) < 0.01


def test_long_form_aadhaar_processing(card_processor, test_images_dir):
    """
    Regression Test: Processes the real Long-Form Aadhaar document under LONG_FORM_PROFILE.
    Verifies:
    1. Correct physical dimensions: ~2480 x 1004 px @ 300 DPI
    2. Aspect ratio: ~2.47:1 (no distortion or squeezing into 1011x638)
    3. Correct orientation & high confidence
    """
    real_f = test_images_dir / "real_samples" / "WhatsApp Image 2026-09-01 at 9.36.55 PM (2).jpeg"
    if not real_f.exists():
        pytest.skip("Real long-form sample not available")

    processed = card_processor.process_image(
        real_f,
        profile=LONG_FORM_PROFILE,
        enhancement_mode=EnhancementMode.DOCUMENT_CRISP
    )

    assert processed is not None
    assert processed.normalized_image is not None

    h, w = processed.normalized_image.shape[:2]
    assert w == LONG_FORM_PROFILE.width_px   # 2480 px
    assert h == LONG_FORM_PROFILE.height_px  # 1004 px
    assert abs((w / h) - (210.0 / 85.0)) < 0.05

    # Verify orientation
    assert processed.orientation_result is not None
    assert processed.format_profile.id == "long_form"

    # Verify granular confidence report
    qr = processed.quality_report
    assert qr is not None
    assert qr.boundary_confidence >= 0.70
    assert qr.format_confidence >= 0.85
    assert not qr.format_mismatch


def test_card_profile_processing(card_processor, test_images_dir):
    """
    Processes standard Card image under CARD_PROFILE.
    Verifies dimensions match CARD_PROFILE (1016x638 px @ 300 DPI) and aspect ratio ~1.59:1.
    """
    card_img = test_images_dir / "cards" / "card_01_straight_front.jpg"
    processed = card_processor.process_image(card_img, profile=CARD_PROFILE)

    assert processed is not None
    assert processed.normalized_image is not None

    h, w = processed.normalized_image.shape[:2]
    assert w == CARD_PROFILE.width_px   # 1016 px
    assert h == CARD_PROFILE.height_px  # 638 px


def test_format_mismatch_detection(card_processor, test_images_dir):
    """
    Verifies that loading a Card image (aspect ratio ~1.55) under LONG_FORM_PROFILE (2.47:1)
    flags format_mismatch=True, reduces format_confidence, and suggests CARD_PROFILE.
    """
    card_img = test_images_dir / "cards" / "card_02_rotated_perspective_back.jpg"
    processed = card_processor.process_image(card_img, profile=LONG_FORM_PROFILE)
    assert processed is not None
    qr = processed.quality_report
    assert qr is not None
    assert qr.format_mismatch is True
    assert qr.suggested_profile == "card"
    assert qr.format_confidence <= 0.50
    assert qr.overall_confidence <= 0.60


def test_runtime_profile_switch(card_processor, test_images_dir):
    """
    Verifies that switching profile at runtime re-normalizes without distortion.
    """
    real_f = test_images_dir / "real_samples" / "WhatsApp Image 2026-09-01 at 9.36.55 PM (2).jpeg"
    if not real_f.exists():
        pytest.skip("Real long-form sample not available")

    # Start with Card profile
    processed = card_processor.process_image(real_f, profile=CARD_PROFILE)
    assert processed.normalized_image.shape == (638, 1016, 3)

    # Switch to Long Form profile
    updated = card_processor.update_profile(processed, LONG_FORM_PROFILE)
    assert updated.normalized_image.shape == (1004, 2480, 3)
    assert updated.format_profile.id == "long_form"
    assert updated.quality_report.format_mismatch is False
