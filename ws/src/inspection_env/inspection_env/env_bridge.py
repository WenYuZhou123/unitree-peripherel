import json
import math
from typing import Dict, Optional

import rclpy
from rclpy.node import Node

from inspection_msgs.msg import AirState, TempHumidity

try:
    import serial  # type: ignore
except ImportError:  # pragma: no cover - optional dependency
    serial = None


class EnvBridge(Node):
    def __init__(self) -> None:
        super().__init__("env_bridge")
        self.declare_parameter("mock_mode", True)
        self.declare_parameter("publish_rate_hz", 1.0)
        self.declare_parameter("air_sensor_port", "/dev/ttyUSB_air")
        self.declare_parameter("temp_humidity_port", "/dev/ttyUSB_temp")
        self.declare_parameter("serial_baudrate", 115200)

        self.mock_mode = bool(self.get_parameter("mock_mode").value)
        self.publish_rate_hz = max(float(self.get_parameter("publish_rate_hz").value), 0.2)
        self.air_sensor_port = str(self.get_parameter("air_sensor_port").value)
        self.temp_humidity_port = str(self.get_parameter("temp_humidity_port").value)
        self.serial_baudrate = int(self.get_parameter("serial_baudrate").value)

        self.air_pub = self.create_publisher(AirState, "/env/air_state", 10)
        self.temp_pub = self.create_publisher(TempHumidity, "/env/temperature_humidity", 10)
        self.air_serial = self._open_serial(self.air_sensor_port)
        self.temp_serial = self._open_serial(self.temp_humidity_port)
        self.timer = self.create_timer(1.0 / self.publish_rate_hz, self._tick)
        self.phase = 0.0

    def _open_serial(self, port: str):
        if self.mock_mode or serial is None:
            return None
        try:
            return serial.Serial(port, baudrate=self.serial_baudrate, timeout=0.2)
        except Exception as exc:  # pragma: no cover - hardware path
            self.get_logger().warning(f"Falling back to mock data for {port}: {exc}")
            return None

    def _tick(self) -> None:
        stamp = self.get_clock().now().to_msg()
        air_data = self._read_air_data() or self._mock_air_data()
        temp_data = self._read_temp_humidity_data() or self._mock_temp_humidity_data()

        air_msg = AirState()
        air_msg.header.stamp = stamp
        air_msg.header.frame_id = "air_sensor_link"
        air_msg.tvoc_ppb = float(air_data["tvoc_ppb"])
        air_msg.eco2_ppm = float(air_data["eco2_ppm"])
        air_msg.co_ppm = float(air_data["co_ppm"])
        air_msg.smoke_alarm = bool(air_data["smoke_alarm"])
        air_msg.device_ok = bool(air_data["device_ok"])
        air_msg.source_port = self.air_sensor_port
        self.air_pub.publish(air_msg)

        temp_msg = TempHumidity()
        temp_msg.header.stamp = stamp
        temp_msg.header.frame_id = "temp_humidity_sensor_link"
        temp_msg.temperature_c = float(temp_data["temperature_c"])
        temp_msg.humidity_rh = float(temp_data["humidity_rh"])
        temp_msg.device_ok = bool(temp_data["device_ok"])
        temp_msg.source_port = self.temp_humidity_port
        self.temp_pub.publish(temp_msg)

    def _read_air_data(self) -> Optional[Dict[str, float]]:
        return self._read_json_payload(
            self.air_serial,
            required_keys=("tvoc_ppb", "eco2_ppm", "co_ppm", "smoke_alarm"),
        )

    def _read_temp_humidity_data(self) -> Optional[Dict[str, float]]:
        return self._read_json_payload(
            self.temp_serial,
            required_keys=("temperature_c", "humidity_rh"),
        )

    def _read_json_payload(self, stream, required_keys):
        if not stream:
            return None

        try:
            line = stream.readline().decode("utf-8").strip()
            if not line:
                return None
            payload = json.loads(line)
            for key in required_keys:
                if key not in payload:
                    raise KeyError(key)
            payload["device_ok"] = True
            return payload
        except Exception as exc:  # pragma: no cover - hardware path
            self.get_logger().warning(f"Sensor payload parse failed, using mock data: {exc}")
            return None

    def _mock_air_data(self) -> Dict[str, float]:
        data = {
            "tvoc_ppb": 110.0 + 35.0 * math.sin(self.phase),
            "eco2_ppm": 520.0 + 60.0 * math.cos(self.phase * 0.8),
            "co_ppm": max(0.0, 2.0 + 0.7 * math.sin(self.phase * 0.4)),
            "smoke_alarm": math.sin(self.phase * 0.2) > 0.96,
            "device_ok": self.mock_mode,
        }
        self.phase += 0.15
        return data

    def _mock_temp_humidity_data(self) -> Dict[str, float]:
        return {
            "temperature_c": 24.0 + 2.0 * math.sin(self.phase * 0.5),
            "humidity_rh": 45.0 + 8.0 * math.cos(self.phase * 0.3),
            "device_ok": self.mock_mode,
        }


def main(args=None) -> None:
    rclpy.init(args=args)
    node = EnvBridge()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        for stream in (node.air_serial, node.temp_serial):
            if stream:
                stream.close()
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
