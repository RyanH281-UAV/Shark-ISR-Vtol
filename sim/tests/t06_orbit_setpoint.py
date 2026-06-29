#!/usr/bin/env python3
"""
T06 — Orbit setpoint geometry
Source: sim/tests/t06_orbit_setpoint.py

Verify autopilot_bridge._orbit_setpoint_ned() produces TrajectorySetpoints
that sit on the orbit circle within ±20% radius tolerance.

Requires (separate terminals, workspace sourced):
  - run_sim.sh running
  - ros2 launch shark_isr_autopilot autopilot.launch.py

Run:
  source ros2_ws/install/setup.bash
  python3 sim/tests/t06_orbit_setpoint.py
"""

import math, sys, threading, time
import rclpy
import _ros_harness
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, DurabilityPolicy, HistoryPolicy
from geometry_msgs.msg import Point
from std_msgs.msg import Header

from shark_isr_interfaces.msg import GuidanceSetpoint, VehicleState
from shark_isr_interfaces.srv import AutopilotCommand
from px4_msgs.msg import TrajectorySetpoint

PX4_QOS = QoSProfile(
    reliability=ReliabilityPolicy.BEST_EFFORT,
    durability=DurabilityPolicy.VOLATILE,
    history=HistoryPolicy.KEEP_LAST,
    depth=1,
)
ORBIT_R_M = 30.0
# Orbit centre ENU (0, 0, 30) → NED (0, 0, -30)
ORBIT_CENTRE_NED_XY = (0.0, 0.0)
SAMPLES_NEEDED = 20
TOLERANCE = 0.20    # ±20% of radius


def _call_ap(cli, cmd: int) -> bool:
    req = AutopilotCommand.Request()
    req.command = cmd
    f = cli.call_async(req)
    deadline = time.monotonic() + 5
    while not f.done() and time.monotonic() < deadline:
        time.sleep(0.05)
    return f.done() and f.result() is not None and f.result().accepted


def _run(node: Node) -> int:
    samples: list[float] = []
    ev_confirmed = threading.Event()
    ev_samples = threading.Event()

    def cb_vs(msg: VehicleState) -> None:
        if msg.armed and msg.offboard_active:
            ev_confirmed.set()

    def cb_tsp(msg: TrajectorySetpoint) -> None:
        if not ev_confirmed.is_set():
            return
        cx, cy = ORBIT_CENTRE_NED_XY
        d = math.sqrt((msg.position[0] - cx) ** 2 + (msg.position[1] - cy) ** 2)
        samples.append(d)
        if len(samples) >= SAMPLES_NEEDED:
            ev_samples.set()

    node.create_subscription(VehicleState, 'vehicle_state', cb_vs, 10)
    node.create_subscription(
        TrajectorySetpoint, '/fmu/in/trajectory_setpoint', cb_tsp, PX4_QOS)
    pub_sp = node.create_publisher(GuidanceSetpoint, 'guidance_setpoint', 10)

    cli = node.create_client(AutopilotCommand, 'autopilot_command')
    if not cli.wait_for_service(timeout_sec=10.0):
        print('\033[31mFAIL: autopilot_command service not found\033[0m')
        return 1

    print('[T06] ARM...')
    if not _call_ap(cli, AutopilotCommand.Request.CMD_ARM):
        print('\033[31mFAIL: ARM rejected\033[0m')
        return 1

    time.sleep(0.5)
    print('[T06] OFFBOARD...')
    if not _call_ap(cli, AutopilotCommand.Request.CMD_OFFBOARD):
        print('\033[31mFAIL: OFFBOARD rejected\033[0m')
        return 1

    print('[T06] Waiting for armed + offboard_active confirmation...')
    if not ev_confirmed.wait(30):
        print('\033[31mFAIL: armed+offboard not confirmed within 30s\033[0m')
        return 1
    print('[T06] Confirmed. Streaming TYPE_ORBIT setpoint...')

    sp = GuidanceSetpoint()
    sp.header = Header(frame_id='odom')
    sp.setpoint_type = GuidanceSetpoint.TYPE_ORBIT
    sp.position_enu_m = Point(x=0.0, y=0.0, z=30.0)   # ENU centre above home
    sp.orbit_radius_m = ORBIT_R_M
    sp.orbit_clockwise = True
    sp.yaw_rad = float('nan')
    sp.yaw_rate_rad_s = float('nan')

    stop_stream = threading.Event()

    def stream() -> None:
        while not stop_stream.is_set():
            sp.header.stamp = node.get_clock().now().to_msg()
            pub_sp.publish(sp)
            time.sleep(0.05)   # 20 Hz

    threading.Thread(target=stream, daemon=True).start()

    if not ev_samples.wait(30):
        stop_stream.set()
        print(f'\033[31mFAIL: only {len(samples)}/{SAMPLES_NEEDED} samples in 30s\033[0m')
        return 1

    stop_stream.set()

    bad = [d for d in samples if abs(d - ORBIT_R_M) > TOLERANCE * ORBIT_R_M]
    lo, hi = ORBIT_R_M * (1 - TOLERANCE), ORBIT_R_M * (1 + TOLERANCE)
    if bad:
        print(f'\033[31mFAIL: {len(bad)}/{len(samples)} samples outside [{lo:.1f}, {hi:.1f}] m: {bad[:5]}\033[0m')
        return 1

    mean = sum(samples) / len(samples)
    print(f'[T06] Samples: min={min(samples):.2f}  max={max(samples):.2f}  mean={mean:.2f} m  (target={ORBIT_R_M} m)')
    print('\033[32mPASS: T06 orbit setpoint geometry\033[0m')
    return 0


if __name__ == '__main__':
    sys.exit(_ros_harness.run('t06_orbit_setpoint', _run))
