# Usage Plan — Driving Ruflo to Build This System

Ruflo is multi-agent orchestration layered on **Claude Code** (it's the rebrand of `claude-flow`).
You'll run Claude Code inside VS Code; Ruflo adds swarms, persistent vector memory, hooks, and a
plugin marketplace underneath it. Verify all commands against the repo README and `docs/USERGUIDE.md`
before running — Ruflo moves fast (it was on v3.10.x as of late May 2026).

## 0. Prerequisites

- **Claude Code** installed and working (the VS Code integration is fine — that satisfies "in VS Code").
- **Node.js / npx** available.
- A funded Claude Code / API setup. Ruflo can also route to other providers, but Claude is the default.
- ROS 2 toolchain for the actual build (`colcon`, a ROS 2 distro) — separate from Ruflo.
- PX4 stack for the build: PX4 SITL (Gazebo), the `px4_msgs` package (branch matching your PX4
  version), and the eProsima micro XRCE-DDS agent on the Pi 5 / dev host.

## 1. Install Ruflo

There are two install paths with very different surface areas (per the README):

| | Plugin path (lite) | CLI init (full) |
| --- | --- | --- |
| Gives you | slash commands + agent defs per plugin | full loop: agents, commands, skills, **MCP server, hooks, daemon** |
| Workspace files | none | `.claude/`, `.claude-flow/`, `CLAUDE.md`, settings |
| MCP server / hooks | no | yes |
| Best for | trying a plugin | **production use — pick this** |

**Use the full CLI init** for this project (you want the memory + hooks):

```
# in the project root
npx ruflo@latest init wizard        # interactive; works on every platform incl. Windows
# or: npx ruflo@latest init          # quick non-interactive
```

Then register the MCP server with Claude Code:

```
claude mcp add ruflo -- npx ruflo@latest mcp start
```

> `init` will create a `CLAUDE.md`. You already have a hand-written one in this kit — **merge yours
> in** (keep your project brief; let Ruflo add its operational section) rather than letting init
> overwrite it. Commit before running init so you can diff.

## 2. Install the plugins that fit this project

From the marketplace (`/plugin marketplace add ruvnet/ruflo`, then `/plugin install <name>@ruflo`),
or via the CLI. Recommended set for an autonomy-stack build:

| Plugin | Why for this project |
| --- | --- |
| `ruflo-core` | Foundation — required. |
| `ruflo-swarm` | Coordinate architect/coder/tester agents per phase. |
| `ruflo-sparc` | 5-phase methodology with quality gates → forces written design rationale. |
| `ruflo-goals` | Plan/track against `docs/BUILD_PLAN.md`. |
| `ruflo-adr` | Living decision record → writes into `docs/DECISIONS.md`. |
| `ruflo-testgen` | Find missing tests for the deterministic guidance/geolocation math. |
| `ruflo-docs` | Keep package READMEs current. |
| `ruflo-rag-memory` / `ruflo-rvf` | Persist + retrieve project knowledge across sessions. |
| `ruflo-cost-tracker` | Token budget for a long multi-session build. |
| `ruflo-observability` | Structured logs/traces of the agent runs. |

Skip the domain-specific ones (neural-trader, market-data, iot-cognitum) — not relevant here.

## 3. The driving loop

```
init + plugins → orient + freeze interfaces → swarm builds a phase (SPARC) → SITL gate → persist memory → next phase
```

1. **Session 1:** paste Prompt 1 from `KICKOFF_PROMPT.md`. Get the interface spec, review it, freeze
   `shark_isr_interfaces`.
2. **Each build session:** paste Prompt 2. It spins a swarm for the current phase, runs each package
   through SPARC, and stops at the SITL gate.
3. **End every session by persisting context to Ruflo memory** (the prompt does this). This is what
   makes a long build hold together — Ruflo's vector memory is the cross-session continuity, the way
   the file-based memory bank would have been for a different tool.

## 4. Mode of operation

- After `init`, Ruflo's hooks auto-route and coordinate in the background — you don't micromanage
  agents. Your job is to **hold the structure**: interfaces first, one package per task, SITL gates,
  decisions logged.
- Use the **swarm** for multi-package phases; use plain Claude Code for a single small fix.
- Use **SPARC** so each package ships with design rationale, not just code — this is also the artifact
  a hiring engineer wants to see.

## 5. How to stress it "to the limit" without it falling apart

- **Front-load context.** `CLAUDE.md` + `docs/` are doing the heavy lifting. When agents drift, fix
  the docs, not the chat.
- **Freeze the interface contract before any node.** This is the line between modular and spaghetti.
- **Make the README + SITL check part of "done"**, every task (the per-task instruction enforces it).
- **Watch cost + git.** Cost-tracker on, small commits, `git restore` for bad edits.
- **Review `docs/DECISIONS.md` and `docs/BUILD_PLAN.md` between sessions** — they're the project's
  durable memory; keep them true.
- **Don't let a swarm replan in circles.** If it loops, narrow the task to one package and re-engage.

## 6. Expansion strategy

The architecture grows without rework:

- **New sensor/payload** → new package (e.g. `shark_isr_thermal`) publishing `Detection`-compatible
  messages. Nothing else changes.
- **New behaviour** (multi-target, geofenced lanes) → extend `shark_isr_guidance` or add a sibling;
  the mission manager arbitrates.
- **New airframe / autopilot** → change `config/` + `shark_isr_autopilot` only (ADR-002).
- **Custom offboard guidance law** (SkimWing-style differentiation, if you want it here too) → slots
  into `shark_isr_guidance` behind the existing `GuidanceSetpoint` interface, no autopilot-boundary
  changes.

Each expansion runs the same loop: ADR logged, package built via SPARC, READMEs + tests, SITL gate,
persist memory.
