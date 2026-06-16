"""
frame_transforms.py — Pure-math NED/FRD ↔ ENU/FLU conversions (no ROS deps).

PX4 internal convention: NED world frame (x=North, y=East, z=Down),
                         FRD body frame  (x=Forward, y=Right, z=Down).
ROS 2 REP-103 convention: ENU world frame (x=East, y=North, z=Up),
                           FLU body frame  (x=Forward, y=Left, z=Up).

All functions are pure Python (math only) so they can be unit-tested without
a ROS 2 installation.  See test/test_frame_transforms.py.

Frame conversion chain (ADR-008):
  shark_isr_autopilot performs ALL NED↔ENU and FRD↔FLU conversions.
  No other package touches PX4 coordinate conventions.
"""

import math


# ── Position / velocity ──────────────────────────────────────────────────────

def ned_to_enu(x_ned: float, y_ned: float, z_ned: float) -> tuple[float, float, float]:
    """NED (x=N, y=E, z=D) → ENU (x=E, y=N, z=U)."""
    return y_ned, x_ned, -z_ned


def enu_to_ned(x_enu: float, y_enu: float, z_enu: float) -> tuple[float, float, float]:
    """ENU (x=E, y=N, z=U) → NED (x=N, y=E, z=D)."""
    return y_enu, x_enu, -z_enu


# ── Yaw / heading ────────────────────────────────────────────────────────────

def yaw_enu_to_ned(yaw_enu: float) -> float:
    """Convert ENU yaw (0=East, CCW+) [rad] to NED yaw (0=North, CW+) [rad].

    ENU yaw = 0 → East → NED yaw = π/2 (East from North, measured CW).
    Formula: yaw_ned = π/2 − yaw_enu, wrapped to (−π, π].
    """
    yaw_ned = math.pi / 2.0 - yaw_enu
    return _wrap_pi(yaw_ned)


def yaw_ned_to_enu(yaw_ned: float) -> float:
    """Convert NED yaw (0=North, CW+) [rad] to ENU yaw (0=East, CCW+) [rad]."""
    yaw_enu = math.pi / 2.0 - yaw_ned
    return _wrap_pi(yaw_enu)


def _wrap_pi(angle: float) -> float:
    """Wrap angle to (-π, π]."""
    angle = angle % (2.0 * math.pi)
    if angle > math.pi:
        angle -= 2.0 * math.pi
    return angle


# ── Quaternion arithmetic ─────────────────────────────────────────────────────

def _qmul(q1: tuple, q2: tuple) -> tuple:
    """Hamilton product q1 ⊗ q2.  Each quaternion is (w, x, y, z)."""
    w1, x1, y1, z1 = q1
    w2, x2, y2, z2 = q2
    return (
        w1*w2 - x1*x2 - y1*y2 - z1*z2,
        w1*x2 + x1*w2 + y1*z2 - z1*y2,
        w1*y2 - x1*z2 + y1*w2 + z1*x2,
        w1*z2 + x1*y2 - y1*x2 + z1*w2,
    )


def _qconj(q: tuple) -> tuple:
    """Quaternion conjugate (= inverse for unit quaternions). (w, x, y, z)."""
    w, x, y, z = q
    return (w, -x, -y, -z)


# ── Attitude quaternion conversion ────────────────────────────────────────────

# Precomputed fixed rotation quaternions (w, x, y, z):
#
# q_ENU_NED: 180° rotation about [1,1,0]/√2.
#   Maps NED basis vectors → ENU: N→y_ENU, E→x_ENU, D→(-z_ENU).
#   Verified: q(0, 1/√2, 1/√2, 0) ✓
_SQRT2_INV = 1.0 / math.sqrt(2.0)
_Q_ENU_NED = (0.0, _SQRT2_INV, _SQRT2_INV, 0.0)

# q_FRD_FLU: 180° rotation about x-axis.
#   Maps FRD body axes → FLU: F→F, R→(-L), D→(-U).
_Q_FRD_FLU = (0.0, 1.0, 0.0, 0.0)

# Inverse (conjugate) of q_FRD_FLU used in the conversion formula.
_Q_FRD_FLU_INV = _qconj(_Q_FRD_FLU)


def att_ned_frd_to_enu_flu(w: float, x: float, y: float, z: float) -> tuple[float, float, float, float]:
    """Convert PX4 attitude quaternion (world=NED, body=FRD) to ROS 2 (world=ENU, body=FLU).

    Formula: q_ENU_FLU = q_ENU_NED ⊗ q_NED_FRD ⊗ q_FRD_FLU⁻¹

    Args:
        w, x, y, z: unit quaternion from PX4 VehicleAttitude (NED world, FRD body).

    Returns:
        (w, x, y, z) unit quaternion for ROS 2 geometry_msgs/Quaternion (ENU world, FLU body).
    """
    q_ned_frd = (w, x, y, z)
    q_enu_flu = _qmul(_qmul(_Q_ENU_NED, q_ned_frd), _Q_FRD_FLU_INV)
    return q_enu_flu


def att_enu_flu_to_ned_frd(w: float, x: float, y: float, z: float) -> tuple[float, float, float, float]:
    """Inverse of att_ned_frd_to_enu_flu.  Used when converting ROS setpoints → PX4."""
    q_enu_flu = (w, x, y, z)
    # q_NED_FRD = q_ENU_NED⁻¹ ⊗ q_ENU_FLU ⊗ q_FRD_FLU
    q_ned_frd = _qmul(_qmul(_qconj(_Q_ENU_NED), q_enu_flu), _Q_FRD_FLU)
    return q_ned_frd


