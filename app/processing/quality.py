"""
Deterministic Image Quality and Granular Confidence Evaluation Engine.
Evaluates blur, contrast, brightness, glare, geometric consistency, format matching, and orientation reliability.
"""
from typing import List, Optional
import cv2
import numpy as np

from app.core.config import QualityThresholds
from app.core.profiles import FormatProfile, CARD_PROFILE, ProfileRegistry
from app.core.models import CornerPoints, QualityReport, ConfidenceLevel
from app.utils.logger import get_logger

logger = get_logger("quality")


class QualityEngine:
    """Evaluates multi-factor document quality and granular confidence deterministically."""

    def __init__(self):
        self.thresh = QualityThresholds()

    def evaluate(
        self,
        image: np.ndarray,
        corners: Optional[CornerPoints] = None,
        detection_confidence: float = 1.0,
        orientation_confidence: float = 1.0,
        profile: Optional[FormatProfile] = None,
        detected_aspect_ratio: Optional[float] = None,
        is_card: bool = True,
        is_fallback: bool = False
    ) -> QualityReport:
        """
        Runs full suite of deterministic quality checks across all pipeline stages:
        1. Boundary & Corner Quality
        2. Format Mismatch Validation (Detected vs Profile aspect ratio)
        3. Orientation Reliability
        4. Photometric Quality (Sharpness, Contrast, Lighting, Glare)
        """
        issues: List[str] = []
        active_profile = profile or CARD_PROFILE

        # 1. Boundary & Fallback Evaluation
        boundary_conf = float(np.clip(detection_confidence, 0.0, 1.0))
        if is_fallback or boundary_conf < 0.40:
            boundary_conf = 0.25
            issues.append("Automatic document boundary detection uncertain; manual 4-corner review required")

        # 2. Geometric Consistency & Corner Confidence
        geometry_score = 1.0
        if corners is not None and not is_fallback:
            geometry_score = self._compute_geometry_score(corners, is_card)
            if geometry_score < 0.65:
                issues.append("Document boundary angles appear skewed; please verify corners")
        elif is_fallback:
            geometry_score = 0.20

        corner_conf = float(np.clip(geometry_score, 0.0, 1.0))
        perspective_conf = float(np.clip(0.6 * boundary_conf + 0.4 * corner_conf, 0.0, 1.0))

        # 3. Format Mismatch Validation
        expected_ratio = active_profile.aspect_ratio  # e.g., ~1.59 for Card, ~2.47 for Long Form
        det_ratio = detected_aspect_ratio if detected_aspect_ratio is not None else expected_ratio
        format_mismatch = False
        suggested_profile_id: Optional[str] = None
        format_conf = 1.0

        if detected_aspect_ratio is not None:
            suggested = ProfileRegistry.detect_best_matching_profile(det_ratio)
            # Thresholds: Card ~1.59, Long Form ~2.47. Midpoint ~2.03.
            # Flag mismatch only when detected ratio is decisively closer to the other format.
            if active_profile.id == "card" and det_ratio >= 2.10:
                format_mismatch = True
                suggested_profile_id = suggested.id
                format_conf = 0.40
                issues.append(
                    f"Possible format mismatch: detected long-form document geometry ({det_ratio:.2f}:1) "
                    f"while Card profile ({expected_ratio:.2f}:1) is active"
                )
            elif active_profile.id == "long_form" and det_ratio <= 1.70:
                format_mismatch = True
                suggested_profile_id = suggested.id
                format_conf = 0.40
                issues.append(
                    f"Possible format mismatch: detected card-sized geometry ({det_ratio:.2f}:1) "
                    f"while Long Form profile ({expected_ratio:.2f}:1) is active"
                )

        # 4. Orientation Confidence Check
        orient_conf = float(np.clip(orientation_confidence, 0.0, 1.0))
        if orient_conf < 0.60 and not is_fallback:
            issues.append(f"Document orientation uncertain (confidence: {orient_conf:.2f}); please verify rotation")

        # 5. Photometric Quality (Sharpness, Contrast, Lighting, Glare)
        if len(image.shape) == 3:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        else:
            gray = image.copy()

        laplacian = cv2.Laplacian(gray, cv2.CV_64F)
        blur_score = float(laplacian.var())
        is_blurry = blur_score < self.thresh.BLUR_THRESHOLD

        if is_blurry:
            issues.append(f"Image appears blurry (sharpness score: {blur_score:.1f} < {self.thresh.BLUR_THRESHOLD:.0f})")
        elif blur_score < self.thresh.BLUR_WARNING_THRESHOLD:
            issues.append(f"Mild blur detected (sharpness score: {blur_score:.1f})")

        brightness_mean = float(np.mean(gray))
        contrast_std = float(np.std(gray))

        if brightness_mean < self.thresh.TOO_DARK_THRESHOLD:
            issues.append(f"Image is underexposed / very dark (avg brightness: {brightness_mean:.1f}/255)")
        elif brightness_mean > self.thresh.TOO_BRIGHT_THRESHOLD:
            issues.append(f"Image is overexposed / washed out (avg brightness: {brightness_mean:.1f}/255)")

        if contrast_std < self.thresh.MIN_CONTRAST_STD:
            issues.append(f"Low contrast between text and background (contrast: {contrast_std:.1f})")

        # Glare Detection
        if len(image.shape) == 3:
            hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
            v_chan = hsv[:, :, 2]
            s_chan = hsv[:, :, 1]
            glare_mask = (v_chan > 248) & (s_chan < 35)
            glare_ratio = float(np.count_nonzero(glare_mask)) / float(gray.size)
        else:
            glare_mask = gray > 250
            glare_ratio = float(np.count_nonzero(glare_mask)) / float(gray.size)

        if glare_ratio > self.thresh.MAX_GLARE_RATIO:
            issues.append(f"Possible glare/flash reflection detected ({glare_ratio * 100:.1f}% of image)")

        blur_factor = min(1.0, blur_score / 200.0)
        lighting_factor = 1.0 - (0.3 if brightness_mean < 40 or brightness_mean > 225 else 0.0) - (0.2 if contrast_std < 25 else 0.0) - (0.2 if glare_ratio > 0.06 else 0.0)
        lighting_factor = max(0.2, lighting_factor)
        quality_conf = float(np.clip(0.6 * blur_factor + 0.4 * lighting_factor, 0.0, 1.0))

        # 6. Overall Confidence Calculation
        if is_fallback:
            overall_conf = 0.25
        else:
            overall_conf = (
                0.25 * boundary_conf +
                0.20 * corner_conf +
                0.25 * orient_conf +
                0.15 * format_conf +
                0.15 * quality_conf
            )
            if format_mismatch:
                overall_conf = min(overall_conf, 0.55)
            if orient_conf < 0.60:
                overall_conf = min(overall_conf, 0.55)
            overall_conf = float(np.clip(overall_conf, 0.0, 0.98))

        # 7. Status Level Assignment
        if is_fallback or overall_conf < self.thresh.REVIEW_CONFIDENCE_MIN or orient_conf < 0.50:
            status = ConfidenceLevel.MANUAL_CORRECTION_REQUIRED
        elif format_mismatch or orient_conf < 0.70 or overall_conf < self.thresh.HIGH_CONFIDENCE_MIN:
            status = ConfidenceLevel.REVIEW_RECOMMENDED
        elif (
            overall_conf >= self.thresh.HIGH_CONFIDENCE_MIN
            and not is_blurry
            and corner_conf >= 0.75
            and orient_conf >= 0.75
            and format_conf >= 0.90
        ):
            status = ConfidenceLevel.HIGH_CONFIDENCE
        else:
            status = ConfidenceLevel.REVIEW_RECOMMENDED

        if not issues:
            issues.append(f"High-quality capture. Boundary, {active_profile.name} format, and orientation checks passed.")

        return QualityReport(
            blur_score=blur_score,
            is_blurry=is_blurry,
            brightness_mean=brightness_mean,
            contrast_std=contrast_std,
            glare_ratio=glare_ratio,
            geometry_score=geometry_score,
            detection_confidence=boundary_conf,
            orientation_confidence=orient_conf,
            boundary_confidence=boundary_conf,
            corner_confidence=corner_conf,
            perspective_confidence=perspective_conf,
            format_confidence=format_conf,
            quality_confidence=quality_conf,
            overall_confidence=overall_conf,
            status_level=status,
            format_mismatch=format_mismatch,
            suggested_profile=suggested_profile_id,
            detected_aspect_ratio=det_ratio,
            expected_aspect_ratio=expected_ratio,
            issues=issues
        )

    def _compute_geometry_score(self, corners: CornerPoints, is_card: bool) -> float:
        """Computes geometric plausibility of the quadrilateral."""
        tl = np.array(corners.top_left)
        tr = np.array(corners.top_right)
        br = np.array(corners.bottom_right)
        bl = np.array(corners.bottom_left)

        top_w = np.linalg.norm(tr - tl)
        bot_w = np.linalg.norm(br - bl)
        left_h = np.linalg.norm(bl - tl)
        right_h = np.linalg.norm(br - tr)

        if max(top_w, bot_w) == 0 or max(left_h, right_h) == 0:
            return 0.2

        w_ratio = min(top_w, bot_w) / max(top_w, bot_w)
        h_ratio = min(left_h, right_h) / max(left_h, right_h)
        parallelism = 0.5 * (w_ratio + h_ratio)

        angles_cos = []
        pts = [tl, tr, br, bl]
        for i in range(4):
            v1 = pts[i - 1] - pts[i]
            v2 = pts[(i + 1) % 4] - pts[i]
            n1 = np.linalg.norm(v1)
            n2 = np.linalg.norm(v2)
            if n1 > 0 and n2 > 0:
                cos = abs(np.dot(v1, v2) / (n1 * n2))
                angles_cos.append(cos)

        perpendicularity = 1.0 - (np.mean(angles_cos) if angles_cos else 0.5)
        score = 0.6 * parallelism + 0.4 * perpendicularity
        return float(np.clip(score, 0.0, 1.0))
