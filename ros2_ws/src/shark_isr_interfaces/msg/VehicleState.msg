# VehicleState.msg — Unified vehicle telemetry published by the autopilot bridge
#
# Published by:  shark_isr_autopilot  (derived from PX4 uXRCE-DDS topics)
# Subscribed by: shark_isr_perception, shark_isr_guidance,
#                shark_isr_mission, shark_isr_telemetry
#
# All other packages MUST subscribe to this message rather than raw px4_msgs topics.
# This is the ADR-002 firmware-agnostic boundary (see ADR-007).
#
# Coordinate frames
#   position_enu_m     : ENU local frame, origin = home at arm [m]
#   velocity_enu_m_s   : ENU frame [m/s]
#   attitude_q         : body-FLU → ENU-world quaternion (ROS 2 REP-103 orientation)
#   latitude_deg /
#   longitude_deg      : WGS-84 [deg]
#   altitude_amsl_m    : AMSL [m]
#   agl_m              : above-ground-level [m] — used by perception for geolocation
#
# Frame conversion: shark_isr_autopilot converts PX4 NED/FRD → ENU/FLU.
# No other package touches px4_msgs coordinate frames.

std_msgs/Header header          # stamp = latest autopilot estimate; frame_id = "odom"

# ── Local position (ENU, rel home) ───────────────────────────────────────────
geometry_msgs/Point position_enu_m      # x=East [m], y=North [m], z=Up [m above home]
float32 position_h_std_m               # [m] horizontal 1-sigma uncertainty

# ── Geographic position (WGS-84) ─────────────────────────────────────────────
float64 latitude_deg
float64 longitude_deg
float32 altitude_amsl_m                # [m] AMSL

# ── Velocity (ENU) ───────────────────────────────────────────────────────────
geometry_msgs/Vector3 velocity_enu_m_s # x=East [m/s], y=North [m/s], z=Up [m/s]
float32 groundspeed_m_s                # [m/s] horizontal magnitude

# ── Attitude ─────────────────────────────────────────────────────────────────
# Quaternion: body FLU frame → ENU world frame (standard ROS orientation —
# rotates body-frame vectors into the world frame; REP-103)
geometry_msgs/Quaternion attitude_q

# ── AGL — used by perception for geolocation transform ───────────────────────
float32 agl_m                          # [m] above ground level
bool    agl_valid                      # true if source is reliable (rangefinder or GPS+terrain)

# ── VTOL flight phase ─────────────────────────────────────────────────────────
uint8 VTOL_PHASE_UNDEFINED    = 0
uint8 VTOL_PHASE_HOVER        = 1     # multicopter / hovering
uint8 VTOL_PHASE_TRANS_TO_FW  = 2     # transitioning to fixed-wing
uint8 VTOL_PHASE_TRANS_TO_MC  = 3     # transitioning to multicopter
uint8 VTOL_PHASE_FIXED_WING   = 4     # fixed-wing cruise
uint8 vtol_phase

# ── Power ─────────────────────────────────────────────────────────────────────
float32 battery_fraction               # [0.0, 1.0] remaining capacity (SOC)
float32 battery_voltage_v              # [V] pack voltage

# ── Status flags ──────────────────────────────────────────────────────────────
bool armed
bool offboard_active                   # true = PX4 in Offboard mode (ROS 2 commanding)
bool position_valid                    # true = local position estimate is good
