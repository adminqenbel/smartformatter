"""
Synthetic Test Image Generator for QenBel Smart Formatter.
Generates realistic photographs of ID cards and document sheets on varied textured backgrounds
with perspective distortion, rotation, shadows, and noise for automated validation.
"""
from pathlib import Path
import cv2
import numpy as np

from app.utils.image_io import save_image_safe


def create_wooden_background(width: int, height: int) -> np.ndarray:
    """Generates a warm wooden desk texture with grain and subtle lighting gradient."""
    # Base warm brown
    bg = np.zeros((height, width, 3), dtype=np.uint8)
    bg[:, :] = (38, 65, 115) # BGR warm wood

    # Add wood grain noise
    noise = np.random.normal(0, 15, (height, width, 3)).astype(np.float32)
    # Stretch horizontally for grain
    grain = cv2.GaussianBlur(noise, (1, 15), 0)
    bg_float = np.clip(bg.astype(np.float32) + grain, 0, 255).astype(np.uint8)

    # Add subtle radial vignette / shadow
    y, x = np.ogrid[:height, :width]
    center_y, center_x = height / 2.0, width / 2.0
    dist_from_center = np.sqrt((x - center_x) ** 2 + (y - center_y) ** 2)
    max_dist = np.sqrt(center_x ** 2 + center_y ** 2)
    vignette = 1.0 - 0.25 * (dist_from_center / max_dist)
    vignette = np.dstack([vignette] * 3)

    return np.clip(bg_float * vignette, 0, 255).astype(np.uint8)


def create_dark_desk_background(width: int, height: int) -> np.ndarray:
    """Generates a dark slate/charcoal desk texture."""
    bg = np.zeros((height, width, 3), dtype=np.uint8)
    bg[:, :] = (40, 40, 45)
    noise = np.random.normal(0, 8, (height, width, 3)).astype(np.float32)
    return np.clip(bg.astype(np.float32) + noise, 0, 255).astype(np.uint8)


