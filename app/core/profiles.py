"""
Physical Format Profiles for QenBel Smart Formatter.
Defines standard physical dimensions (mm), DPI, pixel conversions, and profile registry.
"""
from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass(frozen=True)
class FormatProfile:
    """
    Physical output format profile definition.
    Defines physical dimensions in millimeters, target DPI, and canonical orientation.
    Pixel dimensions are computed dynamically based on physical_mm / 25.4 * DPI.
    """
    id: str                         # e.g., "card", "long_form", "a4"
    name: str                       # e.g., "Card", "Long Form", "A4 Sheet"
    width_mm: float                 # Physical width in millimeters
    height_mm: float                # Physical height in millimeters
    canonical_orientation: str = "landscape"  # "landscape" or "portrait"
    dpi: int = 300
    description: str = ""

    @property
    def width_inch(self) -> float:
        """Physical width in inches."""
        return self.width_mm / 25.4

    @property
    def height_inch(self) -> float:
        """Physical height in inches."""
        return self.height_mm / 25.4

    @property
    def width_px(self) -> int:
        """Target pixel width at target DPI."""
        return int(round(self.width_inch * self.dpi))

    @property
    def height_px(self) -> int:
        """Target pixel height at target DPI."""
        return int(round(self.height_inch * self.dpi))

    @property
    def aspect_ratio(self) -> float:
        """Orientation-invariant aspect ratio (max dimension / min dimension)."""
        return max(self.width_mm, self.height_mm) / max(min(self.width_mm, self.height_mm), 1e-5)

    @property
    def target_aspect_ratio(self) -> float:
        """Directional aspect ratio (width / height)."""
        return self.width_mm / max(self.height_mm, 1e-5)

    @property
    def is_landscape(self) -> bool:
        """True if canonical orientation is landscape (width >= height)."""
        return self.canonical_orientation.lower() == "landscape" or self.width_mm >= self.height_mm

    @property
    def dimensions_mm_str(self) -> str:
        """Formatted physical dimensions string (e.g., '86 × 54 mm')."""
        w_str = f"{self.width_mm:.0f}" if self.width_mm.is_integer() else f"{self.width_mm:.1f}"
        h_str = f"{self.height_mm:.0f}" if self.height_mm.is_integer() else f"{self.height_mm:.1f}"
        return f"{w_str} × {h_str} mm"

    @property
    def dimensions_px_str(self) -> str:
        """Formatted pixel dimensions string (e.g., '1016 × 638 px')."""
        return f"{self.width_px} × {self.height_px} px"

    @property
    def summary_label(self) -> str:
        """Comprehensive summary description for UI headers."""
        return f"{self.name} ({self.dimensions_mm_str} @ {self.dpi} DPI • {self.dimensions_px_str})"


# ================= BUILT-IN STANDARD PROFILES =================

# 1. Standard Card Profile (ISO/IEC 7810 ID-1: 86.0 x 54.0 mm, ~1.59:1 aspect ratio)
CARD_PROFILE = FormatProfile(
    id="card",
    name="Card",
    width_mm=86.0,
    height_mm=54.0,
    canonical_orientation="landscape",
    dpi=300,
    description="Standard ID-1 / PVC Card (PAN, Driving License, Voter ID, Aadhaar Card)"
)

# 2. Long Form Profile (Aadhaar Cut-Slip / Long Document: 210.0 x 85.0 mm, ~2.47:1 aspect ratio)
LONG_FORM_PROFILE = FormatProfile(
    id="long_form",
    name="Long Form",
    width_mm=210.0,
    height_mm=85.0,
    canonical_orientation="landscape",
    dpi=300,
    description="Long Form Document (Aadhaar Letter Bottom Cut-Slip)"
)

# 3. Standard A4 Document Profile (210.0 x 297.0 mm, ~1.41:1 aspect ratio)
A4_PROFILE = FormatProfile(
    id="a4",
    name="A4 Sheet",
    width_mm=210.0,
    height_mm=297.0,
    canonical_orientation="portrait",
    dpi=300,
    description="Standard A4 Document Sheet (Invoices, Letters, Certificates)"
)


class ProfileRegistry:
    """Registry managing available physical format profiles."""

    _PROFILES: Dict[str, FormatProfile] = {
        CARD_PROFILE.id: CARD_PROFILE,
        LONG_FORM_PROFILE.id: LONG_FORM_PROFILE,
        A4_PROFILE.id: A4_PROFILE,
    }

    @classmethod
    def get_profile(cls, profile_id: Optional[str]) -> FormatProfile:
        """Retrieves profile by ID, defaulting to CARD_PROFILE if not found."""
        if not profile_id:
            return CARD_PROFILE
        return cls._PROFILES.get(profile_id.lower(), CARD_PROFILE)

    @classmethod
    def get_card_mode_profiles(cls) -> List[FormatProfile]:
        """Returns physical profiles available for Card Mode (Card, Long Form)."""
        return [CARD_PROFILE, LONG_FORM_PROFILE]

    @classmethod
    def get_all_profiles(cls) -> List[FormatProfile]:
        """Returns all registered format profiles."""
        return list(cls._PROFILES.values())

    @classmethod
    def register_profile(cls, profile: FormatProfile):
        """Registers a custom format profile."""
        cls._PROFILES[profile.id.lower()] = profile

    @classmethod
    def detect_best_matching_profile(cls, aspect_ratio: float) -> FormatProfile:
        """
        Suggests the best profile based on detected aspect ratio.
        Card is ~1.59, Long Form is ~2.47. Threshold is around 2.0.
        """
        if aspect_ratio >= 2.0:
            return LONG_FORM_PROFILE
        else:
            return CARD_PROFILE
