# Decision Log (ADR-style)

Architecture decisions are recorded here as they are made.
Format per entry: context, decision, rationale, status.

---

### ADR-001 — Autopilot firmware: PX4

- **Context:** The Hornet manual recommends ArduPlane and gives `Q_`-parameter values, but Ryan's
  existing expertise and the SkimWing capstone are on PX4/Pixhawk. PX4 supports a native Tiltrotor
  VTOL type (the reference Convergence airframe is itself a two-front-tilt + fixed-rear tri-tiltrotor,
  matching the Hornet geometry).
- **Decision:** Use **PX4** for this project.
- **Rationale:** (1) Ryan is already fluent in PX4 → fastest path and direct skill/code transfer from
  SkimWing. (2) PX4's native ROS 2 path (uXRCE-DDS, see ADR-002) gives lower-latency, direct uORB↔ROS 2
  access for the offboard guidance work that is the project's real value. (3) PX4 supports the
  tiltrotor geometry via control allocation.
- **Trade-off / flag:** The Hornet vendor documents ArduPlane, not PX4 — so tiltrotor setup is
  hand-configured in QGC (airframe geometry + tilt servos), not copy-paste from the manual; budget
  extra bring-up time. Also: this puts the shark project on the *same* stack as the SkimWing capstone,
  which re-raises the "second PX4 VTOL looks redundant" concern. **Mitigation:** the differentiator is
  the autonomy/guidance layer (Bayesian search, detection-triggered ISR transition), not the flight
  stack — keep that the headline.
- **Status:** Locked (per Ryan). ArduPilot remains reachable via the ADR-002 boundary if ever needed.

---

### ADR-002 — Autopilot boundary: uXRCE-DDS primary, isolated in one package

- **Context:** PX4's documented ROS 2 middleware is uXRCE-DDS (native uORB↔ROS 2); MAVROS/MAVLink
  also works and is the portable cross-firmware option.
- **Decision:** All autopilot I/O is isolated in `shark_isr_autopilot`. For PX4 the primary transport
  is **uXRCE-DDS** (micro XRCE-DDS agent on the companion + `px4_msgs` in the workspace); offboard
  commands use `OffboardControlMode` + `TrajectorySetpoint` + `VehicleCommand` (with `target_system`
  matching `MAV_SYS_ID`). MAVLink is kept behind the same package interface as a fallback so ArduPilot
  remains reachable per ADR-001.
- **Rationale:** Native low-latency path for offboard guidance; matches SkimWing; clean boundary keeps
  the rest of the stack firmware-agnostic.
- **Status:** Locked.

---

### ADR-003 — Outer loop only in ROS 2; inner loop + transition in firmware

- **Decision:** ROS 2 owns mission/guidance/perception/telemetry and commands the autopilot. It does
  not run attitude or tilt-transition loops.
- **Rationale:** Don't duplicate a safety-critical controller; keep the companion computer out of the
  critical loop.
- **Status:** Locked.

---

### ADR-004 — Interfaces-first build order

- **Decision:** Define and freeze `shark_isr_interfaces` before implementing any node.
- **Rationale:** The message contract is the integration spine; changing it late is expensive.
- **Status:** Locked.

---

### ADR-005 — SITL-first; simulation parity required

- **Decision:** Every behaviour runs in SITL (`sim/`) before hardware.
- **Rationale:** Safety, cost, reproducibility — no untested code to a 2.5 kg aircraft.
- **Status:** Locked.

---

### ADR-006 — Companion computer + sensing: Pi 5 + AI HAT+ (Hailo-8L, 13 TOPS) + Camera Module 3; onboard inference

- **Context:** Need onboard outer-loop compute plus a vision detector on an energy-constrained
  airframe. Ryan specifies Raspberry Pi 5 + AI HAT+ (13 TOPS) + Camera Module 3.
- **Decision:** Pi 5 as companion computer. Camera Module 3 (Sony IMX708, CSI-2) via
  libcamera/picamera2. The detector runs **onboard** on the AI HAT+ Hailo-8L NPU (HailoRT runtime,
  model compiled to `.hef`). The Pi 5 also hosts the uXRCE-DDS agent and `px4_msgs` (ADR-002).
