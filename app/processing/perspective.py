"""
Perspective Transformation and Topological Corner Ordering.
Computes precise 4-corner homography transformations.
"""
from typing import Tuple, Union
import cv2
import numpy as np

from app.core.models import CornerPoints
from app.utils.logger import get_logger

logger = get_logger("perspective")


def order_corners(pts: Union[np.ndarray, list]) -> CornerPoints:
    """
    Orders 4 points in consistent clockwise order:
    [0]: Top-Left (TL)
    [1]: Top-Right (TR)
    [2]: Bottom-Right (BR)
    [3]: Bottom-Left (BL)
    """
    pts_arr = np.array(pts, dtype=np.float32).reshape(4, 2)

    # 1. Sum of coordinates (x + y): TL has min sum, BR has max sum
    s = pts_arr.sum(axis=1)
    tl = pts_arr[np.argmin(s)]
    br = pts_arr[np.argmax(s)]

    # 2. Difference of coordinates (y - x): TR has min diff, BL has max diff
    # Alternatively (x - y): TR has max diff, BL has min diff
    diff = np.diff(pts_arr, axis=1) # [y - x]
    tr = pts_arr[np.argmin(diff)]
    bl = pts_arr[np.argmax(diff)]

    # Validate that we have 4 distinct points
    ordered = np.array([tl, tr, br, bl], dtype=np.float32)

    # Fallback to polar angle sorting if any duplicate assignments occurred
    if len(np.unique(ordered, axis=0)) < 4:
        center = np.mean(pts_arr, axis=0)
        angles = np.arctan2(pts_arr[:, 1] - center[1], pts_arr[:, 0] - center[0])
        sorted_indices = np.argsort(angles)
        sorted_pts = pts_arr[sorted_indices]
        # Shift to start from top-left (angle around -3pi/4)
        tl_idx = np.argmin(np.sum(sorted_pts, axis=1))
        ordered = np.roll(sorted_pts, -tl_idx, axis=0)

    return CornerPoints(
        top_left=(float(ordered[0][0]), float(ordered[0][1])),
        top_right=(float(ordered[1][0]), float(ordered[1][1])),
        bottom_right=(float(ordered[2][0]), float(ordered[2][1])),
        bottom_left=(float(ordered[3][0]), float(ordered[3][1]))
    )


def calculate_target_dimensions(corners: CornerPoints) -> Tuple[int, int]:
    """
    Calculates the natural width and height from the Euclidean edge lengths of the 4 corners.
    """
    tl = np.array(corners.top_left)
    tr = np.array(corners.top_right)
    br = np.array(corners.bottom_right)
    bl = np.array(corners.bottom_left)

    # Width: max of top edge and bottom edge
    width_top = np.linalg.norm(tr - tl)
    width_bottom = np.linalg.norm(br - bl)
    max_width = int(max(width_top, width_bottom))

    # Height: max of left edge and right edge
    height_left = np.linalg.norm(bl - tl)
    height_right = np.linalg.norm(br - tr)
    max_height = int(max(height_left, height_right))

    # Ensure valid non-zero dimensions
    max_width = max(10, max_width)
    max_height = max(10, max_height)

    return max_width, max_height


def warp_perspective(
    image: np.ndarray,
    corners: CornerPoints,
    target_width: int,
    target_height: int
) -> np.ndarray:
    """
    Applies homography perspective correction to warp the 4-corner document region
    into a flat, rectilinear image of size (target_width, target_height).
    """
    src_pts = corners.to_numpy(dtype=np.float32)
    dst_pts = np.array([
        [0, 0],
        [target_width - 1, 0],
        [target_width - 1, target_height - 1],
        [0, target_height - 1]
    ], dtype=np.float32)

    # Calculate 3x3 Homography Transformation Matrix
    matrix = cv2.getPerspectiveTransform(src_pts, dst_pts)

    # Apply perspective transformation with Lanczos-4 interpolation for maximum sharpness
    warped = cv2.warpPerspective(
        image,
        matrix,
        (target_width, target_height),
        flags=cv2.INTER_LANCZOS4,
        borderMode=cv2.BORDER_REPLICATE
    )

    return warped
