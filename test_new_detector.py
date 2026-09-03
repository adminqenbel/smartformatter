"""
Verification script for the new OpenCVDetector implementation on real-world and synthetic images.
"""
from pathlib import Path
import cv2
import numpy as np

from app.utils.image_io import load_image_safe, save_image_safe
from app.processing.perspective import order_corners, warp_perspective, calculate_target_dimensions


def test_real_images():
    real_files = list(Path("test_images/real_samples").glob("*.jpeg"))
    print(f"Found {len(real_files)} real sample images.")

    out_dir = Path("benchmark_output/new_detector_test")
    out_dir.mkdir(parents=True, exist_ok=True)

    for img_path in real_files:
        print(f"\n--- Testing: {img_path.name} ---")
        image = load_image_safe(img_path)
        h_orig, w_orig = image.shape[:2]

        # Multi-stage detection
        corners, confidence, method = detect_card_quadrilateral(image)

        print(f"Result: method={method}, confidence={confidence:.2f}")
        if corners is not None:
            print(f"Corners (original scale):")
            print(f"  TL: {corners.top_left}")
            print(f"  TR: {corners.top_right}")
            print(f"  BR: {corners.bottom_right}")
            print(f"  BL: {corners.bottom_left}")

            # Draw on original
            overlay = image.copy()
            pts = corners.to_numpy().astype(np.int32)
            cv2.polylines(overlay, [pts], True, (0, 255, 0), 4)
            for pt, lbl in zip(pts, ["TL", "TR", "BR", "BL"]):
                cv2.circle(overlay, tuple(pt), 10, (0, 0, 255), -1)
                cv2.putText(overlay, lbl, (pt[0] + 15, pt[1] + 10), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 255, 255), 2)
            save_image_safe(overlay, out_dir / f"{img_path.stem}_overlay.jpg")

            # Warp
            w_nat, h_nat = calculate_target_dimensions(corners)
            warped = warp_perspective(image, corners, w_nat, h_nat)
            save_image_safe(warped, out_dir / f"{img_path.stem}_warped.jpg")
            print(f"  Warped size: {w_nat} x {h_nat}")