- **Rationale:** 13 TOPS Hailo-8L handles real-time object detection at the edge → the
  detection-triggered ISR transition happens onboard with **no inference downlink**; PCIe Gen 3 +
  camera-stack integration is turnkey; ~3–4 TOPS/W suits a battery-bound airframe far better than a
  GPU board.
- **Consequences / flags:**
  - Detector must be a **Hailo-compiled `.hef`** model — pick from the Hailo Model Zoo (e.g. a YOLO
    variant) or compile your own with the Dataflow Compiler. Not arbitrary runtime PyTorch.
  - **Thermal:** sustained inference inside a sealed LW-PLA fuselage will throttle. The AI HAT+ ships
    with spacers sized for the Pi 5 Active Cooler; plan airflow/heatsinking (mass + power cost).
    Ambient operating range 0–50 °C.
  - **Power:** size the 5 V rail for Pi 5 + HAT + camera under load. Official Pi 5 supply is 5 V/5 A
    (25 W); the owned LM2596S (3 A) is likely insufficient — spec a ≥5 A regulator.
  - **Mass:** weigh the assembled stack (Pi 5 + HAT + cooler + Cam3 + wiring) against the 2.5 kg MTOW
    payload margin.
- **Status:** Locked (per Ryan).

---

*Open decisions: battery chemistry choice against the mass/power budget.*

---

### ADR-007 — VehicleState.msg as firmware-agnostic vehicle telemetry boundary

- **Context:** Multiple packages (perception, guidance, mission, telemetry) need vehicle state
  (position, velocity, attitude, battery, VTOL phase). PX4 exposes these via `px4_msgs` topics
  (`VehicleLocalPosition`, `VehicleAttitude`, `VehicleGlobalPosition`, `BatteryStatus`,
  `VtolVehicleStatus`). If non-autopilot packages subscribe to `px4_msgs` directly, swapping
  firmware requires rewriting them all — breaking ADR-002.
- **Decision:** `shark_isr_autopilot` re-publishes a unified `VehicleState.msg` (from
  `shark_isr_interfaces`) that all other packages subscribe to. It is the sole translator of PX4
  NED/FRD conventions to ROS 2 ENU/FLU and the sole `px4_msgs` consumer among user packages.
- **Rationale:** Maintains the ADR-002 firmware-agnostic boundary without duplicating conversion
  logic. All other packages are truly firmware-independent.
- **Status:** Locked (2026-05-31, Phase 1 freeze).

---

### ADR-008 — Interface coordinate frame convention: ENU/FLU throughout; NED confined to autopilot package

- **Context:** PX4 uses NED (North-East-Down) position and FRD (Forward-Right-Down) body frames
  internally; ROS 2 REP-103 standard is ENU (East-North-Up) and FLU (Forward-Left-Up). Mixed
  conventions in message fields are a persistent source of integration bugs.
- **Decision:** All fields in `shark_isr_interfaces` messages use ENU/FLU (ROS 2 REP-103).
  Geographic coordinates use WGS-84 with `float64` for lat/lon. Heading angles in messages use
  ENU convention (0 = East, CCW positive). `shark_isr_autopilot` performs **all** NED↔ENU and
  FRD↔FLU conversions; no other package does this.
- **Rationale:** Single point of frame conversion; all other packages can be written, tested, and
  reasoned about in pure ENU without knowing PX4 internals.
- **Consequence:** GuidanceSetpoint yaw convention (ENU, 0=East, CCW+) must be documented
  prominently; the autopilot node converts to PX4 NED (0=North, CW+) on the way out.
- **Status:** Locked (2026-05-31, Phase 1 freeze).

---

### ADR-009 — Phase 1 interface set: six interfaces (4 msg + 2 srv)

- **Context:** ADR-004 mandates interfaces before nodes. ARCHITECTURE.md listed four candidate
  interfaces. The full system dataflow reveals two additional required interfaces.
- **Decision:** Phase 1 interface contract comprises:
  - `Detection.msg` — perception → guidance, telemetry
  - `VehicleState.msg` — autopilot → perception, guidance, mission, telemetry (new; see ADR-007)
  - `SearchState.msg` — guidance → mission, telemetry
  - `GuidanceSetpoint.msg` — guidance → autopilot
  - `MissionCommand.srv` — operator/GCS → mission
  - `SetGuidanceMode.srv` — mission → guidance (new; required to command search/orbit/transit)
  - `AutopilotCommand.srv` (arm/RTL/mode; mission → autopilot) is **deferred to Phase 3** — it
    requires PX4 `VehicleCommand` semantics and is best designed alongside that implementation.
