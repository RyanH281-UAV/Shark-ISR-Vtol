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
| Arming timeout | Aborts start sequence → IDLE |
| Transit timeout | Starts search without completing transit |
| Node death / compute loss | PX4 detects lost OffboardControlMode heartbeat → PX4 RTL (hardware failsafe, ADR-003) |

Note: the hardware failsafe (PX4 RTL on link loss) is independent of this node and cannot be disabled from software. The companion computer is never in the safety-critical loop (ADR-003).
