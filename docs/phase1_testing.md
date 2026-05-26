# Phase 1 testing guide

End-to-end test plan and failure-mode reference for the Pi ↔ workstation
messaging foundation. If you're trying to bring the system up from a
cold start, this is the doc.

## What "Phase 1 works" means

- The Pi streams camera frames and ultrasonic readings to the
  workstation, both at ~10 Hz.
- The workstation publishes them on ROS 2 topics in the `/robot_0/`
  namespace.
- A keyboard teleop node on the workstation publishes movement
  commands to `/robot_0/cmd` and the robot executes them.
- The robot sits within 1 s of *any* loss of command flow: explicit
  `stop`, teleop quit, bridge crash, network drop, Pi unplug.

What Phase 1 explicitly does NOT do (deferred):

- Ultrasonic-based obstacle override (Phase 2: safety loop hardening).
- Any VLM, perception, or autonomy (Phase 3+).
- Custom ROS msg types for commands (still `std_msgs/String` + JSON).

## Component map

```
┌────────────────────────┐               ┌──────────────────────────┐
│ Workstation (Ubuntu)   │               │ Raspberry Pi             │
│                        │               │                          │
│ teleop_keyboard_node ──┐               │                          │
│  publishes /robot_0/cmd│               │                          │
│                        │               │                          │
│ cmd_bridge_node ───────┼── TCP 5007 ──▶│ crawler_node.py          │
│  subscribes /robot_0/cmd               │   - cmd server           │
│                        │               │   - worker (do_action)   │
│ udp_telemetry_node ◀───┼── UDP 5005 ───┤   - camera thread        │
│  publishes camera/image│               │                          │
│                        ◀── UDP 5006 ───┤   - ultrasonic thread    │
│  publishes ultrasonic/range            │                          │
└────────────────────────┘               └──────────────────────────┘
       192.168.1.187                            192.168.1.19
```

Ports are configured in `pi/config.yaml` (Pi side) and
`workstation/src/crawler_bridge/config/config.yaml` (workstation
side). They must match.

## Run order

### 0 — Pre-flight

```bash
# On the workstation:
ping -c 2 raspberrypi.local              # or the Pi's IP
sudo ufw status                          # if active, must allow UDP 5005, 5006

# On the Pi (or via ssh):
groups                                   # must include gpio, i2c, spi, video
libcamera-hello --timeout 1000           # camera should produce a preview
```

### 1 — Pi node

```bash
# On the Pi:
cd ~/crawler_ws/pi
source venv/bin/activate
python3 crawler_node.py
```

(Or, once the systemd unit is installed: `sudo systemctl start crawler-node`
and tail with `journalctl -u crawler-node -f`.)

**Pass criteria:** logs show camera + ultrasonic + cmd server + worker
threads up. Robot visibly sits at startup. No errors.

### 2 — Workstation bridge

```bash
# On the workstation, in a fresh shell:
source /opt/ros/jazzy/setup.bash
source ~/crawler_ws/workstation/install/setup.bash
ros2 launch crawler_bridge bringup.launch.py
```

**Pass criteria:** logs say `Listening UDP camera=5005 ultrasonic=5006`
and `Subscribing /robot_0/cmd; forwarding to 192.168.1.19:5007`. No
errors. (cmd_bridge_node won't try to connect until the first
command publish.)

### 3 — Telemetry sanity (no teleop yet)

In another sourced shell:

```bash
ros2 topic hz /robot_0/camera/image       # ~10 Hz
ros2 topic hz /robot_0/ultrasonic/range   # ~10 Hz
ros2 run rqt_image_view rqt_image_view /robot_0/camera/image
ros2 topic echo /robot_0/ultrasonic/range --once
```

**Pass criteria:** both rates ~10. Image looks like the scene the
camera is pointed at (not garbled, not swapped colors). Range value
in metres matches roughly what a ruler says.

### 4 — Teleop

```bash
ros2 run crawler_teleop teleop_keyboard_node
```

**Pass criteria:** robot walks forward on `w`, turns on `a`/`d`,
walks backward on `s`, sits on `space`. Speed indicator updates
on `+`/`-`. Pressing `q` sits the robot and exits cleanly.

### 5 — The safety tests (these are the ones that matter most)

5a. **Teleop quit → robot sits.** Walk forward (`w`), then press `q`.
The teleop publishes one final `stop` before exiting; robot should
sit immediately. ✓

