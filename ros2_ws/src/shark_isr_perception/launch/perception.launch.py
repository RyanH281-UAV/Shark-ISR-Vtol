"""
perception.launch.py — Launch mock_camera_node + detector_node.

Args
----
  use_sim (default true)  : sim mode — runs mock camera + probabilistic detections.
                            Set false for hardware (real camera + HailoRT).
  hef_path (default "")   : path to .hef model on Pi 5 (required when use_sim=false).
  mock_images_dir ("")    : optional dir of test images for mock camera.
  log_level (default info): logging verbosity.
"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
import os
from ament_index_python.packages import get_package_share_directory


def generate_launch_description() -> LaunchDescription:
    pkg_share = get_package_share_directory("shark_isr_perception")
    default_config = os.path.join(pkg_share, "config", "perception.yaml")

    use_sim_arg = DeclareLaunchArgument(
        "use_sim", default_value="true", description="Use sim mode (mock camera + detections)"
    )
    hef_path_arg = DeclareLaunchArgument(
        "hef_path", default_value="", description="Path to Hailo .hef model (real mode)"
    )
    mock_images_dir_arg = DeclareLaunchArgument(
        "mock_images_dir",
        default_value="",
        description="Dir of .png/.jpg frames for mock camera (empty = noise)",
    )
    log_level_arg = DeclareLaunchArgument(
        "log_level", default_value="info", description="Logging level"
    )

    use_sim = LaunchConfiguration("use_sim")
    hef_path = LaunchConfiguration("hef_path")
    mock_images_dir = LaunchConfiguration("mock_images_dir")
    log_level = LaunchConfiguration("log_level")

    mock_camera = Node(
        package="shark_isr_perception",
        executable="mock_camera_node",
        name="mock_camera_node",
        parameters=[
            default_config,
            {"mock_images_dir": mock_images_dir},
        ],
        arguments=["--ros-args", "--log-level", log_level],
        condition=__import__("launch.conditions", fromlist=["IfCondition"]).IfCondition(use_sim),
    )

    detector = Node(
        package="shark_isr_perception",
        executable="detector_node",
        name="detector_node",
        parameters=[
            default_config,
            {"use_sim": use_sim, "hef_path": hef_path},
        ],
        arguments=["--ros-args", "--log-level", log_level],
    )

    return LaunchDescription(
        [
            use_sim_arg,
            hef_path_arg,
            mock_images_dir_arg,
            log_level_arg,
            mock_camera,
            detector,
        ]
    )
