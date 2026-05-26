# Workstation-side ROS 2 packages

Two packages live under `src/`:

- **`crawler_bridge`** — receives UDP telemetry from the Pi and
  republishes it on ROS topics; subscribes to a command topic and
  forwards each message to the Pi over TCP.
- **`crawler_teleop`** — interactive keyboard teleop that publishes
  JSON movement commands.

The Pi-side counterpart is `pi/crawler_node.py` (see `pi/README.md`).

## Topic / param schema

Default namespace is `robot_0` (changeable via the
`robot_namespace` parameter in `config.yaml`):

| Direction | Topic                              | Type                   | Notes                                      |
|-----------|------------------------------------|------------------------|--------------------------------------------|
| Published | `/robot_0/camera/image`            | `sensor_msgs/Image`    | `rgb8`, 640×480, ~10 Hz, sensor-data QoS   |
| Published | `/robot_0/ultrasonic/range`        | `sensor_msgs/Range`    | metres; `+inf` if sensor reported error    |
| Subscribed| `/robot_0/cmd`                     | `std_msgs/String`      | JSON: `{"action": "...", "speed": 0-100}` |

Allowed `action` values: `forward`, `backward`, `turn_left`,
`turn_right`, `stop`. `speed` is optional (defaults to the Pi's
`default_speed`).

The command wire format is JSON-in-String rather than a custom
message — this keeps the schema in one place (the Pi) and avoids a
`rosidl_generator_py` build cycle for Phase 1. We can move to a typed
msg in a later phase without touching the Pi.

## Prerequisites

- Ubuntu 24.04
- ROS 2 Jazzy installed at `/opt/ros/jazzy`
- Pi reachable on the LAN (default `192.168.1.19`), running
  `pi/crawler_node.py`

Each shell that uses ROS must source the distro:

```bash
source /opt/ros/jazzy/setup.bash
```

(Add to `~/.bashrc` if you want it always on.)

## Build

```bash
cd ~/crawler_ws/workstation
source /opt/ros/jazzy/setup.bash
colcon build --symlink-install
source install/setup.bash
```

`--symlink-install` lets you edit `.py` files without rebuilding
(except for `setup.py`, `package.xml`, launch files, or config
files — those still need `colcon build`).

If you ever see "package not found" after editing `package.xml`,
nuke and rebuild:

```bash
rm -rf build install log && colcon build --symlink-install
```

## Configure

Edit `src/crawler_bridge/config/config.yaml`:

- `pi_ip` — IP address of the Pi (default `192.168.1.19`)
- `command_port` / `camera_port` / `ultrasonic_port` — must match
  `pi/config.yaml`

Rebuild after editing (`--symlink-install` does NOT symlink yaml in
`data_files`). If you change config often, `colcon build --packages-select
crawler_bridge` is faster.

## Run

Two shells, both with ROS + workspace sourced.

**Shell 1 — bridge:**

```bash
source /opt/ros/jazzy/setup.bash
source ~/crawler_ws/workstation/install/setup.bash
ros2 launch crawler_bridge bringup.launch.py
```

You should see logs like:

```
[udp_telemetry_node]: Listening UDP camera=5005 ultrasonic=5006; publishing under /robot_0/
[cmd_bridge_node]:    Subscribing /robot_0/cmd; forwarding to 192.168.1.19:5007 over TCP
```

**Shell 2 — teleop:**

Use `ros2 run`, not `ros2 launch`. Launch hides stdin, which the
keyboard reader needs.

```bash
source /opt/ros/jazzy/setup.bash
source ~/crawler_ws/workstation/install/setup.bash
ros2 run crawler_teleop teleop_keyboard_node
```

Then drive: `w/a/s/d` to move, `space` to stop, `+`/`-` to adjust
speed, `q` to quit.

## Visualize / inspect

```bash
# camera feed
ros2 run rqt_image_view rqt_image_view /robot_0/camera/image

# ultrasonic
ros2 topic echo /robot_0/ultrasonic/range

# topic rate sanity (expect ~10 Hz each)
ros2 topic hz /robot_0/camera/image
ros2 topic hz /robot_0/ultrasonic/range

# what teleop is publishing (expect ~5 Hz)
ros2 topic echo /robot_0/cmd

# all running nodes
ros2 node list
```

## Manual command (no teleop)

To poke the system without running teleop:

```bash
ros2 topic pub -r 5 /robot_0/cmd std_msgs/msg/String \
  'data: "{\"action\":\"forward\",\"speed\":80}"'
```

`-r 5` publishes at 5 Hz so the Pi heartbeat doesn't trip. Ctrl-C
stops publishing and the robot sits after the 1 s heartbeat.

## Quick troubleshooting

- **`ros2: command not found`** — you didn't `source /opt/ros/jazzy/setup.bash`.
- **`No package matching 'crawler_*'`** — you didn't `source install/setup.bash`
  (in `~/crawler_ws/workstation/`).
- **No image in `rqt_image_view`** — `ros2 topic hz /robot_0/camera/image`:
  if 0 Hz, the bridge isn't getting UDP. Check `ufw status` and that
  the Pi is sending (the Pi script's logs will say so).
- **Robot won't move when you press `w`** — `ros2 topic echo /robot_0/cmd`
  should show messages. If it does but the robot is still sitting:
  cmd_bridge_node may have failed to connect; check its logs for
  `connect to ... failed`.
- **Teleop prints "stdin is not a tty"** — you used `ros2 launch`
  instead of `ros2 run`. Use `ros2 run`.

The full failure-mode reference lives in `docs/phase1_testing.md`.
