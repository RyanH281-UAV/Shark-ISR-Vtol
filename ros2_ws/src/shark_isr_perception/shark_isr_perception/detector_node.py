"""
detector_node.py — Camera ingest + Hailo-8L inference + geolocation.

Subscribes:
  /camera/image_raw   (sensor_msgs/Image)      — frames from picamera2 or mock_camera_node
  /camera/camera_info (sensor_msgs/CameraInfo) — intrinsics (ADR-018: single source of
                                                  truth, not our own fx/fy/cx/cy copy)
  /vehicle_state      (VehicleState)           — from shark_isr_autopilot

Publishes:
  /detection          (Detection)           — geolocated shark detections

Parameters (all in config/perception.yaml):
  use_sim              bool   — if true, use mock probabilistic detections (no HailoRT)
  hef_path             str    — path to Hailo .hef model file (real mode only)
  confidence_threshold float  — minimum HailoRT score to publish [0..1]
  mock_detection_prob  float  — per-frame probability of mock detection in sim mode

Sim mode
--------
  use_sim:=true  → detector_node subscribes to /camera/image_raw but does not load
  HailoRT.  Instead it generates a probabilistic mock detection at mock_detection_prob
  probability per received frame, at a fixed bbox and confidence value.  This exercises
  the full Detection → guidance pipeline without hardware.

Real mode
---------
  use_sim:=false → detector_node loads the .hef at hef_path via the hailo Python
  bindings (hailort), runs synchronous inference per frame, and publishes real
  detections.  HailoRT is imported lazily so the package builds on non-Pi hardware.
"""

from __future__ import annotations

import random
from typing import Optional

import numpy as np
import rclpy
from rcl_interfaces.msg import SetParametersResult
from rclpy.node import Node
from sensor_msgs.msg import CameraInfo, Image
from std_msgs.msg import Header

from shark_isr_interfaces.msg import Detection, VehicleState

from .geolocate import geolocate


