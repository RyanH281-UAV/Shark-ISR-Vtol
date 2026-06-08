from launch import LaunchDescription
from launch_ros.actions import Node
from ament_index_python.packages import get_package_share_directory
import os


def generate_launch_description() -> LaunchDescription:
    pkg = get_package_share_directory('shark_isr_telemetry')
    config = os.path.join(pkg, 'config', 'telemetry.yaml')

    return LaunchDescription([
        Node(
            package='shark_isr_telemetry',
            executable='telemetry_node',
            name='telemetry_node',
            parameters=[config],
            output='screen',
        ),
    ])
