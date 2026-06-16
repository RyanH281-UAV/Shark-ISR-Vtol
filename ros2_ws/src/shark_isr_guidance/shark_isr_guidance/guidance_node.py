"""
guidance_node.py — Outer-loop guidance: search pattern, Bayesian map, orbit-on-detect.

State machine:
  IDLE ──SetGuidanceMode(TRANSIT)──▶ TRANSIT ──arrived──▶ SEARCH
  IDLE ──SetGuidanceMode(SEARCH)───▶ SEARCH
  SEARCH ──Detection(high conf)────▶ TRACK
  TRACK ──SetGuidanceMode(SEARCH)──▶ SEARCH  (mission re-enables after timeout)
  any ──SetGuidanceMode(RETURN)────▶ RETURN
  any ──SetGuidanceMode(IDLE)──────▶ IDLE

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

from geometry_msgs.msg import Point, Vector3
from std_msgs.msg import Header

from shark_isr_interfaces.msg import Detection, GuidanceSetpoint, SearchState, VehicleState
from shark_isr_interfaces.srv import SetGuidanceMode

from .bayesian_map import BayesianSearchMap
from .search_pattern import (
    Waypoint,
    boustrophedon,
    coverage_fraction_swept,
    distance_to_waypoint,
)

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

        self._update_hz = self.get_parameter('update_hz').value
        self._strip_w = self.get_parameter('strip_width_m').value
        self._arrival_thresh = self.get_parameter('arrival_threshold_m').value
        self._det_conf_thresh = self.get_parameter('detection_confidence_threshold').value
        self._orbit_r = self.get_parameter('orbit_radius_m').value
        self._footprint_r = self.get_parameter('footprint_radius_m').value
        self._p_det = self.get_parameter('p_detection').value
        self._det_sigma = self.get_parameter('detection_sigma_m').value
        self._return_alt = self.get_parameter('return_home_alt_m').value

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

        # Transit state
        self._transit_target: tuple[float, float, float] = (0.0, 0.0, 0.0)

        # Hold position latched on entering IDLE (prevents setpoint drift).
        self._hold_target: tuple[float, float, float] | None = None

        # Track state
        self._orbit_centre: tuple[float, float, float] = (0.0, 0.0, 0.0)
        self._tracked_lat: float = 0.0
        self._tracked_lon: float = 0.0
        self._orbit_clockwise: bool = False

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
        if msg.confidence < self._det_conf_thresh:
            return
        if self._phase not in (SearchState.PHASE_SEARCH, SearchState.PHASE_TRACK):
            return

        det_e, det_n = 0.0, 0.0
        if msg.geo_valid and self._vehicle is not None:
            # Flat-earth offset from the vehicle, added to the vehicle's absolute
            # ENU position — the offset alone is NOT an ENU coordinate.
            off_e, off_n = self._latlondelta_to_enu(
                msg.latitude_deg, msg.longitude_deg)
            det_e = self._vehicle.position_enu_m.x + off_e
            det_n = self._vehicle.position_enu_m.y + off_n
        elif self._vehicle is not None:
            # Fall back: place detection at current vehicle position
            det_e = self._vehicle.position_enu_m.x
            det_n = self._vehicle.position_enu_m.y

        det_alt = self._search_alt  # detection orbits at search altitude

        if self._bayes_map is not None:
            self._bayes_map.positive_detection(det_e, det_n, self._det_sigma)

        self._orbit_centre = (det_e, det_n, det_alt)
        if msg.geo_valid:
            self._tracked_lat = msg.latitude_deg
            self._tracked_lon = msg.longitude_deg
        elif self._vehicle is not None:
            self._tracked_lat = self._vehicle.latitude_deg
            self._tracked_lon = self._vehicle.longitude_deg
        self._set_phase(SearchState.PHASE_TRACK)
        self.get_logger().info(
            f'Detection → TRACK orbit at ({det_e:.1f}, {det_n:.1f}) m ENU, '
            f'conf={msg.confidence:.2f}')

    # ── Guidance update timer (5 Hz) ─────────────────────────────────────────

    def _timer_update(self) -> None:
        if self._vehicle is None:
            return

        pos_e = self._vehicle.position_enu_m.x
        pos_n = self._vehicle.position_enu_m.y

        if self._phase == SearchState.PHASE_IDLE:
            self._publish_hold(pos_e, pos_n)

        elif self._phase == SearchState.PHASE_TRANSIT:
            self._update_transit(pos_e, pos_n)

        elif self._phase == SearchState.PHASE_SEARCH:
            self._update_search(pos_e, pos_n)

        elif self._phase == SearchState.PHASE_TRACK:
            self._update_track()

        elif self._phase == SearchState.PHASE_RETURN:
            self._update_return(pos_e, pos_n)

    def _publish_hold(self, pos_e: float, pos_n: float) -> None:
        # Latch the hold target on first call so the setpoint doesn't follow the
        # vehicle as it drifts.
        if self._hold_target is None:
            self._hold_target = (pos_e, pos_n, self._vehicle.position_enu_m.z)
        he, hn, hu = self._hold_target
        sp = GuidanceSetpoint()
        sp.header = self._header()
        sp.setpoint_type = GuidanceSetpoint.TYPE_POSITION
        sp.position_enu_m = Point(x=he, y=hn, z=hu)
        sp.yaw_rad = float('nan')
        sp.cruise_speed_m_s = 0.0
        self._pub_setpoint.publish(sp)

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
        if not self._waypoints:
            return

        # Null observation update for Bayesian map.
        if self._bayes_map is not None:
            self._bayes_map.null_observation(pos_e, pos_n, self._footprint_r, self._p_det)

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
        if self._phase == SearchState.PHASE_SEARCH and self._waypoints:
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
        self._set_phase(SearchState.PHASE_SEARCH)
        self.get_logger().info(
            f'Search started: centre=({centre_e:.1f}, {centre_n:.1f}) m ENU, '
            f'r={radius:.0f} m, {len(self._waypoints)} waypoints')

    def _set_phase(self, phase: int) -> None:
        if self._phase in (SearchState.PHASE_SEARCH, SearchState.PHASE_TRACK):
            self._time_on_station += time.monotonic() - self._phase_start
        if phase == SearchState.PHASE_IDLE:
            self._hold_target = None  # re-latch on next hold publish
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
