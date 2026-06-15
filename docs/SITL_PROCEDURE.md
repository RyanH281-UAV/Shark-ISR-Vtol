# SITL Test Procedure — Shark-ISR VTOL

> The complete procedure for testing the autonomy stack in simulation, from cold
> start to a full mission rehearsal. Every behaviour in ADR-011 and every
> package checklist item maps to a numbered test here. Nothing flies until every
> test in §6 passes (ADR-005).
>
> Status: build + node bring-up verified 2026-06-11. Tests T1–T10 not yet run.

---

## 1. Architecture under test

```
┌─ Terminal 1 ──────────────────────────────┐  ┌─ Terminal 2 ─────────────────────┐
│ ./scripts/run_sim.sh                      │  │ ros2 launch shark_isr_bringup    │
│  ├─ Gazebo Harmonic (shark_isr_coastal)   │  │            sitl.launch.py        │
│  ├─ MicroXRCE-DDS agent (UDP :8888)       │  │  ├─ autopilot_bridge             │
│  └─ PX4 SITL (airframe 4020 gz_tiltrotor) │  │  ├─ guidance_node                │
│                                           │  │  ├─ mission_node                 │
│         PX4 uORB ⇄ XRCE-DDS ⇄ ROS 2 DDS   │  │  ├─ mock_camera + detector (sim) │
│                                           │  │  └─ telemetry_node               │
└───────────────────────────────────────────┘  └──────────────────────────────────┘
                                                ┌─ Terminal 3 ─────────────────────┐
                                                │ test commands (§6) + monitoring  │
                                                └──────────────────────────────────┘
```

GPS origin: Cottesloe Beach, Perth WA (−31.998, 115.748). The ENU local origin
is wherever PX4's EKF initialises — at SITL start this is the Gazebo world origin.

---

## 2. One-time setup

Everything below persists across sessions. Skip anything already done.

```bash
# 2.1 PX4 SITL binary (already built — verify)
ls ~/PX4-Autopilot/build/px4_sitl_default/bin/px4

# 2.2 MicroXRCE-DDS agent (already installed via snap — verify)
micro-xrce-dds-agent --help | head -1

# 2.3 World symlink into PX4's world dir
ln -sf ~/projects/shark-isr-vtol/sim/worlds/shark_isr_coastal.sdf \
       ~/PX4-Autopilot/Tools/simulation/gz/worlds/shark_isr_coastal.sdf

# 2.4 Workspace build (clean build verified 2026-06-11; 8/8 packages)
cd ~/projects/shark-isr-vtol/ros2_ws
source /opt/ros/humble/setup.bash
colcon build --symlink-install
```

**Build gotchas (hit and fixed 2026-06-11):**

| Symptom | Cause | Fix |
|---|---|---|
| `failed to create symbolic link … existing path cannot be removed` | stale `build/` from a non-symlink or Windows build | `rm -rf build install log` and rebuild |
| `ros2 interface show` says `Unknown package 'shark_isr_interfaces'` | missing `<export><build_type>ament_cmake</build_type></export>` in package.xml — colcon silently built it as **catkin** | fixed in repo; if it recurs, check `install/<pkg>/share/<pkg>/package.dsv` for `catkin_pythonpath` hooks |
| `ros2 run shark_isr_perception …` finds no executables | missing `setup.cfg` (routes scripts to `lib/<pkg>/`) | fixed in repo |
| `Clock skew detected` warnings | WSL2 clock drift | benign; `sudo hwclock -s` if it bothers you |

---

## 3. Session start (every time)

**Terminal 1 — simulator:**
```bash
cd ~/projects/shark-isr-vtol
./scripts/run_sim.sh
```
Wait for the PX4 shell to show `Ready for takeoff!` (or at least the
`pxh>` prompt with no EKF error spam). First Gazebo start can take ~30 s.

**Terminal 2 — autonomy stack:**
```bash
cd ~/projects/shark-isr-vtol/ros2_ws
source /opt/ros/humble/setup.bash && source install/setup.bash
ros2 launch shark_isr_bringup sitl.launch.py
```
All six processes must report `started` with no tracebacks.
Variants: `with_perception:=false` (manual detection injection), `with_telemetry:=false`.

