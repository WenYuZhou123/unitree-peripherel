import json
from typing import Dict

import rclpy
from rclpy.node import Node
from std_msgs.msg import String

from inspection_msgs.srv import SetAlarmMode

try:
    import serial  # type: ignore
except ImportError:  # pragma: no cover - optional dependency
    serial = None


class AlarmController(Node):
    MODES = {"idle", "gas_warning", "thermal_warning", "manual_test"}

    def __init__(self) -> None:
        super().__init__("alarm_controller")
        self.declare_parameter("mock_backend", True)
        self.declare_parameter("controller_device", "/dev/ttyUSB_alarm")
        self.declare_parameter("controller_baudrate", 115200)
        self.declare_parameter("speaker_channel", 0)
        self.declare_parameter("flash_red_channel", 1)
        self.declare_parameter("flash_blue_channel", 2)
        self.declare_parameter("fill_light_channel", 3)

        self.mock_backend = bool(self.get_parameter("mock_backend").value)
        self.controller_device = str(self.get_parameter("controller_device").value)
        self.controller_baudrate = int(self.get_parameter("controller_baudrate").value)
        self.channels = {
            "speaker": int(self.get_parameter("speaker_channel").value),
            "flash_red": int(self.get_parameter("flash_red_channel").value),
            "flash_blue": int(self.get_parameter("flash_blue_channel").value),
            "fill_light": int(self.get_parameter("fill_light_channel").value),
        }
        self.current_mode = "idle"
        self.current_state = self._mode_to_state("idle", enabled=False)
        self.status_pub = self.create_publisher(String, "/alarm/current_mode", 10)
        self.service = self.create_service(SetAlarmMode, "/alarm/set_mode", self._set_mode)
        self.serial_conn = self._open_serial_if_possible()
        self._publish_status()

    def _open_serial_if_possible(self):
        if self.mock_backend or serial is None:
            return None
        try:
            return serial.Serial(
                self.controller_device, baudrate=self.controller_baudrate, timeout=0.2
            )
        except Exception as exc:  # pragma: no cover - hardware path
            self.get_logger().warning(
                f"Falling back to mock alarm backend because serial open failed: {exc}"
            )
            return None

    def _set_mode(self, request, response):
        requested_mode = request.mode.strip().lower()
        if requested_mode not in self.MODES:
            response.success = False
            response.message = f"Unsupported mode '{request.mode}'."
            return response

        state = self._mode_to_state(requested_mode, enabled=request.enabled)
        self.current_mode = requested_mode if request.enabled else "idle"
        self._apply_state(state)
        self.current_state = state
        self._publish_status()
        response.success = True
        response.message = f"Alarm mode set to {self.current_mode}."
        return response

    def _mode_to_state(self, mode: str, enabled: bool) -> Dict[str, bool]:
        if not enabled or mode == "idle":
            return {name: False for name in self.channels}
        if mode == "gas_warning":
            return {
                "speaker": True,
                "flash_red": True,
                "flash_blue": True,
                "fill_light": False,
            }
        if mode == "thermal_warning":
            return {
                "speaker": True,
                "flash_red": True,
                "flash_blue": False,
                "fill_light": True,
            }
        return {name: True for name in self.channels}

    def _apply_state(self, state: Dict[str, bool]) -> None:
        payload = {
            "mode": self.current_mode,
            "channels": {
                channel: {"index": self.channels[channel], "enabled": enabled}
                for channel, enabled in state.items()
            },
        }
        if self.serial_conn:
            self.serial_conn.write((json.dumps(payload) + "\n").encode("utf-8"))
        else:
            self.get_logger().info(f"Mock alarm payload: {payload}")

    def _publish_status(self) -> None:
        msg = String()
        msg.data = self.current_mode
        self.status_pub.publish(msg)


def main(args=None) -> None:
    rclpy.init(args=args)
    node = AlarmController()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        if node.serial_conn:
            node.serial_conn.close()
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
