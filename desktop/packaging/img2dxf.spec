# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller build for the zicengine desktop app.

One file, no console, no installer. Copy `desktop/dist/img2dxf.exe` to any
Windows machine and double-click it.

This spec is evaluated by PyInstaller, not run as a script, so it leans on the
globals PyInstaller injects (`Analysis`, `PYZ`, `EXE`, `SPECPATH`). `SPECPATH`
is the directory holding this file; deriving every other path from it means the
build works from any working directory and survives the monorepo layout, where
the engine lives two directories away in `core/`.
"""

from pathlib import Path

HERE = Path(SPECPATH).resolve()          # desktop/packaging
DESKTOP = HERE.parent                    # desktop/
REPO = DESKTOP.parent                    # the monorepo root
CORE = REPO / "core"

# Both source trees, explicitly. The frozen app cannot fall back on an
# installed `img2dxf` in site-packages -- if it picked that up instead of the
# checkout, the exe would ship a stale engine and there would be no warning.
pathex = [str(DESKTOP), str(CORE)]

hiddenimports = [
    # Imported lazily and by name, so the dependency graph never reaches them.
    "img2dxf.cli",
    "img2dxf.calibrate",
    "img2dxf.settings",
    "img2dxf.upscale",
    # ezdxf picks writers by DXF version string at runtime.
    "ezdxf.addons",
    "ezdxf.layouts",
    "ezdxf.sections",
]

datas = []
binaries = []

# Optional dependencies. Each is collected only if it is actually installed, so
# the same spec builds with and without drag-and-drop support. `collect_all`
# pulls package data as well as modules: tkinterdnd2 ships a Tcl extension that
# PyInstaller cannot find by following imports.
for optional in ("tkinterdnd2", "ezdxf"):
    try:
        from PyInstaller.utils.hooks import collect_all

        o_datas, o_binaries, o_hidden = collect_all(optional)
        datas += o_datas
        binaries += o_binaries
        hiddenimports += o_hidden
    except Exception:  # noqa: BLE001 - not installed, or no hook; carry on
        pass

# Nothing here imports these, and each drags in tens of megabytes.
excludes = [
    "matplotlib",
    "PySide6",
    "PyQt5",
    "PyQt6",
    "IPython",
    "pytest",
    # The web backend must never end up inside the desktop exe. If it does,
    # something has imported across the monorepo boundary in the wrong
    # direction, and a 40 MB exe is the least of the problems.
    "fastapi",
    "uvicorn",
    "starlette",
]

a = Analysis(
    [str(HERE / "entry.py")],
    pathex=pathex,
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="img2dxf",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    runtime_tmpdir=None,
    # A GUI app: no console window behind it.
    console=False,
    disable_windowed_traceback=False,
    icon=None,
)
