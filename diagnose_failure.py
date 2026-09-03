"""
Diagnostic script to investigate OpenCV detector behavior on the user's real-world photograph.
"""
from pathlib import Path
import cv2
import numpy as np

from app.utils.image_io import load_image_safe, save_image_safe
from app.processing.preprocessor import ImagePreprocessor
from app.processing.perspective import order_corners, warp_perspective, calculate_target_dimensions
from app.processing.opencv_detector import OpenCVDetector


def run_diagnosis():
    img_path = Path("test_images/real_samples/WhatsApp Image 2026-09-01 at 9.36.55 PM (2).jpeg")
    if not img_path.exists():
        # Fallback to any jpeg in real_samples
        files = list(Path("test_images/real_samples").glob("*.jpeg"))
        if not files:
            print("No real sample found!")
            return
        img_path = files[0]

    print(f"Diagnosing: {img_path}")
    image = load_image_safe(img_path)
    if image is None:
        print("Failed to load image!")
        return

    out_dir = Path("benchmark_output/diagnosis")
    out_dir.mkdir(parents=True, exist_ok=True)

    h_orig, w_orig = image.shape[:2]
    print(f"Original image size: {w_orig} x {h_orig}")

    # 1. Scaled version
    scaled, inv_scale = ImagePreprocessor.scale_for_processing(image, max_dimension=1200)
    h_scaled, w_scaled = scaled.shape[:2]
    print(f"Scaled size: {w_scaled} x {h_scaled}, inv_scale: {inv_scale}")

    # Save original
    save_image_safe(image, out_dir / "01_original.jpg")

    # 2. Grayscale & CLAHE
    gray = cv2.cvtColor(scaled, cv2.COLOR_BGR2GRAY)
    save_image_safe(gray, out_dir / "02_grayscale.jpg")

    # 3. Edge map from preprocessor
    edges = ImagePreprocessor.prepare_edge_maps(scaled)
    save_image_safe(edges, out_dir / "03_edges.jpg")

    # 4. Find all contours
    contours, hierarchy = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    print(f"Found {len(contours)} contours")

    # Visualize all contours
    contour_vis = scaled.copy()
    cv2.drawContours(contour_vis, contours, -1, (0, 0, 255), 1)
    save_image_safe(contour_vis, out_dir / "04_contours.jpg")

    # 5. Candidate quadrilaterals
    total_area = float(h_scaled * w_scaled)
    candidate_vis = scaled.copy()
    detector = OpenCVDetector()
    candidates = []

    for idx, cnt in enumerate(sorted(contours, key=cv2.contourArea, reverse=True)[:20]):
        area = cv2.contourArea(cnt)
        area_ratio = area / total_area
        peri = cv2.arcLength(cnt, True)
        if peri <= 0:
            continue

        print(f"Contour #{idx}: area={area:.0f} (ratio={area_ratio:.3f}), peri={peri:.1f}")

        for eps_factor in [0.035, 0.025, 0.045, 0.018, 0.05, 0.01]:
            approx = cv2.approxPolyDP(cnt, eps_factor * peri, True)
            if len(approx) == 4:
                is_convex = cv2.isContourConvex(approx)
                pts = approx.reshape(4, 2)
                geom_valid = detector._validate_quad_geometry(pts)
                print(f"   eps={eps_factor}: 4-pts found! convex={is_convex}, geom_valid={geom_valid}")
                if is_convex and geom_valid:
                    candidates.append((cnt, approx, area_ratio, f"contour_eps_{eps_factor}"))
                    cv2.polylines(candidate_vis, [approx], True, (0, 255, 255), 2)
                break

        # Also try hull
        hull = cv2.convexHull(cnt)
        hull_peri = cv2.arcLength(hull, True)
        if hull_peri > 0:
            for eps_factor in [0.035, 0.025, 0.045, 0.018]:
                approx_hull = cv2.approxPolyDP(hull, eps_factor * hull_peri, True)
                if len(approx_hull) == 4 and cv2.isContourConvex(approx_hull):
                    pts = approx_hull.reshape(4, 2)
                    if detector._validate_quad_geometry(pts):
                        candidates.append((cnt, approx_hull, area_ratio, f"hull_eps_{eps_factor}"))
                        cv2.polylines(candidate_vis, [approx_hull], True, (255, 0, 255), 2)
                        break

    save_image_safe(candidate_vis, out_dir / "05_candidate_quadrilaterals.jpg")

    # Run actual detector
    res = detector.detect_card(image)
    print(f"\nDetector result: method={res.method}, confidence={res.confidence}, is_fallback={res.is_fallback}")
    if res.corners:
        print(f"Corners: TL={res.corners.top_left}, TR={res.corners.top_right}, BR={res.corners.bottom_right}, BL={res.corners.bottom_left}")

    # Draw selected quadrilateral on original image
    selected_vis = image.copy()
    if res.corners:
        pts = res.corners.to_numpy().astype(np.int32)
        cv2.polylines(selected_vis, [pts], True, (0, 255, 0), 4)
        for pt, label in zip(pts, ["TL", "TR", "BR", "BL"]):
            cv2.circle(selected_vis, tuple(pt), 10, (0, 0, 255), -1)
            cv2.putText(selected_vis, label, (pt[0] + 15, pt[1] + 10), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 255, 255), 3)
            cv2.putText(selected_vis, label, (pt[0] + 15, pt[1] + 10), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 255), 2)

    save_image_safe(selected_vis, out_dir / "06_selected_quadrilateral.jpg")

    # Warped
    if res.corners:
        w, h = calculate_target_dimensions(res.corners)
        warped = warp_perspective(image, res.corners, w, h)
        save_image_safe(warped, out_dir / "08_perspective_warped.jpg")


if __name__ == "__main__":
    run_diagnosis()
