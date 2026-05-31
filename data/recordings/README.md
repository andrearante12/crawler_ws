# Session recordings

Recorded Pi-Crawler sessions for Pi-less development and replay (Phases 3+).

Each session is a `ros2 bag` directory captured with
`record.launch.py`, paired with a tracked metadata **sidecar** that
describes the physical scene. The bags themselves are **not** committed
(large binary `.mcap`); only this README and the `*.session.yaml`
sidecars are tracked, so the catalog of what we have survives in git
even though the data lives locally.

## Layout

```
data/recordings/
├── README.md                       # this file (tracked)
├── 20260531_142233.session.yaml    # sidecar (tracked)
├── 20260531_142233/                # bag dir (gitignored)
│   ├── metadata.yaml               #   bag metadata (ros2 bag)
│   └── 20260531_142233_0.mcap      #   recorded messages
└── ...
```

The sidecar filename is `<bag-dir-name>.session.yaml` and sits next to
the bag directory it describes (not inside it — inside is gitignored).

## Capturing a session

From the **repo root** (so bags land here, not under `workstation/`):

```bash
source /opt/ros/jazzy/setup.bash
source workstation/install/setup.bash
ros2 launch crawler_bridge record.launch.py
```

Drive the robot with the teleop node in another terminal. Stop with
`Ctrl-C` (this finalizes the bag — don't `kill -9`, or `metadata.yaml`
won't be written). Then copy `TEMPLATE.session.yaml` to
`<bag-dir-name>.session.yaml` and fill it in.

## Replaying a session (Pi not required)

```bash
ros2 launch crawler_bridge replay.launch.py bag_path:=data/recordings/<bag-dir-name>
# faster:
ros2 launch crawler_bridge replay.launch.py bag_path:=data/recordings/<bag-dir-name> rate:=2.0
```

## Sidecar schema

See `TEMPLATE.session.yaml`. Fields:

| Field             | Meaning                                                        |
|-------------------|----------------------------------------------------------------|
| `session`         | Bag directory name (the timestamp), e.g. `20260531_142233`.    |
| `date`            | Capture date (YYYY-MM-DD).                                      |
| `room`            | Where it was shot (e.g. "living room", "hallway + kitchen").   |
| `lighting`        | `bright` / `dim` / `natural` / `mixed`; note anything unusual. |
| `objects`         | List of notable objects in view (future VLM search targets).   |
| `duration_s`      | Length in seconds (see `ros2 bag info`).                       |
| `robot_namespace` | Namespace the topics were recorded under (default `robot_0`).  |
| `notes`           | Anything else worth knowing (clutter, motion, edge cases).     |

## Planned capture set (Phase 2 deliverable #5)

Cap each at ~5 min until we know what consumes them:

- [ ] **empty room** — baseline, minimal clutter
- [ ] **room with objects** — several distinct objects for search targets
- [ ] **hallway / multi-room** — longer traverse, changing scenery
- [ ] **edge case** — low light or heavy clutter
