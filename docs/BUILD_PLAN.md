# Build Plan (phased)

Feed this to Ruflo's goals/planning workflow. `[ ]` todo, `[~]` in progress, `[x]` done.
Do not jump phases — interfaces are frozen before nodes are built; SITL precedes hardware.

## Phase 0 — Foundation
- [ ] `npx ruflo@latest init` in the repo; verify `.claude/`, `.claude-flow/`, `CLAUDE.md` present
- [ ] Install the plugins listed in USAGE_PLAN.md; register the Ruflo MCP server
- [ ] Run `scripts/scaffold.sh` to create the ROS 2 workspace skeleton + module READMEs
- [ ] `colcon build` succeeds on the empty packages

## Phase 1 — Interface contract (ADR-004)
- [x] Specify `Detection.msg`, `SearchState.msg`, `GuidanceSetpoint.msg`, `MissionCommand.srv`
- [x] Add `VehicleState.msg` (ADR-007) and `SetGuidanceMode.srv` (ADR-009) — required by dataflow
- [x] Document frame + units for every field (see shark_isr_interfaces/README.md)
- [x] Write `.msg`/`.srv` files and `CMakeLists.txt`/`package.xml` for `shark_isr_interfaces`
- [x] Freeze: interfaces reviewed, locked, and `colcon build --packages-select shark_isr_interfaces` passes clean (ROS 2 Humble, 2026-05-31)

## Phase 2 — Simulation parity (ADR-005)
- [~] PX4 SITL Tiltrotor VTOL (airframe 4020 gz_tiltrotor, PX4 v1.16, Gazebo Harmonic gz-sim 8)
- [~] micro XRCE-DDS agent (snap `micro-xrce-dds-agent --edge`) + `px4_msgs release/1.16` in workspace
- [x] Gazebo coastal world: `sim/worlds/shark_isr_coastal.sdf` (Cottesloe Beach, Perth WA; ocean surface)
- [x] `scripts/run_sim.sh` — shark-ISR labelled, isolated from SkimWing, starts agent + SITL
- [ ] End-to-end verify: `ros2 topic list | grep fmu` shows PX4 uORB topics via DDS bridge

## Phase 3 — Autopilot bridge (ADR-002)
- [x] `AutopilotCommand.srv` added to `shark_isr_interfaces` (deferred from Phase 1, ADR-009)
- [x] `frame_transforms.py` — pure NED↔ENU, FRD↔FLU math (unit-tested, no ROS deps)
- [x] `autopilot_bridge.py` node — VehicleState publisher, offboard heartbeat, GuidanceSetpoint→TrajectorySetpoint, AutopilotCommand service
- [x] `setup.py`, `package.xml`, `config/autopilot.yaml`, `launch/autopilot.launch.py`
- [x] Unit tests: `test/test_frame_transforms.py` (position/velocity, yaw, quaternion roundtrip)
- [x] `colcon build --packages-select shark_isr_interfaces shark_isr_autopilot` passes in WSL
- [x] `ros2 launch shark_isr_autopilot autopilot.launch.py` starts cleanly against SITL
- [x] Verify offboard setpoints + loiter/orbit in SITL (T06)
- [x] Verify failsafe: link loss → PX4 RTL/hold (T07)

## Phase 4 — Guidance
- [x] `search_pattern.py` — boustrophedon waypoint generator (unit-tested)
- [x] `bayesian_map.py` — discrete Bayesian probability grid (unit-tested)
- [x] `guidance_node.py` — state machine (IDLE/TRANSIT/SEARCH/TRACK/RETURN), SetGuidanceMode srv
- [x] `setup.py`, `package.xml`, `config/guidance.yaml`, `launch/guidance.launch.py`
- [x] `test/test_search_pattern.py` + `test/test_bayesian_map.py`
- [x] `colcon build --packages-select shark_isr_guidance` passes in WSL
- [x] SITL end-to-end: inject SetGuidanceMode SEARCH → vehicle executes pattern (T10)
- [x] SITL: inject mock Detection → vehicle transitions to TRACK orbit (T10/T11)

## Phase 5 — Perception
- [x] `mock_camera_node.py` — synthetic Image publisher for SITL (noise or disk frames)
- [x] `detector_node.py` — HailoRT inference (real) + probabilistic mock (sim); publishes Detection
- [x] `geolocate.py` — pinhole + flat-earth geolocation (no ROS deps, unit-tested)
- [x] `setup.py`, `package.xml`, `config/perception.yaml`, `launch/perception.launch.py`
- [x] `test/test_geolocate.py` — 9 tests (centre, offset, AGL scaling, error cases); 9/9 pass
- [ ] `.hef` model: compile/obtain Hailo Model Zoo YOLO variant; update `hef_path` in config
- [x] `colcon build --packages-select shark_isr_perception` passes in WSL
- [x] SITL end-to-end: launch perception (sim) → mock Detection published → guidance receives (T11)
- [ ] Bench thermal/throughput: sustained inference on Pi 5 + AI HAT+ without throttling (Phase 8)

## Phase 6 — Mission management
- [x] `mission_node.py` — state machine (IDLE/STARTING/TRANSITING/SEARCHING/TRACKING/RETURNING)
- [x] MissionCommand srv server (operator/GCS interface)
- [x] AutopilotCommand + SetGuidanceMode service clients (async, non-blocking)
- [x] Battery failsafe, arm timeout, transit timeout
- [x] MultiThreadedExecutor for non-blocking service calls
- [x] `setup.py`, `package.xml`, `config/mission.yaml`, `launch/mission.launch.py`
- [x] `colcon build --packages-select shark_isr_mission` passes in WSL
- [x] SITL end-to-end: CMD_START → ARM → OFFBOARD → TRANSIT → SEARCH sequence (T10)
- [x] SITL: CMD_ABORT → RTL verified (T08)
- [x] SITL: low battery trigger test (T09)

## Phase 7 — Telemetry & integration
- [x] `shark_isr_telemetry`: structured logging of flight + detections + decisions
- [x] GCS/operator summary relay (`/telemetry_summary` String at 1 Hz)
- [ ] Full mission rehearsal in SITL; review logs (SITL check pending — needs WSL + PX4)

## Phase 8 — Hardware bring-up (post-budget)
- [ ] Mass + power budget vs MTOW (docs/HORNET_PLATFORM.md)
- [ ] Spec/source a ≥5 A 5 V rail (owned LM2596S 3 A likely insufficient)
- [ ] Thermal solution for Pi 5 + AI HAT+ in the fuselage (active cooler + airflow); verify no throttling
- [ ] Pi 5 + AI HAT+ + Camera Module 3 bench integration; HailoRT detector running
- [ ] Measure Wh/km in flight; correct the range estimate in docs/DECISIONS.md
- [ ] CASA/ops checklist (docs/REGULATORY.md) before any flight