- **Rationale:** VehicleState and SetGuidanceMode are required by the dataflow; omitting them
  would force ad-hoc workarounds in Phase 3+. Deferring AutopilotCommand avoids premature
  PX4-specific design decisions.
- **Status:** Locked (2026-05-31, Phase 1 freeze).

---

### ADR-010 — Patrol altitude 30m AGL; Camera Module 3 Standard lens

- **Context:** Detection requires a shark target to subtend enough pixels for the Hailo-8L detector to fire reliably. The Camera Module 3 comes in three variants (Standard, Wide, Global Shutter). Patrol altitude affects ground footprint, which drives apparent target size at the model's input resolution.
- **Decision:** Patrol altitude **30m AGL**. Camera Module 3 **Standard lens** (diagonal FOV ~66°, half-angle 33°). Wide and Global Shutter variants are not used.
- **Rationale:** First-principles pixel budget derivation using W = 2 × H × tan(33°) = 1.299 × H:

  | Alt (m) | Footprint (m) | Shark px (640 px input) | Detect? |
  |---------|---------------|------------------------|---------|
  | 30      | 39.0          | 41                     | ✅      |
  | 35      | 45.5          | 35                     | ✅ borderline |
  | 40      | 52.0          | 31                     | ⚠️ marginal |

  Wide lens at 30m: only ~22 px → below 32 px detection threshold → ruled out.
  Global Shutter: not required (slow-moving target relative to frame rate).
  30m is the lowest operationally comfortable AGL for PX4 to hold reliably over water, and the pixel budget is comfortably above threshold.

- **Consequence:** `config/perception.yaml` sets `patrol_altitude_m: 30.0`. Actual AGL read from `VehicleState.altitude_agl_m` at runtime for geolocation.
- **Status:** Locked (2026-06-08, Phase 5 pre-implementation).

---

### ADR-011 — Orbit synthesised in Offboard; attitude_q is body→world

- **Context:** Code review (2026-06-11) found the TRACK orbit was implemented via
  MAV_CMD_DO_ORBIT with local NED metres in param5/6 (PX4 expects lat/lon degrees),
  re-sent at 20 Hz. DO_ORBIT also switches PX4 out of Offboard into Orbit flight
  mode (MC-only), leaving subsequent SEARCH position setpoints silently ignored.
  Separately, VehicleState.attitude_q was documented as world→body while the
  bridge actually publishes body→world; geolocate.py compensated by conjugating,
  so off-nadir geolocation errors would mirror. Unit tests used only yaw-only
  quaternions with nadir rays, which cannot distinguish the two conventions.
- **Decision:**
  1. The TRACK orbit is **synthesised by the autopilot bridge as streamed Offboard
     position setpoints** (target led ~23° ahead of the vehicle on the circle,
     yaw facing the centre). MAV_CMD_DO_ORBIT is not used.
  2. `VehicleState.attitude_q` is **body-FLU → ENU-world** (standard ROS
     orientation, REP-103). geolocate.py uses the quaternion directly (no
     conjugate). Convention is locked by two new convention-sensitive unit tests
     (heading-North off-centre bbox; 20° roll nadir bbox).
  3. Offboard engagement: bridge streams setpoints for ≥1 s before commanding
     OFFBOARD and retries each second until `VehicleStatus.nav_state` confirms.
     `armed`/`offboard_active` in VehicleState now come from PX4 VehicleStatus,
     not heuristics.
- **Rationale:** Staying in Offboard for the orbit works in both hover and
  fixed-wing VTOL phases, eliminates mode re-engagement on TRACK→SEARCH, and
  removes the command-spam and unit bugs in one move. body→world is what the
  frame-transform chain actually produces and matches every other ROS consumer's
  expectation of an orientation quaternion.
- **Consequence:** Same review also fixed: PX4 custom-mode encoding for
  HOLD/RTL/LAND (previously sent POSCTL/ACRO/invalid — the ACRO-on-RTL bug was
  safety-critical), ENU-origin errors in detection/search-centre placement,
  ENU yaw convention in guidance setpoints, Point() keyword-construction crash,
  hold-position drift latch, and a mission-level TRACKING timeout (120 s default).
