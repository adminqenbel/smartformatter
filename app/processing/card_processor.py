"""
Card and Long-Form Document Processing Pipeline.
Handles boundary detection, perspective warping, profile-driven orientation,
physical normalization (Card / Long Form), format validation, and duplex synchronization.
"""
from typing import Optional, Union, Tuple
from pathlib import Path
import numpy as np

from app.core.profiles import FormatProfile, CARD_PROFILE, ProfileRegistry
from app.core.models import (
    ProcessedImage,
    CardPair,
    CornerPoints,
    EnhancementMode,
    DetectionResult,
    OrientationResult,
)
from app.processing.opencv_detector import OpenCVDetector
from app.processing.perspective import (
    warp_perspective,
    calculate_target_dimensions,
    order_corners,
)
from app.processing.orientation import rotate_image, DocumentOrientationDetector
from app.processing.normalizer import ImageNormalizer
from app.processing.enhancement import ImageEnhancer
from app.processing.quality import QualityEngine
from app.utils.image_io import load_image_safe
from app.utils.logger import get_logger

logger = get_logger("card_processor")


class CardProcessor:
    """Specialized processing workflow for physical cards and long-form documents."""

    def __init__(
        self,
        detector: Optional[OpenCVDetector] = None,
        orientation_detector: Optional[DocumentOrientationDetector] = None
    ):
        self.detector = detector or OpenCVDetector()
        self.orientation_detector = orientation_detector or DocumentOrientationDetector()
        self.quality_engine = QualityEngine()

    def process_image(
        self,
        source: Union[str, Path, np.ndarray],
        profile: Optional[FormatProfile] = None,
        manual_corners: Optional[CornerPoints] = None,
        manual_rotation_deg: int = 0,
        enhancement_mode: EnhancementMode = EnhancementMode.ORIGINAL
    ) -> Optional[ProcessedImage]:
        """
        Processes a single card or long-form document image end-to-end:
        image -> document detection -> 4 corners -> perspective warp ->
        selected output profile -> orientation detection -> rotation correction ->
        physical normalization -> quality/format validation -> enhancement -> output
        """
        active_profile = profile or CARD_PROFILE

        if isinstance(source, (str, Path)):
            source_path = str(source)
            original_image = load_image_safe(source_path)
            if original_image is None:
                logger.error(f"Failed to load image from {source_path}")
                return None
        else:
            source_path = "memory_buffer"
            original_image = source.copy()

        # 1. Detection: Use manual corners if provided, otherwise run automated detector
        if manual_corners is not None:
            active_corners = manual_corners
            detection_res = DetectionResult(
                corners=manual_corners,
                confidence=1.0,
                method="manual_user_correction",
                is_fallback=False
            )
            is_manual = True
        else:
            detection_res = self.detector.detect_card(original_image, profile=active_profile)
            active_corners = detection_res.corners
            is_manual = False

        if active_corners is None:
            h, w = original_image.shape[:2]
            active_corners = CornerPoints((0, 0), (w, 0), (w, h), (0, h))

        # 2. Perspective Correction (Warp Quadrilateral to Natural Euclidean Dimensions)
        nat_w, nat_h = calculate_target_dimensions(active_corners)
        warped = warp_perspective(original_image, active_corners, nat_w, nat_h)

        # Calculate detected aspect ratio (orientation-invariant max/min)
        detected_aspect_ratio = max(nat_w, nat_h) / max(min(nat_w, nat_h), 1)

        # 3. Orientation Detection using Profile Canonical Geometry & Evidence
        orient_res = self.orientation_detector.detect_orientation(
            warped,
            profile=active_profile,
            image_name=Path(source_path).stem if isinstance(source, (str, Path)) else "card"
        )
        auto_rot = orient_res.best_angle

        # 4. Rotation Correction (Auto orientation + Manual adjustment)
        effective_rot = (auto_rot + manual_rotation_deg) % 360
        oriented = rotate_image(warped, effective_rot) if effective_rot != 0 else warped.copy()

        # 5. Physical Normalization according to active FormatProfile (Card / Long Form)
        normalized = ImageNormalizer.normalize(oriented, profile=active_profile)

        # 6. Apply Print Enhancement Filter
        enhanced = ImageEnhancer.apply(normalized, enhancement_mode)

        # 7. Evaluate Multi-Factor Quality, Granular Confidence, and Format Match
        quality = self.quality_engine.evaluate(
            normalized,
            corners=active_corners,
            detection_confidence=detection_res.confidence,
            orientation_confidence=orient_res.confidence,
            profile=active_profile,
            detected_aspect_ratio=detected_aspect_ratio,
            is_card=True,
            is_fallback=detection_res.is_fallback
        )

        return ProcessedImage(
            source_path=source_path,
            original_image=original_image,
            detected_corners=detection_res.corners,
            current_corners=active_corners,
            warped_image=warped,
            oriented_image=oriented,
            normalized_image=normalized,
            enhanced_image=enhanced,
            auto_rotation_deg=auto_rot,
            manual_rotation_deg=manual_rotation_deg,
            orientation_result=orient_res,
            enhancement_mode=enhancement_mode,
            format_profile=active_profile,
            quality_report=quality,
            is_manually_edited=is_manual
        )

    def process_pair(
        self,
        front_source: Optional[Union[str, Path, np.ndarray]] = None,
        back_source: Optional[Union[str, Path, np.ndarray]] = None,
        profile: Optional[FormatProfile] = None,
        enhancement_mode: EnhancementMode = EnhancementMode.ORIGINAL
    ) -> CardPair:
        """Processes Front and Back cards independently and synchronizes them to the selected profile."""
        active_profile = profile or CARD_PROFILE

        front_proc = (
            self.process_image(front_source, profile=active_profile, enhancement_mode=enhancement_mode)
            if front_source is not None else None
        )
        back_proc = (
            self.process_image(back_source, profile=active_profile, enhancement_mode=enhancement_mode)
            if back_source is not None else None
        )

        card_pair = CardPair(front=front_proc, back=back_proc, format_profile=active_profile)
        self.synchronize_pair(card_pair)
        return card_pair

    def synchronize_pair(self, card_pair: CardPair):
        """Forces Front and Back to share exact identical pixel dimensions defined by active profile."""
        profile = card_pair.format_profile or CARD_PROFILE

        f_img = card_pair.front.oriented_image if (card_pair.front and card_pair.front.oriented_image is not None) else (
            card_pair.front.final_image if card_pair.front else None
        )
        b_img = card_pair.back.oriented_image if (card_pair.back and card_pair.back.oriented_image is not None) else (
            card_pair.back.final_image if card_pair.back else None
        )

        norm_f, norm_b, tw, th = ImageNormalizer.synchronize_card_pair(f_img, b_img, profile=profile)
        card_pair.synchronized_width = tw
        card_pair.synchronized_height = th

        if card_pair.front is not None and norm_f is not None:
            card_pair.front.format_profile = profile
            card_pair.front.normalized_image = norm_f
            card_pair.front.enhanced_image = ImageEnhancer.apply(norm_f, card_pair.front.enhancement_mode)

        if card_pair.back is not None and norm_b is not None:
            card_pair.back.format_profile = profile
            card_pair.back.normalized_image = norm_b
            card_pair.back.enhanced_image = ImageEnhancer.apply(norm_b, card_pair.back.enhancement_mode)

    def update_profile(
        self,
        processed: ProcessedImage,
        new_profile: FormatProfile
    ) -> ProcessedImage:
        """Updates the physical format profile and re-normalizes without re-detecting."""
        processed.format_profile = new_profile
        oriented = processed.oriented_image if processed.oriented_image is not None else processed.warped_image

        if oriented is not None:
            normalized = ImageNormalizer.normalize(oriented, profile=new_profile)
            enhanced = ImageEnhancer.apply(normalized, processed.enhancement_mode)

            nat_w, nat_h = (
                calculate_target_dimensions(processed.current_corners)
                if processed.current_corners is not None
                else (oriented.shape[1], oriented.shape[0])
            )
            det_aspect_ratio = max(nat_w, nat_h) / max(min(nat_w, nat_h), 1)

            quality = self.quality_engine.evaluate(
                normalized,
                corners=processed.current_corners,
                detection_confidence=1.0 if processed.is_manually_edited else (
                    processed.quality_report.boundary_confidence if processed.quality_report else 1.0
                ),
                orientation_confidence=processed.orientation_result.confidence if processed.orientation_result else 1.0,
                profile=new_profile,
                detected_aspect_ratio=det_aspect_ratio,
                is_card=True,
                is_fallback=False
            )

            processed.normalized_image = normalized
            processed.enhanced_image = enhanced
            processed.quality_report = quality

        return processed

    def update_manual_rotation(
        self,
        processed: ProcessedImage,
        manual_rotation_deg: int
    ) -> ProcessedImage:
        """Applies manual operator rotation (0, 90, 180, 270) to an already warped card."""
        processed.manual_rotation_deg = manual_rotation_deg % 360
        effective_rot = processed.total_rotation_deg
        oriented = rotate_image(processed.warped_image, effective_rot) if effective_rot != 0 else processed.warped_image.copy()
        
        normalized = ImageNormalizer.normalize(oriented, profile=processed.format_profile)
        enhanced = ImageEnhancer.apply(normalized, processed.enhancement_mode)

        nat_w, nat_h = (
            calculate_target_dimensions(processed.current_corners)
            if processed.current_corners is not None
            else (oriented.shape[1], oriented.shape[0])
        )
        det_aspect_ratio = max(nat_w, nat_h) / max(min(nat_w, nat_h), 1)

        quality = self.quality_engine.evaluate(
            normalized,
            corners=processed.current_corners,
            detection_confidence=1.0 if processed.is_manually_edited else (
                processed.quality_report.boundary_confidence if processed.quality_report else 1.0
            ),
            orientation_confidence=1.0,  # Manual user rotation sets orientation confidence to 100%
            profile=processed.format_profile,
            detected_aspect_ratio=det_aspect_ratio,
            is_card=True,
            is_fallback=False
        )

        processed.oriented_image = oriented
        processed.normalized_image = normalized
        processed.enhanced_image = enhanced
        processed.quality_report = quality
        return processed

    def recompute_from_corners(
        self,
        processed: ProcessedImage,
        new_corners: CornerPoints
    ) -> ProcessedImage:
        """Re-computes warp, orientation, normalization, and quality when corners are edited."""
        ordered = order_corners(new_corners.to_numpy())
        nat_w, nat_h = calculate_target_dimensions(ordered)
        warped = warp_perspective(processed.original_image, ordered, nat_w, nat_h)
        det_aspect_ratio = max(nat_w, nat_h) / max(min(nat_w, nat_h), 1)

        orient_res = self.orientation_detector.detect_orientation(
            warped,
            profile=processed.format_profile,
            image_name=Path(processed.source_path).stem if processed.source_path else "card"
        )
        processed.auto_rotation_deg = orient_res.best_angle
        processed.orientation_result = orient_res

        effective_rot = processed.total_rotation_deg
        oriented = rotate_image(warped, effective_rot) if effective_rot != 0 else warped.copy()
        normalized = ImageNormalizer.normalize(oriented, profile=processed.format_profile)
        enhanced = ImageEnhancer.apply(normalized, processed.enhancement_mode)

        quality = self.quality_engine.evaluate(
            normalized,
            corners=ordered,
            detection_confidence=1.0,
            orientation_confidence=orient_res.confidence,
            profile=processed.format_profile,
            detected_aspect_ratio=det_aspect_ratio,
            is_card=True,
            is_fallback=False
        )

        processed.current_corners = ordered
        processed.warped_image = warped
        processed.oriented_image = oriented
        processed.normalized_image = normalized
        processed.enhanced_image = enhanced
        processed.quality_report = quality
        processed.is_manually_edited = True

        return processed
