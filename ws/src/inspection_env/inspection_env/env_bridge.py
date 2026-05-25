import math

import rclpy
from rclpy.node import Node

from inspection_env.cj702 import Cj702Sample, parse_cj702_frame, read_cj702_frame
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
        self.declare_parameter("serial_port", "/dev/ttyUSB_cj702")
        self.declare_parameter("baudrate", 9600)
        self.declare_parameter("frame_timeout", 0.5)

        self.mock_mode = bool(self.get_parameter("mock_mode").value)
        self.publish_rate_hz = max(float(self.get_parameter("publish_rate_hz").value), 0.2)
        self.serial_port = str(self.get_parameter("serial_port").value)
        self.baudrate = int(self.get_parameter("baudrate").value)
        self.frame_timeout = max(float(self.get_parameter("frame_timeout").value), 0.1)

        self.air_pub = self.create_publisher(AirState, "/env/air_state", 10)
        self.temp_pub = self.create_publisher(TempHumidity, "/env/temperature_humidity", 10)
        self.serial_stream = self._open_serial()
        self.timer = self.create_timer(1.0 / self.publish_rate_hz, self._tick)
        self.phase = 0.0

    def _open_serial(self):
        if self.mock_mode or serial is None:
            return None
        try:
            return serial.Serial(
                self.serial_port,
                baudrate=self.baudrate,
                timeout=self.frame_timeout,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
            )
        except Exception as exc:  # pragma: no cover - hardware path
            self.get_logger().warning(
                f"Falling back to mock CJ702 data because port open failed: {exc}"
            )
            return None

    def _tick(self) -> None:
        stamp = self.get_clock().now().to_msg()
        sample, device_ok = self._get_sample()

        air_msg = AirState()
        air_msg.header.stamp = stamp
        air_msg.header.frame_id = "air_sensor_link"
        air_msg.eco2_ppm = sample.eco2_ppm
        air_msg.ech2o_ug_m3 = sample.ech2o_ug_m3
        air_msg.tvoc_ug_m3 = sample.tvoc_ug_m3
        air_msg.pm25_ug_m3 = sample.pm25_ug_m3
        air_msg.pm10_ug_m3 = sample.pm10_ug_m3
        air_msg.device_ok = device_ok
        air_msg.source_port = self.serial_port
        self.air_pub.publish(air_msg)

        temp_msg = TempHumidity()
        temp_msg.header.stamp = stamp
        temp_msg.header.frame_id = "temp_humidity_sensor_link"
        temp_msg.temperature_c = sample.temperature_c
        temp_msg.humidity_rh = sample.humidity_rh
        temp_msg.device_ok = device_ok
        temp_msg.source_port = self.serial_port
        self.temp_pub.publish(temp_msg)

    def _get_sample(self):
        if self.serial_stream is not None:
            try:
                frame = read_cj702_frame(self.serial_stream)
                if frame is None:
                    raise ValueError("CJ702 frame timeout")
                return parse_cj702_frame(frame), True
            except Exception as exc:  # pragma: no cover - hardware path
                self.get_logger().warning(f"CJ702 parse failed: {exc}")
                return self._invalid_sample(), False
        return self._mock_sample(), True

    def _mock_sample(self) -> Cj702Sample:
        sample = Cj702Sample(
            eco2_ppm=520.0 + 60.0 * math.cos(self.phase * 0.8),
            ech2o_ug_m3=24.0 + 4.0 * math.sin(self.phase * 0.6),
            tvoc_ug_m3=110.0 + 35.0 * math.sin(self.phase),
            pm25_ug_m3=8.0 + 2.0 * math.sin(self.phase * 0.5),
            pm10_ug_m3=14.0 + 3.0 * math.cos(self.phase * 0.4),
            temperature_c=24.0 + 2.0 * math.sin(self.phase * 0.5),
            humidity_rh=45.0 + 8.0 * math.cos(self.phase * 0.3),
        )
        self.phase += 0.15
        return sample

    def _invalid_sample(self) -> Cj702Sample:
        return Cj702Sample(
            eco2_ppm=0.0,
            ech2o_ug_m3=0.0,
            tvoc_ug_m3=0.0,
            pm25_ug_m3=0.0,
            pm10_ug_m3=0.0,
            temperature_c=0.0,
            humidity_rh=0.0,
        )


def main(args=None) -> None:
    rclpy.init(args=args)
    node = EnvBridge()
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
