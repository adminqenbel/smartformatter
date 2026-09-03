"""
Command-Line Processing Laboratory & Benchmark for QenBel Smart Formatter.
Processes test cases, saves full visual diagnostics (including 0°, 90°, 180°, 270° candidates),
measures inference speed, and verifies CV accuracy against real-world and synthetic document images.
"""
import sys
from pathlib import Path
import time
import cv2
import numpy as np

# Configure safe utf-8 stdout if supported
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from app.core.config import PrintConfig
from app.core.models import ProcessingMode, EnhancementMode
from app.processing.card_processor import CardProcessor
from app.processing.sheet_processor import SheetProcessor
from app.processing.preprocessor import ImagePreprocessor
from app.export.docx_export import DocxExporter
from app.export.pdf_export import PdfExporter
from app.export.image_export import ImageExporter
from app.utils.image_io import save_image_safe


def draw_corners_overlay(image: np.ndarray, corners, label: str = "") -> np.ndarray:
    """Draws 4 corner markers, red connecting polygon, and corner labels."""
    overlay = image.copy()
    if corners is None:
        return overlay

    pts = corners.to_numpy().astype(np.int32)
    cv2.polylines(overlay, [pts], isClosed=True, color=(48, 59, 255), thickness=3) # Bright Red (BGR)

    corner_names = ["TL", "TR", "BR", "BL"]
    colors = [(255, 255, 255), (255, 255, 255), (255, 255, 255), (255, 255, 255)]

    for i, (pt, name) in enumerate(zip(pts, corner_names)):
        cv2.circle(overlay, (pt[0], pt[1]), 8, (48, 59, 255), -1)
        cv2.circle(overlay, (pt[0], pt[1]), 10, (255, 255, 255), 2)
        cv2.putText(
            overlay, f"{name}", (pt[0] + 12, pt[1] + 5),
            cv2.FONT_HERSHEY_SIMPLEX, 0.75, (255, 255, 255), 3
        )
        cv2.putText(
            overlay, f"{name}", (pt[0] + 12, pt[1] + 5),
            cv2.FONT_HERSHEY_SIMPLEX, 0.75, (48, 59, 255), 2
        )

    if label:
        cv2.putText(
            overlay, label, (30, 50),
            cv2.FONT_HERSHEY_SIMPLEX, 0.9, (48, 59, 255), 2
        )

    return overlay


