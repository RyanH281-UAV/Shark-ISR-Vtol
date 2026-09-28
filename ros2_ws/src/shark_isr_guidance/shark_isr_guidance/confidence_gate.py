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

Worked numbers with the defaults (tau 0.85, K 6, gain 0.12, decay 0.05),
a 10 fps camera and a 5 Hz guidance tick — use these to reason about tuning:
  - one detection at confidence 0.75 adds 0.12 × 0.75 = 0.09
  - a continuous stream = 2 detections per tick = +0.18, minus 0.05 decay,
    so the score climbs ~0.13 per tick: 7 ticks to reach tau, and the tick
    that crosses it counts as the first of the 6 → TRACK on tick 12, i.e.
    ~2.4 s of steady detections
  - a 5-frame burst adds at most 0.45 → never reaches tau (T10 checks this)
  - with no detections, a full score (1.0) decays to lost (0.25) in
    (1.0 − 0.25) / 0.05 = 15 ticks = 3 s
Raise gain or lower tau → commits faster but trusts noise more; raise K →
more sustained evidence required; raise decay → forgets faster (both in
SEARCH and when judging a TRACK lost).
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
