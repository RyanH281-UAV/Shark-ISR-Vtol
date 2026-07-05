# Hardware Bring-Up & Physical Test Plan — Shark-ISR VTOL

> The physical-world counterpart of `SITL_PROCEDURE.md`. Every component — power,
> companion computer, autopilot, wiring, airframe — earns its way onto the aircraft
> through a numbered bench test here, exactly as every behaviour earned its way
> through T06–T11 in simulation. The end state is a full working prototype:
> the complete stack flying an autonomous search-and-track mission.
>
> Expands `BUILD_PLAN.md` Phase 8 into an executable campaign. Platform figures:
> `HORNET_PLATFORM.md`. Locked hardware decisions: ADR-001 (PX4), ADR-002
> (uXRCE-DDS), ADR-006 (Pi 5 + AI HAT+ + Camera Module 3), ADR-015 (QGC GCS).
>
> Status: not started. Blocked on nothing — H0 can begin today.

---

## 0. Ground rules

1. **SITL precedes hardware** (ADR-005) — the SITL campaign (T06–T11 + full
   rehearsal) must be green before Phase H6 (integrated aircraft) begins.
   H0–H5 are pure bench work and may run in parallel with SITL.
2. **Props off until explicitly stated.** Any test involving ESC/motor signals
   runs with propellers removed. Props go on only in H7, outdoors, aircraft
   restrained or ready to fly.
3. **LiPo discipline.** Charge/store in a LiPo bag, never unattended, storage
   charge (3.8 V/cell) between sessions, reject any cell below 3.0 V or puffed.
4. **One variable per test.** If a test fails, fix and re-run it before moving
   on — the numbering is a dependency order, not a menu.
5. **Log everything.** Every test gets a dated entry (result, measurements,
   anomalies) in `docs/logs/bringup_log.md`. Measured numbers supersede manual
   figures in `HORNET_PLATFORM.md` — update it and note the change in
   `DECISIONS.md` when they differ.
6. **CASA/ops checklist** (`REGULATORY.md`) gates every outdoor flight in H7.
   No flight without it.

---

## 1. Campaign map

```
H0 Inventory & budgets ──► H1 Power bench ──► H2 Companion bench ──┐
                                        │                          │
                                        └──► H3 Autopilot bench ───┤
                                                                   ▼
                              H4 Pi ⇄ Pixhawk integration bench (props off)
                                                                   ▼
                              H5 Full-stack bench rehearsal (props off)
                                                                   ▼
              SITL campaign green (T06–T11) ──► H6 Airframe integration
                                                                   ▼
                                        H7 Flight test campaign (incremental)
                                                                   ▼
                                        Working prototype: autonomous mission
```

Bench tests are numbered **B01–B24**; flight tests **F01–F08**. Numbers are
stable — reference them from commits and the bring-up log.

---

## 2. Phase H0 — Inventory, mass budget, power budget

No solder melts until the arithmetic closes. MTOW 2.5 kg is a ceiling
(`HORNET_PLATFORM.md` §2); energy is the binding resource.

- [ ] **B01 — Component inventory + individual masses.** Weigh every component
      on a kitchen/jewellery scale (±1 g): airframe as built, motors, ESCs,
      servos, Pixhawk 6C Mini, GPS/compass, RC receiver, MAVLink radio, Pi 5,
      AI HAT+, active cooler, Camera Module 3, battery(ies), wiring estimate.
      *Pass:* a filled-in mass table in `HORNET_PLATFORM.md`, total ≤ 2.5 kg
      with ≥ 5% margin. Over budget → shed mass or descope **before** wiring.
- [ ] **B02 — Power budget on paper.** Sum the 5 V loads (Pi 5 + HAT under
      inference ≈ 15–25 W, camera, cooler) and avionics loads. Size the 5 V
      rail: official Pi 5 supply is 5 V/5 A; the owned LM2596S (3 A) is
      expected to fail this (ADR-006) — spec and order a ≥ 5 A buck (or Pi
      5-specific UBEC) now, plus current-measurement kit (USB-C PD tester or
      clamp/shunt meter).
      *Pass:* written budget with ≥ 30% headroom on every rail; parts ordered.
