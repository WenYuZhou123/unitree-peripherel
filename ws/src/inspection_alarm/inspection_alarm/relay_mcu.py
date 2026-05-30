from dataclasses import dataclass
import threading
import time
from typing import Optional


FRAME_HEAD = 0xFF
FRAME_TAIL = 0xFE
FRAME_LENGTH = 6

CMD_SET_ONE = 0x01
CMD_SET_ALL = 0x02
CMD_QUERY_STATE = 0x03

STATUS_OK = 0x00
STATUS_CHECKSUM_ERROR = 0x01
STATUS_INVALID_CMD = 0x02
STATUS_INVALID_CHANNEL = 0x03
STATUS_INVALID_STATE = 0x04


def calc_checksum(cmd: int, arg1: int, arg2: int) -> int:
    return (int(cmd) ^ int(arg1) ^ int(arg2)) & 0xFF


def build_frame(cmd: int, arg1: int = 0, arg2: int = 0) -> bytes:
    cmd = int(cmd) & 0xFF
    arg1 = int(arg1) & 0xFF
    arg2 = int(arg2) & 0xFF
    checksum = calc_checksum(cmd, arg1, arg2)
    return bytes([FRAME_HEAD, cmd, arg1, arg2, checksum, FRAME_TAIL])


@dataclass
class RelayResponse:
    command: int
    status: int
    state_mask: int
    raw: bytes

    @property
    def ok(self) -> bool:
        return self.status == STATUS_OK

    def channel_enabled(self, channel: int) -> bool:
        if channel < 1 or channel > 3:
            raise ValueError(f"channel must be 1..3, got {channel}")
        return bool(self.state_mask & (1 << (channel - 1)))


def parse_frame(frame: bytes) -> RelayResponse:
    if len(frame) != FRAME_LENGTH:
        raise ValueError(f"expected {FRAME_LENGTH} bytes, got {len(frame)}")
    if frame[0] != FRAME_HEAD:
        raise ValueError(f"invalid frame head: 0x{frame[0]:02X}")
    if frame[-1] != FRAME_TAIL:
        raise ValueError(f"invalid frame tail: 0x{frame[-1]:02X}")

    cmd = frame[1]
    status = frame[2]
    state_mask = frame[3]
    expected = calc_checksum(cmd, status, state_mask)
    if frame[4] != expected:
        raise ValueError(
            f"invalid checksum: expected 0x{expected:02X}, received 0x{frame[4]:02X}"
        )

    return RelayResponse(
        command=cmd,
        status=status,
        state_mask=state_mask & 0x07,
        raw=frame,
    )


class RelayMcuClient:
    def __init__(self, stream) -> None:
        self.stream = stream
        self.lock = threading.Lock()
        self.rx_buffer = bytearray()

    def send_command(
        self,
        cmd: int,
        arg1: int = 0,
        arg2: int = 0,
        expect_response: bool = True,
        timeout_s: float = 1.0,
    ):
        frame = build_frame(cmd, arg1, arg2)
        with self.lock:
            if hasattr(self.stream, "reset_input_buffer"):
                self.stream.reset_input_buffer()
            self.stream.write(frame)
            self.stream.flush()
        if not expect_response:
            return frame
        response = self.read_response(timeout_s=timeout_s)
        if response.command != (cmd & 0xFF):
            raise ValueError(
                f"response command mismatch: sent 0x{cmd:02X}, got 0x{response.command:02X}"
            )
        return response

    def set_channel(self, channel: int, enabled: bool, timeout_s: float = 1.0) -> RelayResponse:
        if channel < 1 or channel > 3:
            raise ValueError(f"channel must be 1..3, got {channel}")
        return self.send_command(
            CMD_SET_ONE,
            arg1=channel,
            arg2=1 if enabled else 0,
            timeout_s=timeout_s,
        )

    def set_all(self, state_mask: int, timeout_s: float = 1.0) -> RelayResponse:
        return self.send_command(CMD_SET_ALL, arg1=state_mask & 0x07, timeout_s=timeout_s)

    def query_state(self, timeout_s: float = 1.0) -> RelayResponse:
        return self.send_command(CMD_QUERY_STATE, timeout_s=timeout_s)

    def read_response(self, timeout_s: float = 1.0) -> RelayResponse:
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            response = self._try_read_one()
            if response is not None:
                return response
        raise TimeoutError(f"relay MCU response timeout after {timeout_s:.2f}s")

    def _try_read_one(self) -> Optional[RelayResponse]:
        frame = self._extract_frame_from_buffer()
        if frame is not None:
            return parse_frame(frame)

        chunk = self.stream.read(FRAME_LENGTH)
        if chunk:
            self.rx_buffer.extend(chunk)
        frame = self._extract_frame_from_buffer()
        if frame is None:
            return None
        return parse_frame(frame)

    def _extract_frame_from_buffer(self) -> Optional[bytes]:
        while self.rx_buffer and self.rx_buffer[0] != FRAME_HEAD:
            del self.rx_buffer[0]

        while len(self.rx_buffer) >= FRAME_LENGTH:
            if self.rx_buffer[0] != FRAME_HEAD:
                del self.rx_buffer[0]
                continue

            candidate = bytes(self.rx_buffer[:FRAME_LENGTH])
            if candidate[-1] == FRAME_TAIL:
                del self.rx_buffer[:FRAME_LENGTH]
                return candidate

            del self.rx_buffer[0]

        return None


def status_to_text(status: int) -> str:
    return {
        STATUS_OK: "ok",
        STATUS_CHECKSUM_ERROR: "checksum_error",
        STATUS_INVALID_CMD: "invalid_cmd",
        STATUS_INVALID_CHANNEL: "invalid_channel",
        STATUS_INVALID_STATE: "invalid_state",
    }.get(status, f"unknown_status_0x{status:02X}")
