# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

block_cipher = None

import cv2

project_root = Path.cwd()

datas = [
    (str(project_root / 'Logo'), 'Logo'),
    (cv2.data.haarcascades, 'cv2/data'),
]

hiddenimports = [
    'PySide6',
    'PySide6.QtCore',
    'PySide6.QtGui',
    'PySide6.QtWidgets',
    'PySide6.QtPrintSupport',
    'cv2',
    'PIL',
    'PIL.Image',
    'PIL.ImageOps',
    'docx',
    'numpy',
]

excludes = [
    'paddle',
    'paddleocr',
    'paddlex',
    'transformers',
    'torch',
    'torchvision',
    'torchaudio',
    'tensorflow',
    'sklearn',
    'scipy',
    'pandas',
    'pyarrow',
    'plotly',
    'altair',
    'mako',
    'sqlalchemy',
    'psycopg2',
    'grpc',
    'nltk',
    'librosa',
    'llvmlite',
    'numba',
    'soundfile',
    'av',
    'fsspec',
    'jinja2',
    'jsonschema',
    'jmespath',
    'lark',
    'PyQt6',
    'PyQt6.QtCore',
    'PyQt6.QtGui',
    'PyQt6.QtWidgets',
    'PyQt6.sip',
    'PyQt5',
    'tkinter',
    '_tkinter',
    'matplotlib',
    'IPython',
    'notebook',
    'pytest',
]

a = Analysis(
    ['app/main.py'],
    pathex=[str(project_root)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

# Filter out conflicting third-party ICU libraries (e.g. from poppler/codex on PATH)
# Qt6Core on Windows automatically links against the standard system ICU in System32.
a.binaries = [
    (name, path, type_) for (name, path, type_) in a.binaries
    if not Path(name).name.lower().startswith(('icuuc', 'icudt', 'icuin'))
]

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='QenBelSmartFormatter',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(project_root / 'Logo' / 'app_icon.ico'),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='QenBelSmartFormatter',
)
