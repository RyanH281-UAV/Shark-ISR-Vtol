# Capability Roadmap — Shark-ISR VTOL

> **Lens:** what the system can *do* today, what's missing, and in what order the gaps close.
> This is the capability view. The phase-by-phase build order lives in `BUILD_PLAN.md`; locked
> technical decisions live in `DECISIONS.md`. Consult both for deeper context.

**Status legend:**
✅ done and verified  ·  🔶 code-complete, SITL/hardware-pending  ·  🟡 partial / stub  ·  ⬜ not started

---

## Capability Map

| # | Capability | What it does | State | Critical gaps |
|---|---|---|---|---|
| 1 | **Autonomy / Mission control** | Full mission state machine: IDLE→STARTING→TRANSIT→SEARCH→TRACK→PAUSE→RETURN→LAND. ARM→OFFBOARD→TRANSIT async chain with PX4-confirmed gating. Pause/resume. | 🔶 | `mission_node` has **zero tests**. SITL T3/T7 not run. Failsafe timeouts unverified in sim. |
| 2 | **Search** | Boustrophedon coverage over circle or rotated strip. Bayesian belief map (discrete, log-prob, decay, age). Three live strategies: lawnmower / Bayesian-greedy / persistent-patrol (hard revisit bound). Pre-flight feasibility gate. | 🔶/🟡 | `strategies.py` + `SearchRegion` + `boustrophedon_strip` tested but **not wired** into `guidance_node` (node hardcodes legacy `boustrophedon`). `BarrierStrategy` is an explicit stub. SITL T4. |
| 3 | **Perception** | HailoRT inference lifecycle (real PCIe pipeline). Pinhole+flat-earth geolocation → WGS-84 detection geo-pin. Mock camera node for SITL. | 🟡 | `_hailo_forward` output parser is a **placeholder** (stride-6 guess; must adapt to real model tensors). No `.hef` model compiled. No picamera2/real-camera ingest (node waits for `/camera/image_raw`). SITL T5/T10. |
| 4 | **Autopilot bridge** | uXRCE-DDS to PX4: offboard position/velocity/orbit setpoints (orbit synthesised as streamed Offboard — ADR-011). Mode/arm via `VehicleCommand`. Unified `VehicleState` (ENU/FLU) re-published for the rest of the stack. | 🔶 | **No MAVLink fallback coded** (claimed in README, not implemented). Node logic (non-math) has zero tests. SITL T1/T2 not run. |
| 5 | **Safety / failsafes** | Low-battery→RTL, arm timeout, transit timeout, track timeout. Companion kept out of the inner loop (ADR-003). ACRO-on-RTL bug fixed (ADR-011). | 🔶 | PX4 geofence + RTL params not configured/verified. **Companion-loss failsafe (T9) is the most critical unproven item.** CASA/ops checklist (`docs/REGULATORY.md`) not cleared. |
| 6 | **Telemetry & logging** | Structured JSONL logs: flight state, detections, events. 1 Hz operator summary string on `/telemetry_summary`. | 🔶 | **No RF/GCS downlink path anywhere in the stack.** Logs land on disk only; no radio, no MAVLink stream, no rosbridge → operator. Covered in GCS segment (↓). |
| 7 | **Ground control station** | Operator commands (start/abort/pause/return), flight telemetry HUD, map track, detection overlay. | ⬜ | **Decision (ADR-015):** Use **QGroundControl** off-the-shelf for flight/missions/failsafe/HUD (PX4 speaks MAVLink natively); add a thin custom view for shark detections only. Pieces to build: (a) MAVLink telemetry radio on companion (SiK/RFD900/similar), (b) QGC connected to Pixhawk 6C Mini, (c) detection bridge: `Detection` topic → Foxglove panel or rosbridge→web map with geo-pins. |
| 8 | **Mission planner** | Define and upload search areas + transit waypoints. | 🟡 | Runtime commands exist via `MissionCommand.srv` (CMD_START / CMD_ABORT / CMD_PAUSE / CMD_RETURN). No waypoint/area upload UX. **Path forward:** use QGC `.plan` files for the transit leg; encode the search strip as a `SearchRegion` YAML preset in `config/mission.yaml` (centre, length, width, bearing, alt). |
| 9 | **Simulation / SITL** | PX4 v1.16 SITL + Gazebo Harmonic coastal world (Cottesloe Beach). uXRCE-DDS agent. Full-stack launch via `shark_isr_bringup`. | 🔶 | Stack is built and runnable. **Campaign not run.** G1–G4 (DDS bridge) and T1–T10 (behaviours) all unchecked. This is the critical path gate before hardware (ADR-005). |
| 10 | **Hardware bring-up** | Pi 5 + AI HAT+ (Hailo-8L 13 TOPS) + Camera Module 3 on the Hornet Pixhawk 6C Mini companion. | ⬜ | Mass/power budget vs 2.5 kg MTOW. **≥5 A 5V rail required** (owned LM2596S 3 A insufficient). Thermal in sealed LW-PLA fuselage. `.hef` deploy to Pi. Camera calibration (intrinsics in `config/perception.yaml` are approximate defaults). `hardware.launch.py` + systemd services. Phase 8 — blocked on SITL pass. |
| 11 | **Cross-cutting: tests, CI, decision log** | Unit tests, CI pipeline, ADR coverage. | 🟡 | `mission_node` has zero tests (safety-relevant coordinator). No project-level CI (no `.github/workflows/` at repo root; only vendored `px4_msgs` has its own). ADR log stopped at ADR-011; commits reference ADR-013/ADR-014 which are unrecorded (`docs/DECISIONS.md` updated below). |

---

## Near-term execution plan (SITL campaign first)

