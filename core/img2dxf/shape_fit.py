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

    semi_major = max(w, h) / 2.0
    semi_minor = min(w, h) / 2.0
    if semi_minor <= 0:
        return None

    # Check every vertex against the fitted ellipse equation.
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

    return PrimitiveFit(
        kind=PrimitiveKind.ELLIPSE,
        ellipse_params=(cx, cy, semi_a, semi_b, angle),
        max_error_mm=float(errors.max()),
        vertex_count=len(ring),
    )


def _try_rect(ring: np.ndarray, tol: float) -> PrimitiveFit | None:
    """Fit a (possibly rotated) rectangle using the minimum-area bounding box.

    The test is twofold:
    1. Every vertex must lie within ``tol`` of the nearest edge.
    2. The rectangle's area must be within 5 % of the polygon's area, so a
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


__all__ = [
    "PrimitiveFit",
    "PrimitiveKind",
    "fit_primitive",
]
