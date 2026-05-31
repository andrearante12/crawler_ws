# Phase 2: Safety hardening + bag recording

> **Status**: active.

## Goal

Make the system safe and observable enough to confidently develop against
without the Pi present. Two threads:

1. **Safety**: a fast Pi-side loop independent of the workstation that
   adds ultrasonic-driven reactive stop on top of the existing command-
   timeout fallback. The robot must fail safe.
2. **Recording**: a bag record + replay workflow so we can capture real
   Pi sessions and replay them on the workstation later. This is the
   bridge to Pi-less development for Phases 3+.

## Non-goals

- No VLM yet.
- No simulation environment (Gazebo etc.) — that's a different project.
- No fancy safety beyond reactive stop. No predictive collision
  avoidance, no learned safety policies.
- **No `do_step`-based gait rewrite.** The current `do_action(name, 1,
  speed)` worker is ~1 s blocking per call and is not interruptible
  mid-step. Preemption of an in-flight step is out of scope. Safety
  acts before each new step instead (see "Design notes").

## Carry-over from Phase 1

The following already work from Phase 1 and are NOT re-deliverables —
Phase 2 builds on top of them:

- Command-timeout sit (1 s) at `pi/crawler_node.py:run_worker`.
- Clean SIGTERM/SIGINT shutdown that sits the robot in `finally`.
- WiFi-drop, bridge-crash, teleop-quit, and process-death all already
  trigger the sit-on-timeout path (Phase 1 testing, tests 5a–5d).

## Decisions (locked in)

- **Image transport**: bridge publishes BOTH raw `Image` (for
  `rqt_image_view` and existing consumers) AND a new `CompressedImage`
  (JPEG passthrough — zero decode/encode round-trip). Bags record only
  the compressed topic. *This touches the messaging layer; flagged per
  CLAUDE.md.*
- **Reactive stop semantics**: while ultrasonic distance < threshold,
  the worker silently drops `forward` intents. `backward`, `turn_left`,
  `turn_right`, `stop` all pass through as recovery actions. No
  "sit and refuse all input" mode.
- **Safety isolation**: dedicated thread in `crawler_node.py`, not a
  separate process. The safety thread becomes the *sole* ultrasonic
  reader and exposes a cached value + obstacle flag to the telemetry
  thread and the worker via a shared `SafetyState`.
- **Replay launch**: `ros2 bag play` only. Does NOT start
  `udp_telemetry_node` or `cmd_bridge_node` — commands in a bag are
  historical, not stimulus.

## Deliverables

1. **Pi-side safety hardening** (`pi/crawler_node.py`):
   - New `SafetyState` (analog to `CommandState`): `latest_distance_cm`,
     `forward_blocked`, with stop/resume hysteresis.
   - New `run_safety` thread @ `safety_hz` (default 20 Hz): reads
     ultrasonic, updates state. Sole reader of the HC-SR04.
   - `run_ultrasonic` (UDP telemetry) becomes a consumer of
     `SafetyState` and no longer touches GPIO directly. Wire format
     unchanged — the workstation bridge needs zero changes for this
     deliverable.
   - `run_worker` consults `SafetyState` before each `do_action`: drops
     `forward` while blocked; everything else passes.
   - New config keys: `safety_hz: 15.0`, `ultrasonic_stop_cm: 15.0`,
     `ultrasonic_resume_cm: 20.0`, `ultrasonic_resume_reads: 5`.

2. **Bridge CompressedImage publisher**
   (`workstation/src/crawler_bridge/crawler_bridge/udp_telemetry_node.py`):
   - Publish `/<ns>/camera/image/compressed` as
     `sensor_msgs/CompressedImage`, wrapping the incoming JPEG bytes
     directly (no decode).
   - Keep the existing raw `Image` publisher.

