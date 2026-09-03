"""
Sheet Processing Pipeline.
Handles multi-page document sheet processing, perspective deskew, orientation, normalization, and page management.
"""
from typing import Optional, Union, List
from pathlib import Path
import numpy as np

from app.core.config import PrintConfig
from app.core.models import (
    ProcessedImage,
    SheetQueue,
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
from app.processing.orientation import rotate_image, estimate_deskew_angle, DocumentOrientationDetector
from app.processing.normalizer import ImageNormalizer
from app.processing.enhancement import ImageEnhancer
from app.processing.quality import QualityEngine
from app.utils.image_io import load_image_safe
from app.utils.logger import get_logger

logger = get_logger("sheet_processor")


class SheetProcessor:
    """Specialized processing workflow for document sheets, receipts, and pages."""

    def __init__(
        self,
        detector: Optional[OpenCVDetector] = None,
        orientation_detector: Optional[DocumentOrientationDetector] = None
    ):
        self.detector = detector or OpenCVDetector()
        self.orientation_detector = orientation_detector or DocumentOrientationDetector()
        self.quality_engine = QualityEngine()

    def process_page(
        self,
        source: Union[str, Path, np.ndarray],
        manual_corners: Optional[CornerPoints] = None,
        manual_rotation_deg: int = 0,
        enhancement_mode: EnhancementMode = EnhancementMode.ORIGINAL,
        auto_deskew: bool = True
    ) -> Optional[ProcessedImage]:
        """Processes a single sheet page end-to-end."""
        if isinstance(source, (str, Path)):
            source_path = str(source)
            original_image = load_image_safe(source_path)
            if original_image is None:
                logger.error(f"Failed to load sheet page from {source_path}")
                return None
        else:
            source_path = "memory_buffer"
            original_image = source.copy()

        # 1. Boundary Detection
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
            detection_res = self.detector.detect_sheet(original_image)
            active_corners = detection_res.corners
            is_manual = False

        if active_corners is None:
            h, w = original_image.shape[:2]
            active_corners = CornerPoints((0, 0), (w, 0), (w, h), (0, h))

        # 2. Perspective Correction
        nat_w, nat_h = calculate_target_dimensions(active_corners)
        warped = warp_perspective(original_image, active_corners, nat_w, nat_h)

        # 3. Deskew
        current_img = warped
        if auto_deskew and not is_manual:
            deskew_deg = estimate_deskew_angle(current_img)
            if abs(deskew_deg) > 0.5:
                current_img = rotate_image(current_img, int(round(deskew_deg)))

        # 4. Orientation Detection
        orient_res = self.orientation_detector.detect_orientation(current_img)
        auto_rot = orient_res.best_angle

        # 5. Rotation Correction
        effective_rot = (auto_rot + manual_rotation_deg) % 360
        oriented = rotate_image(current_img, effective_rot) if effective_rot != 0 else current_img.copy()

        # 6. Normalization
        normalized = ImageNormalizer.normalize_sheet(oriented)

        # 7. Print Enhancement
        enhanced = ImageEnhancer.apply(normalized, enhancement_mode)

        # 8. Quality Validation
        quality = self.quality_engine.evaluate(
            normalized,
            corners=active_corners,
            detection_confidence=detection_res.confidence,
            orientation_confidence=orient_res.confidence,
            is_card=False,
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
            quality_report=quality,
            is_manually_edited=is_manual
        )

    def process_queue(
        self,
        sources: List[Union[str, Path, np.ndarray]],
        enhancement_mode: EnhancementMode = EnhancementMode.ORIGINAL
    ) -> SheetQueue:
        """Processes multiple sheet pages into an ordered queue."""
        queue = SheetQueue()
        for src in sources:
            page = self.process_page(src, enhancement_mode=enhancement_mode)
            if page is not None:
                queue.add_page(page)
        return queue

    def update_manual_rotation(
        self,
        processed: ProcessedImage,
        manual_rotation_deg: int
    ) -> ProcessedImage:
        """Applies manual rotation to sheet page."""
        processed.manual_rotation_deg = manual_rotation_deg % 360
        effective_rot = processed.total_rotation_deg
        oriented = rotate_image(processed.warped_image, effective_rot) if effective_rot != 0 else processed.warped_image.copy()
        normalized = ImageNormalizer.normalize_sheet(oriented)
        enhanced = ImageEnhancer.apply(normalized, processed.enhancement_mode)

        quality = self.quality_engine.evaluate(
            normalized,
            corners=processed.current_corners,
            detection_confidence=1.0 if processed.is_manually_edited else (processed.quality_report.detection_confidence if processed.quality_report else 1.0),
            orientation_confidence=1.0,
            is_card=False,
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
        """Re-computes sheet page after manual corner adjustment."""
        ordered = order_corners(new_corners.to_numpy())
        nat_w, nat_h = calculate_target_dimensions(ordered)
        warped = warp_perspective(processed.original_image, ordered, nat_w, nat_h)

        orient_res = self.orientation_detector.detect_orientation(warped)
        processed.auto_rotation_deg = orient_res.best_angle
        processed.orientation_result = orient_res

        effective_rot = processed.total_rotation_deg
        oriented = rotate_image(warped, effective_rot) if effective_rot != 0 else warped.copy()
        normalized = ImageNormalizer.normalize_sheet(oriented)
        enhanced = ImageEnhancer.apply(normalized, processed.enhancement_mode)

        quality = self.quality_engine.evaluate(
            normalized,
            corners=ordered,
            detection_confidence=1.0,
            orientation_confidence=orient_res.confidence,
            is_card=False,
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