- **Status:** Locked (2026-06-11). The orbit-geometry and failsafe fixes are exercised by T06–T09;
  those runs' console output was never committed, so the verification is asserted rather than
  evidenced (see the provenance note in `README.md` § SITL verification).

---

### ADR-012 — Pluggable search strategies: PersistentPatrol default, strip search region

- **Context:** The guidance node hardcoded a boustrophedon pattern over a circle. For a
  beachfront swim zone the search area is a strip (long along-shore, narrow cross-shore), and
  operational use requires a choice of patrol doctrine: full coverage, first-find greedy,
  persistent coverage with a hard revisit bound.
- **Decision:** Introduce a `SearchStrategy` Protocol and four implementations in `strategies.py`:
  `LawnmowerStrategy` (coverage floor), `BayesianGreedyStrategy` (first-find/SAR),
  `PersistentPatrolStrategy` (default — hard revisit bound T: force-visit the oldest cell when
  any cell exceeds T, otherwise highest threat×probability cell), and `BarrierStrategy` (stub —
  IAMSAR barrier, deferred). A `SearchRegion` NamedTuple (rotated rectangle: centre, length,
  width, shore bearing, alt) replaces the circle as the search area primitive.
  `boustrophedon_strip` generates shore-parallel lanes over the strip. `check_feasibility`
  provides a pre-flight gate: loop time ≤ T and ≤ endurance, else named remedy.
- **Rationale:** Strategy is a config choice, not a rewrite. PersistentPatrol's hard revisit
  bound is the differentiator for beach ISR: it guarantees worst-case freshness, not just
  expected freshness. The strip region reflects real beach geometry.
- **Status:** Implemented + unit-tested (2026-06-18). **Wired into `guidance_node` 2026-07-13**
  behind the `search_strategy` param (default `persistent_patrol`; `lawnmower` keeps the
  T10-verified fixed-path baseline). `decay_observation` (probability re-growth) now runs every
  search tick. SITL re-run of T10 with the patrol strategy pending.

---

### ADR-013 — Shark detection: YOLOv8n fine-tuned on beach imagery

- **Context:** The Hailo-8L detector requires a `.hef`-compiled model. A YOLO variant is the
  pragmatic choice (Hailo Model Zoo support; real-time capable at edge). YOLOv8s was the initial
  candidate; the trained model is **YOLOv8n** (`training/runs/detect/train/args.yaml`).
- **Decision:** Fine-tune **YOLOv8n** on the curated beach/aerial shark dataset. Training
  pipeline lives in `training/` (`03_train.py` still accepts `--model yolov8s.pt` for a larger
  offline variant). Model compiled to `.hef` with the Hailo Dataflow Compiler for the AI HAT+.
- **Rationale:** Energy is the binding resource (CLAUDE.md): the nano backbone is the smallest
  model that clears the pixel budget (ADR-010: ~41 px target at 640 px input), and on a 13-TOPS
  INT8 NPU it buys frame rate and watts over YOLOv8s. Held-out results (mAP50 0.945, recall 95%)
  show the nano capacity is not the limiting factor — dataset honesty was (ADR-014). Fine-tuning
  is required because no base model has a beach-aerial shark class.
- **Status:** Trained on the leakage-free split; compiled to
  `training/runs/detect/train/weights/shark_detector.hef` (9 MB, hailo8l). On-Pi deployment
  (`hef_path`) and throughput measurement pending Phase 8 bench (B08). Updated 2026-07-13 to
  match the trained artifact — earlier text said YOLOv8s.

---

### ADR-014 — Leakage-free dataset split: source-disjoint, not frame-random

- **Context:** Initial training used a frame-random train/val split on video-derived imagery.
  Video frames from the same clip are highly correlated → train and val sets share near-duplicate
  frames → mAP50=0.988 was inflated (leakage, not generalisation).
- **Decision:** Enforce a **source-disjoint** split: all frames from a given source video/clip
  go entirely to train *or* val, never split across them. Re-validation after the split fix
  required before trusting eval numbers.
- **Rationale:** Honest eval is a safety-relevant claim. A detector with inflated mAP may miss
  real targets; the leakage must be closed before the model drives any safety-relevant detection.
