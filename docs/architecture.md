# ziconvert Architecture

How the monorepo is put together, what each module owns, and the rules that
keep the layers honest.  Companion document: [enhancements.md](enhancements.md)
covers *what each enhancement does*; this covers *how it all fits together*.

---

## Layout

```
ziconvert/
├── core/                    # UI-free tracing engine (installable package: img2dxf)
│   ├── img2dxf/
│   │   ├── __init__.py      # public API surface
│   │   ├── params.py        # TraceParams dataclass + PRESETS
│   │   ├── pipeline.py      # run(): the stage graph, TraceResult
│   │   ├── preprocess.py    # decode, prepare, to_grayscale, binarize
│   │   ├── denoise.py       # bilateral / NLM / median / box
│   │   ├── morphology.py    # close+open on the binary mask
│   │   ├── thresholding.py  # otsu / adaptive / edge modes
│   │   ├── upscale.py       # super-resolution backends + honesty contract
│   │   ├── contours.py      # mask → Path (cv2.findContours + hierarchy)
│   │   ├── arcfit.py        # least-squares circle fit, sweep gating
│   │   ├── shape_fit.py     # contour → ideal circle/ellipse/rect
│   │   ├── vector_snap.py   # post-trace geometric cleanup (4 stages)
│   │   ├── straighten.py    # flatten structurally straight runs
│   │   ├── units.py         # pixels → millimetres
│   │   ├── kerf.py          # outward/inward offset compensation
│   │   ├── ordering.py      # nearest-neighbour path reordering, tiling
│   │   ├── transform.py     # rotate/flip/auto-levels
│   │   ├── export_dxf.py    # ezdxf document builder (LWPOLYLINE/CIRCLE/ARC)
│   │   ├── export_svg.py    # SVG writer
│   │   ├── cli.py           # argparse front-end, settings files
│   │   └── settings_io.py   # save/load TraceParams as JSON/TOML
│   ├── pyproject.toml
│   └── tests/               # 270+ tests, no network, no GUI
├── desktop/                 # Tkinter app; imports img2dxf, draws results
│   ├── main.py              # window, worker threads, live preview
│   ├── packaging/
│   │   └── release.py       # version bump + test gate + tag in one command
│   ├── pyproject.toml
│   └── tests/               # GUI smoke tests (skip if Tcl is broken)
├── web/
│   ├── backend/             # FastAPI wrapper around core
│   │   ├── main.py          # /health /presets /convert
│   │   └── tests/           # httpx TestClient contract suite
│   ├── frontend/            # Vite + React + TypeScript
│   │   └── src/
│   │       ├── api/convert.ts       # FormData POST, blob download, headers→meta
│   │       ├── components/          # FileUpload, SettingsPanel, ResultPreview
│   │       └── App.tsx              # state owner, layout
│   └── run.bat / run.sh     # launch both tiers
└── docs/
```

## The one-way dependency rule

```
desktop ──▶ core ◀── web/backend
              ▲
              └── web/frontend (via HTTP, never imports)
```

`core/` imports nothing from `desktop/` or `web/`.  Both UI tiers import
`img2dxf` and nothing else of each other's internals.  The frontend talks to
the backend only through `/api/*` fetches — it has no idea Python exists.

Consequence: everything testable in `core/tests/` runs without a display,
a browser, or a GUI toolkit.  The engine is usable as a library
(`python -c "import img2dxf"`), a CLI, a desktop app, and an HTTP service.

## The contract: TraceParams → TraceResult

Everything the user can influence is one frozen dataclass, `TraceParams`
(`core/img2dxf/params.py`).  No hidden globals, no ambient config.  The
presets in `PRESETS` are just `TraceParams` instances; a UI never knows
parameter names, it hands the engine a params object.

`run(image_rgb, params) -> TraceResult` returns:

| field | meaning |
|---|---|
| `paths` | list of `Path` (millimetre-space vertices, arcs, bulges, circles) |
| `bounds` | `Bounds` in mm, or `None` when nothing was traced |
| `path_count`, `vertex_count`, `arc_count` | headline stats |
| `sr_used` | which upscale backend actually ran (`"off"` … `"dnn"`) |
| `summary()` | one-line human string, mirrors what the UIs show |

Two rules the UIs rely on:

1. **Empty result is a normal outcome, not an error.**  `bounds is None`
   means the mask ended up empty; callers show "no paths found" guidance
   rather than crashing.
2. **`sr_used` tells the truth.**  It names the backend that *actually*
   produced the upscaled image.  If a neural backend was requested but the
   model files are missing, the engine degrades to Lanczos and reports
   `"lanczos"` — never the requested backend's name.

## Pipeline stage graph

`pipeline.run()` in execution order — every stage is a pure function of its
inputs plus params:

