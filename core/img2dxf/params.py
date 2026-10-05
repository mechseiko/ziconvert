"""Every knob the pipeline understands, in one place.

The GUI, the CLI and the tests all build a :class:`TraceParams` and hand it to
:func:`img2dxf.pipeline.run`, so there is exactly one code path to reason about.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Literal

BinarizeMode = Literal["otsu", "fixed", "adaptive", "posterize", "edges"]
KerfSide = Literal["none", "outside", "inside"]
SizeMode = Literal["fit", "dpi"]
Origin = Literal["bottom-left", "center"]

#: Which filter removes noise before thresholding. ``median`` is the classic
#: salt-and-pepper killer; ``bilateral`` smooths flat areas while keeping edges
#: crisp, which is what stops an oval coming out jagged; ``nlm`` is the strongest
#: and the slowest, and suits photographs.
DenoiseMode = Literal["off", "median", "bilateral", "nlm"]

#: Structuring element for morphological closing and opening. An ellipse rounds
#: corners the least, a rectangle preserves them, a cross only joins along the
#: axes and so never thickens a diagonal stroke.
MorphKernel = Literal["ellipse", "rect", "cross"]

#: Super-resolution backends, tried in this order by ``"auto"``. ``off`` means
#: the classical cubic supersample the engine has always used, which is free;
#: the others trade seconds of compute for detail that was never in the file.
SrBackend = Literal["auto", "esrgan", "dnn", "lanczos", "cubic", "off"]

#: Primitives a contour may be snapped to.
PrimitiveKind = Literal["circle", "ellipse", "rect"]

#: DXF flavours offered in the UI, newest first. R12 is the compatibility
#: fallback for older Ruida/RDWorks stacks.
DXF_VERSIONS: tuple[str, ...] = ("R2010", "R2000", "R12")

#: The runtime vocabulary of each ``Literal`` field above. Kept beside the
#: aliases rather than derived from them so a CLI ``choices=`` list, a
#: :meth:`TraceParams.normalized` clamp and the type checker all read from the
#: same source of truth and cannot drift apart.
KERF_SIDES: tuple[str, ...] = ("none", "outside", "inside")
DENOISE_MODES: tuple[str, ...] = ("off", "median", "bilateral", "nlm")
MORPH_KERNELS: tuple[str, ...] = ("ellipse", "rect", "cross")
SR_BACKENDS: tuple[str, ...] = ("auto", "esrgan", "dnn", "lanczos", "cubic", "off")
PRIMITIVE_KINDS: tuple[str, ...] = ("circle", "ellipse", "rect")

#: The strength each denoise mode is worth using at when a caller switches it on
#: without picking a number. Radii are not interchangeable between filters —
#: a median of 9 removes whole letters, a bilateral of 3 does nothing — so the
#: default belongs to the mode, not to the field.
DEFAULT_DENOISE: dict[str, int] = {
    "off": 0,
    "median": 3,
    "bilateral": 9,
    "nlm": 3,
}


@dataclass(frozen=True, slots=True)
class TraceParams:
    """Parameters for one image -> DXF conversion.

    Lengths the user types are in millimetres; anything in pixels is internal.
    """

    # --- source framing ------------------------------------------------
    rotate_deg: float = 0.0
    """Rotation applied before anything else. Straightens a crooked scan."""

    crop: tuple[float, float, float, float] | None = None
    """``(left, top, right, bottom)`` as fractions of the rotated image."""

    # --- resolution ----------------------------------------------------
    detail: int = 0
    """Supersampling factor applied before thresholding. 0 picks one.

    Thresholding quantises every outline to the pixel grid, and that — not the
    simplification tolerance — is what limits how clean a traced edge can be.
    Tracing an upscaled image lifts that ceiling: on a small logo it cuts the
    error against the original artwork by roughly five times.
    """

    sr_backend: SrBackend = "off"
    """Super-resolution used for that upscaling. ``"off"`` is the default.

    Deliberately opt-in. The classical cubic resize is free and instant, and
    every enhancement here is a judgement about what the artwork meant; a
    neural network inventing detail that was never in the file is a different
    kind of judgement, and one the operator should choose to make. Set it to
    ``"auto"`` to use the best backend that is installed.
    """

    sr_model: str | None = None
    """Path to a model file, for the backends that need one.

    ``"dnn"`` reads an FSRCNN or ESPCN ``.pb``; ``"esrgan"`` reads a
    Real-ESRGAN ``.param``/``.bin`` pair. Never downloaded behind your back:
    with no path given, ``"dnn"`` is only used if a model already sits in
    ``~/.img2dxf/models/``.
    """

    # --- image adjustments ---------------------------------------------
    auto_levels: bool = False
    """Stretch the tonal range to fill 0-255, ignoring outlier pixels."""

    brightness: int = 0
    """Added to every pixel, -100 to 100."""

    contrast: float = 1.0
    """Multiplier about mid-grey. 1.0 leaves the image alone."""

    gamma: float = 1.0
    """Below 1 darkens midtones, above 1 lightens them."""

    sharpen: float = 0.0
    """Unsharp-mask strength. Pulls against `blur`; use one or the other."""

    # --- preprocessing -------------------------------------------------
    invert: bool = False
    """Trace the light regions instead of the dark ones."""

    blur: int = 0
    """Gaussian blur radius in pixels. 0 disables. Rounded up to an odd kernel."""

    denoise: int = 0
    """How hard to denoise, in the units the chosen mode uses. 0 disables.

    For ``median`` this is the filter radius in pixels. For ``bilateral`` it is
    the neighbourhood diameter. For ``nlm`` it scales the filtering strength.
    See :data:`DEFAULT_DENOISE` for a sensible value per mode.
    """

    denoise_mode: DenoiseMode = "median"
    """Which filter :attr:`denoise` drives.

    ``median`` replaces a pixel with the middle of its neighbours, which deletes
    isolated specks outright and is the right answer for scanner grain. It also
    rounds corners and chews thin strokes. ``bilateral`` averages only
    neighbours of a similar brightness, so flat areas go smooth while edges
    stay put — that is what turns a jagged oval into a curve. ``nlm`` compares
    whole patches rather than single pixels and is stronger still, at a cost.
    """

    bilateral_sigma_color: float = 75.0
    """How different in brightness a neighbour may be and still count.

    Small keeps only near-identical pixels, preserving edges but doing little;
    large smooths across them. 75 is the usual starting point.
    """

    bilateral_sigma_space: float = 75.0
    """How far away a neighbour may be and still count, in pixels."""

    nlm_h: float = 10.0
    """Non-local-means filtering strength. Higher removes more, and detail."""

    nlm_template_window: int = 7
    """Patch size compared between pixels. Forced odd."""

    nlm_search_window: int = 21
    """Area searched for matching patches. Forced odd. The main cost driver."""

    # --- binarization --------------------------------------------------
    mode: BinarizeMode = "otsu"
    threshold: int = 128
    """Cut level for ``mode="fixed"``, 0-255."""

    adaptive_block: int = 31
    """Neighbourhood size for ``mode="adaptive"``. Forced odd and >= 3."""

    adaptive_c: int = 5
    """Constant subtracted from the local mean for ``mode="adaptive"``."""

    levels: int = 3
    """Tone-level count for ``mode="posterize"``, 2-8. Each gets its own layer."""

    canny_low: int = 80
    canny_high: int = 160
    edge_dilate: int = 1
    """Pixels of dilation applied to Canny edges before tracing."""

    # --- morphology ----------------------------------------------------
    close_px: int = 0
    """Morphological closing radius: bridges hairline gaps in the mask.

    This is the control that fixes an oval which has lost quality. A traced
    curve arrives as a staircase with hairline notches along it; closing fills
    the notches from both sides, and what is left is the smooth outline the
    artwork meant.
    """

    open_px: int = 0
    """Morphological opening radius: removes isolated specks from the mask."""

    morph_kernel: MorphKernel = "ellipse"
    """Structuring element for closing and opening.

    A circle traced with a square kernel comes out with flats on it, which is
    the most visible way to get morphology wrong; the ellipse is the default
    for that reason. Use ``rect`` when the artwork is genuinely rectilinear and
    you would rather keep corners sharp, and ``cross`` when thin diagonal
    strokes are being thickened by the other two.
    """

    morph_iterations: int = 1
    """How many times to apply each operation.

    Two passes of a radius-1 kernel reach further than one pass of a radius-2
    one, and do it while following the outline rather than stamping a big disc
    over it — usually the better trade for closing a jagged curve.
    """

    # --- vectorization -------------------------------------------------
    simplify_mm: float = 0.05
    """Douglas-Peucker tolerance. Larger = fewer vertices, blockier curves."""

    smooth: int = 0
    """Corner-aware smoothing passes, 0-3. Softens staircase edges."""

    corner_deg: float = 40.0
    """Turns sharper than this are corners, and smoothing leaves them alone."""

    straighten_mm: float = 0.15
    """Flatten runs that stray less than this from their own chord. 0 disables.

    Deliberately looser than `simplify_mm`: it is a separate judgement that a
    run is structurally a straight line, not a tighter accuracy budget.
    """

    min_run_mm: float = 2.0
    """Only runs at least this long are considered for straightening."""

    min_area_mm2: float = 0.5
    """Drop contours smaller than this. The despeckle control."""

    keep_holes: bool = True
    """Emit inner contours, so the counter of an 'O' is not filled in."""

    # --- primitive snapping --------------------------------------------
    shape_fit: bool = True
    """Snap a contour to the ideal primitive when it obviously is one.

    A circle that was drawn as a circle should come out as a CIRCLE entity, not
    as 200 short segments that only approximate one. Fitting the primitive and
    checking every point against it is the difference between "close" and
    "right", and it is the reason a traced washer holes-out concentrically.
    """

    shape_fit_circle: bool = True
    """Allow snapping to a circle. The result is written as a CIRCLE entity."""

    shape_fit_ellipse: bool = True
    """Allow snapping to an ellipse, for ovals and for circles seen at an angle."""

    shape_fit_rect: bool = True
    """Allow snapping to a rectangle, axis-aligned or rotated."""

    shape_fit_tol_mm: float = 0.0
    """How far a point may sit from the primitive and still count as on it.

    0 means derive it, the same way arc fitting does: the looser of
    :attr:`simplify_mm` and one *source* pixel. Deriving is the right default
    because a traced outline departs from any ideal shape by about half a pixel
    no matter how clean the artwork was, so a tolerance tighter than that
    rejects every real primitive.
    """

    shape_fit_min_vertices: int = 8
    """Do not try to fit a primitive to a ring with fewer vertices than this.

    Five points always fit an ellipse exactly, so a pentagon would be reported
    as one. Requiring a few more than the model has parameters is what makes
    the deviation measurement mean anything.
    """

    # --- vector snapping -----------------------------------------------
    vector_snap: bool = True
    """Regularise the traced geometry on the way out.

    The output-side counterpart of :attr:`shape_fit`. Where that asks "is this
    contour a primitive?", this asks "was this line meant to be exactly
    horizontal, and this corner exactly 90 degrees?" — and makes it so, within
    a tolerance measured in fractions of a pixel.
    """

    snap_axis_deg: float = 0.75
    """Segments within this many degrees of an axis become exactly on it."""

    snap_merge_mm: float = 0.05
    """Coordinates closer together than this collapse onto one value.

    Applied across the whole drawing, not just within a shape, so two stems
    that were meant to line up actually do. 0 disables the merge and leaves
    snapping per-segment only.
    """

    snap_right_angle_deg: float = 1.5
    """Corners within this many degrees of 90 are made exactly 90."""

    snap_circle_mm: float = 0.1
    """Snap tolerance for near-circular rings found at this stage, in mm.

    Separate from :attr:`shape_fit_tol_mm` on purpose: snapping runs before kerf
    compensation and arc fitting, so it is a looser, earlier judgement.
    """

    snap_min_segment_mm: float = 0.05
    """Ignore segments shorter than this; they are noise, not edges."""

    # --- sizing --------------------------------------------------------
    size_mode: SizeMode = "fit"
    width_mm: float = 100.0
    """Target width for ``size_mode="fit"``. Height follows the aspect ratio."""

    height_mm: float | None = None
    """If set, fit to this height instead and let width follow."""

    dpi: float = 96.0
    """Pixels per inch for ``size_mode="dpi"``."""

    origin: Origin = "bottom-left"

    # --- machine compensation ------------------------------------------
    kerf_mm: float = 0.0
    """Beam width. Paths are offset by half of it; 0 disables."""

    kerf_side: KerfSide = "none"
    """``outside`` keeps the part's size, ``inside`` keeps the hole's."""

    fit_arcs: bool = True
    """Replace circular runs with true arcs and circles."""

    tab_count: int = 0
    """Uncut bridges left in each closed path, so parts stay in the sheet."""

    tab_mm: float = 0.5
    """Width of each bridge."""

    optimize_order: bool = True
    """Reorder paths so the head travels less. Geometry is unchanged."""

    # --- layout --------------------------------------------------------
    copies_x: int = 1
    copies_y: int = 1
    """Grid of copies to lay out, for filling a sheet in one job."""

    tile_gap_mm: float = 2.0
    """Space between tiled copies."""

    bed_width_mm: float = 0.0
    bed_height_mm: float = 0.0
    """Machine bed size. 0 means no bed configured, so no fit check."""

    # --- output --------------------------------------------------------
    dxf_version: str = "R2010"
    layer_name: str = "CUT"

    @property
    def straighten_enabled(self) -> bool:
        return self.straighten_mm > 0 and self.min_run_mm > 0

    @property
    def tabs_enabled(self) -> bool:
        """Tabs need both a count and a width to do anything."""
        return self.tab_count > 0 and self.tab_mm > 0

    @property
    def has_bed(self) -> bool:
        return self.bed_width_mm > 0 and self.bed_height_mm > 0

    @property
    def denoise_enabled(self) -> bool:
        """Whether a denoise pass will actually run.

        Both halves are needed: a mode with no strength is a no-op, and a
        strength with the mode switched off is a slider the user turned down.
        Reporting the truth here is what lets a UI grey out the controls that
        follow from it instead of implying work that will not happen.
        """
        return self.denoise_mode != "off" and self.denoise > 0

    @property
    def morphology_enabled(self) -> bool:
        return bool(self.close_px or self.open_px)

    @property
    def snap_enabled(self) -> bool:
        """Whether any part of the vector-snap pass has something to do."""
        return self.vector_snap and (
            self.snap_axis_deg > 0
            or self.snap_merge_mm > 0
            or self.snap_right_angle_deg > 0
            or self.snap_circle_mm > 0
        )

    @property
    def sr_enabled(self) -> bool:
        """Whether super-resolution was asked for at all."""
        return self.sr_backend not in ("off", "")

    def with_denoise(self, enabled: bool) -> "TraceParams":
        """Return these parameters with denoising switched on or off.

        Switching on picks the strength that suits the mode rather than a
        number that suits a different filter, which is the mistake a boolean
        control makes when it just sets a radius.
        """
        if not enabled:
            return replace(self, denoise=0)
        if self.denoise > 0:
            return self
        return replace(self, denoise=DEFAULT_DENOISE.get(self.denoise_mode, 3))

    def with_morphology(self, enabled: bool) -> "TraceParams":
        """Return these parameters with the cleanup passes on or off.

        Switching on gives a one-pixel close, which is the pass that repairs a
        jagged outline; opening is left alone because it removes material, and
        a boolean labelled "cleanup" should not silently delete thin strokes
        the operator did not ask it to.
        """
        if not enabled:
            return replace(self, close_px=0, open_px=0)
        if self.morphology_enabled:
            return self
        return replace(self, close_px=1)

    def normalized(self) -> "TraceParams":
        """Clamp every field into the range the pipeline can actually use.

        Called once at the top of :func:`img2dxf.pipeline.run` so downstream
        code never has to defend against a nonsense slider value.
        """
        return replace(
            self,
            rotate_deg=float(self.rotate_deg) % 360.0,
            crop=_clean_box(self.crop),
            kerf_mm=max(0.0, float(self.kerf_mm)),
            brightness=_clamp(int(self.brightness), -100, 100),
            contrast=max(0.1, min(4.0, float(self.contrast))),
            gamma=max(0.1, min(4.0, float(self.gamma))),
            sharpen=max(0.0, min(3.0, float(self.sharpen))),
            tab_count=_clamp(int(self.tab_count), 0, 24),
            tab_mm=max(0.0, float(self.tab_mm)),
            copies_x=_clamp(int(self.copies_x), 1, 50),
            copies_y=_clamp(int(self.copies_y), 1, 50),
            tile_gap_mm=max(0.0, float(self.tile_gap_mm)),
            bed_width_mm=max(0.0, float(self.bed_width_mm)),
            bed_height_mm=max(0.0, float(self.bed_height_mm)),
            kerf_side=_one_of(self.kerf_side, KERF_SIDES, "none"),
            blur=max(0, int(self.blur)),
            denoise=_clamp(int(self.denoise), 0, 51),
            denoise_mode=_one_of(self.denoise_mode, DENOISE_MODES, "median"),
            bilateral_sigma_color=max(1.0, min(500.0, float(self.bilateral_sigma_color))),
            bilateral_sigma_space=max(1.0, min(500.0, float(self.bilateral_sigma_space))),
            nlm_h=max(0.1, min(100.0, float(self.nlm_h))),
            nlm_template_window=_odd_at_least(int(self.nlm_template_window), 3),
            nlm_search_window=_odd_at_least(int(self.nlm_search_window), 5),
            threshold=_clamp(int(self.threshold), 0, 255),
            adaptive_block=_odd_at_least(int(self.adaptive_block), 3),
            adaptive_c=_clamp(int(self.adaptive_c), -50, 50),
            levels=_clamp(int(self.levels), 2, 8),
            canny_low=_clamp(int(self.canny_low), 0, 255),
            canny_high=_clamp(int(self.canny_high), 0, 255),
            edge_dilate=_clamp(int(self.edge_dilate), 0, 20),
            close_px=_clamp(int(self.close_px), 0, 50),
            open_px=_clamp(int(self.open_px), 0, 50),
            morph_kernel=_one_of(self.morph_kernel, MORPH_KERNELS, "ellipse"),
            morph_iterations=_clamp(int(self.morph_iterations), 1, 10),
            detail=_clamp(int(self.detail), 0, 4),
            sr_backend=_one_of(self.sr_backend, SR_BACKENDS, "off"),
            sr_model=(str(self.sr_model) if self.sr_model else None),
            corner_deg=max(0.0, min(180.0, float(self.corner_deg))),
            straighten_mm=max(0.0, float(self.straighten_mm)),
            min_run_mm=max(0.0, float(self.min_run_mm)),
            simplify_mm=max(0.0, float(self.simplify_mm)),
            smooth=_clamp(int(self.smooth), 0, 3),
            min_area_mm2=max(0.0, float(self.min_area_mm2)),
            shape_fit_tol_mm=max(0.0, float(self.shape_fit_tol_mm)),
            shape_fit_min_vertices=_clamp(int(self.shape_fit_min_vertices), 4, 64),
            snap_axis_deg=max(0.0, min(15.0, float(self.snap_axis_deg))),
            snap_merge_mm=max(0.0, float(self.snap_merge_mm)),
            snap_right_angle_deg=max(0.0, min(15.0, float(self.snap_right_angle_deg))),
            snap_circle_mm=max(0.0, float(self.snap_circle_mm)),
            snap_min_segment_mm=max(0.0, float(self.snap_min_segment_mm)),
            width_mm=max(0.1, float(self.width_mm)),
            dpi=max(1.0, float(self.dpi)),
            dxf_version=_one_of(self.dxf_version, DXF_VERSIONS, "R2010"),
            layer_name=str(self.layer_name or "CUT"),
        )


def _one_of(value, allowed: tuple[str, ...], fallback: str):
    """Keep a string field inside its own vocabulary.

    A typo in a settings file should degrade to the default, not raise from the
    middle of a conversion — the caller cannot catch it usefully, and the
    engine's answer to "which mode?" is never allowed to be "none of them".
    """
    return value if value in allowed else fallback


def _clean_box(box) -> tuple[float, float, float, float] | None:
    """Drop a crop that covers everything; it only costs a copy."""
    if box is None:
        return None
    from .transform import normalize_box

    left, top, right, bottom = normalize_box(tuple(box))
    if right - left <= 0 or bottom - top <= 0:
        return None
    if (left, top, right, bottom) == (0.0, 0.0, 1.0, 1.0):
        return None
    return left, top, right, bottom


def _clamp(value: int, low: int, high: int) -> int:
    return max(low, min(high, value))


def _odd_at_least(value: int, floor: int) -> int:
    value = max(floor, value)
    return value if value % 2 == 1 else value + 1


#: Starting points that get a usable result without touching every slider.
#:
#: Each carries the denoise *mode* that suits its artwork even when the
#: strength is left at 0, so switching denoising on from a UI toggle reaches
#: for the right filter instead of whichever one happens to be the default.
PRESETS: dict[str, TraceParams] = {
    "Logo / clipart": TraceParams(
        mode="otsu", simplify_mm=0.05, min_area_mm2=0.5, smooth=0,
        straighten_mm=0.15,
        # Flat colour with edges the artwork meant to be smooth, which is
        # exactly what a bilateral filter preserves and a median one rounds.
        denoise_mode="bilateral",
        # A one-pixel closing fills the hairline notches a traced curve picks
        # up from the pixel grid, so an oval stays an oval.
        close_px=1, morph_kernel="ellipse", morph_iterations=1,
    ),
    "Photo": TraceParams(
        mode="posterize", levels=3, blur=3, simplify_mm=0.15,
        min_area_mm2=2.0, smooth=1,
        # Photographs have no straight edges to recover; forcing runs flat
        # would only flatten tonal boundaries that are genuinely curved.
        straighten_mm=0.0,
        # Non-local means compares whole patches, which suits the repeated
        # texture of a photograph. Left off by default: it is slow, and the
        # blur above already does most of the work.
        denoise_mode="nlm", denoise=0,
        # Closing tone boundaries would merge bands that are genuinely
        # separate, so morphology stays off here.
        close_px=0, open_px=0,
    ),
    "Line art / scan": TraceParams(
        mode="adaptive", adaptive_block=31, adaptive_c=7, denoise=3,
        simplify_mm=0.08, min_area_mm2=0.3, close_px=1,
        # Scanner grain is isolated pixels; the median filter deletes those
        # outright where a bilateral one would only soften them.
        denoise_mode="median",
        # Two light passes follow a thin stroke rather than stamping one wide
        # disc over it, so a hairline joins up without also getting fatter.
        morph_kernel="ellipse", morph_iterations=2,
    ),
    "Edge outline": TraceParams(
        mode="edges", canny_low=80, canny_high=160, edge_dilate=1,
        simplify_mm=0.08, min_area_mm2=0.2,
        # Canny edges break into dashes on a noisy original; a bilateral pass
        # beforehand keeps them continuous without blurring them away.
        denoise_mode="bilateral",
        close_px=1, morph_kernel="cross",
    ),
}

DEFAULT_PRESET = "Logo / clipart"

#: Built-in presets are the starting points shipped with the tool; the
#: user's own live in ~/.img2dxf/presets.json and are merged over these.
#: See :mod:`img2dxf.settings`.
