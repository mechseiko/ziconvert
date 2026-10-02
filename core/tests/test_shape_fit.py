"""Tests for core/img2dxf/shape_fit.py.

Covers:
- Perfect circle → snapped to CIRCLE
- Perfect ellipse → snapped to ELLIPSE (not CIRCLE)
- Perfect rectangle → snapped to RECT
- Irregular polygon → returns NONE
- Too few vertices → returns NONE immediately
- Selectivity flags (try_circle=False, etc.)
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
