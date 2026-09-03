"""
Experimentation script to find the optimal, robust card detection pipeline for real-world photos.
"""
from pathlib import Path
import cv2
import numpy as np

from app.utils.image_io import load_image_safe, save_image_safe
from app.processing.perspective import order_corners, warp_perspective, calculate_target_dimensions


def analyze_image(img_path: Path):
    image = load_image_safe(img_path)
    h_orig, w_orig = image.shape[:2]
    print(f"\n=======================================================")
    print(f"Analyzing {img_path.name} ({w_orig}x{h_orig})")

    out_dir = Path("benchmark_output/experiments") / img_path.stem
    out_dir.mkdir(parents=True, exist_ok=True)

    # 1. Scaled down
    max_dim = 1200
    scale = max_dim / max(h_orig, w_orig)
    w_sc = int(round(w_orig * scale))
    h_sc = int(round(h_orig * scale))
    scaled = cv2.resize(image, (w_sc, h_sc), interpolation=cv2.INTER_AREA)
    inv_scale = 1.0 / scale
    total_area = float(w_sc * h_sc)

    # 2. Strategy A: Multi-channel analysis
    # Lab: L channel (lightness), a/b channels (color)
    lab = cv2.cvtColor(scaled, cv2.COLOR_BGR2LAB)
    l_chan, a_chan, b_chan = cv2.split(lab)

    # HSV: S channel (saturation) - cards are white/low-saturation, floor often has color tint
    hsv = cv2.cvtColor(scaled, cv2.COLOR_BGR2HSV)
    h_chan, s_chan, v_chan = cv2.split(hsv)

    # Grayscale
    gray = cv2.cvtColor(scaled, cv2.COLOR_BGR2GRAY)

    # 3. Suppress Image Outer Frame / Borders
    # The camera frame edges (within 1% of border) must NEVER be treated as the document boundary
    margin_px = 6
    border_mask = np.zeros((h_sc, w_sc), dtype=np.uint8)
    border_mask[margin_px:h_sc - margin_px, margin_px:w_sc - margin_px] = 255

    # 4. Filter with Bilateral filter to smooth floor texture while keeping card edge sharp
    bilateral = cv2.bilateralFilter(gray, 9, 75, 75)

    # 5. Contrast Thresholding (Otsu on Lightness and Grayscale)
    # The card is bright white on a darker floor
    _, otsu_thresh = cv2.threshold(bilateral, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    save_image_safe(otsu_thresh, out_dir / "otsu_thresh.jpg")

    # Adaptive threshold
    adapt_thresh = cv2.adaptiveThreshold(
        bilateral, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 25, -5
    )
    save_image_safe(adapt_thresh, out_dir / "adapt_thresh.jpg")

    # 6. Canny Edges
    # Use Otsu high threshold
    high_t, _ = cv2.threshold(bilateral, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    low_t = 0.4 * high_t
    canny = cv2.Canny(bilateral, low_t, high_t)
    # Mask out outer camera border
    canny = cv2.bitwise_and(canny, canny, mask=border_mask)
    save_image_safe(canny, out_dir / "canny.jpg")

    # Morphological Close
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
    canny_closed = cv2.morphologyEx(canny, cv2.MORPH_CLOSE, kernel, iterations=3)
    save_image_safe(canny_closed, out_dir / "canny_closed.jpg")

    # 7. Also test Color-based segmentation (White Card extraction in Lab/HSV)
    # In Lab: L > threshold and low color variance
    card_mask = cv2.inRange(lab, np.array([140, 0, 0]), np.array([255, 255, 255]))
    card_mask = cv2.bitwise_and(card_mask, card_mask, mask=border_mask)
    kernel_large = cv2.getStructuringElement(cv2.MORPH_RECT, (7, 7))
    card_mask_clean = cv2.morphologyEx(card_mask, cv2.MORPH_CLOSE, kernel_large, iterations=2)
    card_mask_clean = cv2.morphologyEx(card_mask_clean, cv2.MORPH_OPEN, kernel_large, iterations=1)
    save_image_safe(card_mask_clean, out_dir / "color_mask_clean.jpg")

    # Combine methods to test contour candidates
    candidate_quads = []

    for name, bmap in [
        ("canny_closed", canny_closed),
        ("otsu_thresh", otsu_thresh),
        ("color_mask", card_mask_clean),
    ]:
        contours, _ = cv2.findContours(bmap, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
        for cnt in sorted(contours, key=cv2.contourArea, reverse=True)[:15]:
            area = cv2.contourArea(cnt)
            area_ratio = area / total_area

            # Card must be between 5% and 88% of the image (cannot be the entire 95%+ camera frame)
            if not (0.05 <= area_ratio <= 0.88):
                continue

            # Also verify contour does not hug the image outer frame
            x, y, w, h = cv2.boundingRect(cnt)
            if x <= 2 and y <= 2 and (x + w >= w_sc - 3) and (y + h >= h_sc - 3):
                continue # Skip outer image frame

            hull = cv2.convexHull(cnt)
            hull_peri = cv2.arcLength(hull, True)
            if hull_peri <= 0:
                continue

            for eps in [0.02, 0.03, 0.04, 0.05, 0.015, 0.06]:
                approx = cv2.approxPolyDP(hull, eps * hull_peri, True)
                if len(approx) == 4 and cv2.isContourConvex(approx):
                    pts = approx.reshape(4, 2)
                    candidate_quads.append((pts, area_ratio, name, f"approx_eps_{eps}"))
                    break

            # Also test minAreaRect on hull
            rect = cv2.minAreaRect(hull)
            box = cv2.boxPoints(rect)
            box_area = cv2.contourArea(box.astype(np.int32))
            # If hull area fills most of minAreaRect (solidity > 0.80), this is a good candidate
            if area > 0 and (area / float(box_area + 1e-5)) > 0.78:
                candidate_quads.append((box, area_ratio, name, "min_area_rect_solid"))

    print(f"Total candidate quads found: {len(candidate_quads)}")

    # Score and rank candidates
    scored_candidates = []
    vis_all = scaled.copy()

    for idx, (pts, area_ratio, source_name, method) in enumerate(candidate_quads):
        ordered = order_corners(pts.astype(np.float32) * inv_scale)
        score = score_card_quad(ordered, image, area_ratio)
        scored_candidates.append((score, ordered, pts, area_ratio, source_name, method))
        cv2.polylines(vis_all, [pts.astype(np.int32)], True, (255, 255, 0), 2)
        print(f"Candidate #{idx}: score={score:.3f}, area={area_ratio:.3f}, src={source_name}, method={method}")

    save_image_safe(vis_all, out_dir / "all_candidates.jpg")

    if scored_candidates:
        scored_candidates.sort(key=lambda x: x[0], reverse=True)
        best_score, best_ordered, best_pts_sc, best_area, best_src, best_method = scored_candidates[0]
        print(f"\n---> BEST QUAD: score={best_score:.3f}, src={best_src}, method={best_method}")

        # Draw best quad on original
        vis_best = image.copy()
        pts_orig = best_ordered.to_numpy().astype(np.int32)
        cv2.polylines(vis_best, [pts_orig], True, (0, 255, 0), 4)
        for pt, lbl in zip(pts_orig, ["TL", "TR", "BR", "BL"]):
            cv2.circle(vis_best, tuple(pt), 10, (0, 0, 255), -1)
            cv2.putText(vis_best, lbl, (pt[0] + 12, pt[1] + 8), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 255, 255), 2)
        save_image_safe(vis_best, out_dir / "best_quad_selected.jpg")

        # Warp
        w_nat, h_nat = calculate_target_dimensions(best_ordered)
        warped = warp_perspective(image, best_ordered, w_nat, h_nat)
        save_image_safe(warped, out_dir / "warped_card.jpg")


def score_card_quad(corners, image: np.ndarray, area_ratio: float) -> float:
    """
    Scores a quadrilateral candidate based on:
    1. Parallelism of opposite sides
    2. Perpendicularity of adjacent sides (internal angles near 90°)
    3. Aspect ratio sanity (between 1.2 and 2.4 for cards, or reasonable document ratio)
    4. Contrast between interior of quad and exterior border (edge gradient strength)
    5. Area plausibility (10% to 75% of image)
    """
    tl = np.array(corners.top_left)
    tr = np.array(corners.top_right)
    br = np.array(corners.bottom_right)
    bl = np.array(corners.bottom_left)

    top_w = np.linalg.norm(tr - tl)
    bot_w = np.linalg.norm(br - bl)
    left_h = np.linalg.norm(bl - tl)
    right_h = np.linalg.norm(br - tr)

    if min(top_w, bot_w) == 0 or min(left_h, right_h) == 0:
        return 0.0

    # 1. Parallelism
    w_ratio = min(top_w, bot_w) / max(top_w, bot_w)
    h_ratio = min(left_h, right_h) / max(left_h, right_h)
    parallelism = 0.5 * (w_ratio + h_ratio)

    # 2. Angles perpendicularity
    angles = []
    pts = [tl, tr, br, bl]
    for i in range(4):
        v1 = pts[i - 1] - pts[i]
        v2 = pts[(i + 1) % 4] - pts[i]
        n1 = np.linalg.norm(v1)
        n2 = np.linalg.norm(v2)
        if n1 > 0 and n2 > 0:
            cos_a = abs(np.dot(v1, v2) / (n1 * n2))
            angles.append(cos_a)

    perpendicularity = 1.0 - (np.mean(angles) if angles else 1.0)

    # 3. Aspect ratio check
    w_dim = max(top_w, bot_w)
    h_dim = max(left_h, right_h)
    aspect = max(w_dim, h_dim) / min(w_dim, h_dim)

    # Standard card is ~1.586, document strip is ~1.4 to 2.2
    # Penalize extreme aspect ratios (> 3.5 or < 1.1)
    if aspect > 3.8 or aspect < 1.05:
        aspect_score = 0.1
    elif 1.3 <= aspect <= 2.2:
        aspect_score = 1.0
    else:
        aspect_score = 0.7

    # 4. Area score (prefers cards that take 12% to 65% of photo)
    if 0.12 <= area_ratio <= 0.65:
        area_score = 1.0
    elif 0.06 <= area_ratio <= 0.85:
        area_score = 0.75
    else:
        area_score = 0.2

    # Total score
    total_score = (
        0.35 * parallelism +
        0.30 * perpendicularity +
        0.20 * aspect_score +
        0.15 * area_score
    )
    return float(total_score)


if __name__ == "__main__":
    for f in Path("test_images/real_samples").glob("*.jpeg"):
        analyze_image(f)
