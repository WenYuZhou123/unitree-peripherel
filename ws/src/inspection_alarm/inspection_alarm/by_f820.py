from dataclasses import dataclass
import time
from typing import Optional


START_BYTE = 0x7E
END_BYTE = 0xEF

CMD_PLAY = 0x01
CMD_PAUSE = 0x02
CMD_STOP = 0x0E
CMD_QUERY_PLAY_STATUS = 0x10
CMD_QUERY_VOLUME = 0x11
CMD_QUERY_UDISK_TOTAL = 0x16
CMD_QUERY_FLASH_TOTAL = 0x17
CMD_QUERY_DEVICE = 0x18
CMD_QUERY_UDISK_TRACK = 0x1A
CMD_QUERY_FLASH_TRACK = 0x1B
CMD_SET_VOLUME = 0x31
CMD_SWITCH_DEVICE = 0x35
CMD_PLAY_TRACK = 0x41

DEVICE_UDISK = 0x00
DEVICE_FLASH = 0x02


def build_frame(opcode: int, params: bytes = b"") -> bytes:
    body = bytes([opcode]) + params
    length = len(body) + 2
    checksum = length
    for value in body:
        checksum ^= value
    return bytes([START_BYTE, length, opcode]) + params + bytes([checksum, END_BYTE])


@dataclass
class ByF820Response:
    request: bytes
    raw: bytes

    @property
    def text(self) -> str:
        return self.raw.decode("ascii", errors="replace").strip()


@dataclass
class ByF820Client:
    stream: object
    response_delay_s: float = 0.25

    def send(self, opcode: int, params: bytes = b"", expect_response: bool = False):
        frame = build_frame(opcode, params)
        self.stream.reset_input_buffer()
        self.stream.write(frame)
        self.stream.flush()
        if not expect_response:
            return frame

        if self.response_delay_s > 0:
            time.sleep(self.response_delay_s)
        raw = self.stream.read_all()
        return ByF820Response(request=frame, raw=raw)

    def play(self) -> bytes:
        return self.send(CMD_PLAY)

    def pause(self) -> bytes:
        return self.send(CMD_PAUSE)

    def stop(self) -> bytes:
        return self.send(CMD_STOP)

    def switch_storage(self, target: str) -> bytes:
        normalized = target.strip().lower()
        if normalized == "flash":
            return self.send(CMD_SWITCH_DEVICE, bytes([DEVICE_FLASH]))
        if normalized in {"udisk", "u_disk", "usb", "u"}:
            return self.send(CMD_SWITCH_DEVICE, bytes([DEVICE_UDISK]))
        raise ValueError(f"Unsupported BY-F820 storage target: {target}")

    def set_volume(self, volume: int) -> bytes:
        clamped = max(0, min(int(volume), 30))
        return self.send(CMD_SET_VOLUME, bytes([clamped]))

    def play_track(self, track_id: int) -> bytes:
        track_id = max(1, min(int(track_id), 255))
        return self.send(CMD_PLAY_TRACK, bytes([0x00, track_id]))

    def query_device(self) -> ByF820Response:
        return self.send(CMD_QUERY_DEVICE, expect_response=True)

    def query_play_status(self) -> ByF820Response:
        return self.send(CMD_QUERY_PLAY_STATUS, expect_response=True)

    def query_volume(self) -> ByF820Response:
        return self.send(CMD_QUERY_VOLUME, expect_response=True)

    def query_flash_total(self) -> ByF820Response:
        return self.send(CMD_QUERY_FLASH_TOTAL, expect_response=True)

    def query_udisk_total(self) -> ByF820Response:
        return self.send(CMD_QUERY_UDISK_TOTAL, expect_response=True)

    def query_flash_track(self) -> ByF820Response:
        return self.send(CMD_QUERY_FLASH_TRACK, expect_response=True)

    def query_udisk_track(self) -> ByF820Response:
        return self.send(CMD_QUERY_UDISK_TRACK, expect_response=True)
