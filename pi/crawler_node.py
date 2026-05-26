"""Pi-side node for the Pi-Crawler VLM-search project (Phase 1).

Streams camera frames (UDP) and ultrasonic readings (UDP) to the
workstation, accepts movement commands (TCP, newline-delimited JSON),
and runs a safety loop that sits the robot if no command arrives within
``command_timeout_s``.

No VLM, no perception, no autonomy here — pure messaging + safety.
"""
from __future__ import annotations

import io
import json
import logging
import signal
import socket
import struct
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import yaml
from PIL import Image
from picamera2 import Picamera2
from picrawler import Picrawler
from robot_hat import Pin, Ultrasonic

LOG = logging.getLogger("crawler_node")

# Wire formats. Big-endian to avoid host-byte-order surprises.
# Camera datagram:    u32 seq | u64 ts_ms | u32 jpeg_len | <jpeg bytes>
# Ultrasonic datagram: u32 seq | u64 ts_ms | f32 distance_cm
CAMERA_HEADER = struct.Struct("!IQI")
ULTRASONIC_PACKET = struct.Struct("!IQf")

# The network wire uses snake_case (matches ROS / spec conventions);
# SunFounder's do_action vocabulary uses space-separated names.
ACTION_MAP = {
    "forward": "forward",
    "backward": "backward",
    "turn_left": "turn left",
    "turn_right": "turn right",
}
SIT_SPEED = 30  # SunFounder keyboard demo uses clamp(speed, 20, 40) for sit.


@dataclass
class Config:
    workstation_ip: str
    camera_port: int
    ultrasonic_port: int
    command_port: int
    camera_width: int
    camera_height: int
    jpeg_quality: int
    target_hz: float
    default_speed: int
    command_timeout_s: float


def load_config(path: Path) -> Config:
    with path.open() as f:
        data = yaml.safe_load(f)
    return Config(**data)


class CommandState:
    """Thread-safe holder for the latest movement intent."""

    def __init__(self, default_speed: int) -> None:
        self._lock = threading.Lock()
        self._intent: str = "stop"
        self._speed: int = default_speed
        self._last_cmd_ts: float = 0.0  # monotonic seconds; 0 = never

    def update(self, intent: str, speed: Optional[int] = None) -> None:
        with self._lock:
            self._intent = intent
            if speed is not None:
                self._speed = max(0, min(100, int(speed)))
            self._last_cmd_ts = time.monotonic()

    def snapshot(self) -> tuple[str, int, float]:
        with self._lock:
            return self._intent, self._speed, self._last_cmd_ts


def _now_ms() -> int:
    return int(time.time() * 1000)


def _rate_sleep(next_t: float, period: float) -> float:
    sleep = next_t - time.monotonic()
    if sleep > 0:
        time.sleep(sleep)
        return next_t + period
    # Drifted; resync from now to avoid spiral of catch-up.
    return time.monotonic() + period


def run_camera(cfg: Config, stop_event: threading.Event) -> None:
    LOG.info(
        "Camera: %dx%d JPEG q=%d -> %s:%d @ %.1fHz",
        cfg.camera_width, cfg.camera_height, cfg.jpeg_quality,
        cfg.workstation_ip, cfg.camera_port, cfg.target_hz,
    )
    cam = Picamera2()
    # picamera2 quirk: format names are inverted from numpy memory order.
    # "BGR888" yields an ndarray whose channels are R,G,B in memory —
    # i.e. directly compatible with PIL's "RGB" mode. If colors look
    # swapped during testing, flip this to "RGB888".
    video_cfg = cam.create_video_configuration(
        main={"size": (cfg.camera_width, cfg.camera_height), "format": "BGR888"},
    )
    cam.configure(video_cfg)
    cam.start()

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    dst = (cfg.workstation_ip, cfg.camera_port)
    period = 1.0 / cfg.target_hz
    seq = 0
    next_t = time.monotonic() + period

    try:
        while not stop_event.is_set():
            frame = cam.capture_array()
            buf = io.BytesIO()
            try:
                Image.fromarray(frame, "RGB").save(
                    buf, format="JPEG", quality=cfg.jpeg_quality,
                )
                payload: Optional[bytes] = buf.getvalue()
            except Exception as e:
                LOG.warning("JPEG encode failed for frame %d: %s", seq, e)
                payload = None
            if payload is not None:
                if CAMERA_HEADER.size + len(payload) > 65507:
                    LOG.warning(
                        "Frame %d too large for UDP (%d bytes); dropping",
                        seq, len(payload),
                    )
                else:
                    header = CAMERA_HEADER.pack(seq, _now_ms(), len(payload))
                    try:
                        sock.sendto(header + payload, dst)
                    except OSError as e:
                        LOG.warning("Camera sendto failed: %s", e)
            seq += 1
            next_t = _rate_sleep(next_t, period)
    finally:
        try:
            cam.stop()
        except Exception:
            pass
        sock.close()
        LOG.info("Camera thread exited")


