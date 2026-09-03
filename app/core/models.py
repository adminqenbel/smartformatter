"""
Core Data Models for QenBel Smart Formatter.
"""
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import List, Optional, Tuple, Dict, Any
import numpy as np
import uuid


class ProcessingMode(str, Enum):
    CARD = "CARD"
    SHEET = "SHEET"


class ConfidenceLevel(str, Enum):
    HIGH_CONFIDENCE = "HIGH CONFIDENCE"
    REVIEW_RECOMMENDED = "REVIEW RECOMMENDED"
    MANUAL_CORRECTION_REQUIRED = "MANUAL CORRECTION REQUIRED"


class EnhancementMode(str, Enum):
    ORIGINAL = "ORIGINAL"
    DOCUMENT_CRISP = "DOCUMENT_CRISP"
    AUTO_LEVELS = "AUTO_LEVELS"
    HIGH_CONTRAST_BW = "HIGH_CONTRAST_BW"


@dataclass
class CornerPoints:
    """
    Four corners in clockwise order: Top-Left, Top-Right, Bottom-Right, Bottom-Left.
    Coordinates are in (x, y) float format relative to original image coordinates.
    """
    top_left: Tuple[float, float]
    top_right: Tuple[float, float]
    bottom_right: Tuple[float, float]
    bottom_left: Tuple[float, float]

    def to_numpy(self, dtype=np.float32) -> np.ndarray:
        """Returns 4x2 numpy array [[tl_x, tl_y], [tr_x, tr_y], [br_x, br_y], [bl_x, bl_y]]."""
        return np.array([
            self.top_left,
            self.top_right,
            self.bottom_right,
            self.bottom_left
        ], dtype=dtype)

    @classmethod
    def from_numpy(cls, pts: np.ndarray) -> "CornerPoints":
        """Construct from 4x2 or 4x1x2 numpy array."""
        pts_reshaped = pts.reshape(4, 2)
        return cls(
            top_left=(float(pts_reshaped[0][0]), float(pts_reshaped[0][1])),
            top_right=(float(pts_reshaped[1][0]), float(pts_reshaped[1][1])),
            bottom_right=(float(pts_reshaped[2][0]), float(pts_reshaped[2][1])),
            bottom_left=(float(pts_reshaped[3][0]), float(pts_reshaped[3][1]))
        )

    def to_list(self) -> List[Tuple[float, float]]:
        return [self.top_left, self.top_right, self.bottom_right, self.bottom_left]

    def scale(self, scale_factor: float) -> "CornerPoints":
        """Returns scaled corner points."""
        return CornerPoints(
            top_left=(self.top_left[0] * scale_factor, self.top_left[1] * scale_factor),
            top_right=(self.top_right[0] * scale_factor, self.top_right[1] * scale_factor),
            bottom_right=(self.bottom_right[0] * scale_factor, self.bottom_right[1] * scale_factor),
            bottom_left=(self.bottom_left[0] * scale_factor, self.bottom_left[1] * scale_factor),
        )

    def compute_polygon_area(self) -> float:
        """Shoelace formula for quadrilateral area."""
        x = [self.top_left[0], self.top_right[0], self.bottom_right[0], self.bottom_left[0]]
        y = [self.top_left[1], self.top_right[1], self.bottom_right[1], self.bottom_left[1]]
        return 0.5 * abs(sum(x[i] * y[i - 3] - x[i - 3] * y[i] for i in range(4)))


@dataclass
class DetectionResult:
    """Result of document boundary detection."""
    corners: Optional[CornerPoints]
    confidence: float  # 0.0 to 1.0
    method: str        # e.g., "canny_edges_approx_eps_0.015", "manual"
    is_fallback: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class OrientationResult:
    """Result of document orientation evaluation (0, 90, 180, 270 deg)."""
    best_angle: int  # 0, 90, 180, 270
    confidence: float  # 0.0 to 1.0
    scores: Dict[int, float] = field(default_factory=dict)
    details: Dict[int, Dict[str, Any]] = field(default_factory=dict)
    diagnostic_candidates: Dict[int, np.ndarray] = field(default_factory=dict)


from app.core.profiles import (
    FormatProfile,
    CARD_PROFILE,
    LONG_FORM_PROFILE,
    A4_PROFILE,
    ProfileRegistry,
)


