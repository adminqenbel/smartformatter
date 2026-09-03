"""
Safe Image I/O and Format Conversion Utilities.
Handles Unicode paths, EXIF rotation, and conversions between OpenCV, PIL, and Qt.
"""
from pathlib import Path
from typing import Optional, Union, Tuple
import cv2
import numpy as np
from PIL import Image, ImageOps

from app.utils.logger import get_logger

logger = get_logger("image_io")


def load_image_safe(file_path: Union[str, Path]) -> Optional[np.ndarray]:
    """
    Safely loads an image from disk, handling Unicode paths on Windows and EXIF orientation.
    Returns BGR numpy array or None on failure.
    """
    path = Path(file_path)
    if not path.exists():
        logger.error(f"Image file does not exist: {path}")
        return None

    try:
        # First use PIL to parse EXIF orientation accurately
        with Image.open(path) as pil_img:
            # Auto-rotate based on EXIF tag
            pil_img_transposed = ImageOps.exif_transpose(pil_img)
            # Ensure RGB format
            if pil_img_transposed.mode != "RGB":
                pil_img_transposed = pil_img_transposed.convert("RGB")
            
            # Convert RGB PIL to BGR OpenCV ndarray
            rgb_arr = np.array(pil_img_transposed)
            bgr_arr = cv2.cvtColor(rgb_arr, cv2.COLOR_RGB2BGR)
            return bgr_arr

    except Exception as e:
        logger.warning(f"PIL load failed for {path.name}: {e}. Trying raw OpenCV buffer...")
        try:
            # Fallback to direct numpy fromfile
            raw_data = np.fromfile(str(path), dtype=np.uint8)
            bgr_arr = cv2.imdecode(raw_data, cv2.IMREAD_COLOR)
            return bgr_arr
        except Exception as e2:
            logger.error(f"Failed to load image from {path}: {e2}")
            return None


def save_image_safe(image: np.ndarray, file_path: Union[str, Path], quality: int = 95) -> bool:
    """
    Safely saves an OpenCV BGR image to disk, handling Unicode paths.
    """
    path = Path(file_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    ext = path.suffix.lower()

    try:
        if ext in [".jpg", ".jpeg"]:
            params = [int(cv2.IMWRITE_JPEG_QUALITY), quality]
        elif ext == ".png":
            params = [int(cv2.IMWRITE_PNG_COMPRESSION), 4]
        elif ext == ".webp":
            params = [int(cv2.IMWRITE_WEBP_QUALITY), quality]
        else:
            params = []

        is_success, buffer = cv2.imencode(ext, image, params)
        if not is_success:
            logger.error(f"Failed to encode image to {ext}")
            return False

        with open(path, "wb") as f:
            f.write(buffer)

        return True
    except Exception as e:
        logger.error(f"Failed to save image to {path}: {e}")
        return False


def bgr_to_pil(bgr_image: np.ndarray) -> Image.Image:
    """Converts OpenCV BGR image to PIL RGB Image."""
    rgb_image = cv2.cvtColor(bgr_image, cv2.COLOR_BGR2RGB)
    return Image.fromarray(rgb_image)


def pil_to_bgr(pil_image: Image.Image) -> np.ndarray:
    """Converts PIL RGB Image to OpenCV BGR ndarray."""
    if pil_image.mode != "RGB":
        pil_image = pil_image.convert("RGB")
    rgb_arr = np.array(pil_image)
    return cv2.cvtColor(rgb_arr, cv2.COLOR_RGB2BGR)


def get_image_dimensions(image: np.ndarray) -> Tuple[int, int]:
    """Returns (height, width) of image."""
    return image.shape[0], image.shape[1]
