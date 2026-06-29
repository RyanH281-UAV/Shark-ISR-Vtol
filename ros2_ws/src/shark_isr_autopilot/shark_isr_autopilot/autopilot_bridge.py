"""
autopilot_bridge.py — The ONLY ROS 2 node that talks to PX4.

Responsibilities (ADR-002, ADR-003, ADR-007, ADR-008):
  - Subscribe to PX4 uXRCE-DDS topics and re-publish unified VehicleState
    (with NED/FRD → ENU/FLU frame conversion).
  - Receive GuidanceSetpoint and forward as PX4 OffboardControlMode +
    TrajectorySetpoint.
  - Provide AutopilotCommand service for arm/disarm/mode transitions.
  - Stream OffboardControlMode heartbeat so PX4 stays in Offboard mode.
  - Never participates in the inner control loop or tilt transition.

Failsafe: if this node dies or the link drops, PX4 detects the lost heartbeat
and falls back to its own RTL/Hold failsafe — the companion is never
safety-critical (ADR-003).
"""

import math

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy, DurabilityPolicy

from geometry_msgs.msg import Point, Quaternion, Vector3
from std_msgs.msg import Header

# PX4 messages (uXRCE-DDS)
from px4_msgs.msg import (
    BatteryStatus,
    OffboardControlMode,
    TrajectorySetpoint,
    VehicleAttitude,
    VehicleCommand,
    VehicleGlobalPosition,
    VehicleLocalPosition,
    VehicleStatus,
    VtolVehicleStatus,
)

# Shark-ISR interfaces
from shark_isr_interfaces.msg import GuidanceSetpoint, VehicleState
from shark_isr_interfaces.srv import AutopilotCommand

from .frame_transforms import (
    att_ned_frd_to_enu_flu,
    enu_to_ned,
    ned_to_enu,
    yaw_enu_to_ned,
)


# QoS profile that matches PX4's uXRCE-DDS publishers (best-effort, volatile).
PX4_QOS = QoSProfile(
    reliability=ReliabilityPolicy.BEST_EFFORT,
    durability=DurabilityPolicy.VOLATILE,
    history=HistoryPolicy.KEEP_LAST,
    depth=1,
)
# VehicleStatus is published TRANSIENT_LOCAL by the uXRCE-DDS agent.
# FastDDS (ROS2 Humble) treats TRANSIENT_LOCAL publisher + VOLATILE subscriber
# as incompatible → zero matched subscriptions → no callbacks. Must match.
PX4_STATUS_QOS = QoSProfile(
    reliability=ReliabilityPolicy.BEST_EFFORT,
    durability=DurabilityPolicy.TRANSIENT_LOCAL,
    history=HistoryPolicy.KEEP_LAST,
    depth=1,
)
# Reliable QoS for one-shot vehicle commands (arm/mode) — RxO-compatible with PX4's best-effort reader.
PX4_CMD_QOS = QoSProfile(
    reliability=ReliabilityPolicy.RELIABLE,
    durability=DurabilityPolicy.VOLATILE,
    history=HistoryPolicy.KEEP_LAST,
    depth=10,
)


