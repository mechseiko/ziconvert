# zicengine core — `img2dxf`

The tracing engine. Images in, laser-ready vector files out. No windows, no
HTTP server, no browser: this package knows nothing about how it is being
driven, and that is what lets the desktop app and the web app share it.

```
image bytes ──► decode ──► upscale ──► denoise ──► binarize ──► morphology
                                                                    │
     DXF / SVG bytes ◄── export ◄── order ◄── tile ◄── arcs ◄── contours
```

## Install

```bash
pip install -e ./core            # engine only
pip install -e "./core[sr]"      # + OpenCV contrib, enables AI super-resolution
```

`opencv-contrib-python-headless` provides everything `opencv-python-headless`
does plus the `dnn_superres` module. Install one or the other, never both —
they both ship a module named `cv2`, and whichever lands last shadows the
other.

## Use

The stable public API is two functions. Everything else in the package is an
implementation detail that may move.

```python
from img2dxf import trace, TraceParams

params = TraceParams(width_mm=80, preset="Logo / clipart", denoise_mode="bilateral")
out = trace("logo.png", params)

out.dxf        # bytes — write straight to a socket or a file
out.svg        # bytes — same geometry, for previewing in a browser
out.result     # TraceResult: paths, masks, bounds, vertex counts
out.warnings   # things the engine noticed but could work around
```

From raw bytes instead of a path:

```python
out = img2dxf.trace_encoded(request_body, params)
```

One-shot helpers, when you only want a file on disk:

```python
img2dxf.trace_to_dxf("in.png", "out.dxf", params)
img2dxf.trace_to_svg("in.png", "out.svg", params)
```

## Command line

```bash
python -m img2dxf logo.png -o logo.dxf --width 80 --denoise bilateral
python -m img2dxf --list-presets
python -m img2dxf            # no arguments: launches the desktop app if installed
```

`python -m img2dxf` with no arguments preserves the historical behaviour of
opening the GUI. It does so by *probing* for the optional `img2dxf_gui`
package — core never imports it, never depends on it, and reports a useful
install hint when it is missing. That keeps the dependency arrow pointing one
way (`desktop → core`) without costing the desktop user anything.

## The five enhancements

All five are engine features, switched by `TraceParams` fields, so every front
end gets them for free.

| Field group | What it does | Default |
| --- | --- | --- |
| `denoise_mode` | `median`, `bilateral`, `nlm` or `off` before thresholding | `median` |
| `morph_kernel`, `morph_iterations`, `close_px`, `open_px` | close gaps then open speckle, with a chosen structuring element | ellipse, off |
| `shape_fit`, `shape_fit_circle/ellipse/rect` | snap an obviously-round or obviously-square contour to the ideal primitive | on |
| `sr_backend`, `sr_model` | AI super-resolution before tracing (`esrgan`, `dnn`, `lanczos`, `cubic`) | off |
| `vector_snap`, `snap_axis_deg`, `snap_right_angle_deg` | snap near-horizontal to horizontal, near-90° to exactly 90° | on |

`docs/enhancements.md` in the repo root explains what each one fixes and how to
tell whether it helped.

## Layout

| Module | Responsibility |
| --- | --- |
| `api.py` | the stable public surface: `trace`, `trace_encoded`, `TraceOutput` |
| `params.py` | every knob, its type, its clamp, and the four presets |
| `pipeline.py` | the fixed order the stages run in |
| `preprocess.py` | levels, gamma, denoise, sharpen, blur, binarize, morphology |
| `upscale.py` | super-resolution backends behind one interface |
| `detail.py` | how much to supersample, and doing it |
| `trace.py` | mask → contours → paths, with hole detection |
| `shape_fit.py` | contour → circle / ellipse / rectangle |
| `straighten.py` | flatten runs that were meant to be straight |
| `vector_snap.py` | axis, coordinate, right-angle and circle snapping |
| `kerf.py` | tool-radius compensation |
| `arcfit.py` | points → DXF bulges |
| `tabs.py`, `tile.py`, `order.py` | bridges, repeats, cutting order |
| `export_dxf.py`, `export_svg.py` | writers |
| `geometry.py` | `Path`, `Bounds`, pixel ↔ millimetre |
| `settings.py` | persist a parameter set to JSON |
| `calibrate.py` | measure a printed part to find your real px/mm |
| `cli.py` | argparse front end |

## Tests

```bash
pytest core/tests -q          # from the repo root
```

The suites build their inputs as synthetic images in `conftest.py`, so the repo
carries no binary fixtures and a test cannot rot because a sample file moved.

## The one rule

**Nothing in `core/` may import from `desktop/` or `web/`.** Dependencies flow
UI → core and never back. The engine has its own `pyproject.toml` precisely so
that this is checkable: `pip install ./core` on a machine with no tkinter and
no FastAPI must still import, convert and test cleanly. If that ever stops
being true, the monorepo has become a liability.
