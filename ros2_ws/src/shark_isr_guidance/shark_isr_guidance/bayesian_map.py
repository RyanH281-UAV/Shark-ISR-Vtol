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


class BayesianSearchMap:
    """Discrete Bayesian probability map over a circular search area."""

    def __init__(
        self,
        centre_e: float,
        centre_n: float,
        radius_m: float,
        cell_size_m: float = 10.0,
    ) -> None:
        self.centre_e = centre_e
        self.centre_n = centre_n
        self.radius_m = radius_m
        self.cell_size = cell_size_m

        # Grid spans [-radius, +radius] in both axes; origin = centre.
        half_cells = int(math.ceil(radius_m / cell_size_m))
        self.n = 2 * half_cells + 1
        self.origin_e = centre_e - half_cells * cell_size_m
        self.origin_n = centre_n - half_cells * cell_size_m

        # Build flat list of (row, col) cells inside the circle.
        self._cells: list[tuple[int, int]] = []
        for r in range(self.n):
            for c in range(self.n):
                ce, cn = self._cell_centre(r, c)
                d = math.sqrt((ce - centre_e) ** 2 + (cn - centre_n) ** 2)
                if d <= radius_m:
                    self._cells.append((r, c))

        n_cells = len(self._cells)
        if n_cells == 0:
            raise ValueError('Search area too small for cell_size_m')

        # Grid of log-probabilities (log P) for numerical stability.
        # Initialise to uniform: log(1/n_cells) for cells in circle, -inf outside.
        log_uniform = -math.log(n_cells)
        self._log_p: list[list[float]] = [
            [-math.inf] * self.n for _ in range(self.n)
        ]
        for r, c in self._cells:
            self._log_p[r][c] = log_uniform

        # Track how many cells have been swept (for coverage metric).
        self._swept: list[list[bool]] = [
            [False] * self.n for _ in range(self.n)
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
                updated = True
        if updated:
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
