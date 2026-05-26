"""Subscribes to /<robot_namespace>/cmd (std_msgs/String holding JSON)
and forwards each message to the Pi over a single persistent TCP
connection. Lazy-connect on first publish; on send failure, the socket
is torn down and the next publish reconnects.

Trade-off: a single in-flight send blocks the rclpy executor on this
node. At Phase-1 rates (~5 Hz, ~50-byte payloads) on a LAN this is
fine. If we ever push commands at high rate or over higher-latency
links, move the send to a worker thread fed by a queue.
"""
from __future__ import annotations

import socket
import threading
from typing import Optional

import rclpy
from rclpy.node import Node
from std_msgs.msg import String


class CmdBridgeNode(Node):
    def __init__(self) -> None:
        super().__init__("cmd_bridge_node")

        self.declare_parameter("pi_ip", "192.168.1.19")
        self.declare_parameter("command_port", 5007)
        self.declare_parameter("robot_namespace", "robot_0")
        self.declare_parameter("connect_timeout_s", 2.0)

        self.pi_ip: str = self.get_parameter("pi_ip").value
        self.command_port: int = self.get_parameter("command_port").value
        ns: str = self.get_parameter("robot_namespace").value
        self.connect_timeout: float = float(
            self.get_parameter("connect_timeout_s").value
        )

        self._sock_lock = threading.Lock()
        self._sock: Optional[socket.socket] = None

        self.sub = self.create_subscription(
            String, f"/{ns}/cmd", self._on_cmd, 10,
        )
        self.get_logger().info(
            f"Subscribing /{ns}/cmd; forwarding to "
            f"{self.pi_ip}:{self.command_port} over TCP"
        )

    def _connect_locked(self) -> bool:
        """Caller must hold _sock_lock. Returns True if connected."""
        try:
            s = socket.create_connection(
                (self.pi_ip, self.command_port), timeout=self.connect_timeout,
            )
            s.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
            # Cap send blocking so a wedged socket doesn't stall the executor.
            s.settimeout(self.connect_timeout)
            self._sock = s
            self.get_logger().info(
                f"connected to {self.pi_ip}:{self.command_port}"
            )
            return True
        except OSError as e:
            self.get_logger().warning(
                f"connect to {self.pi_ip}:{self.command_port} failed: {e}"
            )
            self._sock = None
            return False

    def _on_cmd(self, msg: String) -> None:
        line = (msg.data or "").strip()
        if not line:
            return
        payload = (line + "\n").encode("utf-8")
        with self._sock_lock:
            if self._sock is None and not self._connect_locked():
                return
            assert self._sock is not None
            try:
                self._sock.sendall(payload)
            except OSError as e:
                self.get_logger().warning(
                    f"send failed: {e}; will reconnect on next publish"
                )
                try:
                    self._sock.close()
                except Exception:
                    pass
                self._sock = None

    def destroy_node(self) -> bool:
        with self._sock_lock:
            if self._sock is not None:
                try:
                    self._sock.close()
                except Exception:
                    pass
                self._sock = None
        return super().destroy_node()


def main(args: Optional[list[str]] = None) -> None:
    rclpy.init(args=args)
    node = CmdBridgeNode()
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
