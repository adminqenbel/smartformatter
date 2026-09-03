"""
Print Enhancement Filters for Documents and Cards.
Provides crisp document enhancement, auto-levels, and clean black-and-white print modes.
"""
import cv2
import numpy as np

from app.core.models import EnhancementMode
from app.utils.logger import get_logger

logger = get_logger("enhancement")


class ImageEnhancer:
    """Enhancement filters specifically optimized for document and ID card printing."""

    @classmethod
    def apply(cls, image: np.ndarray, mode: EnhancementMode) -> np.ndarray:
        """Applies the selected enhancement mode to the image."""
        if mode == EnhancementMode.ORIGINAL or image is None:
            return image.copy()
        elif mode == EnhancementMode.DOCUMENT_CRISP:
            return cls.document_crisp(image)
        elif mode == EnhancementMode.AUTO_LEVELS:
            return cls.auto_levels(image)
        elif mode == EnhancementMode.HIGH_CONTRAST_BW:
            return cls.high_contrast_bw(image)
        return image.copy()

    @staticmethod
    def document_crisp(image: np.ndarray) -> np.ndarray:
        """
        Enhances document text clarity and neutralizes paper yellowing/shadows
        without distorting photo colors.
        """
        # 1. White balance via percentile illumination normalization
        lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB).astype(np.float32)
        l_chan = lab[:, :, 0]

        # White point estimation (98th percentile)
        p_high = np.percentile(l_chan, 98)
        p_low = np.percentile(l_chan, 2)

        if p_high > p_low + 10:
            # Stretch L channel to fill [0, 255]
            l_stretched = np.clip((l_chan - p_low) * (255.0 / (p_high - p_low)), 0, 255)
            lab[:, :, 0] = l_stretched

        normalized = cv2.cvtColor(lab.astype(np.uint8), cv2.COLOR_LAB2BGR)

        # 2. Mild unsharp mask for crisp text edges
        gaussian = cv2.GaussianBlur(normalized, (0, 0), 2.0)
        unsharp = cv2.addWeighted(normalized, 1.35, gaussian, -0.35, 0)

        return unsharp

    @staticmethod
    def auto_levels(image: np.ndarray) -> np.ndarray:
        """Per-channel histogram stretch for vibrant, balanced colors."""
        channels = cv2.split(image)
        out_channels = []
        for ch in channels:
            p_low = np.percentile(ch, 1)
            p_high = np.percentile(ch, 99)
            if p_high > p_low:
                stretched = np.clip((ch.astype(np.float32) - p_low) * (255.0 / (p_high - p_low)), 0, 255).astype(np.uint8)
                out_channels.append(stretched)
            else:
                out_channels.append(ch)
        return cv2.merge(out_channels)

    @staticmethod
    def high_contrast_bw(image: np.ndarray) -> np.ndarray:
        """
        Adaptive Gaussian thresholding for ultra-crisp monochrome documents,
        invoices, receipts, and forms.
        """
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        # Background illumination estimation using large morphological opening or blur
        bg = cv2.GaussianBlur(gray, (25, 25), 0)
        diff = cv2.absdiff(gray, bg)
        # Adaptive threshold
        bw = cv2.adaptiveThreshold(
            gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 21, 10
        )
        # Convert 1-channel binary to 3-channel BGR for consistent pipeline handling
        return cv2.cvtColor(bw, cv2.COLOR_GRAY2BGR)
