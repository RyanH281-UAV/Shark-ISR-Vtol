"""
test_geolocate.py — Unit tests for geolocate.geolocate().

All tests use known geometry (level flight, identity or simple quaternions) so the
expected outputs are derivable by hand.  No ROS or simulator required.

Camera: 640×480, fx=fy=616, cx=320, cy=240.
Camera mount: nadir (straight down), image top = body +x (forward).
Frame: body FLU → ENU world quaternion (standard ROS orientation, REP-103),
matching what shark_isr_autopilot publishes in VehicleState.attitude_q.

Quaternion conventions:
  q = (qx, qy, qz, qw), body→world
  Heading East  (body +x = ENU +x): q = (0, 0, 0, 1)    — identity
  Heading North (body +x = ENU +y): q = (0, 0, +√½, √½) — Rz(+90°) body→world
  Roll +20° heading East:           q = (sin10°, 0, 0, cos10°)

Tolerance: 0.5 m for position, 5 m for position_std_m.
"""

import math
import pytest
import sys
import os

# Make the package importable without a full colcon build
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from shark_isr_perception.geolocate import geolocate  # noqa: E402


# Shared camera intrinsics
CAM = dict(img_w=640, img_h=480, fx=616.0, fy=616.0, cx=320.0, cy=240.0)

# Quaternions (qx, qy, qz, qw) — body FLU → ENU world
Q_EAST = (0.0, 0.0, 0.0, 1.0)                                  # heading East  (identity)
Q_NORTH = (0.0, 0.0, math.sqrt(0.5), math.sqrt(0.5))           # heading North (Rz +90°)
# Roll +20° about body +x while heading East (left wing up, camera looks North)
_HALF_ROLL = math.radians(20.0) / 2.0
Q_ROLL20_EAST = (math.sin(_HALF_ROLL), 0.0, 0.0, math.cos(_HALF_ROLL))


def _m_to_deg_lat(metres: float) -> float:
    return metres / 111_320.0


def _m_to_deg_lon(metres: float, lat_deg: float) -> float:
    return metres / (111_320.0 * math.cos(math.radians(lat_deg)))


# ── Test 1: centre bbox → target directly below ──────────────────────────────

def test_centre_bbox_heading_east():
    """Image centre at any heading → detection directly below the vehicle."""
    lat, lon, std = geolocate(
        bbox_cx_norm=0.5, bbox_cy_norm=0.5,
        **CAM,
        vehicle_lat_deg=0.0, vehicle_lon_deg=0.0,
        agl_m=30.0,
        attitude_qxyzw=Q_EAST,
    )
    assert abs(lat) < 1e-5, f"Expected lat≈0, got {lat}"
    assert abs(lon) < 1e-5, f"Expected lon≈0, got {lon}"


def test_centre_bbox_heading_north():
    """Centre bbox with heading North also gives detection directly below."""
    lat, lon, std = geolocate(
        bbox_cx_norm=0.5, bbox_cy_norm=0.5,
        **CAM,
        vehicle_lat_deg=0.0, vehicle_lon_deg=0.0,
        agl_m=30.0,
        attitude_qxyzw=Q_NORTH,
    )
    assert abs(lat) < 1e-5, f"Expected lat≈0, got {lat}"
    assert abs(lon) < 1e-5, f"Expected lon≈0, got {lon}"


# ── Test 2: heading East, detection right of centre → South of vehicle ────────

def test_right_of_centre_heading_east():
    """
    Heading East: image right = body -y = South.
    Detection at (0.75, 0.5): u=480, u-cx=160, v-cy=0.
    ray_cam = [160/616, 0, 1].
    ray_body = [cam_y=0, -cam_x=-160/616, -cam_z=-1] → [0, -0.2597, -1.0].
    ENU = body (identity q): East=0, North=-0.2597, Up=-1.0.
    t = 30 / 1.0 = 30.
    dy_north = 30 × (-0.2597) ≈ -7.79 m South.
    """
    lat, lon, std = geolocate(
        bbox_cx_norm=0.75, bbox_cy_norm=0.5,
        **CAM,
        vehicle_lat_deg=0.0, vehicle_lon_deg=0.0,
        agl_m=30.0,
        attitude_qxyzw=Q_EAST,
    )
    expected_south_m = 30.0 * (160.0 / 616.0)   # ≈ 7.79 m
    expected_dlat = -_m_to_deg_lat(expected_south_m)
    assert abs(lat - expected_dlat) < _m_to_deg_lat(0.5), (
        f"Expected lat≈{expected_dlat:.6f} (≈{expected_south_m:.1f} m South), got {lat:.6f}"
    )
    assert abs(lon) < _m_to_deg_lon(0.5, 0.0), f"Expected lon≈0, got {lon}"


