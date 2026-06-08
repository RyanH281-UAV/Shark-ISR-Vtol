# shark_isr_interfaces

**Purpose:** Custom msgs and srvs — the integration contract for the shark ISR autonomy stack.
All other packages depend only on this package; none depend on each other's internals (ADR-004).

**Status:** FROZEN — 2026-05-31. `colcon build` passes clean on ROS 2 Humble. Do not change field names, types, or units without a new ADR.

---

## Coordinate frame conventions (ADR-008)

| Frame | Convention | Used for |
|---|---|---|
| `odom` (ENU) | East-North-Up, origin = home at arm | All local position/velocity msgs |
| body FLU | Forward-Left-Up (ROS 2 REP-103) | Attitude quaternion in VehicleState |
| `camera_optical` | +x right, +y down, +z into scene | Detection.msg header |
| WGS-84 | lat [deg], lon [deg], alt AMSL [m] | Geographic coordinates |
| Heading | 0 = East, CCW positive (ENU) | GuidanceSetpoint yaw_rad |

`shark_isr_autopilot` is the **sole** translator between ENU/FLU (ROS 2) and NED/FRD (PX4).
No other package handles this conversion.

---

## Messages

### `Detection.msg`

| Field | Type | Unit / Frame | Description |
|---|---|---|---|
| `header` | `std_msgs/Header` | — | stamp = detection time; frame_id = "camera_optical" |
| `CLASS_SHARK` | `uint8 = 0` | — | Class constant |
| `object_class` | `uint8` | — | Detected class (CLASS_* constant) |
| `confidence` | `float32` | [0, 1] | HailoRT detection score |
| `bbox_x_min` | `float32` | normalised [0,1] | Left edge of bounding box (image frame) |
| `bbox_y_min` | `float32` | normalised [0,1] | Top edge |
| `bbox_x_max` | `float32` | normalised [0,1] | Right edge |
| `bbox_y_max` | `float32` | normalised [0,1] | Bottom edge |
| `geo_valid` | `bool` | — | true if geolocation succeeded |
| `latitude_deg` | `float64` | deg WGS-84 | Geolocated latitude |
| `longitude_deg` | `float64` | deg WGS-84 | Geolocated longitude |
| `altitude_amsl_m` | `float32` | m AMSL | Geolocated altitude (≈0 over sea) |
| `position_std_m` | `float32` | m (1-sigma) | Horizontal position uncertainty |

**Flow:** `shark_isr_perception` → `shark_isr_guidance`, `shark_isr_telemetry`

---

### `VehicleState.msg`

| Field | Type | Unit / Frame | Description |
|---|---|---|---|
| `header` | `std_msgs/Header` | — | stamp = PX4 estimate time; frame_id = "odom" |
| `position_enu_m` | `geometry_msgs/Point` | m ENU | x=East, y=North, z=Up above home |
| `position_h_std_m` | `float32` | m (1-sigma) | Horizontal position uncertainty |
| `latitude_deg` | `float64` | deg WGS-84 | Geographic latitude |
| `longitude_deg` | `float64` | deg WGS-84 | Geographic longitude |
| `altitude_amsl_m` | `float32` | m AMSL | Barometric/GPS altitude |
| `velocity_enu_m_s` | `geometry_msgs/Vector3` | m/s ENU | x=East, y=North, z=Up |
| `groundspeed_m_s` | `float32` | m/s | Horizontal speed magnitude |
| `attitude_q` | `geometry_msgs/Quaternion` | — | ENU world → body FLU quaternion |
| `agl_m` | `float32` | m | Above-ground-level estimate |
| `agl_valid` | `bool` | — | true if AGL source is reliable |
| `vtol_phase` | `uint8` | VTOL_PHASE_* | HOVER/TRANS_TO_FW/TRANS_TO_MC/FIXED_WING |
| `battery_fraction` | `float32` | [0, 1] | State of charge |
| `battery_voltage_v` | `float32` | V | Pack voltage |
| `armed` | `bool` | — | Autopilot armed |
| `offboard_active` | `bool` | — | PX4 in Offboard mode |
| `position_valid` | `bool` | — | Local position estimate is good |

**Flow:** `shark_isr_autopilot` → `shark_isr_perception`, `shark_isr_guidance`,
                              `shark_isr_mission`, `shark_isr_telemetry`

---

### `SearchState.msg`

| Field | Type | Unit / Frame | Description |
|---|---|---|---|
| `header` | `std_msgs/Header` | — | stamp = last update |
| `phase` | `uint8` | PHASE_* | IDLE/TRANSIT/SEARCH/TRACK/RETURN |
| `coverage_fraction` | `float32` | [0, 1] | Fraction of search area observed |
| `map_max_probability` | `float32` | [0, 1] | Peak Bayesian map cell probability |
| `map_mean_probability` | `float32` | [0, 1] | Mean map cell probability |
| `time_on_station_s` | `float32` | s | Elapsed in SEARCH or TRACK phase |
| `current_target_enu_m` | `geometry_msgs/Point` | m ENU | Active waypoint/target |
| `target_locked` | `bool` | — | true if in TRACK with active detection |
| `tracked_lat_deg` | `float64` | deg WGS-84 | Tracked target latitude (TRACK only) |
| `tracked_lon_deg` | `float64` | deg WGS-84 | Tracked target longitude (TRACK only) |
| `orbit_centre_enu_m` | `geometry_msgs/Point` | m ENU | Orbit centre (TRACK only) |
| `orbit_radius_m` | `float32` | m | Current orbit radius (TRACK only) |

