"""
strategies.py — pluggable search strategies (ADR-013).

Pure math, no ROS deps. Unit-tested in test/test_strategies.py.

One interface, several behaviours, so the shark mission can ship persistent
patrol while keeping lawnmower / Bayesian-greedy / barrier available for other
domains (the strategy is a config choice, not a rewrite):

    LawnmowerStrategy       — complete coverage, ignores probability (the floor).
    BayesianGreedyStrategy  — chase the highest-probability cell (SAR / first-find).
    PersistentPatrolStrategy — DEFAULT. Threat-weighted nominal routing with a
                               HARD revisit bound: if any cell's age exceeds T,
                               force-visit the stalest cell; else go to the
                               highest threat-weighted-probability cell.
    BarrierStrategy         — intercept along a line (IAMSAR barrier). Stub.
"""

from typing import Protocol

from .bayesian_map import BayesianSearchMap
from .search_pattern import SearchRegion, Waypoint, boustrophedon_strip


class SearchStrategy(Protocol):
    """A search strategy maps (region, belief, vehicle state) → next waypoint(s)."""

    def next_waypoints(
        self,
        region: SearchRegion,
        bayes_map: BayesianSearchMap,
        vehicle_pos: tuple[float, float],
        threat_weights: dict[tuple[int, int], float] | None = None,
        revisit_bound_s: float = 300.0,
        n_ahead: int = 1,
    ) -> list[Waypoint]:
        """``n_ahead`` is a hint, not a guarantee. Belief-driven strategies
        (greedy, patrol) recompute from the live map and return a single
        waypoint regardless; only fixed-path strategies (lawnmower) honour it."""
        ...


class LawnmowerStrategy:
    """Complete-coverage boustrophedon over the strip. Ignores the belief map.

    The coverage floor. Caches the path per region and cycles through it in order,
    resuming from where it left off. ``vehicle_pos`` is ignored — after a mission
    diversion it resumes at the next path index, not the nearest lane.
    # ponytail: nearest-lane resume when divert-then-resume coverage gaps bite.
    """

    def __init__(self, strip_width_m: float = 60.0) -> None:
        self._strip_width_m = strip_width_m
        self._region: SearchRegion | None = None
        self._path: list[Waypoint] = []
        self._idx = 0

    def _ensure_path(self, region: SearchRegion) -> None:
        if self._region != region:
            self._region = region
            self._path = boustrophedon_strip(region, self._strip_width_m)
            self._idx = 0

    def next_waypoints(
        self,
        region: SearchRegion,
        bayes_map: BayesianSearchMap,
        vehicle_pos: tuple[float, float],
        threat_weights: dict[tuple[int, int], float] | None = None,
        revisit_bound_s: float = 300.0,
        n_ahead: int = 1,
    ) -> list[Waypoint]:
        self._ensure_path(region)
        out: list[Waypoint] = []
        for _ in range(max(1, n_ahead)):
            out.append(self._path[self._idx % len(self._path)])
            self._idx += 1
        return out


class BayesianGreedyStrategy:
    """Go to the highest-probability cell. First-find / SAR behaviour — no
    coverage guarantee (will starve low-probability cells). Kept for non-
    persistent missions."""

    def next_waypoints(
        self,
        region: SearchRegion,
        bayes_map: BayesianSearchMap,
        vehicle_pos: tuple[float, float],
        threat_weights: dict[tuple[int, int], float] | None = None,
        revisit_bound_s: float = 300.0,
        n_ahead: int = 1,
    ) -> list[Waypoint]:
        e, n = bayes_map.highest_probability_cell_centre()
        return [Waypoint(e, n, region.alt_u)]


class PersistentPatrolStrategy:
    """Default. Threat-weighted persistent coverage with a hard revisit bound.

    FORCE-VISIT (hard constraint): if any cell's time-since-observed exceeds T,
    the only allowed target is the stalest cell — probability weighting is
    suspended. This is what makes T unviolatable; probability re-growth alone
    gives only expected, not worst-case, revisit (ADR-013).

    Otherwise (nominal): go to the cell maximising threat-weight × probability.
    """

    def next_waypoints(
        self,
        region: SearchRegion,
        bayes_map: BayesianSearchMap,
        vehicle_pos: tuple[float, float],
        threat_weights: dict[tuple[int, int], float] | None = None,
        revisit_bound_s: float = 300.0,
        n_ahead: int = 1,
    ) -> list[Waypoint]:
        if bayes_map.max_cell_age_s() > revisit_bound_s:
            e, n = bayes_map.oldest_unobserved_cell_centre()  # force-visit
        else:
            e, n = bayes_map.highest_scoring_cell(threat_weights)
        return [Waypoint(e, n, region.alt_u)]


class BarrierStrategy:
    """IAMSAR barrier search — hold a line across the swim-zone mouth to intercept
    inbound targets. Stub: implement when the beach-mouth scenario is in scope."""

    def next_waypoints(
        self,
        region: SearchRegion,
        bayes_map: BayesianSearchMap,
        vehicle_pos: tuple[float, float],
        threat_weights: dict[tuple[int, int], float] | None = None,
        revisit_bound_s: float = 300.0,
        n_ahead: int = 1,
    ) -> list[Waypoint]:
        # ponytail: deferred until beach-mouth interception is a confirmed scenario.
        return []


STRATEGIES = {
    'lawnmower': LawnmowerStrategy,
    'bayesian_greedy': BayesianGreedyStrategy,
    'persistent_patrol': PersistentPatrolStrategy,
    'barrier': BarrierStrategy,
}