# ── Test 3: heading East, detection below centre → West of vehicle ────────────

def test_below_centre_heading_east():
    """
    Heading East: image down = body +x forward = East.
    Detection at (0.5, 0.75): u-cx=0, v=360, v-cy=120.
    ray_cam = [0, 120/616, 1].
    ray_body = [cam_y=120/616, -cam_x=0, -cam_z=-1] → [0.1948, 0, -1.0].
    ENU = body (identity q): East=0.1948, North=0, Up=-1.
    t = 30 / 1.0 = 30.
    dx_east = 30 × 0.1948 ≈ 5.84 m East.
    """
    lat, lon, std = geolocate(
        bbox_cx_norm=0.5, bbox_cy_norm=0.75,
        **CAM,
        vehicle_lat_deg=0.0, vehicle_lon_deg=0.0,
        agl_m=30.0,
        attitude_qxyzw=Q_EAST,
    )
    expected_east_m = 30.0 * (120.0 / 616.0)   # ≈ 5.84 m East
    expected_dlon = _m_to_deg_lon(expected_east_m, 0.0)
    assert abs(lat) < _m_to_deg_lat(0.5), f"Expected lat≈0, got {lat}"
    assert abs(lon - expected_dlon) < _m_to_deg_lon(0.5, 0.0), (
        f"Expected lon≈{expected_dlon:.6f} ({expected_east_m:.1f} m East), got {lon:.6f}"
    )


# ── Test 3b: convention-sensitive — heading North, detection right of centre ──

def test_right_of_centre_heading_north():
    """
    Heading North (body x = ENU +y): image right = body -y = East.
    A yaw-only quaternion with a nadir centre ray cannot distinguish
    body→world from world→body; this off-centre case can.
    Detection at (0.75, 0.5): ray_body = [0, -160/616, -1].
    Rz(+90°) body→world: (x, y, z) → (-y, x, z) → [+0.2597, 0, -1] = East.
    Expected: ≈7.79 m EAST of vehicle, zero north offset.
    """
    lat, lon, std = geolocate(
        bbox_cx_norm=0.75, bbox_cy_norm=0.5,
        **CAM,
        vehicle_lat_deg=0.0, vehicle_lon_deg=0.0,
        agl_m=30.0,
        attitude_qxyzw=Q_NORTH,
    )
    expected_east_m = 30.0 * (160.0 / 616.0)   # ≈ 7.79 m
    expected_dlon = _m_to_deg_lon(expected_east_m, 0.0)
    assert abs(lon - expected_dlon) < _m_to_deg_lon(0.5, 0.0), (
        f"Expected lon≈{expected_dlon:.6f} ({expected_east_m:.1f} m East), got {lon:.6f}"
    )
    assert abs(lat) < _m_to_deg_lat(0.5), f"Expected lat≈0, got {lat}"


# ── Test 3c: convention-sensitive — 20° roll, centre bbox ─────────────────────

