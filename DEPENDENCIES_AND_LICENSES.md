# Dependency & Commercial License Audit Report

**Project**: QenBel Smart Formatter  
**Target**: Commercial Desktop Application for Windows (.exe distribution)  
**Date**: September 2026  

---

## Executive Summary

All dependencies used in **QenBel Smart Formatter** have been vetted for commercial desktop software distribution. The application uses permissive open-source licenses (Apache 2.0, MIT, BSD-3-Clause, HPND) and standard LGPLv3 for Qt bindings (PySide6 dynamically linked as shared runtime libraries). **No viral GPL or AGPL components are linked statically to proprietary application source code.**

---

## Dependency Inventory

| Package Name | Version | License | Commercial Use Allowed? | Redistribution Requirements | Purpose in Project |
|---|---|---|---|---|---|
| **PySide6** | 6.11.2 | LGPLv3 / Commercial | **Yes** (Free under LGPLv3) | Must dynamically link (standard Python DLL import). Allow users to replace Qt binaries. | Desktop GUI Framework & Interactive Canvas |
| **opencv-python** | 4.13.0 | Apache 2.0 | **Yes** | Include Apache 2.0 notice & copyright attribution. | Edge detection, contours, homography warp, bilateral filter |
| **Pillow** | 12.0.0 | HPND (MIT-like) | **Yes** | Include copyright notice in documentation. | EXIF orientation, image I/O, multi-page PDF generation |
| **python-docx** | 1.2.0 | MIT | **Yes** | Include MIT license notice in documentation. | Automatic Microsoft Word (.docx) print sheet generation |
| **numpy** | 2.1.1 | BSD-3-Clause | **Yes** | Include BSD 3-clause notice. | Fast vectorized coordinate and matrix math |
| **pytest** | 9.1.1 | MIT | **Yes** (Dev/Test Only) | N/A (Not bundled in client runtime). | Automated regression testing suite |
| **pyinstaller** | 6.22.0 | GPL with special packaging exception | **Yes** | Special exception explicitly permits proprietary distribution of output binaries. | Windows .exe packaging |

---

## LGPLv3 Compliance Guidelines for Desktop Distribution

When distributing the packaged `.exe` using PySide6 under LGPLv3:
1. **Dynamic Linking**: PySide6 is loaded dynamically via standard Python C-extensions (`.pyd` / `.dll`).
2. **Attribution**: Include Qt and PySide6 copyright notices in the application's `About` dialog and documentation.
3. **No Qt Modifications**: QenBel Smart Formatter uses official prebuilt upstream PySide6 binaries without modifying Qt internal source code.
