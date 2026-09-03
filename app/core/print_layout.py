"""
Unified Print Layout Engine.

The SAME layout calculation is used by every output path:
  - On-screen print preview
  - PNG / JPG image export
  - PDF export
  - Direct printing (QPrinter)

This guarantees the preview is always an exact representation of what will
actually be printed — the preview and the printed output can never diverge.

Layout contract (Card Mode):
  - A single card entry holds a FRONT and a BACK photographed side.
  - Both sides are normalized to the SAME physical dimensions (profile).
  - The final print layout places them SIDE-BY-SIDE:
        ┌────────────┬────────────┐
        │   FRONT    │    BACK    │
        └────────────┴────────────┘
  - No text, labels, filenames, or metadata are ever rasterized into the
    output. The output contains ONLY the card images.
"""
from dataclasses import dataclass
from typing import Optional, Tuple, List
import numpy as np
import cv2

from app.core.profiles import FormatProfile, CARD_PROFILE
from app.utils.logger import get_logger

logger = get_logger("print_layout")


@dataclass
class LayoutMetrics:
    """Physical + pixel dimensions for a print layout."""

    page_width_mm: float
    page_height_mm: float
    page_width_px: int
    page_height_px: int
    dpi: int
    gap_mm: float = 0.0
    margin_mm: float = 0.0
    front_box_mm: Tuple[float, float, float, float] = (0, 0, 0, 0)  # x, y, w, h (mm)
    back_box_mm: Tuple[float, float, float, float] = (0, 0, 0, 0)


def mm_to_px(mm: float, dpi: int) -> int:
    """Converts millimeters to pixels at the given DPI."""
    return int(round(mm / 25.4 * dpi))


def mm_to_px_f(mm: float, dpi: int) -> float:
    """Converts millimeters to float pixels at the given DPI."""
    return mm / 25.4 * dpi


class CardOutputComposer:
    """
    Dedicated Card Output Composer.
    Input:
        front_processed: BGR np.ndarray or None
        back_processed: BGR np.ndarray or None
        profile: FormatProfile
        gap_px: int (default 0)
    Output:
        final_card_image: BGR np.ndarray
    Rules:
        If front only: final_card_image = front_processed
        If back only:  final_card_image = back_processed
        If front + back: final_card_image = concatenate horizontally(front_processed, back_processed)
        Zero labels, zero text, zero UI, zero branding, zero metadata rendered onto pixels.
    """

    @staticmethod
    def compose(
        front_bgr: Optional[np.ndarray],
        back_bgr: Optional[np.ndarray],
        profile: FormatProfile,
        gap_px: int = 0,
    ) -> Optional[np.ndarray]:
        if front_bgr is None and back_bgr is None:
            return None

        target_w = profile.width_px
        target_h = profile.height_px

        def _prepare_side(img: np.ndarray) -> np.ndarray:
            h, w = img.shape[:2]
            if w != target_w or h != target_h:
                return cv2.resize(img, (target_w, target_h), interpolation=cv2.INTER_LANCZOS4)
            return img

        if front_bgr is not None and back_bgr is None:
            return _prepare_side(front_bgr)

        if front_bgr is None and back_bgr is not None:
            return _prepare_side(back_bgr)

        # Both sides present -> concatenate horizontally
        f_norm = _prepare_side(front_bgr)
        b_norm = _prepare_side(back_bgr)

        if gap_px <= 0:
            return np.concatenate((f_norm, b_norm), axis=1)

        gap_canvas = np.full((target_h, gap_px, 3), 255, dtype=np.uint8)
        return np.concatenate((f_norm, gap_canvas, b_norm), axis=1)


