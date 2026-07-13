"""
guidance_node.py — Outer-loop guidance: search strategy, Bayesian map, orbit-on-detect.

State machine:
  IDLE ──SetGuidanceMode(TRANSIT)──▶ TRANSIT ──arrived──▶ SEARCH
  IDLE ──SetGuidanceMode(SEARCH)───▶ SEARCH
  SEARCH ──sustained detections────▶ TRACK   (confidence gate, ADR-016 —
                                              one lucky frame never transitions)
  TRACK ──evidence decays to lost──▶ SEARCH  (gate-entered tracks only)
  TRACK ──SetGuidanceMode(SEARCH)──▶ SEARCH  (mission re-enables after timeout)
  any ──SetGuidanceMode(RETURN)────▶ RETURN
  any ──SetGuidanceMode(IDLE)──────▶ IDLE

Search strategy (ADR-012) is a config choice (`search_strategy` param):
  lawnmower          — fixed boustrophedon over the area (SITL-verified baseline)
  persistent_patrol  — DEFAULT: threat-weighted belief-driven patrol with a hard
                       revisit bound (force-visit the stalest cell past T)
  bayesian_greedy    — chase the highest-probability cell (SAR / first-find)

Publishes:
  guidance_setpoint  (GuidanceSetpoint)   — consumed by shark_isr_autopilot
  search_state       (SearchState)        — consumed by shark_isr_mission, shark_isr_telemetry

Subscribes:
  vehicle_state      (VehicleState)       — from shark_isr_autopilot
  detection          (Detection)          — from shark_isr_perception

Service server:
  set_guidance_mode  (SetGuidanceMode)    — called by shark_isr_mission
"""

import math
import time

import rclpy
from rclpy.node import Node

from geometry_msgs.msg import Point
from std_msgs.msg import Header

from shark_isr_interfaces.msg import Detection, GuidanceSetpoint, SearchState, VehicleState
from shark_isr_interfaces.srv import SetGuidanceMode

from .bayesian_map import BayesianSearchMap
from .confidence_gate import ConfidenceGate
from .search_pattern import (
    SearchRegion,
    Waypoint,
    boustrophedon,
    coverage_fraction_swept,
    distance_to_waypoint,
)
from .strategies import STRATEGIES

