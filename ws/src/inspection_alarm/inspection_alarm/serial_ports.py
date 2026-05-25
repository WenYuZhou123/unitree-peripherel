from glob import glob
from typing import Iterable, Optional

import serial  # type: ignore


PORT_PATTERNS = ("/dev/ttyCH341USB*", "/dev/ttyUSB*", "/dev/ttyACM*")


def detect_serial_port(explicit_port: str = "", patterns: Iterable[str] = PORT_PATTERNS) -> str:
    if explicit_port:
        return explicit_port
    for pattern in patterns:
        ports = sorted(glob(pattern))
        if ports:
            return ports[0]
    raise RuntimeError("No serial port detected for BY-F820")


def open_serial(
    port: str,
    baudrate: int,
    timeout: float = 0.5,
):
    return serial.Serial(
        port,
        baudrate=baudrate,
        timeout=timeout,
        bytesize=serial.EIGHTBITS,
        parity=serial.PARITY_NONE,
        stopbits=serial.STOPBITS_ONE,
    )
