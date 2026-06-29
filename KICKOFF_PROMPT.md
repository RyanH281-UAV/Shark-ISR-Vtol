# Kickoff Prompt (Ruflo on Claude Code)

These are the prompts you give **Claude Code** after Ruflo is initialised. With Ruflo's hooks active,
you mostly "use Claude Code normally" — the value of these prompts is forcing structure (interfaces
first, one package per task, SITL gates, decisions logged).

---

## Prompt 1 — orientation + interface contract (first session)

```
Read CLAUDE.md and everything in docs/ before doing anything (HORNET_PLATFORM.md, ARCHITECTURE.md,
DECISIONS.md, BUILD_PLAN.md, REGULATORY.md). This is an autonomous shark-monitoring VTOL: a modular
ROS 2 autonomy stack on a Raspberry Pi 5 companion computer (AI HAT+ Hailo-8L running the detector
onboard, Camera Module 3) aboard a PX4 Hornet tri-tiltrotor.

Treat the hard constraints in CLAUDE.md and the locked ADRs in docs/DECISIONS.md as non-negotiable
unless I explicitly change them.

This session, in order:
1. Confirm the responsibility boundary in one paragraph: autopilot owns inner loop + tilt transition;
   ROS 2 owns the outer loop.
2. Validate the package decomposition in docs/ARCHITECTURE.md. Propose changes only if a hard
   constraint forces one.
3. Produce the full interface spec for shark_isr_interfaces (Phase 1): every message/service field,
   type, unit, and coordinate frame. This is the contract; we freeze it next.
4. Append any decisions to docs/DECISIONS.md and update docs/BUILD_PLAN.md.

Do NOT implement nodes yet — interfaces first. Persist the project context to Ruflo memory before
you finish. Ask before deviating from any locked ADR.
```

---

## Prompt 2 — swarm build session (per phase)

```
Read CLAUDE.md and docs/ first, then load project context from Ruflo memory. We are building the
shark-monitoring VTOL stack phase by phase per docs/BUILD_PLAN.md.

Initialise a swarm for the current phase. Use a hierarchical topology with an architect coordinating
and specialist agents (coder, tester, reviewer) under it. Run each package through SPARC
(Specification, Pseudocode, Architecture, Refinement, Completion).

Rules for every task:
- One ROS 2 package = one responsibility. New capability = new package.
- Modules depend only on shark_isr_interfaces, never on each other's internals.
- All autopilot I/O stays inside shark_isr_autopilot (PX4 via uXRCE-DDS + px4_msgs).
- A behaviour is not done until it runs in SITL (sim/). Include the SITL check in the task.
- Every package gets/keeps a README (purpose, topics in/out, services/actions, params, run-in-isolation).
- Unit-test deterministic math without a simulator.
- Keep params in config/ YAML. Record decisions in docs/DECISIONS.md; tick docs/BUILD_PLAN.md.

Before starting, tell me which phase, the task breakdown, and which agents you'll spawn. Persist
context to Ruflo memory at the end of the session.
```

---

## Reusable per-package task instruction

```
Implement <package> via SPARC. Before coding, read its README stub and shark_isr_interfaces.
After: update the package README, add unit tests for any deterministic math, add/extend the SITL
check, and log any decision in docs/DECISIONS.md. Params go in config/ YAML, not source.
```

---

## Guardrails worth setting

- Run with the **cost-tracker** plugin on and a token budget — this is a long, multi-session build.
- Keep the repo under git with small commits so a bad swarm edit is one `git restore` away.
- If a swarm spins (re-planning loops, agents stepping on each other), drop back to plain Claude Code
  for that task and re-engage the swarm once the package boundary is clear again.