def run_ultrasonic(cfg: Config, stop_event: threading.Event) -> None:
    LOG.info(
        "Ultrasonic: D2/D3 -> %s:%d @ %.1fHz",
        cfg.workstation_ip, cfg.ultrasonic_port, cfg.target_hz,
    )
    sonar = Ultrasonic(Pin("D2"), Pin("D3"))
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    dst = (cfg.workstation_ip, cfg.ultrasonic_port)
    period = 1.0 / cfg.target_hz
    seq = 0
    next_t = time.monotonic() + period

    try:
        while not stop_event.is_set():
            try:
                distance_cm = float(sonar.read())
            except Exception as e:
                LOG.warning("Ultrasonic read failed: %s", e)
                distance_cm = -1.0
            try:
                sock.sendto(
                    ULTRASONIC_PACKET.pack(seq, _now_ms(), distance_cm), dst,
                )
            except OSError as e:
                LOG.warning("Ultrasonic sendto failed: %s", e)
            seq += 1
            next_t = _rate_sleep(next_t, period)
    finally:
        sock.close()
        LOG.info("Ultrasonic thread exited")


def _handle_client(
    conn: socket.socket,
    addr: tuple[str, int],
    state: CommandState,
    stop_event: threading.Event,
) -> None:
    LOG.info("Command client connected: %s:%d", *addr)
    try:
        conn.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
        conn.settimeout(1.0)
        buf = b""
        while not stop_event.is_set():
            try:
                chunk = conn.recv(4096)
            except socket.timeout:
                continue
            if not chunk:
                break
            buf += chunk
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                line = line.strip()
                if not line:
                    continue
                try:
                    msg = json.loads(line)
                except json.JSONDecodeError as e:
                    LOG.warning("Bad JSON from %s:%d: %s (%r)", *addr, e, line)
                    continue
                action = msg.get("action")
                if action != "stop" and action not in ACTION_MAP:
                    LOG.warning("Unknown action from %s:%d: %r", *addr, action)
                    continue
                state.update(action, msg.get("speed"))
                LOG.debug("intent <- %s speed=%s", action, msg.get("speed"))
    finally:
        conn.close()
        LOG.info("Command client disconnected: %s:%d", *addr)


def run_command_server(
    state: CommandState, cfg: Config, stop_event: threading.Event,
) -> None:
    LOG.info("Command TCP server listening on 0.0.0.0:%d", cfg.command_port)
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("0.0.0.0", cfg.command_port))
    srv.listen(4)
    srv.settimeout(1.0)
    try:
        while not stop_event.is_set():
            try:
                conn, addr = srv.accept()
            except socket.timeout:
                continue
            threading.Thread(
                target=_handle_client,
                args=(conn, addr, state, stop_event),
                name=f"cmd-{addr[0]}:{addr[1]}",
                daemon=True,
            ).start()
    finally:
        srv.close()
        LOG.info("Command server exited")


def run_worker(
    state: CommandState,
    cfg: Config,
    stop_event: threading.Event,
    crawler: Picrawler,
) -> None:
    LOG.info("Action worker started (timeout=%.1fs)", cfg.command_timeout_s)
    # Put robot in a known pose at startup.
    try:
        crawler.do_step("sit", SIT_SPEED)
    except Exception as e:
        LOG.error("startup sit failed: %s", e)
    last_executed = "stop"
    try:
        while not stop_event.is_set():
            intent, speed, last_cmd_ts = state.snapshot()
            age = (
                time.monotonic() - last_cmd_ts
                if last_cmd_ts > 0 else float("inf")
            )
            timed_out = age > cfg.command_timeout_s

            if timed_out or intent == "stop":
                if last_executed != "stop":
                    reason = "timeout" if timed_out else "stop command"
                    LOG.info("Sitting (reason: %s)", reason)
                    try:
                        crawler.do_step("sit", SIT_SPEED)
                    except Exception as e:
                        LOG.error("do_step('sit') failed: %s", e)
                    last_executed = "stop"
                # Idle briefly; check stop_event responsively.
                stop_event.wait(0.1)
                continue

            action_name = ACTION_MAP.get(intent)
            if action_name is None:
                stop_event.wait(0.1)
                continue
            try:
                crawler.do_action(action_name, 1, speed)
            except Exception as e:
                LOG.error("do_action(%r) failed: %s", action_name, e)
                stop_event.wait(0.2)
            last_executed = intent
    finally:
        try:
            crawler.do_step("sit", SIT_SPEED)
        except Exception:
            pass
        LOG.info("Worker exited (robot sat)")


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )

    cfg_path = Path(__file__).resolve().parent / "config.yaml"
    if len(sys.argv) > 1:
        cfg_path = Path(sys.argv[1])
    if not cfg_path.exists():
        LOG.error("Config file not found: %s", cfg_path)
        return 1
    cfg = load_config(cfg_path)
    LOG.info("Loaded config from %s", cfg_path)

    state = CommandState(default_speed=cfg.default_speed)
    stop_event = threading.Event()
    crawler = Picrawler()

    threads = [
        threading.Thread(
            target=run_camera, args=(cfg, stop_event),
            name="camera", daemon=True,
        ),
        threading.Thread(
            target=run_ultrasonic, args=(cfg, stop_event),
            name="ultrasonic", daemon=True,
        ),
        threading.Thread(
            target=run_command_server, args=(state, cfg, stop_event),
            name="cmd-server", daemon=True,
        ),
        threading.Thread(
            target=run_worker, args=(state, cfg, stop_event, crawler),
            name="worker", daemon=False,
        ),
    ]

    def shutdown(signum: int, _frame: object) -> None:
        LOG.info("Signal %d received; shutting down", signum)
        stop_event.set()

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    for t in threads:
        t.start()

    try:
        while not stop_event.is_set():
            time.sleep(0.5)
    finally:
        stop_event.set()
        for t in threads:
            t.join(timeout=5.0)
    return 0


if __name__ == "__main__":
    sys.exit(main())
