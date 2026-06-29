#!/usr/bin/env python3
"""
T09 — Low battery failsafe → RETURNING
Source: sim/tests/t09_low_battery_failsafe.py

Verify mission_node triggers RETURNING when battery falls below threshold.
Method: set low_battery_threshold above SITL battery (~1.0) via ros2 param set.
mission_node must have param callback support (added in this branch).

Requires (full stack):
  - run_sim.sh running
  - ros2 launch shark_isr_autopilot autopilot.launch.py
  - ros2 launch shark_isr_guidance guidance.launch.py
  - ros2 launch shark_isr_mission mission.launch.py

Run:
  source ros2_ws/install/setup.bash
  python3 sim/tests/t09_low_battery_failsafe.py
"""

import subprocess, sys, threading, time
import rclpy
import _ros_harness
from rclpy.node import Node

from shark_isr_interfaces.msg import SearchState
from shark_isr_interfaces.srv import MissionCommand

SEARCH_LAT = -31.998    # SITL home — transit target ≈ 0 ENU → immediate arrival
SEARCH_LON = 115.748
# SITL battery stays near 1.0; set threshold just above to force failsafe.
TRIGGER_THRESHOLD = 1.05
MISSION_NODE = '/mission_node'


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
    ev_idle = threading.Event()
    ev_return = threading.Event()

    def cb_ss(msg: SearchState) -> None:
        if msg.phase == SearchState.PHASE_IDLE:
            ev_idle.set()
        if msg.phase == SearchState.PHASE_RETURN:
            ev_return.set()

    node.create_subscription(SearchState, 'search_state', cb_ss, 10)

    cli = node.create_client(MissionCommand, 'mission_command')
    if not cli.wait_for_service(timeout_sec=10.0):
        print('\033[31mFAIL: mission_command not available\033[0m')
        return 1

    print('[T09] Waiting for mission PHASE_IDLE (previous test may have left mission active)...')
    if not ev_idle.wait(120):
        print('\033[31mFAIL: mission did not reach IDLE within 120s\033[0m')
        return 1

    print('[T09] CMD_START (retrying until position valid)...')
    for attempt in range(10):
        resp = _call_mc(cli, MissionCommand.Request.CMD_START,
                        search_lat_deg=SEARCH_LAT, search_lon_deg=SEARCH_LON,
                        search_radius_m=100.0, transit_alt_amsl_m=30.0,
                        search_alt_amsl_m=30.0, orbit_radius_m=30.0)
        if resp is not None and resp.accepted:
            break
        reason = resp.reason if resp else 'timeout'
        print(f'[T09]   attempt {attempt + 1}/10: {reason}')
        time.sleep(3)
    else:
        print('\033[31mFAIL: CMD_START never accepted\033[0m')
        return 1

    print(f'[T09] Setting low_battery_threshold={TRIGGER_THRESHOLD} '
          f'(SITL battery ≈ 1.0 → below threshold → failsafe fires)...')
    r = subprocess.run(
        ['ros2', 'param', 'set', MISSION_NODE,
         'low_battery_threshold', str(TRIGGER_THRESHOLD)],
        capture_output=True, text=True, timeout=5,
    )
    if r.returncode != 0:
        print(f'\033[31mFAIL: param set failed:\n{r.stderr}\033[0m')
        return 1
    print('[T09] Param set. Waiting for guidance PHASE_RETURN (mission_node 2Hz timer)...')

    if not ev_return.wait(15):
        print('\033[31mFAIL: guidance did not enter RETURN phase within 15s\033[0m')
        return 1

    print('\033[32mPASS: T09 low battery failsafe → guidance PHASE_RETURN\033[0m')
    subprocess.run(
        ['ros2', 'param', 'set', MISSION_NODE, 'low_battery_threshold', '0.20'],
        capture_output=True, timeout=5)
    return 0


if __name__ == '__main__':
    sys.exit(_ros_harness.run('t09_low_battery', _run))
