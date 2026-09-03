"""
Image Preprocessing and Illumination Normalization.
Prepares photographs for robust edge detection and geometry analysis.
"""
from typing import Tuple
import cv2
import numpy as np

from app.utils.logger import get_logger

logger = get_logger("preprocessor")


class ImagePreprocessor:
    """Handles image scaling, noise filtering, and illumination normalization."""

    @staticmethod
    def scale_for_processing(
        image: np.ndarray, max_dimension: int = 1200
    ) -> Tuple[np.ndarray, float]:
        """
        Scales down large images to a standard dimension for fast, robust CV processing.
        Returns (scaled_image, scale_factor) where scale_factor = original_size / scaled_size.
        """
        h, w = image.shape[:2]
        longest_edge = max(h, w)

        if longest_edge <= max_dimension:
            return image.copy(), 1.0

        scale = max_dimension / float(longest_edge)
        new_w = int(round(w * scale))
        new_h = int(round(h * scale))

        scaled = cv2.resize(image, (new_w, new_h), interpolation=cv2.INTER_AREA)
        inv_scale = float(longest_edge) / max_dimension

        return scaled, inv_scale

    @staticmethod
    def get_border_mask(h: int, w: int, margin_percent: float = 0.015) -> np.ndarray:
        """Returns a binary mask that suppresses the outer camera frame edges."""
        border_px = int(max(4, margin_percent * min(w, h)))
        mask = np.zeros((h, w), dtype=np.uint8)
        mask[border_px:h - border_px, border_px:w - border_px] = 255
        return mask

    @staticmethod
    def prepare_edge_maps(image: np.ndarray) -> np.ndarray:
        """
        Applies edge-preserving bilateral filtering, CLAHE contrast enhancement,
        and morphological edge extraction, suppressing outer camera borders.
        """
        h, w = image.shape[:2]
        border_mask = ImagePreprocessor.get_border_mask(h, w)

        # Convert to Lab color space for illumination enhancement
        lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB)
        l_channel, a_channel, b_channel = cv2.split(lab)

        # Apply CLAHE to L channel
        clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8))
        l_enhanced = clahe.apply(l_channel)

        # Grayscale from enhanced L
        gray = cv2.cvtColor(cv2.merge([l_enhanced, a_channel, b_channel]), cv2.COLOR_LAB2BGR)
        gray = cv2.cvtColor(gray, cv2.COLOR_BGR2GRAY)

        # Edge-preserving bilateral filter
        filtered = cv2.bilateralFilter(gray, d=9, sigmaColor=75, sigmaSpace=75)

        # Adaptive Otsu Canny
        high_thresh, _ = cv2.threshold(filtered, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        low_thresh = 0.4 * high_thresh

        edges = cv2.Canny(filtered, low_thresh, high_thresh)
        edges = cv2.bitwise_and(edges, edges, mask=border_mask)

        # Morphological close to bridge small gaps
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
        closed_edges = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, kernel, iterations=3)

        return closed_edges

    @staticmethod
    def compute_morphological_gradient(image: np.ndarray) -> np.ndarray:
        """Computes morphological gradient for high-contrast border detection."""
        h, w = image.shape[:2]
        border_mask = ImagePreprocessor.get_border_mask(h, w)

        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        gradient = cv2.morphologyEx(blurred, cv2.MORPH_GRADIENT, kernel)
        _, thresh = cv2.threshold(gradient, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        thresh = cv2.bitwise_and(thresh, thresh, mask=border_mask)
        return thresh
