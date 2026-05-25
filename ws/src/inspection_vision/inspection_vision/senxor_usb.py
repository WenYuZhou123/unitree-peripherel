import logging
import time
from dataclasses import dataclass
from typing import Optional

import numpy as np

try:
    import serial  # type: ignore
    import serial.tools.list_ports  # type: ignore
except ImportError:  # pragma: no cover - optional dependency
    serial = None


LOGGER = logging.getLogger(__name__)

MI_VID = 0x0416
MI_PID_EVK = 0xB002
MI_PID_XPRO = 0xB020
MI_PIDS = {MI_PID_EVK, MI_PID_XPRO}

REG_EVK_TEST = 0x00
REG_SENXOR_POWERUP = 0xB0
REG_FRAME_MODE = 0xB1
REG_FRAME_RATE = 0xB4
REG_STATUS = 0xB6
REG_SENXOR_TYPE = 0xBA

MODE_STREAM = 0x02
MODE_NO_HEADER = 0x20
STATUS_BOOTING = 0x20

CAMERA_SHAPES = {
    0: (80, 62),
    1: (80, 62),
    2: (32, 32),
    3: (80, 62),
    4: (80, 62),
}


def _checksum(data: bytes, initial: int = 0) -> int:
    value = initial
    for byte in data:
        value += byte
    return value


def _read_usb_ack(stream):
    marker = b""
    while marker != b"   #":
        marker = stream.read(4)
        if not marker:
            return None
        if marker != b"   #":
            continue

    length_raw = stream.read(4)
    if len(length_raw) != 4:
        return None
    checksum = _checksum(length_raw)
    try:
        ack_len = int(length_raw.decode(), 16)
    except ValueError:
        return None

    command = stream.read(4)
    if len(command) != 4:
        return None
    checksum = _checksum(command, checksum)
    data_len = ack_len - 8
    data = stream.read(data_len)
    if len(data) != data_len:
        return None
    checksum = _checksum(data, checksum) & 0xFFFF

    checksum_raw = stream.read(4)
    if len(checksum_raw) != 4:
        return None
    try:
        expected = int(checksum_raw.decode(), 16)
    except ValueError:
        return None
    if checksum != expected:
        LOGGER.warning(
            "SenXor USB checksum mismatch: calculated 0x%04x, received 0x%04x",
            checksum,
            expected,
        )
        return None
    return command.decode(), data


def _usb_command(stream, command: str):
    stream.write(command.encode())
    stream.flush()
    while True:
        ack = _read_usb_ack(stream)
        if ack is None:
            return None, None
        ack_cmd, data = ack
        if ack_cmd in {"RREG", "WREG", "GFRA", "SERR"}:
            return ack_cmd, data


def _format_reg_read(register: int) -> str:
    payload = f"RREG{register:02X}XXXXXX"
    return f"   #{len(payload):04X}{payload}"


def _format_reg_write(register: int, value: int) -> str:
    payload = f"WREG{register:02X}{value:02X}XXXX"
    return f"   #{len(payload):04X}{payload}"


@dataclass
class SenxorUsbCamera:
    stream: object
    width: int
    height: int
    max_fps: float = 30.0

    @classmethod
    def open(cls, usb_port: str = "", fps: float = 10.0):
        if serial is None:
            raise RuntimeError("pyserial is required for SenXor USB access")

        device = None
        for port in serial.tools.list_ports.comports():
            if port.vid == MI_VID and port.pid in MI_PIDS:
                if usb_port and usb_port not in {port.device, port.name, port.description}:
                    continue
                device = port.device
                break
        if device is None:
            raise RuntimeError("no SenXor USB device found")

        stream = serial.Serial(device, timeout=0.5)
        camera = cls(stream=stream, width=80, height=62)
        camera._initialize()
        camera.set_fps(fps)
        camera.start_stream()
        return camera

    def _read_register(self, register: int) -> int:
        command = _format_reg_read(register)
        for _ in range(5):
            ack_cmd, data = _usb_command(self.stream, command)
            if ack_cmd == "RREG" and data is not None:
                return int(data.decode(), 16)
            if ack_cmd == "GFRA":
                continue
        raise RuntimeError(f"failed to read SenXor register 0x{register:02X}")

    def _write_register(self, register: int, value: int) -> None:
        command = _format_reg_write(register, value)
        for _ in range(5):
            ack_cmd, _ = _usb_command(self.stream, command)
            if ack_cmd == "WREG":
                return
            if ack_cmd == "GFRA":
                continue
        raise RuntimeError(f"failed to write SenXor register 0x{register:02X}")

    def _initialize(self) -> None:
        self.stream.reset_input_buffer()
        self.stream.reset_output_buffer()

        has_bridge = self._read_register(REG_EVK_TEST) == 0xFF
        if not has_bridge:
            self._write_register(REG_SENXOR_POWERUP, 0x13)
            time.sleep(0.1)

        self._write_register(REG_FRAME_MODE, 0x00)
        time.sleep(0.05)

        for _ in range(20):
            status = self._read_register(REG_STATUS)
            if not (status & STATUS_BOOTING):
                break
            time.sleep(0.05)

        camera_type = self._read_register(REG_SENXOR_TYPE)
        self.width, self.height = CAMERA_SHAPES.get(camera_type, (80, 62))

    def set_fps(self, fps: float) -> None:
        fps = max(float(fps), 1.0)
        divisor = max(1, int(round(self.max_fps / fps)))
        self._write_register(REG_FRAME_RATE, divisor)

    def start_stream(self) -> None:
        self._write_register(REG_FRAME_MODE, MODE_STREAM | MODE_NO_HEADER)

    def read_frame(self) -> np.ndarray:
        ack = _read_usb_ack(self.stream)
        while ack is not None and ack[0] != "GFRA":
            ack = _read_usb_ack(self.stream)
        if ack is None:
            raise RuntimeError("did not receive thermal frame from SenXor USB")

        _, payload = ack
        words = np.frombuffer(payload, dtype="<u2")
        count = self.width * self.height
        if len(words) < count:
            raise RuntimeError(f"incomplete thermal frame: {len(words)} words")
        data = words[-count:].astype(np.float32) / 10.0 - 273.15
        return data.reshape((self.width, self.height), order="F").T.copy()

    def stop(self) -> None:
        try:
            self._write_register(REG_FRAME_MODE, 0x00)
        except Exception:
            LOGGER.debug("failed to stop SenXor stream cleanly", exc_info=True)
        self.stream.reset_input_buffer()
        self.stream.reset_output_buffer()
        self.stream.close()