**Terminal 3 — test console:**
```bash
cd ~/projects/shark-isr-vtol/ros2_ws
source /opt/ros/humble/setup.bash && source install/setup.bash
```

---

## 4. Gate check — DDS bridge end-to-end (Phase 2 exit criterion)

Run before any behaviour test. All four must pass.

```bash
# G1: PX4 topics visible in ROS 2
ros2 topic list | grep fmu/out
# EXPECT: vehicle_local_position, vehicle_attitude, vehicle_global_position,
#         battery_status, vehicle_status (vtol_vehicle_status may be quiet until armed)

# G2: data flowing, not just advertised
ros2 topic hz /fmu/out/vehicle_attitude --window 50
# EXPECT: ~100 Hz (PX4 default); anything > 10 Hz is fine

# G3: bridge republishes unified VehicleState
ros2 topic hz /vehicle_state --window 50
# EXPECT: ~20 Hz (vehicle_state_hz param)

# G4: frame sanity on the ground
ros2 topic echo /vehicle_state --once
# EXPECT: position_enu_m ≈ (0, 0, 0); attitude_q ≈ identity (w≈1) when level;
#         latitude_deg ≈ -31.998; armed: false; offboard_active: false;
#         agl_valid: true with agl_m ≈ 0
```

**If G1 fails:** the XRCE agent isn't bridging. Check Terminal 1 for
`Microxrcedds_agent … session established`; confirm agent on UDP 8888; confirm
`uxrce_dds_client status` at the `pxh>` prompt says connected.

---

## 5. Monitoring during tests

Keep these running in spare terminals (or use PlotJuggler if installed):

```bash
ros2 topic echo /search_state                 # guidance phase + coverage
ros2 topic echo /detection                    # mock detections firing
ros2 topic echo /vehicle_state --field position_enu_m   # live position
ros2 topic echo /telemetry_summary            # telemetry rollup
```
PX4 side, at the `pxh>` prompt: `commander status`, `listener vehicle_status`.

---

## 6. Test campaign

Run in order — later tests assume earlier ones pass. Record results in §8.
Service call syntax used throughout:

```bash
AP='ros2 service call /autopilot_command shark_isr_interfaces/srv/AutopilotCommand'
MC='ros2 service call /mission_command shark_isr_interfaces/srv/MissionCommand'
GM='ros2 service call /set_guidance_mode shark_isr_interfaces/srv/SetGuidanceMode'
```

### T1 — Offboard engagement protocol (ADR-011 §3)

The bridge must stream ≥1 s of setpoints before switching, retry until
confirmed, and report real state.

```bash
$AP "{command: 0}"        # CMD_ARM
$AP "{command: 2}"        # CMD_OFFBOARD
sleep 3
ros2 topic echo /vehicle_state --once | grep -E "armed|offboard"
```
**PASS:** `armed: true`, `offboard_active: true` within ~3 s.
PX4 `pxh>`: `commander status` shows **Offboard** mode. No
`Offboard activation failed` in Terminal 1 (a single rejected first attempt
followed by a successful retry is acceptable; repeated failures are not).

### T2 — Mode-encoding fix: HOLD / RTL / LAND (the ACRO bug)

This is the safety-critical ADR-011 verification. Each command must land in
the right PX4 mode — previously RTL produced **ACRO**.

```bash
$AP "{command: 3}"   # CMD_HOLD  → PX4 must show "Hold"   (AUTO_LOITER)
$AP "{command: 2}"   # back to Offboard (re-engages per T1)
$AP "{command: 4}"   # CMD_RTL   → PX4 must show "Return" (AUTO_RTL)
```
**PASS:** `commander status` (or `listener vehicle_status` → `nav_state`)
reads 4=AUTO_LOITER, then 14=OFFBOARD, then 5=AUTO_RTL. **FAIL INSTANTLY** if
any command produces Acro/Manual/Stabilized. Land + disarm before continuing.

