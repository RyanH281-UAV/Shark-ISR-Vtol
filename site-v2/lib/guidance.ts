/*
 * Shared guidance decision model — the single source for the confidence rule
 * that gates SEARCH → TRACK. Both the 2D AutonomyLoop sim and the 3D
 * MissionCanvas import these, so the *decision* is identical in either view:
 * confidence accumulates across frames and only a sustained τ crossing
 * (K_SUSTAIN frames) transitions the aircraft. One lucky frame never does.
 */
// SEARCH → SCAN → TRACK is the guidance framework. SCAN is the "look harder
// before you commit" phase: a candidate has appeared and confidence accumulates
// across frames; only a sustained τ crossing (K_SUSTAIN) promotes SCAN → TRACK.
// One lucky frame never flies the aircraft — that rule is a *state*, not a flag.
export type State = "TRANSIT" | "SEARCH" | "SCAN" | "TRACK" | "RTL";

export const TAU = 0.85; // confidence threshold
export const K_SUSTAIN = 6; // frames required above τ before transition
export const GAIN = 0.12; // confidence rise on a detection frame
export const DECAY = 0.05; // confidence fall on a miss
export const LOST = 0.25; // below this in TRACK → target lost, back to SEARCH
export const TICK_MS = 130;

export function clamp(v: number) {
  return Math.max(0, Math.min(1, v));
}

// State colour tokens (SITE_UPGRADE.md · STATES) — hex, for 3D materials.
export const STATE_COLOR: Record<State, string> = {
  TRANSIT: "#5A7A94",
  SEARCH: "#45B8AC",
  SCAN: "#3FA7D6", // NEW token — azure, "closing in / inspecting" (approve or swap)
  TRACK: "#E8A33D",
  RTL: "#C2604F",
};

// ponytail: no spatial sim existed in the repo (only the non-spatial state
// machine in AutonomyLoop). Grid + orbit geometry are NEW shared constants,
// named here so the 3D layout and the decision read from one place. Tune the
// grid/orbit here, not in the canvas. Upgrade path: a real Bayesian planner
// would replace the lawnmower coverage in MissionCanvas, keeping these dims.
export const CFG = {
  gridCols: 32,
  gridRows: 20,
  oceanW: 62, // world units along x
  oceanD: 42, // world units along z
  flyY: 0.8, // drone altitude above the ocean surface
  orbitR: 4, // orbit-to-observe radius (world units)
} as const;
