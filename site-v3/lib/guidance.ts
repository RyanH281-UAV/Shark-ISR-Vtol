/*
 * Shared guidance decision model — the confidence rule that gates
 * SEARCH → TRACK. Mirrors the flight code exactly:
 * ros2_ws/src/shark_isr_guidance/shark_isr_guidance/confidence_gate.py
 * (ADR-016) and config/guidance.yaml. The demo and the aircraft run the
 * same rule with the same constants.
 */
export type State = "TRANSIT" | "SEARCH" | "TRACK" | "RTL";

export const TAU = 0.85; // confidence threshold (gate_tau)
export const K_SUSTAIN = 6; // ticks required above τ before transition (gate_k_sustain)
export const GAIN = 0.12; // confidence rise on a detection frame (gate_gain)
export const DECAY = 0.05; // confidence fall per tick (gate_decay)
export const LOST = 0.25; // below this in TRACK → target lost, back to SEARCH (gate_lost)
export const TICK_MS = 130;

export function clamp(v: number) {
  return Math.max(0, Math.min(1, v));
}

export const STATE_COLOR: Record<State, string> = {
  TRANSIT: "#5a7a94",
  SEARCH: "#45b8ac",
  TRACK: "#e8a33d",
  RTL: "#c2604f",
};
