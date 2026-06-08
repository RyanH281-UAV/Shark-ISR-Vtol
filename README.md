# Shark-ISR VTOL — Ruflo Starter Kit

A starter kit for building an **autonomous shark-monitoring VTOL** autonomy stack with **Ruflo**
(multi-agent orchestration on Claude Code) — engineered for clear modularity, expansion, and
self-documenting structure.

## What this is

The aircraft is a Titan Dynamics **Hornet** (1.1 m tri-tiltrotor VTOL). This repo is the **software
system** that turns it into a persistent ISR platform: transit → efficient search → detect →
orbit/observe → log, with the autopilot owning the inner loop and ROS 2 owning the outer loop.

This kit does **not** contain the finished code. It contains the **context, plan, prompts, and
scaffold** so Ruflo can generate the modular ROS 2 stack with you driving.

## Start here

1. **`USAGE_PLAN.md`** — install Ruflo, pick plugins, the driving loop, expansion strategy.
2. **`KICKOFF_PROMPT.md`** — the orchestration prompts to paste into Claude Code.
3. **`CLAUDE.md`** — the project brief Claude Code/Ruflo auto-read (your "full context").
4. Run **`scripts/scaffold.sh`** to lay out the ROS 2 workspace with a README per package.

## Layout

```
.
├── CLAUDE.md              # project brief (auto-read by Claude Code + Ruflo)
├── README.md              # this file
├── USAGE_PLAN.md          # how to install + drive Ruflo
├── KICKOFF_PROMPT.md      # orchestration prompts
├── docs/
│   ├── HORNET_PLATFORM.md # part summary + airframe design considerations + range working
│   ├── ARCHITECTURE.md    # system diagram, responsibility boundary, dataflow contract
│   ├── DECISIONS.md       # ADR-style locked decisions + rationale
│   ├── BUILD_PLAN.md      # phased plan (interfaces → sim → bridge → guidance → ...)
│   └── REGULATORY.md      # CASA / ops notes
├── scripts/
│   └── scaffold.sh        # generates ros2_ws/ skeleton + per-package READMEs
├── config/                # vehicle/mission params (YAML) — populated during build
├── sim/                   # SITL + Gazebo assets — populated during build
└── ros2_ws/               # created by scaffold.sh
```

## Module map (after scaffolding)

| Package | Responsibility |
| --- | --- |
| `shark_isr_interfaces` | The message contract — freeze first |
| `shark_isr_bringup` | Launch + aggregated params |
| `shark_isr_autopilot` | The only autopilot boundary — PX4 via uXRCE-DDS (MAVLink fallback) |
| `shark_isr_perception` | Camera + detector → geolocated detections |
| `shark_isr_guidance` | Search pattern, Bayesian map, orbit-on-detect |
| `shark_isr_mission` | Mission state machine + arbitration |
| `shark_isr_telemetry` | Logging + GCS relay |

## Principles (enforced via CLAUDE.md)

- Autopilot owns inner loop + tilt transition; ROS 2 owns the outer loop.
- Companion computer is never safety-critical.
- One package = one responsibility; modules talk via `shark_isr_interfaces` only.
- Energy is the binding constraint; MTOW 2.5 kg is a hard ceiling.
- No code reaches the aircraft until it passes a SITL check.

> Verify Ruflo commands against the current repo README / `docs/USERGUIDE.md` before running —
> the tool iterates quickly.
