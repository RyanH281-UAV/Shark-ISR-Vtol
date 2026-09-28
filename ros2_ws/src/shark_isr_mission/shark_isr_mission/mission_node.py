"""
mission_node.py — Mission state machine: coordinates autopilot and guidance layers.

Phases:
  IDLE ─CMD_START─▶ STARTING ─armed+offboard─▶ TRANSITING
  TRANSITING ─arrival─▶ SEARCHING
  SEARCHING ─Detection─▶ TRACKING    (guidance drives orbit; mission observes)
  TRACKING ─timeout/cmd─▶ SEARCHING
  any ─CMD_ABORT/CMD_RETURN─▶ RETURNING
  any ─CMD_PAUSE─▶ PAUSED ─CMD_RESUME─▶ [prior phase]
  any ─low_battery─▶ RETURNING (failsafe)

This node is purely a coordinator — it never computes trajectories.  It calls
AutopilotCommand and SetGuidanceMode services in response to MissionCommand
requests and state changes, and monitors VehicleState + SearchState for
automated transitions and failsafes.

Two phase machines, on purpose
------------------------------
Mission has its own MissionPhase (it adds STARTING, PAUSED and LANDED, which
guidance has no reason to know about). For TRANSIT/SEARCH/TRACK guidance is
the authority: mission copies guidance's phase from SearchState
(_cb_search_state) instead of guessing, and only commands phase changes
through SetGuidanceMode.

Why the callback group and MultiThreadedExecutor
------------------------------------------------
Every service call here is call_async with a done-callback — never a blocking
call. A blocking call made from inside a callback on a single-threaded
executor waits for a reply that the same (busy) thread would have to
deliver, i.e. it deadlocks. The ReentrantCallbackGroup plus the
MultiThreadedExecutor in main() let replies arrive while other callbacks run.

Where to change things
----------------------
  thresholds and timeouts → config/mission.yaml
  a new operator command → MissionCommand.srv constant + a branch in
      _srv_mission_command
  a new failsafe → a _check_* method called from _timer_update; end it with
      _trigger_return() so guidance and PX4 are both told
"""

import math
import time
from enum import IntEnum

import rclpy
from rclpy.node import Node
from rclpy.callback_groups import ReentrantCallbackGroup
from rcl_interfaces.msg import SetParametersResult

from geometry_msgs.msg import Point
from shark_isr_interfaces.msg import SearchState, VehicleState
from shark_isr_interfaces.srv import AutopilotCommand, MissionCommand, SetGuidanceMode


class MissionPhase(IntEnum):
    IDLE = 0
    STARTING = 1      # arming + mode switch in progress
    TRANSITING = 2
    SEARCHING = 3
    TRACKING = 4
    PAUSED = 5
    RETURNING = 6
    LANDED = 7


# Guidance owns TRANSIT/SEARCH/TRACK; the mission only observes those phase
# changes (SetGuidanceMode is what commands them). Used by _cb_search_state to
# mirror guidance's phase without also matching STARTING/PAUSED/RETURNING/IDLE,
# which the mission itself owns and must not be knocked out of by a stray
# SearchState message.
_GUIDANCE_PHASE_MAP = {
    SearchState.PHASE_TRANSIT: MissionPhase.TRANSITING,
    SearchState.PHASE_SEARCH: MissionPhase.SEARCHING,
    SearchState.PHASE_TRACK: MissionPhase.TRACKING,
}


