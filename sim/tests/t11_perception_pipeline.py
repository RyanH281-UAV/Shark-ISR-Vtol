#!/usr/bin/env python3
"""
T11 — Perception pipeline: mock_camera_node → detector_node → guidance SEARCH→TRACK
Source: sim/tests/t11_perception_pipeline.py

Verify the full perception chain without test-side Detection injection:
  mock_camera_node publishes /camera/image_raw → detector_node (use_sim:=true)
  probabilistically emits Detection (conf=0.75, prob=0.02/frame @ 10 Hz) →
  guidance _cb_detection fires → PHASE_TRACK.

At 0.02 × 10 Hz the expected time-to-first-detection ≈ 5 s; P(none in 60 s) ≈ 5e-6.

Requires (separate terminals, workspace sourced):
  - run_sim.sh running
  - ros2 launch shark_isr_autopilot autopilot.launch.py
  - ros2 launch shark_isr_guidance guidance.launch.py
  - ros2 launch shark_isr_mission mission.launch.py
  - ros2 launch shark_isr_perception perception.launch.py use_sim:=true

Run:
  source ros2_ws/install/setup.bash
  python3 sim/tests/t11_perception_pipeline.py
"""

import sys, threading, time
import rclpy
import _ros_harness
from rclpy.node import Node

from shark_isr_interfaces.msg import Detection, SearchState, VehicleState
from shark_isr_interfaces.srv import MissionCommand

SEARCH_LAT = -31.998
SEARCH_LON = 115.748
OVERALL_TIMEOUT = 180.0  # generous — SEARCH convergence + up to 60 s for first detection

PHASE_LABELS = {
    SearchState.PHASE_IDLE:    'IDLE',
    SearchState.PHASE_TRANSIT: 'TRANSIT',
    SearchState.PHASE_SEARCH:  'SEARCH',
    SearchState.PHASE_TRACK:   'TRACK',
    SearchState.PHASE_RETURN:  'RETURN',
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
    det_count = [0]
    first_det: list[Detection] = []

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
            print(f'[T11] SearchState → {PHASE_LABELS.get(p, p)}')
        if p == SearchState.PHASE_SEARCH:
            ev['search'].set()
        elif p == SearchState.PHASE_TRACK:
            ev['track'].set()
        elif p == SearchState.PHASE_RETURN:
            ev['return'].set()

    def cb_det(msg: Detection) -> None:
        det_count[0] += 1
        if not first_det:
            first_det.append(msg)
            print(f'[T11] First Detection from detector_node: '
                  f'conf={msg.confidence:.2f} geo_valid={msg.geo_valid}')

    node.create_subscription(VehicleState, 'vehicle_state', cb_vs, 10)
    node.create_subscription(SearchState, 'search_state', cb_ss, 10)
    node.create_subscription(Detection, 'detection', cb_det, 10)

    cli = node.create_client(MissionCommand, 'mission_command')
    if not cli.wait_for_service(timeout_sec=10.0):
        print('\033[31mFAIL: mission_command not available\033[0m')
        return 1

    mission_started = False

    def _abort_mission() -> None:
        """Best-effort CMD_RETURN so the vehicle lands and mission reaches IDLE for next run."""
        if not mission_started:
            return
        resp = _call_mc(cli, MissionCommand.Request.CMD_RETURN)
        if resp is not None and resp.accepted:
            ev['return'].wait(15)

    def remaining() -> float:
        return OVERALL_TIMEOUT - (time.monotonic() - t_start)

    def timed_out(step: str) -> bool:
        if remaining() <= 0:
            print(f'\033[31mFAIL: overall {OVERALL_TIMEOUT:.0f}s timeout at step "{step}"\033[0m')
            return True
        return False

    print('[T11] Waiting for mission PHASE_IDLE (previous test may have left mission active)...')
    if not ev['idle'].wait(120):
        print('\033[31mFAIL: mission did not reach IDLE within 120s\033[0m')
        return 1

    print('[T11] CMD_START (retrying until GPS position valid)...')
    for attempt in range(10):
        resp = _call_mc(cli, MissionCommand.Request.CMD_START,
                        search_lat_deg=SEARCH_LAT, search_lon_deg=SEARCH_LON,
                        search_radius_m=100.0, transit_alt_amsl_m=30.0,
                        search_alt_amsl_m=30.0, orbit_radius_m=30.0)
        if resp is not None and resp.accepted:
            mission_started = True
            break
        reason = resp.reason if resp else 'timeout'
        print(f'[T11]   attempt {attempt + 1}/10: {reason}')
        time.sleep(3)
        if timed_out('CMD_START'):
            return 1
    else:
        print('\033[31mFAIL: CMD_START never accepted\033[0m')
        return 1

    print('[T11] Waiting for ARM...')
    if not ev['armed'].wait(min(30, remaining())):
        print('\033[31mFAIL: vehicle not armed within 30s\033[0m')
        _abort_mission()
        return 1
    print(f'[T11] Armed at t+{time.monotonic() - t_start:.1f}s')

    print('[T11] Waiting for OFFBOARD...')
    if not ev['offboard'].wait(min(30, remaining())):
        print('\033[31mFAIL: OFFBOARD not active within 30s\033[0m')
        _abort_mission()
        return 1
    print(f'[T11] Offboard at t+{time.monotonic() - t_start:.1f}s')

    # Don't gate on PHASE_SEARCH published state — the 2Hz search_state timer can
    # miss the SEARCH→TRACK transition if a Detection arrives in the same tick.
    # Guidance still enforces the guard internally; TRACK arriving proves SEARCH happened.
    print('[T11] Waiting for PHASE_TRACK (detector_node driving — no test injection)...')
    if not ev['track'].wait(min(120, remaining())):
        print(f'\033[31mFAIL: did not enter TRACK within 120s '
              f'(detections so far: {det_count[0]})\033[0m')
        _abort_mission()
        return 1
    print(f'[T11] TRACK at t+{time.monotonic() - t_start:.1f}s '
          f'(detections received: {det_count[0]})')

    if det_count[0] < 1:
        print('\033[31mFAIL: TRACK reached but no Detection messages observed '
              '— guidance may have been triggered by something else\033[0m')
        _abort_mission()
        return 1

    elapsed = time.monotonic() - t_start
    print(f'[T11] Phases visited: {[PHASE_LABELS.get(p, p) for p in phases_seen]}')
    print(f'[T11] Elapsed: {elapsed:.1f}s')
    print('\033[32mPASS: T11 perception pipeline → TRACK\033[0m')
    print('[T11] CMD_RETURN (cleanup)...')
    _abort_mission()
    return 0


if __name__ == '__main__':
    sys.exit(_ros_harness.run('t11_perception', _run))