5b. **Bridge crash → robot sits within 1 s.** With teleop holding
`w` (don't press space), Ctrl-C the bridge in shell 1. TCP connection
drops, no more commands arrive on the Pi, heartbeat times out.
Within 1 s the Pi logs `Sitting (reason: timeout)` and the robot sits.

5c. **WiFi drop → robot sits within 1 s.** Same idea but disable the
Pi's WiFi instead of killing the bridge (`ssh pi sudo ifconfig wlan0
down`). Same outcome on the Pi side; the workstation will log TCP
send failures.

5d. **Pi process death → robot sits via process exit.** Ctrl-C the Pi
node while the robot is walking. Worker thread finishes its current
step, then runs `do_step("sit", 30)` in the `finally` block before
exiting.

If any of 5a–5d fails, the safety contract is broken and it must be
fixed before moving on. Phase 2 builds on top of this guarantee.

## Failure modes & fixes

### Network

| Symptom | Likely cause | Fix |
|---|---|---|
| `ros2 topic hz /robot_0/camera/image` = 0 Hz, Pi shows it's sending | UFW or other firewall blocking UDP on workstation | `sudo ufw allow 5005/udp && sudo ufw allow 5006/udp` (or disable ufw for testing) |
| Pi node logs `Camera sendto failed: Network is unreachable` | `workstation_ip` in `pi/config.yaml` is wrong, or the Pi can't reach that subnet | Fix IP; verify with `ping` from Pi |
| `cmd_bridge_node` logs `connect to ... failed: Connection refused` | Pi node isn't running, or its TCP server failed to bind | Check Pi logs |
| `cmd_bridge_node` logs `connect ... failed: No route to host` | Workstation can't reach the Pi (Pi IP wrong, or Pi offline) | Check `pi_ip` in `workstation/src/crawler_bridge/config/config.yaml` and rebuild |
| `raspberrypi.local` resolves intermittently | mDNS / Avahi flake under load | Use the static IP (`192.168.1.19`) directly |
| Robot keeps sitting even though teleop is publishing | Workstation's `pi_ip` is right but bridge can't connect; *or* commands aren't arriving fast enough | `ros2 topic hz /robot_0/cmd` should be ≈ 5; if not, check teleop. Check `cmd_bridge_node` logs for send failures |

### Pi-side hardware/perms

| Symptom | Likely cause | Fix |
|---|---|---|
| `ModuleNotFoundError: picamera2` (or `picrawler`) | `.venv` created without `--system-site-packages` | `cd ~/crawler_ws && rm -rf .venv && python3 -m venv --system-site-packages .venv && source .venv/bin/activate && pip install -r pi/requirements.txt` |
| `Failed to acquire camera` / picamera2 errors at startup | Camera not enabled, or another process is holding it | `sudo raspi-config` → Interface Options → Camera → enable. Reboot. Check no other process has the camera: `sudo fuser /dev/video*` |
| `Permission denied` opening GPIO / I²C devices | User not in the right groups | `sudo usermod -a -G gpio,i2c,spi,video pi` then log out and back in (or reboot). Confirm with `groups` |
| `Ultrasonic read failed` repeatedly, distance = -1 | Sensor wiring loose, or robot HAT not powered | Reseat the connector; check 5 V to the HAT |

### Color / image

| Symptom | Likely cause | Fix |
|---|---|---|
| Image in `rqt_image_view` has red/blue swapped | picamera2 format-name vs memory-order quirk | In `pi/crawler_node.py:run_camera`, swap `"BGR888"` ↔ `"RGB888"`. (Names are inverted from numpy memory layout — see the comment in that function.) |
| Image is too dark / washed out | Auto-exposure tuning; not a software issue | Move the robot to a better-lit area, or tune via picamera2 controls (out of scope for Phase 1) |
| Image is corrupted / partial | UDP fragmentation (frame > 65507 bytes) | Drop `jpeg_quality` in `pi/config.yaml`, or reduce resolution. Pi logs `Frame N too large for UDP` if it caught it on the send side |

### ROS

| Symptom | Likely cause | Fix |
|---|---|---|
| `ros2: command not found` | ROS not sourced in this shell | `source /opt/ros/jazzy/setup.bash` |
| `Package 'crawler_*' not found` after building | Workspace install not sourced | `source ~/crawler_ws/workstation/install/setup.bash` |
| `Package 'crawler_*' not found` after editing `package.xml` | Stale `install/` tree | `rm -rf build install log && colcon build --symlink-install` |
| Teleop exits immediately with `stdin is not a tty` | Started with `ros2 launch` instead of `ros2 run` | Use `ros2 run crawler_teleop teleop_keyboard_node` |
| Two ROS 2 systems on the same LAN see each other's topics | Default `ROS_DOMAIN_ID=0` collision | Set `export ROS_DOMAIN_ID=<n>` (matching on Pi and workstation if/when the Pi gets its own node — Phase 1 doesn't run rclpy on the Pi) |

### Behavior

| Symptom | Likely cause | Fix |
|---|---|---|
| Robot moves jerkily even on continuous `w` | Each `do_action` is ~1 s and blocking; this is by design (continuous-intent worker) | Expected at Phase 1. Smoother motion would need either gait tuning or non-blocking SunFounder primitives — both out of scope. |
| Robot sits a beat after every command, not immediately on `q` | Teleop's final `_tick` publishes synchronously but the publish→TCP→Pi→worker hop has latency | Expected; should be << 1 s. If it's > 1 s, check `ros2 topic hz /robot_0/cmd` |
| Robot does the wrong action for a key | Key mapping mismatch | Check `KEY_TO_ACTION` in `teleop_keyboard_node.py` |
