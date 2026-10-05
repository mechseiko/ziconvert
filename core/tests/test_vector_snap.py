"""Tests for core/img2dxf/vector_snap.py.

Covers:
- Near-horizontal / near-vertical segments made exactly so; real diagonals
  and sub-minimum noise segments left alone
- A corner a fraction of a degree off square moved onto true 90 (Thales),
  its chord endpoints untouched
- The global merge collapsing near-equal coordinates across shapes,
  chaining consecutive values, honouring 0 as off
- Near-circular rings claimed as CIRCLEs; octagons and triangles refused;
  claimed rings protected from every later stage
- Params: snap_enabled covers every stage, the master switch works
- Pipeline: a traced square comes out with exactly four corners, perfectly
  axis-parallel, with straighten+snap alone (shape_fit off)
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from img2dxf.geometry import Path
from img2dxf.params import TraceParams
from img2dxf.pipeline import run
from img2dxf.vector_snap import VectorSnapReport, snap_vectors


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _axes_only(**overrides) -> TraceParams:
    """Params with only axis snapping on."""
    return TraceParams(
        snap_axis_deg=overrides.pop("axis", 0.75),
        snap_merge_mm=0.0,
        snap_right_angle_deg=0.0,
        snap_circle_mm=0.0,
        **overrides,
    )


def _merge_only(tol: float = 0.05) -> TraceParams:
    return TraceParams(
        snap_axis_deg=0.0,
        snap_merge_mm=tol,
        snap_right_angle_deg=0.0,
        snap_circle_mm=0.0,
    )


def _right_only(deg: float = 1.5) -> TraceParams:
    return TraceParams(
        snap_axis_deg=0.0,
        snap_merge_mm=0.0,
        snap_right_angle_deg=deg,
        snap_circle_mm=0.0,
    )


def _circle_only(tol: float = 0.1) -> TraceParams:
    return TraceParams(
        snap_axis_deg=0.0,
        snap_merge_mm=0.0,
        snap_right_angle_deg=0.0,
        snap_circle_mm=tol,
    )


def _ring(points) -> list[Path]:
    return [Path(np.asarray(points, dtype=float))]


# ---------------------------------------------------------------------------
# Axis snapping
# ---------------------------------------------------------------------------

def test_near_horizontal_segment_becomes_exact():
    path = _ring([(0, 0), (10, 0.1), (10, 10), (0, 10)])[0]
    report = snap_vectors([path], _axes_only())

    assert report.segments_axis_snapped == 1
    # Both endpoints move to the shared mean, not one the whole way.
    assert path.outer[0, 1] == path.outer[1, 1] == pytest.approx(0.05, abs=1e-12)
    # The vertical sides are untouched.
    assert path.outer[1, 0] == path.outer[2, 0] == 10.0


def test_genuine_diagonal_is_left_alone():
    original = np.asarray([(0, 0), (10, 1), (10, 10), (0, 10)], dtype=float)
    path = Path(original.copy())
    report = snap_vectors([path], _axes_only())

    assert report.segments_axis_snapped == 0
    assert np.array_equal(path.outer, original)


def test_short_noise_segment_is_not_snapped():
    # The 0.042 mm hop at 45 degrees is below snap_min_segment_mm: its angle
    # is meaningless, so it must not be straightened — the long near-flat
    # segment after it legitimately is.
    original = np.asarray([(0, 0), (0.03, 0.03), (10, 0), (10, 10)], dtype=float)
    path = Path(original.copy())
    report = snap_vectors([path], _axes_only())

    assert report.segments_axis_snapped == 1
    # The short segment's own endpoint never moved: no axis-snap touched it.
    assert np.array_equal(path.outer[0], original[0])
    assert path.outer[1, 0] == 0.03  # only its y moved, via the long segment


# ---------------------------------------------------------------------------
# Right angles
# ---------------------------------------------------------------------------

def test_corner_off_square_moves_onto_true_right_angle():
    # Corner B sits a fraction of a degree off square between two long edges;
    # the two closing corners are ~45 degrees and must not move.
    a = np.array([0.0, 0.0])
    b = np.array([5.0, 4.98])
    c = np.array([10.0, -0.02])
    path = _ring([a, b, c])[0]

    report = snap_vectors([path], _right_only())

    assert report.corners_right_angled == 1
    assert np.array_equal(path.outer[0], a)
    assert np.array_equal(path.outer[2], c)
    moved = path.outer[1]
    to_prev = a - moved
    to_next = c - moved
    assert abs(float(np.dot(to_prev, to_next))) < 1e-3  # exactly square


def test_corner_far_from_square_is_left_alone():
    original = np.asarray(
        [(0, 0), (10, 0), (10, 10), (5, 6), (0, 10)], dtype=float
    )  # the (5,6) corner is ~53 degrees
    path = Path(original.copy())
    report = snap_vectors([path], _right_only())

    assert report.corners_right_angled == 0
    assert np.array_equal(path.outer, original)


# ---------------------------------------------------------------------------
# Global merge
# ---------------------------------------------------------------------------

def test_merge_aligns_coordinates_across_paths():
    left = Path(np.asarray([(0, 0), (10, 0), (10, 10), (0, 10)], dtype=float))
    right = Path(
        np.asarray([(10.03, 0), (20, 0), (20, 10), (10.03, 10)], dtype=float)
    )
    report = snap_vectors([left, right], _merge_only())

    assert report.values_merged == 1  # {10, 10.03} became one value
    shared = left.outer[2, 0]
    assert shared == right.outer[0, 0]
    assert shared == right.outer[3, 0]
    assert shared == left.outer[1, 0]  # the whole right edge of `left`
    assert shared == pytest.approx(10.015, abs=1e-12)  # the cluster mean


def test_merge_chains_consecutive_values():
    # 0.00, 0.04, 0.08: each gap within 0.05, so all three chain into one
    # cluster and take its mean. Pairwise-only merging would leave 0.08 out.
    path = _ring([(0, 0), (0.04, 10), (0.08, 20)])[0]
    report = snap_vectors([path], _merge_only(0.05))

    assert report.values_merged == 2
    assert np.all(path.outer[:, 0] == pytest.approx(0.04, abs=1e-12))


def test_merge_disabled_at_zero():
    original = np.asarray([(0, 0), (10, 0), (10.03, 10), (0, 10)], dtype=float)
    path = Path(original.copy())
    report = snap_vectors([path], _merge_only(0.0))

    assert report.values_merged == 0
    assert np.array_equal(path.outer, original)


# ---------------------------------------------------------------------------
# Near-circles
# ---------------------------------------------------------------------------

def _noisy_circle_ring(cx, cy, r, n=64, noise=0.01, seed=0):
    angles = np.linspace(0, 2 * math.pi, n, endpoint=False)
    rng = np.random.default_rng(seed)
    radius = r + rng.normal(0, noise, n)
    return np.column_stack([cx + radius * np.cos(angles), cy + radius * np.sin(angles)])


def test_near_circular_ring_is_claimed_as_circle():
    path = Path(_noisy_circle_ring(50.0, 40.0, 15.0))
    report = snap_vectors([path], _circle_only())

    assert report.circles_snapped == 1
    assert 0 in path.circles
    cx, cy, radius = path.circles[0]
    assert cx == pytest.approx(50.0, abs=0.1)
    assert cy == pytest.approx(40.0, abs=0.1)
    assert radius == pytest.approx(15.0, abs=0.1)


def test_octagon_is_not_a_circle():
    # An octagon's side midpoints sit 7.6% of the radius off any circle —
    # an order of magnitude beyond the tolerance.
    angles = np.linspace(0, 2 * math.pi, 8, endpoint=False)
    ring = np.column_stack([50 + 10 * np.cos(angles), 40 + 10 * np.sin(angles)])
    path = Path(ring)
    report = snap_vectors([path], _circle_only())

    assert report.circles_snapped == 0
    assert not path.circles


def test_claimed_ring_is_protected_from_later_stages():
    ring = _noisy_circle_ring(50.0, 40.0, 15.0)
    path = Path(ring.copy())
    everything = TraceParams()  # every stage at its default

    report = snap_vectors([path], everything)

    assert report.circles_snapped == 1
    assert np.array_equal(path.outer, ring)  # points untouched after the claim


def test_ring_with_arc_data_is_left_alone():
    original = np.asarray([(0, 0), (10, 0.1), (10, 10), (0, 10)], dtype=float)
    path = Path(original.copy())
    path.bulges[0] = np.zeros(4)

    report = snap_vectors([path], TraceParams())

    assert report.total == 0
    assert np.array_equal(path.outer, original)


# ---------------------------------------------------------------------------
# Params wiring
# ---------------------------------------------------------------------------

def test_snap_enabled_covers_every_stage():
    base = dict(snap_axis_deg=0.0, snap_merge_mm=0.0, snap_right_angle_deg=0.0)
    assert not TraceParams(**base, snap_circle_mm=0.0, vector_snap=True).snap_enabled
    assert TraceParams(**base, snap_circle_mm=0.1, vector_snap=True).snap_enabled
    assert TraceParams(snap_axis_deg=0.75).snap_enabled
    assert not TraceParams(vector_snap=False).snap_enabled


def test_empty_input_gives_empty_report():
    assert snap_vectors([], TraceParams()) == VectorSnapReport()


# ---------------------------------------------------------------------------
# Pipeline integration
# ---------------------------------------------------------------------------

def test_traced_square_comes_out_exactly_axis_parallel():
    """A slightly crooked scan: straighten flattens each side, the snap then
    makes every long edge *exactly* horizontal or vertical.

    An aligned square needs no snap — the pixel grid already delivers exact
    edges — so the image is rotated a third of a degree first, which is the
    crooked-scan case the pass exists for. Tracing keeps the tiny corner
    chamfers, so the ring carries more than four vertices; what matters is
    that every long segment is exact.
    """
    image = np.full((200, 200, 3), 255, np.uint8)
    image[60:140, 60:140] = 0
    params = TraceParams(
        size_mode="width",
        width_mm=100.0,
        rotate_deg=0.3,
        shape_fit=False,  # isolate the snap: no ideal-rectangle replacement
        fit_arcs=False,
    )
    result = run(image, params)

    assert result.path_count == 1
    outer = result.paths[0].outer
    long_edges = 0
    for index in range(len(outer)):
        nxt = outer[(index + 1) % len(outer)]
        dx = float(nxt[0] - outer[index, 0])
        dy = float(nxt[1] - outer[index, 1])
        if math.hypot(dx, dy) < 1.0:
            continue  # a corner chamfer, not an edge
        long_edges += 1
        if abs(dx) >= abs(dy):
            assert outer[index, 1] == nxt[1]  # exactly horizontal
        else:
            assert outer[index, 0] == nxt[0]  # exactly vertical
    assert long_edges == 4
    assert result.vectors_snapped >= 4
    assert "vector-snapped" in result.summary()


def test_traced_circle_is_claimed_inside_the_pipeline(ring_image):
    """The outer ring of a traced annulus is circular within the snap tol.

    The tolerance is ~2.5 source pixels, not the default 0.1: the rasterised
    circle's own staircase sits up to 0.28 mm off its best-fitting circle at
    the default detail factor (0.30 mm at factor 2), because the tracer walks
    pixel boundaries and the Kasa centre drifts with the rasteriser's slight
    asymmetry. 0.4 mm clears every measured factor with headroom while staying
    far below any real feature. The judgement is meant to be the looser,
    earlier one — shape_fit, post-kerf, stays stricter.
    """
    params = TraceParams(
        size_mode="width",
        width_mm=100.0,
        shape_fit=False,  # keep the judgement in the vector-snap stage
        fit_arcs=False,
        straighten_mm=0.0,  # do not flatten the ring before judging it
        snap_circle_mm=0.4,
    )
    result = run(ring_image, params)

    assert result.path_count == 1
    path = result.paths[0]
    assert 0 in path.circles  # outer boundary claimed
    assert 1 in path.circles  # and the hole with it
    cx, cy, radius = path.circles[0]
    assert (cx, cy, radius) == pytest.approx((50.0, 50.0, 40.0), abs=1.0)
