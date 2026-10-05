# The five tracing enhancements

ziconvert began as an enhancement of [dxfconvertor](https://github.com/aryansaraogi/dxfconvertor).
Five capabilities were added to the tracing engine, each designed to survive
contact with real scans: noisy phone photos, crooked scans, JPEG artefacts and
anti-aliased screenshots. This document explains what each one does, why it
exists, and how to use it. Everything here lives in `core/img2dxf/` with no UI
dependencies — the desktop app and the web UI are thin layers over the same
engine.

---

## 1. Denoising before thresholding (`preprocess.py`)

**The problem.** Thresholding is a cliff: every pixel falls on one side or the
other, so a sensor-noise speckle in a flat white area becomes a genuine hole in
the DXF, and JPEG mosquito noise along an edge becomes a fringe of ghost
outlines. Cleaning up *after* thresholding is too late — the noise is already
geometry.

**The fix.** Denoise runs on the grayscale image, before the cliff. Four modes
(`--denoise N --denoise-mode MODE`):

| Mode | Filter | Best for |
|---|---|---|
| `median` | median filter | salt-and-pepper speckle; cheapest |
| `bilateral` | cv2.bilateralFilter | photos: flattens surfaces, keeps edges crisp |
| `nlm` | fastNlMeansDenoising | heavy noise; slowest, strongest |
| `off` | — | clean synthetic input |

`bilateral` is the desktop and web default because photographs are the common
case. Strength (`N`) is the filter's own parameter, not a magic percentage.

## 2. Morphological cleanup of the mask (`preprocess.py`)

**The problem.** Even a noise-free scan has faults thresholding cannot fix: a
hairline gap in an outline where the scanner light caught a fold, a one-pixel
island left by a shadow. The tracer faithfully turns both into path defects.

**The fix.** After binarization, `--close N` dilates-then-erodes the mask to
seal gaps narrower than `N` pixels, and `--open N` erodes-then-dilates to
dissolve specks smaller than `N` pixels. Both are no-ops at 0 (the default for
`open`; `close` defaults to 0 too — the presets turn them on where they help).
Kernel shape (`ellipse`/`rect`/`cross`) and iteration count are exposed for the
rare stubborn case.

Order matters and is fixed: close runs before open, because sealing a gap
first stops the open from eating a thin shape that the gap had broken into
pieces.

## 3. Contour-to-primitive snapping (`shape_fit.py`)

**The problem.** A photographed circle traces as a few hundred short segments
with wobble baked in. The file bloats, controllers stutter, and the burn shows
faceting. The circle was drawn as a circle — the trace should say so.

**The fix.** After tracing (and after kerf compensation, so it judges the path
the machine will actually follow), every closed ring is tested against three
ideal primitives: circle, ellipse and rectangle. A ring is replaced only when
*every* point — vertices and segment midpoints — sits within
`--shape-fit-tol` (default 0.1 mm, derived from resolution when 0) of the
primitive. The replacement is exact geometry: a true `CIRCLE`/`ELLIPSE` entity
or a four-corner rectangle, so downstream CAD sees what was drawn, not what
the camera saw.

Guards against false positives:

- an octagon's side midpoints sit 7.6 % of its radius off any circle — refused;
- a sparse-sampled rectangle (four corners only) is geometrically indistinguishable
  from an ellipse *to its corners*, so the fitter resamples the perimeter before
  judging ellipticity;
- irregular polygons fail all three tests and keep their traced points;
- disable entirely with `--no-shape-fit`.

## 4. Optional super-resolution before tracing (`upscale.py`)

**The problem.** A 300 px logo traced at "80 mm wide" has ~4 px per mm. Every
downstream judgement — simplification tolerance, arc fitting, kerf offsets —
is quantising a staircase that coarse. Interpolation adds pixels but no
information; a neural upscaler adds *plausible* information, which is exactly
what a tracer can use.

**The fix.** `--sr BACKEND [--sr-model FILE]` upscales before tracing, with the
detail factor deciding the target size. Backends, in fallback order for
`auto`:

1. **esrgan** — Real-ESRGAN via the optional `ncnn` runtime (`.param` + `.bin`
   files, chosen with `--sr-model`);
2. **dnn** — OpenCV's `dnn_superres` models (FSRCNN/ESPCN/LAPSRN/EDSR, `.pb`
   files, e.g. `--sr-model FSRCNN_x2.pb`);
