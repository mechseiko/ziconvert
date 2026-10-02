r"""Build the standalone desktop executable.

    python desktop\packaging\build.py

Leaves `desktop/dist/img2dxf.exe`, which runs on a machine with no Python
installed at all. That is the point: the tool should be reachable by
double-click from the workshop PC, not only from a checkout with a virtualenv
activated.

Run it from anywhere. Every path here is derived from this file's own location,
so the script does not care what the current directory is -- a build that only
works from one directory is a build that fails on the CI runner.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent          # desktop/packaging
DESKTOP = HERE.parent                           # desktop/
REPO = DESKTOP.parent                           # the monorepo root
SPEC = HERE / "img2dxf.spec"
DIST = DESKTOP / "dist"
WORK = DESKTOP / "build"
EXE = DIST / "img2dxf.exe"


def main() -> int:
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        print(
            "PyInstaller is not installed. Run:\n"
            "  python -m pip install -e ./desktop[dev]\n"
            "or, plainly:\n"
            "  python -m pip install pyinstaller",
            file=sys.stderr,
        )
        return 1

    for required in (SPEC, HERE / "entry.py", REPO / "core" / "img2dxf"):
        if not required.exists():
            print(f"cannot build: {required} is missing", file=sys.stderr)
            return 1

    # A stale build directory is the usual cause of a build that succeeds but
    # ships the previous version's code.
    for stale in (WORK, DIST):
        shutil.rmtree(stale, ignore_errors=True)

    print(f"building from {DESKTOP}")
    result = subprocess.run(
        [
            sys.executable, "-m", "PyInstaller",
            str(SPEC),
            "--noconfirm",
            "--clean",
            "--distpath", str(DIST),
            "--workpath", str(WORK),
        ],
        cwd=DESKTOP,
    )
    if result.returncode != 0:
        return result.returncode

    if not EXE.is_file():
        print("the build reported success but produced no exe", file=sys.stderr)
        return 1

    print(f"\nbuilt {EXE}  ({EXE.stat().st_size / 1_000_000:.0f} MB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