class PrintLayoutEngine:
    """
    Computes the side-by-side card layout and renders it as a raster.

    Used by Preview, PNG/JPG export, PDF export, and direct printing so all
    consumers share one layout definition.
    """

    def __init__(self, gap_mm: float = 0.0, margin_mm: float = 8.0, bg_white: bool = True):
        self.gap_mm = gap_mm
        self.margin_mm = margin_mm
        self.bg_white = bg_white

    # ── Metric computation ──────────────────────────────────────────

    def compute_metrics(
        self,
        profile: FormatProfile,
        single_page: bool = False,
        has_front: bool = True,
        has_back: bool = True,
    ) -> LayoutMetrics:
        """
        Computes the layout for a card pair (or single side).
        """
        dpi = profile.dpi
        card_w_mm = profile.width_mm
        card_h_mm = profile.height_mm

        is_both = has_front and has_back

        if single_page:
            # Layout onto an A4 page (portrait), centered.
            page_w_mm = 210.0
            page_h_mm = 297.0
            margin = self.margin_mm
            usable_w = page_w_mm - 2 * margin

            pair_w = (card_w_mm * 2 + self.gap_mm) if is_both else card_w_mm
            scale = min(1.0, usable_w / max(pair_w, 1e-5))
            block_w = pair_w * scale
            block_h = card_h_mm * scale
            x0 = (page_w_mm - block_w) / 2.0
            y0 = (page_h_mm - block_h) / 2.0

            card_w_scaled = card_w_mm * scale
            card_h_scaled = card_h_mm * scale
            if is_both:
                front_box = (x0, y0, card_w_scaled, card_h_scaled)
                back_box = (x0 + card_w_scaled + self.gap_mm * scale, y0, card_w_scaled, card_h_scaled)
            elif has_front:
                front_box = (x0, y0, card_w_scaled, card_h_scaled)
                back_box = (0, 0, 0, 0)
            else:
                front_box = (0, 0, 0, 0)
                back_box = (x0, y0, card_w_scaled, card_h_scaled)

            page_px_w = mm_to_px(page_w_mm, dpi)
            page_px_h = mm_to_px(page_h_mm, dpi)
            return LayoutMetrics(
                page_width_mm=page_w_mm, page_height_mm=page_h_mm,
                page_width_px=page_px_w, page_height_px=page_px_h,
                dpi=dpi, gap_mm=self.gap_mm * scale, margin_mm=margin,
                front_box_mm=front_box, back_box_mm=back_box,
            )

        # Pair-only / exact block layout (canvas sized exactly to content).
        gap = self.gap_mm if is_both else 0.0
        block_w_mm = (card_w_mm * 2 + gap) if is_both else card_w_mm
        block_h_mm = card_h_mm
        x0 = 0.0
        y0 = 0.0
        if is_both:
            front_box = (x0, y0, card_w_mm, card_h_mm)
            back_box = (x0 + card_w_mm + gap, y0, card_w_mm, card_h_mm)
        elif has_front:
            front_box = (x0, y0, card_w_mm, card_h_mm)
            back_box = (0, 0, 0, 0)
        else:
            front_box = (0, 0, 0, 0)
            back_box = (x0, y0, card_w_mm, card_h_mm)

        return LayoutMetrics(
            page_width_mm=block_w_mm, page_height_mm=block_h_mm,
            page_width_px=profile.width_px * 2 if is_both else profile.width_px,
            page_height_px=profile.height_px,
            dpi=dpi, gap_mm=gap, margin_mm=0.0,
            front_box_mm=front_box, back_box_mm=back_box,
        )

    def layout_sheet(
        self,
        profile: FormatProfile,
        copies: int = 1,
    ) -> Tuple[LayoutMetrics, List[Tuple[Tuple[float, float, float, float],
                                         Tuple[float, float, float, float]]]]:
        """
        Lays out `copies` of the same card pair onto a single A4 sheet,
        tiling FRONT|BACK blocks in a grid.

        Returns (page_metrics, [(front_box_mm, back_box_mm), ...]).
        """
        dpi = profile.dpi
        page_w_mm, page_h_mm = 210.0, 297.0
        margin = self.margin_mm
        gap = self.gap_mm

        card_w, card_h = profile.width_mm, profile.height_mm
        block_w = card_w * 2 + gap
        block_h = card_h

        # Columns/rows that fit on the sheet.
        cols = max(1, int((page_w_mm - 2 * margin + gap) // (block_w + gap)))
        rows = max(1, int((page_h_mm - 2 * margin + gap) // (block_h + gap)))

        placements: List[Tuple[Tuple, Tuple]] = []
        idx = 0
        for r in range(rows):
            for c in range(cols):
                if idx >= copies:
                    break
                bx = margin + c * (block_w + gap)
                by = margin + r * (block_h + gap)
                front_box = (bx, by, card_w, card_h)
                back_box = (bx + card_w + gap, by, card_w, card_h)
                placements.append((front_box, back_box))
                idx += 1
            if idx >= copies:
                break

        # Auto-grow page height if more copies than the grid fits (rare).
        if idx < copies:
            needed_rows = int(np.ceil((copies - idx) / cols))
            page_h_mm = margin * 2 + (rows + needed_rows) * (block_h + gap)
            for r in range(rows, rows + needed_rows):
                for c in range(cols):
                    if idx >= copies:
                        break
                    bx = margin + c * (block_w + gap)
                    by = margin + r * (block_h + gap)
                    front_box = (bx, by, card_w, card_h)
                    back_box = (bx + card_w + gap, by, card_w, card_h)
                    placements.append((front_box, back_box))
                    idx += 1

        metrics = LayoutMetrics(
            page_width_mm=page_w_mm, page_height_mm=page_h_mm,
            page_width_px=mm_to_px(page_w_mm, dpi),
            page_height_px=mm_to_px(page_h_mm, dpi),
            dpi=dpi, gap_mm=gap, margin_mm=margin,
        )
        return metrics, placements

    # ── Rendering ───────────────────────────────────────────────────

    def render_pair(
        self,
        front_bgr: Optional[np.ndarray],
        back_bgr: Optional[np.ndarray],
        profile: FormatProfile,
        copies: int = 1,
        single_page: bool = False,
    ) -> Tuple[Optional[np.ndarray], Optional[LayoutMetrics]]:
        """
        Renders the side-by-side FRONT|BACK layout (or tiled copies on an A4
        sheet) as a BGR raster. Returns (image, metrics).

        If neither side is present, returns (None, metrics).
        """
        if front_bgr is None and back_bgr is None:
            return None, None

        if single_page:
            return self._render_sheet(front_bgr, back_bgr, profile, copies)

        metrics = self.compute_metrics(
            profile,
            single_page=False,
            has_front=(front_bgr is not None),
            has_back=(back_bgr is not None),
        )
        return self._render_pair_block(front_bgr, back_bgr, profile, metrics)

    def _render_pair_block(
        self,
        front_bgr: Optional[np.ndarray],
        back_bgr: Optional[np.ndarray],
        profile: FormatProfile,
        metrics: LayoutMetrics,
    ) -> Tuple[np.ndarray, LayoutMetrics]:
        gap_px = int(round(mm_to_px(metrics.gap_mm, metrics.dpi)))
        composed = CardOutputComposer.compose(front_bgr, back_bgr, profile, gap_px=gap_px)
        if composed is not None:
            return composed, metrics

        dpi = metrics.dpi
        W = metrics.page_width_px
        H = metrics.page_height_px
        bg = (255, 255, 255) if self.bg_white else (0, 0, 0)
        canvas = np.full((H, W, 3), bg, dtype=np.uint8)
        return canvas, metrics

    def _render_sheet(
        self,
        front_bgr: Optional[np.ndarray],
        back_bgr: Optional[np.ndarray],
        profile: FormatProfile,
        copies: int,
    ) -> Tuple[np.ndarray, LayoutMetrics]:
        metrics, placements = self.layout_sheet(profile, copies)
        W, H = metrics.page_width_px, metrics.page_height_px
        bg = (255, 255, 255) if self.bg_white else (0, 0, 0)
        canvas = np.full((H, W, 3), bg, dtype=np.uint8)

        dpi = metrics.dpi
        for front_box, back_box in placements:
            if front_bgr is not None:
                self._paste_card(canvas, front_bgr, dpi, front_box)
            if back_bgr is not None:
                self._paste_card(canvas, back_bgr, dpi, back_box)
        return canvas, metrics

    def _paste_card(
        self,
        canvas: np.ndarray,
        card_bgr: np.ndarray,
        dpi: int,
        box_mm: Tuple[float, float, float, float],
    ):
        """Resizes a normalized card and pastes it into the mm box without distortion."""
        x_mm, y_mm, w_mm, h_mm = box_mm
        x0 = int(mm_to_px_f(x_mm, dpi))
        y0 = int(mm_to_px_f(y_mm, dpi))
        w = max(1, mm_to_px(w_mm, dpi))
        h = max(1, mm_to_px(h_mm, dpi))

        resized = cv2.resize(card_bgr, (w, h), interpolation=cv2.INTER_LANCZOS4)

        H, W = canvas.shape[:2]
        x1 = min(x0 + w, W)
        y1 = min(y0 + h, H)
        x0 = max(0, min(x0, W))
        y0 = max(0, min(y0, H))
        if x1 > x0 and y1 > y0:
            canvas[y0:y1, x0:x1] = resized[: y1 - y0, : x1 - x0]
