"""Tests for core/img2dxf/shape_fit.py.

Covers:
- Perfect circle → snapped to CIRCLE
- Perfect ellipse → snapped to ELLIPSE (not CIRCLE)
- Perfect rectangle → snapped to RECT
- Irregular polygon → returns NONE
- Too few vertices → returns NONE immediately
- Selectivity flags (try_circle=False, etc.)
- Sparse rectangle ring must never be mistaken for an ellipse
- Batch pass fit_shapes: rects to 4 corners, circles to Path.circles,
  ellipses resampled on the primitive, flags honoured, holes included
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from img2dxf.shape_fit import PrimitiveKind, fit_primitive


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _circle_ring(cx: float, cy: float, r: float, n: int = 64) -> np.ndarray:
    """Generate a perfectly sampled circle as an (N, 2) array."""
    angles = np.linspace(0, 2 * math.pi, n, endpoint=False)
    return np.column_stack([cx + r * np.cos(angles), cy + r * np.sin(angles)])


def _ellipse_ring(cx: float, cy: float, a: float, b: float, n: int = 64) -> np.ndarray:
    """Generate a perfectly sampled axis-aligned ellipse."""
    angles = np.linspace(0, 2 * math.pi, n, endpoint=False)
    return np.column_stack([cx + a * np.cos(angles), cy + b * np.sin(angles)])


def _rect_ring(x0: float, y0: float, x1: float, y1: float, pts_per_side: int = 20) -> np.ndarray:
    """Generate a rectangle ring sampled uniformly along each edge."""
    top = np.column_stack([np.linspace(x0, x1, pts_per_side, endpoint=False),
                           np.full(pts_per_side, y0)])
    right = np.column_stack([np.full(pts_per_side, x1),
                              np.linspace(y0, y1, pts_per_side, endpoint=False)])
    bottom = np.column_stack([np.linspace(x1, x0, pts_per_side, endpoint=False),
                               np.full(pts_per_side, y1)])
    left = np.column_stack([np.full(pts_per_side, x0),
                             np.linspace(y1, y0, pts_per_side, endpoint=False)])
    return np.vstack([top, right, bottom, left])


def _irregular_ring(n: int = 30, seed: int = 0) -> np.ndarray:
    """An irregular closed polygon that should not snap to any primitive."""
    rng = np.random.default_rng(seed)
    radii = rng.uniform(5, 20, n)
    angles = np.sort(rng.uniform(0, 2 * math.pi, n))
    return np.column_stack([radii * np.cos(angles), radii * np.sin(angles)])


# ---------------------------------------------------------------------------
# Circle snapping
# ---------------------------------------------------------------------------

def test_perfect_circle_snaps_to_circle():
    ring = _circle_ring(0.0, 0.0, 10.0, n=64)
    fit = fit_primitive(ring, tol_mm=0.05)
    assert fit.kind == PrimitiveKind.CIRCLE
    assert fit.circle is not None
    cx, cy, r = fit.circle
    assert abs(cx) < 0.1
    assert abs(cy) < 0.1
    assert abs(r - 10.0) < 0.1


def test_circle_max_error_is_small():
    ring = _circle_ring(5.0, -3.0, 7.5, n=128)
    fit = fit_primitive(ring, tol_mm=0.05)
    assert fit.kind == PrimitiveKind.CIRCLE
    assert fit.max_error_mm < 0.05


def test_circle_snapping_disabled():
    ring = _circle_ring(0.0, 0.0, 10.0, n=64)
    fit = fit_primitive(ring, tol_mm=0.05, try_circle=False, try_ellipse=False)
    # With no circle or ellipse fitting, should not snap to circle.
    assert fit.kind != PrimitiveKind.CIRCLE


# ---------------------------------------------------------------------------
# Ellipse snapping
# ---------------------------------------------------------------------------

def test_ellipse_snaps_to_ellipse_not_circle():
    # Semi-axes 10 and 6 — clearly not a circle.
    ring = _ellipse_ring(0.0, 0.0, 10.0, 6.0, n=64)
    fit = fit_primitive(ring, tol_mm=0.5)
    assert fit.kind == PrimitiveKind.ELLIPSE
    assert fit.ellipse_params is not None


def test_ellipse_snapping_disabled_falls_through():
    ring = _ellipse_ring(0.0, 0.0, 10.0, 6.0, n=64)
    fit = fit_primitive(ring, tol_mm=0.5, try_circle=False, try_ellipse=False)
    # Falls through to NONE or RECT (rectangle won't match an ellipse).
    assert fit.kind != PrimitiveKind.ELLIPSE


# ---------------------------------------------------------------------------
# Rectangle snapping
# ---------------------------------------------------------------------------

def test_perfect_rectangle_snaps_to_rect():
    ring = _rect_ring(0.0, 0.0, 20.0, 10.0, pts_per_side=25)
    fit = fit_primitive(ring, tol_mm=0.5)
    assert fit.kind == PrimitiveKind.RECT
    assert fit.rect_pts is not None
    assert fit.rect_pts.shape == (4, 2)


def test_rect_snapping_disabled():
    ring = _rect_ring(0.0, 0.0, 20.0, 10.0, pts_per_side=25)
    fit = fit_primitive(ring, tol_mm=0.5, try_circle=False,
                        try_ellipse=False, try_rect=False)
    assert fit.kind == PrimitiveKind.NONE


# ---------------------------------------------------------------------------
# Irregular / unfitting shapes
# ---------------------------------------------------------------------------

def test_irregular_polygon_returns_none():
    ring = _irregular_ring(n=40)
    fit = fit_primitive(ring, tol_mm=0.05)
    assert fit.kind == PrimitiveKind.NONE


# ---------------------------------------------------------------------------
# Minimum vertices guard
# ---------------------------------------------------------------------------

def test_too_few_vertices_returns_none_immediately():
    # A triangle: 3 vertices.
    ring = np.array([[0.0, 0.0], [5.0, 0.0], [2.5, 4.3]])
    fit = fit_primitive(ring, tol_mm=0.5, min_vertices=8)
    assert fit.kind == PrimitiveKind.NONE
    assert fit.vertex_count == 3


def test_exactly_min_vertices_proceeds():
    """A ring with exactly min_vertices should be tested, not short-circuited."""
    ring = _circle_ring(0.0, 0.0, 8.0, n=8)
    fit = fit_primitive(ring, tol_mm=0.5, min_vertices=8)
    # May or may not snap depending on geometry, but it must not short-circuit.
    assert fit.vertex_count == 8


# ---------------------------------------------------------------------------
# Vertex count reported correctly
# ---------------------------------------------------------------------------

def test_vertex_count_matches_input():
    ring = _circle_ring(0.0, 0.0, 5.0, n=50)
    fit = fit_primitive(ring, tol_mm=0.2)
    assert fit.vertex_count == 50


# ---------------------------------------------------------------------------
# Noisy circle (slightly perturbed) should still snap within generous tolerance
# ---------------------------------------------------------------------------

def test_noisy_circle_snaps_with_generous_tolerance():
    rng = np.random.default_rng(1)
    ring = _circle_ring(0.0, 0.0, 10.0, n=64)
    ring += rng.normal(0, 0.04, ring.shape)  # ±0.04 mm jitter

    fit_tight = fit_primitive(ring, tol_mm=0.02)  # too tight
    fit_loose = fit_primitive(ring, tol_mm=0.15)   # generous

    # Tight tolerance may or may not snap; loose tolerance should snap.
    assert fit_loose.kind == PrimitiveKind.CIRCLE
    # The tight one may be NONE — that's the correct conservative behaviour.
    assert fit_tight.kind in (PrimitiveKind.NONE, PrimitiveKind.CIRCLE)


# ---------------------------------------------------------------------------
# Rectangle must never be mistaken for an ellipse (interpolation guard)
# ---------------------------------------------------------------------------

def test_sparse_rectangle_ring_is_not_snapped_to_ellipse():
    """The fitEllipse-through-the-corners false positive.

    cv2.fitEllipse interpolates: the ellipse through a rectangle's corners
    passes every *vertex* exactly. Only the area band catches it — the
    interpolating ellipse swells far past the ring's edges. Regression test
    for a bug where a traced rectangle came out of the pipeline as a huge
    resampled ellipse.
    """
    ring = _rect_ring(0.0, 0.0, 60.0, 45.0, pts_per_side=2)  # 8 vertices
    fit = fit_primitive(ring, tol_mm=0.35)
    assert fit.kind in (PrimitiveKind.RECT, PrimitiveKind.NONE)
    assert fit.kind != PrimitiveKind.ELLIPSE
    assert fit.kind != PrimitiveKind.CIRCLE


# ---------------------------------------------------------------------------
# Batch pass: fit_shapes over paths during a pipeline run
# ---------------------------------------------------------------------------

from img2dxf.geometry import Path  # noqa: E402
from img2dxf.params import TraceParams  # noqa: E402
from img2dxf.shape_fit import fit_shapes  # noqa: E402


def _batch(px_per_mm: float = 100.0, detail_factor: int = 1, **kw) -> TraceParams:
    return TraceParams(**kw)


def test_batch_snaps_axis_aligned_rect_to_four_corners():
    ring = _rect_ring(0.0, 0.0, 60.0, 45.0, pts_per_side=25)
    path = Path(outer=ring)
    report = fit_shapes([path], _batch(), px_per_mm=100.0)

    assert report.rects == 1
    assert len(path.outer) == 4
    # The four corners sit at the rectangle's extremes.
    assert np.allclose(np.sort(path.outer[:, 0]), [0.0, 0.0, 60.0, 60.0], atol=0.35)
    assert np.allclose(np.sort(path.outer[:, 1]), [0.0, 0.0, 45.0, 45.0], atol=0.35)


def test_batch_bounds_of_snapped_rect_match_the_ring():
    """Regression: snapping must never move the geometry.

    A bug once replaced a traced rectangle with a giant ellipse, growing the
    reported bounds by a third. Whatever a ring snaps to, its extent has to
    stay within the acceptance tolerance of the ring it came from.
    """
    ring = _rect_ring(10.0, 20.0, 70.0, 65.0, pts_per_side=25)
    path = Path(outer=ring)
    fit_shapes([path], _batch(), px_per_mm=100.0)

    assert len(path.outer) == 4
    assert path.outer[:, 0].min() == pytest.approx(10.0, abs=0.35)
    assert path.outer[:, 0].max() == pytest.approx(70.0, abs=0.35)
    assert path.outer[:, 1].min() == pytest.approx(20.0, abs=0.35)
    assert path.outer[:, 1].max() == pytest.approx(65.0, abs=0.35)


def test_batch_snaps_rotated_rect_below_vertex_floor():
    """A simplified rotated rectangle keeps only ~5 vertices — still a RECT.

    The ellipse floor (min_vertices) must not hide rotated rectangles from
    the rect fitter, whose corner-reach and area tests stay exact at four
    points. Exercises the rect-only retry in fit_shapes.
    """
    theta = math.radians(30.0)
    w, h = 20.0, 10.0
    corners = np.array(
        [
            [0.0, 0.0],
            [w * math.cos(theta), w * math.sin(theta)],
            [w * math.cos(theta) + h * math.sin(theta), w * math.sin(theta) - h * math.cos(theta)],
            [h * math.sin(theta), -h * math.cos(theta)],
        ]
    )
    # Four corners plus one mid-edge point, in traversal order: 5 vertices,
    # below the default shape_fit_min_vertices of 8.
    mid = (corners[0] + corners[1]) / 2.0
    ring = np.vstack([corners[:1], mid[None, :], corners[1:]])

    path = Path(outer=ring)
    report = fit_shapes([path], _batch(), px_per_mm=100.0)

    assert report.rects == 1
    assert len(path.outer) == 4
    for corner in corners:
        assert np.linalg.norm(path.outer - corner, axis=1).min() < 0.35


def test_batch_stores_whole_circle_in_circles_dict():
    ring = _circle_ring(50.0, 40.0, 15.0, n=64)
    path = Path(outer=ring)
    report = fit_shapes([path], _batch(), px_per_mm=100.0)

    assert report.circles == 1
    assert 0 in path.circles
    cx, cy, radius = path.circles[0]
    assert abs(cx - 50.0) < 0.35
    assert abs(cy - 40.0) < 0.35
    assert abs(radius - 15.0) < 0.35
    # A snapped circle keeps its ring points (they are simply not exported),
    # and vertex_count reflects that the machine gets one CIRCLE entity.
    assert len(path.outer) == 64
    assert path.vertex_count == 0


def test_batch_resamples_ellipse_on_the_primitive():
    ring = _ellipse_ring(0.0, 0.0, 10.0, 6.0, n=64)
    path = Path(outer=ring)
    report = fit_shapes([path], _batch(), px_per_mm=100.0)

    assert report.ellipses == 1
    # The ring is replaced by a dense sampling of the fitted ellipse, ready
    # for arc fitting downstream.
    assert len(path.outer) >= 96
    for point in path.outer:
        x, y = point
        value = (x / 10.0) ** 2 + (y / 6.0) ** 2
        assert value == pytest.approx(1.0, abs=0.02)


def test_batch_leaves_irregular_ring_untouched():
    ring = _irregular_ring(n=40)
    path = Path(outer=ring)
    report = fit_shapes([path], _batch(), px_per_mm=100.0)

    assert report.total == 0
    assert len(path.outer) == 40
    assert np.array_equal(path.outer, ring)
    assert not path.circles


def test_batch_honours_master_switch():
    ring = _circle_ring(0.0, 0.0, 10.0, n=64)
    path = Path(outer=ring)
    report = fit_shapes([path], _batch(shape_fit=False), px_per_mm=100.0)

    assert report.total == 0
    assert not path.circles


def test_batch_honours_per_primitive_flags():
    ring = _circle_ring(0.0, 0.0, 10.0, n=64)
    params = _batch(shape_fit_circle=False, shape_fit_ellipse=False)
    path = Path(outer=ring)
    report = fit_shapes([path], params, px_per_mm=100.0)

    # No circle and no ellipse allowed; a bounding-box rectangle is not
    # reached by the ring, so nothing may snap at all.
    assert report.total == 0
    assert not path.circles
    assert len(path.outer) == 64


def test_batch_skips_rings_that_already_have_arc_data():
    ring = _circle_ring(0.0, 0.0, 10.0, n=64)
    path = Path(outer=ring, bulges={0: np.zeros(64)})
    report = fit_shapes([path], _batch(), px_per_mm=100.0)

    assert report.total == 0
    assert 0 not in path.circles


def test_batch_processes_holes_too():
    outer = _circle_ring(0.0, 0.0, 20.0, n=64)
    hole = _rect_ring(-5.0, -5.0, 5.0, 5.0, pts_per_side=20)
    path = Path(outer=outer, holes=[hole])
    report = fit_shapes([path], _batch(), px_per_mm=100.0)

    assert report.circles == 1
    assert report.rects == 1
    assert 0 in path.circles
    assert len(path.holes[0]) == 4
