"""
camera_node.py — Real camera frames for hardware (Pi 5 + Camera Module 3).

Hardware counterpart to mock_camera_node. Publishes sensor_msgs/Image on
/camera/image_raw and sensor_msgs/CameraInfo on /camera/camera_info — the exact
same contract detector_node consumes, so nothing downstream changes between sim
and hardware.

Camera capture stays NATIVE on the host (Pi OS), not inside the container:
libcamera/picamera2 in Docker is the Pi-camera pain point, so instead the host
runs rpicam-vid and streams frames over localhost UDP; this node reads that
stream with OpenCV. No libcamera in the container — only OpenCV + ffmpeg.

Host side (Pi OS, native — see docker/README.md):
    rpicam-vid -t 0 --codec mjpeg --width 640 --height 480 \
        --framerate 10 --inline -o 'udp://127.0.0.1:8554'

Then this node (in the Humble container, --network host) reads udp://127.0.0.1:8554.

Timestamp caveat: no capture time crosses the UDP boundary, so frames are stamped
when this node READS them, not when the sensor exposed them. That bias lands in
geolocation (detector_node pairs each frame with the latest vehicle_state). Buffer
depth is pinned to 1 to stop it accumulating — measure the residual at B08.

Params (config/perception.yaml)
-------------------------------
  stream_url    str    — OpenCV-openable source (default udp://127.0.0.1:8554).
                         A device path like /dev/video0 also works for a UVC cam.
  camera_fps    float  — publish rate; the poll rate on the stream.
  image_width   int    — output width  (frame resized to this).
  image_height  int    — output height.
  fx,fy,cx,cy   float  — intrinsics, published in CameraInfo. CALIBRATE on the bench.
"""

from __future__ import annotations

import time

import numpy as np
import rclpy
from rclpy.node import Node
from sensor_msgs.msg import CameraInfo, Image
from std_msgs.msg import Header


def _bgr_frame_to_rgb_bytes(bgr: np.ndarray) -> bytes:
    """OpenCV decodes to BGR; detector_node expects rgb8. Swap channel order.

    ponytail: if colours look inverted on the bench, this swap is the knob —
    some stream/codec paths already hand back RGB. Flip or drop it here.
    """
    return np.ascontiguousarray(bgr[:, :, ::-1]).tobytes()


