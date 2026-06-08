# GuidanceSetpoint.msg — Outer-loop position / velocity / orbit setpoint
#
# Published by:  shark_isr_guidance
# Subscribed by: shark_isr_autopilot
#                (translates to PX4 OffboardControlMode + TrajectorySetpoint)
#
# Coordinate frames
#   position_enu_m     : ENU local frame, origin = home at arm [m]
#   velocity_enu_m_s   : ENU frame [m/s]
#   yaw_rad            : ENU convention — 0 = East, positive counter-clockwise
#                        shark_isr_autopilot converts to PX4 NED (0=North, CW+)
#
# NOTE: shark_isr_autopilot is the sole translator of ENU→NED and FLU→FRD.
# No other package should perform or assume these conversions.

std_msgs/Header header          # stamp = command time; frame_id = "odom" (ENU, home-rel)

# ── Setpoint type ─────────────────────────────────────────────────────────────
uint8 TYPE_POSITION = 0         # fly to position_enu_m
uint8 TYPE_VELOCITY = 1         # velocity command (search sweeps)
uint8 TYPE_ORBIT    = 2         # orbit around position_enu_m with orbit_* params
uint8 setpoint_type

# ── Position (TYPE_POSITION and TYPE_ORBIT centre) ───────────────────────────
geometry_msgs/Point position_enu_m      # x=East [m], y=North [m], z=Up [m above home]

# ── Velocity (TYPE_VELOCITY) ─────────────────────────────────────────────────
geometry_msgs/Vector3 velocity_enu_m_s  # x=East [m/s], y=North [m/s], z=Up [m/s]

# ── Heading ───────────────────────────────────────────────────────────────────
# Use float('nan') for both fields to let the autopilot choose heading freely.
float32 yaw_rad                 # [rad] ENU (0=East, CCW+); NaN = auto
float32 yaw_rate_rad_s          # [rad/s] feed-forward yaw rate (used in TYPE_ORBIT); NaN = auto

# ── Orbit parameters (TYPE_ORBIT) ────────────────────────────────────────────
float32 orbit_radius_m          # [m] orbit radius, must be > 0
bool    orbit_clockwise         # true = clockwise when viewed from above

# ── Execution constraints ─────────────────────────────────────────────────────
float32 cruise_speed_m_s        # [m/s] desired cruise speed; 0.0 = use autopilot default
