"""
Unit tests for Topological Corner Ordering and Perspective Warping.
"""
import numpy as np
import pytest

from app.core.models import CornerPoints
from app.processing.perspective import order_corners, calculate_target_dimensions, warp_perspective


def test_corner_ordering_scrambled():
    # Unordered 4 corners of a rectangle
    # [TR, BL, BR, TL]
    raw_points = np.array([
        [500.0, 100.0], # TR
        [100.0, 400.0], # BL
        [500.0, 400.0], # BR
        [100.0, 100.0]  # TL
    ])

    ordered = order_corners(raw_points)

    assert ordered.top_left == (100.0, 100.0)
    assert ordered.top_right == (500.0, 100.0)
    assert ordered.bottom_right == (500.0, 400.0)
    assert ordered.bottom_left == (100.0, 400.0)


def test_target_dimensions():
    corners = CornerPoints(
        top_left=(100.0, 100.0),
        top_right=(500.0, 100.0),
        bottom_right=(500.0, 350.0),
        bottom_left=(100.0, 350.0)
    )
    w, h = calculate_target_dimensions(corners)
    assert w == 400
    assert h == 250


def test_warp_perspective_output():
    # Create synthetic test canvas with distinct color quadrant
    canvas = np.zeros((600, 800, 3), dtype=np.uint8)
    canvas[100:400, 150:650] = (120, 200, 255) # BGR rectangle

    corners = CornerPoints(
        top_left=(150.0, 100.0),
        top_right=(650.0, 100.0),
        bottom_right=(650.0, 400.0),
        bottom_left=(150.0, 400.0)
    )

    warped = warp_perspective(canvas, corners, 500, 300)
    assert warped.shape == (300, 500, 3)
    # Center pixel should match the colored rectangle
    assert np.allclose(warped[150, 250], [120, 200, 255], atol=5)
