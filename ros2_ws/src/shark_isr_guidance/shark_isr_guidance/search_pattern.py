"""
search_pattern.py — Waypoint/SearchRegion types and the strip boustrophedon
(lawnmower) search pattern (ADR-012/ADR-018).

Pure math, no ROS deps.  Unit-tested in test/test_search_pattern.py.

boustrophedon_strip() generates shore-parallel lanes over a SearchRegion,
spaced strip_width_m apart (= sensor footprint width at search altitude, set
by the caller). A circular search area is represented as a SearchRegion with
shore_bearing_rad=0 and length_m=width_m=2*radius — a bounding square, so its
lawnmower lanes cover the square's corners too, not just the circle; this is
deliberate (LawnmowerStrategy needs no separate circular code path) and only
affects the non-default `lawnmower` strategy, not `persistent_patrol`.
"""

import math
from typing import NamedTuple


class Waypoint(NamedTuple):
    """ENU position in metres, relative to home at arm."""
    east: float
    north: float
    up: float


class SearchRegion(NamedTuple):
    """A rectangular (strip) search area, oriented to the shoreline.

    A beachfront swim zone is a strip, not a circle: ``length`` runs ALONG the
    shore, ``width`` runs CROSS-shore (offshore). ``shore_bearing_rad`` is the
    ENU bearing of the shoreline (0 = +East, CCW positive, per REP-103). The
    local frame is x = along-shore, y = cross-shore (y increasing offshore).
    """
    centre_e: float
    centre_n: float
    length_m: float           # along-shore extent
    width_m: float            # cross-shore extent
    shore_bearing_rad: float  # ENU bearing of the shoreline [rad]
    alt_u: float              # search altitude, ENU z [m]

    def local_to_world(self, x: float, y: float) -> tuple[float, float]:
        """Map a local (along-shore x, cross-shore y) point to ENU (e, n)."""
        cb, sb = math.cos(self.shore_bearing_rad), math.sin(self.shore_bearing_rad)
        e = self.centre_e + x * cb - y * sb
        n = self.centre_n + x * sb + y * cb
        return e, n

    def world_to_local(self, e: float, n: float) -> tuple[float, float]:
        """Inverse of local_to_world: ENU (e, n) → local (x, y)."""
        cb, sb = math.cos(self.shore_bearing_rad), math.sin(self.shore_bearing_rad)
        de, dn = e - self.centre_e, n - self.centre_n
        x = de * cb + dn * sb
        y = -de * sb + dn * cb
        return x, y

    def contains(self, e: float, n: float) -> bool:
        """True if ENU (e, n) lies inside the strip."""
        x, y = self.world_to_local(e, n)
        return abs(x) <= self.length_m / 2.0 and abs(y) <= self.width_m / 2.0

    def cross_shore_offset(self, e: float, n: float) -> float:
        """Cross-shore distance from the shore edge (0 = shore edge, +offshore).

        Used for threat weighting: small offset = nearshore (swim zone) = higher
        threat. The shore edge is the near-Y boundary (y = -width/2).
        """
        _, y = self.world_to_local(e, n)
        return y + self.width_m / 2.0


def distance_to_waypoint(
    pos_e: float, pos_n: float, wp: Waypoint
) -> float:
    """Horizontal distance from (pos_e, pos_n) to waypoint [m]."""
    return math.sqrt((pos_e - wp.east) ** 2 + (pos_n - wp.north) ** 2)


def boustrophedon_strip(
    region: SearchRegion,
    strip_width_m: float,
) -> list[Waypoint]:
    """Shore-parallel boustrophedon (lawnmower) over a rectangular strip.

    Legs run ALONG the shore (long, energy-efficient — few turns), spaced
    ``strip_width_m`` apart CROSS-shore, alternating direction. Endpoints are
    generated in the strip's local frame then rotated to ENU via the shore
    bearing. This is the ADR-013 coverage floor for a beachfront swim zone, and
    the IAMSAR "creeping line" pattern.

    Args:
        region:        the strip search area (see SearchRegion).
        strip_width_m: cross-shore lane spacing (= sensor swath × (1 − overlap)) [m].

    Returns:
        Ordered ENU Waypoints (>= 2). Complete coverage of the strip
        (Choset & Pignon boustrophedon decomposition — a strip is one cell).
    """
    if region.length_m <= 0 or region.width_m <= 0:
        raise ValueError('region length_m and width_m must be positive')
    if strip_width_m <= 0:
        raise ValueError(f'strip_width_m must be positive, got {strip_width_m}')

    n_lanes = max(1, int(math.ceil(region.width_m / strip_width_m)))
    half_x = region.length_m / 2.0
    waypoints: list[Waypoint] = []

    for i in range(n_lanes):
        # Lane centre, cross-shore, distributed across the full width.
        if n_lanes == 1:
            y = 0.0
        else:
            y = -region.width_m / 2.0 + (i + 0.5) * (region.width_m / n_lanes)
        x0, x1 = (-half_x, half_x) if i % 2 == 0 else (half_x, -half_x)
        for x in (x0, x1):
            e, n = region.local_to_world(x, y)
            waypoints.append(Waypoint(e, n, region.alt_u))

    return waypoints


def check_feasibility(
    length_m: float,
    width_m: float,
    strip_width_m: float,
    cruise_speed_m_s: float,
    turn_radius_m: float,
    revisit_bound_s: float,
    endurance_s: float,
) -> tuple[bool, float, str]:
    """Can the patrol revisit every cell within the hard bound T, on this battery?

    The hard revisit bound (no cell unobserved > T) is only meaningful if a full
    coverage loop actually fits inside T *and* inside endurance. This computes a
    tight loop-period estimate and reports feasibility + the limiting reason.

        T_loop = (n_lanes·leg_len + (n_lanes−1)·turn_len) / cruise_speed

    Args:
        length_m:         along-shore strip length L [m].
        width_m:          cross-shore strip width W [m].
        strip_width_m:    lane spacing (swath) [m].
        cruise_speed_m_s: best-L/D cruise speed [m/s].
        turn_radius_m:    lane-end turn radius [m] (≈ orbit radius).
        revisit_bound_s:  hard max cell age T [s].
        endurance_s:      usable flight time on the battery [s].

    Returns:
        (feasible, t_loop_s, reason). ``feasible`` is True iff
        t_loop ≤ T and t_loop ≤ endurance. ``reason`` is '' when feasible,
        else a ranked remedy string.
    """
    if cruise_speed_m_s <= 0:
        return False, math.inf, 'cruise_speed_m_s must be > 0 (currently unset/zero)'
    if strip_width_m <= 0:
        return False, math.inf, 'strip_width_m must be > 0'

    n_lanes = max(1, int(math.ceil(width_m / strip_width_m)))
    leg_len = length_m
    turn_len = math.pi * turn_radius_m  # half-circle U-turn between lanes
    path_len = n_lanes * leg_len + (n_lanes - 1) * turn_len
    t_loop = path_len / cruise_speed_m_s

    if t_loop > revisit_bound_s:
        return (
            False, t_loop,
            f'loop {t_loop:.0f}s > revisit bound {revisit_bound_s:.0f}s — '
            'increase cruise_speed toward best-L/D, widen strip_width_m (less '
            'overlap), shrink the search width, or raise T (operator sign-off)',
        )
    if t_loop > endurance_s:
        return (
            False, t_loop,
            f'loop {t_loop:.0f}s > endurance {endurance_s:.0f}s — '
            'area too large for one charge; reduce coverage area or stage sorties',
        )
    return True, t_loop, ''
