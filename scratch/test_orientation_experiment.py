"""
Experimental test script comparing DocOrient and PaddleOCR on raw perspective-corrected real cards.
"""
from pathlib import Path
import cv2
import numpy as np
from PIL import Image

from app.processing.opencv_detector import OpenCVDetector
from app.processing.perspective import warp_perspective, calculate_target_dimensions
from app.processing.orientation import rotate_image
import docorient

def run_experiment():
    detector = OpenCVDetector()
    samples = [
        ("Front", Path("test_images/real_samples/WhatsApp Image 2026-09-01 at 9.36.55 PM (2).jpeg")),
        ("Back", Path("test_images/real_samples/WhatsApp Image 2026-09-01 at 9.36.35 PM.jpeg"))
    ]

    out_dir = Path("benchmark_output/orientation_experiment")
    out_dir.mkdir(parents=True, exist_ok=True)

    print("================================================================")
    print("        ORIENTATION EXPERIMENT: DocOrient & Geometry            ")
    print("================================================================")

    for side, path in samples:
        print(f"\n--- Processing {side}: {path.name} ---")
        img = cv2.imread(str(path))
        det = detector.detect_card(img)
        corners = det.corners
        if corners is None:
            print("Failed to detect corners")
            continue

        # 1. Perspective Warp
        nat_w, nat_h = calculate_target_dimensions(corners)
        warped = warp_perspective(img, corners, nat_w, nat_h)
        h, w = warped.shape[:2]
        print(f"  Raw warped dimensions: {w}x{h} (Aspect ratio: {w/h:.3f})")

        # Save raw_card.png / 01_raw_perspective.png
        cv2.imwrite(str(out_dir / f"{side.lower()}_01_raw_perspective.png"), warped)
        cv2.imwrite(str(out_dir / f"{side.lower()}_raw_card.png"), warped)

        # 2. Geometry: Ensure Landscape (Physical ID-1 aspect ratio is ~1.586 landscape)
        if h > w:
            landscape = rotate_image(warped, 90)
            initial_rot = 90
        else:
            landscape = warped.copy()
            initial_rot = 0

        h_l, w_l = landscape.shape[:2]
        print(f"  Landscape dimensions: {w_l}x{h_l} (Initial geometry rotation: {initial_rot}°)")
        cv2.imwrite(str(out_dir / f"{side.lower()}_02_landscape.png"), landscape)

        # 3. Two Candidates: candidate_A (0°) and candidate_B (180°)
        cand_0 = landscape.copy()
        cand_180 = rotate_image(landscape, 180)

        cv2.imwrite(str(out_dir / f"{side.lower()}_03_orientation_0.png"), cand_0)
        cv2.imwrite(str(out_dir / f"{side.lower()}_04_orientation_180.png"), cand_180)

        # 4. Test DocOrient on raw warped image and candidates
        pil_raw = Image.fromarray(cv2.cvtColor(warped, cv2.COLOR_BGR2RGB))
        pil_0 = Image.fromarray(cv2.cvtColor(cand_0, cv2.COLOR_BGR2RGB))
        pil_180 = Image.fromarray(cv2.cvtColor(cand_180, cv2.COLOR_BGR2RGB))

        res_raw = docorient.detect_orientation(pil_raw)
        res_0 = docorient.detect_orientation(pil_0)
        res_180 = docorient.detect_orientation(pil_180)

        print(f"  DocOrient on raw warped: angle={res_raw.angle}, confidence={res_raw.confidence:.3f}")
        print(f"  DocOrient on Cand 0°:   angle={res_0.angle}, confidence={res_0.confidence:.3f}")
        print(f"  DocOrient on Cand 180°: angle={res_180.angle}, confidence={res_180.confidence:.3f}")

        # Correct with DocOrient
        corrected_pil = docorient.correct_image(pil_raw)
        corrected_bgr = cv2.cvtColor(np.array(corrected_pil), cv2.COLOR_RGB2BGR)
        cv2.imwrite(str(out_dir / f"{side.lower()}_docorient_orientation.png"), corrected_bgr)

if __name__ == "__main__":
    run_experiment()
