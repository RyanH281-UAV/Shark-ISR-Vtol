#!/usr/bin/env python3
"""
T10 — End-to-end mission rehearsal
Source: sim/tests/t10_e2e_rehearsal.py

Full pipeline: CMD_START → ARM → OFFBOARD → SEARCH → inject Detection
               → TRACK → CMD_RETURN → PHASE_RETURN.

Uses SITL home as the search location so transit target ENU ≈ (0,0) →
guidance arrival is immediate (dist < arrival_threshold_m=15m). Detection
is injected with geo_valid=False so guidance places the orbit centre at the
vehicle's current position.

Requires (full stack, separate terminals, workspace sourced):
  - run_sim.sh running
  - ros2 launch shark_isr_autopilot autopilot.launch.py
  - ros2 launch shark_isr_guidance guidance.launch.py
  - ros2 launch shark_isr_mission mission.launch.py

Run:
  source ros2_ws/install/setup.bash
  python3 sim/tests/t10_e2e_rehearsal.py

Overall timeout: 120 s
"""

import sys, threading, time
import rclpy
import _ros_harness
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, DurabilityPolicy, HistoryPolicy
from std_msgs.msg import Header

from shark_isr_interfaces.msg import Detection, SearchState, VehicleState
from shark_isr_interfaces.srv import MissionCommand
from px4_msgs.msg import VehicleStatus

PX4_QOS = QoSProfile(
    reliability=ReliabilityPolicy.BEST_EFFORT,
    durability=DurabilityPolicy.VOLATILE,
    history=HistoryPolicy.KEEP_LAST,
    depth=1,
)
SEARCH_LAT = -31.998    # SITL home (Cottesloe Beach, Perth WA)
SEARCH_LON = 115.748
OVERALL_TIMEOUT = 120   # s

PHASE_LABELS = {
    SearchState.PHASE_IDLE: 'IDLE',
    SearchState.PHASE_TRANSIT: 'TRANSIT',
    SearchState.PHASE_SEARCH: 'SEARCH',
    SearchState.PHASE_TRACK: 'TRACK',
    SearchState.PHASE_RETURN: 'RETURN',
}


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
    t_start = time.monotonic()
    phases_seen: list[int] = []
    ev = {k: threading.Event() for k in ('idle', 'armed', 'offboard', 'search', 'track', 'return')}

    def cb_vs(msg: VehicleState) -> None:
        if msg.armed:
            ev['armed'].set()
        if msg.offboard_active:
            ev['offboard'].set()

    def cb_ss(msg: SearchState) -> None:
        p = msg.phase
        if p == SearchState.PHASE_IDLE:
            ev['idle'].set()
        if p not in phases_seen:
            phases_seen.append(p)
            print(f'[T10] SearchState → {PHASE_LABELS.get(p, p)}')
        if p == SearchState.PHASE_SEARCH:
            ev['search'].set()
        elif p == SearchState.PHASE_TRACK:
            ev['track'].set()
        elif p == SearchState.PHASE_RETURN:
            ev['return'].set()

    node.create_subscription(VehicleState, 'vehicle_state', cb_vs, 10)
    node.create_subscription(SearchState, 'search_state', cb_ss, 10)
    pub_det = node.create_publisher(Detection, 'detection', 10)

    cli = node.create_client(MissionCommand, 'mission_command')
    if not cli.wait_for_service(timeout_sec=10.0):
        print('\033[31mFAIL: mission_command not available\033[0m')
        return 1

    def remaining() -> float:
        return OVERALL_TIMEOUT - (time.monotonic() - t_start)

    def timed_out(step: str) -> bool:
        if remaining() <= 0:
            print(f'\033[31mFAIL: overall {OVERALL_TIMEOUT}s timeout at step "{step}"\033[0m')
            return True
        return False

    print('[T10] Waiting for mission PHASE_IDLE (previous test may have left mission active)...')
    if not ev['idle'].wait(120):
        print('\033[31mFAIL: mission did not reach IDLE within 120s\033[0m')
        return 1

    print('[T10] CMD_START (retrying until GPS position valid)...')
    for attempt in range(10):
        resp = _call_mc(cli, MissionCommand.Request.CMD_START,
                        search_lat_deg=SEARCH_LAT, search_lon_deg=SEARCH_LON,
                        search_radius_m=100.0, transit_alt_amsl_m=30.0,
                        search_alt_amsl_m=30.0, orbit_radius_m=30.0)
        if resp is not None and resp.accepted:
            break
        reason = resp.reason if resp else 'timeout'
        print(f'[T10]   attempt {attempt + 1}/10: {reason}')
        time.sleep(3)
        if timed_out('CMD_START'):
            return 1
    else:
        print('\033[31mFAIL: CMD_START never accepted\033[0m')
        return 1

    print('[T10] Waiting for ARM...')
    if not ev['armed'].wait(min(30, remaining())):
        print('\033[31mFAIL: vehicle not armed within 30s\033[0m')
        return 1
    if timed_out('arm'):
        return 1
    print(f'[T10] Armed at t+{time.monotonic() - t_start:.1f}s')

    print('[T10] Waiting for OFFBOARD...')
    if not ev['offboard'].wait(min(30, remaining())):
        print('\033[31mFAIL: OFFBOARD not active within 30s\033[0m')
        return 1
    if timed_out('offboard'):
        return 1
    print(f'[T10] Offboard at t+{time.monotonic() - t_start:.1f}s')

    print('[T10] Waiting for PHASE_SEARCH...')
    if not ev['search'].wait(min(30, remaining())):
        print('\033[31mFAIL: did not reach SEARCH within 30s\033[0m')
        return 1
    if timed_out('search'):
        return 1
    print(f'[T10] Search at t+{time.monotonic() - t_start:.1f}s')

    time.sleep(1.0)
    print('[T10] Injecting Detection (geo_valid=False → orbit at vehicle pos)...')
    det = Detection()
    det.header = Header(frame_id='camera_optical')
    det.object_class = Detection.CLASS_SHARK
    det.confidence = 0.95
    det.bbox_x_min, det.bbox_y_min = 0.4, 0.4
    det.bbox_x_max, det.bbox_y_max = 0.6, 0.6
    det.geo_valid = False
    for _ in range(5):
        det.header.stamp = node.get_clock().now().to_msg()
        pub_det.publish(det)
        time.sleep(0.1)

    print('[T10] Waiting for PHASE_TRACK...')
    if not ev['track'].wait(min(15, remaining())):
        print('\033[31mFAIL: did not enter TRACK within 15s of injection\033[0m')
        return 1
    if timed_out('track'):
        return 1
    print(f'[T10] Tracking at t+{time.monotonic() - t_start:.1f}s')

    time.sleep(2.0)
    print('[T10] CMD_RETURN...')
    resp = _call_mc(cli, MissionCommand.Request.CMD_RETURN)
    if resp is None or not resp.accepted:
        print('\033[31mFAIL: CMD_RETURN rejected\033[0m')
        return 1

    print('[T10] Waiting for PHASE_RETURN...')
    if not ev['return'].wait(min(15, remaining())):
        print('\033[31mFAIL: guidance did not enter RETURN within 15s\033[0m')
        return 1

    elapsed = time.monotonic() - t_start
    print(f'[T10] Phases visited: {[PHASE_LABELS.get(p, p) for p in phases_seen]}')
    print(f'[T10] Elapsed: {elapsed:.1f}s')
    print('\033[32mPASS: T10 end-to-end mission rehearsal\033[0m')
    return 0


if __name__ == '__main__':
    sys.exit(_ros_harness.run('t10_e2e', _run))
