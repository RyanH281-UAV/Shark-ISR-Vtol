"""
strategies.py — pluggable search strategies (ADR-012).

Pure math, no ROS deps. Unit-tested in test/test_strategies.py.

One interface, several behaviours, so the shark mission can ship persistent
patrol while keeping lawnmower / Bayesian-greedy available for other domains
(the strategy is a config choice, not a rewrite):

    LawnmowerStrategy       — complete coverage, ignores probability (the floor).
    BayesianGreedyStrategy  — chase the highest-probability cell (SAR / first-find).
    PersistentPatrolStrategy — DEFAULT. Threat-weighted nominal routing with a
                               HARD revisit bound: if any cell's age exceeds T,
                               force-visit the stalest cell; else go to the
                               highest threat-weighted-probability cell.

BarrierStrategy (IAMSAR barrier line intercept) was removed 2026-09-03 — it was
a NotImplementedError reachable from config (search_strategy: barrier passed
startup validation and only crashed once the 5 Hz timer called it). Re-add when
the beach-mouth interception scenario is real; see ADR-012.
"""

import math

from .bayesian_map import BayesianSearchMap
from .search_pattern import SearchRegion, Waypoint, boustrophedon_strip


class LawnmowerStrategy:
    """Complete-coverage boustrophedon over the strip. Ignores the belief map.

    The coverage floor. Caches the path per region and cycles through it in order,
    resuming from where it left off. ``vehicle_pos`` is ignored — after a mission
    diversion it resumes at the next path index, not the nearest lane.
    # TODO: nearest-lane resume when divert-then-resume coverage gaps bite.
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
    ) -> list[Waypoint]:
        self._ensure_path(region)
        wp = self._path[self._idx % len(self._path)]
        self._idx += 1
        return [wp]


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
    ) -> list[Waypoint]:
        e, n = bayes_map.highest_probability_cell_centre()
        return [Waypoint(e, n, region.alt_u)]


class PersistentPatrolStrategy:
    """Default. Threat-weighted persistent coverage with a hard revisit bound.

    FORCE-VISIT (hard constraint): if any cell's time-since-observed exceeds T,
    the only allowed target is the stalest cell — probability weighting is
    suspended. This is what makes T unviolatable; probability re-growth alone
    gives only expected, not worst-case, revisit (ADR-012).

    Otherwise (nominal): go to the cell maximising threat-weight × probability.
    """

    def next_waypoints(
        self,
        region: SearchRegion,
        bayes_map: BayesianSearchMap,
        vehicle_pos: tuple[float, float],
        threat_weights: dict[tuple[int, int], float] | None = None,
        revisit_bound_s: float = 300.0,
    ) -> list[Waypoint]:
        if bayes_map.max_cell_age_s() > revisit_bound_s:
            e, n = bayes_map.oldest_unobserved_cell_centre()  # force-visit
        else:
            e, n = bayes_map.highest_scoring_cell(threat_weights)
        return [Waypoint(e, n, region.alt_u)]


STRATEGIES = {
    'lawnmower': LawnmowerStrategy,
    'bayesian_greedy': BayesianGreedyStrategy,
    'persistent_patrol': PersistentPatrolStrategy,
}


def threat_weights_from_shore(
    region: SearchRegion,
    bayes_map: BayesianSearchMap,
    scale_m: float,
) -> dict[tuple[int, int], float]:
    """Per-cell threat weight for PersistentPatrolStrategy: exponential
    falloff offshore from the shore edge (``region.cross_shore_offset`` is 0
    at the shore edge, increasing offshore), so nearshore cells — the swim
    zone — score highest, matching ADR-012's "small offset = higher threat".

    Only meaningful for a real (bearing-aligned) strip region — the legacy
    circular search area has no shoreline to weight against.

    # ponytail: exponential falloff from the shore edge is a naive threat
    # prior — replace with a fitted/sightings-driven weight when real data
    # (e.g. historical sighting density) exists.
    """
    return {
        rc: math.exp(-max(0.0, region.cross_shore_offset(*bayes_map.cell_centre(*rc))) / scale_m)
        for rc in bayes_map.cells()
    }
