"""
Unit tests for frame_transforms.py — no ROS 2 required.

Run from the repo root (or any directory):
    python -m pytest ros2_ws/src/shark_isr_autopilot/test/test_frame_transforms.py -v

These tests cover the deterministic math in frame_transforms.py so that
correctness can be verified without a simulator.  The tested functions are
pure Python (no ROS deps).
"""

import math
import sys
import os

# Allow import without a ROS workspace sourced
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from shark_isr_autopilot.frame_transforms import (
    att_ned_frd_to_enu_flu,
    att_enu_flu_to_ned_frd,
    ned_to_enu,
    enu_to_ned,
    yaw_enu_to_ned,
    yaw_ned_to_enu,
)

TOL = 1e-9


# ── Position / velocity ──────────────────────────────────────────────────────

def test_ned_to_enu_cardinal_directions():
    """North → y_ENU, East → x_ENU, Down → -z_ENU."""
    assert ned_to_enu(1, 0, 0) == (0, 1, 0)   # North → y
    assert ned_to_enu(0, 1, 0) == (1, 0, 0)   # East  → x
    assert ned_to_enu(0, 0, 1) == (0, 0, -1)  # Down  → -z (Up)


def test_enu_to_ned_cardinal_directions():
    """East → x_NED=0, y_NED=1, z_NED=0."""
    assert enu_to_ned(1, 0, 0) == (0, 1, 0)   # East  → y_NED
    assert enu_to_ned(0, 1, 0) == (1, 0, 0)   # North → x_NED
    assert enu_to_ned(0, 0, 1) == (0, 0, -1)  # Up    → -z_NED (Down)


def test_ned_enu_roundtrip():
    """ned_to_enu(enu_to_ned(p)) == p."""
    pts = [(1, 2, 3), (-5, 0, 7), (0, 0, 0), (100, -50, -10)]
    for p in pts:
        assert enu_to_ned(*ned_to_enu(*p)) == pytest_approx(p)


# ── Yaw conversion ────────────────────────────────────────────────────────────

def test_yaw_enu_east_is_ned_northeast():
    """ENU yaw=0 (East) → NED yaw=π/2 (East from North)."""
    assert abs(yaw_enu_to_ned(0.0) - math.pi / 2.0) < TOL


def test_yaw_enu_north_is_ned_zero():
    """ENU yaw=π/2 (North) → NED yaw=0."""
    assert abs(yaw_enu_to_ned(math.pi / 2.0)) < TOL


def test_yaw_enu_west():
    """ENU yaw=π (West) → NED yaw=-π/2 (West from North)."""
    assert abs(yaw_enu_to_ned(math.pi) + math.pi / 2.0) < TOL


def test_yaw_roundtrip():
    """yaw_ned_to_enu(yaw_enu_to_ned(y)) ≈ y for many angles."""
    for deg in range(-180, 181, 15):
        yaw = math.radians(deg)
        roundtrip = yaw_ned_to_enu(yaw_enu_to_ned(yaw))
        diff = abs(math.sin(roundtrip - yaw))  # sin handles ±π boundary
        assert diff < TOL, f'Roundtrip failed at {deg}°: got {math.degrees(roundtrip):.6f}°'


# ── Attitude quaternion ───────────────────────────────────────────────────────

def _qrot_vec(q, v):
    """Rotate vector v by unit quaternion q = (w,x,y,z). Returns (x,y,z)."""
    w, qx, qy, qz = q
    # v' = q ⊗ (0,v) ⊗ q*
    vx, vy, vz = v
    # q ⊗ (0, vx, vy, vz)
    tw = -qx*vx - qy*vy - qz*vz
    tx = w*vx + qy*vz - qz*vy
    ty = w*vy - qx*vz + qz*vx
    tz = w*vz + qx*vy - qy*vx
    # result ⊗ q*
    ox = tx*w + tw*(-qx) + ty*(-qz) - tz*(-qy)
    oy = ty*w - tx*(-qz) + tw*(-qy) + tz*(-qx)
    oz = tz*w + tx*(-qy) - ty*(-qx) + tw*(-qz)
    return ox, oy, oz


def test_identity_attitude():
    """Identity quaternion (no rotation) converts to identity in ENU/FLU."""
    # PX4 identity = vehicle pointed North in NED world, body FRD aligned with world axes.
    # In ENU/FLU: forward = North = y_ENU, up = z_ENU.
    q_enu_flu = att_ned_frd_to_enu_flu(1.0, 0.0, 0.0, 0.0)
    # ENU/FLU: forward (FLU x) should point North (ENU y).
    forward_enu = _qrot_vec(q_enu_flu, (1, 0, 0))
    assert abs(forward_enu[0]) < TOL  # no East component
    assert abs(forward_enu[1] - 1.0) < TOL  # North
    assert abs(forward_enu[2]) < TOL  # no Up component


def test_att_roundtrip():
    """att_enu_flu_to_ned_frd(att_ned_frd_to_enu_flu(q)) ≈ q."""
    test_quats = [
        (1.0, 0.0, 0.0, 0.0),  # identity
        (0.0, 1.0, 0.0, 0.0),  # 180° about x
        (math.cos(math.pi/4), 0.0, 0.0, math.sin(math.pi/4)),  # 90° about z
    ]
    for q in test_quats:
        q_enu = att_ned_frd_to_enu_flu(*q)
        q_back = att_enu_flu_to_ned_frd(*q_enu)
        for a, b in zip(q, q_back):
            assert abs(a - b) < TOL or abs(abs(a) - abs(b)) < TOL, (
                f'Roundtrip failed: {q} → {q_enu} → {q_back}')


def test_att_unit_norm_preserved():
    """Output quaternion should remain unit norm."""
    q_in = (math.cos(0.3), math.sin(0.3)*0.6, math.sin(0.3)*0.8, 0.0)
    q_out = att_ned_frd_to_enu_flu(*q_in)
    norm = math.sqrt(sum(x**2 for x in q_out))
    assert abs(norm - 1.0) < TOL


# ── Helper for pytest approximate comparison ─────────────────────────────────

class pytest_approx:
    """Simple tuple approximate equality helper (avoids pytest dependency in __eq__)."""
    def __init__(self, expected, tol=TOL):
        self.expected = expected
        self.tol = tol

    def __eq__(self, other):
        return all(abs(a - b) < self.tol for a, b in zip(other, self.expected))
