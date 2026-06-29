# CLAUDE.md — Autonomous Shark-Monitoring VTOL

> This is the project brief Claude Code reads on every session. Ruflo agents inherit it.
> Treat the hard constraints and locked decisions here as non-negotiable unless explicitly changed.
> Detailed references live in `docs/`.

## What this project is

A modular **ROS 2 autonomy stack** running on a companion computer aboard a **Titan Dynamics Hornet**
(1.1 m tri-tiltrotor VTOL). The aircraft performs **autonomous persistent ISR**: transit to an area,
run an efficient search pattern, and on detecting a target (shark) switch to a loiter/orbit-to-observe
behaviour while logging geolocated detections.

Engineering framing: *autonomous persistent ISR with detection-triggered mode transition.* The shark
is the application; the engineering is maritime-patrol guidance, perception, and mission autonomy.

## Responsibility boundary (read this twice)

- **The autopilot (PX4) owns the inner loop and the tilt transition.** ROS 2 commands it over
  **uXRCE-DDS** (offboard setpoints, mode/`VehicleCommand`). **Do not** re-implement attitude or
  transition control in ROS 2 for this platform.
- **ROS 2 owns the outer loop:** mission, guidance, perception, telemetry.
- **The companion computer is never in the safety-critical loop.** Any loss (compute, link, battery)
  must degrade to an autopilot-handled safe state (RTL/loiter).

## Hard constraints

- **MTOW 2.5 kg** is a ceiling. Any payload proposal needs a mass figure that fits the budget.
- **Energy is the binding resource.** Prefer best-L/D loiter; minimise onboard compute draw.
- **No code reaches the aircraft until it has run in SITL** (`sim/`).
- All autopilot I/O lives in exactly one package (`shark_isr_autopilot`); the rest of the stack is
  firmware-agnostic. PX4-native **uXRCE-DDS** is the primary transport (MAVLink kept behind the same
  interface as fallback), so the autopilot stays a config choice, not a rewrite.

## Architecture (see docs/ARCHITECTURE.md)

ROS 2 packages, one responsibility each:
`shark_isr_interfaces` · `shark_isr_bringup` · `shark_isr_autopilot` · `shark_isr_perception` ·
`shark_isr_guidance` · `shark_isr_mission` · `shark_isr_telemetry`.

**Hardware:** PX4 autopilot (uXRCE-DDS to ROS 2). Companion computer = Raspberry Pi 5 + AI HAT+
(Hailo-8L, 13 TOPS) running the detector **onboard**, with Camera Module 3 via libcamera/picamera2.
See ADR-006 for the thermal / 5 V-rail / mass flags.

Platform facts and the binding energy/MTOW numbers: **docs/HORNET_PLATFORM.md**.
Locked decisions + rationale: **docs/DECISIONS.md**. Phased plan: **docs/BUILD_PLAN.md**.
Regulatory/ops notes: **docs/REGULATORY.md**.

## Conventions agents must follow

- **One ROS 2 package = one responsibility.** New capability → new package, not a new branch in a node.
- **Interfaces are the contract.** Modules depend only on `shark_isr_interfaces`, never on each
  other's internals. Freeze the interfaces before implementing nodes.
- **Frames + units explicit** on every position/velocity message.
- **Parameters in `config/` YAML**, never hardcoded.
- **No silent failures.** Log at appropriate severity; surface degraded states to the mission manager.
- **Every package has a README**: purpose, subscribed topics, published topics, services/actions,
  parameters, and a "run in isolation" command.
- **Tests:** unit-test deterministic math (search coverage, orbit geometry, geolocation) without a
  simulator; add a SITL check for every behaviour.
- Python: PEP 8 + type hints, `ament_python`. C++ (where used): `ament_cmake`, C++17.
- Small commits; commit messages explain *why*. Record decisions in `docs/DECISIONS.md`.

## How Ruflo should work this repo

- Use **swarm coordination** for multi-package phases; keep agents scoped to one package per task.
- Use **SPARC** (Specification → Pseudocode → Architecture → Refinement → Completion) for each
  package so design rationale is written down, not just code.
- Log architecture decisions via the **ADR** workflow into `docs/DECISIONS.md`.
- Use **goals/plan tracking** against `docs/BUILD_PLAN.md`; don't jump phases.
- Persist project knowledge to Ruflo memory at the end of each session so context survives.
- Keep an eye on **token cost** — this is a long multi-session build.

## Definition of done (per task)

Code + updated package README + unit tests for any deterministic math + a SITL check that passes +
a decision-log entry if anything non-trivial was decided. Nothing is "done" without the SITL check.
