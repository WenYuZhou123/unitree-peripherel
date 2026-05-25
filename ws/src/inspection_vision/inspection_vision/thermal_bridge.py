import json
import math
import struct
from typing import List, Optional

import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Image

from inspection_msgs.msg import ThermalHotspot

try:
    import serial  # type: ignore
except ImportError:  # pragma: no cover - optional dependency
    serial = None


class ThermalBridge(Node):
    def __init__(self) -> None:
        super().__init__("thermal_bridge")
        self.declare_parameter("mock_mode", True)
        self.declare_parameter("publish_rate_hz", 5.0)
        self.declare_parameter("threshold_temp_c", 55.0)
        self.declare_parameter("frame_id", "thermal_link")
        self.declare_parameter("width", 80)
        self.declare_parameter("height", 62)
        self.declare_parameter("device_path", "/dev/ttyACM_thermal")

        self.mock_mode = bool(self.get_parameter("mock_mode").value)
        self.publish_rate_hz = max(float(self.get_parameter("publish_rate_hz").value), 1.0)
        self.threshold_temp_c = float(self.get_parameter("threshold_temp_c").value)
        self.frame_id = str(self.get_parameter("frame_id").value)
        self.width = int(self.get_parameter("width").value)
        self.height = int(self.get_parameter("height").value)
        self.device_path = str(self.get_parameter("device_path").value)

        self.image_pub = self.create_publisher(Image, "/thermal/image_temperature", 10)
        self.hotspot_pub = self.create_publisher(ThermalHotspot, "/thermal/hotspot", 10)
        self.timer = self.create_timer(1.0 / self.publish_rate_hz, self._tick)
        self.serial_conn = self._open_serial_if_possible()
        self.phase = 0.0

    def _open_serial_if_possible(self):
        if self.mock_mode or serial is None:
            return None

        try:
            return serial.Serial(self.device_path, baudrate=115200, timeout=0.2)
        except Exception as exc:  # pragma: no cover - hardware path
            self.get_logger().warning(
                f"Falling back to mock thermal frames because serial open failed: {exc}"
            )
            return None

    def _tick(self) -> None:
        frame = self._read_device_frame() if self.serial_conn else self._mock_frame()
        stamp = self.get_clock().now().to_msg()

        image = Image()
        image.header.stamp = stamp
        image.header.frame_id = self.frame_id
        image.height = self.height
        image.width = self.width
        image.encoding = "32FC1"
        image.is_bigendian = 0
        image.step = self.width * 4
        image.data = struct.pack(f"<{len(frame)}f", *frame)
        self.image_pub.publish(image)

        max_temp = max(frame)
        min_temp = min(frame)
        hot_index = frame.index(max_temp)

        hotspot = ThermalHotspot()
        hotspot.header = image.header
        hotspot.max_temp_c = float(max_temp)
        hotspot.min_temp_c = float(min_temp)
        hotspot.hotspot_u = hot_index % self.width
        hotspot.hotspot_v = hot_index // self.width
        hotspot.alarm = max_temp >= self.threshold_temp_c
        self.hotspot_pub.publish(hotspot)

    def _read_device_frame(self) -> Optional[List[float]]:
        if not self.serial_conn:
            return None

        try:
            line = self.serial_conn.readline().decode("utf-8").strip()
            if not line:
                return None
            payload = json.loads(line)
            values = payload.get("temperatures", [])
            if len(values) != self.width * self.height:
                raise ValueError("unexpected thermal payload size")
            return [float(v) for v in values]
        except Exception as exc:  # pragma: no cover - hardware path
            self.get_logger().warning(f"Thermal payload parse failed, using mock frame: {exc}")
            return self._mock_frame()

    def _mock_frame(self) -> List[float]:
        frame = []
        hot_u = int((math.sin(self.phase) * 0.5 + 0.5) * (self.width - 1))
        hot_v = int((math.cos(self.phase * 0.7) * 0.5 + 0.5) * (self.height - 1))
        for v in range(self.height):
            for u in range(self.width):
                base = 27.0 + 2.5 * math.sin((u / max(self.width - 1, 1)) * math.pi)
                dist = abs(u - hot_u) + abs(v - hot_v)
                hotspot = max(0.0, 42.0 - dist * 2.0)
                frame.append(base + hotspot)
        self.phase += 0.2
        return frame


def main(args=None) -> None:
    rclpy.init(args=args)
    node = ThermalBridge()
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
