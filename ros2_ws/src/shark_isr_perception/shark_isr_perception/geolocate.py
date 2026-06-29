"""
geolocate.py — Pinhole camera + flat-earth geolocation.

No ROS dependencies — pure numpy math so it is unit-testable without a simulator.

Camera model
------------
Standard Camera Module 3 (Sony IMX708).  Top of image = body +x (forward).

Coordinate frames
-----------------
  camera optical : +x right, +y down, +z into scene (nadir → straight down)
  body FLU       : +x forward, +y left, +z up  (ROS 2 REP-103)
  ENU world      : +x East, +y North, +z Up

  R_cam_to_body  : cam_y → body_x, -cam_x → body_y, -cam_z → body_z
  attitude_q     : quaternion body FLU → ENU world (from VehicleState.attitude_q,
                   standard ROS orientation: rotates body-frame vectors into world).

Flat-earth ground intersection
-------------------------------
Ground plane is z_ENU = 0.  Vehicle is at z_ENU = +agl_m.
Scale factor:  t = agl_m / (-ray_enu_z)
ENU offset:    (dx_east, dy_north) = t * (ray_enu_x, ray_enu_y)
Lat/lon delta: flat-earth approximation valid for offsets ≲ 1 km.
"""

from __future__ import annotations

import math

import numpy as np


# R_cam_to_body — fixed for nadir mount, image top = body forward
_R_CAM_TO_BODY = np.array(
    [
        [0.0,  1.0,  0.0],   # body_x = cam_y
        [-1.0, 0.0,  0.0],   # body_y = -cam_x
        [0.0,  0.0, -1.0],   # body_z = -cam_z
    ],
    dtype=np.float64,
)

_M_PER_DEG_LAT = 111_320.0  # metres per degree latitude (WGS-84 approx)


def _quat_rotate(v: np.ndarray, q: np.ndarray) -> np.ndarray:
    """Rotate vector v by unit quaternion q = [qx, qy, qz, qw]."""
    qx, qy, qz, qw = float(q[0]), float(q[1]), float(q[2]), float(q[3])
    qv = np.array([qx, qy, qz], dtype=np.float64)
    t = 2.0 * np.cross(qv, v)
    return v + qw * t + np.cross(qv, t)


def geolocate(
    bbox_cx_norm: float,
    bbox_cy_norm: float,
    img_w: int,
    img_h: int,
    fx: float,
    fy: float,
    cx: float,
    cy: float,
    vehicle_lat_deg: float,
    vehicle_lon_deg: float,
    agl_m: float,
    attitude_qxyzw: tuple[float, float, float, float],
) -> tuple[float, float, float]:
    """Return (lat_deg, lon_deg, position_std_m) for a detected bounding-box centre.

    Parameters
    ----------
    bbox_cx_norm, bbox_cy_norm:
        Normalised bounding-box centre, origin top-left, [0.0, 1.0].
    img_w, img_h:
        Camera image dimensions in pixels.
    fx, fy, cx, cy:
        Camera intrinsic parameters (pixels).  cx/cy = principal point.
    vehicle_lat_deg, vehicle_lon_deg:
        Vehicle WGS-84 position at detection time.
    agl_m:
        Vehicle altitude above ground level [m].  Must be > 0.
    attitude_qxyzw:
        Body-FLU → ENU-world quaternion (qx, qy, qz, qw) from VehicleState
        (standard ROS orientation convention).

    Returns
    -------
    lat_deg, lon_deg : WGS-84 position of detected target.
    position_std_m   : conservative 1-sigma horizontal uncertainty [m].

    Raises
    ------
    ValueError if the geometry is degenerate (ray parallel to ground, t < 0).
    """
    if agl_m <= 0.0:
        raise ValueError(f"agl_m must be positive, got {agl_m}")

    # 1. Pixel offset from principal point
    u = bbox_cx_norm * img_w - cx
    v = bbox_cy_norm * img_h - cy

    # 2. Ray in camera optical frame (unnormalised — projection preserves ratios)
    ray_cam = np.array([u / fx, v / fy, 1.0], dtype=np.float64)

    # 3. Rotate to body FLU (nadir mount, image top = forward)
    ray_body = _R_CAM_TO_BODY @ ray_cam

    # 4. Rotate body FLU → ENU world (attitude_q is already body→world)
    q = np.array(attitude_qxyzw, dtype=np.float64)
    ray_enu = _quat_rotate(ray_body, q)

    # 5. Intersect with ground plane (z_ENU = 0, vehicle at z_ENU = +agl_m)
    if abs(ray_enu[2]) < 1e-6:
        raise ValueError("Ray is nearly horizontal — cannot intersect ground plane.")
    t = agl_m / (-ray_enu[2])
    if t < 0.0:
        raise ValueError("Ground intersection is behind the camera (ray points up).")

    # 6. ENU offset from vehicle to target
    dx_east_m = t * ray_enu[0]
    dy_north_m = t * ray_enu[1]

    # 7. Flat-earth lat/lon conversion
    dlat = dy_north_m / _M_PER_DEG_LAT
    dlon = dx_east_m / (_M_PER_DEG_LAT * math.cos(math.radians(vehicle_lat_deg)))

    lat_out = vehicle_lat_deg + dlat
    lon_out = vehicle_lon_deg + dlon

    # 8. Conservative position uncertainty:
    #    dominant source = AGL error (assume ±2 m) scaled by footprint/AGL ratio
    #    plus a 1 m floor.
    footprint_half_m = agl_m * math.tan(math.radians(33.0))  # Standard lens half-angle
    agl_uncertainty_m = 2.0
    position_std_m = float(footprint_half_m * (agl_uncertainty_m / agl_m) + 1.0)

    return lat_out, lon_out, position_std_m