class AutopilotBridge(Node):
    """Bridge between ROS 2 guidance stack and PX4 via uXRCE-DDS."""

    def __init__(self) -> None:
        super().__init__('autopilot_bridge')

        # ── Parameters ───────────────────────────────────────────────────────
        self.declare_parameter('mav_sys_id', 1)
        self.declare_parameter('mav_comp_id', 1)
        self.declare_parameter('offboard_hz', 20.0)
        self.declare_parameter('vehicle_state_hz', 20.0)
        self.declare_parameter('setpoint_timeout_s', 2.0)

        self._sys_id = self.get_parameter('mav_sys_id').value
        self._comp_id = self.get_parameter('mav_comp_id').value
        _ob_hz = self.get_parameter('offboard_hz').value
        _vs_hz = self.get_parameter('vehicle_state_hz').value
        self._setpoint_timeout = self.get_parameter('setpoint_timeout_s').value

        # ── State ────────────────────────────────────────────────────────────
        self._local_pos: VehicleLocalPosition | None = None
        self._attitude: VehicleAttitude | None = None
        self._global_pos: VehicleGlobalPosition | None = None
        self._battery: BatteryStatus | None = None
        self._vtol_status: VtolVehicleStatus | None = None
        self._vehicle_status: VehicleStatus | None = None
        self._guidance_setpoint: GuidanceSetpoint | None = None
        self._last_setpoint_time: rclpy.time.Time | None = None
        self._offboard_active = False              # streaming requested by mission
        self._offboard_requested_at: rclpy.time.Time | None = None
        self._last_mode_switch_at: rclpy.time.Time | None = None

        # ── PX4 subscribers ──────────────────────────────────────────────────
        self.create_subscription(
            VehicleLocalPosition, '/fmu/out/vehicle_local_position',
            self._cb_local_pos, PX4_QOS)
        self.create_subscription(
            VehicleAttitude, '/fmu/out/vehicle_attitude',
            self._cb_attitude, PX4_QOS)
        self.create_subscription(
            VehicleGlobalPosition, '/fmu/out/vehicle_global_position',
            self._cb_global_pos, PX4_QOS)
        self.create_subscription(
            BatteryStatus, '/fmu/out/battery_status',
            self._cb_battery, PX4_QOS)
        self.create_subscription(
            VtolVehicleStatus, '/fmu/out/vtol_vehicle_status',
            self._cb_vtol, PX4_QOS)
        self.create_subscription(
            VehicleStatus, '/fmu/out/vehicle_status_v1',
            self._cb_status, PX4_STATUS_QOS)

        # ── PX4 publishers ───────────────────────────────────────────────────
        # High-rate streams use best-effort (freshest-wins, matches PX4 reader QoS).
        self._pub_offboard_mode = self.create_publisher(
            OffboardControlMode, '/fmu/in/offboard_control_mode', PX4_QOS)
        self._pub_trajectory = self.create_publisher(
            TrajectorySetpoint, '/fmu/in/trajectory_setpoint', PX4_QOS)
        self._pub_vehicle_cmd = self.create_publisher(
            VehicleCommand, '/fmu/in/vehicle_command', PX4_CMD_QOS)

        # ── Shark-ISR publishers ─────────────────────────────────────────────
        self._pub_vehicle_state = self.create_publisher(
            VehicleState, 'vehicle_state', 10)

        # ── Shark-ISR subscribers ────────────────────────────────────────────
        self.create_subscription(
            GuidanceSetpoint, 'guidance_setpoint',
            self._cb_guidance_setpoint, 10)

        # ── Services ─────────────────────────────────────────────────────────
        self.create_service(
            AutopilotCommand, 'autopilot_command', self._srv_autopilot_command)

        # ── Timers ───────────────────────────────────────────────────────────
        self.create_timer(1.0 / _ob_hz, self._timer_offboard_heartbeat)
        self.create_timer(1.0 / _vs_hz, self._timer_vehicle_state)

        self.get_logger().info(
            f'autopilot_bridge started (sys_id={self._sys_id}, '
            f'offboard_hz={_ob_hz}, state_hz={_vs_hz})')

    # ── PX4 subscriber callbacks ─────────────────────────────────────────────

    def _cb_local_pos(self, msg: VehicleLocalPosition) -> None:
        self._local_pos = msg

    def _cb_attitude(self, msg: VehicleAttitude) -> None:
        self._attitude = msg

    def _cb_global_pos(self, msg: VehicleGlobalPosition) -> None:
        self._global_pos = msg

    def _cb_battery(self, msg: BatteryStatus) -> None:
        self._battery = msg

    def _cb_vtol(self, msg: VtolVehicleStatus) -> None:
        self._vtol_status = msg

    def _cb_status(self, msg: VehicleStatus) -> None:
        prev = self._vehicle_status
        self._vehicle_status = msg
        if prev is None or prev.arming_state != msg.arming_state or prev.nav_state != msg.nav_state:
            self.get_logger().info(
                f'PX4 status: arm={msg.arming_state} nav={msg.nav_state} '
                f'(armed={self._px4_is_armed()} offboard={self._px4_nav_offboard()})')

    def _px4_is_armed(self) -> bool:
        s = self._vehicle_status
        return s is not None and s.arming_state == VehicleStatus.ARMING_STATE_ARMED

    def _px4_nav_offboard(self) -> bool:
        s = self._vehicle_status
        return s is not None and s.nav_state == VehicleStatus.NAVIGATION_STATE_OFFBOARD

    # ── Guidance setpoint callback ───────────────────────────────────────────

    def _cb_guidance_setpoint(self, msg: GuidanceSetpoint) -> None:
        self._guidance_setpoint = msg
        self._last_setpoint_time = self.get_clock().now()

    # ── 20 Hz offboard heartbeat + setpoint publisher ────────────────────────

    def _timer_offboard_heartbeat(self) -> None:
        """Publish OffboardControlMode (keeps PX4 in Offboard) and TrajectorySetpoint."""
        if not self._offboard_active:
            return

        sp = self._guidance_setpoint
        stale = self._setpoint_is_stale()

        # Determine control dimensions from setpoint type.
        # Stale/None: velocity hold (0,0,0) — NOT NaN positions with position=True,
        # which PX4 v1.16 rejects in the OFFBOARD pre-check and prevents mode entry.
        hold = stale or sp is None
        use_pos = not hold and sp.setpoint_type in (
            GuidanceSetpoint.TYPE_POSITION, GuidanceSetpoint.TYPE_ORBIT)
        use_vel = hold or (sp is not None and not stale
                           and sp.setpoint_type == GuidanceSetpoint.TYPE_VELOCITY)

        # --- OffboardControlMode heartbeat ---
        ocm = OffboardControlMode()
        ocm.timestamp = self._px4_timestamp()
        ocm.position = use_pos
        ocm.velocity = use_vel
        ocm.acceleration = False
        ocm.attitude = False
        ocm.body_rate = False
        self._pub_offboard_mode.publish(ocm)

        # Offboard mode switch: drive OFFBOARD engagement regardless of hold/setpoint
        # state. PX4 accepts OFFBOARD during velocity-hold; the hold stream is a
        # valid Offboard setpoint. Previously this lived after `if hold: return` and
        # only ran when a fresh guidance setpoint was present — which meant OFFBOARD
        # would never engage when guidance is IDLE-silent (DWI-001).
        if self._offboard_active and not self._px4_nav_offboard():
            now = self.get_clock().now()
            if self._offboard_requested_at is None:
                self._offboard_requested_at = now
            warmed_up = (now - self._offboard_requested_at).nanoseconds > 1.0e9
            retry_due = (
                self._last_mode_switch_at is None
                or (now - self._last_mode_switch_at).nanoseconds > 1.0e9
            )
            if warmed_up and retry_due:
                self._send_mode(self._MAIN_OFFBOARD)
                self._last_mode_switch_at = now
                self.get_logger().info('Sent OFFBOARD mode switch')

        # --- TrajectorySetpoint ---
        tsp = TrajectorySetpoint()
        tsp.timestamp = self._px4_timestamp()

        if hold:
            # Velocity hold in place — NaN positions are valid alongside velocity=True
            tsp.position = [float('nan'), float('nan'), float('nan')]
            tsp.velocity = [0.0, 0.0, 0.0]
            tsp.yaw = float('nan')
            self._pub_trajectory.publish(tsp)
            return

        if sp.setpoint_type == GuidanceSetpoint.TYPE_POSITION:
            x_ned, y_ned, z_ned = enu_to_ned(
                sp.position_enu_m.x,
                sp.position_enu_m.y,
                sp.position_enu_m.z,
            )
            tsp.position = [x_ned, y_ned, z_ned]
            tsp.velocity = [float('nan'), float('nan'), float('nan')]
            tsp.yaw = yaw_enu_to_ned(sp.yaw_rad) if not math.isnan(sp.yaw_rad) else float('nan')

        elif sp.setpoint_type == GuidanceSetpoint.TYPE_VELOCITY:
            vx_ned, vy_ned, vz_ned = enu_to_ned(
                sp.velocity_enu_m_s.x,
                sp.velocity_enu_m_s.y,
                sp.velocity_enu_m_s.z,
            )
            tsp.position = [float('nan'), float('nan'), float('nan')]
            tsp.velocity = [vx_ned, vy_ned, vz_ned]
            tsp.yaw = yaw_enu_to_ned(sp.yaw_rad) if not math.isnan(sp.yaw_rad) else float('nan')
            tsp.yawspeed = -sp.yaw_rate_rad_s if not math.isnan(sp.yaw_rate_rad_s) else float('nan')

        elif sp.setpoint_type == GuidanceSetpoint.TYPE_ORBIT:
            # Synthesise the orbit as streamed position setpoints so PX4 stays in
            # Offboard for both hover and fixed-wing phases.  (MAV_CMD_DO_ORBIT
            # would switch PX4 into Orbit flight mode — MC-only, and it drops
            # Offboard, leaving later SEARCH setpoints ignored.)
            tsp.position, tsp.yaw = self._orbit_setpoint_ned(sp)
            tsp.velocity = [float('nan'), float('nan'), float('nan')]

        self._pub_trajectory.publish(tsp)

    _VTOL_STATE_MAP: dict = {
        0: VehicleState.VTOL_PHASE_UNDEFINED,
        1: VehicleState.VTOL_PHASE_TRANS_TO_FW,
        2: VehicleState.VTOL_PHASE_TRANS_TO_MC,
        3: VehicleState.VTOL_PHASE_HOVER,
        4: VehicleState.VTOL_PHASE_FIXED_WING,
    }

    # Lead angle for the synthesised orbit: the position target stays this far
    # ahead of the vehicle on the circle, producing continuous tangential motion.
    _ORBIT_LEAD_RAD = 0.4

    def _orbit_setpoint_ned(self, sp: GuidanceSetpoint) -> tuple[list, float]:
        """Position setpoint on the orbit circle, led ahead of the vehicle.

        Returns ([x_ned, y_ned, z_ned], yaw_ned) with yaw facing the orbit centre.
        NED top-view: angle = atan2(E, N) increases clockwise from above, so a
        clockwise orbit advances the angle positively.
        """
        cx_ned, cy_ned, cz_ned = enu_to_ned(
            sp.position_enu_m.x,
            sp.position_enu_m.y,
            sp.position_enu_m.z,
        )
        radius = max(1.0, sp.orbit_radius_m)

        lp = self._local_pos
        if lp is None:
            return [cx_ned + radius, cy_ned, cz_ned], float('nan')

        theta = math.atan2(lp.y - cy_ned, lp.x - cx_ned)
        lead = self._ORBIT_LEAD_RAD if sp.orbit_clockwise else -self._ORBIT_LEAD_RAD
        theta_t = theta + lead

        x_t = cx_ned + radius * math.cos(theta_t)
        y_t = cy_ned + radius * math.sin(theta_t)
        yaw_to_centre = math.atan2(cy_ned - lp.y, cx_ned - lp.x)
        return [x_t, y_t, cz_ned], yaw_to_centre

    # ── 20 Hz VehicleState publisher ─────────────────────────────────────────

    def _timer_vehicle_state(self) -> None:
        """Translate PX4 state topics → VehicleState and publish."""
        if self._local_pos is None or self._attitude is None:
            return

        vs = VehicleState()
        vs.header = Header()
        vs.header.stamp = self.get_clock().now().to_msg()
        vs.header.frame_id = 'odom'

        lp = self._local_pos
        att = self._attitude

        # Position (NED → ENU)
        if lp.xy_valid:
            ex, ey, ez = ned_to_enu(float(lp.x), float(lp.y), float(lp.z))
            vs.position_enu_m = Point(x=ex, y=ey, z=ez)
            vs.position_h_std_m = float(lp.eph)
        else:
            vs.position_enu_m = Point()
            vs.position_h_std_m = float('inf')

        # Velocity (NED → ENU)
        vex, vey, vez = ned_to_enu(float(lp.vx), float(lp.vy), float(lp.vz))
        vs.velocity_enu_m_s = Vector3(x=vex, y=vey, z=vez)
        vs.groundspeed_m_s = math.sqrt(lp.vx ** 2 + lp.vy ** 2)

        # Attitude (NED/FRD quaternion → ENU/FLU)
        q = att.q  # [w, x, y, z] in PX4
        w_enu, x_enu, y_enu, z_enu = att_ned_frd_to_enu_flu(
            float(q[0]), float(q[1]), float(q[2]), float(q[3]))
        vs.attitude_q = Quaternion(x=x_enu, y=y_enu, z=z_enu, w=w_enu)

        # Global position
        if self._global_pos is not None:
            gp = self._global_pos
            vs.latitude_deg = gp.lat
            vs.longitude_deg = gp.lon
            vs.altitude_amsl_m = float(gp.alt)

        # AGL (use altitude_agl from local position if available, else mark invalid)
        if lp.dist_bottom_valid:
            vs.agl_m = lp.dist_bottom
            vs.agl_valid = True
        elif self._global_pos is not None and lp.z_valid:
            vs.agl_m = -lp.z  # approx AGL over sea = altitude above home
            vs.agl_valid = True
        else:
            vs.agl_m = 0.0
            vs.agl_valid = False

        # VTOL phase
        if self._vtol_status is not None:
            vs.vtol_phase = self._map_vtol_phase(self._vtol_status.vehicle_vtol_state)
        else:
            vs.vtol_phase = VehicleState.VTOL_PHASE_UNDEFINED

        # Battery
        if self._battery is not None:
            vs.battery_fraction = float(self._battery.remaining)
            vs.battery_voltage_v = float(self._battery.voltage_v)
        else:
            vs.battery_fraction = -1.0
            vs.battery_voltage_v = 0.0

        # Status flags (from PX4 VehicleStatus — actual arming/nav state)
        vs.armed = self._px4_is_armed()
        vs.offboard_active = self._px4_nav_offboard()
        vs.position_valid = lp.xy_valid

        self._pub_vehicle_state.publish(vs)

    # ── AutopilotCommand service ──────────────────────────────────────────────

    def _srv_autopilot_command(
        self,
        request: AutopilotCommand.Request,
        response: AutopilotCommand.Response,
    ) -> AutopilotCommand.Response:
        cmd = request.command

        if cmd == AutopilotCommand.Request.CMD_ARM:
            self._send_arm(arm=True)
            response.accepted = True

        elif cmd == AutopilotCommand.Request.CMD_DISARM:
            self._send_arm(arm=False)
            response.accepted = True

        elif cmd == AutopilotCommand.Request.CMD_OFFBOARD:
            # Start streaming setpoints now; the heartbeat timer sends the actual
            # mode switch after >1 s of stream (PX4 rejects OFFBOARD without a
            # pre-existing setpoint stream) and retries until nav_state confirms.
            self._offboard_active = True
            self._offboard_requested_at = self.get_clock().now()
            self._last_mode_switch_at = None
            response.accepted = True

        elif cmd == AutopilotCommand.Request.CMD_HOLD:
            self._offboard_active = False
            self._send_mode(self._MAIN_AUTO, self._SUB_AUTO_LOITER)
            response.accepted = True

        elif cmd == AutopilotCommand.Request.CMD_RTL:
            self._offboard_active = False
            self._send_mode(self._MAIN_AUTO, self._SUB_AUTO_RTL)
            response.accepted = True

        elif cmd == AutopilotCommand.Request.CMD_LAND:
            self._offboard_active = False
            self._send_mode(self._MAIN_AUTO, self._SUB_AUTO_LAND)
            response.accepted = True

        else:
            response.accepted = False
            response.reason = f'Unknown command: {cmd}'
            return response

        self.get_logger().info(f'AutopilotCommand {cmd} sent (accepted)')
        return response

    # ── VehicleCommand helpers ────────────────────────────────────────────────

    def _send_arm(self, arm: bool) -> None:
        cmd = self._make_vehicle_command(
            command=400,    # MAV_CMD_COMPONENT_ARM_DISARM
            param1=1.0 if arm else 0.0,
            param2=21196.0 if arm else 0.0,  # force arm: bypasses preflight checks
        )
        # from_external=False: PX4 arm(reason, from_external || !forced) — with
        # from_external=True the force flag is ignored and preflight checks always run.
        # Internal command matches what `commander arm -f` does in pxh>.
        cmd.from_external = False
        self._pub_vehicle_cmd.publish(cmd)
        self.get_logger().info(f'Sent ARM={arm}')

    # PX4 custom mode encoding for MAV_CMD_DO_SET_MODE:
    #   param2 = main mode, param3 = sub mode (sub mode only used when main = AUTO).
    # Main modes: 1=MANUAL 2=ALTCTL 3=POSCTL 4=AUTO 5=ACRO 6=OFFBOARD 7=STABILIZED
    # AUTO sub modes: 3=LOITER 5=RTL 6=LAND
    _MAIN_AUTO = 4.0
    _MAIN_OFFBOARD = 6.0
    _SUB_AUTO_LOITER = 3.0
    _SUB_AUTO_RTL = 5.0
    _SUB_AUTO_LAND = 6.0

    def _send_mode(self, main_mode: float, sub_mode: float = 0.0) -> None:
        """Send VEHICLE_CMD_DO_SET_MODE with PX4 custom main/sub mode."""
        cmd = self._make_vehicle_command(
            command=176,    # MAV_CMD_DO_SET_MODE
            param1=1.0,     # MAV_MODE_FLAG_CUSTOM_MODE_ENABLED
            param2=main_mode,
            param3=sub_mode,
        )
        self._pub_vehicle_cmd.publish(cmd)

    def _make_vehicle_command(
        self,
        command: int,
        param1: float = float('nan'),
        param2: float = float('nan'),
        param3: float = float('nan'),
        param4: float = float('nan'),
        param5: float = float('nan'),
        param6: float = float('nan'),
        param7: float = float('nan'),
    ) -> VehicleCommand:
        vc = VehicleCommand()
        vc.timestamp = self._px4_timestamp()
        vc.command = command
        vc.param1 = param1
        vc.param2 = param2
        vc.param3 = param3
        vc.param4 = param4
        vc.param5 = param5
        vc.param6 = param6
        vc.param7 = param7
        vc.target_system = self._sys_id
        vc.target_component = self._comp_id
        vc.source_system = self._sys_id
        vc.source_component = self._comp_id
        vc.from_external = True
        return vc

    # ── Utilities ────────────────────────────────────────────────────────────

    def _px4_timestamp(self) -> int:
        """PX4 timestamp in microseconds (PX4's DDS client handles clock offset)."""
        return self.get_clock().now().nanoseconds // 1000

    def _setpoint_is_stale(self) -> bool:
        if self._last_setpoint_time is None:
            return True
        elapsed = (self.get_clock().now() - self._last_setpoint_time).nanoseconds * 1e-9
        return elapsed > self._setpoint_timeout

    @staticmethod
    def _map_vtol_phase(px4_state: int) -> int:
        """Map PX4 vtol_vehicle_state (PX4 v1.16) to VehicleState VTOL_PHASE_* constant."""
        return AutopilotBridge._VTOL_STATE_MAP.get(px4_state, VehicleState.VTOL_PHASE_UNDEFINED)


def main(args=None) -> None:
    rclpy.init(args=args)
    node = AutopilotBridge()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()
