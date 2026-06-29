#!/usr/bin/env python3
"""
T08 — CMD_ABORT → RTL
Source: sim/tests/t08_abort_rtl.py

Verify that CMD_ABORT from an active mission causes the vehicle to enter
PX4 AUTO_RTL (nav_state=5) or AUTO_LOITER (nav_state=4).

Requires (full stack, separate terminals, workspace sourced):
  - run_sim.sh running
  - ros2 launch shark_isr_autopilot autopilot.launch.py
  - ros2 launch shark_isr_guidance guidance.launch.py
  - ros2 launch shark_isr_mission mission.launch.py

Run:
  source ros2_ws/install/setup.bash
  python3 sim/tests/t08_abort_rtl.py
"""

import sys, threading, time
import rclpy
import _ros_harness
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, DurabilityPolicy, HistoryPolicy

from shark_isr_interfaces.msg import SearchState, VehicleState
from shark_isr_interfaces.srv import MissionCommand
from px4_msgs.msg import VehicleStatus

PX4_QOS = QoSProfile(
    reliability=ReliabilityPolicy.BEST_EFFORT,
    durability=DurabilityPolicy.VOLATILE,
    history=HistoryPolicy.KEEP_LAST,
    depth=1,
)
# Use SITL GPS origin (Cottesloe Beach) — transit delta = 0 → immediate arrival
SEARCH_LAT = -31.998
SEARCH_LON = 115.748
# PX4 nav states that indicate a safe hold/return after abort
NAV_RTL = 5
NAV_LOITER = 4


def _call_mc(cli, cmd: int, **kwargs):
    req = MissionCommand.Request()
    req.command = cmd
    for k, v in kwargs.items():
        setattr(req, k, v)
    f = cli.call_async(req)
    deadline = time.monotonic() + 5
    while not f.done() and time.monotonic() < deadline:
        time.sleep(0.05)
    return f.result() if f.done() else None




def _run(node: Node) -> int:
    nav_state = {'val': -1}
    ev_armed = threading.Event()        # vehicle armed → abort will trigger real RTL
    ev_not_idle = threading.Event()     # guidance left IDLE → mission is active
    ev_safe = threading.Event()         # nav_state → RTL or LOITER

    def cb_vs(msg: VehicleState) -> None:
        if msg.armed:
            ev_armed.set()

    def cb_ss(msg: SearchState) -> None:
        if msg.phase != SearchState.PHASE_IDLE:
            ev_not_idle.set()

    def cb_status(msg: VehicleStatus) -> None:
        nav_state['val'] = msg.nav_state
        if msg.nav_state in (NAV_RTL, NAV_LOITER):
            ev_safe.set()

    node.create_subscription(VehicleState, 'vehicle_state', cb_vs, 10)
    node.create_subscription(SearchState, 'search_state', cb_ss, 10)
    node.create_subscription(
        VehicleStatus, '/fmu/out/vehicle_status_v1', cb_status, PX4_QOS)

    cli = node.create_client(MissionCommand, 'mission_command')
    if not cli.wait_for_service(timeout_sec=10.0):
        print('\033[31mFAIL: mission_command service not available\033[0m')
        return 1

    print('[T08] CMD_START (retrying until vehicle position is valid)...')
    for attempt in range(10):
        resp = _call_mc(cli, MissionCommand.Request.CMD_START,
                        search_lat_deg=SEARCH_LAT, search_lon_deg=SEARCH_LON,
                        search_radius_m=100.0, transit_alt_amsl_m=30.0,
                        search_alt_amsl_m=30.0, orbit_radius_m=30.0)
        if resp is not None and resp.accepted:
            break
        reason = resp.reason if resp else 'timeout'
        print(f'[T08]   attempt {attempt + 1}/10: {reason}')
        time.sleep(3)
    else:
        print('\033[31mFAIL: CMD_START never accepted\033[0m')
        return 1

    print('[T08] CMD_START accepted. Waiting for vehicle to arm...')
    if not ev_armed.wait(30):
        print('\033[31mFAIL: vehicle not armed within 30s\033[0m')
        return 1

    print('[T08] Waiting for guidance to leave IDLE...')
    if not ev_not_idle.wait(30):
        print('\033[31mFAIL: guidance still IDLE after 30s\033[0m')
        return 1
    print('[T08] Mission active. Sending CMD_ABORT...')

    resp = _call_mc(cli, MissionCommand.Request.CMD_ABORT)
    if resp is None or not resp.accepted:
        print(f'\033[31mFAIL: CMD_ABORT rejected: {resp.reason if resp else "timeout"}\033[0m')
        return 1
    print('[T08] ABORT accepted. Waiting for PX4 RTL/Hold...')

    if not ev_safe.wait(20):
        print(f'\033[31mFAIL: PX4 did not enter RTL/Hold within 20s (nav_state={nav_state["val"]})\033[0m')
        return 1

    label = 'RTL' if nav_state['val'] == NAV_RTL else 'LOITER'
    print(f'[T08] PX4 nav_state={nav_state["val"]} ({label})')
    print('\033[32mPASS: T08 CMD_ABORT → RTL\033[0m')
    return 0


if __name__ == '__main__':
    sys.exit(_ros_harness.run('t08_abort_rtl', _run))
