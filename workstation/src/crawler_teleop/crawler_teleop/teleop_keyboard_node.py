"""Keyboard teleop for the Pi-Crawler.

Maintains a current "intent" string and publishes it as JSON to
/<robot_namespace>/cmd at a fixed rate (default 5 Hz). The fixed rate
keeps the Pi's 1 s heartbeat from tripping while the user holds an
action; keystrokes only mutate the intent, they don't gate publishes.

Keys:
    w / a / s / d : forward / turn_left / backward / turn_right
    space         : stop  (Pi will sit)
    + / =         : speed up
    - / _         : speed down
    q  or  Ctrl-C : quit (publishes one final stop, then exits)
"""
from __future__ import annotations

import json
import select
import sys
import termios
import threading
import tty
from typing import Optional

import rclpy
from rclpy.node import Node
from std_msgs.msg import String

KEY_TO_ACTION = {
    "w": "forward",
    "s": "backward",
    "a": "turn_left",
    "d": "turn_right",
    " ": "stop",
}
SPEED_UP_KEYS = {"+", "="}
SPEED_DOWN_KEYS = {"-", "_"}
QUIT_KEYS = {"q", "\x03"}  # 'q' or Ctrl-C

HELP_TEXT = """
Pi-Crawler keyboard teleop
  w / a / s / d : forward / turn_left / backward / turn_right
  space         : stop (sit)
  + / -         : adjust speed (10..100)
  q             : quit
Publishing at the configured rate so the Pi heartbeat (1 s) doesn't trip.
"""


class TeleopNode(Node):
    def __init__(self) -> None:
        super().__init__("teleop_keyboard_node")

        self.declare_parameter("robot_namespace", "robot_0")
        self.declare_parameter("default_speed", 80)
        self.declare_parameter("publish_hz", 5.0)
        self.declare_parameter("speed_step", 10)

        ns: str = self.get_parameter("robot_namespace").value
        self.speed: int = int(self.get_parameter("default_speed").value)
        publish_hz: float = float(self.get_parameter("publish_hz").value)
        self.speed_step: int = int(self.get_parameter("speed_step").value)

        self._state_lock = threading.Lock()
        self._intent: str = "stop"
        self._stop = threading.Event()

        self.pub = self.create_publisher(String, f"/{ns}/cmd", 10)
        self.create_timer(1.0 / publish_hz, self._tick)

        self.get_logger().info(
            f"publishing to /{ns}/cmd at {publish_hz:.1f}Hz, "
            f"initial speed={self.speed}"
        )
        sys.stdout.write(HELP_TEXT)
        sys.stdout.flush()

        threading.Thread(
            target=self._keyboard_loop, name="teleop-kb", daemon=True,
        ).start()

    def _tick(self) -> None:
        with self._state_lock:
            intent = self._intent
            speed = self.speed
        msg = String()
        msg.data = json.dumps({"action": intent, "speed": speed})
        self.pub.publish(msg)

    def _print_status(self) -> None:
        # \r to overwrite the same status line; readers can still scroll log lines.
        sys.stdout.write(
            f"\rintent={self._intent:<11s} speed={self.speed:<3d}    "
        )
        sys.stdout.flush()

    def _keyboard_loop(self) -> None:
        fd = sys.stdin.fileno()
        try:
            old_attrs = termios.tcgetattr(fd)
        except termios.error:
            self.get_logger().error(
                "stdin is not a tty; teleop needs to run in a terminal "
                "(use `ros2 run`, not `ros2 launch`)"
            )
            self._stop.set()
            rclpy.shutdown()
            return
        try:
            tty.setcbreak(fd)
            while not self._stop.is_set():
                if not select.select([fd], [], [], 0.1)[0]:
                    continue
                ch = sys.stdin.read(1)
                if not ch:
                    continue
                if ch in QUIT_KEYS:
                    with self._state_lock:
                        self._intent = "stop"
                    # Publish stop immediately so robot sits before we tear down.
                    self._tick()
                    sys.stdout.write("\nquitting; sent stop.\n")
                    sys.stdout.flush()
                    self._stop.set()
                    rclpy.shutdown()
                    return
                if ch in KEY_TO_ACTION:
                    with self._state_lock:
                        self._intent = KEY_TO_ACTION[ch]
                elif ch in SPEED_UP_KEYS:
                    with self._state_lock:
                        self.speed = min(100, self.speed + self.speed_step)
                elif ch in SPEED_DOWN_KEYS:
                    with self._state_lock:
                        self.speed = max(10, self.speed - self.speed_step)
                else:
                    continue  # ignore other keys silently
                self._print_status()
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_attrs)
            sys.stdout.write("\n")
            sys.stdout.flush()

    def destroy_node(self) -> bool:
        self._stop.set()
        return super().destroy_node()


def main(args: Optional[list[str]] = None) -> None:
    rclpy.init(args=args)
    node = TeleopNode()
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
