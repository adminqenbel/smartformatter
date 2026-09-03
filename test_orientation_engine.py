"""
Experimental script to develop and verify the 4-candidate orientation detection engine (0°, 90°, 180°, 270°).
"""
from pathlib import Path
import cv2
import numpy as np

from app.utils.image_io import load_image_safe, save_image_safe
from app.processing.perspective import order_corners, warp_perspective, calculate_target_dimensions
from app.processing.orientation import rotate_image


def test_orientation():
    real_files = list(Path("test_images/real_samples").glob("*.jpeg"))
    print(f"Testing orientation on {len(real_files)} real images")

    out_base = Path("benchmark_output/orientation_diagnostics")
    out_base.mkdir(parents=True, exist_ok=True)

    # Load OpenCV built-in face detector
    face_cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
    face_cascade = cv2.CascadeClassifier(face_cascade_path)
    print(f"Face cascade loaded: {not face_cascade.empty()}")

    for img_path in real_files:
        print(f"\n=======================================================")
        print(f"Image: {img_path.name}")
        image = load_image_safe(img_path)

        # 1. Warp perspective to isolate card
        from app.processing.opencv_detector import OpenCVDetector
        detector = OpenCVDetector()
        res = detector.detect_card(image)
        if res.corners is None:
            print("Detection failed!")
            continue

        w_nat, h_nat = calculate_target_dimensions(res.corners)
        warped = warp_perspective(image, res.corners, w_nat, h_nat)

        img_out_dir = out_base / img_path.stem
        img_out_dir.mkdir(parents=True, exist_ok=True)

        # 2. Generate and score all 4 candidate rotations
        rotations = [0, 90, 180, 270]
        candidate_scores = {}

        for deg in rotations:
            candidate_img = rotate_image(warped, deg)
            score, details = score_orientation_candidate(candidate_img, face_cascade)
            candidate_scores[deg] = (score, details, candidate_img)
            save_image_safe(candidate_img, img_out_dir / f"orientation_{deg}.png")
            print(f"  {deg:3d}° | Total Score: {score:5.1f} | Details: {details}")

        # Best rotation
        best_deg = max(candidate_scores.keys(), key=lambda d: candidate_scores[d][0])
        best_score, best_details, best_img = candidate_scores[best_deg]
        print(f"\n---> SELECTED ORIENTATION: {best_deg}° (Score: {best_score:.1f})")

        save_image_safe(best_img, img_out_dir / "canonical_oriented_card.png")


def score_orientation_candidate(img: np.ndarray, face_cascade: cv2.CascadeClassifier):
    """
    Evaluates orientation candidate image using:
    1. Face detection (OpenCV Haar Cascade) - strongest signal if ID photo is present
    2. Text line directionality (Horizontal vs Vertical text lines via anisotropic morphology)
    3. Aspect ratio alignment for standard ID-1 card (Landscape aspect ratio ~ 1.58)
    4. Top-heavy header / script baseline energy
    """
    h, w = img.shape[:2]
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    details = {}

    # 1. Face Detection Signal
    # Search for upright frontal face
    min_face_size = int(min(h, w) * 0.15)
    max_face_size = int(min(h, w) * 0.85)
    faces = face_cascade.detectMultiScale(
        gray,
        scaleFactor=1.1,
        minNeighbors=4,
        minSize=(min_face_size, min_face_size),
        maxSize=(max_face_size, max_face_size)
    )

    face_score = 0.0
    if len(faces) > 0:
        # Check if face is in plausible ID card position (usually left or right third)
        for (fx, fy, fw, fh) in faces:
            # Plausible face is well within card bounds
            face_score = max(face_score, 100.0)
            details["face_found"] = f"{fx},{fy},{fw}x{fh}"
    else:
        details["face_found"] = "none"

    # 2. Text Line Directionality (Horizontal vs Vertical)
    # Cards have horizontal text lines.
    # We apply horizontal structuring element (15, 1) vs vertical (1, 15) to Otsu binary
    _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

    # Horizontal dilation (fuses characters in a horizontal line)
    k_h = cv2.getStructuringElement(cv2.MORPH_RECT, (15, 1))
    dilated_h = cv2.dilate(thresh, k_h, iterations=1)
    cnts_h, _ = cv2.findContours(dilated_h, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    # Count wide text blobs (width > 2 * height)
    h_text_blobs = 0
    for c in cnts_h:
        bx, by, bw, bh = cv2.boundingRect(c)
        if bw > 2.0 * bh and bw > 30:
            h_text_blobs += 1

    # Vertical dilation (fuses characters in a vertical line)
    k_v = cv2.getStructuringElement(cv2.MORPH_RECT, (1, 15))
    dilated_v = cv2.dilate(thresh, k_v, iterations=1)
    cnts_v, _ = cv2.findContours(dilated_v, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    v_text_blobs = 0
    for c in cnts_v:
        bx, by, bw, bh = cv2.boundingRect(c)
        if bh > 2.0 * bw and bh > 30:
            v_text_blobs += 1

    text_dir_ratio = (h_text_blobs + 1.0) / (v_text_blobs + 1.0)
    details["h_blobs"] = h_text_blobs
    details["v_blobs"] = v_text_blobs
    details["text_ratio"] = f"{text_dir_ratio:.2f}"

    # Text direction score: 0 to 40
    if text_dir_ratio > 1.5:
        text_score = min(40.0, 20.0 * text_dir_ratio)
    elif text_dir_ratio < 0.67:
        text_score = -20.0
    else:
        text_score = 0.0

    # 3. Aspect Ratio Score (Landscape vs Portrait)
    # Standard ID-1 cards are landscape (w > h)
    aspect = float(w) / float(h)
    details["aspect"] = f"{aspect:.2f}"
    if 1.25 <= aspect <= 2.2:
        aspect_score = 25.0
    elif aspect > 1.0:
        aspect_score = 10.0
    else:
        # Portrait orientation
        aspect_score = -15.0

    # 4. Top Header Structure (Header text / logo is in upper 40% of card)
    top_half = gray[:h // 2, :]
    bot_half = gray[h // 2:, :]
    # Edge density difference
    edges_top = cv2.Canny(top_half, 50, 150)
    edges_bot = cv2.Canny(bot_half, 50, 150)
    top_edge_density = float(np.count_nonzero(edges_top)) / float(top_half.size)
    bot_edge_density = float(np.count_nonzero(edges_bot)) / float(bot_half.size)
    header_score = (top_edge_density - bot_edge_density) * 100.0
    details["top_density"] = f"{top_edge_density:.3f}"

    # Total Score Calculation
    total_score = face_score + text_score + aspect_score + header_score
    return total_score, details


if __name__ == "__main__":
    test_orientation()
