"""
Multi-Stage OpenCV Document and Card Detector.

Generation of candidates from multiple independent strategies:
  1. Multi-channel contour approximation (internal boxes + clean outer contours).
  2. Foreground-region segmentation (robust outer-document footprint).
  3. Hough / convex-hull edge quad.

Candidates are ranked by an "outness-aware" score that measures how much of
the document's foreground content each quadrilateral encloses, so that an
internal printed box (which encloses only a fraction of the document) loses
to the true OUTER physical boundary (which encloses essentially all of it).

The format profile (when the caller provides one) is used only as a ranking
prior -- never as a substitute for detecting the real boundary.
"""
from typing import Optional, Tuple, List, Dict, Any
import cv2
import numpy as np

from app.core.config import QualityThresholds
from app.core.models import CornerPoints, DetectionResult
from app.processing.document_detector import DocumentDetector
from app.processing.preprocessor import ImagePreprocessor
from app.processing.perspective import order_corners
from app.utils.logger import get_logger

logger = get_logger("opencv_detector")

# Area ratio limits used when unifying the raw candidate quads.
_MIN_AREA_RATIO = 0.03
_MAX_AREA_RATIO = 0.92


class OpenCVDetector(DocumentDetector):
    """
    Robust OpenCV-based card and document boundary detector.
    """

    def __init__(self):
        self.thresholds = QualityThresholds()

    # ─────────────────────────────────────────────────────────────────────
    # Public API
    # ─────────────────────────────────────────────────────────────────────
    def detect_card(self, image: np.ndarray, debug_dir: Optional[str] = None,
                    profile: Optional[Any] = None) -> DetectionResult:
        return self._detect_document(image, is_card=True, debug_dir=debug_dir, profile=profile)

    def detect_sheet(self, image: np.ndarray, debug_dir: Optional[str] = None,
                     profile: Optional[Any] = None) -> DetectionResult:
        return self._detect_document(image, is_card=False, debug_dir=debug_dir, profile=profile)

    # ─────────────────────────────────────────────────────────────────────
    # Main detection pipeline
    # ─────────────────────────────────────────────────────────────────────
    def _detect_document(
        self,
        image: np.ndarray,
        is_card: bool = False,
        profile: Optional[Any] = None,
        debug_dir: Optional[str] = None,
    ) -> DetectionResult:
        h_orig, w_orig = image.shape[:2]

        # 1. Downscale for fast, robust processing
        scaled, inv_scale = ImagePreprocessor.scale_for_processing(image, max_dimension=1200)
        h_sc, w_sc = scaled.shape[:2]
        total_scaled_area = float(h_sc * w_sc)

        # 2. Build a foreground document mask (content vs. background).
        #    Background luminance estimated from image borders, so this works
        #    for both dark and light backgrounds.
        fg_mask = self._build_foreground_mask(scaled)
        # Remove tiny speckle components so that scattered far-from-document
        # noise does not inflate the enclosing shape.
        fg_mask = self._clean_foreground(fg_mask)
        total_fg = int(cv2.countNonZero(fg_mask))

        # Dilate foreground to fill blank-paper gaps between content lines
        # within the document. This makes the enclosure metric robust against
        # fragmented content (e.g., a Long Form with dark header bands).
        # Long Form cards (~2.47:1 aspect) need a wider dilation kernel to bridge
        # the larger blank-paper strips between the header band and the text body.
        is_long_form = (
            profile is not None
            and hasattr(profile, "aspect_ratio")
            and float(profile.aspect_ratio) >= 2.0
        )
        if is_long_form:
            # Use a much larger dilation to fuse the fragmented content bands.
            kernel_size = max(35, int(0.06 * min(h_sc, w_sc)))
        else:
            kernel_size = max(15, int(0.02 * min(h_sc, w_sc)))
        kernel_size = kernel_size | 1  # ensure odd
        fg_dil = cv2.dilate(fg_mask,
                            cv2.getStructuringElement(cv2.MORPH_RECT,
                                                      (kernel_size, kernel_size)),
                            iterations=2 if is_long_form else 1)
        total_fg_dil = int(cv2.countNonZero(fg_dil))

        # 3. Generate candidate quadrilaterals from multiple strategies.
        quads = self._generate_candidates(scaled, fg_mask, total_scaled_area, total_fg)

        # 4. Deduplicate near-identical candidates.
        quads = self._dedupe_quads(quads)

        # 5. Score every candidate with an outness-aware metric.
        if quads:
            scored: List[Tuple[float, CornerPoints, str, float, Dict[str, Any]]] = []
            for pts, method in quads:
                ordered_scaled = order_corners(pts.astype(np.float32))
                ordered_orig = order_corners(pts.astype(np.float32) * inv_scale)
                score, details = self._score_quadrilateral(
                    ordered_scaled, scaled, fg_mask, fg_dil,
                    total_fg, total_fg_dil,
                    total_scaled_area, is_card, profile
                )
                scored.append((score, ordered_orig, method, details))

            scored.sort(key=lambda x: x[0], reverse=True)
            best_score, best_corners, best_method, best_details = scored[0]

            # Compute margin over the second-best DISTINCT candidate.
            margin = 0.0
            second_score = None
            if len(scored) > 1:
                second_score = scored[1][0]
                margin = best_score - second_score

            # Count how many candidates agree (are near-duplicates) with the winner.
            # Multiple independent methods converging on the same boundary is
            # strong evidence -- reward it.
            agreement = 1
            best_pts0 = self._center_normalize(scored[0][1])
            for score, corners, method, _ in scored:
                if score == best_score:
                    continue
                if self._corner_norm_dist(self._center_normalize(corners), best_pts0) < 0.12:
                    agreement += 1

            confidence = self._outness_confidence(
                best_score, margin, best_details, total_fg, agreement, len(scored)
            )

            if debug_dir:
                self._save_debug(scaled, quads, scored, best_details, best_method,
                                 debug_dir, inv_scale, fg_mask, fg_dil)

            if best_score >= 0.45:
                logger.info(
                    f"Accepted outer quad: score={best_score:.3f} conf={confidence:.3f} "
                    f"method={best_method} margin={margin:.3f} agreement={agreement} "
                    f"encloses={best_details.get('enclosure',0):.2f}"
                )
                return DetectionResult(
                    corners=best_corners,
                    confidence=float(confidence),
                    method=f"opencv_{best_method}",
                    is_fallback=False,
                    metadata={
                        "score": float(best_score),
                        "enclosure": float(best_details.get("enclosure", 0.0)),
                        "num_candidates": len(scored),
                        "margin": float(margin),
                        "agreement": agreement,
                        "method": best_method,
                    },
                )

        # 6. Safe fallback
        logger.warning("No high-confidence outer boundary found. Requesting manual corner review.")
        margin_x = 0.05 * w_orig
        margin_y = 0.05 * h_orig
        fallback_pts = CornerPoints(
            top_left=(margin_x, margin_y),
            top_right=(w_orig - margin_x, margin_y),
            bottom_right=(w_orig - margin_x, h_orig - margin_y),
            bottom_left=(margin_x, h_orig - margin_y),
        )
        return DetectionResult(
            corners=fallback_pts,
            confidence=0.20,
            method="opencv_fallback_margin",
            is_fallback=True,
            metadata={"reason": "no_candidate_passed_outer_boundary_validation"},
        )

    # ─────────────────────────────────────────────────────────────────────
    # Foreground segmentation
    # ─────────────────────────────────────────────────────────────────────
    def _estimate_background_level(self, image: np.ndarray) -> float:
        """Estimates background luminance from the image border strip."""
        h, w = image.shape[:2]
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        strip = 0.06 * min(h, w)
        parts = [
            gray[:int(strip), :],
            gray[-int(strip):, :],
            gray[:, :int(strip)],
            gray[:, -int(strip):],
        ]
        samples = np.concatenate([p.ravel() for p in parts])
        return float(np.median(samples))

    def _build_foreground_mask(self, image: np.ndarray) -> np.ndarray:
        """
        Returns a binary mask of document/content pixels, robust to both
        dark and light backgrounds (background level estimated from borders).
        """
        h, w = image.shape[:2]
        # Exclude the border strip from the mask itself so the estimated
        # background doesn't leak in and connect to the content.
        border_mask = ImagePreprocessor.get_border_mask(h, w, margin_percent=0.04)
        bg_level = self._estimate_background_level(image)
        lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB)
        l_chan = lab[:, :, 0].astype(np.float32)

        # Brightness differencing vs. background
        diff = np.abs(l_chan - bg_level)
        # A document differs from background; use a relative threshold.
        # Scale by global contrast so low-contrast photos still work.
        global_std = float(np.std(l_chan))
        thresh = max(bg_level * 0.25, 12.0)
        if global_std > 1:
            thresh = max(thresh, global_std * 0.5)

        fg = (diff > thresh).astype(np.uint8) * 255
        fg = cv2.bitwise_and(fg, fg, mask=border_mask)

        # Morphologically clean small speckle, preserve structure.
        k_small = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
        fg = cv2.morphologyEx(fg, cv2.MORPH_OPEN, k_small, iterations=1)

        # If almost nothing was detected (e.g. uniform near-background doc),
        # fall back to a luminance-based segmentation.
        if cv2.countNonZero(fg) < int(0.02 * h * w):
            _, otsu = cv2.threshold(l_chan, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            # choose the side that is NOT the background
            if bg_level > 127:
                otsu = 255 - otsu  # background is bright -> keep dark docs
            fg = cv2.bitwise_and(otsu, otsu, mask=border_mask).astype(np.uint8)

        return fg

    def _subtract_skin(self, image: np.ndarray, fg_mask: np.ndarray) -> np.ndarray:
        """
        Removes skin-colored pixels from the foreground mask.

        When a card is held in someone's hand the foreground segmentation
        picks up the hand/arm as document content, causing the outer-boundary
        quad to encompass the holder rather than the card.
        Skin tones occupy a well-defined region in YCrCb and HSV color spaces;
        subtracting them from the foreground mask leaves mostly the card face.

        Conservative thresholds are used so that cards with skin-tone
        backgrounds (light-brown paper) are not mistakenly suppressed.
        """
        h, w = fg_mask.shape[:2]

        # ── YCrCb skin model (robust across ethnicities) ──────────────────
        ycrcb = cv2.cvtColor(image, cv2.COLOR_BGR2YCrCb)
        skin_ycrcb = cv2.inRange(
            ycrcb,
            np.array([0,   133, 77],  dtype=np.uint8),
            np.array([255, 173, 127], dtype=np.uint8),
        )

        # ── HSV skin model ────────────────────────────────────────────────
        hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
        skin_hsv = cv2.inRange(
            hsv,
            np.array([0,  20,  50],  dtype=np.uint8),
            np.array([25, 200, 255], dtype=np.uint8),
        )
        # Wrap-around for reddish hues (H > 165)
        skin_hsv2 = cv2.inRange(
            hsv,
            np.array([165, 20,  50],  dtype=np.uint8),
            np.array([180, 200, 255], dtype=np.uint8),
        )
        skin_hsv = cv2.bitwise_or(skin_hsv, skin_hsv2)

        # Intersection of both models → conservative skin mask
        skin = cv2.bitwise_and(skin_ycrcb, skin_hsv)

        # Dilate slightly to cover partially-saturated edge pixels
        k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
        skin = cv2.dilate(skin, k, iterations=2)

        # Only suppress skin if it is actually present in the foreground
        # (guard against incorrectly stripping cards on skin-tone backgrounds).
        skin_in_fg = cv2.countNonZero(cv2.bitwise_and(fg_mask, skin))
        if skin_in_fg < int(0.03 * h * w):
            return fg_mask  # negligible skin detected – leave mask unchanged

        no_skin = cv2.bitwise_and(fg_mask, cv2.bitwise_not(skin))

        # Only use the skin-suppressed mask if it still has meaningful content
        # (some cards have skin-tone colour fields; we don't want to erase them).
        if cv2.countNonZero(no_skin) >= int(0.03 * h * w):
            return no_skin
        return fg_mask  # fallback: skin suppression removed too much

    def _clean_foreground(self, fg_mask: np.ndarray) -> np.ndarray:
        """
        Drops tiny speckle components (noise, reflections far from the document)
        while preserving the substantive document content components.
        """
        h, w = fg_mask.shape[:2]
        n, labels, stats, _ = cv2.connectedComponentsWithStats(fg_mask, 8)
        if n <= 1:
            return fg_mask
        # Speckle threshold: 0.15% of image area (small specks/glare no dots).
        thr = 0.0015 * h * w
        keep = [1]
        for i in range(2, n):
            if stats[i, cv2.CC_STAT_AREA] >= thr:
                keep.append(i)
        cleaned = np.zeros_like(fg_mask)
        for i in keep:
            cleaned[labels == i] = 255
        return cleaned

    # ─────────────────────────────────────────────────────────────────────
    # Candidate generation (multiple strategies)
    # ─────────────────────────────────────────────────────────────────────
    def _generate_candidates(
        self, scaled: np.ndarray, fg_mask: np.ndarray,
        total_scaled_area: float, total_fg: int
    ) -> List[Tuple[np.ndarray, str]]:
        candidates: List[Tuple[np.ndarray, str]] = []

        # Strategy A: contour approximation across multiple binary sources.
        candidates.extend(self._strategy_contour_approx(scaled, total_scaled_area))

        # Strategy B: Hough-line rectangle — finds the card's actual physical
        # boundary from dominant straight-edge segments. Most reliable strategy
        # for cards held in hands where the foreground includes skin.
        candidates.extend(self._strategy_hough_rectangle(scaled, total_scaled_area))

        # Strategy C: foreground-region outer footprint.
        # Use skin-suppressed foreground so that the holder's hand/arm does
        # not inflate the bounding quad beyond the card boundary.
        fg_no_skin = self._subtract_skin(scaled, fg_mask)
        candidates.extend(self._strategy_foreground_outer(scaled, fg_no_skin, total_scaled_area))

        return candidates

    def _strategy_hough_rectangle(
        self, scaled: np.ndarray, total_scaled_area: float
    ) -> List[Tuple[np.ndarray, str]]:
        """
        Detects the card boundary using Probabilistic Hough Line Transform.

        Cards have 4 very straight, sharp edges. This strategy:
        1. Detects all strong line segments.
        2. Clusters them into 4 directional groups (top, bottom, left, right).
        3. Fits one representative line per group.
        4. Computes the 4 corner intersection points.

        Robust for cards held in hands because card edges are usually
        sharper than the skin/background boundary.
        """
        h_sc, w_sc = scaled.shape[:2]
        candidates: List[Tuple[np.ndarray, str]] = []

        gray = cv2.cvtColor(scaled, cv2.COLOR_BGR2GRAY)
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)
        high_t, _ = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        edges = cv2.Canny(blurred, 0.3 * high_t, high_t)

        # Dilate edges slightly to bridge tiny gaps at card corners
        k = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
        edges = cv2.dilate(edges, k, iterations=1)

        min_line_len = int(0.12 * min(h_sc, w_sc))
        lines = cv2.HoughLinesP(
            edges,
            rho=1,
            theta=np.pi / 180,
            threshold=max(30, int(0.06 * min(h_sc, w_sc))),
            minLineLength=min_line_len,
            maxLineGap=int(0.04 * min(h_sc, w_sc)),
        )
        if lines is None or len(lines) < 4:
            return candidates

        # Represent each segment by its angle (0-180°), midpoint, and length
        segs = []
        for seg in lines:
            x1, y1, x2, y2 = seg[0]
            angle = float(np.degrees(np.arctan2(y2 - y1, x2 - x1))) % 180.0
            mx, my = (x1 + x2) / 2.0, (y1 + y2) / 2.0
            length = float(np.hypot(x2 - x1, y2 - y1))
            segs.append((angle, mx, my, length, x1, y1, x2, y2))

        def _angle_diff(a, b):
            d = abs(a - b) % 180
            return min(d, 180 - d)

        def _line_from_segs(group):
            """Fit a single line to a group of segments (weighted by length)."""
            pts, wts = [], []
            for angle, mx, my, length, x1, y1, x2, y2 in group:
                pts.extend([(x1, y1), (x2, y2)])
                wts.extend([length, length])
            pts = np.array(pts, dtype=np.float32)
            wts = np.array(wts, dtype=np.float32)
            cx = np.average(pts[:, 0], weights=wts)
            cy = np.average(pts[:, 1], weights=wts)
            a_mean = float(np.average([s[0] for s in group], weights=[s[3] for s in group]))
            return cx, cy, a_mean  # (cx, cy, angle_degrees)

        def _intersect(cx1, cy1, a1_deg, cx2, cy2, a2_deg):
            """Intersect two lines given centre-point + angle."""
            a1, a2 = np.radians(a1_deg), np.radians(a2_deg)
            dx1, dy1 = np.cos(a1), np.sin(a1)
            dx2, dy2 = np.cos(a2), np.sin(a2)
            denom = dx1 * dy2 - dy1 * dx2
            if abs(denom) < 1e-6:
                return None
            t = ((cx2 - cx1) * dy2 - (cy2 - cy1) * dx2) / denom
            return float(cx1 + t * dx1), float(cy1 + t * dy1)

        # Try two angular decompositions: near-axis-aligned cards and
        # moderately rotated cards (up to ~45°).
        for rot_offset in [0, 45]:
            h_segs, v_segs = [], []
            for seg in segs:
                a = (seg[0] + rot_offset) % 180
                if a <= 25 or a >= 155:
                    h_segs.append(seg)  # "horizontal"
                elif 65 <= a <= 115:
                    v_segs.append(seg)  # "vertical"

            if len(h_segs) < 2 or len(v_segs) < 2:
                continue

            # Split horizontals into top vs bottom by midpoint y
            h_segs.sort(key=lambda s: s[2])  # sort by my
            mid_y = np.mean([s[2] for s in h_segs])
            top_segs = [s for s in h_segs if s[2] <= mid_y]
            bot_segs = [s for s in h_segs if s[2] > mid_y]

            # Split verticals into left vs right by midpoint x
            v_segs.sort(key=lambda s: s[1])  # sort by mx
            mid_x = np.mean([s[1] for s in v_segs])
            left_segs = [s for s in v_segs if s[1] <= mid_x]
            right_segs = [s for s in v_segs if s[1] > mid_x]

            if not (top_segs and bot_segs and left_segs and right_segs):
                continue

            top_line    = _line_from_segs(top_segs)
            bot_line    = _line_from_segs(bot_segs)
            left_line   = _line_from_segs(left_segs)
            right_line  = _line_from_segs(right_segs)

            corners = [
                _intersect(*top_line,   *left_line),
                _intersect(*top_line,   *right_line),
                _intersect(*bot_line,   *right_line),
                _intersect(*bot_line,   *left_line),
            ]
            if any(c is None for c in corners):
                continue

            pts = np.array(corners, dtype=np.float32)
            # Clip to image bounds with a small margin
            pts[:, 0] = np.clip(pts[:, 0], -0.1 * w_sc, 1.1 * w_sc)
            pts[:, 1] = np.clip(pts[:, 1], -0.1 * h_sc, 1.1 * h_sc)

            area = cv2.contourArea(pts.reshape(-1, 1, 2))
            area_ratio = area / max(total_scaled_area, 1)
            if _MIN_AREA_RATIO <= area_ratio <= 0.80 and self._valid_quad(pts, w_sc, h_sc):
                candidates.append((pts, f"hough_rect_rot{rot_offset}"))

        return candidates

    def _strategy_contour_approx(
        self, scaled: np.ndarray, total_scaled_area: float
    ) -> List[Tuple[np.ndarray, str]]:
        candidates: List[Tuple[np.ndarray, str]] = []
        h_sc, w_sc = scaled.shape[:2]
        border_mask = ImagePreprocessor.get_border_mask(h_sc, w_sc, margin_percent=0.015)

        gray = cv2.cvtColor(scaled, cv2.COLOR_BGR2GRAY)
        lab = cv2.cvtColor(scaled, cv2.COLOR_BGR2LAB)
        l_chan = lab[:, :, 0]
        bilateral = cv2.bilateralFilter(gray, 9, 75, 75)

        binary_sources = []
        # Source 1: Canny + close
        high_t, _ = cv2.threshold(bilateral, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        canny = cv2.Canny(bilateral, 0.4 * high_t, high_t)
        canny = cv2.bitwise_and(canny, canny, mask=border_mask)
        k_close = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
        binary_sources.append(("canny_edges", cv2.morphologyEx(canny, cv2.MORPH_CLOSE, k_close, iterations=3)))

        # Source 2: Lab L Otsu
        _, otsu_l = cv2.threshold(l_chan, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        otsu_l = cv2.bitwise_and(otsu_l, otsu_l, mask=border_mask)
        binary_sources.append(("lab_luminance", cv2.morphologyEx(otsu_l, cv2.MORPH_CLOSE, k_close, iterations=2)))

        # Source 3: Morphological gradient
        binary_sources.append(("morph_gradient", ImagePreprocessor.compute_morphological_gradient(scaled)))

        for src_name, bmap in binary_sources:
            contours, _ = cv2.findContours(bmap, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
            for cnt in contours:
                area = cv2.contourArea(cnt)
                area_ratio = area / total_scaled_area
                if not (_MIN_AREA_RATIO <= area_ratio <= _MAX_AREA_RATIO):
                    continue
                x, y, w, h = cv2.boundingRect(cnt)
                if x <= 3 and y <= 3 and (x + w >= w_sc - 4) and (y + h >= h_sc - 4):
                    continue
                hull = cv2.convexHull(cnt)
                hull_peri = cv2.arcLength(hull, True)
                if hull_peri <= 0:
                    continue
                for eps in [0.015, 0.02, 0.025, 0.03, 0.04, 0.05, 0.06]:
                    approx = cv2.approxPolyDP(hull, eps * hull_peri, True)
                    if len(approx) == 4 and cv2.isContourConvex(approx):
                        pts = approx.reshape(4, 2).astype(np.float32)
                        if self._valid_quad(pts, w_sc, h_sc):
                            candidates.append((pts, f"contour_{src_name}_eps{eps}"))
                        break

        return candidates

    def _strategy_foreground_outer(
        self, scaled: np.ndarray, fg_mask: np.ndarray, total_scaled_area: float
    ) -> List[Tuple[np.ndarray, str]]:
        """
        Fits the outer document quad around the foreground document region.

        Generates candidates both from the union of ALL foreground points
        (captures the full document footprint even when the bright interior is
        fragmented) and from the single largest contiguous component.
        """
        candidates: List[Tuple[np.ndarray, str]] = []
        h_sc, w_sc = scaled.shape[:2]
        nonzero = cv2.findNonZero(fg_mask)
        if nonzero is None:
            return candidates

        def add_box(pts, name):
            pts = np.asarray(pts, dtype=np.float32)
            a = cv2.contourArea(pts.reshape(-1, 1, 2))
            r = a / total_scaled_area
            if _MIN_AREA_RATIO <= r <= _MAX_AREA_RATIO and self._valid_quad(pts, w_sc, h_sc):
                candidates.append((pts, name))

        # -- Candidate from union of ALL foreground points (full footprint).
        hull_all = cv2.convexHull(nonzero)
        add_box(cv2.boxPoints(cv2.minAreaRect(hull_all)), "foreground_minAreaRect")
        hull_peri = cv2.arcLength(hull_all, True)
        for eps in [0.02, 0.03, 0.04, 0.05]:
            approx = cv2.approxPolyDP(hull_all, eps * hull_peri, True)
            if len(approx) == 4 and cv2.isContourConvex(approx):
                add_box(approx.reshape(4, 2), "foreground_quad")
                break

        # -- Candidate from the largest contiguous component (handles a clean,
        #    compact document where the full-hull would bleed into noise).
        k = cv2.getStructuringElement(cv2.MORPH_RECT, (11, 11))
        closed = cv2.morphologyEx(fg_mask, cv2.MORPH_CLOSE, k, iterations=4)
        n, labels, stats, _ = cv2.connectedComponentsWithStats(closed, 8)
        if n >= 2:
            big_idx = int(np.argmax(stats[1:, cv2.CC_STAT_AREA])) + 1
            big_area_ratio = stats[big_idx, cv2.CC_STAT_AREA] / total_scaled_area
            if big_area_ratio <= _MAX_AREA_RATIO:
                comp_mask = ((labels == big_idx).astype(np.uint8)) * 255
                contours, _ = cv2.findContours(comp_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                if contours:
                    big_contour = max(contours, key=cv2.contourArea)
                    hull = cv2.convexHull(big_contour)
                    add_box(cv2.boxPoints(cv2.minAreaRect(hull)), "foreground_component_minAreaRect")
                    hull_peri2 = cv2.arcLength(hull, True)
                    for eps in [0.02, 0.03, 0.04, 0.05, 0.06]:
                        approx = cv2.approxPolyDP(hull, eps * hull_peri2, True)
                        if len(approx) == 4 and cv2.isContourConvex(approx):
                            add_box(approx.reshape(4, 2), "foreground_component_quad")
                            break

        return candidates

    # ─────────────────────────────────────────────────────────────────────
    # Candidate scoring (outness-aware)
    # ─────────────────────────────────────────────────────────────────────
    def _score_quadrilateral(
        self,
        corners: CornerPoints,
        scaled: np.ndarray,
        fg_mask: np.ndarray,
        fg_dil: np.ndarray,
        total_fg: int,
        total_fg_dil: int,
        total_scaled_area: float,
        is_card: bool,
        profile: Optional[Any],
    ) -> Tuple[float, Dict[str, Any]]:
        tl = np.array(corners.top_left)
        tr = np.array(corners.top_right)
        br = np.array(corners.bottom_right)
        bl = np.array(corners.bottom_left)
        h_sc, w_sc = scaled.shape[:2]

        pts_int = np.array([tl, tr, br, bl], dtype=np.int32).reshape(-1, 1, 2)

        # -- 1. Enclosure fraction: how much of the (dilated) document foreground
        #       is inside the quad. Dilation fills blank-paper gaps so that an
        #       elongated document quad gets proper enclosure even when content
        #       is fragmented into disconnected lines/bands.
        fill = np.zeros((h_sc, w_sc), dtype=np.uint8)
        cv2.fillPoly(fill, [pts_int], 255)
        inside_fg_dil = int(cv2.countNonZero(cv2.bitwise_and(fill, fill, mask=fg_dil)))
        enclosure = inside_fg_dil / max(total_fg_dil, 1)

        # -- 2. Exterior leak: fraction of the quad area that is NOT foreground
        #       (using the *undilated* mask so that blank paper within the quad
        #       is counted as "leak" -- penalizing oversized quads).
        quad_area = cv2.countNonZero(fill)
        interior_fg_raw = int(cv2.countNonZero(cv2.bitwise_and(fill, fill, mask=fg_mask)))
        leak = 1.0 - (interior_fg_raw / max(quad_area, 1))

        # -- 3. Geometry quality (parallelism, perpendicularity, convexity).
        geo = self._geometry_score(tl, tr, br, bl)

        # -- 4. Area ratio plausibility.
        area_ratio = quad_area / max(total_scaled_area, 1)
        area_score = self._area_plausibility(area_ratio)

        # -- 5. Edge support along the 4 sides (moderate weight; internal
        #       boxes score high here, so it must NOT dominate).
        edge_support = self._edge_support(corners, scaled)

        # -- 6. Aspect-ratio prior (profile). When a format profile is known
        #       (e.g. Long Form ~2.47:1), this becomes a PRIMARY ranking term so
        #       that the elongated document-shaped quad wins over a near-square
        #       box. Without a profile it stays a mild guide.
        aspect_prior = self._aspect_prior(corners, is_card, profile)

        # -- Combined outness-aware score.
        #    Enclosure: an OUTER doc encloses ~all substantive content.
        #    Aspect prior: uses the expected format to prefer the right shape.
        #    Area/leak: prevent swallowing the whole frame or bleeding to bg.
        using_profile = profile is not None
        is_long_form_profile = (
            using_profile
            and hasattr(profile, "aspect_ratio")
            and float(profile.aspect_ratio) >= 2.0
        )
        if is_long_form_profile:
            # LONG FORM detection strategy:
            # The aspect prior is the DOMINANT term (0.50 weight) because a
            # long-form card (~2.47:1) has a very distinctive elongated shape.
            # Any near-square quad can be immediately deprioritized by shape alone.
            # Enclosure weight is lowered because the large blank area in the card
            # band means enclosure scoring is noisier than for standard cards.
            w_enc, w_area, w_aspect, w_leak, w_geo, w_edge = \
                0.20, 0.06, 0.50, -0.05, 0.12, 0.07
        elif using_profile:
            # STANDARD CARD detection strategy (86×54mm, aspect ~1.59):
            # The shape (aspect) prior is the PRIMARY term: selects the quad
            # matching the expected compact rectangle, deprioritizing elongated
            # noise bands that can look like long-form documents.
            w_enc, w_area, w_aspect, w_leak, w_geo, w_edge = \
                0.28, 0.10, 0.38, -0.06, 0.12, 0.05
        else:
            # No profile provided: fall back to enclosure-dominant mode.
            w_enc, w_area, w_aspect, w_leak, w_geo, w_edge = \
                0.52, 0.14, 0.12, -0.10, 0.08, 0.05
        score = (
            w_enc * enclosure
            + w_area * area_score
            + w_aspect * aspect_prior
            + w_leak * leak
            + w_geo * geo
            + w_edge * edge_support
        )
        score = float(np.clip(score, 0.0, 1.0))

        details = {
            "enclosure": float(enclosure),
            "leak": float(leak),
            "geometry": float(geo),
            "area_ratio": float(area_ratio),
            "area_score": float(area_score),
            "edge_support": float(edge_support),
            "aspect_prior": float(aspect_prior),
            "aspect_ratio": float(self._aspect(corners)),
        }
        return score, details

    def _geometry_score(self, tl, tr, br, bl) -> float:
        top_w = np.linalg.norm(tr - tl)
        bot_w = np.linalg.norm(br - bl)
        left_h = np.linalg.norm(bl - tl)
        right_h = np.linalg.norm(br - tr)
        # Parallelism
        w_ratio = min(top_w, bot_w) / max(top_w, bot_w)
        h_ratio = min(left_h, right_h) / max(left_h, right_h)
        parallelism = 0.5 * (w_ratio + h_ratio)
        # Perpendicularity
        pts = [tl, tr, br, bl]
        cos_angles = []
        for i in range(4):
            v1 = pts[i - 1] - pts[i]
            v2 = pts[(i + 1) % 4] - pts[i]
            n1, n2 = np.linalg.norm(v1), np.linalg.norm(v2)
            if n1 > 0 and n2 > 0:
                cos_angles.append(abs(np.dot(v1, v2) / (n1 * n2)))
        perpendicularity = 1.0 - (np.mean(cos_angles) if cos_angles else 0.5)
        return float(np.clip(0.5 * parallelism + 0.5 * perpendicularity, 0.0, 1.0))

    def _area_plausibility(self, area_ratio: float) -> float:
        if 0.10 <= area_ratio <= 0.75:
            return 1.0
        elif 0.05 <= area_ratio <= 0.88:
            return 0.8
        elif 0.03 <= area_ratio <= _MAX_AREA_RATIO:
            return 0.5
        return 0.2

    def _edge_support(self, corners: CornerPoints, scaled: np.ndarray) -> float:
        l_chan = cv2.cvtColor(scaled, cv2.COLOR_BGR2LAB)[:, :, 0]
        edges = cv2.Canny(l_chan, 50, 150)
        edges = cv2.dilate(edges, cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3)), iterations=2)
        pts = np.array([
            corners.top_left, corners.top_right,
            corners.bottom_right, corners.bottom_left
        ], dtype=np.float32)
        n_samples = 40
        hits = 0.0
        count = n_samples * 4
        h, w = edges.shape[:2]
        for i in range(4):
            p1 = pts[i]
            p2 = pts[(i + 1) % 4]
            xs = np.linspace(p1[0], p2[0], n_samples)
            ys = np.linspace(p1[1], p2[1], n_samples)
            xs = np.clip(xs, 0, w - 1).astype(int)
            ys = np.clip(ys, 0, h - 1).astype(int)
            hits += edges[ys, xs].sum() / 255.0
        return float(np.clip(hits / count, 0.0, 1.0))

    def _aspect(self, corners: CornerPoints) -> float:
        tl = np.array(corners.top_left)
        tr = np.array(corners.top_right)
        br = np.array(corners.bottom_right)
        bl = np.array(corners.bottom_left)
        top_w = np.linalg.norm(tr - tl)
        bot_w = np.linalg.norm(br - bl)
        left_h = np.linalg.norm(bl - tl)
        right_h = np.linalg.norm(br - tr)
        w = max(top_w, bot_w)
        h = max(left_h, right_h)
        return max(w, h) / max(min(w, h), 1.0)

    def _aspect_prior(self, corners: CornerPoints, is_card: bool, profile: Optional[Any]) -> float:
        aspect = self._aspect(corners)
        if profile is not None and hasattr(profile, "aspect_ratio"):
            target = float(profile.aspect_ratio)
            is_long_form = target >= 2.0
            ratio = aspect / max(target, 1e-5)
            if is_long_form:
                # Long Form (~2.47:1): tight acceptance band — elongated quads only.
                # A near-square quad (ratio < 0.70) is strongly penalized so it
                # cannot beat a genuinely elongated boundary even on enclosure.
                if 0.78 <= ratio <= 1.22:
                    return 1.0
                elif 0.60 <= ratio <= 1.40:
                    return 0.70
                elif 0.45 <= ratio <= 1.80:
                    return 0.40
                else:
                    return 0.10  # strongly reject obviously-wrong shape
            else:
                # Standard Card (~1.59:1): reward compact rectangle shapes.
                if 0.82 <= ratio <= 1.22:
                    return 1.0
                elif 0.68 <= ratio <= 1.45:
                    return 0.75
                elif 0.52 <= ratio <= 1.80:
                    return 0.50
                else:
                    return 0.25
        # No profile: differentiate by card vs sheet.
        if is_card:
            # Standard card heuristic (86×54mm ~ 1.59:1 landscape).
            if 1.35 <= aspect <= 1.85:
                return 1.0
            elif 1.1 <= aspect <= 2.2:
                return 0.7
            return 0.35
        # Document sheet: broader tolerance.
        lo, hi = 1.0, 3.0
        if lo <= aspect <= hi:
            return 1.0
        elif lo * 0.6 <= aspect <= hi * 1.4:
            return 0.7
        return 0.4

    def _outness_confidence(
        self, best_score: float, margin: float,
        best_details: Dict[str, Any], total_fg: int,
        agreement: int = 1, num_candidates: int = 1
    ) -> float:
        enclosure = best_details.get("enclosure", 0.0)
        leak = best_details.get("leak", 1.0)

        # A confident OUTER boundary must enclose nearly all the document and
        # must not be bleeding into the background heavily.
        if enclosure >= 0.85 and leak <= 0.75:
            conf = 0.75
            if margin >= 0.10:
                conf = 0.86
            if enclosure >= 0.93 and margin >= 0.15:
                conf = 0.95
        elif enclosure >= 0.70:
            conf = 0.65
            if margin >= 0.10:
                conf = 0.72
        else:
            conf = 0.45

        # Reward independent-method agreement on the same outer boundary.
        if agreement >= 3 and conf < 0.93:
            conf = max(conf, 0.90)
        elif agreement == 2 and conf < 0.82:
            conf = max(conf, 0.80)

        # Penalize when there are multiple materially different plausible
        # candidates competing (uncertain which is truly the outer document).
        # Only relevant when the winner does NOT overwhelmingly contain the doc.
        if enclosure < 0.85 and num_candidates >= 4 and margin < 0.08 and agreement < 2:
            conf = min(conf, 0.55)

        return float(np.clip(conf, 0.0, 0.98))

    def _center_normalize(self, corners: CornerPoints) -> np.ndarray:
        a = np.array([
            corners.top_left, corners.top_right,
            corners.bottom_right, corners.bottom_left,
        ], dtype=np.float32)
        c = a.mean(axis=0)
        r = np.linalg.norm(a - c, axis=1).max()
        return (a - c) / max(r, 1e-5)

    @staticmethod
    def _corner_norm_dist(a: np.ndarray, b: np.ndarray) -> float:
        return float(np.linalg.norm(a - b))

    # ─────────────────────────────────────────────────────────────────────
    # Utility
    # ─────────────────────────────────────────────────────────────────────
    def _valid_quad(self, pts: np.ndarray, w_sc: int, h_sc: int) -> bool:
        if len(pts) != 4:
            return False
        pts = np.asarray(pts, dtype=np.float32)
        # Basic in-frame sanity
        x = pts[:, 0]
        y = pts[:, 1]
        if x.min() < -0.15 * w_sc or x.max() > 1.15 * w_sc:
            return False
        if y.min() < -0.15 * h_sc or y.max() > 1.15 * h_sc:
            return False
        for i in range(4):
            p1 = pts[i - 1]
            p2 = pts[i]
            p3 = pts[(i + 1) % 4]
            v1 = p1 - p2
            v2 = p3 - p2
            n1, n2 = np.linalg.norm(v1), np.linalg.norm(v2)
            if n1 == 0 or n2 == 0:
                return False
            c = np.clip(np.dot(v1, v2) / (n1 * n2), -1, 1)
            a = np.degrees(np.arccos(c))
            if not (40.0 <= a <= 140.0):
                return False
        return True

    def _dedupe_quads(self, quads: List[Tuple[np.ndarray, str]]) -> List[Tuple[np.ndarray, str]]:
        """Removes quads that are near-duplicates of an existing one."""
        unique = []
        for pts, method in quads:
            is_dup = False
            for u_pts, _ in unique:
                if self._quads_similar(pts, u_pts):
                    is_dup = True
                    break
            if not is_dup:
                unique.append((pts, method))
        return unique

    @staticmethod
    def _quads_similar(a: np.ndarray, b: np.ndarray, tol: float = 0.06) -> bool:
        a = np.asarray(a, dtype=np.float32)
        b = np.asarray(b, dtype=np.float32)
        # compare centered, scale-normalized corner positions
        ca = a.mean(axis=0)
        cb = b.mean(axis=0)
        ra = np.linalg.norm(a - ca, axis=1).max()
        rb = np.linalg.norm(b - cb, axis=1).max()
        if ra == 0 or rb == 0:
            return True
        na = (a - ca) / ra
        nb = (b - cb) / rb
        d = np.linalg.norm(na - nb)
        return d < tol

    def _save_debug(
        self, scaled, quads, scored, best_details, best_method,
        debug_dir: str, inv_scale: float,
        fg_mask: np.ndarray, fg_dil: np.ndarray,
    ):
        """Saves candidate visualization + per-candidate scores for debugging."""
        try:
            from pathlib import Path
            out = Path(debug_dir)
            out.mkdir(parents=True, exist_ok=True)

            vis = scaled.copy()
            colors = [
                (255, 0, 0), (0, 255, 0), (0, 0, 255),
                (255, 255, 0), (255, 0, 255), (0, 255, 255),
            ]
            for idx, (score, corners, method, details) in enumerate(scored):
                color = colors[idx % len(colors)]
                pts = np.array([
                    corners.top_left, corners.top_right,
                    corners.bottom_right, corners.bottom_left
                ], dtype=np.int32).reshape(-1, 1, 2)
                cv2.polylines(vis, [pts], True, color, 2)
                # label at centroid
                cx = int(corners.top_left[0] + corners.bottom_right[0]) // 2
                cy = int(corners.top_left[1] + corners.bottom_right[1]) // 2
                label = f"#{idx} encl={details.get('enclosure',0):.2f} sc={score:.2f}"
                cv2.putText(vis, label, (cx, cy), cv2.FONT_HERSHEY_SIMPLEX,
                            0.5, color, 1, cv2.LINE_AA)

            cv2.imwrite(str(out / "03_all_candidate_quads.jpg"), vis)
            cv2.imwrite(str(out / "01_original.jpg"), scaled)
            cv2.imwrite(str(out / "02_preprocessed.jpg"), cv2.cvtColor(scaled, cv2.COLOR_BGR2GRAY))
            # Dilated foreground visualization: yellow = raw fg, green overlay = dilated fill
            fg_vis = scaled.copy()
            fg_vis[fg_mask > 0] = (0, 255, 255)  # yellow for raw foreground
            fg_vis[fg_dil > 0] = (0, 180, 0)     # green for dilated fill
            fg_vis[fg_mask > 0] = (0, 255, 255)  # raw on top
            cv2.imwrite(str(out / "04_foreground_dilated.jpg"), fg_vis)

            import json
            info = {
                "best_method": best_method,
                "best_score": scored[0][0],
                "best_details": best_details,
                "candidates": [
                    {
                        "rank": i,
                        "method": m,
                        "score": round(s, 3),
                        "details": d,
                        "corners_orig": [
                            [round(c.top_left[0], 1) * inv_scale, round(c.top_left[1], 1) * inv_scale],
                            [round(c.top_right[0], 1) * inv_scale, round(c.top_right[1], 1) * inv_scale],
                            [round(c.bottom_right[0], 1) * inv_scale, round(c.bottom_right[1], 1) * inv_scale],
                            [round(c.bottom_left[0], 1) * inv_scale, round(c.bottom_left[1], 1) * inv_scale],
                        ],
                    }
                    for i, (s, c, m, d) in enumerate(scored)
                ],
            }
            with open(out / "boundary_debug.json", "w", encoding="utf-8") as f:
                json.dump(info, f, indent=2)
        except Exception as e:
            logger.warning(f"Could not save boundary debug: {e}")
