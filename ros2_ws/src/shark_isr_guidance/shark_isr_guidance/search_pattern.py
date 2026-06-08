"""
search_pattern.py — Boustrophedon (lawnmower) search pattern over a circular area.

Pure math, no ROS deps.  Unit-tested in test/test_search_pattern.py.

The pattern generates east-west rows across the full circle diameter, connected
as a boustrophedon (alternating row directions) to minimise turn distance.
Strip width = sensor footprint width at search altitude, set by the caller via
parameters (default 60 m — conservative for Camera Module 3 at 50 m AGL with
~70° HFOV).
"""

import math
from typing import NamedTuple


class Waypoint(NamedTuple):
    """ENU position in metres, relative to home at arm."""
    east: float
    north: float
    up: float


def boustrophedon(
    centre_e: float,
    centre_n: float,
    alt_u: float,
    radius_m: float,
    strip_width_m: float,
) -> list[Waypoint]:
    """Generate boustrophedon waypoints for a circular search area.

    Rows run east-west (constant north), spaced strip_width_m apart,
    from south to north.  Odd rows run west-to-east, even rows east-to-west
    (classic lawnmower, minimises turns).

    Entry is at the south-west of the first row; exit is at the far end of
    the final row.

    Args:
        centre_e, centre_n: ENU centre of search circle [m]
        alt_u:              search altitude in ENU z [m]
        radius_m:           search circle radius [m]
        strip_width_m:      row spacing (= sensor swath width * (1 - overlap)) [m]

    Returns:
        Ordered list of Waypoints (at least 2 entries, even for a tiny circle).
    """
    if radius_m <= 0:
        raise ValueError(f'radius_m must be positive, got {radius_m}')
    if strip_width_m <= 0:
        raise ValueError(f'strip_width_m must be positive, got {strip_width_m}')

    waypoints: list[Waypoint] = []

    # Start at the southernmost row centre and work north.
    n_rows = max(1, int(math.ceil(2 * radius_m / strip_width_m)))
    # Distribute rows symmetrically around the centre.
    north_start = centre_n - (n_rows // 2) * strip_width_m
    if n_rows % 2 == 0:
        north_start += strip_width_m / 2.0

    for row in range(n_rows):
        n_coord = north_start + row * strip_width_m
        dy = n_coord - centre_n
        if abs(dy) > radius_m + 1e-6:
            continue

        half_chord = math.sqrt(max(0.0, radius_m ** 2 - dy ** 2))
        e_west = centre_e - half_chord
        e_east = centre_e + half_chord

        if row % 2 == 0:
            waypoints.append(Waypoint(e_west, n_coord, alt_u))
            waypoints.append(Waypoint(e_east, n_coord, alt_u))
        else:
            waypoints.append(Waypoint(e_east, n_coord, alt_u))
            waypoints.append(Waypoint(e_west, n_coord, alt_u))

    if not waypoints:
        waypoints.append(Waypoint(centre_e, centre_n, alt_u))

    return waypoints


def coverage_fraction_swept(
    waypoints: list[Waypoint],
    next_wp_idx: int,
    radius_m: float,
    strip_width_m: float,
) -> float:
    """Estimate coverage fraction from how many row legs have been completed.

    Simple geometric estimate: each completed leg sweeps strip_width_m × chord_length
    over the total circle area.

    Args:
        waypoints:    full waypoint list from boustrophedon()
        next_wp_idx:  index of the next waypoint yet to be reached
        radius_m:     search area radius [m]
        strip_width_m: row spacing [m]

    Returns:
        Fraction of circle area swept, in [0.0, 1.0].
    """
    circle_area = math.pi * radius_m ** 2
    if circle_area <= 0 or next_wp_idx <= 1:
        return 0.0

    swept = 0.0
    # Each pair of adjacent waypoints (start, end of a row leg) swept strip_width_m × leg_len.
    # We count pairs that have been completed (both indices < next_wp_idx).
    for i in range(0, min(next_wp_idx - 1, len(waypoints) - 1)):
        a, b = waypoints[i], waypoints[i + 1]
        leg_len = math.sqrt((b.east - a.east) ** 2 + (b.north - a.north) ** 2)
        swept += strip_width_m * leg_len

    return min(1.0, swept / circle_area)


def distance_to_waypoint(
    pos_e: float, pos_n: float, wp: Waypoint
) -> float:
    """Horizontal distance from (pos_e, pos_n) to waypoint [m]."""
    return math.sqrt((pos_e - wp.east) ** 2 + (pos_n - wp.north) ** 2)