3. **Bag-recording launch**
   (`workstation/src/crawler_bridge/launch/record.launch.py`):
   - Composes `bringup.launch.py` + a `ros2 bag record` process.
   - Records `/<ns>/camera/image/compressed`,
     `/<ns>/ultrasonic/range`, `/<ns>/cmd`. Output under
     `data/recordings/<timestamp>/`.
   - Reserve `/<ns>/odom` as a future topic name (don't subscribe yet).

4. **Bag-replay launch**
   (`workstation/src/crawler_bridge/launch/replay.launch.py`):
   - Runs `ros2 bag play` with `rate` and `bag_path` args.
   - Does NOT start `udp_telemetry_node` or `cmd_bridge_node`.

5. **Session library** (`data/recordings/`):
   - `.gitignore` ignores bag files; tracks README + per-session
     metadata sidecars.
   - `README.md` documenting the sidecar schema (room, lighting,
     objects, length, notes).
   - 4 captured sessions: empty room, room with objects, hallway /
     multi-room, edge case (low light or cluttered). Cap each at
     ~5 min until we know what consumes them.

6. **Phase 2 testing doc** (`docs/phase2_testing.md`):
   - Obstacle test: drive at a wall, forward refused, backward/turns OK.
   - Recording roundtrip: record 5 min, replay, compare msg counts +
     rates.
   - Pi-off replay: shut Pi down, run replay launch, verify
     `rqt_image_view` shows the feed from the bag.
   - Re-run Phase 1 tests 5a-5d against the new code.

## Design notes

- **Ultrasonic preemption isn't possible mid-step.** `do_action(name, 1,
  speed)` is one ~1 s blocking gait cycle; the SunFounder library does
  not expose a cancel hook. The safety thread detects obstacles fast
  but the worker can only act on that information *before* starting the
  next step. At `default_speed: 80` (~10–15 cm/s) the worst-case
  overshoot is ~one full step (~10–15 cm). The hardware test passed at a
  25 cm stop, but the operator tightened it to `ultrasonic_stop_cm: 15.0`
  for closer approaches. That leaves little-to-no clearance against a
  single in-flight step at speed 80 — if contact is observed, drop
  `default_speed` (shorter steps = less overshoot) rather than widening
  the threshold back out.
- **Noise rejection (debounce).** First hardware runs showed the HC-SR04
  returning bimodal garbage — alternating a ~4 cm near value with a far
  value (25–297 cm) on nearly every read, even while sitting. A plain
  stop/resume hysteresis can't help: each reading jumps clear past both
  thresholds, so the state flapped and forward leaked through during the
  "far" reads. Fix is an asymmetric debounce biased toward stopped: block
  on a single close read, but re-enable only after `ultrasonic_resume_reads`
  (default 5) *consecutive* clear reads. Replaying the logged noise through
  it yields one block and no spurious resumes.
- **Sensor poll rate.** The HC-SR04 needs ≥60 ms between pings or the next
  trigger can catch the previous echo's ringing as a phantom near-return —
  the likely source of the bimodal noise above. `safety_hz` dropped from
  20 Hz (50 ms) to 15 Hz (66 ms) to respect this. If noise persists, the
  sensor mounting/wiring itself needs a look.
- **Sensor-stale fail-safe.** If the ultrasonic returns failure (-1/-2)
  for longer than 1 s, the safety thread forces `forward_blocked` to
  True. Transient single-read failures don't lock the robot up.
- **Bag size.** At 640×480 JPEG q=70 / 10 Hz, a 30-min session lands
  around 500 MB. (Recording raw `Image` would be ~16 GB / 30 min, which
  is why we record the compressed topic only.)

## Open questions

- Do we eventually want pose recording? Not now — no native pose source.
  We reserve `/<ns>/odom` as a topic name so a future visual-odometry
  node can slot in without retooling the bag pipeline.

## Working style

Pause for hardware handoff after each Pi-touching deliverable:

1. Deliver #1 (safety). **Stop**, sync + hardware-test.
2. Deliver #2-4 (bridge + launch files). Workable on the workstation
   alone with the synthetic-Pi loopback from Phase 1.
3. **Stop**, sync to Pi, capture #5 (session library) on hardware.
4. Write #6 (testing doc) from the actual results.

## Testing plan

(See `docs/phase2_testing.md` once written.) Key checks:

- **Obstacle test (new):** drive forward at a wall slowly, verify the
  robot stops accepting `forward` at ~15 cm and resumes at ~20 cm.
  Backward/turns continue to work.
- **Connection-loss test:** same as Phase 1 tests 5b/5c — must still
  pass after the safety thread refactor.
- **Recording roundtrip:** record 5 min, replay at 1× and 2×, verify
  topic rates and msg counts match.
- **Pi-off replay:** shut the Pi off, run replay launch, verify
  `rqt_image_view` against the compressed topic shows the recorded
  feed.

## Scope

Smaller than Phase 1. Pi-side change is a focused refactor; launch
files are mechanical; the session-capture step is operational.

## Definition of done

- Robot fails safe under WiFi drop, GPIO error, *and* ultrasonic
  obstacle.
- 4 recorded sessions live under `data/recordings/` with metadata
  sidecars.
- I can develop downstream code (Phase 3+) with the Pi powered off,
  using `replay.launch.py` against any of the captured sessions.