- [ ] **B03 — Battery baseline.** For each flight pack: label, weigh, measure
      internal resistance per cell (charger IR readout), full-charge capacity
      check via a measured discharge.
      *Pass:* per-pack log entry; packs within 10% of rated capacity, cells
      matched. Also confirms/records the chemistry choice left open in
      `DECISIONS.md` (6S LiPo vs 6S2P Li-ion — Li-ion needs the sustained-current
      check from `HORNET_PLATFORM.md` §5 caveat 4).

## 3. Phase H1 — Power bench

The 5 V rail is the highest-risk single component in the system: a brownout
reboots the Pi mid-flight (acceptable — companion is not safety-critical) or
resets the autopilot (never acceptable — it must have its own supply path).

- [ ] **B04 — 5 V rail under static load.** Bench supply or battery into the
      chosen buck; dummy load (or the Pi itself, B06) at expected draw.
      Measure output voltage at the *load end* of the cable at 1 A, 3 A, 5 A.
      *Pass:* ≥ 4.9 V at the Pi's USB-C/GPIO input at 5 A continuous; buck
      temperature stabilises below 70 °C.
- [ ] **B05 — Transient/brownout test.** Step the load (inference burst
      simulation: toggle a 2–3 A step on top of 2 A base). Scope or min/max
      voltmeter on the rail.
      *Pass:* no dip below 4.75 V (Pi 5 brownout threshold region); no buck
      restart. Fail → bigger buck, shorter/thicker cables, bulk capacitance.
- [ ] **B06 — Separate autopilot supply verified.** Pixhawk 6C Mini powered
      from its own power module (battery → PM → Pixhawk), Pi rail powered
      separately from the same battery. Kill the Pi rail with everything
      running.
      *Pass:* Pixhawk unaffected (no reboot, no voltage event in log) when the
      companion rail is shorted off. This is the "companion never in the
      safety-critical loop" boundary, physically enforced.

## 4. Phase H2 — Companion computer bench (Pi 5 + AI HAT+ + Camera Module 3)

Closes `BUILD_PLAN.md` Phase 5's open bench item and ADR-006's thermal flag.

- [ ] **B07 — Bring-up.** Pi OS (64-bit) install, ROS 2 + workspace build on
      the Pi, AI HAT+ detected over PCIe Gen 3 (`hailortcli fw-control identify`),
      Camera Module 3 streaming via libcamera/picamera2.
      *Pass:* `colcon build` clean on the Pi; `hailortcli` reports the Hailo-8L;
      camera preview at target resolution/framerate.
- [ ] **B08 — Detector on real hardware.** `.hef` model loaded (Model Zoo YOLO
      variant per ADR-006, `hef_path` set in `config/perception.yaml`);
      `detector_node` running in real (non-mock) mode against live camera.
      *Pass:* `/detection` messages publish end-to-end at the target rate;
      latency camera→Detection measured and logged.
- [ ] **B09 — Thermal soak.** Sustained inference ≥ 30 min at room temperature
      with the active cooler fitted, then repeat inside the (closed) fuselage
      or a cardboard mock of its air volume.
      *Pass:* no thermal throttling (`vcgencmd get_throttled` = 0x0), SoC and
      Hailo temps logged and stable. Fail in the fuselage → cut intake/exhaust
      vents, re-test; record the airflow solution as an ADR.
- [ ] **B10 — Power under inference.** Repeat B08 while measuring 5 V rail
      current/power.
      *Pass:* measured watts logged against the B02 budget; Wh impact on
      endurance computed and noted in `HORNET_PLATFORM.md`.

## 5. Phase H3 — Autopilot bench (Pixhawk 6C Mini + PX4)

Props off throughout.

- [ ] **B11 — Flash + airframe config.** PX4 v1.16 flashed; Tiltrotor VTOL
      airframe selected; actuator/control-allocation geometry configured in
      QGroundControl for the Hornet (two front tilt motors, fixed rear, ±30°
      control-surface throws per manual).
      *Pass:* QGC shows the correct airframe; parameter file exported to
      `config/px4/` and committed.
