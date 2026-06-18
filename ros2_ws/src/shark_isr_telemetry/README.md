# shark_isr_telemetry

**Purpose:** Structured logging of flight state, detections, and phase events; publishes a human-readable operator summary.

## Subscribed Topics

| Topic | Type | Source | Notes |
|---|---|---|---|
| `/vehicle_state` | `shark_isr_interfaces/VehicleState` | `shark_isr_autopilot` | Position, velocity, battery, VTOL phase |
| `/search_state` | `shark_isr_interfaces/SearchState` | `shark_isr_guidance` | Mission phase, coverage, orbit state |
| `/detections` | `shark_isr_interfaces/Detection` | `shark_isr_perception` | Shark detections with geo position |

## Published Topics

| Topic | Type | Rate | Notes |
|---|---|---|---|
| `/telemetry_summary` | `std_msgs/String` | 1 Hz | Human-readable one-line status for operator/GCS |

## Log Files

Written to `log_dir` (default `/tmp/shark_isr_logs`), named by session start UTC time.

| File | Content | Format |
|---|---|---|
| `flight_YYYYMMDD_HHMMSS.jsonl` | Vehicle state at `flight_log_hz` | JSONL — one record per line |
| `detections_YYYYMMDD_HHMMSS.jsonl` | Every detection event | JSONL |
| `events_YYYYMMDD_HHMMSS.jsonl` | Phase transitions, session start/end | JSONL |

### Flight record fields
`ts` (Unix epoch), `lat_deg`, `lon_deg`, `alt_amsl_m`, `agl_m`, `gs_m_s`, `batt` (0–1), `batt_v`, `vtol`, `armed`, `offboard`, `phase`, `coverage`

### Detection record fields
`ts`, `confidence`, `class`, `geo_valid`, `bbox` [x_min, y_min, x_max, y_max], `lat_deg`, `lon_deg`, `pos_std_m` (if geo valid)

### Event record fields
`ts`, `event` (string), plus event-specific fields

## Parameters (`config/telemetry.yaml`)

| Parameter | Type | Default | Description |
|---|---|---|---|
| `log_dir` | string | `/tmp/shark_isr_logs` | Directory for JSONL log files |
| `flight_log_hz` | float | `1.0` | Vehicle state records per second |
| `summary_hz` | float | `1.0` | `/telemetry_summary` publish rate |

## Run in Isolation

```bash
# In WSL with ROS 2 sourced + shark_isr_interfaces built:
ros2 run shark_isr_telemetry telemetry_node \
  --ros-args -p log_dir:=/tmp/test_logs

# Or via launch file:
ros2 launch shark_isr_telemetry telemetry.launch.py

# Monitor summary:
ros2 topic echo /telemetry_summary

# Tail the flight log:
tail -f /tmp/shark_isr_logs/flight_*.jsonl | python -m json.tool
```

## Notes

- Depends only on `shark_isr_interfaces` for cross-package types (ADR-002).
- No RF/GCS transport in this node. The GCS telemetry link is QGC ↔ Pixhawk over a
  MAVLink radio (ADR-015); `/telemetry_summary` is a supplementary ROS operator feed only.
- JSONL format: each line is valid JSON, easy to ingest with `pandas.read_json(..., lines=True)`.
- Log files are line-buffered — data is flushed on every detection/record even without a flush call.
- No deterministic math → no unit tests required per project convention.
- SITL check: run against a simulated mission and verify all three log files populate correctly.
