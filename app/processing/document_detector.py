"""
Abstract Document Detector Interface.
Enables pluggable detection strategies without coupling to specific implementations.
"""
from abc import ABC, abstractmethod
import numpy as np

from app.core.models import DetectionResult


class DocumentDetector(ABC):
    """Abstract base class for all card and sheet document detectors."""

    @abstractmethod
    def detect_card(self, image: np.ndarray) -> DetectionResult:
        """
        Detects 4 corners of a physical card in the image.
        Returns DetectionResult with CornerPoints and confidence.
        """
        pass

    @abstractmethod
    def detect_sheet(self, image: np.ndarray) -> DetectionResult:
        """
        Detects 4 corners of a document sheet/page in the image.
        Returns DetectionResult with CornerPoints and confidence.
        """
        pass