- [ ] **B12 — Sensor calibration + GPS.** Accel/gyro/compass/level calibration;
      GPS lock outdoors or at a window; compass sane vs. known heading.
      *Pass:* QGC pre-flight sensor checks green; HDOP/satellite count logged.
- [ ] **B13 — RC link + failsafe config.** ELRS/Crossfire receiver bound;
      channel mapping, arm switch, kill switch verified; RC-loss and battery
      failsafe parameters set (RTL) and RC-loss triggered by powering off the
      transmitter.
      *Pass:* PX4 enters the configured failsafe on transmitter-off; kill
      switch cuts outputs instantly.
- [ ] **B14 — Servo + ESC bench (props off).** All 6 servos move the correct
      surface in the correct direction; tilt servos sweep the full
      hover↔cruise range without binding; ESCs calibrated, motors spin correct
      direction at idle.
      *Pass:* QGC actuator-test tab drives every actuator correctly; tilt
      mechanism smooth through full travel under QGC transition command.
- [ ] **B15 — MAVLink radio link.** SiK/RFD900 radio pair configured
      (ADR-015); telemetry to the GCS laptop at expected range on the bench
      (attenuated) and RSSI logged.
      *Pass:* QGC connects over the radio, parameter download completes,
      link stats logged.

## 6. Phase H4 — Pi ⇄ Pixhawk integration bench

The wire that makes it one system. Props off.

- [ ] **B16 — Physical link + wiring loom v1.** Pixhawk TELEM/UART ↔ Pi (UART
      or USB-serial) wired; full harness laid out at flight lengths: battery →
      PM → Pixhawk, battery → buck → Pi, Pi ↔ Pixhawk serial, camera ribbon.
      Strain relief, polarity double-checked, connectors labelled, loom
      photographed for `docs/img/`.
      *Pass:* continuity + polarity verified with a meter before first
      power-on; single battery powers the whole stack.
- [ ] **B17 — uXRCE-DDS over the real link.** `micro-xrce-dds-agent` on the Pi
      against the Pixhawk serial port (PX4 `UXRCE_DDS_CFG` on the chosen
      TELEM port).
      *Pass:* `ros2 topic list | grep fmu` on the Pi shows PX4 uORB topics —
      the hardware twin of Phase 2's SITL gate.
- [ ] **B18 — Bridge on hardware.** `autopilot_bridge` on the Pi against the
      real Pixhawk.
      *Pass:* `/vehicle_state` publishes with sane values (attitude tracks
      hand-tilting the bench rig, battery voltage matches meter); an
      `AutopilotCommand` mode request is acknowledged.
- [ ] **B19 — Link-loss failsafe on hardware (T07 twin).** With PX4 in a bench
      offboard test (props off, actuator outputs observed), kill the Pi
      mid-stream.
      *Pass:* PX4 detects offboard timeout and falls back per configuration;
      Pixhawk itself unaffected (B06 already proved the power side).

## 7. Phase H5 — Full-stack bench rehearsal

Everything H2–H4 running together, props off — the hardware twin of the SITL
full-mission rehearsal.

- [ ] **B20 — Full launch on the Pi.** `ros2 launch shark_isr_bringup` (real
      hardware config): bridge, guidance, mission, perception (real detector),
      telemetry — all on the Pi, all against the real Pixhawk.
      *Pass:* every node healthy, `/telemetry_summary` at 1 Hz, no node above
      its CPU budget, total Pi power draw within B02.
- [ ] **B21 — Bench mission dry-run.** `MissionCommand CMD_START` with arming
      inhibited (or bench-safe arming, props off). Walk the state machine:
      IDLE → STARTING → (mode changes observed on Pixhawk) → abort → RTL
      command observed.
      *Pass:* mission/guidance state transitions mirror T08/T10 behaviour with
      the real autopilot in the loop.
- [ ] **B22 — Detection-in-the-loop.** Show the camera a target (printed shark
      on video, or any class the interim model detects) during the bench
      mission.
      *Pass:* real Detection → guidance TRACK transition → orbit setpoints
      visible on `/fmu/in/trajectory_setpoint` — T11 with photons instead of
      mocks.
