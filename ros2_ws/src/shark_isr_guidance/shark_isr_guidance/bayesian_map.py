"""
bayesian_map.py — Bayesian probability grid over a circular search area.

Pure math, no ROS deps.  Unit-tested in test/test_bayesian_map.py.

Each cell holds P(shark in cell).  The grid is normalised so that
  sum(P(cell) for cell in search_area) = 1.0

Updates:
  null_observation(pos, footprint_r):
      Aircraft swept footprint_r metres radius with no detection.
      Multiply in-footprint cells by (1 - p_detection) and renormalise.

  positive_detection(det_pos, sigma):
      Detection at det_pos.  Multiply all cells by a Gaussian likelihood
      centred on det_pos and renormalise.

Coverage metric:
  coverage_fraction = fraction of cells in the search area whose probability
  has been reduced to ≤ p_detection × prior.  Equivalent to: cells the sensor
  has been 'responsible for' given the detection probability.
"""

import math

from .search_pattern import SearchRegion


class BayesianSearchMap:
    """Discrete Bayesian probability map over a circular OR strip search area."""

    def __init__(
        self,
        centre_e: float,
        centre_n: float,
        radius_m: float,
        cell_size_m: float = 10.0,
        region: SearchRegion | None = None,
    ) -> None:
        """Build the grid. If ``region`` (a strip) is given it defines the search
        area; otherwise the legacy circle (centre + radius_m) is used."""
        self.region = region
        self.cell_size = cell_size_m

        if region is not None:
            self.centre_e = region.centre_e
            self.centre_n = region.centre_n
            # bounding box must hold the rotated strip → half-diagonal extent
            extent = 0.5 * math.hypot(region.length_m, region.width_m)
            self.radius_m = extent

            def member(ce: float, cn: float) -> bool:
                return region.contains(ce, cn)
        else:
            self.centre_e = centre_e
            self.centre_n = centre_n
            self.radius_m = radius_m
            extent = radius_m

            def member(ce: float, cn: float) -> bool:
                return math.sqrt((ce - centre_e) ** 2 + (cn - centre_n) ** 2) <= radius_m

        # Grid spans [-extent, +extent] in both axes; origin = min corner.
        half_cells = int(math.ceil(extent / cell_size_m))
        self.n = 2 * half_cells + 1
        self.origin_e = self.centre_e - half_cells * cell_size_m
        self.origin_n = self.centre_n - half_cells * cell_size_m

        # Build flat list of (row, col) cells inside the search area.
        self._cells: list[tuple[int, int]] = []
        for r in range(self.n):
            for c in range(self.n):
                ce, cn = self._cell_centre(r, c)
                if member(ce, cn):
                    self._cells.append((r, c))

        n_cells = len(self._cells)
        if n_cells == 0:
            raise ValueError('Search area too small for cell_size_m')

        # Grid of log-probabilities (log P) for numerical stability.
        # Initialise to uniform: log(1/n_cells) inside area, -inf outside.
        self._log_uniform = -math.log(n_cells)
        self._log_p: list[list[float]] = [
            [-math.inf] * self.n for _ in range(self.n)
        ]
        for r, c in self._cells:
            self._log_p[r][c] = self._log_uniform

        # Coverage tracker (ever swept) + per-cell staleness clock [s since
        # last observed]. Age drives the hard revisit bound (see decay_observation
        # / oldest_unobserved_cell_centre). Starts at 0 — nothing seen yet, and
        # age only accrues once time advances via decay_observation().
        self._swept: list[list[bool]] = [
            [False] * self.n for _ in range(self.n)
        ]
        self._age: list[list[float]] = [
            [0.0] * self.n for _ in range(self.n)
        ]

    # ── Coordinate helpers ────────────────────────────────────────────────────

    def _cell_centre(self, row: int, col: int) -> tuple[float, float]:
        e = self.origin_e + (col + 0.5) * self.cell_size
        n = self.origin_n + (row + 0.5) * self.cell_size
        return e, n

    def _world_to_cell(self, e: float, n: float) -> tuple[int, int]:
        col = int((e - self.origin_e) / self.cell_size)
        row = int((n - self.origin_n) / self.cell_size)
        return row, col

    def _in_bounds(self, row: int, col: int) -> bool:
        return 0 <= row < self.n and 0 <= col < self.n

    # ── Update operations ─────────────────────────────────────────────────────

    def null_observation(
        self,
        pos_e: float,
        pos_n: float,
        footprint_radius_m: float,
        p_detection: float = 0.85,
    ) -> None:
        """Aircraft swept footprint_radius_m around pos with no detection.

        Multiplies in-footprint cell probabilities by (1 - p_detection)
        and renormalises.  Marks swept cells in the coverage tracker.

        Args:
            pos_e, pos_n:      vehicle position in ENU [m]
            footprint_radius_m: half-width of sensor swath [m]
            p_detection:        probability of detecting a shark if present in cell
        """
        log_scale = math.log(max(1e-12, 1.0 - p_detection))
        updated = False
        for r, c in self._cells:
            ce, cn = self._cell_centre(r, c)
            dist = math.sqrt((ce - pos_e) ** 2 + (cn - pos_n) ** 2)
            if dist <= footprint_radius_m:
                self._log_p[r][c] += log_scale
                self._swept[r][c] = True
                self._age[r][c] = 0.0  # observed now → staleness reset
                updated = True
        if updated:
            self._normalise()

    def decay_observation(self, dt_s: float, alpha: float = 0.001) -> None:
        """Advance time by dt_s: age every cell, and re-grow probability.

        Target motion means a 'cleared' cell can hold a shark again later, so
        probability must diffuse back toward the prior over time — otherwise the
        map is greedy one-shot clearing and the search starves swept cells. Each
        cell's log-prob is nudged toward uniform at rate ``alpha`` per second;
        cleared (below-uniform) cells rise, stale detection peaks decay.

        This provides the *expected* revisit pressure. The *hard* revisit bound
        is enforced separately via the age clock (see oldest_unobserved_cell_centre);
        re-growth alone does not guarantee a worst-case bound.

        Args:
            dt_s:  elapsed time since the last call [s].
            alpha: re-growth rate toward the prior [1/s].
        """
        if dt_s <= 0:
            return
        for r, c in self._cells:
            self._age[r][c] += dt_s
            lp = self._log_p[r][c]
            if math.isfinite(lp):
                # Exact solution of d(log_p)/dt = alpha*(log_uniform - log_p),
                # not the Euler step lp + alpha*dt*(uniform-lp): Euler inverts the
                # map when alpha*dt > 1 (coefficient on lp goes negative). This
                # form is monotone toward uniform for any alpha>0, dt>0.
                self._log_p[r][c] = self._log_uniform + (lp - self._log_uniform) * math.exp(-alpha * dt_s)
        self._normalise()

    def positive_detection(
        self,
        det_e: float,
        det_n: float,
        sigma_m: float = 25.0,
    ) -> None:
        """A shark was detected at (det_e, det_n).

        Applies a Gaussian likelihood update and renormalises.

        Args:
            det_e, det_n: detection ENU position [m]
            sigma_m:      position uncertainty standard deviation [m]
        """
        two_sigma_sq = 2.0 * sigma_m ** 2
        for r, c in self._cells:
            ce, cn = self._cell_centre(r, c)
            d_sq = (ce - det_e) ** 2 + (cn - det_n) ** 2
            self._log_p[r][c] += -d_sq / two_sigma_sq  # log of Gaussian kernel
        self._normalise()

    def _normalise(self) -> None:
        """Renormalise log-probabilities to keep numerical stability."""
        # log-sum-exp trick
        valid = [self._log_p[r][c] for r, c in self._cells if math.isfinite(self._log_p[r][c])]
        if not valid:
            return
        log_max = max(valid)
        log_sum = log_max + math.log(sum(math.exp(v - log_max) for v in valid))
        for r, c in self._cells:
            if math.isfinite(self._log_p[r][c]):
                self._log_p[r][c] -= log_sum

    # ── Query ─────────────────────────────────────────────────────────────────

    def probability(self, row: int, col: int) -> float:
        """Return P(shark in cell[row, col])."""
        if not self._in_bounds(row, col):
            return 0.0
        lp = self._log_p[row][col]
        return math.exp(lp) if math.isfinite(lp) else 0.0

    def max_probability(self) -> float:
        """Peak cell probability."""
        return max(self.probability(r, c) for r, c in self._cells)

    def mean_probability(self) -> float:
        """Mean cell probability (= 1 / n_cells for a uniform map)."""
        n = len(self._cells)
        return sum(self.probability(r, c) for r, c in self._cells) / max(1, n)

    def coverage_fraction(self) -> float:
        """Fraction of cells in the search area that have been swept."""
        if not self._cells:
            return 0.0
        swept = sum(1 for r, c in self._cells if self._swept[r][c])
        return swept / len(self._cells)

    def highest_probability_cell_centre(self) -> tuple[float, float]:
        """ENU (e, n) of the cell with the highest probability."""
        best_r, best_c = max(self._cells, key=lambda rc: self._log_p[rc[0]][rc[1]])
        return self._cell_centre(best_r, best_c)

    # ── Staleness (hard revisit bound) ─────────────────────────────────────────

    def cell_age_s(self, row: int, col: int) -> float:
        """Seconds since cell[row, col] was last observed (0 if just swept)."""
        if not self._in_bounds(row, col):
            return 0.0
        return self._age[row][col]

    def max_cell_age_s(self) -> float:
        """Largest time-since-observed over all cells [s]. Compare against T."""
        return max(self._age[r][c] for r, c in self._cells)

    def oldest_unobserved_cell_centre(self) -> tuple[float, float]:
        """ENU (e, n) of the stalest cell — the FORCE-VISIT target for the
        hard revisit bound."""
        best_r, best_c = max(self._cells, key=lambda rc: self._age[rc[0]][rc[1]])
        return self._cell_centre(best_r, best_c)

    def highest_scoring_cell(
        self,
        weights: dict[tuple[int, int], float] | None = None,
    ) -> tuple[float, float]:
        """ENU (e, n) of the cell maximising threat-weighted probability
        w(c)·P(c). This is the *nominal* routing target; staleness is carried by
        the probability re-growth and enforced separately by the force-visit
        clock, so age does not appear here.

        Args:
            weights: optional {(row, col): threat_weight}. Missing cells → 1.0.
        """
        w = weights or {}

        def score(rc: tuple[int, int]) -> float:
            return w.get(rc, 1.0) * self.probability(rc[0], rc[1])

        best_r, best_c = max(self._cells, key=score)
        return self._cell_centre(best_r, best_c)
