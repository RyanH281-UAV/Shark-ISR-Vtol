"""
telemetry_node.py — Structured logging and operator summary relay.

Responsibilities
----------------
- Write three JSONL log files (flight state, detections, events) to log_dir.
- Publish a 1-line human-readable summary on /telemetry_summary at summary_hz.
- Log every phase transition and detection as an event record.

Log file format: one JSON object per line (JSONL), UTF-8, named by session start time.
  flight_YYYYMMDD_HHMMSS.jsonl  — periodic vehicle state at flight_log_hz
  detections_YYYYMMDD_HHMMSS.jsonl — every Detection message (with geo fields)
  events_YYYYMMDD_HHMMSS.jsonl  — phase changes and notable state transitions

Subscriptions
-------------
  /vehicle_state    VehicleState   — autopilot bridge telemetry
  /search_state     SearchState    — guidance layer state
  /detections       Detection      — perception detections

Publications
------------
  /telemetry_summary  std_msgs/String  — 1-Hz human-readable status line

No GCS RF transport: that is the autopilot bridge's responsibility.
"""

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import rclpy
from rclpy.node import Node
from std_msgs.msg import String

from shark_isr_interfaces.msg import Detection, SearchState, VehicleState

_PHASE_NAMES = {
    SearchState.PHASE_IDLE: 'IDLE',
    SearchState.PHASE_TRANSIT: 'TRANSIT',
    SearchState.PHASE_SEARCH: 'SEARCH',
    SearchState.PHASE_TRACK: 'TRACK',
    SearchState.PHASE_RETURN: 'RETURN',
}

_VTOL_NAMES = {
    VehicleState.VTOL_PHASE_UNDEFINED: 'UNDEF',
    VehicleState.VTOL_PHASE_HOVER: 'HOVER',
    VehicleState.VTOL_PHASE_TRANS_TO_FW: 'TRANS→FW',
    VehicleState.VTOL_PHASE_TRANS_TO_MC: 'TRANS→MC',
    VehicleState.VTOL_PHASE_FIXED_WING: 'FW',
}


