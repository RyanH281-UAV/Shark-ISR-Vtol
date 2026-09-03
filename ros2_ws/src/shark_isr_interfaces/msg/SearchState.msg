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
# coverage_fraction: fraction of cells within the hard revisit bound (fresh
# enough), NOT cumulative ever-swept coverage — that number only ever rises
# and pegs at 1.0 forever after the first full sweep (ADR-018).
float32 coverage_fraction       # [0.0, 1.0] fraction of search area "fresh"
float32 map_max_probability     # [0.0, 1.0] peak cell probability (Bayesian map)
# ADR-018: replaces map_mean_probability, which was mathematically constant
# (always 1/n_cells — the mean of any distribution over n cells that sums to
# 1) and therefore carried no information. This is the number that actually
# reflects the hard revisit bound, the project's stated differentiator.
float32 max_cell_age_s          # [s] staleness of the stalest cell in the map

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
