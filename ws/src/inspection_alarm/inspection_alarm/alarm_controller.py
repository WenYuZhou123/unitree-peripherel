from typing import Dict, Optional

import rclpy
from rclpy.node import Node
from std_msgs.msg import String

from inspection_alarm.by_f820 import ByF820Client
from inspection_alarm.serial_ports import detect_serial_port, open_serial
from inspection_msgs.srv import SetAlarmMode


class AlarmController(Node):
    MODES = {"idle", "gas_warning", "thermal_warning", "manual_test"}

    def __init__(self) -> None:
        super().__init__("alarm_controller")
        self.declare_parameter("mock_backend", True)
        self.declare_parameter("speaker_port", "")
        self.declare_parameter("speaker_baudrate", 9600)
        self.declare_parameter("speaker_volume", 30)
        self.declare_parameter("speaker_storage_target", "flash")
        self.declare_parameter("log_serial_frames", True)
        self.declare_parameter("speaker_tracks.gas_warning", 1)
        self.declare_parameter("speaker_tracks.thermal_warning", 2)
        self.declare_parameter("speaker_tracks.manual_test", 1)
        self.declare_parameter("speaker_channel", 0)
        self.declare_parameter("flash_red_channel", 1)
        self.declare_parameter("flash_blue_channel", 2)
        self.declare_parameter("fill_light_channel", 3)

        self.mock_backend = bool(self.get_parameter("mock_backend").value)
        self.speaker_port = str(self.get_parameter("speaker_port").value)
        self.speaker_baudrate = int(self.get_parameter("speaker_baudrate").value)
        self.speaker_volume = int(self.get_parameter("speaker_volume").value)
        self.speaker_storage_target = str(self.get_parameter("speaker_storage_target").value)
        self.log_serial_frames = bool(self.get_parameter("log_serial_frames").value)
        self.track_map = {
            "gas_warning": int(self.get_parameter("speaker_tracks.gas_warning").value),
            "thermal_warning": int(
                self.get_parameter("speaker_tracks.thermal_warning").value
            ),
            "manual_test": int(self.get_parameter("speaker_tracks.manual_test").value),
        }
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
        self.speaker_error: Optional[str] = None
        self.serial_stream = self._open_serial_if_possible()
        self.speaker = ByF820Client(self.serial_stream) if self.serial_stream else None
        self._publish_status()

    def _resolve_speaker_port(self) -> str:
        port = detect_serial_port(self.speaker_port)
        if not self.speaker_port:
            self.get_logger().info(f"Auto-detected speaker serial port: {port}")
        return port

    def _open_serial_if_possible(self):
        if self.mock_backend:
            return None
        try:
            port = self._resolve_speaker_port()
            self.speaker_port = port
            return open_serial(port, self.speaker_baudrate, timeout=0.5)
        except Exception as exc:  # pragma: no cover - hardware path
            self.speaker_error = str(exc)
            self.get_logger().error(f"Speaker serial backend unavailable: {exc}")
            return None

    def _set_mode(self, request, response):
        requested_mode = request.mode.strip().lower()
        if requested_mode not in self.MODES:
            response.success = False
            response.message = f"Unsupported mode '{request.mode}'."
            return response

        state = self._mode_to_state(requested_mode, enabled=request.enabled)
        self.current_mode = requested_mode if request.enabled else "idle"
        self.current_state = state

        success, message = self._apply_state()
        self._publish_status()
        response.success = success
        response.message = message
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

    def _log_frame(self, label: str, frame: bytes, response: Optional[object] = None) -> None:
        if not self.log_serial_frames:
            return
        message = f"{label} TX={frame.hex(' ')}"
        if response is not None:
            message += f" RX={response.raw.hex(' ')} ASCII={response.text}"
        self.get_logger().info(message)

    def _maybe_switch_storage(self) -> None:
        target = self.speaker_storage_target.strip().lower()
        if target in {"", "none", "current"}:
            return
        frame = self.speaker.switch_storage(target)
        self._log_frame(f"switch_storage[{target}]", frame)

    def _query_state_snapshot(self) -> None:
        if self.speaker is None:
            return
        try:
            device = self.speaker.query_device()
            self._log_frame("query_device", device.request, device)
            volume = self.speaker.query_volume()
            self._log_frame("query_volume", volume.request, volume)
            status = self.speaker.query_play_status()
            self._log_frame("query_play_status", status.request, status)
        except Exception as exc:  # pragma: no cover - hardware path
            self.get_logger().warning(f"Speaker query failed: {exc}")

    def _apply_state(self):
        payload = {
            "mode": self.current_mode,
            "channels": {
                channel: {"index": self.channels[channel], "enabled": enabled}
                for channel, enabled in self.current_state.items()
            },
        }

        if self.speaker is None:
            if not self.mock_backend:
                reason = self.speaker_error or "serial port not available"
                return False, f"Speaker serial backend unavailable: {reason}"
            self.get_logger().info(f"Mock alarm payload: {payload}")
            return True, f"Alarm mode set to {self.current_mode}."

        try:
            if self.current_mode == "idle" or not self.current_state["speaker"]:
                frame = self.speaker.stop()
                self._log_frame("stop", frame)
                self._query_state_snapshot()
            else:
                self._maybe_switch_storage()
                frame = self.speaker.set_volume(self.speaker_volume)
                self._log_frame("set_volume", frame)
                track_id = self.track_map.get(self.current_mode, self.track_map["manual_test"])
                frame = self.speaker.play_track(track_id)
                self._log_frame(f"play_track[{track_id}]", frame)
                self._query_state_snapshot()
            return True, f"Alarm mode set to {self.current_mode}."
        except Exception as exc:  # pragma: no cover - hardware path
            self.get_logger().error(f"BY-F820 command failed: {exc}")
            return False, f"Failed to drive speaker: {exc}"

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
        if node.serial_stream:
            node.serial_stream.close()
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