### T3 — Mission start: ARM → OFFBOARD → TRANSIT (PX4-confirmed)

```bash
$MC "{command: 0, search_lat_deg: -31.998, search_lon_deg: 115.748, \
     search_radius_m: 300.0, transit_alt_amsl_m: 50.0, \
     search_alt_amsl_m: 50.0, orbit_radius_m: 50.0}"
```
**PASS:** mission log shows `STARTING` → `PX4 confirmed armed + Offboard → transit`
→ `TRANSITING`. Vehicle climbs and flies toward the search centre. The
transition to TRANSITING must NOT happen before PX4 actually arms (watch for
preflight-check rejections — mission must stay in STARTING and time out at
`arm_timeout_s` if PX4 refuses).

### T4 — Boustrophedon search execution + ENU yaw

Continues from T3 (transit arrival auto-starts SEARCH), or directly:
```bash
$GM "{mode: 2, search_centre_enu_m: {x: 0.0, y: 0.0, z: 0.0}, \
     search_radius_m: 200.0, search_alt_enu_z_m: 50.0}"
```
**PASS:**
- `/search_state` shows `phase: 2` (SEARCH), `coverage_fraction` increasing.
- Plot `/vehicle_state` position: east-west rows ~60 m apart walking south→north.
- Vehicle nose points along the direction of travel (ENU yaw fix) — in Gazebo,
  the aircraft must NOT fly sideways or mirror-heading.
- No crash of guidance_node while `/search_state` publishes in every phase
  (exercises the `Point()` constructor fix).

### T5 — Detection → TRACK orbit (synthesised orbit, centre placement)

