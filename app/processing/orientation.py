"""
Orientation and Orthogonal Rotation Processing.
Content-orientation detection using PaddleOCR text-position analysis,
face cascade, and text-line Sobel heuristics. Produces probability-based
confidence scores for each candidate (0° vs 180°).
"""
from typing import Tuple, Dict, Any, Optional, Union, List
from pathlib import Path
import json
import cv2
import numpy as np

from app.core.models import OrientationResult
from app.utils.logger import get_logger

logger = get_logger("orientation")


def rotate_image(image: np.ndarray, angle_deg: int) -> np.ndarray:
    """Rotates image by 0, 90, 180, or 270 degrees clockwise cleanly."""
    angle_mod = angle_deg % 360
    if angle_mod == 0:
        return image.copy()
    elif angle_mod == 90:
        return cv2.rotate(image, cv2.ROTATE_90_CLOCKWISE)
    elif angle_mod == 180:
        return cv2.rotate(image, cv2.ROTATE_180)
    elif angle_mod == 270:
        return cv2.rotate(image, cv2.ROTATE_90_COUNTERCLOCKWISE)
    else:
        h, w = image.shape[:2]
        center = (w / 2.0, h / 2.0)
        matrix = cv2.getRotationMatrix2D(center, -angle_deg, 1.0)
        cos = np.abs(matrix[0, 0])
        sin = np.abs(matrix[0, 1])
        new_w = int((h * sin) + (w * cos))
        new_h = int((h * cos) + (w * sin))
        matrix[0, 2] += (new_w / 2.0) - center[0]
        matrix[1, 2] += (new_h / 2.0) - center[1]
        return cv2.warpAffine(
            image, matrix, (new_w, new_h),
            flags=cv2.INTER_LANCZOS4, borderMode=cv2.BORDER_REPLICATE
        )


def estimate_deskew_angle(image: np.ndarray) -> float:
    """Estimates small residual skew angle using Hough lines on text lines."""
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if len(image.shape) == 3 else image.copy()
    edges = cv2.Canny(gray, 50, 150, apertureSize=3)
    min_len = image.shape[1] // 4
    lines = cv2.HoughLinesP(edges, 1, np.pi / 180, threshold=100, minLineLength=min_len, maxLineGap=20)
    if lines is None:
        return 0.0
    angles = []
    for line in lines:
        x1, y1, x2, y2 = line[0]
        angle = np.degrees(np.arctan2(y2 - y1, x2 - x1))
        if abs(angle) < 20.0:
            angles.append(angle)
    if not angles:
        return 0.0
    return float(np.median(angles))


_SHARED_OCR = None
_SHARED_OCR_INITIALIZED = False


