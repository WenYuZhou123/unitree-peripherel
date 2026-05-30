import argparse
import os
import subprocess
import threading
import time
from glob import glob
from typing import List, Optional

import rclpy
from rclpy.node import Node

from inspection_env.cj702 import Cj702Sample, parse_cj702_frame, read_cj702_frame
from inspection_msgs.msg import AirState, TempHumidity

try:
    import serial  # type: ignore
except ImportError:  # pragma: no cover - optional dependency
    serial = None


PORT_PATTERNS = (
    "/dev/ttyUSB_cj702",
    "/dev/ttyCH341USB*",
    "/dev/ttyUSB*",
    "/dev/ttyACM*",
)


def _print_prefixed(prefix, line):
    print(f"[{prefix}] {line}", end="")


def _pump_output(proc, prefix):
    assert proc.stdout is not None
    for line in proc.stdout:
        _print_prefixed(prefix, line)


def _format_sample(sample: Cj702Sample) -> str:
    return (
        f"eCO2={sample.eco2_ppm:.1f}ppm "
        f"eCH2O={sample.ech2o_ug_m3:.1f}ug/m3 "
        f"TVOC={sample.tvoc_ug_m3:.1f}ug/m3 "
        f"PM2.5={sample.pm25_ug_m3:.1f}ug/m3 "
        f"PM10={sample.pm10_ug_m3:.1f}ug/m3 "
        f"T={sample.temperature_c:.2f}C "
        f"RH={sample.humidity_rh:.2f}%"
    )


def _values_look_valid(sample: Cj702Sample) -> bool:
    return sample.eco2_ppm > 0.0 and sample.humidity_rh > 0.0


def _resolve_sensor_port(explicit_port: str = "") -> str:
    if explicit_port:
        return explicit_port

    candidates: List[str] = []
    for pattern in PORT_PATTERNS:
        if "*" not in pattern:
            if os.path.exists(pattern) and pattern not in candidates:
                candidates.append(pattern)
            continue
        for match in sorted(glob(pattern)):
            if match not in candidates:
                candidates.append(match)

    if serial is not None:
        for candidate in candidates:
            try:
                ser = serial.Serial(
                    candidate,
                    baudrate=9600,
                    timeout=0.3,
                    bytesize=serial.EIGHTBITS,
                    parity=serial.PARITY_NONE,
                    stopbits=serial.STOPBITS_ONE,
                )
                try:
                    time.sleep(0.5)
                    frame = _wait_for_frame(ser, 1.5)
                    if frame is not None:
                        parse_cj702_frame(frame)
                        return candidate
                finally:
                    ser.close()
            except Exception:
                continue

    if candidates:
        return candidates[0]

    raise RuntimeError(
        "No serial port detected for CJ702. "
        "Checked /dev/ttyUSB_cj702, /dev/ttyCH341USB*, /dev/ttyUSB*, and /dev/ttyACM*."
    )


def _wait_for_frame(stream, timeout_s: float) -> Optional[bytes]:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        frame = read_cj702_frame(stream)
        if frame is not None:
            return frame
    return None


def _serial_smoke_test(
    port: str,
    baudrate: int,
    frame_timeout: float,
    sample_count: int,
    startup_delay_s: float,
    sample_timeout_s: float,
) -> bool:
    if serial is None:
        raise RuntimeError("pyserial is not available")

    ser = serial.Serial(
        port,
        baudrate=baudrate,
        timeout=frame_timeout,
        bytesize=serial.EIGHTBITS,
        parity=serial.PARITY_NONE,
        stopbits=serial.STOPBITS_ONE,
    )
    try:
        print(f"Using serial port: {port}")
        if startup_delay_s > 0.0:
            time.sleep(startup_delay_s)
        for index in range(sample_count):
            frame = _wait_for_frame(ser, sample_timeout_s)
            if frame is None:
                print(f"Timed out waiting for CJ702 frame within {sample_timeout_s:.1f}s.")
                return False
            sample = parse_cj702_frame(frame)
            print(
                f"sample[{index + 1}] RAW={frame.hex(' ')} "
                f"{_format_sample(sample)}"
            )
            if not _values_look_valid(sample):
                print("Parsed frame succeeded, but the values look suspicious.")
                return False
        return True
    finally:
        ser.close()


class _EnvTopicWatcher(Node):
    def __init__(self, expected_port: str) -> None:
        super().__init__("env_acceptance_watcher")
        self.expected_port = expected_port
        self.air_msg: Optional[AirState] = None
        self.temp_msg: Optional[TempHumidity] = None
        self.valid_air_count = 0
        self.valid_temp_count = 0
        self.create_subscription(AirState, "/env/air_state", self._air_cb, 10)
        self.create_subscription(
            TempHumidity,
            "/env/temperature_humidity",
            self._temp_cb,
            10,
        )

    def _air_cb(self, msg: AirState) -> None:
        self.air_msg = msg
        if msg.device_ok and msg.source_port == self.expected_port and msg.eco2_ppm > 0.0:
            self.valid_air_count += 1

    def _temp_cb(self, msg: TempHumidity) -> None:
        self.temp_msg = msg
        if msg.device_ok and msg.source_port == self.expected_port and msg.humidity_rh > 0.0:
            self.valid_temp_count += 1

    def has_enough_samples(self, min_samples: int) -> bool:
        return self.valid_air_count >= min_samples and self.valid_temp_count >= min_samples


