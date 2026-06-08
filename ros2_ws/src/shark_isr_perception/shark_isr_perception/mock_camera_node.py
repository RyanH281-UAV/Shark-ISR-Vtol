"""
mock_camera_node.py — Publishes synthetic camera frames for SITL.

Publishes sensor_msgs/Image on /camera/image_raw and sensor_msgs/CameraInfo on
/camera/camera_info at a configurable frame rate.  If mock_images_dir is set to
a directory containing .png / .jpg files, they are served in a loop; otherwise
random noise frames are generated.

Use this node in simulation (use_sim:=true) so detector_node can be tested end-to-
end without physical hardware.  On real hardware, replace with a picamera2 ROS 2
wrapper.
"""

from __future__ import annotations

import os
import glob as _glob
from pathlib import Path

import numpy as np
import rclpy
from rclpy.node import Node
from sensor_msgs.msg import CameraInfo, Image
from std_msgs.msg import Header


class MockCameraNode(Node):
    def __init__(self) -> None:
        super().__init__("mock_camera_node")

        self.declare_parameter("camera_fps", 10.0)
        self.declare_parameter("image_width", 640)
        self.declare_parameter("image_height", 480)
        self.declare_parameter("mock_images_dir", "")
        # Camera intrinsics — must match detector_node config
        self.declare_parameter("fx", 616.0)
        self.declare_parameter("fy", 616.0)
        self.declare_parameter("cx", 320.0)
        self.declare_parameter("cy", 240.0)

        fps = self.get_parameter("camera_fps").value
        self._w = self.get_parameter("image_width").value
        self._h = self.get_parameter("image_height").value
        images_dir = self.get_parameter("mock_images_dir").value

        self._img_pub = self.create_publisher(Image, "camera/image_raw", 10)
        self._info_pub = self.create_publisher(CameraInfo, "camera/camera_info", 10)

        self._frames: list[np.ndarray] = []
        self._frame_idx = 0
        if images_dir:
            self._load_images(images_dir)

        self._info_msg = self._build_camera_info()

        period = 1.0 / fps
        self.create_timer(period, self._publish_frame)
        self.get_logger().info(
            f"MockCameraNode: {self._w}x{self._h} @ {fps:.1f} Hz, "
            f"{'noise' if not self._frames else str(len(self._frames)) + ' loaded frames'}"
        )

    # ------------------------------------------------------------------ #

    def _load_images(self, directory: str) -> None:
        try:
            import cv2  # type: ignore
        except ImportError:
            self.get_logger().warn("cv2 not available — falling back to noise frames.")
            return

        patterns = ["*.png", "*.jpg", "*.jpeg"]
        paths: list[str] = []
        for pat in patterns:
            paths.extend(sorted(_glob.glob(os.path.join(directory, pat))))

        for p in paths:
            img = cv2.imread(p)
            if img is None:
                continue
            img = cv2.resize(img, (self._w, self._h))
            img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
            self._frames.append(img)

        if not self._frames:
            self.get_logger().warn(f"No images found in {directory!r} — using noise.")

    def _build_camera_info(self) -> CameraInfo:
        fx = self.get_parameter("fx").value
        fy = self.get_parameter("fy").value
        cx = self.get_parameter("cx").value
        cy = self.get_parameter("cy").value

        info = CameraInfo()
        info.width = self._w
        info.height = self._h
        info.distortion_model = "plumb_bob"
        info.d = [0.0, 0.0, 0.0, 0.0, 0.0]
        info.k = [fx, 0.0, cx, 0.0, fy, cy, 0.0, 0.0, 1.0]
        info.r = [1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0]
        info.p = [fx, 0.0, cx, 0.0, 0.0, fy, cy, 0.0, 0.0, 0.0, 1.0, 0.0]
        return info

    def _publish_frame(self) -> None:
        stamp = self.get_clock().now().to_msg()

        header = Header()
        header.stamp = stamp
        header.frame_id = "camera_optical"

        # Build image message
        img_msg = Image()
        img_msg.header = header
        img_msg.width = self._w
        img_msg.height = self._h
        img_msg.encoding = "rgb8"
        img_msg.is_bigendian = False
        img_msg.step = self._w * 3

        if self._frames:
            arr = self._frames[self._frame_idx % len(self._frames)]
            self._frame_idx += 1
        else:
            rng = np.random.default_rng()
            arr = rng.integers(0, 256, (self._h, self._w, 3), dtype=np.uint8)

        img_msg.data = arr.flatten().tolist()
        self._img_pub.publish(img_msg)

        # Camera info shares the same stamp
        self._info_msg.header = header
        self._info_pub.publish(self._info_msg)


def main(args=None) -> None:
    rclpy.init(args=args)
    node = MockCameraNode()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()
