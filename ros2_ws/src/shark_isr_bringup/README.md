# shark_isr_bringup

**Purpose:** Launch files and aggregated params; brings the whole stack (or subsets) up.

## Launch files

| File | What it starts |
| --- | --- |
| `sitl.launch.py` | Full stack: autopilot_bridge, guidance_node, mission_node, perception (mock_camera + detector, sim mode), telemetry_node. Each package's own launch file is included, so per-package `config/*.yaml` loading stays in the owning package. |

## Launch arguments

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `with_perception` | bool | `true` | Start mock_camera + detector (set `false` to inject detections manually) |
| `with_telemetry` | bool | `true` | Start the telemetry logger |

## Interfaces

None of its own — this package only composes the other packages' launch files.

## Run in isolation

```bash
# Terminal 1: simulator (Gazebo + XRCE agent + PX4 SITL)
./scripts/run_sim.sh

# Terminal 2: full autonomy stack
source ros2_ws/install/setup.bash
ros2 launch shark_isr_bringup sitl.launch.py

# Subset without perception:
ros2 launch shark_isr_bringup sitl.launch.py with_perception:=false
```

Full test campaign: **docs/SITL_PROCEDURE.md**.

## Notes
- Depends only on `shark_isr_interfaces` for cross-package types.
- No behaviour is "done" until it has a passing SITL check (see docs/BUILD_PLAN.md).
