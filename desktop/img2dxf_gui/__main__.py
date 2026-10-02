"""``python -m img2dxf_gui`` opens the desktop app."""

from __future__ import annotations

import sys

from .app import launch

if __name__ == "__main__":
    try:
        launch()
    except Exception:  # noqa: BLE001 - surfaced, never silent
        import traceback

        traceback.print_exc()
        sys.exit(1)
