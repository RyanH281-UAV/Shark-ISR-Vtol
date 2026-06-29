# SearchState.msg — Guidance layer state summary
#
# Published by:  shark_isr_guidance
# Subscribed by: shark_isr_mission, shark_isr_telemetry
#
# Coordinate frames
#   current_target_enu_m  : ENU local frame, origin = home [m]
#   orbit_centre_enu_m    : ENU local frame, origin = home [m]
#   tracked_lat/lon_deg   : WGS-84 [deg]

std_msgs/Header header          # stamp = last state update

# ── Mission phase ─────────────────────────────────────────────────────────────
uint8 PHASE_IDLE    = 0
uint8 PHASE_TRANSIT = 1
uint8 PHASE_SEARCH  = 2         # executing search pattern
uint8 PHASE_TRACK   = 3         # orbiting a detected target
uint8 PHASE_RETURN  = 4
uint8 phase

# ── Search coverage metrics ───────────────────────────────────────────────────
float32 coverage_fraction       # [0.0, 1.0] fraction of search area observed
float32 map_max_probability     # [0.0, 1.0] peak cell probability (Bayesian map)
float32 map_mean_probability    # [0.0, 1.0] mean cell probability

# ── Time tracking ─────────────────────────────────────────────────────────────
float32 time_on_station_s       # [s] elapsed in SEARCH or TRACK phase

# ── Current guidance target (ENU frame, rel home) ────────────────────────────
geometry_msgs/Point current_target_enu_m   # x=East [m], y=North [m], z=Up [m]

# ── Track state (valid only when phase == PHASE_TRACK) ───────────────────────
bool target_locked
float64 tracked_lat_deg         # [deg] WGS-84 of tracked target
float64 tracked_lon_deg         # [deg] WGS-84 of tracked target
geometry_msgs/Point orbit_centre_enu_m  # ENU orbit centre
float32 orbit_radius_m          # [m] current orbit radius