@dataclass
class QualityReport:
    """Comprehensive multi-factor diagnostic quality evaluation with granular confidence scoring."""
    blur_score: float
    is_blurry: bool
    brightness_mean: float
    contrast_std: float
    glare_ratio: float
    geometry_score: float
    detection_confidence: float = 1.0
    orientation_confidence: float = 1.0
    boundary_confidence: float = 1.0
    corner_confidence: float = 1.0
    perspective_confidence: float = 1.0
    format_confidence: float = 1.0
    quality_confidence: float = 1.0
    overall_confidence: float = 1.0
    status_level: ConfidenceLevel = ConfidenceLevel.HIGH_CONFIDENCE
    format_mismatch: bool = False
    suggested_profile: Optional[str] = None
    detected_aspect_ratio: float = 1.0
    expected_aspect_ratio: float = 1.0
    issues: List[str] = field(default_factory=list)


@dataclass
class ProcessedImage:
    """Data representation of a single processed document or card."""
    source_path: str
    original_image: np.ndarray  # BGR
    detected_corners: Optional[CornerPoints] = None
    current_corners: Optional[CornerPoints] = None
    warped_image: Optional[np.ndarray] = None
    oriented_image: Optional[np.ndarray] = None
    normalized_image: Optional[np.ndarray] = None
    enhanced_image: Optional[np.ndarray] = None
    auto_rotation_deg: int = 0      # Automatically determined rotation (0, 90, 180, 270)
    manual_rotation_deg: int = 0    # Operator manual rotation adjustment (0, 90, 180, 270)
    orientation_result: Optional[OrientationResult] = None
    enhancement_mode: EnhancementMode = EnhancementMode.ORIGINAL
    format_profile: FormatProfile = field(default_factory=lambda: CARD_PROFILE)
    quality_report: Optional[QualityReport] = None
    is_manually_edited: bool = False
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])

    @property
    def total_rotation_deg(self) -> int:
        """Total effective rotation in degrees (auto + manual) % 360."""
        return (self.auto_rotation_deg + self.manual_rotation_deg) % 360

    @property
    def rotation_deg(self) -> int:
        """Backward-compatible alias for total_rotation_deg."""
        return self.total_rotation_deg

    @property
    def final_image(self) -> Optional[np.ndarray]:
        """Returns the final active processed image for preview and export."""
        return self.enhanced_image if self.enhanced_image is not None else (
            self.normalized_image if self.normalized_image is not None else self.warped_image
        )


@dataclass
class CardPair:
    """Two-sided card container."""
    front: Optional[ProcessedImage] = None
    back: Optional[ProcessedImage] = None
    format_profile: FormatProfile = field(default_factory=lambda: CARD_PROFILE)
    synchronized_width: int = 0
    synchronized_height: int = 0

    def swap_sides(self):
        """Swaps front and back cards."""
        self.front, self.back = self.back, self.front

    def is_complete(self) -> bool:
        """Returns True if at least one card is loaded and processed."""
        return self.front is not None or self.back is not None


@dataclass
class CardEntry:
    """
    A single customer/card entry. Holds BOTH photographed sides (front/back)
    as ONE logical record. The two sides are always handled together.
    """
    front: Optional[ProcessedImage] = None
    back: Optional[ProcessedImage] = None
    format_profile: FormatProfile = field(default_factory=lambda: CARD_PROFILE)

    def is_single_sided(self) -> bool:
        """True if only one side is present."""
        return (self.front is not None) != (self.back is not None)

    def is_empty(self) -> bool:
        return self.front is None and self.back is None


@dataclass
class SheetQueue:
    """Multi-page document container."""
    pages: List[ProcessedImage] = field(default_factory=list)

    def add_page(self, page: ProcessedImage):
        self.pages.append(page)

    def remove_page(self, index: int):
        if 0 <= index < len(self.pages):
            self.pages.pop(index)

    def move_page_up(self, index: int):
        if index > 0:
            self.pages[index - 1], self.pages[index] = self.pages[index], self.pages[index - 1]

    def move_page_down(self, index: int):
        if index < len(self.pages) - 1:
            self.pages[index], self.pages[index + 1] = self.pages[index + 1], self.pages[index]

    def reorder(self, new_order: List[int]):
        """Reorder pages according to list of indices."""
        self.pages = [self.pages[i] for i in new_order if i < len(self.pages)]