class TelemetryNode(Node):
    """Logs flight data + detections; publishes operator summary."""

    def __init__(self) -> None:
        super().__init__('telemetry_node')

        # ── Parameters ────────────────────────────────────────────────────────
        self.declare_parameter('log_dir', '/tmp/shark_isr_logs')
        self.declare_parameter('flight_log_hz', 1.0)
        self.declare_parameter('summary_hz', 1.0)

        log_dir = Path(self.get_parameter('log_dir').value)
        flight_hz = float(self.get_parameter('flight_log_hz').value)
        summary_hz = float(self.get_parameter('summary_hz').value)

        # ── Session timestamp (used to name log files) ────────────────────────
        session_ts = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')
        log_dir.mkdir(parents=True, exist_ok=True)

        self._f_flight = self._open_log(log_dir / f'flight_{session_ts}.jsonl')
        self._f_detect = self._open_log(log_dir / f'detections_{session_ts}.jsonl')
        self._f_events = self._open_log(log_dir / f'events_{session_ts}.jsonl')

        self.get_logger().info(f'Logging to {log_dir}/ (session {session_ts})')

        # ── State ──────────────────────────────────────────────────────────────
        self._vehicle: Optional[VehicleState] = None
        self._search: Optional[SearchState] = None
        self._last_phase: Optional[int] = None  # detect transitions
        self._detection_count: int = 0

        # ── Subscribers ────────────────────────────────────────────────────────
        self.create_subscription(
            VehicleState, 'vehicle_state', self._cb_vehicle, 10)
        self.create_subscription(
            SearchState, 'search_state', self._cb_search_state, 10)
        self.create_subscription(
            Detection, 'detection', self._cb_detection, 10)

        # ── Publisher ──────────────────────────────────────────────────────────
        self._pub_summary = self.create_publisher(String, 'telemetry_summary', 10)

        # ── Timers ─────────────────────────────────────────────────────────────
        self.create_timer(1.0 / flight_hz, self._timer_flight_log)
        self.create_timer(1.0 / summary_hz, self._timer_summary)

        self._log_event('session_start', {'session': session_ts, 'log_dir': str(log_dir)})
        self.get_logger().info('telemetry_node started')

    # ── Subscriber callbacks ──────────────────────────────────────────────────

    def _cb_vehicle(self, msg: VehicleState) -> None:
        self._vehicle = msg

    def _cb_search_state(self, msg: SearchState) -> None:
        if self._last_phase is not None and msg.phase != self._last_phase:
            old_name = _PHASE_NAMES.get(self._last_phase, str(self._last_phase))
            new_name = _PHASE_NAMES.get(msg.phase, str(msg.phase))
            self.get_logger().info(f'Phase transition: {old_name} → {new_name}')
            self._log_event('phase_transition', {
                'from': old_name,
                'to': new_name,
                'coverage': msg.coverage_fraction,
                'time_on_station_s': msg.time_on_station_s,
            })
        self._last_phase = msg.phase
        self._search = msg

    def _cb_detection(self, msg: Detection) -> None:
        self._detection_count += 1
        record: dict = {
            'ts': msg.header.stamp.sec + msg.header.stamp.nanosec * 1e-9,
            'confidence': round(msg.confidence, 4),
            'class': msg.object_class,
            'geo_valid': msg.geo_valid,
            'bbox': [
                round(msg.bbox_x_min, 4),
                round(msg.bbox_y_min, 4),
                round(msg.bbox_x_max, 4),
                round(msg.bbox_y_max, 4),
            ],
        }
        if msg.geo_valid:
            record['lat_deg'] = round(msg.latitude_deg, 7)
            record['lon_deg'] = round(msg.longitude_deg, 7)
            record['pos_std_m'] = round(msg.position_std_m, 2)
        self._write(self._f_detect, record)

        if msg.geo_valid:
            self.get_logger().info(
                f'Detection #{self._detection_count}: conf={msg.confidence:.2f} '
                f'lat={msg.latitude_deg:.5f} lon={msg.longitude_deg:.5f} '
                f'±{msg.position_std_m:.0f}m')
        else:
            self.get_logger().info(
                f'Detection #{self._detection_count}: conf={msg.confidence:.2f} (geo invalid)')

    # ── Timers ────────────────────────────────────────────────────────────────

    def _timer_flight_log(self) -> None:
        if self._vehicle is None:
            return
        v = self._vehicle
        record: dict = {
            'ts': v.header.stamp.sec + v.header.stamp.nanosec * 1e-9,
            'lat_deg': round(v.latitude_deg, 7),
            'lon_deg': round(v.longitude_deg, 7),
            'alt_amsl_m': round(v.altitude_amsl_m, 1),
            'agl_m': round(v.agl_m, 1),
            'gs_m_s': round(v.groundspeed_m_s, 2),
            'batt': round(v.battery_fraction, 3),
            'batt_v': round(v.battery_voltage_v, 2),
            'vtol': _VTOL_NAMES.get(v.vtol_phase, str(v.vtol_phase)),
            'armed': v.armed,
            'offboard': v.offboard_active,
        }
        if self._search is not None:
            record['phase'] = _PHASE_NAMES.get(self._search.phase, str(self._search.phase))
            record['coverage'] = round(self._search.coverage_fraction, 4)
        self._write(self._f_flight, record)

    def _timer_summary(self) -> None:
        parts: list[str] = []

        if self._vehicle is not None:
            v = self._vehicle
            vtol = _VTOL_NAMES.get(v.vtol_phase, '?')
            batt_pct = int(v.battery_fraction * 100)
            parts.append(
                f'POS lat={v.latitude_deg:.4f} lon={v.longitude_deg:.4f} '
                f'alt={v.altitude_amsl_m:.0f}m agl={v.agl_m:.0f}m '
                f'gs={v.groundspeed_m_s:.1f}m/s {vtol} batt={batt_pct}%'
            )
        else:
            parts.append('POS: no vehicle state')

        if self._search is not None:
            s = self._search
            phase = _PHASE_NAMES.get(s.phase, '?')
            parts.append(
                f'PHASE={phase} cov={s.coverage_fraction:.1%} '
                f't={s.time_on_station_s:.0f}s dets={self._detection_count}'
            )
        else:
            parts.append('GUIDANCE: no data')

        msg = String()
        msg.data = ' | '.join(parts)
        self._pub_summary.publish(msg)

    # ── Log helpers ───────────────────────────────────────────────────────────

    def _log_event(self, event_type: str, data: dict) -> None:
        record = {'ts': time.time(), 'event': event_type, **data}
        self._write(self._f_events, record)

    @staticmethod
    def _open_log(path: Path):
        return open(path, 'a', encoding='utf-8', buffering=1)  # line-buffered

    @staticmethod
    def _write(f, record: dict) -> None:
        f.write(json.dumps(record, separators=(',', ':')) + '\n')

    def destroy_node(self) -> None:
        self._log_event('session_end', {})
        for f in (self._f_flight, self._f_detect, self._f_events):
            try:
                f.close()
            except Exception:
                pass
        super().destroy_node()


def main(args=None) -> None:
    rclpy.init(args=args)
    node = TelemetryNode()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()
