# Hornet Platform — Part Summary & Design Considerations

> Source of all airframe figures below: *Titan Dynamics – Hornet VTOL, Build & User Manual, Revision 1.1*.
> This file is the authoritative platform reference for the autonomy stack. The agent must treat
> these as fixed constraints unless a flight log or measurement supersedes them.

## 1. Airframe identity

The Hornet is a **1.1 m wingspan tri-tiltrotor VTOL**. Two front motors tilt; the rear motor is
stationary. This is the physical platform the shark-monitoring ISR system flies on. The autonomy
stack does **not** own the tilt-transition control law — that lives in the autopilot firmware (see
`decisionLog.md`). Our software owns the *outer loop*: mission, guidance, perception, telemetry.

## 2. Stated specifications (from manual)

| Parameter | Value | Notes for autonomy |
| --- | --- | --- |
| Wingspan | 1100 mm | — |
| Wing area | 2238 cm² | — |
| Max take-off weight (MTOW) | 2.5 kg | **Hard payload ceiling.** ISR payload competes with battery. |
| Stated efficiency | 2.2 Wh/km | Cruise figure, ~stock weight. Used for range estimate below. |
| Cruise speed | 50–75 kph (≈13.9–20.8 m/s) | Sets sensor framerate / orbit radius assumptions. |
| Recommended prop | 7 in (7×4 or 7×5) | — |
| Root / tip / wingtip airfoil | NACA 4410 / 2410 / 0010 | — |
| Root chord / tip chord | 240 mm / 178 mm | — |
| Aspect ratio | 5.40 | — |
| Max L/D | 22 | Endurance-relevant; loiter near best-L/D speed. |
| Root incidence / dihedral / TE sweep | 3° / 0° / −7° | — |
| Structural test | survived 6.4 G at 3% cubic-subdivision infill | Manoeuvre/gust envelope ceiling. |

## 3. Recommended stock electronics (from manual)

| Item | Manual recommendation |
| --- | --- |
| Flight controller | Matek F405-WTE (or similar) |
| GPS / compass | Matek M8Q-5883 (or similar) |
| ESC | 3× 35 A BLHeli |
| Servos | 6× Emax ES08MAII |
| RC link | TBS Crossfire / ELRS |
| Video | 5.8 GHz / 1.2 GHz analog or digital (19×19 camera) |
| Battery | 6S2P 21700 Molicel 8400 mAh Li-ion, **or** 6S 4000 mAh LiPo |

**Autopilot setup (manual, ArduPilot/ArduPlane):** `Q_FRAME_CLASS = 7`, `Q_TILT_MASK = 3`,
`Q_TILT_TYPE = 0`. Control surfaces ±30° throw or more; CG marked under the wing; half flaps for
landing.

> **This project uses PX4, not ArduPlane (ADR-001).** The `Q_*` values above do not apply. On PX4 the
> Hornet is set up as a **Tiltrotor VTOL** airframe; geometry, the two front tilt servos, and the
> fixed rear motor are configured via the Actuator/control-allocation config in QGroundControl. The
> ±30° throws, CG, and flap guidance still apply.

## 4. ISR payload additions (this project — to be mass/power budgeted)

These turn the Hornet into a shark-monitoring ISR platform. The compute/sensing stack is now fixed
(ADR-006); masses must still be confirmed by weighing the assembled stack:

- **Companion computer:** Raspberry Pi 5. Hosts ROS 2 (outer loop), the uXRCE-DDS agent, and `px4_msgs`.
- **Inference accelerator:** AI HAT+ (Hailo-8L, 13 TOPS, INT8) over PCIe Gen 3. Runs the detector
  **onboard** via HailoRT on a `.hef`-compiled model — no inference downlink needed.
- **Camera:** Camera Module 3 (Sony IMX708, CSI-2), via libcamera/picamera2 into the detector.
- **5 V rail:** must power Pi 5 + HAT + camera under inference load. Official Pi 5 supply is 5 V/5 A
  (25 W). The owned **LM2596S (3 A) is likely insufficient** with inference + transients — spec a
  ≥5 A buck.
- **Storage:** for flight + detection logs.

**Binding constraints this adds:**
- **Thermal.** Sustained NN inference in a sealed LW-PLA fuselage will throttle the Pi 5/Hailo. The
  AI HAT+ ships with spacers for the Pi 5 Active Cooler; budget airflow/heatsinking (mass + power).
  Ambient operating range 0–50 °C.
- **Mass.** Pi 5 is ~46 g; with the AI HAT+, an active cooler, Camera Module 3, and wiring the stack
  is on the order of ~120–160 g — **weigh it as assembled** and check against the MTOW margin below.
- **Power → endurance.** Every watt of onboard compute is watt-hours not spent flying. Log the
  delta to Wh/km once measured.

**Open task (do not fabricate):** a mass budget and a power budget against the 2.5 kg MTOW and the
chosen battery, before flight. Tracked in `BUILD_PLAN.md`.

## 5. Range / endurance — order-of-magnitude only

The manual gives **2.2 Wh/km**. A still-air, cruise-only, stock-weight estimate:

**6S 4000 mAh LiPo**
- Energy: 22.2 V (6 × 3.7 V nominal) × 4.0 Ah = **88.8 Wh**
- Usable at 80% depth-of-discharge: 0.80 × 88.8 = 71.0 Wh
- Range: 71.0 Wh ÷ 2.2 Wh/km ≈ **32 km**

**6S2P 21700 Li-ion 8400 mAh**
- Energy: 21.6 V (6 × 3.6 V nominal for 21700 Li-ion) × 8.4 Ah = **181.4 Wh**
- Usable at 80%: 0.80 × 181.4 = 145.2 Wh
- Range: 145.2 Wh ÷ 2.2 Wh/km ≈ **66 km**

**Caveats (these numbers are optimistic upper bounds):**
1. The 2.2 Wh/km figure is cruise efficiency near stock weight; it excludes VTOL hover and the
   hover↔cruise transition, which are energy-expensive.
2. ISR payload pushes mass toward MTOW and **worsens** Wh/km — the real figure must be measured.
3. No navigation, loiter-on-station, or landing reserve is included.
4. Li-ion sustained-current limits at 6S2P may constrain hover thrust — verify against cell datasheet.

Use these only for first-cut mission planning. Replace with measured Wh/km from flight logs as soon
as available, and log the corrected value in `decisionLog.md`.

## 6. Design considerations the autonomy stack must respect

- **Energy is the binding constraint.** Persistent ISR = loiter time. Every onboard compute watt and
  every gram of payload trades against station time. Guidance should favour best-L/D loiter speeds.
- **The autopilot owns inner-loop + transition.** Do not re-implement the tilt-transition controller
  in ROS 2 for this platform; command PX4 over uXRCE-DDS (offboard setpoints, mode, `VehicleCommand`).
  Keep the boundary clean.
- **Autopilot-agnostic autonomy.** Talk to PX4 via uXRCE-DDS behind one package so the rest of the
  stack is firmware-agnostic (MAVLink fallback keeps ArduPilot reachable if ever needed).
- **Fail-safe first.** Loss of companion computer, loss of detection link, or low battery must all
  degrade to an autopilot-handled safe state (RTL/loiter). The companion computer is never in the
  safety-critical loop.
- **Everything is logged.** Flight logs + detection events + decisions, version-controlled, are the
  deliverable that demonstrates engineering understanding — not just that it flew.