class GuidanceNode(Node):
    """Guidance layer: search pattern, Bayesian map, detection-triggered orbit."""

    def __init__(self) -> None:
        super().__init__('guidance_node')

        # ── Parameters ───────────────────────────────────────────────────────
        self.declare_parameter('update_hz', 5.0)
        self.declare_parameter('state_hz', 2.0)
        self.declare_parameter('strip_width_m', 60.0)
        self.declare_parameter('arrival_threshold_m', 15.0)
        self.declare_parameter('detection_confidence_threshold', 0.70)
        self.declare_parameter('orbit_radius_m', 50.0)
        self.declare_parameter('footprint_radius_m', 35.0)
        self.declare_parameter('p_detection', 0.85)
        self.declare_parameter('detection_sigma_m', 25.0)
        self.declare_parameter('return_home_alt_m', 30.0)
        # Search strategy (ADR-012)
        self.declare_parameter('search_strategy', 'persistent_patrol')
        self.declare_parameter('revisit_bound_s', 300.0)
        self.declare_parameter('regrowth_alpha', 0.001)
        # Confidence gate (ADR-016) — constants mirror site-v2/lib/guidance.ts
        self.declare_parameter('gate_tau', 0.85)
        self.declare_parameter('gate_k_sustain', 6)
        self.declare_parameter('gate_gain', 0.12)
        self.declare_parameter('gate_decay', 0.05)
        self.declare_parameter('gate_lost', 0.25)

        self._update_hz = self.get_parameter('update_hz').value
        self._strip_w = self.get_parameter('strip_width_m').value
        self._arrival_thresh = self.get_parameter('arrival_threshold_m').value
        self._det_conf_thresh = self.get_parameter('detection_confidence_threshold').value
        self._orbit_r = self.get_parameter('orbit_radius_m').value
        self._footprint_r = self.get_parameter('footprint_radius_m').value
        self._p_det = self.get_parameter('p_detection').value
        self._det_sigma = self.get_parameter('detection_sigma_m').value
        self._return_alt = self.get_parameter('return_home_alt_m').value
        self._strategy_name = self.get_parameter('search_strategy').value
        self._revisit_bound_s = self.get_parameter('revisit_bound_s').value
        self._regrowth_alpha = self.get_parameter('regrowth_alpha').value
        if self._strategy_name not in STRATEGIES:
            raise ValueError(
                f"search_strategy '{self._strategy_name}' unknown; "
                f'choose from {sorted(STRATEGIES)}')
        self._gate = ConfidenceGate(
            tau=self.get_parameter('gate_tau').value,
            k_sustain=self.get_parameter('gate_k_sustain').value,
            gain=self.get_parameter('gate_gain').value,
            decay=self.get_parameter('gate_decay').value,
            lost=self.get_parameter('gate_lost').value,
        )

        # ── State ────────────────────────────────────────────────────────────
        self._phase: int = SearchState.PHASE_IDLE
        self._vehicle: VehicleState | None = None

        # Search state
        self._search_centre: tuple[float, float, float] = (0.0, 0.0, 0.0)
        self._search_radius: float = 200.0
        self._search_alt: float = 50.0
        self._waypoints: list[Waypoint] = []
        self._wp_idx: int = 0
        self._bayes_map: BayesianSearchMap | None = None
        # Belief-driven strategy state ('lawnmower' keeps the waypoint list above)
        self._strategy = None
        self._region: SearchRegion | None = None
        self._strategy_target: Waypoint | None = None
        self._last_map_update: float = time.monotonic()

        # Transit state
        self._transit_target: tuple[float, float, float] = (0.0, 0.0, 0.0)

        # Track state
        self._orbit_centre: tuple[float, float, float] = (0.0, 0.0, 0.0)
        self._tracked_lat: float = 0.0
        self._tracked_lon: float = 0.0
        self._orbit_clockwise: bool = False
        self._track_from_detection: bool = False  # gate-entered (vs MODE_ORBIT)
        # Latest gate candidate (ENU e, n, lat, lon) — becomes the orbit centre
        # when the gate triggers
        self._candidate: tuple[float, float, float, float] | None = None

        # Timing
        self._phase_start: float = time.monotonic()
        self._time_on_station: float = 0.0

        # ── Subscribers ──────────────────────────────────────────────────────
        self.create_subscription(VehicleState, 'vehicle_state', self._cb_vehicle, 10)
        self.create_subscription(Detection, 'detection', self._cb_detection, 10)

        # ── Publishers ───────────────────────────────────────────────────────
        self._pub_setpoint = self.create_publisher(GuidanceSetpoint, 'guidance_setpoint', 10)
        self._pub_state = self.create_publisher(SearchState, 'search_state', 10)

        # ── Service ──────────────────────────────────────────────────────────
        self.create_service(SetGuidanceMode, 'set_guidance_mode', self._srv_set_mode)

        # ── Timers ───────────────────────────────────────────────────────────
        self.create_timer(1.0 / self._update_hz, self._timer_update)
        state_hz = self.get_parameter('state_hz').value
        self.create_timer(1.0 / state_hz, self._timer_publish_state)

        self.get_logger().info('guidance_node started')

    # ── Subscriber callbacks ─────────────────────────────────────────────────

    def _cb_vehicle(self, msg: VehicleState) -> None:
        self._vehicle = msg

    def _cb_detection(self, msg: Detection) -> None:
        """Feed the confidence gate (ADR-016). No single detection transitions
        the phase — the gate's sustained-crossing check in _timer_update does."""
        if msg.confidence < self._det_conf_thresh:
            return
        if self._phase not in (SearchState.PHASE_SEARCH, SearchState.PHASE_TRACK):
            return
        if self._vehicle is None:
            # No vehicle state → can't place the orbit; without this guard the
            # centre defaults to ENU origin (0,0) and the aircraft flies home.
            self.get_logger().warn('Detection ignored: no vehicle state yet')
            return

        if msg.geo_valid:
            # Flat-earth offset from the vehicle, added to the vehicle's absolute
            # ENU position — the offset alone is NOT an ENU coordinate.
            off_e, off_n = self._latlondelta_to_enu(
                msg.latitude_deg, msg.longitude_deg)
            det_e = self._vehicle.position_enu_m.x + off_e
            det_n = self._vehicle.position_enu_m.y + off_n
            lat, lon = msg.latitude_deg, msg.longitude_deg
        else:
            # Fall back: place detection at current vehicle position
            det_e = self._vehicle.position_enu_m.x
            det_n = self._vehicle.position_enu_m.y
            lat, lon = self._vehicle.latitude_deg, self._vehicle.longitude_deg

        if self._bayes_map is not None:
            self._bayes_map.positive_detection(det_e, det_n, self._det_sigma)

        self._gate.on_detection(msg.confidence)
        self._candidate = (det_e, det_n, lat, lon)

        # In TRACK, follow the target: keep the orbit centred on fresh evidence.
        if self._phase == SearchState.PHASE_TRACK and self._track_from_detection:
            self._orbit_centre = (det_e, det_n, self._orbit_centre[2])
            self._tracked_lat, self._tracked_lon = lat, lon

    # ── Guidance update timer (5 Hz) ─────────────────────────────────────────

    def _timer_update(self) -> None:
        if self._vehicle is None:
            return

        pos_e = self._vehicle.position_enu_m.x
        pos_n = self._vehicle.position_enu_m.y

        if self._phase == SearchState.PHASE_IDLE:
            return  # bridge stale-timeout handles hold; don't compete with other setpoint publishers

        elif self._phase == SearchState.PHASE_TRANSIT:
            self._update_transit(pos_e, pos_n)

        elif self._phase == SearchState.PHASE_SEARCH:
            self._gate.on_tick()
            if self._gate.triggered and self._candidate is not None:
                self._enter_track(*self._candidate)
                return
            self._update_search(pos_e, pos_n)

        elif self._phase == SearchState.PHASE_TRACK:
            self._gate.on_tick()
            if self._track_from_detection and self._gate.lost:
                # Evidence gone — resume the search instead of orbiting water.
                self.get_logger().info(
                    f'Track lost (score={self._gate.score:.2f}) → resuming SEARCH')
                self._gate.reset()
                self._candidate = None
                self._track_from_detection = False
                self._set_phase(SearchState.PHASE_SEARCH)
                return
            self._update_track()

        elif self._phase == SearchState.PHASE_RETURN:
            self._update_return(pos_e, pos_n)

    def _enter_track(self, det_e: float, det_n: float,
                     lat: float, lon: float) -> None:
        """Sustained τ crossing confirmed (ADR-016) — commit to the orbit."""
        self._orbit_centre = (det_e, det_n, self._search_alt)
        self._tracked_lat = lat
        self._tracked_lon = lon
        self._track_from_detection = True
        self._set_phase(SearchState.PHASE_TRACK)
        self.get_logger().info(
            f'Confidence gate triggered (score={self._gate.score:.2f}, '
            f'{self._gate.k_sustain} ticks ≥ τ={self._gate.tau}) → TRACK orbit '
            f'at ({det_e:.1f}, {det_n:.1f}) m ENU')

    def _update_transit(self, pos_e: float, pos_n: float) -> None:
        te, tn, tu = self._transit_target
        sp = GuidanceSetpoint()
        sp.header = self._header()
        sp.setpoint_type = GuidanceSetpoint.TYPE_POSITION
        sp.position_enu_m = Point(x=te, y=tn, z=tu)
        sp.yaw_rad = math.atan2(tn - pos_n, te - pos_e)  # face target (ENU: 0=East, CCW+)
        sp.cruise_speed_m_s = 0.0
        self._pub_setpoint.publish(sp)

        dist = math.sqrt((te - pos_e) ** 2 + (tn - pos_n) ** 2)
        if dist < self._arrival_thresh:
            self.get_logger().info('Transit complete → SEARCH')
            self._start_search(
                self._search_centre[0], self._search_centre[1],
                self._search_radius, self._search_alt,
            )

    def _update_search(self, pos_e: float, pos_n: float) -> None:
        # Belief update: sweep + probability re-growth (targets move, cleared
        # water doesn't stay cleared — ADR-012).
        now = time.monotonic()
        if self._bayes_map is not None:
            self._bayes_map.decay_observation(
                now - self._last_map_update, self._regrowth_alpha)
            self._bayes_map.null_observation(pos_e, pos_n, self._footprint_r, self._p_det)
        self._last_map_update = now

        if self._strategy is not None:
            self._update_search_strategy(pos_e, pos_n)
            return

        # Legacy lawnmower path: fixed boustrophedon waypoint list.
        if not self._waypoints:
            return

        # Advance waypoint if close enough.
        while self._wp_idx < len(self._waypoints):
            wp = self._waypoints[self._wp_idx]
            if distance_to_waypoint(pos_e, pos_n, wp) < self._arrival_thresh:
                self._wp_idx += 1
                self.get_logger().debug(f'Waypoint {self._wp_idx}/{len(self._waypoints)}')
            else:
                break

        if self._wp_idx >= len(self._waypoints):
            self.get_logger().info('Search pattern complete — restarting')
            self._wp_idx = 0

        wp = self._waypoints[self._wp_idx]
        sp = GuidanceSetpoint()
        sp.header = self._header()
        sp.setpoint_type = GuidanceSetpoint.TYPE_POSITION
        sp.position_enu_m = Point(x=wp.east, y=wp.north, z=wp.up)
        sp.yaw_rad = math.atan2(wp.north - pos_n, wp.east - pos_e)  # ENU: 0=East, CCW+
        sp.cruise_speed_m_s = 0.0
        self._pub_setpoint.publish(sp)

    def _update_search_strategy(self, pos_e: float, pos_n: float) -> None:
        """Belief-driven search (ADR-012): ask the strategy for the next target
        whenever there is none or the current one is reached."""
        target = self._strategy_target
        if target is None or distance_to_waypoint(pos_e, pos_n, target) < self._arrival_thresh:
            target = self._strategy.next_waypoints(
                self._region, self._bayes_map, (pos_e, pos_n),
                revisit_bound_s=self._revisit_bound_s,
            )[0]
            self._strategy_target = target
            self.get_logger().debug(
                f'{self._strategy_name} target → ({target.east:.0f}, {target.north:.0f})')

        sp = GuidanceSetpoint()
        sp.header = self._header()
        sp.setpoint_type = GuidanceSetpoint.TYPE_POSITION
        sp.position_enu_m = Point(x=target.east, y=target.north, z=target.up)
        sp.yaw_rad = math.atan2(target.north - pos_n, target.east - pos_e)
        sp.cruise_speed_m_s = 0.0
        self._pub_setpoint.publish(sp)

    def _update_track(self) -> None:
        oe, on_, ou = self._orbit_centre
        sp = GuidanceSetpoint()
        sp.header = self._header()
        sp.setpoint_type = GuidanceSetpoint.TYPE_ORBIT
        sp.position_enu_m = Point(x=oe, y=on_, z=ou)
        sp.orbit_radius_m = self._orbit_r
        sp.orbit_clockwise = self._orbit_clockwise
        sp.yaw_rad = float('nan')
        sp.yaw_rate_rad_s = float('nan')
        sp.cruise_speed_m_s = 0.0
        self._pub_setpoint.publish(sp)

    def _update_return(self, pos_e: float, pos_n: float) -> None:
        sp = GuidanceSetpoint()
        sp.header = self._header()
        sp.setpoint_type = GuidanceSetpoint.TYPE_POSITION
        sp.position_enu_m = Point(x=0.0, y=0.0, z=self._return_alt)
        sp.yaw_rad = float('nan')
        sp.cruise_speed_m_s = 0.0
        self._pub_setpoint.publish(sp)

    # ── SearchState publisher (2 Hz) ─────────────────────────────────────────

    def _timer_publish_state(self) -> None:
        ss = SearchState()
        ss.header = self._header()
        ss.phase = self._phase

        if self._bayes_map is not None:
            ss.coverage_fraction = self._bayes_map.coverage_fraction()
            ss.map_max_probability = self._bayes_map.max_probability()
            ss.map_mean_probability = self._bayes_map.mean_probability()
        else:
            ss.coverage_fraction = coverage_fraction_swept(
                self._waypoints, self._wp_idx,
                self._search_radius, self._strip_w,
            ) if self._waypoints else 0.0

        ss.time_on_station_s = float(self._time_on_station_elapsed())

        if self._vehicle is not None:
            ss.current_target_enu_m = self._current_target_point()

        ss.target_locked = (self._phase == SearchState.PHASE_TRACK)
        if ss.target_locked:
            ss.tracked_lat_deg = self._tracked_lat
            ss.tracked_lon_deg = self._tracked_lon
            oe, on_, ou = self._orbit_centre
            ss.orbit_centre_enu_m = Point(x=oe, y=on_, z=ou)
            ss.orbit_radius_m = self._orbit_r

        self._pub_state.publish(ss)

    def _current_target_point(self) -> Point:
        if self._phase == SearchState.PHASE_TRANSIT:
            te, tn, tu = self._transit_target
            return Point(x=te, y=tn, z=tu)
        if self._phase == SearchState.PHASE_SEARCH:
            if self._strategy is not None and self._strategy_target is not None:
                t = self._strategy_target
                return Point(x=t.east, y=t.north, z=t.up)
            if self._waypoints:
                wp = self._waypoints[min(self._wp_idx, len(self._waypoints) - 1)]
                return Point(x=wp.east, y=wp.north, z=wp.up)
        if self._phase == SearchState.PHASE_TRACK:
            oe, on_, ou = self._orbit_centre
            return Point(x=oe, y=on_, z=ou)
        if self._vehicle:
            p = self._vehicle.position_enu_m
            return Point(x=p.x, y=p.y, z=p.z)
        return Point()

    # ── SetGuidanceMode service ───────────────────────────────────────────────

    def _srv_set_mode(
        self,
        request: SetGuidanceMode.Request,
        response: SetGuidanceMode.Response,
    ) -> SetGuidanceMode.Response:
        mode = request.mode

        if mode == SetGuidanceMode.Request.MODE_IDLE:
            self._set_phase(SearchState.PHASE_IDLE)
            response.accepted = True

        elif mode == SetGuidanceMode.Request.MODE_TRANSIT:
            t = request.transit_target_enu_m
            self._transit_target = (t.x, t.y, t.z)
            self._set_phase(SearchState.PHASE_TRANSIT)
            response.accepted = True

        elif mode == SetGuidanceMode.Request.MODE_SEARCH:
            sc = request.search_centre_enu_m
            self._start_search(
                sc.x, sc.y,
                request.search_radius_m,
                request.search_alt_enu_z_m,
            )
            response.accepted = True

        elif mode == SetGuidanceMode.Request.MODE_ORBIT:
            oc = request.orbit_centre_enu_m
            self._orbit_centre = (oc.x, oc.y, oc.z)
            self._orbit_r = request.orbit_radius_m
            self._orbit_clockwise = request.orbit_clockwise
            # Commanded orbit, not gate-entered — the lost check must not
            # kick a MODE_ORBIT hold back to SEARCH.
            self._track_from_detection = False
            self._set_phase(SearchState.PHASE_TRACK)
            response.accepted = True

        elif mode == SetGuidanceMode.Request.MODE_RETURN:
            self._set_phase(SearchState.PHASE_RETURN)
            response.accepted = True

        else:
            response.accepted = False
            response.reason = f'Unknown mode: {mode}'

        self.get_logger().info(f'SetGuidanceMode {mode} → phase {self._phase}')
        return response

    # ── Internal helpers ─────────────────────────────────────────────────────

    def _start_search(
        self, centre_e: float, centre_n: float, radius: float, alt: float
    ) -> None:
        self._search_centre = (centre_e, centre_n, alt)
        self._search_radius = radius
        self._search_alt = alt
        self._waypoints = boustrophedon(centre_e, centre_n, alt, radius, self._strip_w)
        self._wp_idx = 0
        self._bayes_map = BayesianSearchMap(
            centre_e, centre_n, radius,
            cell_size_m=max(5.0, self._strip_w / 6.0),
        )
        self._last_map_update = time.monotonic()
        # Belief-driven strategies replace the fixed waypoint list (ADR-012).
        # The region carries the search altitude; cell membership stays the
        # circle the Bayesian map was built with.
        if self._strategy_name == 'lawnmower':
            self._strategy = None
        else:
            self._strategy = STRATEGIES[self._strategy_name]()
            self._region = SearchRegion(
                centre_e, centre_n, 2.0 * radius, 2.0 * radius, 0.0, alt)
        self._strategy_target = None
        self._gate.reset()
        self._candidate = None
        self._set_phase(SearchState.PHASE_SEARCH)
        self.get_logger().info(
            f'Search started ({self._strategy_name}): '
            f'centre=({centre_e:.1f}, {centre_n:.1f}) m ENU, r={radius:.0f} m')

    def _set_phase(self, phase: int) -> None:
        if self._phase in (SearchState.PHASE_SEARCH, SearchState.PHASE_TRACK):
            self._time_on_station += time.monotonic() - self._phase_start
        self._phase = phase
        self._phase_start = time.monotonic()

    def _time_on_station_elapsed(self) -> float:
        extra = 0.0
        if self._phase in (SearchState.PHASE_SEARCH, SearchState.PHASE_TRACK):
            extra = time.monotonic() - self._phase_start
        return self._time_on_station + extra

    def _latlondelta_to_enu(
        self, lat_deg: float, lon_deg: float
    ) -> tuple[float, float]:
        """Flat-earth (east, north) offset of lat/lon from the vehicle's CURRENT
        position.  NOT an absolute ENU coordinate — callers must add the
        vehicle's position_enu_m to get one."""
        if self._vehicle is None or not self._vehicle.position_valid:
            return 0.0, 0.0
        lat0 = self._vehicle.latitude_deg
        lon0 = self._vehicle.longitude_deg
        dlat = math.radians(lat_deg - lat0)
        dlon = math.radians(lon_deg - lon0)
        R = 6_371_000.0
        north = dlat * R
        east = dlon * R * math.cos(math.radians(lat0))
        return east, north

    def _header(self) -> Header:
        h = Header()
        h.stamp = self.get_clock().now().to_msg()
        h.frame_id = 'odom'
        return h


def main(args=None) -> None:
    rclpy.init(args=args)
    node = GuidanceNode()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()