With perception running in sim mode, a mock detection (conf 0.75 ≥ 0.70
threshold) fires randomly (~2 %/frame). To force one deterministically:
```bash
# Either wait for the mock, or temporarily raise the rate:
ros2 param set /detector_node mock_detection_prob 0.5
```
**PASS:**
- guidance log: `Detection → TRACK orbit at (E, N) m ENU` where (E, N) is
  near the vehicle's position at detection time — NOT near the origin
  (verifies the ENU-origin fix; before the fix the orbit centre was wrong by
  the vehicle's distance from home).
- Vehicle settles into a ~50 m-radius circle around that point. Measure:
  min/max distance from centre over one lap should stay within ±10 m of
  `orbit_radius_m`.
- PX4 stays in **Offboard** the whole time (`commander status`) — the old
  DO_ORBIT path switched flight modes; the synthesised orbit must not.
- `/search_state` shows `phase: 3`, `target_locked: true`, sane
  `tracked_lat/lon` (≈ −31.99x / 115.7x, never 0.0).

### T6 — Track timeout → resume search

Let the orbit run untouched for `track_timeout_s` (default 120 s; for a faster
test: `ros2 param set /mission_node track_timeout_s 30.0` before T5).
**PASS:** mission log `Track timeout … resuming search`; guidance returns to
`phase: 2`; vehicle resumes the lawnmower **with PX4 still in Offboard and
the vehicle actually following waypoints again** (this exact handover was
broken before ADR-011 — watch that setpoints are obeyed, not ignored).

### T7 — Abort / RTL from mission level

While searching:
```bash
$MC "{command: 1}"     # CMD_ABORT
```
**PASS:** mission → `RETURNING`; PX4 switches to **Return** (AUTO_RTL, nav_state
5 — not ACRO); vehicle flies home and lands. This is T2 exercised through the
full mission path.

### T8 — Low-battery failsafe

```bash
ros2 param set /mission_node low_battery_threshold 0.95   # force-trigger
```
(SITL battery drains slowly from 1.0; 0.95 trips within a few minutes — or
use `pxh> failure battery low` if the SITL build supports failure injection.)
**PASS:** mission log `LOW BATTERY … triggering return` exactly once
(latch verified — no repeat triggers); behaviour as T7.

### T9 — Companion-loss failsafe (ADR-003 — the one that matters most)

While the vehicle is mid-search in Offboard: **kill the entire ROS 2 stack**
(Ctrl-C Terminal 2).
**PASS:** within ~1–2 s PX4 detects the OffboardControlMode stream loss and
fails over to its own Hold/RTL (check `commander status` + Terminal 1 log
`Offboard control lost`). The aircraft must never continue blindly on the last
setpoint. This validates that the companion is not safety-critical — the
PX4-side failsafe behaviour (COM_OBL_RC_ACT / COM_OF_LOSS_T params) decides
Hold vs RTL; record which fires.

### T10 — Geolocation sanity (perception chain)

With the vehicle in steady SEARCH at 50 m and mock detections firing:
```bash
ros2 topic echo /detection
```
**PASS:** `geo_valid: true`; detection lat/lon within ~100 m of the vehicle's
current lat/lon (mock bbox is near image centre → target nearly below the
vehicle); `position_std_m` ≈ 2–5 m at 50 m AGL. With the vehicle banked in a
turn, lat/lon offsets shift in the **correct direction** (toward the lowered
wing side — verifies the body→world attitude fix in real geometry; the unit
tests prove the math, this proves the plumbing).

---

## 7. Telemetry verification (Phase 7 closeout)

After any full run:
```bash
ls /tmp/shark_isr_logs/
python3 -c "
import json,sys,glob
f=sorted(glob.glob('/tmp/shark_isr_logs/*/detections.jsonl'))[-1]
print(sum(1 for _ in open(f)), 'detections logged in', f)"
```
**PASS:** JSONL session directory exists, detection/vehicle-state records
parse as JSON, timestamps monotonic.

---

## 8. Results record

Copy per session into `docs/sitl_runs/YYYY-MM-DD.md`:

| Test | Description | Result | Notes |
|---|---|---|---|
| G1–G4 | DDS bridge gate | ☐ | |
| T1 | Offboard engagement | ☐ | |
| T2 | HOLD/RTL/LAND modes | ☐ | **safety-critical** |
| T3 | Mission start sequence | ☐ | |
| T4 | Search pattern + yaw | ☐ | |
| T5 | Detection → orbit | ☐ | |
| T6 | Track timeout handover | ☐ | |
| T7 | Abort/RTL | ☐ | |
| T8 | Low-battery failsafe | ☐ | |
| T9 | Companion-loss failsafe | ☐ | **safety-critical** |
| T10 | Geolocation sanity | ☐ | |

All ☑ + a clean telemetry log = Phase 2–7 SITL exit. Then, and only then,
Phase 8 hardware bring-up (after the 5 A regulator + thermal fixes, ADR-006).

---

## 9. Troubleshooting

| Symptom | Likely cause | Action |
|---|---|---|
| `gz: command not found` | PX4 gz env not sourced | run_sim.sh sources it; don't launch gz manually |
| Gazebo starts, PX4 exits immediately | world symlink missing/stale | redo §2.3 |
| No `/fmu/out/*` topics | agent not bridging | restart run_sim.sh; check `uxrce_dds_client status` at pxh> |
| Topics exist, no data | QoS mismatch on manual `ros2 topic echo` | add `--qos-reliability best_effort` to echo PX4 topics |
| Offboard switch always rejected | EKF not ready / no GPS lock yet | wait for `Ready for takeoff!`; check `ekf2 status` |
| Arm rejected | preflight checks (common SITL: no RC) | `pxh> param set COM_RC_IN_MODE 4` (joystick/none) or `param set NAV_RCL_ACT 0` for bench tests — note it in the run log |
| Vehicle ignores setpoints after orbit/hold | PX4 left Offboard | check nav_state; T1 retry logic should re-engage on next CMD_OFFBOARD; if reproducible, file it |
| Nodes silent under `head`/pipes | stdout buffering | log to file or `export RCUTILS_LOGGING_BUFFERED_STREAM=0` |
| WSL: no Gazebo GUI | server-only launch (`-s` flag in run_sim.sh) | headless is intended; for visuals run `gz sim -g` in another terminal (WSLg) |

---

*Created 2026-06-11. Companion to ADR-011 (docs/DECISIONS.md) — tests T1, T2,
T5, T6 exist specifically to verify that review's fixes in simulation.*
