from launch import LaunchDescription
from launch_ros.actions import Node
from ament_index_python.packages import get_package_share_directory
import os


def generate_launch_description() -> LaunchDescription:
    config = os.path.join(
        get_package_share_directory('shark_isr_guidance'),
        'config', 'guidance.yaml',
    )
    return LaunchDescription([
        Node(
            package='shark_isr_guidance',
            executable='guidance_node',
            name='guidance_node',
            parameters=[config],
            output='screen',
            emulate_tty=True,
        ),
    ])
