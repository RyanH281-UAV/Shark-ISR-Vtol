# shark_isr_autopilot

**The ONLY package talking to the autopilot.**  All other stack packages are firmware-agnostic.

PX4 via uXRCE-DDS + `px4_msgs`. ADR-002 reserves the interface boundary for a MAVLink
fallback, but **no MAVLink implementation is currently present** — uXRCE-DDS is the only
transport coded. The GCS radio link is handled by QGC ↔ Pixhawk directly (ADR-015).
See ADR-002, ADR-003, ADR-007, ADR-008.

## Responsibilities

- Subscribe to raw PX4 uORB topics (`/fmu/out/…`) and re-publish a unified
  `VehicleState` in ENU/FLU convention.
- Receive `GuidanceSetpoint` and publish `OffboardControlMode` +
  `TrajectorySetpoint` to PX4 at ≥20 Hz.
- Provide `AutopilotCommand` service for arm/disarm/mode transitions
  (client: `shark_isr_mission`).
- Stream OffboardControlMode heartbeat so PX4 holds Offboard mode.

**Not** responsible for: inner loop, attitude control, tilt transition (PX4 owns those).

## Subscribed Topics

| Topic | Type | Source |
|---|---|---|
| `/fmu/out/vehicle_local_position` | `px4_msgs/VehicleLocalPosition` | PX4 (NED) |
| `/fmu/out/vehicle_attitude` | `px4_msgs/VehicleAttitude` | PX4 (NED/FRD quat) |
| `/fmu/out/vehicle_global_position` | `px4_msgs/VehicleGlobalPosition` | PX4 |
| `/fmu/out/battery_status` | `px4_msgs/BatteryStatus` | PX4 |
| `/fmu/out/vtol_vehicle_status` | `px4_msgs/VtolVehicleStatus` | PX4 |
| `guidance_setpoint` | `shark_isr_interfaces/GuidanceSetpoint` | `shark_isr_guidance` (ENU/FLU) |

## Published Topics

| Topic | Type | Subscribers |
|---|---|---|
| `vehicle_state` | `shark_isr_interfaces/VehicleState` | all other packages (ENU/FLU) |
| `/fmu/in/offboard_control_mode` | `px4_msgs/OffboardControlMode` | PX4 |
| `/fmu/in/trajectory_setpoint` | `px4_msgs/TrajectorySetpoint` | PX4 |
| `/fmu/in/vehicle_command` | `px4_msgs/VehicleCommand` | PX4 |

## Services

| Service | Type | Description |
|---|---|---|
| `autopilot_command` | `shark_isr_interfaces/AutopilotCommand` | arm/disarm/offboard/hold/RTL/land |

## Parameters (`config/autopilot.yaml`)

| Parameter | Default | Description |
|---|---|---|
| `mav_sys_id` | 1 | PX4 `MAV_SYS_ID` — must match QGC/PX4 param |
| `mav_comp_id` | 1 | PX4 component ID |
| `offboard_hz` | 20.0 | OffboardControlMode + TrajectorySetpoint publish rate [Hz] |
| `vehicle_state_hz` | 20.0 | VehicleState publish rate [Hz] |
| `setpoint_timeout_s` | 2.0 | Seconds without a GuidanceSetpoint before holding position |

## Run in isolation (SITL)

```bash
# Terminal 1: SITL + Gazebo + DDS agent
./scripts/run_sim.sh

# Terminal 2: verify topics
source ros2_ws/install/setup.bash
ros2 topic list | grep fmu           # should show /fmu/in/* and /fmu/out/*

# Terminal 3: launch bridge
ros2 launch shark_isr_autopilot autopilot.launch.py

# Terminal 4: verify VehicleState
ros2 topic echo /vehicle_state

# Quick arm + offboard test
ros2 service call /autopilot_command shark_isr_interfaces/srv/AutopilotCommand "{command: 0}"  # ARM
ros2 service call /autopilot_command shark_isr_interfaces/srv/AutopilotCommand "{command: 2}"  # OFFBOARD
```

## Frame Convention (ADR-008)

All NED↔ENU and FRD↔FLU conversions happen **exclusively** in this package.
`frame_transforms.py` contains the pure-math conversion functions (no ROS deps).

```
PX4 NED/FRD  ──── this package ────  ROS 2 ENU/FLU
                  frame_transforms.py
```

## Unit Tests (no ROS required)

```bash
# From repo root — no ROS workspace needed
python -m pytest ros2_ws/src/shark_isr_autopilot/test/test_frame_transforms.py -v
```

Tests cover: NED↔ENU position/velocity roundtrip, yaw conversion roundtrip,
attitude quaternion identity case, unit-norm preservation.

## Phase 3 SITL checklist

- [ ] `colcon build --packages-select shark_isr_interfaces shark_isr_autopilot` passes
- [ ] `ros2 launch shark_isr_autopilot autopilot.launch.py` starts cleanly
- [ ] `ros2 topic echo vehicle_state` shows valid ENU position while SITL runs
- [ ] ARM service call succeeds in SITL
- [ ] OFFBOARD service call + `GuidanceSetpoint` TYPE_POSITION moves vehicle in SITL
- [ ] Link loss (kill bridge) → PX4 enters RTL/Hold failsafe within its timeout
