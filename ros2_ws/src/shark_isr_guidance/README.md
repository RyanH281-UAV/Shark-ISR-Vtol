# shark_isr_guidance

Search-pattern generation, Bayesian probability map, detection-triggered orbit/loiter.
Produces `GuidanceSetpoint` — consumed by `shark_isr_autopilot`.

## Responsibilities

- **Search strategy (ADR-012):** config choice via `search_strategy` —
  `persistent_patrol` (default: threat-weighted belief-driven patrol with a hard revisit
  bound), `bayesian_greedy` (first-find), or `lawnmower` (fixed boustrophedon baseline,
  T10-verified).
- **Bayesian map:** discrete probability grid; null observations (sweep, no detection),
  positive detections (Gaussian likelihood spike), and time-based probability re-growth
  toward the prior (`regrowth_alpha`) — cleared water doesn't stay cleared.
- **Confidence gate (ADR-016):** detections add `gate_gain × confidence` to an evidence
  score; every tick subtracts `gate_decay`. SEARCH → TRACK only after the score holds
  ≥ `gate_tau` for `gate_k_sustain` consecutive ticks — one lucky frame never flies the
  aircraft. In TRACK, score ≤ `gate_lost` returns guidance to SEARCH.
- **State machine:** IDLE → TRANSIT → SEARCH → TRACK → RETURN.
  Transitions driven by `SetGuidanceMode` from `shark_isr_mission` and the gate.

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
| `strip_width_m` | 25.0 | Lane spacing [m] — sized to the 31 m cross-track footprint at 30 m AGL (ADR-010) |
| `arrival_threshold_m` | 15.0 | Waypoint arrival radius [m] |
| `detection_confidence_threshold` | 0.70 | Min Detection.confidence fed to the gate |
| `gate_tau` | 0.85 | Evidence score threshold (ADR-016) |
| `gate_k_sustain` | 6 | Consecutive ticks ≥ τ required to transition |
| `gate_gain` | 0.12 | Score rise per detection (× confidence) |
| `gate_decay` | 0.05 | Score fall per guidance tick |
| `gate_lost` | 0.25 | Score at which a tracked target counts as lost |
| `search_strategy` | persistent_patrol | `lawnmower` / `persistent_patrol` / `bayesian_greedy` (ADR-012) |
| `revisit_bound_s` | 300.0 | Hard revisit bound T [s] (persistent_patrol) |
| `regrowth_alpha` | 0.001 | Probability re-growth toward prior [1/s] |
| `orbit_radius_m` | 50.0 | Orbit radius when tracking [m] |
| `footprint_radius_m` | 12.0 | Sensor footprint half-width for Bayesian update [m] |
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
- `test_strategies.py`: lawnmower cycling, greedy targeting, persistent-patrol
  force-visit past the revisit bound, barrier stub raises.
- `test_confidence_gate.py`: single lucky frame never triggers, short burst never
  triggers, sustained stream triggers, k-consecutive-tick rule, lost-target decay.