class DocumentOrientationDetector:
    """
    Content-Orientation Classifier.

    Pipeline:
        1. Profile geometry  → resolve 90° / 270° (physical rectangle alignment)
        2. Two content candidates: 0° and 180°
        3. Score each candidate using PaddleOCR text-position analysis,
           face cascade, and text-line Sobel heuristics
        4. Convert scores → probabilities with margin-based confidence
    """

    def __init__(self):
        try:
            face_cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
            self.face_cascade = cv2.CascadeClassifier(face_cascade_path)
            self._has_face_cascade = not self.face_cascade.empty()
        except Exception as e:
            logger.warning(f"Could not load Haar face cascade: {e}")
            self.face_cascade = None
            self._has_face_cascade = False

        # PaddleOCR is lazily initialized on first use to ensure instant startup
        pass

    # ── PaddleOCR singleton ──

    def _init_paddleocr(self):
        global _SHARED_OCR, _SHARED_OCR_INITIALIZED
        if _SHARED_OCR_INITIALIZED:
            return
        _SHARED_OCR_INITIALIZED = True
        try:
            import os
            import importlib
            os.environ["PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK"] = "True"
            os.environ["FLAGS_use_mkldnn"] = "0"
            paddleocr_mod = importlib.import_module("paddleocr")
            PaddleOCR = getattr(paddleocr_mod, "PaddleOCR")
            _SHARED_OCR = PaddleOCR(
                use_textline_orientation=True,
                lang="en",
                enable_mkldnn=False,
            )
            logger.info("PaddleOCR initialized for orientation detection.")
        except Exception as e:
            logger.warning(f"PaddleOCR not available for orientation: {e}")
            _SHARED_OCR = None

    @property
    def _ocr(self):
        global _SHARED_OCR, _SHARED_OCR_INITIALIZED
        if not _SHARED_OCR_INITIALIZED:
            self._init_paddleocr()
        return _SHARED_OCR

    @property
    def _has_paddleocr(self):
        return self._ocr is not None

    # ── Public API ──

    def detect_orientation(
        self,
        warped_image: np.ndarray,
        profile: Optional[Any] = None,
        save_debug_dir: Optional[Union[str, Path]] = None,
        image_name: str = "card",
    ) -> OrientationResult:
        """
        Returns an OrientationResult with best_angle, probability-based confidence,
        and detailed per-candidate diagnostics.
        """
        h_raw, w_raw = warped_image.shape[:2]

        # ── Stage 1: Profile geometry → resolve 90/270 ──
        is_profile_landscape = True
        if profile is not None and hasattr(profile, "is_landscape"):
            is_profile_landscape = profile.is_landscape

        if is_profile_landscape:
            if h_raw > w_raw:
                initial_rot = 90
                canonical_base = rotate_image(warped_image, 90)
            else:
                initial_rot = 0
                canonical_base = warped_image.copy()
        else:
            if w_raw > h_raw:
                initial_rot = 90
                canonical_base = rotate_image(warped_image, 90)
            else:
                initial_rot = 0
                canonical_base = warped_image.copy()

        # ── Stage 2: Generate content candidates ──
        cand_0 = canonical_base.copy()
        cand_180 = rotate_image(canonical_base, 180)

        # ── Stage 3: DocOrient reference (informational only) ──
        docorient_raw_angle = 0
        try:
            from PIL import Image
            import docorient
            pil_raw = Image.fromarray(cv2.cvtColor(warped_image, cv2.COLOR_BGR2RGB))
            doc_raw_res = docorient.detect_orientation(pil_raw)
            docorient_raw_angle = int(doc_raw_res.angle)
        except Exception:
            pass

        # ── Stage 4: Score each candidate ──
        score_0, det_0 = self._evaluate_candidate(cand_0, "0°")
        score_180, det_180 = self._evaluate_candidate(cand_180, "180°")

        # ── Stage 5: Convert raw scores → probabilities ──
        prob_0, prob_180 = self._scores_to_probabilities(score_0, score_180)

        # ── Stage 6: Select best ──
        if prob_180 > prob_0:
            selected_flip = 180
            best_prob = prob_180
            second_prob = prob_0
            winning_det = det_180
        else:
            selected_flip = 0
            best_prob = prob_0
            second_prob = prob_180
            winning_det = det_0

        margin = best_prob - second_prob

        # ── Stage 7: Confidence ──
        confidence = self._compute_confidence(best_prob, margin, winning_det)

        best_angle = (initial_rot + selected_flip) % 360

        # ── Build result scores dict ──
        scores = {
            (initial_rot + 0) % 360: prob_0,
            (initial_rot + 180) % 360: prob_180,
            (initial_rot + 90) % 360: 0.0,
            (initial_rot + 270) % 360: 0.0,
        }

        details = {
            (initial_rot + 0) % 360: det_0,
            (initial_rot + 180) % 360: det_180,
        }

        # ── Debug artifacts ──
        selected_image = rotate_image(warped_image, best_angle)
        diagnostic_candidates = {
            a: rotate_image(warped_image, a) for a in (0, 90, 180, 270)
        }

        if save_debug_dir:
            out = Path(save_debug_dir)
            out.mkdir(parents=True, exist_ok=True)
            cv2.imwrite(str(out / "01_raw_perspective.png"), warped_image)
            cv2.imwrite(str(out / "02_canonical_base.png"), canonical_base)
            cv2.imwrite(str(out / "03_orientation_0.png"), cand_0)
            cv2.imwrite(str(out / "04_orientation_180.png"), cand_180)
            cv2.imwrite(str(out / "05_selected.png"), selected_image)

            debug_json = {
                "image_name": image_name,
                "profile_landscape": is_profile_landscape,
                "initial_geometry_rotation": initial_rot,
                "selected_flip": selected_flip,
                "best_angle": best_angle,
                "confidence": round(confidence, 4),
                "probabilities": {"0deg": round(prob_0, 4), "180deg": round(prob_180, 4)},
                "margin": round(margin, 4),
                "docorient_angle": docorient_raw_angle,
                "candidate_0": det_0,
                "candidate_180": det_180,
            }
            with open(out / "orientation_debug.json", "w", encoding="utf-8") as f:
                json.dump(debug_json, f, indent=2)

        logger.info(
            f"Orientation: P(0°)={prob_0:.3f}  P(180°)={prob_180:.3f}  "
            f"Selected={best_angle}°  Confidence={confidence:.3f}  "
            f"DocOrient={docorient_raw_angle}°"
        )

        return OrientationResult(
            best_angle=best_angle,
            confidence=confidence,
            scores=scores,
            details=details,
            diagnostic_candidates=diagnostic_candidates,
        )

    # ── Candidate scoring ──

    def _evaluate_candidate(
        self, img: np.ndarray, cand_label: str
    ) -> Tuple[float, Dict[str, Any]]:
        """
        Scores a single content candidate (0° or 180°).

        Signals (weights chosen so OCR confidence is PRIMARY):
            A. PaddleOCR recognition confidence sum      (primary,    weight ×100)
            B. PaddleOCR text-position spatial analysis  (secondary,  weight ×40)
            C. Header / footer semantic position bonus   (tertiary,   weight ×15)
            D. Haar face cascade                         (decisive for portraits, flat +40)
            E. Sobel text-line energy ratio               (supporting, weight ×5)
        """
        h, w = img.shape[:2]
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if len(img.shape) == 3 else img.copy()

        # ── A. PaddleOCR evidence ──
        ocr_conf_score = 0.0
        text_position_score = 0.0
        header_bonus = 0.0
        footer_bonus = 0.0
        ocr_mean_conf = 0.0
        ocr_line_count = 0
        ocr_high_conf_count = 0
        ocr_texts_sample: List[str] = []
        method = "sobel_only"

        header_phrases = [
            "government of india", "bharat sarkar", "unique identification",
            "income tax department", "election commission", "driving licence",
            "republic of india", "identity card", "aadhaar",
            "uidai", "enrolment", "enrollment", "national identity",
            "passport", "driving license", "tax", "pan",
        ]
        footer_phrases = [
            "valid throughout", "services in future", "proof of identity",
            "authenticate online", "help@uidai", "toll free",
            "www.uidai", "resident", "your aadhaar", "vid :",
            "signature", "date of issue", "authority", "address",
        ]

        if self._has_paddleocr and self._ocr is not None:
            method = "paddleocr"
            try:
                scale = min(1.0, 800.0 / max(h, w))
                ocr_input = (
                    cv2.resize(img, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
                    if scale < 1.0
                    else img
                )
                ocr_h, ocr_w = ocr_input.shape[:2]

                res = self._ocr.predict(ocr_input)
                if res and len(res) > 0:
                    r = res[0]
                    texts = r.get("rec_texts", [])
                    rec_scores = r.get("rec_scores", [])
                    polys = r.get("dt_polys", [])
                    ocr_line_count = len(texts)

                    # --- A1: OCR recognition confidence ---
                    # Right-side-up text → higher per-line confidence.
                    # Use SUM of confidences so more text lines = stronger signal.
                    if rec_scores:
                        ocr_mean_conf = float(np.mean(rec_scores))
                        ocr_high_conf_count = sum(1 for s in rec_scores if s > 0.85)
                        # Sum of confidence scores: more lines + higher conf = stronger
                        ocr_conf_score = float(np.sum(rec_scores)) * 100.0

                    # --- A2: Text-position spatial analysis ---
                    # Right-side-up document: text centroids skew toward top.
                    # Compute average normalised Y of all text centroids.
                    # avg_norm_y < 0.5 → text is in upper half → likely right-side-up.
                    top_count = 0
                    bottom_count = 0
                    norm_ys: List[float] = []

                    for poly, text, sc in zip(polys, texts, rec_scores):
                        pts = poly.tolist() if hasattr(poly, "tolist") else poly
                        center_y = float(np.mean([p[1] for p in pts]))
                        norm_y = center_y / float(ocr_h)
                        norm_ys.append(norm_y)

                        if norm_y < 0.40:
                            top_count += 1
                        elif norm_y > 0.60:
                            bottom_count += 1

                        t_lower = text.lower()
                        for hp in header_phrases:
                            if hp in t_lower:
                                if norm_y < 0.50:
                                    header_bonus += 15.0 * sc
                                else:
                                    header_bonus -= 15.0 * sc
                        for fp in footer_phrases:
                            if fp in t_lower:
                                if norm_y > 0.50:
                                    footer_bonus += 15.0 * sc
                                else:
                                    footer_bonus -= 15.0 * sc

                    if norm_ys:
                        avg_norm_y = float(np.mean(norm_ys))
                        # avg_norm_y = 0.3 → text is in top 30% → score = 70 (right-side-up)
                        # avg_norm_y = 0.7 → text is in bottom 30% → score = -30 (upside-down)
                        # Scale: map 0.0–1.0 → +100 to -100
                        text_position_score = (1.0 - avg_norm_y * 2.0) * 100.0
                    else:
                        text_position_score = 0.0

                    ocr_texts_sample = [
                        t.encode("ascii", "ignore").decode("ascii") for t in texts[:6]
                    ]

            except Exception as e:
                logger.warning(f"PaddleOCR error in candidate {cand_label}: {e}")
                method = "paddleocr_error"

        # ── B. Face / Portrait detection ──
        face_detected = False
        face_score = 0.0
        if self._has_face_cascade and self.face_cascade is not None:
            min_face = int(min(h, w) * 0.10)
            max_face = int(min(h, w) * 0.85)
            try:
                faces = self.face_cascade.detectMultiScale(
                    gray, scaleFactor=1.1, minNeighbors=3,
                    minSize=(min_face, min_face), maxSize=(max_face, max_face),
                )
                if len(faces) > 0:
                    face_detected = True
                    face_score = 40.0
            except Exception:
                pass

        # ── C. Sobel text-line energy (supporting) ──
        sy = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
        sx = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
        row_energy = np.mean(np.abs(sy), axis=1)
        col_energy = np.mean(np.abs(sx), axis=0)
        row_var = float(np.var(row_energy))
        col_var = float(np.var(col_energy))
        text_line_ratio = row_var / (col_var + 1e-5)
        sobel_bonus = 5.0 if text_line_ratio > 1.2 else 0.0

        # ── Combined weighted score ──
        # OCR confidence is the dominant discriminator: upside-down text
        # consistently produces lower per-line recognition confidence.
        total_score = (
            ocr_conf_score        # 0–∞, primary signal (×100 weight)
            + text_position_score # −100 to +100, secondary signal
            + header_bonus        # ±N, semantic bonus
            + footer_bonus        # ±N, semantic bonus
            + face_score          # 0 or 40, decisive for portraits
            + sobel_bonus         # 0 or 5, supporting
        )

        details = {
            "cand_label": cand_label,
            "method": method,
            "face_detected": face_detected,
            "face_score": face_score,
            "ocr_line_count": ocr_line_count,
            "ocr_mean_conf": round(ocr_mean_conf, 4),
            "ocr_high_conf_count": ocr_high_conf_count,
            "text_position_score": round(text_position_score, 2),
            "header_bonus": round(header_bonus, 2),
            "footer_bonus": round(footer_bonus, 2),
            "sobel_bonus": round(sobel_bonus, 2),
            "total_score": round(total_score, 2),
            "ocr_texts_sample": ocr_texts_sample,
        }

        return total_score, details

    # ── Probability conversion ──

    @staticmethod
    def _scores_to_probabilities(score_a: float, score_b: float) -> Tuple[float, float]:
        """
        Converts two raw scores into [0, 1] probabilities that sum to 1.0.
        Uses softmax with temperature scaling for numerical stability.
        """
        scores = np.array([score_a, score_b], dtype=np.float64)
        # Shift for numerical stability
        scores_shifted = scores - np.max(scores)
        exp_scores = np.exp(scores_shifted * 0.1)  # temperature = 10 for gentle scaling
        probs = exp_scores / np.sum(exp_scores)
        return float(probs[0]), float(probs[1])

    # ── Confidence ──

    @staticmethod
    def _compute_confidence(
        best_prob: float,
        margin: float,
        winning_det: Dict[str, Any],
    ) -> float:
        """
        Probability-based confidence rule:
            - If best_prob >= 0.70 AND margin >= 0.15  → high confidence
            - If best_prob >= 0.60 AND margin >= 0.10  → medium
            - Otherwise                                  → ambiguous → REVIEW
        """
        has_face = winning_det.get("face_detected", False)

        if has_face and best_prob >= 0.70:
            return min(best_prob + 0.10, 0.98)

        if best_prob >= 0.70 and margin >= 0.15:
            return min(best_prob + 0.05, 0.96)
        elif best_prob >= 0.60 and margin >= 0.10:
            return best_prob
        elif best_prob >= 0.55 and margin >= 0.08:
            return best_prob * 0.9
        else:
            # Ambiguous: force review
            return max(best_prob, 0.45)
