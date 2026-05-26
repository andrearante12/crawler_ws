# Phase 2: Safety hardening + bag recording

> **Status**: STUB. Expand when Phase 1 is done. Below is the rough shape;
> details (and probably the deliverables list itself) will change based on
> what we learned in Phase 1.

## Goal

Make the system safe and observable enough to confidently develop against
without the Pi present. Two threads:

1. **Safety**: a fast Pi-side loop independent of the workstation that
   handles ultrasonic emergency stop, command-timeout fallback, and
   connection-loss behavior. The robot must fail safe.
2. **Recording**: a bag-recording workflow so we can capture real Pi
   sessions and replay them on the workstation later. This is the bridge
   to Pi-less development for Phases 3+.

## Non-goals

- No VLM yet.
- No simulation environment (Gazebo etc.) — that's a different project.
- No fancy safety beyond reactive stop. No predictive collision avoidance,
  no learned safety policies.

## Deliverables (rough)

1. Safety refactor on `pi/crawler_node.py`:
   - Fast loop at ≥20 Hz reading ultrasonic and watchdogging command
     timestamps.
   - Reactive stop if ultrasonic < threshold (configurable, ~15-20 cm).
   - Command-timeout stop (already in Phase 1 — verify it actually works
     under WiFi drop).
   - Clean shutdown on SIGTERM.
2. Bag recording launch file:
   - Records `/robot_0/camera/image`, `/robot_0/ultrasonic/range`, and
     `/robot_0/cmd` (so we can replay both inputs and intended outputs).
3. Bag replay launch file:
   - Plays a bag file with adjustable speed.
   - Swaps in for the bridge node so downstream code sees identical
     topics.
4. A small library of recorded sessions (gitignored, but documented in
   `data/recordings/README.md`):
   - Empty room.
   - Room with a few objects.
   - Hallway / multi-room.
   - At least one "edge case" session (low light, cluttered, etc.).
5. Phase 2 testing doc.

## Design notes (to be expanded)

- Safety loop should run as a separate thread/process from the telemetry
  loop. Telemetry can lag without safety lagging.
- Bag size matters — at 10 Hz, JPEG frames, a 30-min session is order of
  ~500 MB. Plan disk usage.
- Consider whether to record the raw UDP stream (smaller, replayable
  bit-exact) or the post-bridge ROS topics (larger, more useful for
  downstream development). Probably the latter.

## Open questions

- Should the safety loop be a separate Python process, or a thread in
  the main script? Thread is simpler; process is more robust to bugs.
- Ultrasonic stop threshold: too tight = annoying false stops on uneven
  floors; too loose = doesn't actually save anything. Tune empirically.
- Do we want pose recording? No native pose source yet, but might add
  visual odometry later. Leave a placeholder topic.

## Working style

TBD when starting this phase.

## Testing plan

- Connection-loss test: yank WiFi mid-drive, robot stops within
  configured timeout. Verify multiple times.
- Obstacle test: drive at a wall slowly, verify ultrasonic stop triggers
  reliably.
- Recording test: record a 10-minute session, replay it, verify topics
  arrive identically.
- Replay-without-Pi test: shut off the Pi, run a bag, verify the rest of
  the pipeline (bridge + any consumers) works against playback.

## Scope

Smaller than Phase 1, probably a few sessions. Most of the work is
operational/testing, not new code.

## Definition of done

- Robot fails safe under WiFi drop, GPIO error, or ultrasonic obstacle.
- I have a couple of recorded sessions across multiple rooms.
- I can develop downstream code (Phase 3+) with the Pi powered off,
  using bag playback.
