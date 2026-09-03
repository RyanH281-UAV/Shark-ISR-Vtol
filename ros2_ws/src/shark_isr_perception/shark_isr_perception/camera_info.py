"""camera_info.py — shared CameraInfo builder (ADR-018).

Pure message construction, no ROS node coupling. camera_node.py and
mock_camera_node.py used to each carry a byte-identical copy of this.
"""

from sensor_msgs.msg import CameraInfo


def build_camera_info(
    width: int, height: int, fx: float, fy: float, cx: float, cy: float,
) -> CameraInfo:
    info = CameraInfo()
    info.width = width
    info.height = height
    info.distortion_model = "plumb_bob"
    info.d = [0.0, 0.0, 0.0, 0.0, 0.0]
    info.k = [fx, 0.0, cx, 0.0, fy, cy, 0.0, 0.0, 1.0]
    info.r = [1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0]
    info.p = [fx, 0.0, cx, 0.0, 0.0, fy, cy, 0.0, 0.0, 0.0, 1.0, 0.0]
    return info
