"""
confidence_gate.py — Evidence accumulator gating SEARCH → TRACK (ADR-016).

Pure math, no ROS deps. Unit-tested in test/test_confidence_gate.py.

One lucky frame never flies the aircraft: detections add confidence-weighted
evidence, the score decays every guidance tick, and only a score held at or
above tau for k_sustain consecutive ticks triggers the transition. The
constants mirror the site's decision model (site-v2/lib/guidance.ts —
TAU / K_SUSTAIN / GAIN / DECAY / LOST) so the demo and the aircraft run the
same rule.

Usage (guidance_node):
    gate.on_detection(conf)   # every Detection message ≥ the confidence floor
    gate.on_tick()            # every guidance update tick (update_hz)
    gate.triggered            # SEARCH → TRACK when True
    gate.lost                 # TRACK → SEARCH when True (target gone)
"""


class ConfidenceGate:
    """Leaky-integrator confidence score with a sustained-crossing trigger."""

    def __init__(
        self,
        tau: float = 0.85,
        k_sustain: int = 6,
        gain: float = 0.12,
        decay: float = 0.05,
        lost: float = 0.25,
    ) -> None:
        if not 0.0 < tau <= 1.0:
            raise ValueError(f'tau must be in (0, 1], got {tau}')
        if k_sustain < 1:
            raise ValueError(f'k_sustain must be >= 1, got {k_sustain}')
        self.tau = tau
        self.k_sustain = k_sustain
        self.gain = gain
        self.decay = decay
        self.lost_threshold = lost
        self.score = 0.0
        self._ticks_above = 0

    def on_detection(self, confidence: float) -> None:
        """Add evidence from one detection (score rises gain × confidence)."""
        self.score = min(1.0, self.score + self.gain * confidence)

    def on_tick(self) -> None:
        """Advance one guidance tick: decay, then update the sustain counter."""
        self.score = max(0.0, self.score - self.decay)
        self._ticks_above = self._ticks_above + 1 if self.score >= self.tau else 0

    @property
    def triggered(self) -> bool:
        """True once the score has held ≥ tau for k_sustain consecutive ticks."""
        return self._ticks_above >= self.k_sustain

    @property
    def lost(self) -> bool:
        """True when evidence has decayed to the lost floor (target gone)."""
        return self.score <= self.lost_threshold

    def reset(self) -> None:
        self.score = 0.0
        self._ticks_above = 0