- [ ] **B23 — Endurance bench soak.** ≥ 45 min full-stack run on battery
      power.
      *Pass:* no thermal throttle, no brownout, no node crash/restart, logs
      intact; measured stack Wh logged against the endurance budget.
- [ ] **B24 — Vibration + EMI sanity.** Motors at low throttle (props OFF,
      airframe restrained): watch EKF variance, compass interference, camera
      image, serial-link error counters.
      *Pass:* no EKF/compass alarms at bench throttle; DDS link error-free.
      (Full vibration truth arrives only in flight — this catches gross
      mounting/EMI mistakes early.)

## 8. Phase H6 — Airframe integration

- [ ] Mount stack in fuselage: Pi + HAT + cooler ventilation per B09 outcome,
      camera aimed per `geolocate.py` mounting assumptions (record the actual
      mounting angle in `config/perception.yaml`), antennas separated from
      compass/GPS.
- [ ] Final loom install; re-run B16 continuity checks post-install.
- [ ] Weigh the finished aircraft; CG at the manual's mark (half-flap landing
      config checked). Update the B01 mass table with as-built truth.
- [ ] Re-run B12 (compass/level) in the final installation — motors, radios
      and the Pi all moved relative to the compass.
- [ ] Range check RC + MAVLink radio at field distance.
- [ ] SITL campaign confirmed green (T06–T11 + rehearsal) — gate to H7.

## 9. Phase H7 — Flight test campaign

Incremental: each flight adds exactly one new thing. CASA/`REGULATORY.md`
checklist before every session. Kill switch and RC takeover rehearsed. Review
logs (PX4 ulog + `shark_isr_telemetry`) after **every** flight before the next.

- [ ] **F01 — Hover, manual/stabilised.** Companion powered but passive.
      *Pass:* stable hover, tame landing, log review clean (vibration levels,
      current draw at hover logged).
- [ ] **F02 — Hover failsafe pulls.** RC-loss → RTL/land verified in the air
      at low altitude; kill-switch procedure rehearsed mentally, not triggered.
- [ ] **F03 — Transition + cruise, manual/position.** First tilt transition
      airborne; cruise trim; back-transition; land.
      *Pass:* clean both transitions; cruise current → first measured Wh/km
      (correct `HORNET_PLATFORM.md` §5 and `DECISIONS.md`).
- [ ] **F04 — Autonomous mission, autopilot-only.** QGC `.plan` waypoint
      mission (transit-out, loiter, return), companion passive.
      *Pass:* full mission hands-off; loiter at best-L/D speed verified.
- [ ] **F05 — Offboard in hover (T06 twin, airborne).** Companion commands a
      short offboard position hold + small orbit at low altitude; RC pilot
      hovering thumb throughout.
      *Pass:* aircraft follows guidance setpoints; RC takeover practiced once.
- [ ] **F06 — Offboard link-loss in flight (T07 twin, airborne).** Kill the
      companion during F05-style offboard at safe altitude.
      *Pass:* PX4 failsafe to hold/RTL, pilot recovery not required.
- [ ] **F07 — Search pattern flight.** `CMD_START` → transit → boustrophedon
      search over a small survey box, no detection injected; perception
      logging live camera the whole time.
      *Pass:* pattern flown as generated; coverage + energy vs. prediction
      reviewed; camera footage usable (exposure, vibration blur).
- [ ] **F08 — Full mission: detection-triggered track.** Search with a
      plantable target (shark cutout/tarp on the survey area — or accept an
      interim-class target). Detection → TRACK orbit → operator observes on
      the detection view (ADR-015) → RTL.
      *Pass:* the headline behaviour, on hardware, end-to-end: **this is the
      working prototype.** Geolocation error vs. surveyed target position
      measured and logged.

---

## 10. Definition of done

The campaign is complete when F08 passes and:

- the bring-up log documents every B/F test with measurements,
- `HORNET_PLATFORM.md` carries measured mass, power, and Wh/km replacing
  manual estimates,
- non-trivial deviations are recorded as ADRs in `DECISIONS.md`,
- `BUILD_PLAN.md` Phase 8 items are checked off against their B-test numbers.

*Anything that flies differently from how it benched goes back to the bench.*
