from dataclasses import dataclass

import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Image


@dataclass
class ImageSpec:
    width: int
    height: int
    fps: float
    frame_id: str
    label: str


class CameraPlaceholder(Node):
    def __init__(self) -> None:
        super().__init__("camera_placeholder")
        self.declare_parameter("width", 1280)
        self.declare_parameter("height", 720)
        self.declare_parameter("fps", 15.0)
        self.declare_parameter("frame_id", "camera_optical_frame")
        self.declare_parameter("label", "camera")

        self.spec = ImageSpec(
            width=int(self.get_parameter("width").value),
            height=int(self.get_parameter("height").value),
            fps=max(float(self.get_parameter("fps").value), 1.0),
            frame_id=str(self.get_parameter("frame_id").value),
            label=str(self.get_parameter("label").value),
        )
        self.publisher = self.create_publisher(Image, "image_raw", 10)
        self.timer = self.create_timer(1.0 / self.spec.fps, self._publish_frame)
        self.sequence = 0

    def _publish_frame(self) -> None:
        msg = Image()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.header.frame_id = self.spec.frame_id
        msg.height = self.spec.height
        msg.width = self.spec.width
        msg.encoding = "rgb8"
        msg.is_bigendian = 0
        msg.step = self.spec.width * 3
        value = self.sequence % 255
        msg.data = bytes([value, 64, 192]) * (self.spec.width * self.spec.height)
        self.publisher.publish(msg)
        self.sequence += 1


def main(args=None) -> None:
    rclpy.init(args=args)
    node = CameraPlaceholder()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