- **Status:** Locked (2026-06-18, fix committed). Re-validation **done** — the retrained model
  scores mAP50 **0.945** on the held-out test split, evidenced by
  `training/runs/detect/val-2/BoxPR_curve.png`. The remaining figures quoted in `README.md`
  (mAP50-95, recall, precision) come from the same run but its console output was not saved;
  re-run `yolo val …sharks_eval.yaml` and commit the output to close that gap. Supersedes the
  "results pending" wording and reconciles the conflict with ADR-013.

---

### ADR-015 — Ground control station: QGroundControl + thin detection view

- **Context:** The stack has no GCS, no MAVLink radio, and no RF downlink. The architecture doc
  shows a GCS ↔ autopilot over MAVLink, but nothing was built. Options: (a) full custom GCS,
  (b) QGroundControl off-the-shelf + custom detection overlay only.
- **Decision:** Use **QGroundControl** for flight operations (maps, mission upload, telemetry
  HUD, arm/mode/failsafe, parameter tuning). Build only the custom slice QGC cannot provide: a
  live shark-detection feed with geo-pins — via a Foxglove panel subscribing to `/detection` or
  a rosbridge→web map. RF link: SiK or RFD900 MAVLink radio between Pixhawk 6C Mini and GCS
  laptop/tablet.
- **Rationale:** QGC is mature, PX4-native, and free. Re-implementing maps/HUD/mission editor
  would take months with no user-facing gain. The detection overlay is the only novel element.
  Lazy: build the 5%, reuse the 95%.
- **Consequences:** (a) Need a MAVLink radio (mass/power budget — factor into Phase 8). (b)
  QGC `.plan` files handle transit waypoints; the search strip is encoded as a `SearchRegion`
  YAML preset in `config/mission.yaml`. (c) `shark_isr_telemetry`'s "GCS relay" claim is
  satisfied by the QGC connection, not by the `/telemetry_summary` String topic alone.
- **Status:** Decision locked (2026-06-18). Implementation pending (Phase GCS — after SITL).

---

### ADR-016 — SEARCH → TRACK confidence gate: sustained evidence, not single frames