def run_benchmark():
    root_dir = Path(__file__).resolve().parent.parent
    test_images_dir = root_dir / "test_images"
    output_dir = root_dir / "benchmark_output"
    output_dir.mkdir(parents=True, exist_ok=True)

    print("=================================================================")
    print("      QENBEL SMART FORMATTER -- BENCHMARK & DIAGNOSTIC LAB       ")
    print("=================================================================")

    card_processor = CardProcessor()
    sheet_processor = SheetProcessor()

    # 1. Benchmark Card Mode (Synthetic + Real-World Samples)
    print("\n[1/3] Benchmarking Card Mode & Orientation Evaluation...")
    card_files = list((test_images_dir / "cards").glob("*.jpg"))
    real_files = list((test_images_dir / "real_samples").glob("*.jpeg")) + list((test_images_dir / "real_samples").glob("*.jpg"))
    all_card_files = card_files + real_files

    comparison_records = []

    for card_file in all_card_files:
        t0 = time.perf_counter()
        
        # Run card processing with diagnostic output saving
        case_out = output_dir / "cards" / card_file.stem
        case_out.mkdir(parents=True, exist_ok=True)

        # Detect and perspective-warp
        img_bgr = cv2.imread(str(card_file))
        det_res = card_processor.detector.detect_card(img_bgr)
        w_nat, h_nat = 1011, 638
        if det_res.corners is not None:
            from app.processing.perspective import calculate_target_dimensions, warp_perspective
            w_nat, h_nat = calculate_target_dimensions(det_res.corners)
            warped = warp_perspective(img_bgr, det_res.corners, w_nat, h_nat)
        else:
            warped = img_bgr.copy()

        # Run orientation engine with full diagnostic saving
        orient_res = card_processor.orientation_detector.detect_orientation(
            warped, save_debug_dir=case_out, image_name=card_file.name
        )

        processed = card_processor.process_image(card_file, enhancement_mode=EnhancementMode.DOCUMENT_CRISP)
        duration_ms = (time.perf_counter() - t0) * 1000.0

        if processed is not None:
            # Save full detector diagnostics
            gray = cv2.cvtColor(processed.original_image, cv2.COLOR_BGR2GRAY)
            edges = ImagePreprocessor.prepare_edge_maps(processed.original_image)
            overlay = draw_corners_overlay(
                processed.original_image,
                processed.detected_corners,
                f"Conf: {processed.quality_report.overall_confidence:.2f} ({processed.quality_report.status_level.value})"
            )
            save_image_safe(processed.original_image, case_out / "00_original_capture.jpg")
            save_image_safe(gray, case_out / "00_grayscale.jpg")
            save_image_safe(edges, case_out / "00_edges.jpg")
            save_image_safe(overlay, case_out / "00_selected_quadrilateral.jpg")
            save_image_safe(processed.normalized_image, case_out / "10_normalized_1011x638.jpg")
            save_image_safe(processed.enhanced_image, case_out / "11_enhanced_crisp.jpg")

            # Extract comparison details
            json_path = case_out / "orientation_debug.json"
            paddle_angle = orient_res.best_angle
            docorient_angle = 0
            agreement = False
            if json_path.exists():
                import json
                with open(json_path, "r", encoding="utf-8") as f:
                    j_data = json.load(f)
                    paddle_angle = j_data.get("paddleocr_angle", paddle_angle)
                    docorient_angle = j_data.get("docorient_angle", 0)
                    agreement = j_data.get("agreement", False)

            reliable = "YES" if orient_res.confidence >= 0.75 else "REVIEW REQUIRED"
            comparison_records.append({
                "image": card_file.name[:35],
                "paddle_angle": f"{paddle_angle}°",
                "docorient_angle": f"{docorient_angle}°",
                "reliable": reliable,
                "agreement": "YES" if agreement else "NO",
                "confidence": f"{orient_res.confidence:.0%}"
            })

            ores_str = f" | Orient: {processed.auto_rotation_deg}° (Conf={orient_res.confidence:.0%})"
            print(f"  [OK] {card_file.name:45s} | {duration_ms:5.1f} ms | Conf: {processed.quality_report.overall_confidence:.2f} | Status: {processed.quality_report.status_level.value}{ores_str}")

    # Print Comparison Table
    print("\n==========================================================================================")
    print("                    ORIENTATION COMPARISON REPORT (PaddleOCR vs DocOrient)                ")
    print("==========================================================================================")
    print(f"{'Image':38s} | {'PaddleOCR':10s} | {'DocOrient':10s} | {'Reliable':15s} | {'Agreement':10s}")
    print("-" * 90)
    for r in comparison_records:
        print(f"{r['image']:38s} | {r['paddle_angle']:10s} | {r['docorient_angle']:10s} | {r['reliable']:15s} | {r['agreement']:10s}")
    print("==========================================================================================\n")

    # 2. Benchmark Card Pair Synchronization & Word Export
    print("\n[2/3] Testing Card Pair Synchronization & Word Export...")
    if len(all_card_files) >= 2:
        pair = card_processor.process_pair(all_card_files[0], all_card_files[1], enhancement_mode=EnhancementMode.DOCUMENT_CRISP)
        docx_card_path = output_dir / "card_print_sheet.docx"
        pdf_card_path = output_dir / "card_print_sheet.pdf"
        DocxExporter.export_card_pair(pair, docx_card_path)
        PdfExporter.export_card_pair(pair, pdf_card_path)
        print(f"  [OK] Exported Card Pair Word Doc: {docx_card_path}")
        print(f"  [OK] Exported Card Pair PDF:     {pdf_card_path}")

    # 3. Benchmark Sheet Mode
    print("\n[3/3] Benchmarking Sheet Mode & Multi-Page Export...")
    sheet_files = list((test_images_dir / "sheets").glob("*.jpg"))
    sheet_queue = sheet_processor.process_queue(sheet_files, enhancement_mode=EnhancementMode.DOCUMENT_CRISP)

    for idx, (sheet_file, page) in enumerate(zip(sheet_files, sheet_queue.pages)):
        case_out = output_dir / "sheets" / sheet_file.stem
        case_out.mkdir(parents=True, exist_ok=True)
        overlay = draw_corners_overlay(
            page.original_image,
            page.detected_corners,
            f"Page {idx+1} | Conf: {page.quality_report.overall_confidence:.2f}"
        )
        save_image_safe(page.original_image, case_out / "01_original.jpg")
        save_image_safe(overlay, case_out / "02_detection_overlay.jpg")
        if page.oriented_image is not None:
            save_image_safe(page.oriented_image, case_out / "03_oriented.jpg")
        save_image_safe(page.normalized_image, case_out / "04_normalized.jpg")
        save_image_safe(page.enhanced_image, case_out / "05_enhanced.jpg")
        print(f"  [OK] {sheet_file.name:45s} | Conf: {page.quality_report.overall_confidence:.2f} | Status: {page.quality_report.status_level.value}")

    docx_sheet_path = output_dir / "multi_page_document.docx"
    pdf_sheet_path = output_dir / "multi_page_document.pdf"
    DocxExporter.export_sheet_queue(sheet_queue, docx_sheet_path)
    PdfExporter.export_sheet_queue(sheet_queue, pdf_sheet_path)
    ImageExporter.export_sheet_queue(sheet_queue, output_dir / "exported_images")

    print(f"  [OK] Exported Sheet Word Doc:    {docx_sheet_path}")
    print(f"  [OK] Exported Sheet PDF:         {pdf_sheet_path}")
    print(f"  [OK] Exported Sheet PNG Images:  {output_dir / 'exported_images'}")

    print("\n=================================================================")
    print("                    BENCHMARK COMPLETED                          ")
    print(f" Diagnostic artifacts saved to: {output_dir}")
    print("=================================================================\n")


if __name__ == "__main__":
    run_benchmark()
