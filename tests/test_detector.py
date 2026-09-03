"""
Unit and Regression tests for OpenCV Document & Card Detection.
Includes real-world WhatsApp card captures and synthetic benchmark images.
"""
from pathlib import Path
import numpy as np
import pytest

from app.core.models import CornerPoints
from app.processing.opencv_detector import OpenCVDetector
from app.utils.image_io import load_image_safe


@pytest.fixture
def detector():
    return OpenCVDetector()


@pytest.fixture
def test_images_dir():
    return Path(__file__).resolve().parent.parent / "test_images"


def test_detect_straight_card(detector, test_images_dir):
    img_path = test_images_dir / "cards" / "card_01_straight_front.jpg"
    img = load_image_safe(img_path)
    assert img is not None

    res = detector.detect_card(img)
    assert res.corners is not None
    assert res.confidence >= 0.70
    assert not res.is_fallback


def test_detect_rotated_perspective_card(detector, test_images_dir):
    img_path = test_images_dir / "cards" / "card_02_rotated_perspective_back.jpg"
    img = load_image_safe(img_path)
    assert img is not None

    res = detector.detect_card(img)
    assert res.corners is not None
    assert res.confidence >= 0.70
    assert not res.is_fallback


def test_detect_real_world_aadhaar_card(detector, test_images_dir):
    """Regression test for real-world card photo on concrete floor."""
    real_sample_path = test_images_dir / "real_samples" / "WhatsApp Image 2026-09-01 at 9.36.55 PM (2).jpeg"
    if not real_sample_path.exists():
        pytest.skip("Real sample image not present in test_images/real_samples")

    img = load_image_safe(real_sample_path)
    assert img is not None

    res = detector.detect_card(img)
    assert res.corners is not None
    assert not res.is_fallback
    assert res.confidence >= 0.75

    # Verify that the detected quadrilateral is NOT the outer camera frame
    # (i.e. does not have corners at (0, 0) and (1600, 1200))
    tl = res.corners.top_left
    br = res.corners.bottom_right
    assert tl[1] > 100 # Card top is below y=100
    assert br[1] < 1100 # Card bottom is above y=1100
    assert (br[0] - tl[0]) > 800 # Card width is substantial
