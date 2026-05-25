import argparse
import re
import time
from typing import Optional

from inspection_alarm.by_f820 import ByF820Client, build_frame
from inspection_alarm.serial_ports import detect_serial_port, open_serial


def _assert_frame(label: str, actual: bytes, expected: bytes) -> None:
    if actual != expected:
        raise AssertionError(
            f"{label} frame mismatch: actual={actual.hex(' ')} expected={expected.hex(' ')}"
        )


def _decode_play_status(response_text: str) -> Optional[int]:
    text = response_text.strip()
    matches = re.findall(r"OK([0-9A-Fa-f]{4})", text)
    if not matches:
        if "ERR" in text.upper():
            return None
        return None
    try:
        return int(matches[-1], 16)
    except ValueError:
        return None


def _wait_for_track_completion(
    cli: ByF820Client,
    timeout_s: float,
    poll_interval_s: float,
    require_complete_status: bool,
) -> bool:
    deadline = time.time() + timeout_s
    saw_any_response = False
    saw_playing_or_done = False
    while time.time() < deadline:
        response = cli.query_play_status()
        if response.raw:
            saw_any_response = True
        status_code = _decode_play_status(response.text)
        print(
            "query_play_status "
            f"TX={response.request.hex(' ')} "
            f"RX={response.raw.hex(' ')} "
            f"ASCII={response.text}"
        )
        if status_code == 0:
            return True
        if status_code == 1:
            saw_playing_or_done = True
        elif status_code is not None:
            saw_playing_or_done = True
        time.sleep(poll_interval_s)
    if require_complete_status:
        return False
    return saw_any_response or saw_playing_or_done


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Play a single BY-F820 track over serial.")
    parser.add_argument("--port", default="", help="Serial port path; auto-detect if empty.")
    parser.add_argument("--baudrate", type=int, default=9600)
    parser.add_argument(
        "--storage-target",
        default="flash",
        choices=["current", "none", "flash", "udisk"],
    )
    parser.add_argument("--volume", type=int, default=30)
    parser.add_argument("--track-id", type=int, required=True, help="Track number to play.")
    parser.add_argument("--playback-timeout", type=float, default=30.0)
    parser.add_argument("--poll-interval", type=float, default=1.0)
    parser.add_argument("--no-stop-after", action="store_true")
    parser.add_argument(
        "--require-complete-status",
        action="store_true",
        help="Fail if the module does not clearly report a completed play state.",
    )
    args = parser.parse_args(argv)

    try:
        port = detect_serial_port(args.port)
        ser = open_serial(port, args.baudrate, timeout=0.5)
        cli = ByF820Client(ser, response_delay_s=0.35)
        try:
            print(f"Using serial port: {port}")
            frame = cli.stop()
            _assert_frame("stop", frame, build_frame(0x0E))
            print(f"stop TX={frame.hex(' ')}")

            if args.storage_target not in {"", "none", "current"}:
                frame = cli.switch_storage(args.storage_target)
                expected = build_frame(
                    0x35,
                    bytes([0x02 if args.storage_target == "flash" else 0x00]),
                )
                _assert_frame(f"switch_storage[{args.storage_target}]", frame, expected)
                print(f"switch_storage[{args.storage_target}] TX={frame.hex(' ')}")

            volume = max(0, min(int(args.volume), 30))
            frame = cli.set_volume(volume)
            _assert_frame("set_volume", frame, build_frame(0x31, bytes([volume])))
            print(f"set_volume TX={frame.hex(' ')}")

            track_id = max(1, min(int(args.track_id), 255))
            frame = cli.play_track(track_id)
            _assert_frame("play_track", frame, build_frame(0x41, bytes([0x00, track_id])))
            print(f"play_track[{track_id}] TX={frame.hex(' ')}")
            print(f"Waiting up to {args.playback_timeout:.1f}s for track playback to finish...")

            completed = _wait_for_track_completion(
                cli,
                args.playback_timeout,
                args.poll_interval,
                args.require_complete_status,
            )
            if not completed:
                if args.require_complete_status:
                    print("Track did not report a completed state before timeout.")
                else:
                    print("Playback-status response stayed noisy, but serial playback command was sent.")
                return 1

            if not args.no_stop_after:
                frame = cli.stop()
                _assert_frame("stop", frame, build_frame(0x0E))
                print(f"stop TX={frame.hex(' ')}")
            return 0
        finally:
            ser.close()
    except Exception as exc:
        print(f"Play-file command failed: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