def test_roll_20deg_centre_bbox():
    """
    Heading East with +20° roll (left wing up): camera bore tilts North.
    ray_body = [0, 0, -1]; Rx(+20°) body→world → [0, +sin20°, -cos20°].
    t = 30/cos20°; north offset = t·sin20° = 30·tan20° ≈ 10.92 m NORTH.
    The world→body (conjugate) interpretation gives -10.92 m — this test
    locks in the body→world convention.
    """
    lat, lon, std = geolocate(
        bbox_cx_norm=0.5, bbox_cy_norm=0.5,
        **CAM,
        vehicle_lat_deg=0.0, vehicle_lon_deg=0.0,
        agl_m=30.0,
        attitude_qxyzw=Q_ROLL20_EAST,
    )
    expected_north_m = 30.0 * math.tan(math.radians(20.0))   # ≈ 10.92 m
    expected_dlat = _m_to_deg_lat(expected_north_m)
    assert abs(lat - expected_dlat) < _m_to_deg_lat(0.5), (
        f"Expected lat≈{expected_dlat:.6f} (≈{expected_north_m:.1f} m North), got {lat:.6f}"
    )
    assert abs(lon) < _m_to_deg_lon(0.5, 0.0), f"Expected lon≈0, got {lon}"


# ── Test 4: AGL scales offset linearly ───────────────────────────────────────

def test_agl_scales_offset():
    """Doubling AGL should roughly double the ENU offset for the same pixel displacement."""
    _, _, _ = geolocate(
        bbox_cx_norm=0.75, bbox_cy_norm=0.5, **CAM,
        vehicle_lat_deg=0.0, vehicle_lon_deg=0.0, agl_m=15.0, attitude_qxyzw=Q_EAST,
    )
    lat30, lon30, _ = geolocate(
        bbox_cx_norm=0.75, bbox_cy_norm=0.5, **CAM,
        vehicle_lat_deg=0.0, vehicle_lon_deg=0.0, agl_m=30.0, attitude_qxyzw=Q_EAST,
    )
    lat15, lon15, _ = geolocate(
        bbox_cx_norm=0.75, bbox_cy_norm=0.5, **CAM,
        vehicle_lat_deg=0.0, vehicle_lon_deg=0.0, agl_m=15.0, attitude_qxyzw=Q_EAST,
    )
    # South offset at 30 m should be ≈ 2× south offset at 15 m
    assert abs(lat30 / lat15 - 2.0) < 0.01, (
        f"Expected lat30 ≈ 2×lat15, got ratio {lat30 / lat15:.4f}"
    )


# ── Test 5: invalid AGL raises ValueError ────────────────────────────────────

def test_zero_agl_raises():
    with pytest.raises(ValueError, match="agl_m must be positive"):
        geolocate(
            bbox_cx_norm=0.5, bbox_cy_norm=0.5, **CAM,
            vehicle_lat_deg=0.0, vehicle_lon_deg=0.0, agl_m=0.0, attitude_qxyzw=Q_EAST,
        )


def test_negative_agl_raises():
    with pytest.raises(ValueError, match="agl_m must be positive"):
        geolocate(
            bbox_cx_norm=0.5, bbox_cy_norm=0.5, **CAM,
            vehicle_lat_deg=0.0, vehicle_lon_deg=0.0, agl_m=-5.0, attitude_qxyzw=Q_EAST,
        )


# ── Test 6: position_std_m is positive and reasonable ────────────────────────

def test_position_std_positive():
    _, _, std = geolocate(
        bbox_cx_norm=0.5, bbox_cy_norm=0.5, **CAM,
        vehicle_lat_deg=0.0, vehicle_lon_deg=0.0, agl_m=30.0, attitude_qxyzw=Q_EAST,
    )
    assert std > 0.0, f"position_std_m must be positive, got {std}"
    assert std < 50.0, f"position_std_m unexpectedly large at 30 m AGL: {std}"


# ── Test 7: non-zero vehicle lat/lon shifts output correctly ──────────────────

def test_offset_from_nonzero_vehicle_position():
    """Vehicle at 31.9°S, 115.8°E (Cottesloe), centre bbox → same coords."""
    lat, lon, _ = geolocate(
        bbox_cx_norm=0.5, bbox_cy_norm=0.5, **CAM,
        vehicle_lat_deg=-31.9, vehicle_lon_deg=115.8,
        agl_m=30.0, attitude_qxyzw=Q_EAST,
    )
    assert abs(lat - (-31.9)) < 1e-4, f"Expected lat≈-31.9, got {lat}"
    assert abs(lon - 115.8) < 1e-4, f"Expected lon≈115.8, got {lon}"
