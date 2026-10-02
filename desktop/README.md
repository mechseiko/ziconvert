# zicengine desktop — `img2dxf_gui`

The Tkinter app. It is a front end and nothing more: every pixel of image
processing happens in [`../core`](../core), which this package imports and
never modifies.

## Run it from a checkout

```bash
python desktop/app.py        # or:  python -m img2dxf
```

`desktop/app.py` puts `desktop/` and `core/` at the front of `sys.path` before
importing anything, so a working tree always wins over a stale install in
`site-packages`. That is the whole reason the launcher exists — without it,
editing `core/` and launching the GUI can silently run last week's engine.

## Install it

```bash
pip install -e ./core -e ./desktop
img2dxf-desktop
```

Optional extras:

```bash
pip install -e "./desktop[dnd]"    # drag-and-drop onto the window
pip install -e "./desktop[dev]"    # + pytest and PyInstaller
```

The app degrades gracefully without `tkinterdnd2`; the Open button always
works.

## Build the .exe

```bash
python desktop/packaging/build.py
```

Leaves `desktop/dist/img2dxf.exe`, one file, no console window, runnable on a
machine with no Python installed. PyInstaller is driven from `desktop/` with
`core/` and `desktop/` both on `pathex`, which is what lets the frozen build
see the engine without it being installed.

## Cut a release

```bash
python desktop/packaging/release.py 0.3.0 --dry-run   # checks and tests only
python desktop/packaging/release.py 0.3.0             # bump, build, tag, publish
```

Needs the GitHub CLI, logged in once with `gh auth login`. The script refuses
to start from a dirty tree or a branch other than `main`, bumps the version in
all three places it is written (`core/pyproject.toml`,
`core/img2dxf/__init__.py`, the root README badge), and only then builds,
commits, tags, pushes and creates the release with the exe attached. A release
whose badge disagrees with its tag is a release nobody can trust, so those move
together or not at all.

## Layout

| File | Responsibility |
| --- | --- |
| `app.py` | checkout launcher: fix `sys.path`, then start the GUI |
| `img2dxf_gui/app.py` | window, layout, event wiring, the convert button |
| `img2dxf_gui/controls.py` | building each widget and binding it to a param field |
| `img2dxf_gui/preview.py` | drawing masks and traced paths on a canvas |
| `img2dxf_gui/worker.py` | running the engine on a thread so the window stays alive |
| `img2dxf_gui/recent.py` | remembering recent files |
| `img2dxf_gui/tooltips.py` | hover help for every control |
| `packaging/` | PyInstaller spec, build script, release script |
| `tests/test_gui.py` | headless checks: the app imports and maps params correctly |

## Tests

```bash
pytest desktop/tests -q      # from the repo root; pythonpath is set in the root pyproject.toml
```

These construct widgets but never call `mainloop()`, so they run on a build
agent with no display. Anything that would need a real screen is left to the
end-to-end check in `../docs/architecture.md`.
