"""
Dimension and Aspect Ratio Normalizer.
Ensures cards, long-form documents, and sheets match target physical profile dimensions
without distortion, and synchronizes front/back pairs to identical scale.
"""
from typing import Tuple, Optional
import cv2
import numpy as np

from app.core.profiles import FormatProfile, CARD_PROFILE, A4_PROFILE
from app.utils.logger import get_logger

logger = get_logger("normalizer")


class ImageNormalizer:
    """Normalizes images to canonical print dimensions defined by FormatProfile."""

    @classmethod
    def normalize(
        cls,
        image: np.ndarray,
        profile: Optional[FormatProfile] = None,
        target_width: Optional[int] = None,
        target_height: Optional[int] = None
    ) -> np.ndarray:
        """
        Normalizes an image to the exact pixel dimensions specified by a FormatProfile
        (or explicit target dimensions) using high-quality Lanczos-4 interpolation.
        Preserves aspect ratio alignment with the profile's canonical orientation.
        """
        if profile is None:
            profile = CARD_PROFILE

        h, w = image.shape[:2]
        is_image_landscape = w >= h

        if target_width is not None and target_height is not None:
            tw, th = target_width, target_height
        else:
            # Determine target dimensions from profile, taking image orientation into account
            if profile.is_landscape:
                if is_image_landscape:
                    tw = profile.width_px
                    th = profile.height_px
                else:
                    # Portrait image on landscape profile: swap to avoid stretching
                    tw = profile.height_px
                    th = profile.width_px
            else:
                if not is_image_landscape:
                    tw = profile.width_px
                    th = profile.height_px
                else:
                    # Landscape image on portrait profile: swap to avoid stretching
                    tw = profile.height_px
                    th = profile.width_px

        if w == tw and h == th:
            return image.copy()

        normalized = cv2.resize(image, (tw, th), interpolation=cv2.INTER_LANCZOS4)
        return normalized

    @classmethod
    def normalize_card(
        cls,
        image: np.ndarray,
        target_width: Optional[int] = None,
        target_height: Optional[int] = None,
        profile: Optional[FormatProfile] = None
    ) -> np.ndarray:
        """
        Normalizes a card or long-form document to target profile dimensions.
        Defaults to CARD_PROFILE if no profile is specified.
        """
        active_profile = profile or CARD_PROFILE
        return cls.normalize(image, profile=active_profile, target_width=target_width, target_height=target_height)

    @classmethod
    def normalize_sheet(
        cls,
        image: np.ndarray,
        target_width: Optional[int] = None,
        target_height: Optional[int] = None,
        profile: Optional[FormatProfile] = None
    ) -> np.ndarray:
        """
        Normalizes a sheet image to A4 printable resolution (2480x3508 px @ 300 DPI)
        or proportional high-resolution output.
        """
        active_profile = profile or A4_PROFILE
        return cls.normalize(image, profile=active_profile, target_width=target_width, target_height=target_height)

    @classmethod
    def synchronize_card_pair(
        cls,
        front_img: Optional[np.ndarray],
        back_img: Optional[np.ndarray],
        profile: Optional[FormatProfile] = None
    ) -> Tuple[Optional[np.ndarray], Optional[np.ndarray], int, int]:
        """
        Synchronizes Front and Back card dimensions to identical canonical size defined by FormatProfile.
        Respects individual image orientations (landscape vs portrait) to prevent stretching or squashing.
        """
        if front_img is None and back_img is None:
            return None, None, 0, 0

        active_profile = profile or CARD_PROFILE

        def _get_target_dims(img: np.ndarray) -> Tuple[int, int]:
            ih, iw = img.shape[:2]
            if iw >= ih:  # Landscape
                if active_profile.is_landscape:
                    return active_profile.width_px, active_profile.height_px
                else:
                    return active_profile.height_px, active_profile.width_px
            else:  # Portrait
                if active_profile.is_landscape:
                    return active_profile.height_px, active_profile.width_px
                else:
                    return active_profile.width_px, active_profile.height_px

        norm_front = None
        target_w, target_h = 0, 0
        if front_img is not None:
            fw, fh = _get_target_dims(front_img)
            norm_front = cls.normalize(front_img, profile=active_profile, target_width=fw, target_height=fh)
            target_w, target_h = fw, fh

        norm_back = None
        if back_img is not None:
            bw, bh = _get_target_dims(back_img)
            norm_back = cls.normalize(back_img, profile=active_profile, target_width=bw, target_height=bh)
            if target_w == 0:
                target_w, target_h = bw, bh

        return norm_front, norm_back, target_w, target_h
