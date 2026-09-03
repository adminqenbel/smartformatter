# QenBel Smart Formatter — Windows Installer Guide

This guide documents the architecture, build procedure, and maintenance for the professional Windows installer (`QenBel-Smart-Formatter-Setup.exe`).

---

## 1. Prerequisites & Tooling

To compile the Windows installer, the following tools are required:

1. **Python 3.10+ / 3.11** with project dependencies:
   ```bash
   pip install -r requirements.txt
   ```
2. **Inno Setup 6**:
   - Install via Windows Package Manager (`winget`):
     ```cmd
     winget install JRSoftware.InnoSetup
     ```
   - Standard executable path:
     `%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe` or `C:\Program Files (x86)\Inno Setup 6\ISCC.exe`.

---

## 2. Build Process & Reproduction

The build pipeline consists of two stages:
1. **PyInstaller Packaging**: Freezes Python code, PySide6 UI, OpenCV, and dependencies into `dist/QenBelSmartFormatter/`.
2. **Inno Setup Compilation**: Packages the distribution payload into a single self-extracting setup executable.

### One-Click Full Build:
```cmd
build_installer.bat
```

### Quick Installer-Only Compilation (Skipping PyInstaller rebuild):
If `dist/QenBelSmartFormatter/` is already up to date:
```cmd
build_installer.bat --skip-pyinstaller
```

### Generated Artifact:
The setup installer is generated at:
```
dist/installer/QenBel-Smart-Formatter-Setup.exe
```

---

## 3. Installer Architecture & Specifications

| Property | Value / Behavior |
|---|---|
| **Product Name** | QenBel Smart Formatter |
| **Publisher** | QenBel Technologies |
| **Default Location** | `C:\Program Files\QenBel\Smart Formatter` (User-selectable) |
| **Privileges** | Admin elevation requested during installation for `C:\Program Files` write access |
| **Compression** | LZMA2 Ultra-64 (Solid compression for minimal download footprint) |
| **AppId** | `{{E4A28B31-9F22-4D39-A33A-1B8DF12A7C34}}` |
| **Shortcuts** | Desktop shortcut (`Smart Formatter`) and Start Menu (`QenBel \ Smart Formatter`) |
| **Uninstaller** | Registered in Windows Settings → Installed Apps |

---

## 4. User Data & Upgrade Handling

### Separation of Binaries and Mutable User Data
- Binaries and bundled assets are installed into:
  `C:\Program Files\QenBel\Smart Formatter\`
- Mutable customer preferences, logs, and temporary caches are stored in the per-user application directory:
  `%APPDATA%\QenBelSmartFormatter\` (e.g. `C:\Users\<User>\AppData\Roaming\QenBelSmartFormatter\`)

### Seamless Upgrades
Because the `AppId` is fixed across releases:
1. Running a newer version installer (e.g., v1.1.0 over v1.0.0) automatically detects the existing installation.
2. Binary files in `C:\Program Files\QenBel\Smart Formatter\` are updated cleanly.
3. User preferences, logs, and custom profiles in `%APPDATA%\QenBelSmartFormatter\` are fully preserved.

---

## 5. Security & Exclusions

The installer packages only production runtime files from `dist/QenBelSmartFormatter/` and excludes:
- Development virtual environments (`venv/`)
- Git repository (`.git/`)
- Test suites (`tests/`, `pytest_cache/`)
- Development scripts (`scratch/`, temporary images)
- Secrets, passwords, and private API keys (verified by security scan)

---

## 6. Troubleshooting

- **Inno Setup compiler not found**:
  Verify Inno Setup 6 is installed. Ensure `ISCC.exe` is either in `PATH` or located in `%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe`.
- **PyInstaller packaging fails**:
  Run `build_windows_exe.bat` directly to view full PyInstaller logs.
- **Application cannot find models/resources after install**:
  Verify `AppPaths.ROOT_DIR` in `app/core/config.py` resolves correctly relative to the bundled executable.