class DetectorNode(Node):
    def __init__(self) -> None:
        super().__init__("detector_node")

        self.declare_parameter("use_sim", True)
        self.declare_parameter("hef_path", "")
        self.declare_parameter("confidence_threshold", 0.45)
        self.declare_parameter("mock_detection_prob", 0.02)
        # Frames a mock detection persists once triggered. A real target stays
        # in the footprint for ~2-3 s of frames, and the guidance confidence
        # gate (ADR-016) requires sustained evidence — a single mock frame
        # would (correctly) never transition.
        self.declare_parameter("mock_burst_frames", 30)

        self._use_sim: bool = self.get_parameter("use_sim").value
        self._conf_thresh: float = self.get_parameter("confidence_threshold").value
        self._mock_prob: float = self.get_parameter("mock_detection_prob").value
        self._mock_burst_frames: int = self.get_parameter("mock_burst_frames").value
        self._mock_burst_remaining: int = 0

        # mock_detection_prob/mock_burst_frames must be live-tunable: `ros2
        # param set` on this node otherwise "succeeds" (the parameter server
        # accepts it) while _run_sim_detection keeps using the __init__-time
        # cached value forever — a silent no-op a caller has no way to detect.
        self.add_on_set_parameters_callback(self._on_params_change)

        self._vehicle_state: Optional[VehicleState] = None
        # Intrinsics (ADR-018): read from CameraInfo, not our own params — both
        # camera_node and mock_camera_node already publish it, so this was the
        # third independent copy of fx/fy/cx/cy/width/height with nothing
        # enforcing agreement. None until the first CameraInfo arrives, which
        # means any detection in the ~1 camera-frame startup window is (not
        # silently) marked geo_valid=False by the info-is-None guard below —
        # the same bounded cold-start gap that already existed for a missing
        # vehicle_state, just with one more topic that has to arrive first.
        self._camera_info: Optional[CameraInfo] = None
        self._hailo_infer = None  # set in _init_hailo()

        self._det_pub = self.create_publisher(Detection, "detection", 10)

        self.create_subscription(Image, "camera/image_raw", self._image_cb, 10)
        self.create_subscription(VehicleState, "vehicle_state", self._state_cb, 10)
        self.create_subscription(CameraInfo, "camera/camera_info", self._camera_info_cb, 10)

        if not self._use_sim:
            self._init_hailo()
        else:
            self.get_logger().info("DetectorNode: SIM mode — probabilistic mock detections.")

    # ------------------------------------------------------------------ #
    # Subscriptions

    def _state_cb(self, msg: VehicleState) -> None:
        self._vehicle_state = msg

    def _camera_info_cb(self, msg: CameraInfo) -> None:
        self._camera_info = msg

    def _on_params_change(self, params) -> SetParametersResult:
        for p in params:
            if p.name == "mock_detection_prob":
                self._mock_prob = p.value
                # A burst already in flight (self._mock_burst_remaining > 0)
                # is independent of mock_prob and would otherwise keep firing
                # up to mock_burst_frames more detections regardless of this
                # change — muting has to mean "stop now", not just "stop
                # starting new ones". Cancel it outright rather than only on
                # value==0: a caller lowering the rate mid-burst means it too.
                self._mock_burst_remaining = 0
            elif p.name == "mock_burst_frames":
                self._mock_burst_frames = p.value
        return SetParametersResult(successful=True)

    def _image_cb(self, msg: Image) -> None:
        if self._use_sim:
            self._run_sim_detection(msg.header.stamp)
        else:
            self._run_hailo_detection(msg)

    # ------------------------------------------------------------------ #
    # Sim mode

    def _run_sim_detection(self, stamp) -> None:
        # A trigger starts a burst: the mock target stays "in view" for
        # mock_burst_frames consecutive frames, like a real overflight.
        if self._mock_burst_remaining > 0:
            self._mock_burst_remaining -= 1
        elif random.random() <= self._mock_prob:
            self._mock_burst_remaining = max(0, self._mock_burst_frames - 1)
        else:
            return

        # Publish a mock detection near image centre with some jitter
        det = Detection()
        det.header = Header()
        det.header.stamp = stamp
        det.header.frame_id = "camera_optical"
        det.object_class = Detection.CLASS_SHARK
        # Hardcoded above guidance's detection_confidence_threshold (0.70,
        # shark_isr_guidance/config/guidance.yaml) by a fixed 0.05 margin —
        # a silent cross-package coupling. Raising that threshold above 0.75
        # makes every sim detection silently invisible to guidance.
        det.confidence = 0.75

        jitter = 0.05
        cx = 0.5 + random.uniform(-jitter, jitter)
        cy = 0.5 + random.uniform(-jitter, jitter)
        hw = 0.04
        det.bbox_x_min = float(cx - hw)
        det.bbox_y_min = float(cy - hw)
        det.bbox_x_max = float(cx + hw)
        det.bbox_y_max = float(cy + hw)

        self._fill_geolocation(det, cx, cy)
        self._det_pub.publish(det)
        self.get_logger().debug(
            f"Mock detection: conf={det.confidence:.2f} geo_valid={det.geo_valid}"
        )

    # ------------------------------------------------------------------ #
    # Real Hailo mode

    def _init_hailo(self) -> None:
        hef_path = self.get_parameter("hef_path").value
        if not hef_path:
            self.get_logger().error("hef_path is empty — cannot load model.")
            return
        try:
            from hailo_platform import (  # type: ignore
                HEF,
                VDevice,
                HailoStreamInterface,
                InferVStreams,
                ConfigureParams,
                InputVStreamParams,
                OutputVStreamParams,
                FormatType,
            )

            hef = HEF(hef_path)
            target = VDevice()
            configure_params = ConfigureParams.create_from_hef(
                hef=hef, interface=HailoStreamInterface.PCIe
            )
            network_groups = target.configure(hef, configure_params)
            network_group = network_groups[0]
            # BUG (B08 bench item, not fixed here — needs real HailoRT to
            # verify): stored but never used. HailoRT requires
            # `with network_group.activate(network_group_params):` around the
            # InferVStreams call in _hailo_forward; without it, inference below
            # is expected to fail once a real .hef is loaded.
            network_group_params = network_group.create_params()

            input_params = InputVStreamParams.make(
                network_group, format_type=FormatType.FLOAT32
            )
            output_params = OutputVStreamParams.make(
                network_group, format_type=FormatType.FLOAT32
            )

            self._hailo_target = target
            self._hailo_ng = network_group
            self._hailo_ng_params = network_group_params
            self._hailo_input_params = input_params
            self._hailo_output_params = output_params
            self._hailo_infer = InferVStreams
            self.get_logger().info(f"Hailo .hef loaded: {hef_path}")
        except Exception as exc:
            self.get_logger().error(f"Failed to initialise HailoRT: {exc}")

    def _run_hailo_detection(self, msg: Image) -> None:
        if self._hailo_infer is None:
            return

        try:
            frame = self._decode_image(msg)
            detections = self._hailo_forward(frame)
        except Exception as exc:
            self.get_logger().warn(f"Hailo inference failed: {exc}")
            return

        for bbox, conf in detections:
            det = Detection()
            det.header = msg.header
            det.object_class = Detection.CLASS_SHARK
            det.confidence = float(conf)
            x_min, y_min, x_max, y_max = bbox
            det.bbox_x_min = float(x_min)
            det.bbox_y_min = float(y_min)
            det.bbox_x_max = float(x_max)
            det.bbox_y_max = float(y_max)

            cx = (x_min + x_max) / 2.0
            cy = (y_min + y_max) / 2.0
            self._fill_geolocation(det, cx, cy)
            self._det_pub.publish(det)

    def _decode_image(self, msg: Image) -> np.ndarray:
        data = np.frombuffer(bytes(msg.data), dtype=np.uint8)
        arr = data.reshape((msg.height, msg.width, 3))
        return arr.astype(np.float32) / 255.0

    _MODEL_SIZE = 640  # .hef input side (square)

    def _letterbox(self, frame: np.ndarray) -> tuple[np.ndarray, float, int, int]:
        """Scale-preserving resize onto a 640×640 canvas (grey pad).

        Returns (canvas, scale, pad_x, pad_y) so detections can be mapped back.
        A plain cv2.resize would stretch 640×480 by 1.33× vertically — every
        bbox (and the geolocation ray derived from it) would be distorted.
        """
        import cv2  # type: ignore  # required in real mode; fail loudly if absent

        h, w = frame.shape[:2]
        s = self._MODEL_SIZE / max(h, w)
        nw, nh = round(w * s), round(h * s)
        canvas = np.full(
            (self._MODEL_SIZE, self._MODEL_SIZE, 3), 0.447, dtype=frame.dtype)
        pad_x = (self._MODEL_SIZE - nw) // 2
        pad_y = (self._MODEL_SIZE - nh) // 2
        canvas[pad_y:pad_y + nh, pad_x:pad_x + nw] = cv2.resize(frame, (nw, nh))
        return canvas, s, pad_x, pad_y

    def _hailo_forward(self, frame: np.ndarray) -> list:
        """Run HailoRT inference; return list of (bbox_norm, confidence),
        bboxes normalised to the ORIGINAL frame (letterbox removed)."""
        img_h, img_w = frame.shape[:2]
        canvas, scale, pad_x, pad_y = self._letterbox(frame)

        input_data = {
            list(self._hailo_input_params.keys())[0]: np.expand_dims(canvas, 0)
        }

        with self._hailo_infer(
            self._hailo_ng,
            self._hailo_input_params,
            self._hailo_output_params,
        ) as infer_pipeline:
            infer_pipeline.infer(input_data)
            output = infer_pipeline.get_output()

        # Parse output — format depends on the .hef model (YOLO-style: cx,cy,w,h,conf,class...)
        # This is a placeholder; adapt to the actual model output layer shape
        # on the bench (HARDWARE_BRINGUP B08) before real use.
        def unletterbox(v: float, pad: int, dim: int) -> float:
            """Canvas-normalised coord → original-frame-normalised coord."""
            px = v * self._MODEL_SIZE            # canvas pixels
            return min(1.0, max(0.0, (px - pad) / scale / dim))

        results = []
        for layer in output.values():
            arr = np.array(layer).flatten()
            # Example: assume flat [x1, y1, x2, y2, conf, class_id, ...] per detection,
            # coords normalised to the 640×640 letterboxed canvas.
            stride = 6
            for i in range(0, len(arr) - stride + 1, stride):
                conf = float(arr[i + 4])
                cls = int(arr[i + 5])
                if cls == 0 and conf >= self._conf_thresh:
                    bbox = (
                        unletterbox(float(arr[i]), pad_x, img_w),
                        unletterbox(float(arr[i + 1]), pad_y, img_h),
                        unletterbox(float(arr[i + 2]), pad_x, img_w),
                        unletterbox(float(arr[i + 3]), pad_y, img_h),
                    )
                    results.append((bbox, conf))
        return results

    # ------------------------------------------------------------------ #
    # Geolocation

    @staticmethod
    def _mark_geo_invalid(det: Detection) -> None:
        det.geo_valid = False
        det.latitude_deg = 0.0
        det.longitude_deg = 0.0
        det.altitude_amsl_m = 0.0
        det.position_std_m = 0.0

    def _fill_geolocation(
        self, det: Detection, bbox_cx_norm: float, bbox_cy_norm: float
    ) -> None:
        vs = self._vehicle_state
        info = self._camera_info
        if vs is None or not vs.agl_valid or vs.agl_m <= 0.0 or info is None:
            self._mark_geo_invalid(det)
            return

        # geolocate() requires NORMALISED bbox centre [0,1] (Detection.msg contract).
        # The Hailo parser (_hailo_forward) is a placeholder; many YOLO/.hef exports
        # emit pixel coords (0..640). If that lands here it would double-scale by img_w
        # and geolocate silently wrong. Reject loudly instead — normalise upstream.
        if not (0.0 <= bbox_cx_norm <= 1.0 and 0.0 <= bbox_cy_norm <= 1.0):
            self.get_logger().error(
                f"bbox centre not normalised ({bbox_cx_norm:.3f}, {bbox_cy_norm:.3f}); "
                "expected [0,1] per Detection.msg — check _hailo_forward output scaling."
            )
            self._mark_geo_invalid(det)
            return

        q = vs.attitude_q
        attitude_qxyzw = (q.x, q.y, q.z, q.w)

        try:
            lat, lon, std = geolocate(
                bbox_cx_norm=bbox_cx_norm,
                bbox_cy_norm=bbox_cy_norm,
                img_w=info.width,
                img_h=info.height,
                fx=info.k[0],
                fy=info.k[4],
                cx=info.k[2],
                cy=info.k[5],
                vehicle_lat_deg=vs.latitude_deg,
                vehicle_lon_deg=vs.longitude_deg,
                agl_m=float(vs.agl_m),
                attitude_qxyzw=attitude_qxyzw,
            )
            det.geo_valid = True
            det.latitude_deg = lat
            det.longitude_deg = lon
            det.altitude_amsl_m = vs.altitude_amsl_m
            det.position_std_m = float(std)
        except ValueError as exc:
            self.get_logger().warn(f"Geolocation failed: {exc}")
            self._mark_geo_invalid(det)


def main(args=None) -> None:
    rclpy.init(args=args)
    node = DetectorNode()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()
