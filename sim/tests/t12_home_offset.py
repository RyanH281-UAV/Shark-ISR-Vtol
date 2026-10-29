#!/usr/bin/env python3
"""
T12 — VehicleState z is height above home, not above the EKF origin (ADR-019)
Source: sim/tests/t12_home_offset.py

PX4's local z is relative to the EKF origin, which differs from home whenever
GPS locks in one place and the aircraft launches from another. The bridge
shifts z by home's z both ways (VehicleState out, setpoints in), so mission's
10-120 m above-home check (CASA 400 ft) bounds the real height above home.

SITL can't put the EKF origin away from the launch point, so this moves home
instead, in flight:
  1. On the ground: z ~ 0.
  2. CMD_START at 30 m above home; wait until z ~ 30.
  3. DO_SET_HOME 20 m higher → VehicleState z drops to ~10 at once (state
     path), then the vehicle climbs back to ~30 above the new home (setpoint
     path). Before the fix z ignored home entirely and stayed at 30.
  4. Restore home, CMD_RETURN.

Requires (full stack): run_sim.sh, autopilot_bridge, guidance_node,
mission_node. Mission must be IDLE.

Run:
  source ros2_ws/install/setup.bash
  python3 sim/tests/t12_home_offset.py

Overall timeout: ~150 s
"""

import sys, time
import _ros_harness
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, DurabilityPolicy, HistoryPolicy

from shark_isr_interfaces.msg import SearchState, VehicleState
from shark_isr_interfaces.srv import MissionCommand
from px4_msgs.msg import VehicleCommand

PX4_CMD_QOS = QoSProfile(
    reliability=ReliabilityPolicy.RELIABLE,
    durability=DurabilityPolicy.VOLATILE,
    history=HistoryPolicy.KEEP_LAST,
    depth=10,
)
ALT_M = 30.0
HOME_RAISE_M = 20.0
TOL_M = 2.0


def _run(node: Node) -> int:
    latest: dict = {}
    node.create_subscription(
        VehicleState, 'vehicle_state', lambda m: latest.__setitem__('vs', m), 10)
    node.create_subscription(
        SearchState, 'search_state', lambda m: latest.__setitem__('ss', m), 10)
    pub_cmd = node.create_publisher(VehicleCommand, '/fmu/in/vehicle_command', PX4_CMD_QOS)
    cli = node.create_client(MissionCommand, 'mission_command')
    if not cli.wait_for_service(timeout_sec=10.0):
        print('\033[31mFAIL: mission_command not available\033[0m')
        return 1

    def z_now() -> float | None:
        vs = latest.get('vs')
        return vs.position_enu_m.z if vs is not None and vs.position_valid else None

    def wait_z(target: float, timeout: float) -> float | None:
        deadline = time.monotonic() + timeout
        z = None
        while time.monotonic() < deadline:
            z = z_now()
            if z is not None and abs(z - target) < TOL_M:
                return z
            time.sleep(0.1)
        print(f'\033[31mFAIL: z never reached {target:.1f} m (last {z})\033[0m')
        return None

    def call(cmd: int, **kwargs):
        req = MissionCommand.Request()
        req.command = cmd
        for k, v in kwargs.items():
            setattr(req, k, v)
        f = cli.call_async(req)
        deadline = time.monotonic() + 5
        while not f.done() and time.monotonic() < deadline:
            time.sleep(0.05)
        return f.result() if f.done() else None

    def set_home(lat: float, lon: float, alt: float) -> None:
        vc = VehicleCommand()
        vc.timestamp = node.get_clock().now().nanoseconds // 1000
        vc.command = VehicleCommand.VEHICLE_CMD_DO_SET_HOME
        vc.param1 = 0.0  # use the location given in param5-7
        vc.param5, vc.param6, vc.param7 = float(lat), float(lon), float(alt)
        vc.target_system = vc.target_component = 1
        vc.source_system = vc.source_component = 1
        vc.from_external = True
        for _ in range(3):  # PX4's reader is best-effort
            pub_cmd.publish(vc)
            time.sleep(0.1)

    print('[T12] Waiting for mission IDLE and z ~ 0 on the ground...')
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        ss = latest.get('ss')
        if ss is not None and ss.phase == SearchState.PHASE_IDLE and z_now() is not None:
            break
        time.sleep(0.5)
    else:
        print('\033[31mFAIL: mission IDLE / valid position not seen within 120 s\033[0m')
        return 1
    if wait_z(0.0, 10) is None:
        return 1
    vs = latest['vs']
    lat, lon, home_amsl = vs.latitude_deg, vs.longitude_deg, vs.altitude_amsl_m
    print(f'[T12] Home {home_amsl:.2f} m AMSL, z={vs.position_enu_m.z:.2f} ✓')

    resp = call(MissionCommand.Request.CMD_START,
                search_lat_deg=lat, search_lon_deg=lon, search_radius_m=100.0,
                transit_alt_amsl_m=home_amsl + ALT_M, search_alt_amsl_m=home_amsl + ALT_M,
                orbit_radius_m=30.0)
    if resp is None or not resp.accepted:
        print(f'\033[31mFAIL: CMD_START rejected: {resp.reason if resp else "timeout"}\033[0m')
        return 1
    try:
        print(f'[T12] Climbing to {ALT_M:.0f} m above home...')
        if wait_z(ALT_M, 90) is None:
            return 1

        print(f'[T12] DO_SET_HOME {HOME_RAISE_M:.0f} m higher...')
        set_home(lat, lon, home_amsl + HOME_RAISE_M)
        if wait_z(ALT_M - HOME_RAISE_M, 3) is None:
            return 1
        print(f'[T12] VehicleState z dropped to ~{ALT_M - HOME_RAISE_M:.0f} m ✓')
        if wait_z(ALT_M, 60) is None:
            return 1
        print(f'[T12] Climbed back to {ALT_M:.0f} m above the new home ✓')
    finally:
        print('[T12] Restoring home, CMD_RETURN...')
        set_home(lat, lon, home_amsl)
        call(MissionCommand.Request.CMD_RETURN)

    print('\033[32mPASS: T12 VehicleState z is height above home\033[0m')
    return 0


if __name__ == '__main__':
    sys.exit(_ros_harness.run('t12_home_offset', _run))