3. **lanczos** — the sharpest classical resize;
4. **cubic** — plain bicubic.

Model files live in `~/.img2dxf/models/` (or any path passed to `--sr-model`).
Nothing is ever downloaded at run time.

**The contract that matters:** the report never lies. `sr=dnn` in the summary
line means the dnn model actually ran; if the asked-for backend could not
(honestly: no model file installed), the run degrades to lanczos and says
`sr=lanczos`. A user debugging a blurry trace is never told a neural network
was involved when it was not. The default is `off` — the engine never silently
changes resolution.

## 5. Post-tracing vector snap (`vector_snap.py`)

**The problem.** Tracing reproduces what the pixels say, and the pixels almost
never say what the artwork meant. A stem drawn perfectly vertical arrives
tilted by 0.02°; two features meant to share an edge arrive 0.02 mm apart; a
corner meant to be square arrives at 89.96°. Each error is far below any
machine's repeatability — but the machine reproduces every one of them,
because the path says so.

**The fix.** Four regularisations, in a deliberate order (each protects the
one after):

1. **Near-circles** are claimed first (`--snap-circle`, default 0.1 mm). Every
   later stage would mangle a curve — forcing its segments onto the axes
   staircases it — and a claimed ring exports as a single CIRCLE entity, so
   its points stop mattering. This is deliberately looser and earlier than
   shape_fit's judgement.
2. **Axis snap** (`--snap-axis-deg`, default 0.75°): segments within tolerance
   of horizontal or vertical become *exactly* so, both endpoints moving to the
   shared mean. Sub-minimum segments (`--snap-min-segment`, 0.05 mm) are
   skipped: noise has no meaningful angle.
3. **Right angles** (`--snap-right-angle-deg`, default 1.5°): the corner moves
   onto the circle whose diameter is the chord across it. By the converse of
   Thales' theorem, that circle is exactly the locus of corners seeing the
   chord at 90°, so its nearest point is the smallest legal move. Runs after
   axis snap because axis-aligned neighbours are already exactly perpendicular.
4. **Global merge** (`--snap-merge`, default 0.05 mm): near-equal x coordinates
   across the whole drawing collapse onto one value, then y likewise. Pooled
   globally, so two stems meant to line up do even when no single shape
   contains both. It runs last because it is the coarsest judgement — and
   because axis snapping sets both endpoints of a segment to one identical
   float, which a merge cluster cannot pull apart.

The master switch `--no-vector-snap` turns the whole pass off.

---

## How they compose

The full pipeline, in the order the stages run:

```
load → transform (rotate/crop) → super-resolution → px/mm → denoise
     → binarize → morphology → trace → straighten → vector snap
     → kerf → shape fit → arc fit → tile → order → export
```

Two ordering decisions are worth knowing:

- **Vector snap runs before kerf.** A parallel offset preserves straightness
  and squareness, so compensating afterwards costs nothing. And kerf rebuilds
  every path from raw rings — running the snap after it would throw the
  circle claims away.
- **Shape fit runs after kerf.** It must judge the geometry the machine will
  actually cut, and the arcs it enables describe the snapped primitive rather
  than the pixel staircase.

## Testing

Every enhancement ships with its own suite under `core/tests/`
(`test_preprocess.py`, `test_shape_fit.py`, `test_upscale.py`,
`test_vector_snap.py`, `test_cli.py`), plus the API contract tests in
`web/backend/tests/`. The guiding rule: a test measuring one feature pins the
other features *off*, so a passing suite means each behaviour was observed in
isolation.
