# Pi-Crawler Pi-side node

`crawler_node.py` is the only thing that runs on the Pi in Phase 1. It:

- Captures camera frames (640×480, JPEG q70) and sends them to the
  workstation over UDP at ~10 Hz.
- Reads the ultrasonic sensor and sends distance (cm) over a separate
  UDP port at ~10 Hz.
- Listens on TCP for newline-delimited JSON commands of the form
  `{"action": "forward"|"backward"|"turn_left"|"turn_right"|"stop", "speed": 80}`
  (`speed` optional; defaults to `config.yaml` value).
- Maintains a continuous-intent worker: as long as the latest command
  is a movement, it keeps stepping. If no command arrives for
  `command_timeout_s` (default 1.0 s), or the command is `stop`, the
  worker calls `crawler.do_step("sit", 30)`.

## Prerequisites

- SunFounder Pi-Crawler software stack installed per
  [the official docs](https://docs.sunfounder.com/projects/pi-crawler/en/latest/python/play_with_python.html).
  Verify by running any of their demo scripts first — if their
  `keyboard_control.py` doesn't work, this won't either.
- Camera enabled: `sudo raspi-config` → Interface Options → Camera.
  `libcamera-hello` should produce a preview.
- The `pi` user (or whoever runs the node) is in groups:
  `gpio`, `i2c`, `spi`, `video`. Check with `groups`; add with
  `sudo usermod -a -G gpio,i2c,spi,video pi` then log out / back in.

## Setup

The venv lives at the workspace root (`~/crawler_ws/.venv`), shared by
any Python that runs on the Pi.

```bash
cd ~/crawler_ws   # repo root

# --system-site-packages so the system-installed picamera2,
# picrawler, and robot_hat remain importable inside the venv.
python3 -m venv --system-site-packages .venv
source .venv/bin/activate
pip install -r pi/requirements.txt
```

Then edit `pi/config.yaml` and set `workstation_ip` to the workstation's
LAN address (default `192.168.1.187`).

## Run

```bash
source ~/crawler_ws/.venv/bin/activate
cd ~/crawler_ws/pi
python3 crawler_node.py            # uses ./config.yaml
# or: python3 crawler_node.py /path/to/other-config.yaml
```

You should see log lines for each thread starting up, the robot will
sit once at startup, and then telemetry will start flowing.

`Ctrl-C` triggers a graceful shutdown: worker sits the robot, then
threads exit.

## Smoke tests (before the workstation side exists)

These let you verify each piece independently from any other machine
on the LAN (the "workstation" here is just whichever machine you run
`nc` from — set `workstation_ip` accordingly).

**1. Camera UDP packets reach the workstation:**

```bash
# On the workstation:
nc -u -l 5005 | head -c 64 | xxd
```

You should see binary chunks arriving at ~10 Hz. The first 16 bytes
are the header (`u32 seq | u64 ts_ms | u32 jpeg_len`).

**2. Ultrasonic UDP packets reach the workstation:**

```bash
# On the workstation:
nc -u -l 5006 | xxd | head
```

Same idea — 20-byte packets at ~10 Hz.

**3. The robot accepts and acts on a command:**

```bash
# From any machine on the LAN (replace IP with the Pi's):
echo '{"action": "forward"}' | nc 192.168.1.19 5007
```

The robot should take a step or two forward, then sit after ~1 s
(connection closes, heartbeat times out).

**4. Sustained walk + automatic stop on disconnect:**

```bash
( while sleep 0.3; do echo '{"action": "forward"}'; done ) | nc 192.168.1.19 5007
```

The robot walks continuously. Hit `Ctrl-C` on the workstation —
within 1 second the Pi's heartbeat times out and the robot sits.

**5. Explicit stop:**

```bash
printf '{"action":"forward"}\n{"action":"forward"}\n{"action":"stop"}\n' | nc 192.168.1.19 5007
```

A couple of steps, then sit.

## Run as a systemd service

Once the manual tests above pass, install the unit file (`crawler-node.service`
in this directory) — one-time setup on the Pi:

```bash
sudo cp ~/crawler_ws/pi/crawler-node.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now crawler-node
journalctl -u crawler-node -f    # tail logs
```

After that, the node starts automatically at boot and respawns on
crash (`Restart=on-failure`).

## Deploying changes from the workstation

`scripts/deploy_pi.sh` (from the repo root on the workstation)
rsyncs the `pi/` directory to the Pi and restarts the service:

```bash
./scripts/deploy_pi.sh
# or with overrides:
PI_HOST=pi@192.168.1.19 ./scripts/deploy_pi.sh
```

`venv/` and `__pycache__/` are excluded so the venv stays put.

## Troubleshooting (quick reference)

The deeper version of this lives in `docs/phase1_testing.md` (written
in Step 6 of Phase 1). Quick hits:

- `ModuleNotFoundError: picamera2` / `picrawler` — `.venv` was created
  without `--system-site-packages`. Recreate it.
- `Permission denied` on GPIO — user not in `gpio` group, or
  SunFounder's install requires the device files to be set up.
- Frames not arriving on the workstation — check `workstation_ip` in
  `config.yaml`, check `sudo ufw status` on the workstation, check
  the Pi can ping the workstation.
- Robot sits immediately after every command — heartbeat is working
  as intended; commands need to keep arriving faster than
  `command_timeout_s`.