def _launch_env_bridge(
    port: str,
    baudrate: int,
    frame_timeout: float,
    publish_rate_hz: float,
):
    cmd = [
        "ros2",
        "run",
        "inspection_env",
        "env_bridge",
        "--ros-args",
        "-p",
        "mock_mode:=false",
        "-p",
        f"serial_port:={port}",
        "-p",
        f"baudrate:={baudrate}",
        "-p",
        f"frame_timeout:={frame_timeout}",
        "-p",
        f"publish_rate_hz:={publish_rate_hz}",
    ]
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    thread = threading.Thread(target=_pump_output, args=(proc, "env_bridge"), daemon=True)
    thread.start()
    return proc, thread


def _topic_smoke_test(
    port: str,
    baudrate: int,
    frame_timeout: float,
    publish_rate_hz: float,
    min_samples: int,
    timeout_s: float,
) -> bool:
    bridge, thread = _launch_env_bridge(port, baudrate, frame_timeout, publish_rate_hz)
    rclpy.init()
    watcher = _EnvTopicWatcher(port)
    try:
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            rclpy.spin_once(watcher, timeout_sec=0.5)
            if watcher.has_enough_samples(min_samples):
                air = watcher.air_msg
                temp = watcher.temp_msg
                assert air is not None
                assert temp is not None
                print(
                    "air_state "
                    f"device_ok={air.device_ok} "
                    f"source_port={air.source_port} "
                    f"eCO2={air.eco2_ppm:.1f}ppm "
                    f"eCH2O={air.ech2o_ug_m3:.1f}ug/m3 "
                    f"TVOC={air.tvoc_ug_m3:.1f}ug/m3 "
                    f"PM2.5={air.pm25_ug_m3:.1f}ug/m3 "
                    f"PM10={air.pm10_ug_m3:.1f}ug/m3"
                )
                print(
                    "temperature_humidity "
                    f"device_ok={temp.device_ok} "
                    f"source_port={temp.source_port} "
                    f"T={temp.temperature_c:.2f}C "
                    f"RH={temp.humidity_rh:.2f}%"
                )
                return True

        print("Timed out waiting for valid /env topics.")
        if watcher.air_msg is not None:
            print(
                "Last air_state "
                f"device_ok={watcher.air_msg.device_ok} "
                f"source_port={watcher.air_msg.source_port} "
                f"eCO2={watcher.air_msg.eco2_ppm:.1f}ppm"
            )
        if watcher.temp_msg is not None:
            print(
                "Last temperature_humidity "
                f"device_ok={watcher.temp_msg.device_ok} "
                f"source_port={watcher.temp_msg.source_port} "
                f"T={watcher.temp_msg.temperature_c:.2f}C "
                f"RH={watcher.temp_msg.humidity_rh:.2f}%"
            )
        return False
    finally:
        watcher.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
        bridge.terminate()
        try:
            bridge.wait(timeout=5.0)
        except subprocess.TimeoutExpired:
            bridge.kill()
        thread.join(timeout=1.0)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="CJ702 air-quality acceptance script")
    parser.add_argument("--port", default="", help="Serial port path; default resolves /dev/ttyUSB_cj702 first.")
    parser.add_argument("--baudrate", type=int, default=9600)
    parser.add_argument("--frame-timeout", type=float, default=0.5)
    parser.add_argument("--publish-rate-hz", type=float, default=1.0)
    parser.add_argument("--serial-samples", type=int, default=3)
    parser.add_argument("--serial-startup-delay", type=float, default=0.6)
    parser.add_argument("--serial-sample-timeout", type=float, default=3.0)
    parser.add_argument("--topic-samples", type=int, default=2)
    parser.add_argument("--topic-timeout", type=float, default=15.0)
    parser.add_argument(
        "--phase",
        default="both",
        choices=["serial", "topic", "both"],
        help="Choose whether to validate raw serial, ROS topic flow, or both.",
    )
    args = parser.parse_args(argv)

    try:
        port = _resolve_sensor_port(args.port)

        if args.phase in {"serial", "both"}:
            print("=== Serial smoke test ===")
            if not _serial_smoke_test(
                port,
                args.baudrate,
                args.frame_timeout,
                max(1, args.serial_samples),
                max(0.0, args.serial_startup_delay),
                max(args.frame_timeout, args.serial_sample_timeout),
            ):
                print("Serial smoke test failed.")
                return 1

        if args.phase in {"topic", "both"}:
            print("=== ROS topic test ===")
            if not _topic_smoke_test(
                port,
                args.baudrate,
                args.frame_timeout,
                args.publish_rate_hz,
                max(1, args.topic_samples),
                args.topic_timeout,
            ):
                print("ROS topic test failed.")
                return 1

        return 0
    except Exception as exc:
        print(f"Acceptance script failed: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
