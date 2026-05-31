"""Replay a recorded Pi-Crawler session bag.

Does NOT start udp_telemetry_node or cmd_bridge_node: the commands in a
bag are historical, not live stimulus, and the camera/ultrasonic topics
play straight back from the bag. The Pi does not need to be present or
powered on — this is the Pi-less development entry point for Phases 3+.

  ros2 launch crawler_bridge replay.launch.py bag_path:=data/recordings/<timestamp>
  ros2 launch crawler_bridge replay.launch.py bag_path:=<dir> rate:=2.0
"""
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, ExecuteProcess
from launch.substitutions import LaunchConfiguration


def generate_launch_description() -> LaunchDescription:
    bag_path = LaunchConfiguration("bag_path")
    rate = LaunchConfiguration("rate")
    return LaunchDescription([
        # No default: bag_path is required.
        DeclareLaunchArgument(
            "bag_path",
            description="Path to the recorded bag directory to play back.",
        ),
        DeclareLaunchArgument(
            "rate", default_value="1.0",
            description="Playback rate multiplier (2.0 = double speed).",
        ),
        ExecuteProcess(
            cmd=["ros2", "bag", "play", bag_path, "--rate", rate],
            output="screen",
        ),
    ])
