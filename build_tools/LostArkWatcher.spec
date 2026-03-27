# -*- mode: python ; coding: utf-8 -*-

import os
import sys
from pathlib import Path


VC_RUNTIME_DLL_NAMES = (
    "concrt140.dll",
    "msvcp140.dll",
    "msvcp140_1.dll",
    "msvcp140_2.dll",
    "msvcp140_atomic_wait.dll",
    "msvcp140_codecvt_ids.dll",
    "vccorlib140.dll",
    "vcruntime140.dll",
    "vcruntime140_1.dll",
    "vcamp140.dll",
    "vcomp140.dll",
)


def collect_vc_runtime_binaries() -> list[tuple[str, str]]:
    python_root = Path(sys.base_prefix)
    search_roots = [
        python_root,
        python_root / "DLLs",
        Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32",
    ]

    runtime_binaries: list[tuple[str, str]] = []
    seen_paths: set[Path] = set()
    for dll_name in VC_RUNTIME_DLL_NAMES:
        for root in search_roots:
            dll_path = root / dll_name
            if not dll_path.exists():
                continue

            resolved_path = dll_path.resolve()
            if resolved_path in seen_paths:
                continue

            runtime_binaries.append((str(resolved_path), "."))
            seen_paths.add(resolved_path)
            break

    return runtime_binaries


runtime_binaries = collect_vc_runtime_binaries()


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