class MissionNode(Node):
    """Coordinates AutopilotCommand and SetGuidanceMode to run the ISR mission."""

    def __init__(self) -> None:
        super().__init__('mission_node')

        # ── Parameters ───────────────────────────────────────────────────────
        self.declare_parameter('update_hz', 2.0)
        self.declare_parameter('low_battery_threshold', 0.20)
        self.declare_parameter('arm_timeout_s', 10.0)
        self.declare_parameter('transit_timeout_s', 300.0)
        self.declare_parameter('track_timeout_s', 120.0)
        # Search area preset (ADR-012/ADR-015/ADR-018): a beachfront swim zone
        # is a strip, not a circle. Applied only when CMD_START doesn't select
        # a strip itself (search_length_m <= 0) — default 0 keeps every
        # existing caller (including the SITL tests) on the circular area.
        self.declare_parameter('search_length_m', 0.0)
        self.declare_parameter('search_width_m', 120.0)
        self.declare_parameter('shore_bearing_rad', 0.0)
        # Altitude envelope, as height above home (ENU z). CMD_START altitudes
        # are AMSL; they are converted and then checked against this band so a
        # typo (or AMSL-vs-AGL confusion) is rejected on the ground instead of
        # flown. 120 m = the CASA standard-operating ceiling (400 ft AGL).
        self.declare_parameter('min_alt_above_home_m', 10.0)
        self.declare_parameter('max_alt_above_home_m', 120.0)

        self._low_batt_thresh = self.get_parameter('low_battery_threshold').value
        self._arm_timeout = self.get_parameter('arm_timeout_s').value
        self._transit_timeout = self.get_parameter('transit_timeout_s').value
        self._track_timeout = self.get_parameter('track_timeout_s').value
        self._default_search_length = self.get_parameter('search_length_m').value
        self._default_search_width = self.get_parameter('search_width_m').value
        self._default_shore_bearing = self.get_parameter('shore_bearing_rad').value
        self._min_alt = self.get_parameter('min_alt_above_home_m').value
        self._max_alt = self.get_parameter('max_alt_above_home_m').value

        self.add_on_set_parameters_callback(self._on_params_change)

        # ── State ────────────────────────────────────────────────────────────
        self._phase = MissionPhase.IDLE
        self._prior_phase = MissionPhase.IDLE   # restored on CMD_RESUME
        self._vehicle: VehicleState | None = None
        self._search_state: SearchState | None = None

        # Mission parameters (set by CMD_START)
        self._search_lat: float = 0.0
        self._search_lon: float = 0.0
        self._search_radius: float = 200.0
        # Heights here are ENU z = metres ABOVE HOME, already converted from the
        # AMSL values in CMD_START (see _amsl_to_height_above_home).
        self._transit_alt: float = 50.0
        self._search_alt: float = 50.0
        # 0 = "use guidance's own orbit_radius_m" — guidance owns the default.
        self._orbit_radius: float = 0.0
        self._search_length: float = 0.0    # 0 = circle; ADR-012/ADR-018 strip
        self._search_width: float = 0.0
        self._shore_bearing: float = 0.0

        # Phase timing
        self._phase_start: float = 0.0
        self._low_battery_triggered = False

        # ── Callback group (allows service calls from timer callbacks) ───────
        self._cb = ReentrantCallbackGroup()

        # ── Subscribers ──────────────────────────────────────────────────────
        self.create_subscription(
            VehicleState, 'vehicle_state', self._cb_vehicle, 10,
            callback_group=self._cb)
        self.create_subscription(
            SearchState, 'search_state', self._cb_search_state, 10,
            callback_group=self._cb)

        # ── Service clients ──────────────────────────────────────────────────
        self._cli_ap = self.create_client(
            AutopilotCommand, 'autopilot_command', callback_group=self._cb)
        self._cli_gd = self.create_client(
            SetGuidanceMode, 'set_guidance_mode', callback_group=self._cb)

        # ── Service server ───────────────────────────────────────────────────
        self.create_service(
            MissionCommand, 'mission_command', self._srv_mission_command,
            callback_group=self._cb)

        # ── Timer ────────────────────────────────────────────────────────────
        hz = self.get_parameter('update_hz').value
        self.create_timer(1.0 / hz, self._timer_update, callback_group=self._cb)

        self.get_logger().info('mission_node started')

    # ── Subscriber callbacks ─────────────────────────────────────────────────

    def _cb_vehicle(self, msg: VehicleState) -> None:
        self._vehicle = msg

    def _cb_search_state(self, msg: SearchState) -> None:
        self._search_state = msg
        # Guidance-driven phase transitions (mission observes, doesn't command).
        # Only mirror while the mission is itself in a guidance-owned phase —
        # this used to have separate SEARCHING/TRACKING branches and no
        # TRANSITING one, so the mission sat in TRANSITING for up to
        # transit_timeout_s after guidance had already reached SEARCH.
        if self._phase not in _GUIDANCE_PHASE_MAP.values():
            return
        target = _GUIDANCE_PHASE_MAP.get(msg.phase)
        if target is not None and target != self._phase:
            self._set_phase(target)
            self.get_logger().info(f'SearchState phase {msg.phase} → {target.name}')

    # ── 2 Hz monitor: failsafes + timeout transitions ────────────────────────

    def _timer_update(self) -> None:
        self._check_battery_failsafe()
        self._check_phase_timeouts()
        self._check_starting_complete()

    def _check_starting_complete(self) -> None:
        """STARTING → TRANSITING once PX4 confirms armed + Offboard (real state,
        not just service acks)."""
        if self._phase != MissionPhase.STARTING or self._vehicle is None:
            return
        if self._vehicle.armed and self._vehicle.offboard_active:
            self.get_logger().info('PX4 confirmed armed + Offboard → transit')
            self._do_transit()

    def _check_battery_failsafe(self) -> None:
        if self._low_battery_triggered:
            return
        if self._vehicle is None:
            return
        if self._phase in (MissionPhase.IDLE, MissionPhase.LANDED, MissionPhase.RETURNING):
            return
        # Trigger on a finite, in-range reading below threshold. math.isfinite
        # rejects NaN (estimator not converged — nan<thresh is False anyway, but
        # the explicit guard documents intent); >=0.0 includes a genuine 0% while
        # rejecting the bridge's -1.0 "no battery msg" sentinel.
        frac = self._vehicle.battery_fraction
        if math.isfinite(frac) and 0.0 <= frac < self._low_batt_thresh:
            self.get_logger().warn(
                f'LOW BATTERY ({frac:.0%}) → triggering return')
            self._low_battery_triggered = True
            self._trigger_return()

    def _check_phase_timeouts(self) -> None:
        elapsed = time.monotonic() - self._phase_start
        if self._phase == MissionPhase.STARTING:
            if elapsed > self._arm_timeout:
                self.get_logger().error(
                    f'Arming timeout ({self._arm_timeout:.0f}s) — aborting')
                self._trigger_return()
        elif self._phase == MissionPhase.TRANSITING:
            if elapsed > self._transit_timeout:
                self.get_logger().warn(
                    f'Transit timeout ({self._transit_timeout:.0f}s) — starting search anyway')
                self._start_search()
        elif self._phase == MissionPhase.TRACKING:
            if elapsed > self._track_timeout:
                self.get_logger().info(
                    f'Track timeout ({self._track_timeout:.0f}s) — resuming search')
                self._start_search()
        elif self._phase == MissionPhase.RETURNING:
            if self._vehicle is not None and not self._vehicle.armed:
                self.get_logger().info('Vehicle disarmed after return → IDLE')
                self._set_phase(MissionPhase.IDLE)
                req = SetGuidanceMode.Request()
                req.mode = SetGuidanceMode.Request.MODE_IDLE
                self._cli_gd.call_async(req)

    # ── MissionCommand service ────────────────────────────────────────────────

    def _srv_mission_command(
        self,
        request: MissionCommand.Request,
        response: MissionCommand.Response,
    ) -> MissionCommand.Response:
        cmd = request.command

        if cmd == MissionCommand.Request.CMD_START:
            if self._phase != MissionPhase.IDLE:
                response.accepted = False
                response.reason = f'Mission already active (phase={self._phase.name})'
                response.current_phase = self._guidance_phase()
                return response

            # Altitudes first: they need a valid position (to find home's AMSL)
            # and can reject the whole command, so nothing is stored until
            # they pass.
            heights, reason = self._start_altitudes(
                request.transit_alt_amsl_m, request.search_alt_amsl_m)
            if heights is None:
                self.get_logger().error(f'CMD_START rejected: {reason}')
                response.accepted = False
                response.reason = reason
                response.current_phase = self._guidance_phase()
                return response
            self._transit_alt, self._search_alt = heights

            self._search_lat = request.search_lat_deg
            self._search_lon = request.search_lon_deg
            self._search_radius = request.search_radius_m or 200.0
            # Per-mission, not sticky: 0 hands the choice back to guidance's
            # default instead of silently reusing the previous mission's radius.
            self._orbit_radius = max(0.0, request.orbit_radius_m)
            # Strip area: only when the request itself asks for one, else the
            # node's configured preset (which defaults to 0 = circle).
            if request.search_length_m > 0:
                self._search_length = request.search_length_m
                self._search_width = request.search_width_m or self._default_search_width
                self._shore_bearing = request.shore_bearing_rad
            else:
                self._search_length = self._default_search_length
                self._search_width = self._default_search_width
                self._shore_bearing = self._default_shore_bearing
            self._low_battery_triggered = False
            if not self._start_mission():
                response.accepted = False
                response.reason = ('No valid vehicle position yet — cannot place '
                                   'the search area; retry once GPS is valid')
                response.current_phase = self._guidance_phase()
                return response
            response.accepted = True

        elif cmd == MissionCommand.Request.CMD_ABORT:
            if self._phase in (MissionPhase.IDLE, MissionPhase.LANDED):
                response.accepted = False
                response.reason = 'Nothing to abort'
                response.current_phase = self._guidance_phase()
                return response
            self._trigger_return()
            response.accepted = True

        elif cmd == MissionCommand.Request.CMD_RETURN:
            self._trigger_return()
            response.accepted = True

        elif cmd == MissionCommand.Request.CMD_PAUSE:
            if self._phase == MissionPhase.PAUSED:
                response.accepted = False
                response.reason = 'Already paused'
                response.current_phase = self._guidance_phase()
                return response
            self._prior_phase = self._phase
            self._set_phase(MissionPhase.PAUSED)
            self._call_ap(AutopilotCommand.Request.CMD_HOLD)
            response.accepted = True

        elif cmd == MissionCommand.Request.CMD_RESUME:
            if self._phase != MissionPhase.PAUSED:
                response.accepted = False
                response.reason = 'Not paused'
                response.current_phase = self._guidance_phase()
                return response
            self._call_ap(AutopilotCommand.Request.CMD_OFFBOARD)
            self._set_phase(self._prior_phase)
            self._restore_guidance()
            response.accepted = True

        else:
            response.accepted = False
            response.reason = f'Unknown command: {cmd}'
            response.current_phase = self._guidance_phase()
            return response

        self.get_logger().info(f'MissionCommand {cmd} accepted → phase={self._phase.name}')
        response.current_phase = self._guidance_phase()
        return response

    # ── Mission sequence helpers ──────────────────────────────────────────────

    def _start_mission(self) -> bool:
        """ARM → OFFBOARD → TRANSIT. Returns False when start is rejected so the
        MissionCommand response reports the truth (not a blanket accepted)."""
        # Reject start without a valid position estimate: _latlondelta_to_enu would
        # silently return the ENU origin (0,0), making the vehicle arm and "transit"
        # to home instead of the requested search area.
        if self._vehicle is None or not self._vehicle.position_valid:
            self.get_logger().error(
                'CMD_START rejected: no valid vehicle position yet — '
                'cannot compute transit target (would default to ENU origin).')
            return False
        self._set_phase(MissionPhase.STARTING)
        self._call_ap(AutopilotCommand.Request.CMD_ARM,
                      done_cb=self._on_arm_response)
        return True

    def _on_arm_response(self, future) -> None:
        result = future.result()
        if result and result.accepted:
            self.get_logger().info('Armed — switching to Offboard')
            self._call_ap(AutopilotCommand.Request.CMD_OFFBOARD,
                          done_cb=self._on_offboard_response)
        else:
            reason = result.reason if result else 'no response'
            self.get_logger().error(f'Arm rejected: {reason}')
            self._set_phase(MissionPhase.IDLE)

    def _on_offboard_response(self, future) -> None:
        result = future.result()
        if result and result.accepted:
            # Bridge accepted the request; PX4 confirmation (armed + nav_state
            # OFFBOARD) is verified in _timer_update before transit starts.
            self.get_logger().info('Offboard requested — awaiting PX4 confirmation')
        else:
            reason = result.reason if result else 'no response'
            self.get_logger().error(f'Offboard rejected: {reason}')
            self._trigger_return()

    def _do_transit(self) -> None:
        """Call SetGuidanceMode TRANSIT.  Guidance will switch to SEARCH on arrival."""
        self._set_phase(MissionPhase.TRANSITING)
        req = SetGuidanceMode.Request()
        req.mode = SetGuidanceMode.Request.MODE_TRANSIT
        # Transit target: above search area centre at transit altitude.
        # Flat-earth ENU offset from home (guidance does the same conversion).
        te, tn = self._latlondelta_to_enu(self._search_lat, self._search_lon)
        req.transit_target_enu_m = Point(x=te, y=tn, z=self._transit_alt)
        # Seed the eventual search area — guidance self-transitions to SEARCH
        # on arrival and needs these before MODE_SEARCH is ever called.
        req.search_radius_m = self._search_radius
        req.search_alt_enu_z_m = self._search_alt
        req.search_length_m = self._search_length
        req.search_width_m = self._search_width
        req.shore_bearing_rad = self._shore_bearing
        # Carried so guidance knows the orbit radius for a gate-entered TRACK;
        # before this, CMD_START.orbit_radius_m was stored here and never sent.
        req.orbit_radius_m = self._orbit_radius
        future = self._cli_gd.call_async(req)
        future.add_done_callback(self._on_transit_response)

    def _on_transit_response(self, future) -> None:
        result = future.result()
        if result and result.accepted:
            self.get_logger().info('Guidance: TRANSIT started')
            # Wait for guidance to reach transit target; it will call _start_search
            # via the arrival detection in guidance_node.
            # Mission also has a timeout fallback in _check_phase_timeouts.
        else:
            self.get_logger().warn('Transit guidance rejected — starting search directly')
            self._start_search()

    def _start_search(self) -> None:
        self._set_phase(MissionPhase.SEARCHING)
        req = SetGuidanceMode.Request()
        req.mode = SetGuidanceMode.Request.MODE_SEARCH
        te, tn = self._latlondelta_to_enu(self._search_lat, self._search_lon)
        req.search_centre_enu_m = Point(x=te, y=tn, z=0.0)
        req.search_radius_m = self._search_radius
        req.search_alt_enu_z_m = self._search_alt
        req.search_length_m = self._search_length
        req.search_width_m = self._search_width
        req.shore_bearing_rad = self._shore_bearing
        req.orbit_radius_m = self._orbit_radius
        future = self._cli_gd.call_async(req)
        future.add_done_callback(
            lambda f: self.get_logger().info(
                f'SetGuidanceMode SEARCH: accepted={f.result().accepted if f.result() else False}'))

    def _trigger_return(self) -> None:
        self._set_phase(MissionPhase.RETURNING)
        req = SetGuidanceMode.Request()
        req.mode = SetGuidanceMode.Request.MODE_RETURN
        self._cli_gd.call_async(req)
        self._call_ap(AutopilotCommand.Request.CMD_RTL)
        self.get_logger().info('Return triggered (RTL)')

    def _restore_guidance(self) -> None:
        """Re-issue the guidance mode matching current mission phase after resume."""
        if self._phase == MissionPhase.TRANSITING:
            self._do_transit()
        elif self._phase == MissionPhase.SEARCHING:
            self._start_search()
        elif self._phase == MissionPhase.TRACKING:
            # Guidance will re-engage orbit from its own state.
            pass

    # ── Service call helpers ──────────────────────────────────────────────────

    def _call_ap(self, command: int, done_cb=None) -> None:
        req = AutopilotCommand.Request()
        req.command = command
        future = self._cli_ap.call_async(req)
        if done_cb:
            future.add_done_callback(done_cb)

    # ── Utilities ────────────────────────────────────────────────────────────

    def _set_phase(self, phase: MissionPhase) -> None:
        self._phase = phase
        self._phase_start = time.monotonic()
        self.get_logger().info(f'Mission phase → {phase.name}')

    def _guidance_phase(self) -> int:
        if self._search_state is not None:
            return self._search_state.phase
        return SearchState.PHASE_IDLE

    # Height above home used when CMD_START leaves an altitude at 0 (ADR-010's
    # 30 m patrol altitude). Already home-relative, so it is not converted.
    _DEFAULT_ALT_ABOVE_HOME_M = 30.0

    def _start_altitudes(
        self, transit_amsl_m: float, search_amsl_m: float,
    ) -> tuple[tuple[float, float] | None, str]:
        """Convert CMD_START's AMSL altitudes to heights above home and range-check.

        Returns ((transit_z, search_z), '') or (None, reason). Everything below
        the mission layer (guidance setpoints, the bridge) works in ENU z =
        metres above home, so AMSL must be converted exactly once, here.
        """
        v = self._vehicle
        if v is None or not v.position_valid:
            return None, ('No valid vehicle position yet — cannot place the '
                          'search area; retry once GPS is valid')
        # The bridge leaves lat/lon/AMSL at 0.0 until PX4's global position
        # arrives; converting against that would place home at sea level
        # regardless of where it really is.
        if v.latitude_deg == 0.0 and v.longitude_deg == 0.0:
            return None, 'No global position (lat/lon) yet — retry once GPS is valid'
        # Home's AMSL = where we are now (AMSL) minus how high above home we are.
        # Works whether CMD_START is sent on the ground (z ~ 0) or mid-flight.
        home_amsl = v.altitude_amsl_m - v.position_enu_m.z
        heights = []
        for name, amsl in (('transit', transit_amsl_m), ('search', search_amsl_m)):
            z = (amsl - home_amsl) if amsl else self._DEFAULT_ALT_ABOVE_HOME_M
            if not self._min_alt <= z <= self._max_alt:
                return None, (
                    f'{name} altitude {amsl:.1f} m AMSL is {z:.1f} m above home '
                    f'(home {home_amsl:.1f} m AMSL); allowed '
                    f'{self._min_alt:.0f}-{self._max_alt:.0f} m above home')
            heights.append(z)
        return (heights[0], heights[1]), ''

    def _latlondelta_to_enu(self, lat_deg: float, lon_deg: float) -> tuple[float, float]:
        """Absolute ENU (east, north) of (lat_deg, lon_deg).

        Computes the flat-earth offset from the vehicle's current lat/lon and
        adds the vehicle's current ENU position, so the result is valid even
        when the vehicle is far from the ENU origin (e.g. CMD_START mid-flight).
        """
        if self._vehicle is None or not self._vehicle.position_valid:
            return 0.0, 0.0
        lat0 = self._vehicle.latitude_deg
        lon0 = self._vehicle.longitude_deg
        R = 6_371_000.0
        dlat = math.radians(lat_deg - lat0)
        dlon = math.radians(lon_deg - lon0)
        north = dlat * R
        east = dlon * R * math.cos(math.radians(lat0))
        return (
            self._vehicle.position_enu_m.x + east,
            self._vehicle.position_enu_m.y + north,
        )

    def _on_params_change(self, params) -> SetParametersResult:
        for p in params:
            if p.name == 'low_battery_threshold':
                self._low_batt_thresh = p.value
                self.get_logger().info(f'low_battery_threshold updated → {p.value:.3f}')
        return SetParametersResult(successful=True)


def main(args=None) -> None:
    rclpy.init(args=args)
    node = MissionNode()
    from rclpy.executors import MultiThreadedExecutor
    executor = MultiThreadedExecutor()
    executor.add_node(node)
    try:
        executor.spin()
    finally:
        node.destroy_node()
        rclpy.shutdown()
