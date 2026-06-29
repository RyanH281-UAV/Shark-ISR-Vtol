"""
sitl.launch.py — Full-stack SITL bring-up: all five shark-ISR nodes.

Includes each package's own launch file so per-package config/*.yaml loading
stays in exactly one place (the owning package).

Prerequisites (run first, separate terminal):
    ./scripts/run_sim.sh     # Gazebo + MicroXRCE-DDS agent + PX4 SITL

Usage:
    source ros2_ws/install/setup.bash
    ros2 launch shark_isr_bringup sitl.launch.py

Subsets (skip perception, e.g. when injecting detections by hand):
    ros2 launch shark_isr_bringup sitl.launch.py with_perception:=false
"""

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.conditions import IfCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration


def _include(package: str, launch_file: str, condition=None):
    src = PythonLaunchDescriptionSource(
        os.path.join(get_package_share_directory(package), 'launch', launch_file)
    )
    if condition is not None:
        return IncludeLaunchDescription(src, condition=condition)
    return IncludeLaunchDescription(src)


def generate_launch_description() -> LaunchDescription:
    with_perception = LaunchConfiguration('with_perception')
    with_telemetry = LaunchConfiguration('with_telemetry')

    return LaunchDescription([
        DeclareLaunchArgument(
            'with_perception', default_value='true',
            description='Start mock_camera + detector (sim mode)'),
        DeclareLaunchArgument(
            'with_telemetry', default_value='true',
            description='Start telemetry logger'),

        _include('shark_isr_autopilot', 'autopilot.launch.py'),
        _include('shark_isr_guidance', 'guidance.launch.py'),
        _include('shark_isr_mission', 'mission.launch.py'),
        _include('shark_isr_perception', 'perception.launch.py',
                 condition=IfCondition(with_perception)),
        _include('shark_isr_telemetry', 'telemetry.launch.py',
                 condition=IfCondition(with_telemetry)),
    ])
