# Decision Log (ADR-style)

Seed entries for the project. The Ruflo ADR workflow appends new ones here as decisions are made.
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

*Open decisions to record when made: specific detector model/`.hef`; geolocation method (camera
intrinsics + vehicle attitude + AGL → lat/lon); comms/link architecture; battery chemistry choice
against the mass/power budget.*

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
