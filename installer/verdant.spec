# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the Verdant Windows build.

Run from the repo root:

    pyinstaller --noconfirm installer/verdant.spec

Produces dist/verdant/ — a folder the WiX installer step harvests.
"""
import os

REPO_ROOT = os.path.join(SPECPATH, "..")

block_cipher = None

a = Analysis(
    [os.path.join(SPECPATH, "verdant-launcher.py")],
    pathex=[REPO_ROOT],
    binaries=[],
    datas=[
        # Jinja templates, static assets, and the crop/pest/zip-zone data
        # files are resolved at runtime via Path(__file__).parent, so they
        # must land next to the app package inside the bundle.
        (os.path.join(REPO_ROOT, "app", "templates"), "app/templates"),
        (os.path.join(REPO_ROOT, "app", "static"), "app/static"),
        (os.path.join(REPO_ROOT, "app", "data"), "app/data"),
    ],
    hiddenimports=[
        "app",
        "app.main",
        "uvicorn.logging",
        "uvicorn.loops",
        "uvicorn.loops.auto",
        "uvicorn.protocols",
        "uvicorn.protocols.http",
        "uvicorn.protocols.http.auto",
        "uvicorn.protocols.websockets",
        "uvicorn.protocols.websockets.auto",
        "uvicorn.lifespan",
        "uvicorn.lifespan.on",
        "uvicorn.middleware",
        "sqlmodel",
        "apscheduler",
        "apscheduler.triggers",
        "jinja2",
        "multipart",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="verdant",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,  # keep the console: it shows the URL and any startup error
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="verdant",
)
