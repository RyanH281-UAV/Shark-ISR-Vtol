# shark_isr_guidance

Search-pattern generation, Bayesian probability map, detection-triggered orbit/loiter.
Produces `GuidanceSetpoint` — consumed by `shark_isr_autopilot`.

## Responsibilities

- **Search pattern:** boustrophedon (lawnmower) east-west rows across a circular area.
  Strip width = sensor swath at search altitude (configurable, default 60 m).
- **Bayesian map:** discrete probability grid; updates on null observations (sensor sweep
  with no detection) and positive detections (Gaussian likelihood spike).
- **Detection-triggered orbit:** on receiving a `Detection` with confidence ≥ threshold,
  immediately commands an orbit around the detection position.
- **State machine:** IDLE → TRANSIT → SEARCH → TRACK → RETURN.
  Transitions driven by `SetGuidanceMode` from `shark_isr_mission`.

## Subscribed Topics

| Topic | Type | Source |
|---|---|---|
| `vehicle_state` | `shark_isr_interfaces/VehicleState` | `shark_isr_autopilot` |
| `detection` | `shark_isr_interfaces/Detection` | `shark_isr_perception` |

## Published Topics

| Topic | Type | Subscribers |
|---|---|---|
| `guidance_setpoint` | `shark_isr_interfaces/GuidanceSetpoint` | `shark_isr_autopilot` |
| `search_state` | `shark_isr_interfaces/SearchState` | `shark_isr_mission`, `shark_isr_telemetry` |

## Services

| Service | Type | Client |
|---|---|---|
| `set_guidance_mode` | `shark_isr_interfaces/SetGuidanceMode` | `shark_isr_mission` |

## Parameters (`config/guidance.yaml`)

| Parameter | Default | Description |
|---|---|---|
| `update_hz` | 5.0 | Setpoint publish rate [Hz] |
| `state_hz` | 2.0 | SearchState publish rate [Hz] |
| `strip_width_m` | 60.0 | Boustrophedon row spacing [m] |
| `arrival_threshold_m` | 15.0 | Waypoint arrival radius [m] |
| `detection_confidence_threshold` | 0.70 | Min Detection.confidence to trigger orbit |
| `orbit_radius_m` | 50.0 | Orbit radius when tracking [m] |
| `footprint_radius_m` | 35.0 | Sensor footprint radius for Bayesian update [m] |
| `p_detection` | 0.85 | P(detect | shark in footprint) for Bayesian update |
| `detection_sigma_m` | 25.0 | Gaussian sigma for positive detection update [m] |
| `return_home_alt_m` | 30.0 | ENU z altitude for return-to-home leg [m] |

## Run in isolation (mock inputs)

```bash
source ros2_ws/install/setup.bash
ros2 launch shark_isr_guidance guidance.launch.py

# Inject a search command (from a second terminal)
ros2 service call /set_guidance_mode shark_isr_interfaces/srv/SetGuidanceMode \
  "{mode: 2, search_centre_enu_m: {x: 0.0, y: 0.0, z: 0.0}, \
    search_radius_m: 200.0, search_alt_enu_z_m: 50.0}"

# Watch setpoints
ros2 topic echo /guidance_setpoint

# Watch coverage / state
ros2 topic echo /search_state
```

## Unit Tests (no ROS required)

```bash
python -m pytest ros2_ws/src/shark_isr_guidance/test/ -v
```

Covers:
- `test_search_pattern.py`: all waypoints inside circle, altitude constant,
  alternating direction, coverage monotonic, edge cases.
- `test_bayesian_map.py`: probabilities sum to 1 after every update,
  detection increases centre probability, coverage tracker.
