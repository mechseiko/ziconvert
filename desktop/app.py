#!/usr/bin/env python3
r"""Launch the zicengine desktop app straight from a checkout.

    python desktop\app.py

No install step and no virtualenv activation needed: this file puts ``desktop/``
and ``core/`` on ``sys.path`` itself, so it works from a bare clone as long as
the engine's dependencies (numpy, opencv, pillow, ezdxf, pyclipper) are
importable by whatever ``python`` you invoked.

The same bootstrap is what ``python -m img2dxf gui`` and the packaged ``.exe``
rely on, so there is one way the app finds the engine and not three.
"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
"""``desktop/`` — holds the ``img2dxf_gui`` package."""

REPO = HERE.parent
"""The monorepo root — ``core/`` underneath it holds the ``img2dxf`` engine."""


def bootstrap() -> list[str]:
    """Put the engine and the GUI package on ``sys.path``; return what was added.

    Front-loaded and de-duplicated so a checkout always wins over a stale
    site-packages install of the same name. That matters when you are editing
    ``core/`` and testing through the GUI: without it, the app silently imports
    the last version you happened to ``pip install``.
    """
    added: list[str] = []
    for candidate in (HERE, REPO / "core"):
        entry = str(candidate)
        if not candidate.is_dir():
            continue
        while entry in sys.path:
            sys.path.remove(entry)
        sys.path.insert(0, entry)
        added.append(entry)
    return added


def main() -> int:
    bootstrap()

    try:
        from img2dxf_gui import launch
    except Exception:  # noqa: BLE001 - shown in a dialog when there is a display
        import traceback

        message = traceback.format_exc()
        try:
            import tkinter as tk
            from tkinter import messagebox

            root = tk.Tk()
            root.withdraw()
            messagebox.showerror("zicengine desktop could not start", message)
            root.destroy()
        except Exception:
            print(message, file=sys.stderr)
        return 1

    launch()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
