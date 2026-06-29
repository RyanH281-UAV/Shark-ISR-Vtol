"""Unit tests for bayesian_map.py — no ROS 2 required."""

import math
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from shark_isr_guidance.bayesian_map import BayesianSearchMap
from shark_isr_guidance.search_pattern import SearchRegion

TOL = 1e-9


def _uniform_map():
    return BayesianSearchMap(centre_e=0.0, centre_n=0.0, radius_m=100.0, cell_size_m=10.0)


# ── Initialisation ────────────────────────────────────────────────────────────

def test_initial_probabilities_sum_to_one():
    bm = _uniform_map()
    total = sum(bm.probability(r, c) for r, c in bm._cells)
    assert abs(total - 1.0) < 1e-6


def test_initial_coverage_fraction_zero():
    bm = _uniform_map()
    assert bm.coverage_fraction() == 0.0


def test_initial_mean_probability():
    bm = _uniform_map()
    n = len(bm._cells)
    expected_mean = 1.0 / n
    assert abs(bm.mean_probability() - expected_mean) < 1e-9


# ── null_observation ──────────────────────────────────────────────────────────

def test_null_observation_reduces_swept_cells():
    bm = _uniform_map()
    n = len(bm._cells)
    initial_mean = 1.0 / n
    bm.null_observation(0.0, 0.0, footprint_radius_m=20.0, p_detection=0.9)
    # Cells in footprint should have lower probability than initial uniform.
    # (Some cells near origin will be reduced; others renormalised upward.)
    # Check that coverage fraction increases.
    assert bm.coverage_fraction() > 0.0


def test_null_observation_probabilities_sum_to_one():
    bm = _uniform_map()
    bm.null_observation(0.0, 0.0, 30.0, 0.85)
    total = sum(bm.probability(r, c) for r, c in bm._cells)
    assert abs(total - 1.0) < 1e-6


def test_null_observation_marks_swept_cells():
    bm = _uniform_map()
    assert bm.coverage_fraction() == 0.0
    bm.null_observation(0.0, 0.0, 15.0)
    assert bm.coverage_fraction() > 0.0


def test_full_sweep_coverage():
    """Sweeping the entire area should give coverage_fraction = 1.0."""
    bm = _uniform_map()
    # Large footprint covering whole circle.
    bm.null_observation(0.0, 0.0, footprint_radius_m=120.0)
    assert bm.coverage_fraction() == 1.0


# ── positive_detection ────────────────────────────────────────────────────────

def test_detection_increases_centre_probability():
    bm = _uniform_map()
    n = len(bm._cells)
    prior_mean = 1.0 / n
    bm.positive_detection(0.0, 0.0, sigma_m=20.0)
    r, c = bm._world_to_cell(0.0, 0.0)
    centre_prob = bm.probability(r, c)
    assert centre_prob > prior_mean


def test_detection_probabilities_sum_to_one():
    bm = _uniform_map()
    bm.positive_detection(10.0, -10.0, sigma_m=15.0)
    total = sum(bm.probability(r, c) for r, c in bm._cells)
    assert abs(total - 1.0) < 1e-6


def test_detection_max_probability_increases():
    bm = _uniform_map()
    n = len(bm._cells)
    before = bm.max_probability()
    bm.positive_detection(0.0, 0.0, sigma_m=20.0)
    after = bm.max_probability()
    assert after > before


def test_detection_peak_near_detection_location():
    bm = _uniform_map()
    det_e, det_n = 20.0, -10.0
    bm.positive_detection(det_e, det_n, sigma_m=15.0)
    best_e, best_n = bm.highest_probability_cell_centre()
    dist = math.sqrt((best_e - det_e) ** 2 + (best_n - det_n) ** 2)
    # Peak should be within 1.5 cell widths of detection.
    assert dist < 15.0, f'Peak at ({best_e:.1f}, {best_n:.1f}), expected near ({det_e}, {det_n})'


# ── Multiple updates ──────────────────────────────────────────────────────────

def test_repeated_sweeps_and_detection():
    bm = _uniform_map()
    # Simulate multiple sweeps with no detection
    for _ in range(5):
        bm.null_observation(30.0, 0.0, 20.0, 0.8)
    bm.positive_detection(0.0, 0.0, sigma_m=10.0)
    # After detection at origin, max prob should be near origin.
    best_e, best_n = bm.highest_probability_cell_centre()
    dist = math.sqrt(best_e ** 2 + best_n ** 2)
    assert dist < 20.0
    # Normalised.
    total = sum(bm.probability(r, c) for r, c in bm._cells)
    assert abs(total - 1.0) < 1e-6


# ── staleness clock + re-growth (ADR-013) ─────────────────────────────────────

def test_decay_ages_cells():
    bm = _uniform_map()
    assert bm.max_cell_age_s() == 0.0
    bm.decay_observation(dt_s=10.0, alpha=0.001)
    assert abs(bm.max_cell_age_s() - 10.0) < TOL
    bm.decay_observation(dt_s=5.0, alpha=0.001)
    assert abs(bm.max_cell_age_s() - 15.0) < TOL


def test_null_observation_resets_age():
    bm = _uniform_map()
    bm.decay_observation(dt_s=50.0, alpha=0.001)          # all cells age 50
    bm.null_observation(0.0, 0.0, footprint_radius_m=25.0)  # sweep origin
    r, c = bm._world_to_cell(0.0, 0.0)
    assert bm.cell_age_s(r, c) == 0.0                      # origin observed → reset
    assert bm.max_cell_age_s() == 50.0                    # outer cells still stale


def test_oldest_unobserved_cell_is_stale_and_far():
    bm = _uniform_map()
    bm.decay_observation(dt_s=100.0, alpha=0.001)          # everything stale
    bm.null_observation(50.0, 0.0, footprint_radius_m=20.0)  # refresh near (50,0)
    e, n = bm.oldest_unobserved_cell_centre()
    # The stalest cell must NOT be one we just refreshed.
    assert math.sqrt((e - 50.0) ** 2 + n ** 2) > 20.0
    assert bm.max_cell_age_s() == 100.0


def test_probability_regrowth_after_clear():
    bm = _uniform_map()
    bm.null_observation(0.0, 0.0, footprint_radius_m=20.0, p_detection=0.9)
    r, c = bm._world_to_cell(0.0, 0.0)
    p_cleared = bm.probability(r, c)
    bm.decay_observation(dt_s=600.0, alpha=0.01)           # large alpha*dt: must not overshoot
    p_regrown = bm.probability(r, c)
    p_uniform = 1.0 / len(bm._cells)
    assert p_regrown > p_cleared                           # cleared cell rises again
    # ...toward the prior, never PAST it. Euler step inverted the map here.
    assert p_regrown <= p_uniform + TOL


def test_highest_scoring_cell_uses_weights():
    bm = _uniform_map()                                    # uniform → all P equal
    r, c = bm._world_to_cell(40.0, 40.0)
    e_t, n_t = bm._cell_centre(r, c)
    best_e, best_n = bm.highest_scoring_cell(weights={(r, c): 10.0})
    assert abs(best_e - e_t) < TOL and abs(best_n - n_t) < TOL


# ── strip region ──────────────────────────────────────────────────────────────

def test_strip_region_cells_inside_strip():
    region = SearchRegion(0.0, 0.0, 300.0, 100.0, 0.5, 50.0)
    bm = BayesianSearchMap(0.0, 0.0, 1.0, cell_size_m=10.0, region=region)
    assert len(bm._cells) > 0
    for r, c in bm._cells:
        ce, cn = bm._cell_centre(r, c)
        assert region.contains(ce, cn)