The project rule is strict: **no code flies until it passes SITL** (ADR-005). Nothing in the
stack is sim-verified yet. The entire GCS, hardware, and strategy-wiring work waits here.

### Step 1 — DDS bridge gates G1–G4 (Phase 2 exit criterion)

See `docs/SITL_PROCEDURE.md` §4 for commands. These four gates prove the uXRCE-DDS bridge is
alive before any ROS node does anything interesting.

| Gate | Check | Tool |
|------|-------|------|
| G1 | PX4 uORB topics visible on DDS | `ros2 topic list \| grep fmu/out` |
| G2 | `vehicle_attitude` flowing ~100 Hz | `ros2 topic hz /fmu/out/vehicle_attitude` |
| G3 | Bridge republishes `/vehicle_state` ~20 Hz | `ros2 topic hz /vehicle_state` |
| G4 | Ground frame sanity (pos≈0, quat≈identity, lat≈−32.0, armed=false) | `ros2 topic echo /vehicle_state --once` |

### Step 2 — Behaviour tests T1–T10 (priority order)

Run in this order — safety-critical first, features after.

| Test | Behaviour | Why first |
|------|-----------|-----------|
| **T2** | HOLD/RTL/LAND mode encoding | Safety. Fixed the ACRO-on-RTL bug (ADR-011); must confirm in sim. |
| **T1** | Offboard engagement (1 s pre-stream + retry) | Foundation for everything else. |
| **T3** | CMD_START → ARM → OFFBOARD → TRANSIT → SEARCH | Mission start chain. |
| **T4** | Boustrophedon search + ENU yaw waypoints | Guidance loop. |
| **T5** | Mock detection → TRACK orbit | Detection-triggered transition. |
| **T6** | Track timeout → resume SEARCH | Robustness. |
| **T7** | CMD_ABORT → RTL | Mission-level abort. |
| **T8** | Low-battery failsafe → RTL | Energy safety. |
| **T9** | **Companion-loss → PX4 handles it alone** | **Most important.** Companion is never in the safety loop (ADR-003); verify PX4 GCS timeout/failsafe fires independently. |
| **T10** | Geolocation accuracy sanity | Perception math validation. |

### Step 3 — Fixes from SITL

Bugs found during the campaign get small commits with ADR entries. Expect mode encoding, timing,
and coordinate surprises.

### Step 4 — After SITL passes (ordered by impact)

Once G1–G4 + T1–T10 are all checked:

1. **Wire `strategies.py` into `guidance_node`** — `PersistentPatrolStrategy` replaces the
   hardcoded `boustrophedon` call; expose `strategy` as a `config/guidance.yaml` param.
   `SearchRegion` replaces the circle (centre+radius) as the search area definition.
2. **Perception: compile/obtain `.hef` + adapt `_hailo_forward`** — pick a YOLO variant from
   the Hailo Model Zoo, fine-tune on the shark training dataset, compile to `.hef` with the
   Hailo Dataflow Compiler. Adapt the output parser to the real tensor layout.
3. **Add real picamera2 camera publisher** — a small `camera_node.py` that reads from
   `CameraModule3` via picamera2 and publishes `Image` + `CameraInfo` on `/camera/image_raw`.
   Camera calibration (checkerboard) writes real intrinsics to `config/perception.yaml`.
4. **GCS — MAVLink radio + QGC** — spec a SiK/RFD900 pair (mass/power budget), connect QGC
   to Pixhawk 6C Mini over MAVLink. This gives: maps, telemetry HUD, arm/mode/failsafe. Then
   build the thin detection view (Detection → Foxglove panel or rosbridge→web map).
5. **Mission node tests** — at minimum: state transition matrix test; CMD_START guard
   (no valid position → reject); low-battery failsafe mock. These are safety-relevant paths with
   zero test coverage.
6. **Phase 8 hardware bring-up** — per `docs/BUILD_PLAN.md` Phase 8 checklist.

---

## What `docs/BUILD_PLAN.md` shows vs here

`BUILD_PLAN.md` is ordered by *build dependency* (interfaces before nodes, etc.). This roadmap
is ordered by *operational capability*. They are complementary:

- Build plan tells you what to build and in what order (Phase 0–8).
- This roadmap tells you what the aircraft can *do* at each level of completion, and which gaps
  matter most for flight safety vs feature completeness.

The Phase 2–7 "🔶 code-complete, SITL-pending" classification here maps directly to the
unchecked SITL items scattered across Build Plan Phases 2–7.

---

## Open decisions to record (next ADRs)

These decisions were taken but never written up:

| # | Topic | Decision summary |
|---|-------|-----------------|
| ADR-012 | Pluggable search strategies | `strategies.py` protocol + LawnmowerStrategy / BayesianGreedyStrategy / PersistentPatrolStrategy / BarrierStrategy (stub). PersistentPatrol is the default: hard revisit bound T via force-visit on oldest cell. Strip `SearchRegion` replaces circle as search area primitive. |
| ADR-013 | Shark detection dataset + training | YOLOv8s fine-tune on leakage-free source-disjoint split (ADR-014 cross-ref). Training pipeline in `training/`. |
| ADR-014 | Leakage-free dataset split | Source-disjoint (not frame-random) train/val split to prevent temporal leakage. Re-validation required after split fix. |
| **ADR-015** | **Comms / GCS architecture** | **QGroundControl off-the-shelf for flight/missions/failsafe/HUD (MAVLink to PX4 Pixhawk 6C Mini via SiK or RFD900 radio). Custom thin detection view only: `Detection` ROS topic → Foxglove panel or rosbridge→web map. No full custom GCS.** |

Record each in `docs/DECISIONS.md` before the next implementation phase.
