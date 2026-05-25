from dataclasses import dataclass
from typing import Optional


CJ702_FRAME_LENGTH = 17
CJ702_HEADER = b"\x3c\x02"


@dataclass
class Cj702Sample:
    eco2_ppm: float
    ech2o_ug_m3: float
    tvoc_ug_m3: float
    pm25_ug_m3: float
    pm10_ug_m3: float
    temperature_c: float
    humidity_rh: float


def parse_cj702_frame(frame: bytes) -> Cj702Sample:
    if len(frame) != CJ702_FRAME_LENGTH:
        raise ValueError(f"expected {CJ702_FRAME_LENGTH} bytes, got {len(frame)}")
    if frame[:2] != CJ702_HEADER:
        raise ValueError("invalid CJ702 frame header")

    checksum = sum(frame[:16]) & 0xFF
    if checksum != frame[16]:
        raise ValueError(
            f"invalid checksum: expected 0x{checksum:02x}, received 0x{frame[16]:02x}"
        )

    temp_int_raw = frame[12]
    temp_sign = -1.0 if temp_int_raw & 0x80 else 1.0
    temp_int = float(temp_int_raw & 0x7F)
    temperature_c = temp_sign * (temp_int + frame[13] / 100.0)

    humidity_rh = float(frame[14]) + frame[15] / 100.0

    return Cj702Sample(
        eco2_ppm=float((frame[2] << 8) | frame[3]),
        ech2o_ug_m3=float((frame[4] << 8) | frame[5]),
        tvoc_ug_m3=float((frame[6] << 8) | frame[7]),
        pm25_ug_m3=float((frame[8] << 8) | frame[9]),
        pm10_ug_m3=float((frame[10] << 8) | frame[11]),
        temperature_c=temperature_c,
        humidity_rh=humidity_rh,
    )


def read_cj702_frame(stream) -> Optional[bytes]:
    if stream is None:
        return None

    while True:
        first = stream.read(1)
        if not first:
            return None
        if first != CJ702_HEADER[:1]:
            continue

        second = stream.read(1)
        if not second:
            return None
        if second != CJ702_HEADER[1:]:
            continue

        payload = stream.read(CJ702_FRAME_LENGTH - 2)
        if len(payload) != CJ702_FRAME_LENGTH - 2:
            return None
        return first + second + payload