```
RGB image
  │ transform        rotate / flip / auto-levels
  │ resolve_detail   detail preset → upscale factor
  │ upscale          optional SR (factor > 1 only); returns (img, sr_used)
  │ pixels_per_mm    after upscale — mm scale is locked here
  │ prepare          RGBA→RGB, resize to target mm width
  │ grayscale + binarize   denoise (enh. 1) → threshold → morphology (enh. 2)
  │ trace_mask       contours + holes via cv2 hierarchy
  │ to_millimetres   pixel polyline → mm-space Path list
  │ straighten       collapse collinear runs
  │ vector_snap      enh. 5: circles → axis → right angles → merge
  │ kerf             offset paths; rebuilds Path objects (see below)
  │ shape_fit        enh. 3: snap to ideal primitives (post-kerf on purpose)
  │ fit_arcs         smooth runs → ARC/BULGE
  │ tile             copies × copies with spacing
  │ order            nearest-neighbour reordering
  ▼ bounds + TraceResult
```

Ordering is load-bearing:

- **vector_snap before kerf.**  Kerf offsetting constructs *fresh* `Path`
  objects (`kerf._rebuild`), which would drop the claimed
  `path.circles[index]` entries from the circle stage.  Claiming rings
  before kerf means they survive as `CIRCLE` entities.
- **shape_fit after kerf.**  Shape fitting replaces vertex sequences with
  ideal primitives; doing it before kerf would let the offset walk the raw
  staircase again.  After kerf, the ideal shape is what gets offset — and
  the offset of a circle is a circle.
- **tile before order.**  Ordering is nearest-neighbour travel minimisation;
  running it per-copy after tiling minimises the real cut path.

## The kerf-rebuilds-paths fact

`kerf.offset_paths` cannot offset a polyline in place — an outward offset of
a closed contour has a different vertex count.  It builds new `Path`
objects, so any annotation attached to the old ones (claimed circles,
bulge arcs) is lost unless it was claimed *before* the offset or re-derivable
after it.  This single fact dictates the vector_snap / shape_fit placement
above, and is why circle claims made by `shape_fit` land post-kerf by design.

## Layer notes

### core → CLI

`cli.params_from_args` folds flags onto a preset's `TraceParams` in one
explicit tuple of field names.  Adding a knob means: add the field to
`TraceParams`, the flag to the parser, the name to that tuple — and
`--save-settings` / settings files pick it up for free because they
serialise the dataclass, not a hand-written dict.

### desktop

`main.py` runs `run()` on a worker thread, keeps a cached preview image, and
renders paths with Tk canvas primitives.  It never mutates engine state;
progress and results come back through a queue.

`packaging/release.py` is the release automation: `python packaging/release.py 0.3.0`
bumps every version site (core pyproject, `__init__.__version__`, desktop
pyproject, README badge), runs the full test gate over `core/tests`,
`desktop/tests`, and `web/backend/tests`, then tags.  **API tests must live
in `web/backend/tests/`** or the gate will not find them — that path is
pinned in `TEST_PATHS`.

### web

`web/backend/main.py` is deliberately thin: validate → build `TraceParams`
(preset + toggles + optional tolerance overrides, `None` = keep preset
value) → `run()` → serialise.  No engine logic lives there.  Stats ride out
as `X-Path-Count` / `X-Vertex-Count` / `X-Arc-Count` / `X-Sr-Used` /
`X-Summary` headers next to the DXF attachment so the frontend can render a
result card without parsing the DXF.

`web/frontend` owns all interaction state.  `api/convert.ts` turns the
response into a Blob URL plus metadata; blank optional inputs are *omitted*
from the FormData so the backend's `None`-keeps-preset contract holds.

The Vite dev server proxies `/api` → `http://localhost:8000` (prefix
stripped), so in development the browser stays same-origin and no CORS
is exercised; the backend's permissive CORS exists for other local tooling.

## Testing layout

| suite | location | runs with |
|---|---|---|
| engine | `core/tests/` | no display, no network |
| CLI | `core/tests/test_cli.py` | tmp dirs, no network |
| desktop | `desktop/tests/` | skips cleanly if Tcl is unusable |
| web API | `web/backend/tests/` | httpx TestClient, no live server |

Everything runs offline from the repo root:

```
./.venv/Scripts/python.exe -m pytest core/tests desktop/tests web/backend/tests -q
```

Desktop GUI tests are auto-skipped when the machine's Tcl runtime is broken —
the skip is reported honestly by pytest rather than hidden.

## Adding an engine knob, end to end

The checklist that keeps all four surfaces in sync:

1. `core/img2dxf/params.py` — add the field (with a safe default).
2. `core/img2dxf/pipeline.py` — honour it at the right stage.
3. `core/img2dxf/cli.py` — add the flag + tuple entry; core tests.
4. `web/backend/main.py` — add the `Form` field (optional scalar → `None`
   keeps preset) + validation + any new `X-` header; backend tests.
5. `web/frontend/src/api/convert.ts` — extend `ConvertSettings`; omit
   undefined optional fields from the FormData.
6. `web/frontend/src/components/SettingsPanel.tsx` — surface it in the UI.
7. `docs/enhancements.md` — document it if it changes tool behaviour.
