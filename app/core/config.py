"""
Application Configuration and Constants for QenBel Smart Formatter.
"""
from dataclasses import dataclass
from pathlib import Path
import os


@dataclass(frozen=True)
class PrintConfig:
    # Target Print DPI
    DEFAULT_DPI: int = 300

    # ISO/IEC 7810 ID-1 Standard Card Dimensions in Millimeters & Inches
    CARD_WIDTH_MM: float = 85.60
    CARD_HEIGHT_MM: float = 53.98
    CARD_WIDTH_INCH: float = 3.37008
    CARD_HEIGHT_INCH: float = 2.12520
    CARD_ASPECT_RATIO: float = 85.60 / 53.98  # ~1.58577

    # Target Card Pixel Dimensions at 300 DPI
    CARD_WIDTH_PX: int = int(round(CARD_WIDTH_INCH * DEFAULT_DPI))   # 1011 px
    CARD_HEIGHT_PX: int = int(round(CARD_HEIGHT_INCH * DEFAULT_DPI)) # 638 px

    # Standard Sheet Dimensions (A4) in Millimeters & Inches
    A4_WIDTH_MM: float = 210.0
    A4_HEIGHT_MM: float = 297.0
    A4_WIDTH_INCH: float = 8.26772
    A4_HEIGHT_INCH: float = 11.6929
    A4_ASPECT_RATIO: float = 297.0 / 210.0  # ~1.41428

    # A4 Pixel Dimensions at 300 DPI
    A4_WIDTH_PX: int = int(round(A4_WIDTH_INCH * DEFAULT_DPI))   # 2480 px
    A4_HEIGHT_PX: int = int(round(A4_HEIGHT_INCH * DEFAULT_DPI)) # 3508 px

    # Word (.docx) Export Margins in Inches
    DOCX_MARGIN_INCH: float = 0.5


@dataclass(frozen=True)
class QualityThresholds:
    # Laplacian blur variance threshold (below this is flagged as blurry)
    BLUR_THRESHOLD: float = 80.0
    BLUR_WARNING_THRESHOLD: float = 120.0

    # Brightness thresholds (0-255 grayscale scale)
    TOO_DARK_THRESHOLD: float = 40.0
    TOO_BRIGHT_THRESHOLD: float = 225.0

    # Contrast threshold (standard deviation of pixel intensities)
    MIN_CONTRAST_STD: float = 25.0

    # Glare threshold (percentage of near-saturated pixels)
    MAX_GLARE_RATIO: float = 0.06

    # Minimum corner angles for a valid quad (degrees)
    MIN_CORNER_ANGLE_DEG: float = 55.0
    MAX_CORNER_ANGLE_DEG: float = 125.0

    # Minimum document area relative to original image
    MIN_AREA_RATIO: float = 0.08

    # Overall Confidence Thresholds
    HIGH_CONFIDENCE_MIN: float = 0.75
    REVIEW_CONFIDENCE_MIN: float = 0.45


class AppPaths:
    """Standard application paths."""
    ROOT_DIR = Path(__file__).resolve().parent.parent.parent
    APP_DIR = ROOT_DIR / "app"
    LOGO_LIGHT = ROOT_DIR / "Logo" / "black_text_qenbel_logo_for_light_background.png"
    
    # User Application Data Directory
    USER_DATA_DIR = Path(os.environ.get("APPDATA", str(Path.home()))) / "QenBelSmartFormatter"
    LOGS_DIR = USER_DATA_DIR / "logs"
    TEMP_DIR = USER_DATA_DIR / "temp"

    @classmethod
    def ensure_directories(cls):
        """Ensure necessary runtime directories exist."""
        cls.USER_DATA_DIR.mkdir(parents=True, exist_ok=True)
        cls.LOGS_DIR.mkdir(parents=True, exist_ok=True)
        cls.TEMP_DIR.mkdir(parents=True, exist_ok=True)
