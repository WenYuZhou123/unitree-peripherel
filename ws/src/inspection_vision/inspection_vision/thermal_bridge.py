import math
import struct
from typing import Optional

import numpy as np
import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Image

from inspection_msgs.msg import ThermalHotspot
from inspection_vision.senxor_usb import SenxorUsbCamera


class ThermalBridge(Node):
    def __init__(self) -> None:
        super().__init__("thermal_bridge")
        self.declare_parameter("backend", "mock")
        self.declare_parameter("publish_rate_hz", 5.0)
        self.declare_parameter("fps", 10.0)
        self.declare_parameter("hflip", False)
        self.declare_parameter("threshold_temp_c", 55.0)
        self.declare_parameter("allow_mock_fallback", True)
        self.declare_parameter("frame_id", "thermal_link")
        self.declare_parameter("width", 80)
        self.declare_parameter("height", 62)
        self.declare_parameter("usb_port", "")

        requested_backend = str(self.get_parameter("backend").value)
        self.publish_rate_hz = max(float(self.get_parameter("publish_rate_hz").value), 1.0)
        self.fps = max(float(self.get_parameter("fps").value), 1.0)
        self.hflip = bool(self.get_parameter("hflip").value)
        self.threshold_temp_c = float(self.get_parameter("threshold_temp_c").value)
        self.allow_mock_fallback = bool(self.get_parameter("allow_mock_fallback").value)
        self.frame_id = str(self.get_parameter("frame_id").value)
        self.width = int(self.get_parameter("width").value)
        self.height = int(self.get_parameter("height").value)
        self.usb_port = str(self.get_parameter("usb_port").value)

        self.image_pub = self.create_publisher(Image, "/thermal/image_temperature", 10)
        self.preview_pub = self.create_publisher(Image, "/thermal/image_preview", 10)
        self.hotspot_pub = self.create_publisher(ThermalHotspot, "/thermal/hotspot", 10)

        self.camera: Optional[SenxorUsbCamera] = None
        self.backend = self._configure_backend(requested_backend)
        self.timer = self.create_timer(1.0 / self.publish_rate_hz, self._tick)
        self.phase = 0.0

    def _configure_backend(self, backend: str) -> str:
        if backend == "senxor_usb":
            try:
                self.camera = SenxorUsbCamera.open(usb_port=self.usb_port, fps=self.fps)
                self.width = self.camera.width
                self.height = self.camera.height
                self.get_logger().info(
                    f"SenXor thermal camera connected over USB at {self.camera.stream.port}"
                )
                return "senxor_usb"
            except Exception as exc:  # pragma: no cover - hardware path
                if self.allow_mock_fallback:
                    self.get_logger().warning(
                        f"SenXor USB backend unavailable, using mock frames instead: {exc}"
                    )
                    return "mock"
                self.get_logger().error(f"SenXor USB backend unavailable: {exc}")
                return "unavailable"
        return "mock"

    def _tick(self) -> None:
        frame = self._read_frame()
        if frame is None:
            return

        stamp = self.get_clock().now().to_msg()
        image = Image()
        image.header.stamp = stamp
        image.header.frame_id = self.frame_id
        image.height = self.height
        image.width = self.width
        image.encoding = "32FC1"
        image.is_bigendian = 0
        image.step = self.width * 4
        image.data = struct.pack(f"<{frame.size}f", *frame.astype(np.float32).reshape(-1))
        self.image_pub.publish(image)

        preview = Image()
        preview.header = image.header
        preview.height = self.height
        preview.width = self.width
        preview.encoding = "mono8"
        preview.is_bigendian = 0
        preview.step = self.width
        preview.data = self._to_preview(frame).tobytes()
        self.preview_pub.publish(preview)

        max_temp = float(np.max(frame))
        min_temp = float(np.min(frame))
        hot_index = int(np.argmax(frame))

        hotspot = ThermalHotspot()
        hotspot.header = image.header
        hotspot.max_temp_c = max_temp
        hotspot.min_temp_c = min_temp
        hotspot.hotspot_u = hot_index % self.width
        hotspot.hotspot_v = hot_index // self.width
        hotspot.alarm = max_temp >= self.threshold_temp_c
        self.hotspot_pub.publish(hotspot)

    def _read_frame(self):
        if self.backend == "senxor_usb" and self.camera is not None:
            try:
                frame = self.camera.read_frame()
                if self.hflip:
                    frame = np.flip(frame, axis=1)
                return frame.astype(np.float32)
            except Exception as exc:  # pragma: no cover - hardware path
                self.get_logger().warning(f"SenXor frame read failed: {exc}")
                if self.allow_mock_fallback:
                    self.backend = "mock"
                else:
                    return None
        if self.backend == "mock":
            return self._mock_frame()
        return None

    def _mock_frame(self):
        frame = np.zeros((self.height, self.width), dtype=np.float32)
        hot_u = int((math.sin(self.phase) * 0.5 + 0.5) * (self.width - 1))
        hot_v = int((math.cos(self.phase * 0.7) * 0.5 + 0.5) * (self.height - 1))
        for v in range(self.height):
            for u in range(self.width):
                base = 27.0 + 2.5 * math.sin((u / max(self.width - 1, 1)) * math.pi)
                dist = abs(u - hot_u) + abs(v - hot_v)
                hotspot = max(0.0, 42.0 - dist * 2.0)
                frame[v, u] = base + hotspot
        self.phase += 0.2
        return frame

    def _to_preview(self, frame: np.ndarray) -> np.ndarray:
        low = float(np.min(frame))
        high = float(np.max(frame))
        if high - low < 1e-6:
            return np.zeros((self.height, self.width), dtype=np.uint8)
        preview = ((frame - low) / (high - low) * 255.0).clip(0, 255)
        return preview.astype(np.uint8)


def main(args=None) -> None:
    rclpy.init(args=args)
    node = ThermalBridge()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        if node.camera is not None:
            node.camera.stop()
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
