"""Record a Pi-Crawler session.

Brings up the bridge nodes (so a live Pi streams in) and simultaneously
records the compressed camera, ultrasonic, and command topics to a
timestamped bag under data/recordings/. Replay later with
replay.launch.py — the Pi is not needed for replay.

  ros2 launch crawler_bridge record.launch.py
  ros2 launch crawler_bridge record.launch.py namespace:=robot_0
  ros2 launch crawler_bridge record.launch.py bag_dir:=/abs/path/to/bag

The default bag directory is <cwd>/data/recordings/<timestamp>, so run
this from the repo root to land bags in the tracked session library.
"""
from datetime import datetime
from pathlib import Path

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import (
    DeclareLaunchArgument,
    ExecuteProcess,
    IncludeLaunchDescription,
    OpaqueFunction,
)
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration


def _launch_setup(context, *args, **kwargs) -> list:
    ns = LaunchConfiguration("namespace").perform(context)
    bag_dir = LaunchConfiguration("bag_dir").perform(context)

    pkg_share = Path(get_package_share_directory("crawler_bridge"))
    bringup = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            str(pkg_share / "launch" / "bringup.launch.py")
        ),
    )

    # Record the compressed camera topic, not the raw Image — the raw feed
    # would balloon the bag ~30x for no replay benefit. /<ns>/odom is
    # reserved for a future visual-odometry node and is not recorded yet
    # (nothing publishes it).
    topics = [
        f"/{ns}/camera/image/compressed",
        f"/{ns}/ultrasonic/range",
        f"/{ns}/cmd",
    ]
    record = ExecuteProcess(
        cmd=["ros2", "bag", "record", "-o", bag_dir, *topics],
        output="screen",
    )
    return [bringup, record]


def generate_launch_description() -> LaunchDescription:
    default_bag_dir = str(
        Path.cwd() / "data" / "recordings" / datetime.now().strftime("%Y%m%d_%H%M%S")
    )
    return LaunchDescription([
        DeclareLaunchArgument(
            "namespace", default_value="robot_0",
            description="Robot namespace prefix for the recorded topics.",
        ),
        DeclareLaunchArgument(
            "bag_dir", default_value=default_bag_dir,
            description="Output bag directory (must not already exist).",
        ),
        OpaqueFunction(function=_launch_setup),
    ])
