"""Contour-to-primitive snapping: the shape-fitting public surface.

This module is the published boundary between the engine's internals and the
web / CLI callers that want to know *what kind of shape* a ring is, without
knowing about bulges or DXF write paths.

The heavy lifting lives in :mod:`img2dxf.arcfit`; this module aggregates the
results into a single typed interface so callers can treat shape fitting as one
self-contained step rather than orchestrating arcfit directly.

Typical use::

    from img2dxf.shape_fit import fit_primitive, PrimitiveFit, PrimitiveKind

    ring_mm = ...  # (N, 2) float array in millimetres
    fit = fit_primitive(ring_mm, tol_mm=0.1)
    if fit.kind == PrimitiveKind.CIRCLE:
        cx, cy, r = fit.circle       # exact circle
    elif fit.kind == PrimitiveKind.NONE:
        ...                           # keep original polygon

The module is UI-free and carries no GUI imports.  Both the desktop app and the
web backend may import it freely.

For the tracing pipeline itself there is also :func:`fit_shapes`, the batch
pass that applies :func:`fit_primitive` to every ring of every path and
rewrites the ones that qualify, so a traced circle leaves the engine as a true
CIRCLE entity rather than as a few hundred short segments.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

import numpy as np

from .arcfit import fit_circle


class PrimitiveKind(str, Enum):
    """Which primitive a ring was snapped to, or ``NONE`` if it stayed a polygon."""

    NONE = "none"
    CIRCLE = "circle"
    ELLIPSE = "ellipse"
    RECT = "rect"


@dataclass(slots=True)
class PrimitiveFit:
    """Result of fitting one ring to the nearest geometric primitive.

    Exactly one of :attr:`circle`, :attr:`ellipse_params`, or :attr:`rect_pts`
    is populated, matching :attr:`kind`.  All others are ``None`` so callers
    can branch on :attr:`kind` and then unpack the relevant field.
    """

    kind: PrimitiveKind = PrimitiveKind.NONE

    # --- CIRCLE ----------------------------------------------------------
    circle: Optional[tuple[float, float, float]] = None
    """``(cx, cy, radius)`` in the same units as the input ring."""

    # --- ELLIPSE ---------------------------------------------------------
    ellipse_params: Optional[tuple[float, float, float, float, float]] = None
    """``(cx, cy, semi_major, semi_minor, angle_deg)``."""

    # --- RECT ------------------------------------------------------------
    rect_pts: Optional[np.ndarray] = None
    """Four corner points of the fitted (possibly rotated) rectangle, shape ``(4, 2)``."""

    # --- diagnostics -----------------------------------------------------
    max_error_mm: float = 0.0
    """Largest distance from any ring vertex to the fitted primitive surface."""

    vertex_count: int = 0
    """How many vertices were in the ring that was tested."""


def fit_primitive(
    ring: np.ndarray,
    *,
    tol_mm: float = 0.1,
    try_circle: bool = True,
    try_ellipse: bool = True,
    try_rect: bool = True,
    min_vertices: int = 8,
) -> PrimitiveFit:
    """Fit the best geometric primitive to a closed ring.

    Parameters
    ----------
    ring:
        ``(N, 2)`` array of vertices in any consistent unit (millimetres
        in normal use).  The ring is treated as closed: the edge from the
        last vertex back to the first is implicit.
    tol_mm:
        How far any vertex may lie from the primitive surface and still be
        considered a match.  Pass the same value you would use for arc
        fitting — usually ``max(simplify_mm, 1/px_per_mm)``.
    try_circle:
        Attempt to snap to a circle.  Tried first; the tightest primitive wins.
    try_ellipse:
        Attempt to snap to an ellipse when circle fitting fails.
    try_rect:
        Attempt to snap to a rectangle.
    min_vertices:
        Rings with fewer vertices than this are too small for the deviation
        test to mean anything and are returned as ``NONE`` immediately.

    Returns
    -------
    PrimitiveFit
        The best-fitting primitive, or ``kind=NONE`` when nothing qualified.
    """
    n = len(ring)
    base = PrimitiveFit(vertex_count=n)

    if n < min_vertices:
        return base

    if try_circle:
        result = _try_circle(ring, tol_mm)
        if result is not None:
            return result

    if try_ellipse:
        result = _try_ellipse(ring, tol_mm)
        if result is not None:
            return result

    if try_rect:
        result = _try_rect(ring, tol_mm)
        if result is not None:
            return result

    return base


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _try_circle(ring: np.ndarray, tol: float) -> PrimitiveFit | None:
    """Delegate to :func:`~img2dxf.arcfit.fit_circle` and wrap the result."""
    circle = fit_circle(ring, tol)
    if circle is None:
        return None

    cx, cy, radius = circle
    probes = np.vstack([ring, (ring + np.roll(ring, -1, axis=0)) / 2.0])
    errors = np.abs(np.hypot(probes[:, 0] - cx, probes[:, 1] - cy) - radius)

    return PrimitiveFit(
        kind=PrimitiveKind.CIRCLE,
        circle=circle,
        max_error_mm=float(errors.max()),
        vertex_count=len(ring),
    )


def _try_ellipse(ring: np.ndarray, tol: float) -> PrimitiveFit | None:
    """Fit a general ellipse using the Fitzgibbon–Pilu–Fisher algebraic method.

    Requires at least 6 non-degenerate points. The OpenCV fitEllipse routine
    uses the same mathematics and is wrapped here so the rest of the engine
    does not have to import OpenCV just for this.
    """
    try:
        import cv2  # noqa: PLC0415 – optional heavy import
    except ImportError:
        return None

    if len(ring) < 6:
        return None

    pts = ring.astype(np.float32).reshape(-1, 1, 2)
    try:
        (cx, cy), (w, h), angle = cv2.fitEllipse(pts)
    except cv2.error:
        return None

    # Check the vertices against the fitted ellipse — vertex-only, on purpose.
    # Probing segment midpoints would be wrong here: a simplified ring is a
    # polygon, and a polygon's chords sag away from any smooth curve by up to
    # millimetres between sparse vertices. That sagitta is the approximation
    # error tracing already accepted, not evidence the fit is bad. What
    # actually marks an interpolating false fit (the ellipse fitEllipse draws
    # through a rectangle's corners, say) is that its surface inflates far
    # beyond the ring — which the area band below measures directly.
    angle_rad = math.radians(angle)
    cos_a, sin_a = math.cos(angle_rad), math.sin(angle_rad)
    dx = ring[:, 0] - cx
    dy = ring[:, 1] - cy
    rx = cos_a * dx + sin_a * dy   # in ellipse-local coords
    ry = -sin_a * dx + cos_a * dy

    # OpenCV fitEllipse convention: w is the width along the rotated X axis
    # (minor), h is the height along the rotated Y axis (major).
    # In local frame: (rx / semi_b)² + (ry / semi_a)² = 1 for points on ellipse.
    semi_a = h / 2.0  # half-height (major, along rotated Y)
    semi_b = w / 2.0  # half-width  (minor, along rotated X)
    if semi_a <= 0 or semi_b <= 0:
        return None

    # Nearest point on actual ellipse: project each point (rx, ry) in unit-ellipse
    # space (ux = rx/semi_b, uy = ry/semi_a), normalise, then scale back.
    ux = rx / semi_b
    uy = ry / semi_a
    unit_norm = np.sqrt(ux ** 2 + uy ** 2)
    with np.errstate(invalid='ignore', divide='ignore'):
        near_x = np.where(unit_norm > 0, (ux / unit_norm) * semi_b, semi_b)
        near_y = np.where(unit_norm > 0, (uy / unit_norm) * semi_a, 0.0)
    errors = np.hypot(rx - near_x, ry - near_y)
    if errors.max() > tol:
        return None

    # Area band: the polygon and its fitted ellipse must be nearly the same
    # size. An ellipse fitted *through* the vertices of some other shape — a
    # rectangle's corners — swells well past the ring's edges, and its area
    # leaves the band by half as much again; a genuine fit of a traced ring
    # sits within a few percent even after simplification.
    x, y = ring[:, 0], ring[:, 1]
    poly_area = float(abs(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1))) / 2.0)
    ellipse_area = math.pi * semi_a * semi_b
    if poly_area <= 0 or ellipse_area <= 0:
        return None
    ratio = ellipse_area / poly_area
    if not 0.8 <= ratio <= 1.25:
        return None

    return PrimitiveFit(
        kind=PrimitiveKind.ELLIPSE,
        ellipse_params=(cx, cy, semi_a, semi_b, angle),
        max_error_mm=float(errors.max()),
        vertex_count=len(ring),
    )


def _try_rect(ring: np.ndarray, tol: float) -> PrimitiveFit | None:
    """Fit a (possibly rotated) rectangle using the minimum-area bounding box.

    The test is threefold:
    1. Every vertex must lie within ``tol`` of the nearest edge.
    2. Every rectangle corner must be reached by some vertex — without this,
       an L-shape or a notched bar whose bounding box is bigger than the shape
       would pass the first test and snap to a rectangle it is not.
    3. The rectangle's area must be within 5 % of the polygon's area, so a
       very irregular shape does not get snapped to its bounding box.
    """
    try:
        import cv2  # noqa: PLC0415
    except ImportError:
        return None

    pts = ring.astype(np.float32).reshape(-1, 1, 2)
    rect = cv2.minAreaRect(pts)
    box = cv2.boxPoints(rect).astype(float)  # (4, 2)

    # Check that every ring vertex is close to the rectangle outline.
    errors = _dist_to_quadrilateral(ring, box)
    if errors.max() > tol:
        return None

    # And that the rectangle's own corners are reached by the ring.
    corner_errors = _dist_to_ring(box, ring)
    if corner_errors.max() > tol:
        return None

    # Area check: rectangle area vs polygon shoelace area.
    x, y = ring[:, 0], ring[:, 1]
    poly_area = float(abs(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1))) / 2.0)
    rect_area = float(rect[1][0]) * float(rect[1][1])
    if poly_area <= 0 or rect_area <= 0:
        return None
    if abs(rect_area - poly_area) / rect_area > 0.05:
        return None

    return PrimitiveFit(
        kind=PrimitiveKind.RECT,
        rect_pts=box,
        max_error_mm=float(errors.max()),
        vertex_count=len(ring),
    )


def _dist_to_quadrilateral(pts: np.ndarray, quad: np.ndarray) -> np.ndarray:
    """Perpendicular distance from each point to the nearest side of ``quad``."""
    n = len(pts)
    min_dist = np.full(n, np.inf)
    for i in range(4):
        a = quad[i]
        b = quad[(i + 1) % 4]
        ab = b - a
        ab_len_sq = float(np.dot(ab, ab))
        if ab_len_sq < 1e-12:
            continue
        ap = pts - a
        t = np.clip((ap @ ab) / ab_len_sq, 0.0, 1.0)
        proj = a + t[:, None] * ab
        dist = np.hypot(pts[:, 0] - proj[:, 0], pts[:, 1] - proj[:, 1])
        min_dist = np.minimum(min_dist, dist)
    return min_dist


def _dist_to_ring(pts: np.ndarray, ring: np.ndarray) -> np.ndarray:
    """Distance from each point to its nearest position on the closed ring."""
    n = len(pts)
    min_dist = np.full(n, np.inf)
    count = len(ring)
    for i in range(count):
        a = ring[i]
        b = ring[(i + 1) % count]
        ab = b - a
        ab_len_sq = float(np.dot(ab, ab))
        if ab_len_sq < 1e-12:
            continue
        ap = pts - a
        t = np.clip((ap @ ab) / ab_len_sq, 0.0, 1.0)
        proj = a + t[:, None] * ab
        dist = np.hypot(pts[:, 0] - proj[:, 0], pts[:, 1] - proj[:, 1])
        min_dist = np.minimum(min_dist, dist)
    return min_dist


# ---------------------------------------------------------------------------
# Batch pass: snap every ring of every path during a pipeline run
# ---------------------------------------------------------------------------

#: An accepted ellipse is resampled at at least this many points, so the arc
#: fitter downstream sees a smooth curve rather than a coarse polygon.
_MIN_ELLIPSE_SAMPLES = 96


@dataclass(slots=True)
class ShapeFit:
    """One ring that accepted a primitive during a pipeline run."""

    path_index: int
    ring_index: int
    kind: PrimitiveKind


@dataclass(slots=True)
class ShapeFitReport:
    """What the pass snapped, so a UI can report it instead of implying magic."""

    fits: list[ShapeFit] = field(default_factory=list)

    @property
    def circles(self) -> int:
        return sum(1 for fit in self.fits if fit.kind == PrimitiveKind.CIRCLE)

    @property
    def ellipses(self) -> int:
        return sum(1 for fit in self.fits if fit.kind == PrimitiveKind.ELLIPSE)

    @property
    def rects(self) -> int:
        return sum(1 for fit in self.fits if fit.kind == PrimitiveKind.RECT)

    @property
    def total(self) -> int:
        return len(self.fits)


def fit_shapes(
    paths: list["Path"],
    params: "TraceParams",
    px_per_mm: float,
    detail_factor: int = 1,
) -> ShapeFitReport:
    """Try to replace each ring with the primitive it matches, in place.

    Runs after straightening and kerf compensation, before arc fitting: the
    primitives then describe the geometry the machine will actually cut, and
    the arcs fitted afterwards describe the snapped shape rather than
    re-deriving the pixel staircase. Rings that accepted a whole circle are
    stored in :attr:`Path.circles`, which every exporter already writes as a
    true CIRCLE entity; ellipses and rectangles replace the ring points with
    points on the primitive itself.

    The tolerance derives the way arc fitting derives its own: an explicit
    ``shape_fit_tol_mm`` wins, otherwise the looser of the simplification
    tolerance and one *source* pixel. A traced outline departs from any ideal
    shape by about half a pixel no matter how clean the artwork was, so a
    tighter tolerance rejects every real primitive.
    """
    report = ShapeFitReport()
    if not params.shape_fit or not paths:
        return report

    tol = _batch_tolerance(params, px_per_mm, detail_factor)

    for path_index, path in enumerate(paths):
        # ``rings()`` yields outer then holes; the index keys circles/bulges.
        for ring_index, ring in enumerate(path.rings()):
            if ring_index in path.circles or ring_index in path.bulges:
                continue

            fit = fit_primitive(
                ring,
                tol_mm=tol,
                try_circle=params.shape_fit_circle,
                try_ellipse=params.shape_fit_ellipse,
                try_rect=params.shape_fit_rect,
                min_vertices=params.shape_fit_min_vertices,
            )
            if (
                fit.kind == PrimitiveKind.NONE
                and params.shape_fit_rect
                and 4 <= len(ring) < params.shape_fit_min_vertices
            ):
                # Rings below the vertex floor are too few for a confident
                # circle or ellipse judgement (five points always fit an
                # ellipse exactly — that is what the floor protects against).
                # A rectangle is different: its corner-reach and area tests
                # stay exact at four points, so a simplified quadrilateral
                # that IS a rotated rectangle should still snap to one.
                fit = fit_primitive(
                    ring,
                    tol_mm=tol,
                    try_circle=False,
                    try_ellipse=False,
                    try_rect=True,
                    min_vertices=4,
                )
            if fit.kind == PrimitiveKind.NONE:
                continue

            if fit.kind == PrimitiveKind.CIRCLE and fit.circle is not None:
                path.circles[ring_index] = fit.circle
            elif fit.kind == PrimitiveKind.ELLIPSE and fit.ellipse_params is not None:
                _replace_ring(path, ring_index, _sample_ellipse(fit.ellipse_params, len(ring)))
            elif fit.kind == PrimitiveKind.RECT and fit.rect_pts is not None:
                _replace_ring(path, ring_index, np.asarray(fit.rect_pts, dtype=float))
            else:  # pragma: no cover - fit populated nothing; treat as no match
                continue

            report.fits.append(ShapeFit(path_index, ring_index, fit.kind))

    return report


def _batch_tolerance(params: "TraceParams", px_per_mm: float, detail_factor: int) -> float:
    """Acceptance distance for the batch pass, mirroring arc fitting."""
    if params.shape_fit_tol_mm > 0:
        return params.shape_fit_tol_mm
    source_pixel_mm = detail_factor / px_per_mm if px_per_mm > 0 else 0.0
    return max(params.simplify_mm, source_pixel_mm, 0.02)


def _replace_ring(path: "Path", ring_index: int, points: np.ndarray) -> None:
    """Swap the ring's points, keeping every other ring in place."""
    if ring_index == 0:
        path.outer = points
    else:
        path.holes[ring_index - 1] = points
    # Any arc data described the old points; the fitter will re-derive it.
    path.bulges.pop(ring_index, None)


def _sample_ellipse(
    params: tuple[float, float, float, float, float], original_count: int
) -> np.ndarray:
    """Points on the fitted ellipse, evenly spaced in its parameter angle.

    Uses the same axis convention as :func:`fit_primitive`: ``semi_major``
    lies along the rotated Y axis, ``semi_minor`` along the rotated X axis, so
    the sampled points satisfy the very equation the deviation test passed.
    """
    cx, cy, semi_major, semi_minor, angle_deg = params
    count = max(original_count, _MIN_ELLIPSE_SAMPLES)
    t = np.linspace(0.0, 2.0 * math.pi, count, endpoint=False)
    local = np.column_stack([semi_minor * np.cos(t), semi_major * np.sin(t)])
    angle = math.radians(angle_deg)
    rotate = np.array(
        [[math.cos(angle), -math.sin(angle)], [math.sin(angle), math.cos(angle)]]
    )
    return local @ rotate.T + np.array([cx, cy])


__all__ = [
    "PrimitiveFit",
    "PrimitiveKind",
    "ShapeFit",
    "ShapeFitReport",
    "fit_primitive",
    "fit_shapes",
]