class CameraNode(Node):
    def __init__(self) -> None:
        super().__init__("camera_node")

        self.declare_parameter("stream_url", "udp://127.0.0.1:8554")
        self.declare_parameter("camera_fps", 10.0)
        self.declare_parameter("image_width", 640)
        self.declare_parameter("image_height", 480)
        # Intrinsics — must match detector_node config.
        self.declare_parameter("fx", 616.0)
        self.declare_parameter("fy", 616.0)
        self.declare_parameter("cx", 320.0)
        self.declare_parameter("cy", 240.0)

        self._url = self.get_parameter("stream_url").value
        fps = self.get_parameter("camera_fps").value
        self._w = self.get_parameter("image_width").value
        self._h = self.get_parameter("image_height").value

        self._img_pub = self.create_publisher(Image, "camera/image_raw", 10)
        self._info_pub = self.create_publisher(CameraInfo, "camera/camera_info", 10)
        self._info_msg = self._build_camera_info()

        # cv2 imported lazily so the package still builds/tests off-Pi (WSL/CI),
        # mirroring detector_node's lazy HailoRT import.
        import cv2  # type: ignore

        self._cv2 = cv2
        self._cap = None
        self._size_warned = False
        self._last_open_attempt = 0.0
        self._open_stream()

        # Poll the stream on a timer — the stream self-paces, so a read() that
        # blocks briefly is fine on the bench. ponytail: single-threaded poll;
        # move to a capture thread only if read latency shows up in B08.
        period = 1.0 / fps
        self.create_timer(period, self._publish_frame)

    # Seconds between reconnect attempts. Each failed attempt costs OPEN_TIMEOUT_MS
    # of blocked executor, so retrying every timer tick (10 Hz) would wedge the node.
    _RETRY_PERIOD_S = 3.0
    _OPEN_TIMEOUT_MS = 2000
    _READ_TIMEOUT_MS = 2000

    def _open_stream(self) -> bool:
        """(Re)open the stream. Returns True if it is now readable.

        Called at startup AND from the timer, because the host rpicam-vid and this
        container start in separate terminals — the stream is very often not up yet
        when the node launches, and it can drop mid-flight. Without the retry the
        node would sit alive and permanently silent after one startup error.

        Rate-limited: opening a dead URL blocks for the full timeout, and with no
        timeouts at all FFMPEG blocks for ~30 s, which hangs the node before it
        ever spins (it can't even be Ctrl-C'd cleanly).
        """
        now = time.monotonic()
        if now - self._last_open_attempt < self._RETRY_PERIOD_S:
            return False
        self._last_open_attempt = now

        if self._cap is not None:
            self._cap.release()

        if "://" in self._url:
            # Network stream: force FFMPEG so the timeout params are honoured.
            self._cap = self._cv2.VideoCapture(
                self._url,
                self._cv2.CAP_FFMPEG,
                [
                    self._cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, self._OPEN_TIMEOUT_MS,
                    self._cv2.CAP_PROP_READ_TIMEOUT_MSEC, self._READ_TIMEOUT_MS,
                ],
            )
        else:
            # Local device path (/dev/videoN) — V4L2, opens immediately.
            self._cap = self._cv2.VideoCapture(self._url)

        if not self._cap.isOpened():
            self.get_logger().error(
                f"Could not open camera stream {self._url!r} — retrying. Is rpicam-vid "
                f"running on the host? (see docker/README.md)",
                throttle_duration_sec=5.0,
            )
            return False

        # Keep one frame in flight. The FFMPEG/UDP backend otherwise queues frames,
        # and that backlog never drains: detector_node geolocates each frame against
        # the LATEST vehicle_state, so read lag converts straight into position error
        # (~10 m per second of lag at cruise, against a 39 m footprint).
        self._cap.set(self._cv2.CAP_PROP_BUFFERSIZE, 1)
        self.get_logger().info(f"CameraNode: streaming from {self._url!r}")
        return True

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
        if not self._cap.isOpened() and not self._open_stream():
            return

        ok, frame = self._cap.read()
        if not ok or frame is None:
            # Publisher went away or the stream stalled — reopen rather than spin
            # silently on a dead handle.
            self.get_logger().warn(
                "Empty frame from stream — reopening.", throttle_duration_sec=5.0
            )
            self._open_stream()
            return

        if frame.shape[1] != self._w or frame.shape[0] != self._h:
            # This resize STRETCHES — it does not preserve aspect. The intrinsics
            # (fx/fy/cx/cy) describe the configured size, so a stream at a different
            # aspect ratio silently skews every bbox and geolocation ray. Fix the
            # rpicam-vid --width/--height to match instead of relying on this.
            if not self._size_warned:
                self.get_logger().warn(
                    f"Stream is {frame.shape[1]}x{frame.shape[0]}, config expects "
                    f"{self._w}x{self._h} — stretching. Intrinsics assume the configured "
                    f"size; match rpicam-vid to it or geolocation will be wrong."
                )
                self._size_warned = True
            frame = self._cv2.resize(frame, (self._w, self._h))

        stamp = self.get_clock().now().to_msg()
        header = Header()
        header.stamp = stamp
        header.frame_id = "camera_optical"

        img_msg = Image()
        img_msg.header = header
        img_msg.width = self._w
        img_msg.height = self._h
        img_msg.encoding = "rgb8"
        img_msg.is_bigendian = False
        img_msg.step = self._w * 3
        img_msg.data = _bgr_frame_to_rgb_bytes(frame)
        self._img_pub.publish(img_msg)

        self._info_msg.header = header
        self._info_pub.publish(self._info_msg)


def main(args=None) -> None:
    rclpy.init(args=args)
    node = CameraNode()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()
