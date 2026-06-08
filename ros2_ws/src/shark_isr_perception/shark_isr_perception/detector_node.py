"""
detector_node.py — Camera ingest + Hailo-8L inference + geolocation.

Subscribes:
  /camera/image_raw   (sensor_msgs/Image)   — frames from picamera2 or mock_camera_node
  /vehicle_state      (VehicleState)        — from shark_isr_autopilot

Publishes:
  /detection          (Detection)           — geolocated shark detections

Parameters (all in config/perception.yaml):
  use_sim              bool   — if true, use mock probabilistic detections (no HailoRT)
  hef_path             str    — path to Hailo .hef model file (real mode only)
  confidence_threshold float  — minimum HailoRT score to publish [0..1]
  mock_detection_prob  float  — per-frame probability of mock detection in sim mode
  image_width          int    — expected image width [px]
  image_height         int    — expected image height [px]
  fx, fy, cx, cy       float  — camera intrinsics [px]

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
from rclpy.node import Node
from sensor_msgs.msg import Image
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
        self.declare_parameter("image_width", 640)
        self.declare_parameter("image_height", 480)
        self.declare_parameter("fx", 616.0)
        self.declare_parameter("fy", 616.0)
        self.declare_parameter("cx", 320.0)
        self.declare_parameter("cy", 240.0)

        self._use_sim: bool = self.get_parameter("use_sim").value
        self._conf_thresh: float = self.get_parameter("confidence_threshold").value
        self._mock_prob: float = self.get_parameter("mock_detection_prob").value
        self._img_w: int = self.get_parameter("image_width").value
        self._img_h: int = self.get_parameter("image_height").value
        self._fx: float = self.get_parameter("fx").value
        self._fy: float = self.get_parameter("fy").value
        self._cx: float = self.get_parameter("cx").value
        self._cy: float = self.get_parameter("cy").value

        self._vehicle_state: Optional[VehicleState] = None
        self._hailo_infer = None  # set in _init_hailo()

        self._det_pub = self.create_publisher(Detection, "detection", 10)

        self.create_subscription(Image, "camera/image_raw", self._image_cb, 10)
        self.create_subscription(VehicleState, "vehicle_state", self._state_cb, 10)

        if not self._use_sim:
            self._init_hailo()
        else:
            self.get_logger().info("DetectorNode: SIM mode — probabilistic mock detections.")

    # ------------------------------------------------------------------ #
    # Subscriptions

    def _state_cb(self, msg: VehicleState) -> None:
        self._vehicle_state = msg

    def _image_cb(self, msg: Image) -> None:
        if self._use_sim:
            self._run_sim_detection(msg.header.stamp)
        else:
            self._run_hailo_detection(msg)

    # ------------------------------------------------------------------ #
    # Sim mode

    def _run_sim_detection(self, stamp) -> None:
        if random.random() > self._mock_prob:
            return

        # Publish a mock detection near image centre with some jitter
        det = Detection()
        det.header = Header()
        det.header.stamp = stamp
        det.header.frame_id = "camera_optical"
        det.object_class = Detection.CLASS_SHARK
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
            self._HEF = HEF
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
            if conf < self._conf_thresh:
                continue

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

    def _hailo_forward(self, frame: np.ndarray) -> list:
        """Run HailoRT inference; return list of (bbox_norm, confidence)."""
        import numpy as np  # noqa: F811

        # Resize to model input (640×640 with letterboxing)
        try:
            import cv2  # type: ignore

            resized = cv2.resize(frame, (640, 640))
        except ImportError:
            resized = frame

        input_data = {
            list(self._hailo_input_params.keys())[0]: np.expand_dims(resized, 0)
        }

        with self._hailo_infer(
            self._hailo_ng,
            self._hailo_input_params,
            self._hailo_output_params,
        ) as infer_pipeline:
            infer_pipeline.infer(input_data)
            output = infer_pipeline.get_output()

        # Parse output — format depends on the .hef model (YOLO-style: cx,cy,w,h,conf,class...)
        # This is a placeholder; adapt to the actual model output layer shape.
        results = []
        for layer in output.values():
            arr = np.array(layer).flatten()
            # Example: assume flat [x1, y1, x2, y2, conf, class_id, ...] per detection
            stride = 6
            for i in range(0, len(arr) - stride + 1, stride):
                conf = float(arr[i + 4])
                cls = int(arr[i + 5])
                if cls == 0 and conf >= self._conf_thresh:
                    bbox = (
                        float(arr[i]),
                        float(arr[i + 1]),
                        float(arr[i + 2]),
                        float(arr[i + 3]),
                    )
                    results.append((bbox, conf))
        return results

    # ------------------------------------------------------------------ #
    # Geolocation

    def _fill_geolocation(
        self, det: Detection, bbox_cx_norm: float, bbox_cy_norm: float
    ) -> None:
        vs = self._vehicle_state
        if vs is None or not vs.agl_valid or vs.agl_m <= 0.0:
            det.geo_valid = False
            det.latitude_deg = 0.0
            det.longitude_deg = 0.0
            det.altitude_amsl_m = 0.0
            det.position_std_m = 0.0
            return

        q = vs.attitude_q
        attitude_qxyzw = (q.x, q.y, q.z, q.w)

        try:
            lat, lon, std = geolocate(
                bbox_cx_norm=bbox_cx_norm,
                bbox_cy_norm=bbox_cy_norm,
                img_w=self._img_w,
                img_h=self._img_h,
                fx=self._fx,
                fy=self._fy,
                cx=self._cx,
                cy=self._cy,
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
            det.geo_valid = False
            det.latitude_deg = 0.0
            det.longitude_deg = 0.0
            det.altitude_amsl_m = 0.0
            det.position_std_m = 0.0


def main(args=None) -> None:
    rclpy.init(args=args)
    node = DetectorNode()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()