**Flow:** `shark_isr_guidance` → `shark_isr_mission`, `shark_isr_telemetry`

---

### `GuidanceSetpoint.msg`

| Field | Type | Unit / Frame | Description |
|---|---|---|---|
| `header` | `std_msgs/Header` | — | stamp = command time; frame_id = "odom" |
| `setpoint_type` | `uint8` | TYPE_* | POSITION / VELOCITY / ORBIT |
| `position_enu_m` | `geometry_msgs/Point` | m ENU | Target position or orbit centre |
| `velocity_enu_m_s` | `geometry_msgs/Vector3` | m/s ENU | Velocity command (TYPE_VELOCITY) |
| `yaw_rad` | `float32` | rad ENU | Heading (0=East, CCW+); NaN = auto |
| `yaw_rate_rad_s` | `float32` | rad/s | Yaw rate feed-forward; NaN = auto |
| `orbit_radius_m` | `float32` | m | Orbit radius > 0 (TYPE_ORBIT) |
| `orbit_clockwise` | `bool` | — | CW from above if true |
| `cruise_speed_m_s` | `float32` | m/s | Desired speed; 0.0 = autopilot default |

**Flow:** `shark_isr_guidance` → `shark_isr_autopilot`

---

## Services

### `MissionCommand.srv`

**Server:** `shark_isr_mission` | **Client:** `shark_isr_telemetry` / operator tool

**Request:**

| Field | Type | Unit | Description |
|---|---|---|---|
| `command` | `uint8` | CMD_* | START / ABORT / RETURN / PAUSE / RESUME |
| `search_lat_deg` | `float64` | deg WGS-84 | Search area centre latitude (START only) |
| `search_lon_deg` | `float64` | deg WGS-84 | Search area centre longitude (START only) |
| `search_radius_m` | `float32` | m | Search area radius (START only) |
| `transit_alt_amsl_m` | `float32` | m AMSL | Transit altitude (START only) |
| `search_alt_amsl_m` | `float32` | m AMSL | Search/loiter altitude (START only) |
| `orbit_radius_m` | `float32` | m | Orbit radius on detection; 0 = default (START only) |

**Response:**

| Field | Type | Description |
|---|---|---|
| `accepted` | `bool` | true if command was applied |
| `reason` | `string` | Rejection reason (empty if accepted) |
| `current_phase` | `uint8` | SearchState PHASE_* after command |

---

### `SetGuidanceMode.srv`

**Server:** `shark_isr_guidance` | **Client:** `shark_isr_mission`

**Request:**

| Field | Type | Unit | Description |
|---|---|---|---|
| `mode` | `uint8` | MODE_* | IDLE / TRANSIT / SEARCH / ORBIT / RETURN |
| `transit_target_enu_m` | `geometry_msgs/Point` | m ENU | Destination (TRANSIT) |
| `search_centre_enu_m` | `geometry_msgs/Point` | m ENU | Search area centre (SEARCH) |
| `search_radius_m` | `float32` | m | Search area radius (SEARCH) |
| `search_alt_enu_z_m` | `float32` | m (z Up) | Search altitude above home (SEARCH) |
| `orbit_centre_enu_m` | `geometry_msgs/Point` | m ENU | Orbit centre (ORBIT) |
| `orbit_radius_m` | `float32` | m | Orbit radius (ORBIT) |
| `orbit_clockwise` | `bool` | — | CW from above; false = CCW default |

**Response:**

| Field | Type | Description |
|---|---|---|
| `accepted` | `bool` | true if mode change applied |
| `reason` | `string` | Rejection reason (empty if accepted) |

---

## Topic map

```
shark_isr_perception ─→ /shark_isr/detection      (Detection)
                    └──→ shark_isr_telemetry

shark_isr_autopilot  ─→ /shark_isr/vehicle_state  (VehicleState)
                    └──→ perception, guidance, mission, telemetry

shark_isr_guidance   ─→ /shark_isr/search_state   (SearchState)
                    └──→ mission, telemetry
shark_isr_guidance   ─→ /shark_isr/guidance_setpoint (GuidanceSetpoint)
                    └──→ shark_isr_autopilot

shark_isr_mission    srv→ /shark_isr/set_guidance_mode (SetGuidanceMode)
                    └──→ shark_isr_guidance
shark_isr_telemetry  srv→ /shark_isr/mission_command  (MissionCommand)
                    └──→ shark_isr_mission
```

## Run in isolation

```bash
# Verify the package builds (no nodes in this package)
cd ros2_ws
colcon build --packages-select shark_isr_interfaces
source install/setup.bash
ros2 interface list | grep shark_isr
```

## Notes

- Phase 1 spec is **not yet frozen** — freeze happens in next session after review.
- `AutopilotCommand.srv` (arm/RTL/mode direct commands mission → autopilot) deferred to Phase 3;
  it requires PX4-specific VehicleCommand semantics and belongs in that implementation phase.
- No behaviour is "done" until it has a passing SITL check (see docs/BUILD_PLAN.md).