def detect_card_quadrilateral(image: np.ndarray):
    """Refined multi-source quadrilateral detector."""
    h_orig, w_orig = image.shape[:2]
    max_dim = 1200
    scale = max_dim / float(max(h_orig, w_orig))
    w_sc = int(round(w_orig * scale))
    h_sc = int(round(h_orig * scale))
    scaled = cv2.resize(image, (w_sc, h_sc), interpolation=cv2.INTER_AREA)
    inv_scale = 1.0 / scale
    total_area = float(w_sc * h_sc)

    # Inset mask: Ignore 1.5% outer frame borders
    border_px = int(max(4, 0.015 * min(w_sc, h_sc)))
    border_mask = np.zeros((h_sc, w_sc), dtype=np.uint8)
    border_mask[border_px:h_sc - border_px, border_px:w_sc - border_px] = 255

    gray = cv2.cvtColor(scaled, cv2.COLOR_BGR2GRAY)
    lab = cv2.cvtColor(scaled, cv2.COLOR_BGR2LAB)
    l_chan = lab[:, :, 0]

    # Bilateral smoothing
    bilateral = cv2.bilateralFilter(gray, 9, 75, 75)

    # 1. Edge maps
    high_t, _ = cv2.threshold(bilateral, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    canny = cv2.Canny(bilateral, 0.4 * high_t, high_t)
    canny = cv2.bitwise_and(canny, canny, mask=border_mask)
    k_close = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
    canny_closed = cv2.morphologyEx(canny, cv2.MORPH_CLOSE, k_close, iterations=3)

    # 2. Lab L-channel Otsu threshold (bright card on darker table/floor)
    _, otsu_l = cv2.threshold(l_chan, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    otsu_l = cv2.bitwise_and(otsu_l, otsu_l, mask=border_mask)
    otsu_l_clean = cv2.morphologyEx(otsu_l, cv2.MORPH_CLOSE, k_close, iterations=2)

    # 3. Grayscale Otsu
    _, otsu_g = cv2.threshold(bilateral, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    otsu_g = cv2.bitwise_and(otsu_g, otsu_g, mask=border_mask)
    otsu_g_clean = cv2.morphologyEx(otsu_g, cv2.MORPH_CLOSE, k_close, iterations=2)

    # 4. Adaptive threshold
    adapt = cv2.adaptiveThreshold(bilateral, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, -5)
    adapt = cv2.bitwise_and(adapt, adapt, mask=border_mask)
    adapt_clean = cv2.morphologyEx(adapt, cv2.MORPH_CLOSE, k_close, iterations=2)

    sources = [
        ("canny_edges", canny_closed),
        ("lab_otsu", otsu_l_clean),
        ("gray_otsu", otsu_g_clean),
        ("adaptive_thresh", adapt_clean),
    ]

    candidate_quads = []

    for src_name, bmap in sources:
        contours, _ = cv2.findContours(bmap, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
        for cnt in contours:
            area = cv2.contourArea(cnt)
            area_ratio = area / total_area

            # Must be a plausible document area: 5% to 88% of image
            if not (0.05 <= area_ratio <= 0.88):
                continue

            # Skip contours that touch outer image boundaries
            x, y, w, h = cv2.boundingRect(cnt)
            if x <= 3 or y <= 3 or (x + w >= w_sc - 4) or (y + h >= h_sc - 4):
                continue

            hull = cv2.convexHull(cnt)
            hull_peri = cv2.arcLength(hull, True)
            if hull_peri <= 0:
                continue

            # Try approxPolyDP on hull with decaying epsilon
            found_quad = False
            for eps in [0.015, 0.02, 0.025, 0.03, 0.04, 0.05, 0.06]:
                approx = cv2.approxPolyDP(hull, eps * hull_peri, True)
                if len(approx) == 4 and cv2.isContourConvex(approx):
                    pts = approx.reshape(4, 2)
                    candidate_quads.append((pts, area_ratio, src_name, f"approx_eps_{eps}"))
                    found_quad = True
                    break

            # If approxPolyDP produced 4-8 vertices, check minAreaRect on hull
            if not found_quad:
                rect = cv2.minAreaRect(hull)
                box = cv2.boxPoints(rect)
                box_area = cv2.contourArea(box.astype(np.int32))
                if box_area > 0 and (area / float(box_area)) > 0.75:
                    candidate_quads.append((box, area_ratio, src_name, "min_area_rect_solid"))

    if not candidate_quads:
        # Fallback
        margin_x = 0.05 * w_orig
        margin_y = 0.05 * h_orig
        from app.core.models import CornerPoints
        fallback_pts = CornerPoints((margin_x, margin_y), (w_orig - margin_x, margin_y), (w_orig - margin_x, h_orig - margin_y), (margin_x, h_orig - margin_y))
        return fallback_pts, 0.25, "fallback_margin"

    # Score and rank candidates
    scored = []
    for pts, area_ratio, src_name, method in candidate_quads:
        ordered = order_corners(pts.astype(np.float32) * inv_scale)
        score = evaluate_candidate_geometry(ordered, area_ratio)
        scored.append((score, ordered, src_name, method))

    scored.sort(key=lambda x: x[0], reverse=True)
    best_score, best_corners, best_src, best_method = scored[0]

    return best_corners, float(best_score), f"{best_src}_{best_method}"


def evaluate_candidate_geometry(corners, area_ratio: float) -> float:
    tl = np.array(corners.top_left)
    tr = np.array(corners.top_right)
    br = np.array(corners.bottom_right)
    bl = np.array(corners.bottom_left)

    top_w = np.linalg.norm(tr - tl)
    bot_w = np.linalg.norm(br - bl)
    left_h = np.linalg.norm(bl - tl)
    right_h = np.linalg.norm(br - tr)

    if min(top_w, bot_w) == 0 or min(left_h, right_h) == 0:
        return 0.1

    # 1. Parallelism of opposite edges
    w_ratio = min(top_w, bot_w) / max(top_w, bot_w)
    h_ratio = min(left_h, right_h) / max(left_h, right_h)
    parallelism = 0.5 * (w_ratio + h_ratio)

    # 2. Perpendicularity of adjacent edges (cosine should be close to 0)
    cos_angles = []
    pts = [tl, tr, br, bl]
    for i in range(4):
        v1 = pts[i - 1] - pts[i]
        v2 = pts[(i + 1) % 4] - pts[i]
        n1 = np.linalg.norm(v1)
        n2 = np.linalg.norm(v2)
        if n1 > 0 and n2 > 0:
            cos = abs(np.dot(v1, v2) / (n1 * n2))
            cos_angles.append(cos)

    perpendicularity = 1.0 - (np.mean(cos_angles) if cos_angles else 0.5)

    # 3. Aspect ratio sanity
    w_dim = max(top_w, bot_w)
    h_dim = max(left_h, right_h)
    aspect = max(w_dim, h_dim) / min(w_dim, h_dim)

    # Plausible card / paper slip aspect ratios (1.2 to 2.8)
    if 1.25 <= aspect <= 2.6:
        aspect_score = 1.0
    elif 1.1 <= aspect <= 3.2:
        aspect_score = 0.8
    else:
        aspect_score = 0.3

    # 4. Area plausibility (10% to 65% of photo)
    if 0.10 <= area_ratio <= 0.65:
        area_score = 1.0
    elif 0.05 <= area_ratio <= 0.85:
        area_score = 0.8
    else:
        area_score = 0.2

    score = (
        0.35 * parallelism +
        0.30 * perpendicularity +
        0.20 * aspect_score +
        0.15 * area_score
    )
    return float(np.clip(score, 0.1, 0.98))


if __name__ == "__main__":
    test_real_images()
