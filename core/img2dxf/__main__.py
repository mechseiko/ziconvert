"""``python -m img2dxf`` — the engine's own entry point.

Three behaviours, chosen by the arguments:

``python -m img2dxf``
    Opens the desktop app, which is what this command has always done.

``python -m img2dxf gui``
    The same thing, said explicitly.

``python -m img2dxf logo.png -o logo.dxf``
    Converts headlessly and never touches the GUI.

The desktop app lives in ``desktop/``, a separate distribution, so launching it
from here is a *lazy, optional* import. That is deliberate and it is the whole
point of the monorepo rule that dependencies flow ``UI -> core``: this package
installs, imports, converts and passes its test suite on a machine that has no
tkinter and no ``img2dxf-desktop`` at all. Nothing at module level reaches for
a UI library, and ``[project.dependencies]`` in ``core/pyproject.toml`` lists
none.
"""

from __future__ import annotations

import importlib.util
import sys

#: Accepted as the first argument to mean "open the desktop app".
GUI_WORDS = frozenset({"gui", "--gui", "-g"})


def gui_is_available() -> bool:
    """Whether the desktop distribution can be imported, without importing it.

    ``find_spec`` rather than a try/except around the import: this runs on every
    bare invocation, and actually importing tkinter just to discover it is
    missing would cost a moment and, on some broken installs, raise something
    other than ``ImportError``.
    """
    try:
        return importlib.util.find_spec("img2dxf_gui") is not None
    except (ImportError, ValueError, AttributeError):
        return False


def launch_gui() -> int:
    """Open the desktop app, or explain precisely how to get it."""
    try:
        from img2dxf_gui import launch
    except Exception as exc:  # noqa: BLE001 - reported, never swallowed
        print(
            f"error: the desktop app could not start: {exc}\n"
            "  from a checkout:  pip install -e ./core -e ./desktop\n"
            "  or run it directly:  python desktop/app.py",
            file=sys.stderr,
        )
        return 1

    launch()
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)

    if argv and argv[0] in GUI_WORDS:
        return launch_gui()

    # A bare invocation means "open the app", preserving the historical
    # behaviour. Without the desktop distribution installed there is nothing to
    # open, so show the CLI's help instead of a confusing "image is required".
    if not argv:
        if gui_is_available():
            return launch_gui()
        from .cli import main as cli_main

        return cli_main(["--help"])

    from .cli import main as cli_main

    return cli_main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
