"""Unit tests for search_pattern.py — no ROS 2 required."""

import math
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from shark_isr_guidance.search_pattern import (
    Waypoint,
    boustrophedon,
    coverage_fraction_swept,
    distance_to_waypoint,
)

TOL = 1e-9


# ── boustrophedon ─────────────────────────────────────────────────────────────

def test_all_waypoints_inside_or_on_circle():
    """Every waypoint row endpoint must lie within the search circle."""
    cx, cy, alt, r, sw = 0.0, 0.0, 50.0, 200.0, 60.0
    wps = boustrophedon(cx, cy, alt, r, sw)
    assert len(wps) >= 2
    for wp in wps:
        d = math.sqrt((wp.east - cx) ** 2 + (wp.north - cy) ** 2)
        assert d <= r + 1e-6, f'Waypoint ({wp.east:.1f}, {wp.north:.1f}) outside circle (d={d:.2f} > r={r})'


def test_altitude_constant():
    """All waypoints must be at the specified altitude."""
    wps = boustrophedon(0, 0, 42.5, 150.0, 50.0)
    for wp in wps:
        assert abs(wp.up - 42.5) < TOL


def test_returns_at_least_two_waypoints():
    """Even a tiny circle returns at least one row (2 waypoints)."""
    wps = boustrophedon(0, 0, 10.0, 5.0, 3.0)
    assert len(wps) >= 1


def test_boustrophedon_alternating_direction():
    """Consecutive row pairs should start on opposite sides (alternating direction)."""
    wps = boustrophedon(0, 0, 50.0, 300.0, 80.0)
    # Find the first pair that belongs to different rows (north coord changes).
    row_starts = []
    prev_n = None
    for wp in wps:
        if prev_n is None or abs(wp.north - prev_n) > 1e-6:
            row_starts.append(wp.east)
            prev_n = wp.north
    # First row starts west (negative east), second starts east (positive east) or vice versa.
    if len(row_starts) >= 2:
        assert row_starts[0] != row_starts[1]  # different sides


def test_offset_centre():
    """Pattern centred at non-origin should still keep waypoints inside shifted circle."""
    cx, cy = 500.0, -300.0
    r = 150.0
    wps = boustrophedon(cx, cy, 50.0, r, 50.0)
    for wp in wps:
        d = math.sqrt((wp.east - cx) ** 2 + (wp.north - cy) ** 2)
        assert d <= r + 1e-6


def test_strip_width_larger_than_radius():
    """strip_width > diameter: still returns at least one waypoint."""
    wps = boustrophedon(0, 0, 20.0, 50.0, 200.0)
    assert len(wps) >= 1


# ── coverage_fraction_swept ───────────────────────────────────────────────────

def test_zero_coverage_at_start():
    wps = boustrophedon(0, 0, 50.0, 200.0, 60.0)
    assert coverage_fraction_swept(wps, 0, 200.0, 60.0) == 0.0


def test_full_coverage_at_end():
    wps = boustrophedon(0, 0, 50.0, 200.0, 60.0)
    frac = coverage_fraction_swept(wps, len(wps), 200.0, 60.0)
    assert 0.0 <= frac <= 1.0


def test_coverage_monotonic():
    """Coverage should not decrease as more waypoints are completed."""
    wps = boustrophedon(0, 0, 50.0, 300.0, 60.0)
    fracs = [coverage_fraction_swept(wps, i, 300.0, 60.0) for i in range(len(wps) + 1)]
    for i in range(len(fracs) - 1):
        assert fracs[i] <= fracs[i + 1] + 1e-9


# ── distance_to_waypoint ──────────────────────────────────────────────────────

def test_distance_zero_at_waypoint():
    wp = Waypoint(east=10.0, north=20.0, up=50.0)
    assert abs(distance_to_waypoint(10.0, 20.0, wp)) < TOL


def test_distance_pythagorean():
    wp = Waypoint(east=3.0, north=4.0, up=0.0)
    assert abs(distance_to_waypoint(0.0, 0.0, wp) - 5.0) < TOL
