# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path
import sys


python_root = Path(sys.base_prefix)
runtime_binaries = []
for dll_name in ("vcruntime140.dll", "vcruntime140_1.dll", "msvcp140.dll"):
    dll_path = python_root / dll_name
    if dll_path.exists():
        runtime_binaries.append((str(dll_path), '.'))


a = Analysis(
    ['..\\src\\watcher.py'],
    pathex=[],
    binaries=runtime_binaries,
    datas=[
        ('..\\data\\monitors.json', 'data'),
        ('..\\data\\app_version.txt', 'data'),
        ('..\\src\\lostark_watcher\\metadata\\accessory_metadata.json', 'lostark_watcher/metadata'),
    ],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='LostArkWatcher',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
