"""Bring up both crawler_bridge nodes (UDP telemetry + TCP cmd) with
parameters from share/crawler_bridge/config/config.yaml.
"""
from pathlib import Path

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch_ros.actions import Node


def generate_launch_description() -> LaunchDescription:
    pkg_share = Path(get_package_share_directory("crawler_bridge"))
    config_file = str(pkg_share / "config" / "config.yaml")
    return LaunchDescription([
        Node(
            package="crawler_bridge",
            executable="udp_telemetry_node",
            name="udp_telemetry_node",
            parameters=[config_file],
            output="screen",
            emulate_tty=True,
        ),
        Node(
            package="crawler_bridge",
            executable="cmd_bridge_node",
            name="cmd_bridge_node",
            parameters=[config_file],
            output="screen",
            emulate_tty=True,
        ),
    ])
