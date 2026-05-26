"""Receives camera + ultrasonic UDP streams from the Pi and republishes
them on ROS 2 topics under /<robot_namespace>/.

Two background threads (one per UDP socket) decode incoming datagrams
and publish directly. rclpy publishers are thread-safe, so no queue +
timer indirection is needed at Phase-1 rates (~10 Hz).
"""
from __future__ import annotations

import io
import socket
import struct
import threading
from typing import Optional

import numpy as np
import rclpy
from PIL import Image as PILImage
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import Image, Range

# Wire formats — must match pi/crawler_node.py exactly.
CAMERA_HEADER = struct.Struct("!IQI")        # seq, ts_ms, jpeg_len
ULTRASONIC_PACKET = struct.Struct("!IQf")    # seq, ts_ms, distance_cm


class UdpTelemetryNode(Node):
    def __init__(self) -> None:
        super().__init__("udp_telemetry_node")

        self.declare_parameter("camera_port", 5005)
        self.declare_parameter("ultrasonic_port", 5006)
        self.declare_parameter("robot_namespace", "robot_0")
        self.declare_parameter("camera_frame_id", "camera_link")
        self.declare_parameter("ultrasonic_frame_id", "ultrasonic_link")
        self.declare_parameter("ultrasonic_min_range_m", 0.02)
        self.declare_parameter("ultrasonic_max_range_m", 4.0)
        self.declare_parameter("ultrasonic_fov_rad", 0.26)

        camera_port: int = self.get_parameter("camera_port").value
        ultrasonic_port: int = self.get_parameter("ultrasonic_port").value
        ns: str = self.get_parameter("robot_namespace").value
        self.camera_frame_id: str = self.get_parameter("camera_frame_id").value
        self.ultrasonic_frame_id: str = self.get_parameter("ultrasonic_frame_id").value
        self.min_range: float = float(self.get_parameter("ultrasonic_min_range_m").value)
        self.max_range: float = float(self.get_parameter("ultrasonic_max_range_m").value)
        self.fov: float = float(self.get_parameter("ultrasonic_fov_rad").value)

        # Sensor-data QoS (BEST_EFFORT) matches typical camera/range publishers.
        self.image_pub = self.create_publisher(
            Image, f"/{ns}/camera/image", qos_profile_sensor_data,
        )
        self.range_pub = self.create_publisher(
            Range, f"/{ns}/ultrasonic/range", qos_profile_sensor_data,
        )

        self._stop = threading.Event()

        self._camera_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        # Generous receive buffer so a stalled main thread doesn't drop frames.
        self._camera_sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 1 << 20)
        self._camera_sock.bind(("0.0.0.0", camera_port))
        self._camera_sock.settimeout(1.0)

        self._range_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._range_sock.bind(("0.0.0.0", ultrasonic_port))
        self._range_sock.settimeout(1.0)

        threading.Thread(
            target=self._camera_loop, name="camera-rx", daemon=True,
        ).start()
        threading.Thread(
            target=self._range_loop, name="range-rx", daemon=True,
        ).start()

        self.get_logger().info(
            f"Listening UDP camera={camera_port} ultrasonic={ultrasonic_port}; "
            f"publishing under /{ns}/"
        )

    def _camera_loop(self) -> None:
        last_seq: Optional[int] = None
        gap_warnings = 0
        while not self._stop.is_set():
            try:
                data, _addr = self._camera_sock.recvfrom(65535)
            except socket.timeout:
                continue
            except OSError as e:
                self.get_logger().warning(f"camera recv error: {e}")
                continue
            if len(data) < CAMERA_HEADER.size:
                continue
            seq, _ts_ms, jpeg_len = CAMERA_HEADER.unpack_from(data, 0)
            jpeg = data[CAMERA_HEADER.size:CAMERA_HEADER.size + jpeg_len]
            if len(jpeg) != jpeg_len:
                self.get_logger().warning(
                    f"truncated frame seq={seq}: {len(jpeg)}/{jpeg_len}B"
                )
                continue
            try:
                pil = PILImage.open(io.BytesIO(jpeg))
                pil.load()
                if pil.mode != "RGB":
                    pil = pil.convert("RGB")
                arr = np.asarray(pil, dtype=np.uint8)
            except Exception as e:
                self.get_logger().warning(f"JPEG decode failed seq={seq}: {e}")
                continue

            # Optional debug: warn if more than 3 frames dropped between callbacks.
            if last_seq is not None and seq - last_seq > 3:
                gap_warnings += 1
                if gap_warnings <= 5 or gap_warnings % 100 == 0:
                    self.get_logger().info(
                        f"camera seq gap: {seq - last_seq - 1} dropped "
                        f"(total warns={gap_warnings})"
                    )
            last_seq = seq

            msg = Image()
            msg.header.stamp = self.get_clock().now().to_msg()
            msg.header.frame_id = self.camera_frame_id
            msg.height = int(arr.shape[0])
            msg.width = int(arr.shape[1])
            msg.encoding = "rgb8"
            msg.is_bigendian = 0
            msg.step = msg.width * 3
            msg.data = arr.tobytes()
            self.image_pub.publish(msg)

    def _range_loop(self) -> None:
        while not self._stop.is_set():
            try:
                data, _addr = self._range_sock.recvfrom(64)
            except socket.timeout:
                continue
            except OSError as e:
                self.get_logger().warning(f"range recv error: {e}")
                continue
            if len(data) != ULTRASONIC_PACKET.size:
                continue
            _seq, _ts_ms, distance_cm = ULTRASONIC_PACKET.unpack(data)
            msg = Range()
            msg.header.stamp = self.get_clock().now().to_msg()
            msg.header.frame_id = self.ultrasonic_frame_id
            msg.radiation_type = Range.ULTRASOUND
            msg.field_of_view = self.fov
            msg.min_range = self.min_range
            msg.max_range = self.max_range
            # SunFounder returns -1 / -2 on read failure; REP-117 says use
            # +inf for "no return" so consumers can branch on it.
            if distance_cm < 0:
                msg.range = float("+inf")
            else:
                msg.range = float(distance_cm) / 100.0
            self.range_pub.publish(msg)

    def destroy_node(self) -> bool:
        self._stop.set()
        try:
            self._camera_sock.close()
            self._range_sock.close()
        except Exception:
            pass
        return super().destroy_node()


def main(args: Optional[list[str]] = None) -> None:
    rclpy.init(args=args)
    node = UdpTelemetryNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