def render_synthetic_id_card_front(width: int = 600, height: int = 380) -> np.ndarray:
    """Renders a crisp synthetic ID card (Front Side)."""
    card = np.ones((height, width, 3), dtype=np.uint8) * 245 # Off-white card

    # Top header bar
    cv2.rectangle(card, (0, 0), (width, 65), (140, 50, 20), -1) # Dark blue/teal header
    cv2.putText(card, "NATIONAL IDENTITY CARD", (25, 42), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)

    # Photo placeholder
    photo_x, photo_y, photo_w, photo_h = 35, 95, 130, 160
    cv2.rectangle(card, (photo_x, photo_y), (photo_x + photo_w, photo_y + photo_h), (210, 210, 210), -1)
    cv2.rectangle(card, (photo_x, photo_y), (photo_x + photo_w, photo_y + photo_h), (120, 120, 120), 1)
    # Head & shoulders avatar silhouette
    cv2.circle(card, (photo_x + photo_w // 2, photo_y + 55), 30, (130, 130, 140), -1)
    cv2.ellipse(card, (photo_x + photo_w // 2, photo_y + 145), (45, 40), 0, 180, 360, (130, 130, 140), -1)

    # Chip emblem
    chip_x, chip_y = 190, 100
    cv2.rectangle(card, (chip_x, chip_y), (chip_x + 55, chip_y + 42), (80, 180, 220), -1) # Gold chip
    cv2.rectangle(card, (chip_x, chip_y), (chip_x + 55, chip_y + 42), (40, 120, 160), 1)

    # Text fields
    cv2.putText(card, "NAME: JANE DOE", (190, 180), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (30, 30, 30), 2)
    cv2.putText(card, "ID NO: 9876-5432-1098", (190, 215), cv2.FONT_HERSHEY_SIMPLEX, 0.60, (40, 40, 40), 2)
    cv2.putText(card, "DOB: 15/08/1990", (190, 250), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (50, 50, 50), 1)
    cv2.putText(card, "EXPIRY: 31/12/2030", (190, 280), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (50, 50, 50), 1)

    # Bottom footer line
    cv2.rectangle(card, (0, height - 15), (width, height), (140, 50, 20), -1)

    return card


def render_synthetic_id_card_back(width: int = 600, height: int = 380) -> np.ndarray:
    """Renders a crisp synthetic ID card (Back Side)."""
    card = np.ones((height, width, 3), dtype=np.uint8) * 245

    # Magnetic stripe
    cv2.rectangle(card, (0, 30), (width, 85), (25, 25, 25), -1)

    # Barcode
    cv2.rectangle(card, (40, 120), (320, 180), (255, 255, 255), -1)
    for bx in range(50, 310, 6):
        thickness = np.random.choice([1, 2, 3])
        cv2.line(card, (bx, 125), (bx, 175), (0, 0, 0), thickness)

    # QR Code placeholder
    cv2.rectangle(card, (400, 110), (540, 250), (255, 255, 255), -1)
    cv2.rectangle(card, (400, 110), (540, 250), (0, 0, 0), 2)
    cv2.rectangle(card, (420, 130), (450, 160), (0, 0, 0), -1)
    cv2.rectangle(card, (490, 130), (520, 160), (0, 0, 0), -1)
    cv2.rectangle(card, (420, 200), (450, 230), (0, 0, 0), -1)

    # Address / Info Text
    cv2.putText(card, "ADDRESS: 42 BAKER STREET, LONDON", (40, 220), cv2.FONT_HERSHEY_SIMPLEX, 0.50, (40, 40, 40), 1)
    cv2.putText(card, "IF FOUND RETURN TO NEAREST POLICE", (40, 245), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (80, 80, 80), 1)

    # Machine Readable Zone (MRZ lines)
    cv2.rectangle(card, (0, height - 70), (width, height), (230, 230, 230), -1)
    cv2.putText(card, "I<GBRDOE<<JANE<<<<<<<<<<<<<<<<<<", (20, height - 42), cv2.FONT_HERSHEY_PLAIN, 1.4, (20, 20, 20), 2)
    cv2.putText(card, "9876543210GBR9008154F3012318<<<<", (20, height - 18), cv2.FONT_HERSHEY_PLAIN, 1.4, (20, 20, 20), 2)

    return card


def render_synthetic_sheet_page(width: int = 700, height: int = 990, title: str = "INVOICE #4092") -> np.ndarray:
    """Renders a synthetic A4 document page."""
    sheet = np.ones((height, width, 3), dtype=np.uint8) * 252 # Clean paper

    # Header
    cv2.putText(sheet, "ACME PRINTING & SUPPLIES LTD.", (50, 65), cv2.FONT_HERSHEY_SIMPLEX, 0.85, (20, 20, 20), 2)
    cv2.putText(sheet, title, (50, 110), cv2.FONT_HERSHEY_SIMPLEX, 1.1, (160, 40, 20), 2)
    cv2.line(sheet, (50, 130), (width - 50, 130), (180, 180, 180), 2)

    # Billed To
    cv2.putText(sheet, "Billed To: Global Logistics Inc.", (50, 175), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (40, 40, 40), 2)
    cv2.putText(sheet, "Date: 01-Sep-2026", (480, 175), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (40, 40, 40), 1)

    # Table
    table_top = 230
    cv2.rectangle(sheet, (50, table_top), (width - 50, table_top + 40), (220, 220, 220), -1)
    cv2.putText(sheet, "Item Description", (65, table_top + 28), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 2)
    cv2.putText(sheet, "Qty", (380, table_top + 28), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 2)
    cv2.putText(sheet, "Rate", (460, table_top + 28), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 2)
    cv2.putText(sheet, "Amount", (560, table_top + 28), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 2)

    # Rows
    rows = [
        ("Premium Matte Cardstock 350gsm", "500", "$0.45", "$225.00"),
        ("Custom Embossed Business Cards", "1000", "$0.80", "$800.00"),
        ("Large Format A1 Blueprint Print", "10", "$15.00", "$150.00"),
        ("Duplex Laminated ID Badges", "50", "$3.50", "$175.00"),
    ]
    y = table_top + 40
    for desc, qty, rate, amt in rows:
        y += 45
        cv2.line(sheet, (50, y), (width - 50, y), (235, 235, 235), 1)
        cv2.putText(sheet, desc, (65, y - 12), cv2.FONT_HERSHEY_SIMPLEX, 0.52, (50, 50, 50), 1)
        cv2.putText(sheet, qty, (385, y - 12), cv2.FONT_HERSHEY_SIMPLEX, 0.52, (50, 50, 50), 1)
        cv2.putText(sheet, rate, (465, y - 12), cv2.FONT_HERSHEY_SIMPLEX, 0.52, (50, 50, 50), 1)
        cv2.putText(sheet, amt, (565, y - 12), cv2.FONT_HERSHEY_SIMPLEX, 0.52, (50, 50, 50), 2)

    # Total Box
    cv2.rectangle(sheet, (450, y + 40), (width - 50, y + 90), (240, 240, 240), -1)
    cv2.putText(sheet, "TOTAL: $1,350.00", (470, y + 75), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 0), 2)

    # Stamp
    cv2.circle(sheet, (200, y + 120), 45, (60, 60, 200), 2)
    cv2.putText(sheet, "PAID", (175, y + 128), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (60, 60, 200), 2)

    return sheet


def composite_with_perspective(
    foreground: np.ndarray,
    background: np.ndarray,
    dst_quad: np.ndarray,
    add_shadow: bool = True
) -> np.ndarray:
    """Warps foreground into dst_quad on the background with soft drop shadow."""
    h_fg, w_fg = foreground.shape[:2]
    src_pts = np.array([
        [0, 0],
        [w_fg - 1, 0],
        [w_fg - 1, h_fg - 1],
        [0, h_fg - 1]
    ], dtype=np.float32)

    dst_pts = dst_quad.astype(np.float32)
    h_matrix = cv2.getPerspectiveTransform(src_pts, dst_pts)

    bg_h, bg_w = background.shape[:2]
    result = background.copy()

    # Drop shadow
    if add_shadow:
        shadow_mask = np.zeros((bg_h, bg_w), dtype=np.uint8)
        shadow_quad = dst_quad.copy() + np.array([12, 16]) # Offset shadow
        cv2.fillConvexPoly(shadow_mask, shadow_quad.astype(np.int32), 255)
        blurred_shadow = cv2.GaussianBlur(shadow_mask, (35, 35), 0)
        shadow_factor = 1.0 - 0.45 * (blurred_shadow.astype(np.float32) / 255.0)
        result = np.clip(result.astype(np.float32) * np.dstack([shadow_factor]*3), 0, 255).astype(np.uint8)

    # Warp foreground
    warped_fg = cv2.warpPerspective(foreground, h_matrix, (bg_w, bg_h))
    mask = cv2.warpPerspective(np.ones((h_fg, w_fg), dtype=np.uint8) * 255, h_matrix, (bg_w, bg_h))
    mask_3ch = np.dstack([mask] * 3) / 255.0

    blended = np.clip(warped_fg * mask_3ch + result * (1.0 - mask_3ch), 0, 255).astype(np.uint8)
    return blended


def generate_all_samples(output_dir: Path):
    """Generates all synthetic card and sheet test images."""
    cards_dir = output_dir / "cards"
    sheets_dir = output_dir / "sheets"
    cards_dir.mkdir(parents=True, exist_ok=True)
    sheets_dir.mkdir(parents=True, exist_ok=True)

    # 1. Card 1: Straight Card Front on Wood
    bg1 = create_wooden_background(1200, 900)
    fg_card1 = render_synthetic_id_card_front(600, 380)
    quad1 = np.array([
        [300, 260],
        [900, 260],
        [900, 640],
        [300, 640]
    ])
    sample_card_straight = composite_with_perspective(fg_card1, bg1, quad1)
    save_image_safe(sample_card_straight, cards_dir / "card_01_straight_front.jpg")

    # 2. Card 2: Rotated & Perspective Tilt Card Back on Wood
    bg2 = create_wooden_background(1200, 900)
    fg_card2 = render_synthetic_id_card_back(600, 380)
    quad2 = np.array([
        [340, 220],
        [880, 290],
        [780, 720],
        [240, 650]
    ])
    sample_card_rotated_back = composite_with_perspective(fg_card2, bg2, quad2)
    save_image_safe(sample_card_rotated_back, cards_dir / "card_02_rotated_perspective_back.jpg")

    # 3. Card 3: Card Front on Dark Slate Table with Perspective
    bg3 = create_dark_desk_background(1200, 900)
    quad3 = np.array([
        [280, 210],
        [940, 180],
        [890, 680],
        [210, 710]
    ])
    sample_card_dark_table = composite_with_perspective(fg_card1, bg3, quad3)
    save_image_safe(sample_card_dark_table, cards_dir / "card_03_dark_table_front.jpg")

    # 4. Sheet 1: A4 Invoice with Perspective on Wood
    bg4 = create_wooden_background(1400, 1600)
    fg_sheet1 = render_synthetic_sheet_page(700, 990, "INVOICE #4092 - PAGE 1")
    quad4 = np.array([
        [320, 240],
        [1120, 180],
        [1220, 1420],
        [220, 1480]
    ])
    sample_sheet1 = composite_with_perspective(fg_sheet1, bg4, quad4)
    save_image_safe(sample_sheet1, sheets_dir / "sheet_01_invoice_p1.jpg")

    # 5. Sheet 2: A4 Invoice Page 2 with Lighting Gradient
    bg5 = create_dark_desk_background(1400, 1600)
    fg_sheet2 = render_synthetic_sheet_page(700, 990, "STATEMENT OF ACCOUNT - PAGE 2")
    quad5 = np.array([
        [260, 200],
        [1180, 260],
        [1100, 1480],
        [180, 1420]
    ])
    sample_sheet2 = composite_with_perspective(fg_sheet2, bg5, quad5)
    save_image_safe(sample_sheet2, sheets_dir / "sheet_02_invoice_p2.jpg")

    print(f"Generated synthetic test samples in {output_dir}")


if __name__ == "__main__":
    test_img_dir = Path(__file__).resolve().parent.parent / "test_images"
    generate_all_samples(test_img_dir)
