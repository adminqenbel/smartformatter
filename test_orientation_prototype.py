"""
Prototype and verification for the multi-signal orientation detector.
"""
from pathlib import Path
import cv2
import numpy as np

from app.utils.image_io import load_image_safe, save_image_safe
from app.processing.perspective import order_corners, warp_perspective, calculate_target_dimensions
from app.processing.orientation import rotate_image
from app.processing.opencv_detector import OpenCVDetector


def detect_document_orientation(image: np.ndarray) -> dict:
    """
    Evaluates 0°, 90°, 180°, 270° rotations of the perspective-warped card/document.
    Returns:
      {
        'best_angle': int,
        'confidence': float,
        'scores': {0: float, 90: float, 180: float, 270: float},
        'details': {0: dict, 90: dict, 180: dict, 270: dict},
        'candidates': {0: np.ndarray, 90: np.ndarray, 180: np.ndarray, 270: np.ndarray}
      }
    """
    face_cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
    face_cascade = cv2.CascadeClassifier(face_cascade_path)

    rotations = [0, 90, 180, 270]
    candidates = {}
    scores = {}
    details = {}

    for deg in rotations:
        cand_img = rotate_image(image, deg)
        candidates[deg] = cand_img
        score, det = _evaluate_single_candidate(cand_img, face_cascade)
        scores[deg] = score
        details[deg] = det

    # Sort rotations by score descending
    sorted_rots = sorted(rotations, key=lambda r: scores[r], reverse=True)
    best_deg = sorted_rots[0]
    second_deg = sorted_rots[1]

    best_score = scores[best_deg]
    second_score = scores[second_deg]

    # Calculate confidence based on margin
    score_diff = best_score - second_score
    if details[best_deg].get("face_detected", False):
        confidence = 0.98
    elif score_diff > 40.0:
        confidence = 0.95
    elif score_diff > 20.0:
        confidence = 0.85
    elif score_diff > 10.0:
        confidence = 0.70
    else:
        confidence = 0.40 # Ambiguous orientation

    return {
        "best_angle": best_deg,
        "confidence": confidence,
        "scores": scores,
        "details": details,
        "candidates": candidates
    }


def _evaluate_single_candidate(img: np.ndarray, face_cascade: cv2.CascadeClassifier) -> tuple:
    h, w = img.shape[:2]
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if len(img.shape) == 3 else img.copy()

    # 1. Face detection
    min_face = int(min(h, w) * 0.12)
    max_face = int(min(h, w) * 0.85)
    faces = face_cascade.detectMultiScale(
        gray,
        scaleFactor=1.1,
        minNeighbors=3,
        minSize=(min_face, min_face),
        maxSize=(max_face, max_face)
    )

    face_detected = len(faces) > 0
    face_score = 100.0 if face_detected else 0.0

    # 2. Text Line Directionality (Horizontal vs Vertical text lines)
    sy = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
    sx = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)

    row_energy = np.mean(np.abs(sy), axis=1)
    col_energy = np.mean(np.abs(sx), axis=0)

    row_var = float(np.var(row_energy))
    col_var = float(np.var(col_energy))

    text_line_ratio = row_var / (col_var + 1e-5)

    # Score horizontal text alignment
    if text_line_ratio > 2.0:
        text_score = 45.0
    elif text_line_ratio > 1.2:
        text_score = 25.0
    elif text_line_ratio < 0.5:
        text_score = -30.0
    else:
        text_score = 0.0

    # 3. Header / Top Density (Header banner / logo in upper 35%)
    top_30_h = max(1, int(0.35 * h))
    bot_30_h = max(1, int(0.35 * h))
    top_energy = float(np.sum(np.abs(sy[:top_30_h, :])))
    bot_energy = float(np.sum(np.abs(sy[-bot_30_h:, :])))

    header_ratio = (top_energy + 1e-5) / (bot_energy + 1e-5)
    if header_ratio > 1.4:
        header_score = 25.0
    elif header_ratio < 0.7:
        header_score = -15.0
    else:
        header_score = 5.0

    total_score = face_score + text_score + header_score
    det = {
        "face_detected": face_detected,
        "text_line_ratio": text_line_ratio,
        "header_ratio": header_ratio,
        "face_score": face_score,
        "text_score": text_score,
        "header_score": header_score
    }
    return total_score, det


if __name__ == "__main__":
    detector = OpenCVDetector()
    real_files = list(Path("test_images/real_samples").glob("*.jpeg"))

    for f in real_files:
        print(f"\n==================================================")
        print(f"File: {f.name}")
        img = load_image_safe(f)
        res = detector.detect_card(img)
        w_nat, h_nat = calculate_target_dimensions(res.corners)
        warped = warp_perspective(img, res.corners, w_nat, h_nat)

        res_orient = detect_document_orientation(warped)
        print(f"Orientation Scores:")
        for deg in [0, 90, 180, 270]:
            sc = res_orient['scores'][deg]
            det = res_orient['details'][deg]
            print(f"  {deg:3d}° : Score = {sc:5.1f} | TextRatio = {det['text_line_ratio']:5.2f} | HeaderRatio = {det['header_ratio']:5.2f} | Face = {det['face_detected']}")

        print(f"---> Best Rotation: {res_orient['best_angle']}° (Confidence: {res_orient['confidence']:.2f})")
