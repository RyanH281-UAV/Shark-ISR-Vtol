# Hardware Recommendations — Shark-ISR VTOL

> Companion to `HARDWARE_BRINGUP.md` (the *what to test*); this is the *what to buy / choose and
> why*, from the 2026-07-13 full-project review. Personal reference — measured numbers from the
> bench campaign supersede everything here.

## 1. Power — the highest-risk single component

- **5 V rail: order a ≥5 A buck now.** The owned LM2596S (3 A) will brown out the Pi 5 under
  inference transients (Pi 5 + AI HAT+ under load ≈ 15–25 W, plus camera and cooler). Options:
  a Pi-5-specific 5 V/5 A UBEC, or a quality 5 A+ buck (e.g. Pololu D24V50F5-class) with short,
  thick leads and bulk capacitance at the Pi end. Pass criterion is B04/B05: ≥ 4.9 V at the Pi
  input at 5 A continuous, no dip below 4.75 V on a 2–3 A load step.
- **Autopilot supply stays physically separate** (battery → power module → Pixhawk). B06 proves
  it: shorting the Pi rail off must not touch the Pixhawk. This is the "companion never in the
  safety-critical loop" boundary enforced in copper.
- Buy the measurement kit with the buck: USB-C PD tester or clamp/shunt meter — B02/B10 need
  real watt numbers, and the endurance model runs on them.

## 2. Battery — chemistry per flight phase (open ADR to record)

- **Early flight tests (F01–F06): 6S LiPo 4000 mAh.** Lighter (~550–600 g vs ~840 g), higher
  C-rate headroom for hover/transition mishaps, cheaper to sacrifice in a bad landing.
  ~71 Wh usable → plenty for 10–20 min test cards.
- **Endurance missions (F07+): 6S2P 21700 Li-ion (Molicel, 8400 mAh).** ~145 Wh usable ≈ 2× the
  LiPo. Hover draw for a ~2.5 kg tri-tiltrotor is roughly 300–500 W ≈ 15–25 A at 21.6 V — a 2P
  Molicel pack sustains that with margin (HORNET_PLATFORM §5 caveat 4 check will pass), but the
  ~250 g penalty only makes sense once the B01 mass table shows margin under MTOW.
- Per-pack log discipline (B03): label, weigh, IR per cell, measured capacity; reject < 90%.

## 3. Thermal — the highest-probability failure

- Sealed LW-PLA fuselage + sustained 15–25 W of Pi + Hailo **will** throttle without airflow.
  Fit the Pi 5 Active Cooler (AI HAT+ ships with matching spacers) and plan the vent cut *now*:
  intake near the nose (prop-wash shadow), exhaust aft — don't wait for the B09 soak to fail.
- B09 pass bar: 30 min sustained inference inside the closed fuselage (or cardboard air-volume
  mock), `vcgencmd get_throttled` = 0x0, SoC + Hailo temps stable. Record the airflow solution
  as an ADR; vents change the airframe.

## 4. Camera + detector geometry (ADR-010 numbers)

- At 30 m AGL, Standard lens (~55° horizontal FOV on the 4:3 IMX708): footprint ≈ **31 m
  cross-track × 23 m along-track**. At ~14 m/s cruise that is ~1.7 s of dwell ≈ 15–20 frames at
  10 Hz — exactly why the ADR-016 confidence gate (sustained evidence) is viable in flight.
- Guidance lane spacing is now sized to this: `strip_width_m: 25` (~20% overlap),
  `footprint_radius_m: 12`. If the altitude ever changes, these two follow it.
- **Calibrate intrinsics before B08** (checkerboard → real fx/fy/cx/cy into `perception.yaml`).
  The 616 px guess propagates directly into geolocation error.
- Record the as-installed camera mounting angle in `perception.yaml` at H6 — `geolocate.py`
  assumes nadir with image-top = body-forward.

## 5. Comms (ADR-015)

- **MAVLink telemetry radio: SiK/RFD900-class pair**, Pixhawk TELEM ↔ GCS laptop. Budget
  ~30–100 g + antenna placement away from GPS/compass — **add a line for it in the B01 mass
  table**; it is currently in no budget.
- No companion MAVLink code needed: QGC talks to the Pixhawk directly over the radio. The
  companion's only comms deliverable is the thin detection view (Detection topic → Foxglove
  panel or rosbridge → web map).

## 6. Mass budget headline (B01 before any wiring)

Everything above competes for the 2.5 kg MTOW. Order-of-magnitude stack: Pi 5 ~46 g + AI HAT+
~30 g + active cooler ~25 g + Cam3 ~4 g + buck/wiring ~40–60 g + radio ~30–100 g ≈ **175–265 g of
ISR payload** before the battery choice. Weigh as-assembled; ≥ 5% margin under MTOW or shed
mass before soldering (B01 pass bar).

## 7. Purchase list (short)

| Item | Why | Blocking |
|---|---|---|
| ≥5 A 5 V buck / Pi-5 UBEC | LM2596S insufficient (ADR-006) | B04 — everything |
| USB-C PD tester or shunt meter | Measured watts for B02/B05/B10 | B02 |
| SiK / RFD900 radio pair | ADR-015 GCS link | B15 |
| Checkerboard target (print) | Camera intrinsics for geolocation | B08 |
| Spare 6S LiPo 4000 mAh | Flight-test pack, sacrificial | F01 |
| 6S2P Molicel pack (or cells + BMS-less build) | Endurance missions | F07 |
