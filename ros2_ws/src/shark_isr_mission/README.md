# shark_isr_mission

Mission state machine — coordinates `shark_isr_autopilot` and `shark_isr_guidance`.

This node is a **pure coordinator**: it calls services, never computes trajectories.

## State Machine

```
IDLE ─CMD_START─▶ STARTING ─armed+offboard─▶ TRANSITING
TRANSITING ─arrival(guidance)─▶ SEARCHING
SEARCHING ─Detection(guidance)─▶ TRACKING
TRACKING ─guidance back to SEARCH─▶ SEARCHING
any ─CMD_ABORT/RETURN─▶ RETURNING
any ─CMD_PAUSE─▶ PAUSED ─CMD_RESUME─▶ [prior phase]
any ─low_battery─▶ RETURNING  (failsafe)
```

## Subscribed Topics

| Topic | Type | Source |
|---|---|---|
| `vehicle_state` | `shark_isr_interfaces/VehicleState` | `shark_isr_autopilot` |
| `search_state` | `shark_isr_interfaces/SearchState` | `shark_isr_guidance` |

## Services Called

| Service | Type | Purpose |
|---|---|---|
| `autopilot_command` | `shark_isr_interfaces/AutopilotCommand` | arm/offboard/hold/RTL |
| `set_guidance_mode` | `shark_isr_interfaces/SetGuidanceMode` | transit/search/orbit/return |

## Service Server

| Service | Type | Clients |
|---|---|---|
| `mission_command` | `shark_isr_interfaces/MissionCommand` | GCS relay (telemetry), operator tooling |

## Parameters (`config/mission.yaml`)

| Parameter | Default | Description |
|---|---|---|
| `update_hz` | 2.0 | State monitor rate [Hz] |
| `low_battery_threshold` | 0.20 | Battery fraction to trigger return (application failsafe) |
| `arm_timeout_s` | 10.0 | Seconds before aborting arm sequence |
| `transit_timeout_s` | 300.0 | Seconds before starting search if transit hasn't completed |
| `track_timeout_s` | 120.0 | Seconds in TRACKING before auto-resuming SEARCH |
| `search_length_m` | 0.0 | Along-shore strip extent [m]; 0 = circular area (ADR-018). Overridden per-mission by `CMD_START`'s own `search_length_m` when it is > 0 |
| `search_width_m` | 120.0 | Cross-shore strip extent [m] |
| `shore_bearing_rad` | 0.0 | ENU bearing of the shoreline [rad] (REP-103) |
| `min_alt_above_home_m` | 10.0 | Lowest allowed transit/search height above home [m]; CMD_START is rejected below it |
| `max_alt_above_home_m` | 120.0 | Highest allowed height above home [m] (CASA 400 ft ceiling); CMD_START is rejected above it |

**Altitudes:** `CMD_START` takes AMSL. Mission converts once, using home AMSL = current AMSL − current height above home, and everything downstream works in height above home. `orbit_radius_m` is forwarded to guidance; 0 means guidance's default.

## Run in isolation

```bash
source ros2_ws/install/setup.bash
ros2 launch shark_isr_mission mission.launch.py

# Start mission (search area at -31.998°, 115.748° = Cottesloe Beach)
ros2 service call /mission_command shark_isr_interfaces/srv/MissionCommand \
  "{command: 0, search_lat_deg: -31.998, search_lon_deg: 115.748, \
    search_radius_m: 300.0, transit_alt_amsl_m: 50.0, \
    search_alt_amsl_m: 50.0, orbit_radius_m: 50.0}"

# Abort
ros2 service call /mission_command shark_isr_interfaces/srv/MissionCommand "{command: 1}"

# Pause / resume
ros2 service call /mission_command shark_isr_interfaces/srv/MissionCommand "{command: 3}"
ros2 service call /mission_command shark_isr_interfaces/srv/MissionCommand "{command: 4}"
```

## Failsafes

| Trigger | Action |
|---|---|
| `battery_fraction` < 0.20 | Application-level: calls SetGuidanceMode RETURN + AutopilotCommand RTL |
| Arming timeout | Triggers RETURN (guidance RETURN + PX4 RTL), not IDLE — the code does this even though the aircraft may still be on the ground |
| Transit timeout | Starts search without completing transit |
| Node death / compute loss | PX4 detects lost OffboardControlMode heartbeat → PX4 RTL (hardware failsafe, ADR-003) |

Note: the hardware failsafe (PX4 RTL on link loss) is independent of this node and cannot be disabled from software. The companion computer is never in the safety-critical loop (ADR-003).