- **Context:** `guidance_node` transitioned to TRACK on any single detection ≥ 0.70 — one lucky
  frame could fly the aircraft to a whitecap. The public materials (README, site) had long
  described an accumulate/decay rule, but it existed only in the site's demo model
  (the site's browser demo model, now `site-v3/lib/guidance.ts`), not in the stack.
- **Decision:** A `ConfidenceGate` (pure math, `shark_isr_guidance/confidence_gate.py`) gates the
  transition: each detection adds `gain × confidence`; every guidance tick subtracts `decay`;
  SEARCH → TRACK fires only after the score holds ≥ `tau` for `k_sustain` consecutive ticks.
  In TRACK, score ≤ `lost` (evidence gone) returns guidance to SEARCH; the mission-level
  `track_timeout_s` remains as backstop. Constants (τ=0.85, K=6, gain=0.12, decay=0.05,
  lost=0.25) mirror the site model so the demo and the aircraft run the same rule. Gate applies
  only to detection-entered TRACK — a commanded `MODE_ORBIT` is never kicked back to SEARCH.
- **Consequences:** (a) `detector_node` sim mode emits *bursts* (`mock_burst_frames`, default 30)
  instead of single frames — a real target stays in the footprint for seconds, and the gate
  correctly ignores isolated blips. (b) T10 now asserts both halves: a 5-frame burst must NOT
  transition; a 30-frame stream must. (c) Unit-tested (`test_confidence_gate.py`); SITL re-run of
  T10/T11 pending.
- **Status:** Locked (2026-07-13).

---

### ADR-017 — Companion OS: Pi OS Bookworm host + Humble in Docker (supersedes "flash Ubuntu on the Pi")

- **Context:** ADR-006 fixes the companion computer as Pi 5 + AI HAT+ + Camera Module 3. The
  unwritten assumption behind it — and behind `HARDWARE_BRINGUP.md` B07's "Pi OS (64-bit) install,
  ROS 2 + workspace build on the Pi" — was that the Pi would run a single OS that had both the ROS 2
  Humble stack and working Pi 5 hardware support. No such OS exists:
  - The stack is frozen on **ROS 2 Humble / Ubuntu 22.04** (Phase 1 freeze; ADR-004/005). Humble
    has no Bookworm binaries.
  - Ubuntu does not support Pi 5 hardware before **24.04**, and **libcamera does not work on
    Ubuntu before 25.04** — so "flash Ubuntu on the Pi" costs either the camera or the frozen
    distro.
  - Building Humble from source on Bookworm, or porting the stack to Jazzy/Ubuntu 24.04, both
    break the SITL-parity guarantee ADR-005 depends on.
- **Decision:** Split the companion computer along the hardware/runtime boundary.
  - **Host = Raspberry Pi OS Bookworm (64-bit).** Owns all hardware: kernel, `hailo_pci` +
    HailoRT (`hailo-all`), the camera stack (libcamera/`rpicam-*`), and the Pixhawk serial port.
  - **Container = `ros:humble` (Ubuntu 22.04) via Docker**, running the frozen stack unchanged —
    `ros2_ws` bind-mounted, `colcon build` inside. Bit-identical to SITL.
  - **Four wires** cross the boundary and nothing else (`docker/run_pi.sh`):
    `--network host` (DDS discovery), `--device /dev/hailo0` (PCIe inference),
    `--device $PIXHAWK_DEV` (uXRCE-DDS ↔ PX4), and **camera as a localhost UDP stream, not a
    device** — the host runs `rpicam-vid` natively and `camera_node` in the container reads it,
    republishing `/camera/image_raw`, the same topic contract as `mock_camera_node`.
- **Rationale:**
  1. **SITL parity is preserved exactly (ADR-005).** The container is the same Ubuntu 22.04 +
     Humble the campaign T06–T11 was verified on. No distro port, no re-verification of the stack.
  2. **Pi 5 hardware support is preserved.** Bookworm is the reference OS for the Pi 5, the AI
     HAT+, and Camera Module 3 — the hardware is first-class instead of a fight.
  3. **The libcamera constraint is designed around, not worked around.** libcamera-in-Docker is
     the known Pi-camera pain point, so the container never touches the camera stack at all;
     capture is native and only pixels cross the boundary. Container needs OpenCV + ffmpeg only.
  4. Keeps the companion out of the safety-critical loop unchanged — a container crash is exactly
     as survivable as a node crash was.
- **Cross-references:**
  - **ADR-002** (uXRCE-DDS, autopilot I/O in one package): unchanged. The agent and the bridge run
    in the container; the Pixhawk serial device is passed through. The transport boundary is
    untouched.
  - **ADR-006** (Pi 5 + AI HAT+ + Camera Module 3, onboard inference): unchanged in substance and
    **refined in mechanism**. ADR-006 says "Camera Module 3 via libcamera/picamera2" — that remains
    true, but libcamera now runs on the **host**, not in the process that consumes the frames.
    HailoRT userspace is in the container; the `hailo_pci` kernel driver is on the host, and the
    HailoRT wheel version **must match** the host `hailo-all` version (a mismatch fails at runtime,
    not build time).
- **Consequences / flags:**
  - `docker/Dockerfile.pi`, `docker/run_pi.sh`, `docker/README.md`, and
    `shark_isr_perception/camera_node.py` (+ `test/test_camera_node.py`) implement this.
  - **Frame timestamps are read-time, not capture-time** — no capture stamp crosses the UDP
    boundary. Lag converts directly to geolocation error (~10 m/s of lag at cruise, against a 39 m
    diagonal footprint per ADR-010). **Total lag is unmeasured — measure at B08.** Note the obvious
    mitigation does not work: `CAP_PROP_BUFFERSIZE` is unsupported on the FFMPEG backend
    (`set()` returns `False` on OpenCV 4.5.4 / libavformat 58.45, which is what this container
    ships), so the depth-1 request is a no-op on the `udp://` path. If lag proves to matter, drain
    per tick or move capture into a thread; `picamera2` inside the container is the last resort
    (more fragile, lower latency).
  - **HailoRT version coupling is a hard requirement, not a soft one.** The pip wheel is
    bindings-only — its `_pyhailort.so` carries `DT_NEEDED: libhailort.so.4.20.0`, a *fully
    versioned* filename rather than a `.so.4` SONAME. `run_pi.sh` bind-mounts the host's library
    so userspace and kernel driver are the same build, but that does **not** make the wheel adapt
    to the host: upgrade `hailo-all` to 4.21 and `import hailo_platform` fails outright at load
    time. Rebuild the image with a matching wheel on every `hailo-all` upgrade.
  - **`--ipc host` is required, but not yet load-bearing.** `--network host` shares the network
    namespace and not the IPC namespace, so each container gets its own `/dev/shm`. Fast-DDS
    discovers over UDP (which works) and then prefers its shared-memory transport for same-host
    data — so participants match, `ros2 topic list` looks healthy, and the writer pushes into a
    ring buffer in its own `/dev/shm` that nobody reads. Silent data-plane failure behind a
    healthy control plane. In the *current* single-container design nothing needs this (the host
    runs no ROS 2); it becomes load-bearing as soon as the uXRCE-DDS agent and the stack are split
    across two `docker run` invocations. Set now so that split fails loudly rather than silently.
  - **The MJPEG demuxer is forced to remove a race, not because ffmpeg cannot detect MJPEG.**
    ffmpeg probes a bare elementary MJPEG stream from a file without difficulty. The problem is
    specific to joining a live `udp://` source mid-stream: the first `probesize` bytes may contain
    no JPEG SOI marker, so `ff_mjpeg_probe` scores low and detection is non-deterministic —
    sometimes fine, sometimes mis-detected, sometimes the open-timeout fires inside
    `avformat_find_stream_info`. `OPENCV_FFMPEG_CAPTURE_OPTIONS=input_format;mjpeg` forces the
    demuxer and removes the race.
  - `rpicam-vid --width/--height` must equal `image_width`/`image_height` in
    `config/perception.yaml`, or the stretch invalidates the `fx/fy/cx/cy` intrinsics.
- **Status:** Locked (2026-08-04); consequences corrected 2026-08-13 after empirical checking (the
  original entry asserted `CAP_PROP_BUFFERSIZE` controlled queue depth and that the library mount
  removed version coupling — both wrong). **B07a host gates passed 2026-08-10**
  (`hailortcli fw-control identify` → Hailo-8 / HAILO8L, firmware 4.20.0; `rpicam-hello
  --list-cameras` → imx708). **B07b container gates partially passed**: `docker build`, in-container
  `colcon build`, and in-container HailoRT device access all work; `ros2 topic hz /camera/image_raw`
  at `camera_fps` is **still open**. See `HARDWARE_BRINGUP.md` B07 and `docs/logs/bringup_log.md`.

---

## Deferred Watch Items

Short-lived simplifications accepted deliberately. Each entry names the trigger for revisiting.

---

### DWI-001 — guidance_node IDLE publishes nothing; bridge stale-hold covers it

- **Context:** `guidance_node` in `PHASE_IDLE` was publishing `TYPE_POSITION` setpoints at the
  vehicle's latched ground position at 5 Hz. This competed with test T06's orbit stream on the
  shared `guidance_setpoint` topic, causing 5/20 samples to measure distance ≈ 0.03 m instead of
  30 m. (Root cause: both publish to the same topic; bridge picks last-received.)
- **Decision (2026-06-23):** IDLE → return early (no publish). The bridge's 2-second stale-timeout
  fires and holds via velocity=(0,0,0). Latched-position HOLD was removed.
- **Accepted trade-off:** If guidance transitions to IDLE *while the vehicle is flying with non-zero
  velocity*, the bridge's velocity-hold cuts in instead of a locked position hold. Vehicle may drift
  slowly until mission re-engages.
- **Revisit if:** A real flight or SITL run shows the vehicle drifting unacceptably when guidance
  goes IDLE mid-flight. Fix: restore `_publish_hold` but gate it on
  `_vehicle.armed and _vehicle.offboard_active`, and only trigger it after guidance has been in IDLE
  for ≥1 s (to avoid racing other publishers at startup).
- **Follow-up (2026-06-23, closed):** The IDLE-silent change exposed that the bridge's OFFBOARD
  mode-switch was gated behind "a fresh guidance setpoint is present" (it lived after
  `if hold: return`). With guidance IDLE-silent, the mode-switch never ran and OFFBOARD never
  engaged. Fixed by moving the mode-switch block before the hold early-return so it runs on every
  heartbeat tick regardless of setpoint state. Not a deferred shortcut — this closed the coupling
  cleanly. DWI-001 has no remaining watch item.
