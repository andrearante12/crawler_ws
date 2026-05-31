#!/usr/bin/python3
"""Render the camera frames from a recorded bag to an .mp4 for easy viewing.

Reads the CompressedImage (JPEG) topic out of a rosbag2 bag, decodes each
frame, and writes a real-time .mp4 whose fps is derived from the recorded
message timestamps. The Pi is not required.

Requires the ROS 2 overlay to be sourced (for rosbag2_py) and runs under the
system interpreter — conda's python lacks the ROS native modules, so this
file's shebang pins /usr/bin/python3:

    source /opt/ros/jazzy/setup.bash
    source workstation/install/setup.bash
    scripts/bag_to_mp4.py data/recordings/<bag-dir>
    scripts/bag_to_mp4.py data/recordings/<bag-dir> -o /tmp/out.mp4 --rgb-swap
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional

import cv2
import numpy as np
from rclpy.serialization import deserialize_message
from rosbag2_py import ConverterOptions, SequentialReader, StorageOptions
from sensor_msgs.msg import CompressedImage

DEFAULT_TOPIC = "/robot_0/camera/image/compressed"


def _open(bag: Path, storage_id: str) -> SequentialReader:
    reader = SequentialReader()
    reader.open(
        StorageOptions(uri=str(bag), storage_id=storage_id),
        ConverterOptions("", ""),
    )
    return reader


def render(
    bag: Path,
    topic: str,
    out: Path,
    storage_id: str,
    fps_override: Optional[float],
    rgb_swap: bool,
) -> int:
    # Pass 1: collect timestamps only (no JPEG decode) to derive real-time fps.
    reader = _open(bag, storage_id)
    stamps_ns: list[int] = []
    while reader.has_next():
        t, _data, ts = reader.read_next()
        if t == topic:
            stamps_ns.append(ts)

    if not stamps_ns:
        print(f"error: no messages on topic {topic!r} in {bag}", file=sys.stderr)
        return 1

    if fps_override:
        fps = fps_override
    elif len(stamps_ns) > 1:
        span_s = (stamps_ns[-1] - stamps_ns[0]) / 1e9
        fps = (len(stamps_ns) - 1) / span_s if span_s > 0 else 10.0
    else:
        fps = 10.0
    fps = round(fps, 2)

    # Pass 2: decode + write streaming, so memory stays bounded for long bags.
    reader = _open(bag, storage_id)
    writer: Optional[cv2.VideoWriter] = None
    written = corrupt = 0
    w = h = 0
    while reader.has_next():
        t, data, _ts = reader.read_next()
        if t != topic:
            continue
        msg = deserialize_message(data, CompressedImage)
        arr = np.frombuffer(bytes(msg.data), dtype=np.uint8)
        img = cv2.imdecode(arr, cv2.IMREAD_COLOR)  # JPEG -> BGR
        if img is None:
            corrupt += 1
            continue
        if rgb_swap:
            img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        if writer is None:
            h, w = img.shape[:2]
            writer = cv2.VideoWriter(
                str(out), cv2.VideoWriter_fourcc(*"mp4v"), fps, (w, h)
            )
            if not writer.isOpened():
                print(f"error: could not open VideoWriter for {out}", file=sys.stderr)
                return 1
        if img.shape[:2] != (h, w):  # guard against an odd-sized frame
            img = cv2.resize(img, (w, h))
        writer.write(img)
        written += 1

    if writer is not None:
        writer.release()

    print(f"wrote {out}")
    print(
        f"  frames={written}  corrupt={corrupt}  {w}x{h}  {fps} fps  "
        f"~{written / fps:.1f}s"
    )
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description="Render a bag's camera topic to .mp4")
    p.add_argument("bag", type=Path, help="bag directory")
    p.add_argument("-t", "--topic", default=DEFAULT_TOPIC, help="CompressedImage topic")
    p.add_argument(
        "-o", "--output", type=Path, help="output .mp4 (default: <bag-dir>.mp4)"
    )
    p.add_argument("--storage", default="mcap", help="rosbag2 storage id (default: mcap)")
    p.add_argument("--fps", type=float, help="override fps (default: from timestamps)")
    p.add_argument(
        "--rgb-swap", action="store_true", help="swap R/B channels if colors look wrong"
    )
    args = p.parse_args()

    if not args.bag.exists():
        print(f"error: bag not found: {args.bag}", file=sys.stderr)
        return 1
    out = args.output or args.bag.with_suffix(".mp4")
    return render(args.bag, args.topic, out, args.storage, args.fps, args.rgb_swap)


if __name__ == "__main__":
    raise SystemExit(main())
