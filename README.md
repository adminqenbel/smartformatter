# QenBel Smart Formatter

A Windows desktop application designed specifically for printing shops to automatically detect, crop, straighten, perspective-correct, normalize, and format customer photographs (e.g. from WhatsApp/phone cameras) into print-ready documents and cards.

---

## Key Features

- **Card Mode (Front & Back)**:
  - Supports 1 or 2 images (Front only or Front + Back).
  - One-click **Swap Front / Back**.
  - Automatically detects card boundaries, corrects perspective skew, and normalizes both sides to exact **ISO/IEC 7810 ID-1 standard dimensions** ($85.60 \times 53.98\text{ mm}$ @ 300 DPI).
  - Enforces **symmetrical scale synchronization** so front and back match identically for duplex printing.
- **Sheet Mode (Multi-Page Documents)**:
  - Multi-page batch processing for photographed documents, invoices, and receipts.
  - Automatic page straightening, border removal, and A4/Letter normalization.
  - Full page reordering (Move Up / Down / Remove).
- **1-Click Microsoft Word (`.docx`) Integration**:
  - Automatically places cropped and normalized images into clean Word documents with exact physical centimetre dimensions and cut guides, ready for instant printing with `Ctrl+P`.
- **Interactive 4-Corner Manual Correction Canvas**:
  - High-performance graphics canvas with real-time draggable corner pins.
  - **3x Magnifier Loupe** for sub-pixel precision on mobile captures.
  - Live homography warp preview.
- **Deterministic Quality Engine**:
  - Evaluates blur (Laplacian variance), contrast, underexposure, overexposure, glare, and boundary geometry.
  - Provides clear status indicators: `🟢 HIGH CONFIDENCE`, `🟡 REVIEW RECOMMENDED`, `🔴 MANUAL REVIEW REQUIRED`.
- **Print Enhancement Filters**:
  - `Original`: Raw warped pixels.
  - `Document Crisp`: Auto-levels white balance + text unsharp mask (cleans shadows & yellow paper).
  - `Auto Levels`: Histogram stretch for vivid photos.
  - `High Contrast B&W`: Adaptive Gaussian thresholding for ultra-crisp monochrome forms/receipts.
- **100% Local & Offline**:
  - Zero cloud dependencies or telemetry — guarantees total privacy for customer documents.
- **ChatGPT-Inspired Minimalist Monochrome Interface**:
  - Sleek dark theme with crisp typography and distraction-free workflow.

---

## Project Structure

```
qenbel_smart_formatter/
├── Logo/
│   └── black_text_qenbel_logo_for_light_background.png
├── app/
│   ├── main.py                     # Application entry point
│   ├── core/
│   │   ├── config.py               # Constants, print DPI, dimensions
│   │   ├── models.py               # Data models (CardPair, SheetQueue, etc.)
│   │   └── pipeline.py             # Orchestrator
│   ├── processing/
│   │   ├── preprocessor.py         # Bilateral filter, CLAHE, downscaling
│   │   ├── document_detector.py    # Detector interface
│   │   ├── opencv_detector.py      # Multi-stage contour, quad approx & min-area rect
│   │   ├── perspective.py          # Topological corner ordering & homography
│   │   ├── orientation.py          # Orthogonal rotation & deskew
│   │   ├── normalizer.py           # Canonical dimensions & card pair sync
│   │   ├── quality.py              # Sharpness, glare, geometry scoring
│   │   ├── enhancement.py          # Document Crisp & print filters
│   │   ├── card_processor.py       # Card Mode pipeline
│   │   └── sheet_processor.py      # Sheet Mode pipeline
│   ├── export/
│   │   ├── docx_export.py          # Word (.docx) generator
│   │   ├── pdf_export.py           # Multi-page 300 DPI PDF generator
│   │   └── image_export.py         # Lossless PNG / JPEG exporter
│   ├── ui/
│   │   ├── theme.py                # ChatGPT monochrome stylesheet
│   │   ├── main_window.py          # Shell window with QenBel logo header
│   │   ├── mode_selection.py       # Card vs Sheet mode selector
│   │   ├── upload_view.py          # Drag & Drop intake & async worker
│   │   ├── preview_view.py         # Split comparison & quality inspector
│   │   └── corner_editor.py        # 4-corner draggable canvas + 3x loupe
│   └── utils/
│       ├── logger.py               # Local privacy-safe structured logger
│       └── image_io.py             # Safe Unicode-path & EXIF I/O
├── tests/
│   ├── create_synthetic_samples.py # Synthetic card/sheet generator
│   ├── benchmark.py                # CLI testing lab saving diagnostics
│   ├── test_detector.py            # Automated detector tests
│   ├── test_perspective.py         # Automated perspective tests
│   ├── test_card_processor.py      # Automated card pair tests
│   ├── test_sheet_processor.py     # Automated sheet queue tests
│   └── test_export.py              # Automated Word/PDF export tests
├── requirements.txt                # Dependencies
├── build_windows_exe.bat           # PyInstaller build batch script
├── qenbel_formatter.spec           # PyInstaller spec
└── DEPENDENCIES_AND_LICENSES.md    # Commercial license compliance audit
```

---

## Quickstart & Installation

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Run Application
```bash
python -m app.main
```

### 3. Run Automated Tests
```bash
pytest tests/
```

### 4. Run Benchmark Laboratory
```bash
python -m tests.benchmark
```
*Outputs diagnostic visual artifacts (original, 4-corner overlay, warped, normalized, enhanced, Word docx, and PDF) into `benchmark_output/`.*

---

## Building Windows .exe

To build a standalone Windows desktop executable package:
```cmd
build_windows_exe.bat
```
The compiled application will be created in `dist\QenBelSmartFormatter\QenBelSmartFormatter.exe`.

---

## License & Commercial Distribution

All dependencies are verified for commercial proprietary distribution. For full licensing breakdown, see [DEPENDENCIES_AND_LICENSES.md](file:///d:/qenbel_smart_formatter/DEPENDENCIES_AND_LICENSES.md).
