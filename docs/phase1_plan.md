# Phase 1: Messaging foundation

> **Status**: active. Most detailed of the phase plans because this is what
> we're working on now. Later phases are stubs — expand when starting them.

## Goal

A reliable, low-latency messaging layer between the Pi and the workstation,
with a keyboard teleop node on the workstation that can drive the robot.
Camera frames and ultrasonic readings stream from Pi to workstation as ROS 2
topics; movement commands flow back to the Pi. The Pi runs no ROS — only a
lightweight Python script.

By the end of this phase, I should be able to sit at the workstation, run a
launch file, press WASD, and watch the robot move while a separate window
shows the live camera feed.

## Non-goals

- No VLM, perception, or autonomy logic.
- No image processing on the Pi (frames pass through; encoding happens in
  the picamera2 pipeline).
- No multi-robot support yet — but topic namespaces (`/robot_0/...`) should
  be in place so Phase ≥4 can extend cleanly.
- No advanced safety logic beyond a basic "stop if no command in 1s"
  heartbeat. Hardened safety is Phase 2.

## Deliverables

1. **Pi-side script** (`pi/crawler_node.py`):
   - Captures camera frames via picamera2 with built-in JPEG encoding.
   - Reads ultrasonic via the SunFounder library.
   - Streams telemetry to workstation over UDP at ~10 Hz.
   - Listens on TCP for commands (`{"action": "forward"|"turn_left"|"turn_right"|"stop"}`).
   - Heartbeat: if no command received in 1s, stops the robot.
   - Config via YAML (`pi/config.yaml`) for IPs/ports.
2. **Pi-side README** (`pi/README.md`): venv setup, deps, how to run.
3. **ROS 2 package `crawler_bridge`** (`workstation/src/crawler_bridge/`):
   - UDP listener node → publishes `/robot_0/camera/image` (sensor_msgs/Image)
     and `/robot_0/ultrasonic/range` (sensor_msgs/Range).
   - Command forwarder node → subscribes to `/robot_0/cmd` and sends TCP
     to the Pi.
   - Python launch file to start both.
4. **ROS 2 package `crawler_teleop`** (`workstation/src/crawler_teleop/`):
   - Keyboard teleop node publishing to `/robot_0/cmd`.
5. **Workstation README** (`workstation/README.md`): ROS 2 Jazzy install
   reminder, colcon build, launch instructions.
6. **Sync script** (`scripts/sync-pi.sh`): rsync wrapper.
7. **Phase 1 testing doc** (`docs/phase1_testing.md`): how to run, what
   success looks like, common failure modes.

## Design notes

- **Telemetry over UDP, commands over TCP.** Telemetry is OK to drop;
  stale frames are useless. Commands must arrive — control matters.
- **No cv2 on the Pi.** picamera2's built-in JPEG encoder does the work.
- **JSON message format** for both telemetry and commands. Easy to debug,
  language-agnostic, fine at this scale. Switch to binary if we ever care
  about per-byte overhead (we won't, at this frame rate).
- **Namespaced topics.** Everything is `/robot_0/<thing>` so Phase ≥4 can
  add `/robot_1/`, etc.
- **The bridge is the only thing that talks to the Pi.** All downstream
  workstation code consumes ROS topics. This is the seam that lets us
  swap in bag playback or a fake Pi later.

## Open questions

1. **picamera2 JPEG encoder API:** Confirm the exact call to get encoded
   bytes per frame in the version we have. (Should be `picam2.capture_array`
   with a JPEG-configured stream, or a `JpegEncoder` with a file-like sink
   that we redirect — Claude Code should verify on the actual Pi.)
2. **SunFounder API specifics:** Which methods correspond to forward /
   turn / stop? Confirm by reading the installed library and the docs at
   https://docs.sunfounder.com/projects/pi-crawler/en/latest/python/play_with_python.html
3. **GPIO/camera perms:** Does the SunFounder library need root, or does
   adding `pi` to `gpio,i2c,spi,video` cover it? Test before writing a
   systemd service.
4. **Autostart on boot?** Optional for Phase 1. Nice for demo day. Defer.

## Working style

Walk me through it step by step:

1. ROS 2 Jazzy install on the workstation — verify before moving on.
2. Project repo skeleton + CLAUDE.md.
3. Pi-side script + README. Stop here, let me sync and test on the Pi.
4. Workstation `crawler_bridge` package.
5. Workstation `crawler_teleop` package.
6. End-to-end test guide.

Ask before guessing on the SunFounder API or picamera2 specifics.

## Testing plan

- **Unit-ish**: run `pi/crawler_node.py` standalone, verify it prints
  ultrasonic readings and captures frames without crashing.
- **Loopback**: run the bridge node on the workstation pointing at
  localhost; run a fake-Pi script that streams a static image and a
  fake ultrasonic value. Verify ROS topics show data.
- **End-to-end**: real Pi streaming to real workstation. Open
  `rqt_image_view` on `/robot_0/camera/image`, see the live feed.
  Drive with teleop. Yank the Pi's WiFi mid-drive — robot should stop
  within ~1 second.
- **Latency check**: rough measure of frame-arrival to display. Expect
  100-300ms over WiFi. If >500ms, debug.

## Scope

Medium. A weekend or so of work, plus a chunk of debugging time for the
WiFi / firewall / perms layer cake. Plan for one full session that goes
sideways before the first end-to-end success.

## Definition of done

I can boot the workstation, run one launch command, see the camera feed
on screen, and drive the robot around with the keyboard. The connection
is stable for at least 5 minutes of continuous teleop without dropouts
that require a restart.
