"""Unit tests for strategies.py — no ROS 2 required."""

import math
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from shark_isr_guidance.bayesian_map import BayesianSearchMap
from shark_isr_guidance.search_pattern import SearchRegion, boustrophedon_strip
from shark_isr_guidance.strategies import (
    LawnmowerStrategy,
    BayesianGreedyStrategy,
    PersistentPatrolStrategy,
    BarrierStrategy,
    STRATEGIES,
)

TOL = 1e-9


def _region():
    return SearchRegion(0.0, 0.0, 300.0, 120.0, 0.0, 50.0)


def _map(region):
    return BayesianSearchMap(0.0, 0.0, 1.0, cell_size_m=10.0, region=region)


# ── Lawnmower ─────────────────────────────────────────────────────────────────

def test_lawnmower_cycles_all_waypoints():
    region = _region()
    strat = LawnmowerStrategy(strip_width_m=40.0)
    path = boustrophedon_strip(region, 40.0)
    seen = []
    for _ in range(len(path) + 3):
        wp = strat.next_waypoints(region, _map(region), (0.0, 0.0))[0]
        seen.append((round(wp.east, 6), round(wp.north, 6)))
    path_set = {(round(p.east, 6), round(p.north, 6)) for p in path}
    assert path_set.issubset(set(seen))          # visits every lane endpoint
    assert seen[0] == seen[len(path)]            # wraps around


def test_lawnmower_ignores_belief():
    """Lawnmower must not be diverted by a detection peak — coverage floor."""
    region = _region()
    strat = LawnmowerStrategy(strip_width_m=40.0)
    bm = _map(region)
    bm.positive_detection(100.0, 40.0, sigma_m=10.0)
    first = strat.next_waypoints(region, bm, (0.0, 0.0))[0]
    expected = boustrophedon_strip(region, 40.0)[0]
    assert abs(first.east - expected.east) < TOL
    assert abs(first.north - expected.north) < TOL


# ── Bayesian greedy ───────────────────────────────────────────────────────────

def test_bayesian_greedy_targets_peak():
    region = _region()
    bm = _map(region)
    bm.positive_detection(80.0, 30.0, sigma_m=12.0)
    wp = BayesianGreedyStrategy().next_waypoints(region, bm, (0.0, 0.0))[0]
    assert math.sqrt((wp.east - 80.0) ** 2 + (wp.north - 30.0) ** 2) < 15.0
    assert abs(wp.up - region.alt_u) < TOL


# ── Persistent patrol (the default) ───────────────────────────────────────────

def test_patrol_force_visit_overrides_probability():
    """When a cell exceeds the revisit bound T, patrol force-visits the stalest
    cell, IGNORING a probability peak elsewhere."""
    region = _region()
    bm = _map(region)
    # age everything past T, then refresh + spike probability near (80,30)
    bm.decay_observation(dt_s=400.0, alpha=0.0)        # alpha 0 → pure aging
    bm.null_observation(80.0, 30.0, footprint_radius_m=15.0)
    bm.positive_detection(80.0, 30.0, sigma_m=10.0)    # peak where it's fresh
    wp = PersistentPatrolStrategy().next_waypoints(
        region, bm, (0.0, 0.0), revisit_bound_s=300.0
    )[0]
    # must go to a STALE cell (far from the fresh peak), not the peak
    assert math.sqrt((wp.east - 80.0) ** 2 + (wp.north - 30.0) ** 2) > 15.0


def test_patrol_nominal_follows_weighted_probability():
    """Below the revisit bound, patrol goes to the highest threat-weighted prob."""
    region = _region()
    bm = _map(region)
    bm.decay_observation(dt_s=10.0, alpha=0.001)        # young — under T
    bm.positive_detection(70.0, -20.0, sigma_m=12.0)
    wp = PersistentPatrolStrategy().next_waypoints(
        region, bm, (0.0, 0.0), revisit_bound_s=300.0
    )[0]
    assert math.sqrt((wp.east - 70.0) ** 2 + (wp.north + 20.0) ** 2) < 20.0


# ── Barrier (stub) + factory ──────────────────────────────────────────────────

def test_barrier_is_stub():
    # Stub must raise, not return [] — a silent empty plan would look like a
    # valid "no waypoints" answer to the caller (CLAUDE.md: no silent failures).
    region = _region()
    try:
        BarrierStrategy().next_waypoints(region, _map(region), (0.0, 0.0))
    except NotImplementedError:
        pass
    else:
        raise AssertionError('BarrierStrategy stub should raise NotImplementedError')


def test_strategy_factory_keys():
    assert set(STRATEGIES) == {
        'lawnmower', 'bayesian_greedy', 'persistent_patrol', 'barrier'
    }
    # all instantiable with no required args
    for cls in STRATEGIES.values():
        cls()
