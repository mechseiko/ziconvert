"""Post-tracing vector snap: regularise the traced geometry on the way out.

Tracing faithfully reproduces what the pixels say, and what the pixels say is
almost never quite what the artwork meant. A stem that was drawn perfectly
vertical arrives tilted by a few hundredths of a degree; two features meant to
share an edge arrive 0.02 mm apart; a corner meant to be square arrives at
89.96 degrees. Every one of those errors is far below the user's tolerance —
and far below what a laser can hold — so correcting them is not a guess about
intent, it is removing noise no machine could reproduce anyway.

The pass makes four judgements, in a deliberate order:

1. **Near-circles** are claimed first, because every later stage would mangle
   them: forcing a curve's segments onto the axes staircases it. A claimed
   ring exports as a single CIRCLE entity, so its points stop mattering.
2. **Axis snapping** makes segments within a fraction of a degree of
   horizontal or vertical exactly so.
3. **Right angles** follow, because axis-aligned neighbours are already
   exactly perpendicular once stage 2 has run — what remains are the diagonal
   corners. The corner moves onto the circle whose diameter is the chord
   across it: by the converse of Thales' theorem, that circle is exactly the
   locus of corners seeing the chord at 90 degrees, so its nearest point is
   the smallest legal move.
4. **The global merge runs last** because it is the coarsest judgement and
   the last writer wins. Axis snapping sets both endpoints of a segment to
   one identical float, so a merge that collapses near-equal coordinates
   maps that float through one cluster and cannot un-straighten the segment —
   the reverse order would let snapping pull endpoints off the merged grid.

All tolerances come from :class:`~img2dxf.params.TraceParams` and are
millimetre values by design: at trace resolution they are fractions of a
pixel, which is precisely the noise floor this pass exists to remove.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from .arcfit import fit_circle
from .geometry import Path
from .params import TraceParams

#: Rings with fewer vertices are never judged for circularity. Not because a
#: triangle could sneak through — fit_circle probes segment midpoints, and the
#: middle of an edge sits far off any circle through the corners — but because
#: below a handful of vertices the question is not worth asking.
_MIN_CIRCLE_VERTICES = 8


@dataclass(slots=True)
class VectorSnapReport:
    """What the vector-snap pass changed, for the status line."""

    segments_axis_snapped: int = 0
    """Segments made exactly horizontal or vertical."""

    corners_right_angled: int = 0
    """Corners moved onto a true 90 degrees."""

    values_merged: int = 0
    """Distinct coordinate values collapsed onto a shared one."""

    circles_snapped: int = 0
    """Rings claimed as whole circles."""

    @property
    def total(self) -> int:
        return (
            self.segments_axis_snapped
            + self.corners_right_angled
            + self.values_merged
            + self.circles_snapped
        )


def snap_vectors(paths: list[Path], params: TraceParams) -> VectorSnapReport:
    """Regularise every ring of every path, in place; report what changed."""
    report = VectorSnapReport()
    if not paths:
        return report

    if params.snap_circle_mm > 0:
        report.circles_snapped = _snap_circles(paths, params.snap_circle_mm)
    if params.snap_axis_deg > 0:
        report.segments_axis_snapped = _snap_axes(paths, params)
    if params.snap_right_angle_deg > 0:
        report.corners_right_angled = _snap_right_angles(paths, params)
    if params.snap_merge_mm > 0:
        report.values_merged = _merge_values(paths, params.snap_merge_mm)
    return report


def _editable_rings(path: Path):
    """Yield the ring arrays a regularisation pass may still touch.

    Rings a circle fit has claimed export as a single CIRCLE entity, and
    rings carrying fitted arcs have already been judged curves — bending
    either with per-segment snapping would undo a decision already made.
    """
    for index, ring in enumerate(path.rings()):
        if index in path.circles or index in path.bulges:
            continue
        yield ring


# ---------------------------------------------------------------------------
# Stage 1: near-circles
# ---------------------------------------------------------------------------

def _snap_circles(paths: list[Path], tol: float) -> int:
    """Claim every ring that sits within ``tol`` of a whole circle.

    ``fit_circle`` already refuses rings that do not close a full turn and
    probes segment midpoints, so a square or triangle cannot sneak through.
    """
    claimed = 0
    for path in paths:
        for index, ring in enumerate(path.rings()):
            if index in path.circles or index in path.bulges:
                continue
            if len(ring) < _MIN_CIRCLE_VERTICES:
                continue
            circle = fit_circle(ring, tol)
            if circle is not None:
                path.circles[index] = circle
                claimed += 1
    return claimed


# ---------------------------------------------------------------------------
# Stage 2: axis snapping
# ---------------------------------------------------------------------------

def _snap_axes(paths: list[Path], params: TraceParams) -> int:
    """Make near-horizontal segments exactly horizontal, near-vertical exact.

    Both endpoints move to the mean of their shared coordinate: gentler than
    dragging one endpoint the whole way, and the segment keeps its length.
    """
    axis_deg = params.snap_axis_deg
    min_segment = params.snap_min_segment_mm
    snapped = 0

    for path in paths:
        for ring in _editable_rings(path):
            count = len(ring)
            if count < 3:
                continue
            for index in range(count):
                nxt = (index + 1) % count
                dx = float(ring[nxt, 0] - ring[index, 0])
                dy = float(ring[nxt, 1] - ring[index, 1])
                if math.hypot(dx, dy) < min_segment:
                    # Noise, not an edge: its angle is meaningless.
                    continue
                angle = math.degrees(math.atan2(abs(dy), abs(dx)))
                deviation = min(angle, 90.0 - angle)
                if deviation <= 0.0 or deviation > axis_deg:
                    # Already exact, or a genuine diagonal.
                    continue
                if abs(dx) >= abs(dy):
                    shared = (ring[index, 1] + ring[nxt, 1]) / 2.0
                    ring[index, 1] = shared
                    ring[nxt, 1] = shared
                else:
                    shared = (ring[index, 0] + ring[nxt, 0]) / 2.0
                    ring[index, 0] = shared
                    ring[nxt, 0] = shared
                snapped += 1

    return snapped


# ---------------------------------------------------------------------------
# Stage 3: right angles
# ---------------------------------------------------------------------------

def _snap_right_angles(paths: list[Path], params: TraceParams) -> int:
    """Move corners that are within tolerance of square to exactly square.

    The chord across the corner is left untouched; only the corner itself
    moves, and only as far as the nearest point from which the chord subtends
    a true right angle.
    """
    right_deg = params.snap_right_angle_deg
    min_segment = params.snap_min_segment_mm
    corners = 0

    for path in paths:
        for ring in _editable_rings(path):
            count = len(ring)
            if count < 3:
                continue
            for index in range(count):
                prev = ring[index - 1]  # ring[-1] wraps the seam
                here = ring[index]
                nxt = ring[(index + 1) % count]
                to_prev = prev - here
                to_next = nxt - here
                len_prev = float(np.hypot(to_prev[0], to_prev[1]))
                len_next = float(np.hypot(to_next[0], to_next[1]))
                if len_prev < min_segment or len_next < min_segment:
                    continue

                cos_angle = (
                    float(np.dot(to_prev, to_next)) / (len_prev * len_next)
                )
                # Near a square corner |cos| is the sine of the miss, which is
                # the numerically stable way to measure a deviation from 90.
                deviation = math.degrees(math.asin(min(1.0, abs(cos_angle))))
                if deviation <= 0.0 or deviation > right_deg:
                    continue

                middle = (prev + nxt) / 2.0
                offset = here - middle
                dist = float(np.hypot(offset[0], offset[1]))
                if dist < 1e-12:
                    continue
                span = nxt - prev
                radius = float(np.hypot(span[0], span[1])) / 2.0
                ring[index] = middle + offset * (radius / dist)
                corners += 1

    return corners


# ---------------------------------------------------------------------------
# Stage 4: global merge
# ---------------------------------------------------------------------------

def _merge_values(paths: list[Path], tol: float) -> int:
    """Collapse near-equal x coordinates onto one value, then y likewise.

    The pools are global — every editable ring of every path at once — so two
    stems meant to line up do, even when no single shape contains both. Each
    pool is clustered by chaining: sorted values join the same cluster while
    each sits within ``tol`` of its neighbour, and a cluster's members take
    its mean. Both endpoints of an axis-snapped segment carry one identical
    float, so they always land in one cluster and stay exactly aligned.
    """
    rings = [
        ring
        for path in paths
        for ring in _editable_rings(path)
        if len(ring) >= 3
    ]
    if not rings:
        return 0

    stacked = np.vstack(rings)
    lengths = [len(ring) for ring in rings]
    collapsed = 0

    for axis in (0, 1):
        values, inverse = np.unique(stacked[:, axis], return_inverse=True)
        means, clusters = _cluster_means(values, tol)
        collapsed += int(len(values)) - clusters
        inverses = np.split(inverse, np.cumsum(lengths)[:-1])
        for ring, ring_inverse in zip(rings, inverses):
            ring[:, axis] = means[ring_inverse]

    return collapsed


def _cluster_means(values: np.ndarray, tol: float) -> tuple[np.ndarray, int]:
    """The mean of each chained cluster, per value; and the cluster count."""
    means = values.copy()
    clusters = 0
    start = 0
    for index in range(1, len(values) + 1):
        if index == len(values) or values[index] - values[index - 1] > tol:
            means[start:index] = values[start:index].mean()
            clusters += 1
            start = index
    return means, clusters
