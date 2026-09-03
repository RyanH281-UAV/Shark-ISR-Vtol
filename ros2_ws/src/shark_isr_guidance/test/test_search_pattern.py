"""Unit tests for search_pattern.py — no ROS 2 required."""

import math
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from shark_isr_guidance.search_pattern import (
    Waypoint,
    SearchRegion,
    boustrophedon_strip,
    check_feasibility,
    distance_to_waypoint,
)

TOL = 1e-9


# ── distance_to_waypoint ──────────────────────────────────────────────────────

def test_distance_zero_at_waypoint():
    wp = Waypoint(east=10.0, north=20.0, up=50.0)
    assert abs(distance_to_waypoint(10.0, 20.0, wp)) < TOL


def test_distance_pythagorean():
    wp = Waypoint(east=3.0, north=4.0, up=0.0)
    assert abs(distance_to_waypoint(0.0, 0.0, wp) - 5.0) < TOL


# ── boustrophedon_strip (shore-parallel) ──────────────────────────────────────

def _strip(length=500.0, width=200.0, bearing=0.0):
    return SearchRegion(0.0, 0.0, length, width, bearing, 50.0)


def test_strip_waypoints_inside_region():
    region = _strip()
    wps = boustrophedon_strip(region, 60.0)
    assert len(wps) >= 2
    for wp in wps:
        assert region.contains(wp.east, wp.north), f'{wp} outside strip'


def test_strip_legs_run_along_shore():
    """In the local frame each lane's two endpoints share a cross-shore y and
    span the full along-shore length (legs run ALONG the shore)."""
    region = _strip(length=500.0, width=200.0, bearing=0.0)
    wps = boustrophedon_strip(region, 50.0)
    for i in range(0, len(wps) - 1, 2):
        x0, y0 = region.world_to_local(wps[i].east, wps[i].north)
        x1, y1 = region.world_to_local(wps[i + 1].east, wps[i + 1].north)
        assert abs(y0 - y1) < 1e-6                       # same lane (constant y)
        assert abs(abs(x0) - 250.0) < 1e-6               # endpoints at ±L/2
        assert abs(abs(x1) - 250.0) < 1e-6


def test_strip_no_cross_shore_gaps():
    """Every cross-shore position in the strip is within half a swath of a lane —
    no uncovered band ('nothing missed')."""
    region = _strip(length=400.0, width=200.0, bearing=0.7)
    swath = 60.0
    wps = boustrophedon_strip(region, swath)
    lane_ys = sorted({round(region.world_to_local(wp.east, wp.north)[1], 6) for wp in wps})
    for k in range(201):
        y = -region.width_m / 2.0 + k * (region.width_m / 200.0)
        gap = min(abs(y - ly) for ly in lane_ys)
        assert gap <= swath / 2.0 + 1e-6, f'cross-shore gap {gap:.2f} at y={y:.1f}'


def test_strip_rotation_bearing_90_runs_north():
    """Shore bearing 90° (north) → legs run north-south in ENU (east≈const per lane)."""
    region = _strip(length=300.0, width=100.0, bearing=math.pi / 2)
    wps = boustrophedon_strip(region, 50.0)
    # First leg endpoints should differ mostly in north, not east.
    a, b = wps[0], wps[1]
    assert abs(a.east - b.east) < 1e-6
    assert abs(abs(a.north - b.north) - 300.0) < 1e-6


# ── check_feasibility ─────────────────────────────────────────────────────────

def test_feasibility_pass():
    ok, t_loop, reason = check_feasibility(
        length_m=500.0, width_m=200.0, strip_width_m=60.0,
        cruise_speed_m_s=15.0, turn_radius_m=30.0,
        revisit_bound_s=300.0, endurance_s=2400.0,
    )
    assert ok is True
    assert reason == ''
    assert t_loop < 300.0


def test_feasibility_fail_revisit_bound():
    ok, t_loop, reason = check_feasibility(
        length_m=5000.0, width_m=2000.0, strip_width_m=60.0,
        cruise_speed_m_s=15.0, turn_radius_m=30.0,
        revisit_bound_s=60.0, endurance_s=6000.0,
    )
    assert ok is False
    assert t_loop > 60.0
    assert 'revisit bound' in reason


def test_feasibility_fail_zero_speed():
    ok, t_loop, reason = check_feasibility(
        length_m=500.0, width_m=200.0, strip_width_m=60.0,
        cruise_speed_m_s=0.0, turn_radius_m=30.0,
        revisit_bound_s=300.0, endurance_s=2400.0,
    )
    assert ok is False
    assert 'cruise_speed' in reason
