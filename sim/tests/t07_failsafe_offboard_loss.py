#!/usr/bin/env python3
"""
T07 — Failsafe: offboard stream loss → PX4 exits OFFBOARD autonomously
Source: sim/tests/t07_failsafe_offboard_loss.py

Verify ADR-003 safety guarantee: PX4 exits OFFBOARD when the companion
process (autopilot_bridge) dies. PX4 COM_OF_LOSS_T=5.0 s is set by run_sim.sh.

Requires:
  - run_sim.sh running
  - ros2 launch shark_isr_autopilot autopilot.launch.py

Run:
  source ros2_ws/install/setup.bash
  python3 sim/tests/t07_failsafe_offboard_loss.py

WARNING: This test kills autopilot_bridge. Restart it after the test.
"""

import subprocess, sys, threading, time
import rclpy
import _ros_harness
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, DurabilityPolicy, HistoryPolicy

from shark_isr_interfaces.srv import AutopilotCommand
from px4_msgs.msg import VehicleStatus

PX4_QOS = QoSProfile(
    reliability=ReliabilityPolicy.BEST_EFFORT,
    durability=DurabilityPolicy.VOLATILE,
    history=HistoryPolicy.KEEP_LAST,
    depth=1,
)
NAV_OFFBOARD = 14
LOSS_T = 5.0        # COM_OF_LOSS_T set in run_sim.sh
MARGIN = 5.0        # extra wait beyond LOSS_T


def _call_ap(cli, cmd: int) -> bool:
    req = AutopilotCommand.Request()
    req.command = cmd
    f = cli.call_async(req)
    deadline = time.monotonic() + 5
    while not f.done() and time.monotonic() < deadline:
        time.sleep(0.05)
    return f.done() and f.result() is not None and f.result().accepted


def _run(node: Node) -> int:
    nav_state = {'val': -1}
    ev_offboard = threading.Event()     # nav_state reached OFFBOARD
    ev_exited = threading.Event()       # nav_state left OFFBOARD after kill

    def cb_status(msg: VehicleStatus) -> None:
        nav_state['val'] = msg.nav_state
        if msg.nav_state == NAV_OFFBOARD:
            ev_offboard.set()
        elif ev_offboard.is_set() and msg.nav_state != NAV_OFFBOARD:
            ev_exited.set()

    node.create_subscription(
        VehicleStatus, '/fmu/out/vehicle_status_v1', cb_status, PX4_QOS)

    cli = node.create_client(AutopilotCommand, 'autopilot_command')
    if not cli.wait_for_service(timeout_sec=10.0):
        print('\033[31mFAIL: autopilot_command not available\033[0m')
        return 1

    print('[T07] ARM...')
    if not _call_ap(cli, AutopilotCommand.Request.CMD_ARM):
        print('\033[31mFAIL: ARM rejected\033[0m')
        return 1

    time.sleep(0.5)
    print('[T07] OFFBOARD...')
    if not _call_ap(cli, AutopilotCommand.Request.CMD_OFFBOARD):
        print('\033[31mFAIL: OFFBOARD rejected\033[0m')
        return 1

    print('[T07] Waiting for PX4 nav_state == OFFBOARD (14)...')
    if not ev_offboard.wait(30):
        print(f'\033[31mFAIL: OFFBOARD not confirmed in 30s (nav_state={nav_state["val"]})\033[0m')
        return 1
    print('[T07] OFFBOARD confirmed. Killing autopilot_bridge (simulates companion crash)...')

    r = subprocess.run(['pkill', '-f', 'autopilot_bridge'], capture_output=True)
    # pkill returns 1 if no process matched; that's fine
    if r.returncode not in (0, 1):
        print(f'\033[31mFAIL: pkill returned unexpected code {r.returncode}\033[0m')
        return 1
    kill_t = time.monotonic()

    timeout = LOSS_T + MARGIN
    print(f'[T07] Bridge killed. Expecting PX4 to exit OFFBOARD within {timeout:.0f}s '
          f'(COM_OF_LOSS_T={LOSS_T}s + {MARGIN}s margin)...')
    if not ev_exited.wait(timeout):
        print(f'\033[31mFAIL: PX4 still in OFFBOARD after {timeout:.0f}s '
              f'(nav_state={nav_state["val"]})\033[0m')
        return 1

    elapsed = time.monotonic() - kill_t
    print(f'[T07] PX4 exited OFFBOARD in {elapsed:.1f}s → nav_state={nav_state["val"]}')
    print('\033[32mPASS: T07 failsafe — companion death → PX4 exits OFFBOARD\033[0m')
    print('[T07] NOTE: restart autopilot_bridge before running further tests.')
    return 0


if __name__ == '__main__':
    sys.exit(_ros_harness.run('t07_failsafe', _run))
