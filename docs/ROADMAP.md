# Capability Roadmap — Shark-ISR VTOL

> **Lens:** what the system can *do* today, what's missing, and in what order the gaps close.
> This is the capability view. The phase-by-phase build order lives in `BUILD_PLAN.md`; locked
> technical decisions live in `DECISIONS.md`; the physical campaign lives in
> `HARDWARE_BRINGUP.md`. Updated 2026-07-13 (post-SITL campaign, post gate/strategy wiring).

**Status legend:**
✅ done and verified  ·  🔶 code-complete, SITL/hardware re-verification pending  ·  🟡 partial / stub  ·  ⬜ not started

---

## Where the project stands

The SITL campaign (T06–T11) ran and passed — orbit geometry, companion-loss failsafe, abort→RTL,
low-battery return, full end-to-end mission, and the perception→TRACK chain are all sim-verified
(evidence: `sim/orbit_trace.png`, README §SITL). Since that campaign, two headline behaviours were
wired into guidance (2026-07-13) and now need a **T10/T11 re-run** before they count as verified:

1. **Confidence gate (ADR-016)** — SEARCH→TRACK requires sustained evidence, not one frame.
2. **Persistent patrol (ADR-012)** — belief-driven strategy with hard revisit bound + probability
   re-growth replaces the fixed lawnmower (which remains available as `search_strategy: lawnmower`).

## Capability map

| # | Capability | State | Critical gaps |
|---|---|---|---|
| 1 | **Mission control** — full state machine, ARM→OFFBOARD→TRANSIT chain PX4-confirmed, pause/resume | ✅ (T08/T09/T10) | `mission_node` still has zero unit tests (state matrix, CMD_START guard). |
| 2 | **Search** — persistent patrol / greedy / lawnmower strategies over Bayesian map, re-growth, hard revisit bound | 🔶 | Wired 2026-07-13; **T10 re-run with `persistent_patrol` pending.** `BarrierStrategy` still an explicit stub. Strip `SearchRegion` used for alt only — mission still commands a circle. |
| 3 | **Detection gating** — confidence accumulates/decays; sustained τ crossing transitions; lost-target reverts to SEARCH | 🔶 | Wired 2026-07-13 (ADR-016), unit-tested; **T10/T11 re-run pending.** |
| 4 | **Perception** — HailoRT lifecycle, letterboxed ingest, geolocation, sim burst mode | 🟡 | `_hailo_forward` output parser is still a placeholder — adapt to the real `.hef` tensor layout on the bench (B08). `shark_detector.hef` compiled but not deployed (`hef_path` empty). No picamera2 camera node yet. |
| 5 | **Autopilot bridge** — uXRCE-DDS, offboard orbit synthesis, unified VehicleState, force-arm now gated behind `sitl_force_arm` | ✅ (T06/T07) | MAVLink fallback is a documented option, not code (nothing needs it — QGC talks MAVLink to the Pixhawk directly). |
| 6 | **Safety / failsafes** — battery→RTL, arm/transit/track timeouts, companion-loss verified | ✅ (T07/T08/T09) | PX4 geofence + RTL params still to be configured/verified on hardware (B13). CASA checklist before flight. |
| 7 | **Telemetry & logging** — JSONL flight/detections/events, 1 Hz summary | ✅ | No RF downlink — by design until ADR-015's radio lands (Phase GCS). |
| 8 | **GCS** — QGroundControl + thin detection view (ADR-015) | ⬜ | Radio (SiK/RFD900) purchase + QGC setup + Detection→Foxglove/rosbridge view. After hardware bench starts. |
| 9 | **Hardware bring-up** — Pi 5 + AI HAT+ + Cam3 + Pixhawk 6C Mini | ⬜ | `HARDWARE_BRINGUP.md` B01–B24, F01–F08. H0–H5 can start now. See `HARDWARE_RECOMMENDATIONS.md`. |
| 10 | **Cross-cutting** — tests, CI | 🟡 | 75/75 unit tests pass; mission_node untested; no project-level CI. |

---

## Near-term execution order

1. **SITL re-run: T10 + T11 with gate + patrol** (the only gate on calling capabilities 2–3
   verified). Save the console log to `sim/results/`.
2. **Hardware H0–H2 in parallel** (`HARDWARE_BRINGUP.md`): mass table (B01), power budget + ≥5 A
   buck order (B02), Pi bench + `.hef` deploy (B07/B08) — B08 also replaces the placeholder
   Hailo output parser with the real tensor layout.
3. **mission_node tests** — state transition matrix, CMD_START-without-position reject (now
   propagated honestly), battery failsafe mock.
4. **GCS slice (ADR-015)** — radio pair, QGC, detection overlay.
5. **Flight campaign F01–F08** — gated on all of the above + CASA checklist.

## Deliberately not doing

- Full custom GCS (ADR-015: QGC + thin detection view only).
- MAVLink companion fallback (documented option; zero current need).
- BarrierStrategy (stub until a beach-mouth interception scenario is real).
- SCAN as a separate mission phase — the gate models "look harder before committing" inside
  SEARCH; a distinct phase would change the frozen interface for no behavioural gain.
