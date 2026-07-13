"""Unit tests for confidence_gate.py — the SEARCH → TRACK evidence rule (ADR-016)."""

import pytest

from shark_isr_guidance.confidence_gate import ConfidenceGate


def make_gate(**kw) -> ConfidenceGate:
    defaults = dict(tau=0.85, k_sustain=6, gain=0.12, decay=0.05, lost=0.25)
    defaults.update(kw)
    return ConfidenceGate(**defaults)


def run_frames(gate: ConfidenceGate, n_frames: int, conf: float,
               det_per_tick: int = 2) -> int:
    """Simulate detections at det_per_tick × tick rate (camera 10 Hz, guidance
    5 Hz). Returns the tick index at which the gate triggered, or -1."""
    ticks = (n_frames + det_per_tick - 1) // det_per_tick
    for t in range(ticks):
        for _ in range(det_per_tick):
            gate.on_detection(conf)
        gate.on_tick()
        if gate.triggered:
            return t
    return -1


class TestSingleFrame:
    def test_one_lucky_frame_never_triggers(self):
        gate = make_gate()
        gate.on_detection(1.0)  # perfect-confidence single frame
        for _ in range(100):
            gate.on_tick()
        assert not gate.triggered
        assert gate.score == 0.0  # fully decayed

    def test_short_burst_never_triggers(self):
        # T10's old 5-frame injection must NOT transition under the gate.
        gate = make_gate()
        assert run_frames(gate, n_frames=5, conf=0.95) == -1
        for _ in range(50):
            gate.on_tick()
        assert not gate.triggered


class TestSustained:
    def test_sustained_stream_triggers(self):
        # 30 frames @ 0.95 (T10's new injection) must transition.
        gate = make_gate()
        assert run_frames(gate, n_frames=30, conf=0.95) >= 0

    def test_mock_burst_triggers(self):
        # T11 mock: 30 frames @ 0.75 (detector sim burst) must transition.
        gate = make_gate()
        trig = run_frames(gate, n_frames=30, conf=0.75)
        if trig == -1:
            # burst may finish before k_sustain ticks elapse — decay must not
            # drop the score below tau before the counter completes
            for _ in range(gate.k_sustain):
                gate.on_tick()
                if gate.triggered:
                    break
        assert gate.triggered

    def test_trigger_requires_k_consecutive_ticks(self):
        gate = make_gate(k_sustain=3, tau=0.8)
        gate.score = gate.tau  # at threshold — one decay tick drops below
        gate.on_tick()  # counter resets
        assert not gate.triggered
        gate.score = 1.0  # decays 0.95 → 0.90 → 0.85, all ≥ tau
        gate.on_tick()
        gate.on_tick()
        assert not gate.triggered  # only 2 consecutive
        gate.on_tick()
        assert gate.triggered


class TestLost:
    def test_lost_after_decay(self):
        gate = make_gate()
        gate.score = 1.0
        assert not gate.lost
        for _ in range(15):  # (1.0 - 0.25) / 0.05 = 15 ticks
            gate.on_tick()
        assert gate.lost

    def test_detections_hold_track(self):
        gate = make_gate()
        gate.score = 1.0
        for _ in range(100):  # orbiting with target in view
            gate.on_detection(0.75)
            gate.on_detection(0.75)
            gate.on_tick()
        assert not gate.lost


class TestBounds:
    def test_score_clamped(self):
        gate = make_gate()
        for _ in range(100):
            gate.on_detection(1.0)
        assert gate.score == 1.0
        for _ in range(1000):
            gate.on_tick()
        assert gate.score == 0.0

    def test_reset(self):
        gate = make_gate()
        gate.score = 1.0
        for _ in range(10):
            gate.on_tick()
        gate.reset()
        assert gate.score == 0.0
        assert not gate.triggered

    def test_invalid_params_rejected(self):
        with pytest.raises(ValueError):
            ConfidenceGate(tau=0.0)
        with pytest.raises(ValueError):
            ConfidenceGate(k_sustain=0)
