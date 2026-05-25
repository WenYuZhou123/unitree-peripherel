import argparse
import re
import subprocess
import threading
import time
from typing import Optional

from inspection_alarm.by_f820 import ByF820Client, build_frame
from inspection_alarm.serial_ports import detect_serial_port, open_serial


def _print_prefixed(prefix, line):
    print(f"[{prefix}] {line}", end="")


def _pump_output(proc, prefix):
    assert proc.stdout is not None
    for line in proc.stdout:
        _print_prefixed(prefix, line)


def _ros_service_call(mode: str, enabled: bool, timeout_s: float = 20.0) -> subprocess.CompletedProcess:
    return subprocess.run(
        [
            "ros2",
            "service",
            "call",
            "/alarm/set_mode",
            "inspection_msgs/srv/SetAlarmMode",
            f"{{mode: {mode}, enabled: {str(enabled).lower()}}}",
        ],
        capture_output=True,
        text=True,
        timeout=timeout_s,
    )


def _wait_for_service(timeout_s: float = 20.0) -> bool:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        res = subprocess.run(
            ["ros2", "service", "list"],
            capture_output=True,
            text=True,
        )
        if "/alarm/set_mode" in res.stdout:
            return True
        time.sleep(0.5)
    return False


def _assert_frame(label: str, actual: bytes, expected: bytes) -> None:
    if actual != expected:
        raise AssertionError(
            f"{label} frame mismatch: actual={actual.hex(' ')} expected={expected.hex(' ')}"
        )


def _decode_play_status(response_text: str) -> Optional[int]:
    text = response_text.strip()
    matches = re.findall(r"OK([0-9A-Fa-f]{4})", text)
    if not matches:
        return None
    try:
        return int(matches[-1], 16)
    except ValueError:
        return None


def _wait_for_track_completion(
    cli: ByF820Client,
    timeout_s: float,
    poll_interval_s: float,
) -> bool:
    deadline = time.time() + timeout_s
    saw_any_response = False
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
        time.sleep(poll_interval_s)
    return saw_any_response


def _serial_smoke_test(
    port: str,
    baudrate: int,
    storage_target: str,
    volume: int,
    track: int,
    require_query_response: bool,
    playback_timeout_s: float,
    poll_interval_s: float,
) -> bool:
    ser = open_serial(port, baudrate, timeout=0.5)
    cli = ByF820Client(ser, response_delay_s=0.35)
    try:
        print(f"Using serial port: {port}")
        frame = cli.stop()
        _assert_frame("stop", frame, build_frame(0x0E))
        print(f"stop TX={frame.hex(' ')}")
        if storage_target not in {"", "none", "current"}:
            frame = cli.switch_storage(storage_target)
            expected = build_frame(0x35, bytes([0x02 if storage_target == "flash" else 0x00]))
            _assert_frame(f"switch_storage[{storage_target}]", frame, expected)
            print(f"switch_storage[{storage_target}] TX={frame.hex(' ')}")
        frame = cli.set_volume(volume)
        _assert_frame("set_volume", frame, build_frame(0x31, bytes([max(0, min(int(volume), 30))])))
        print(f"set_volume TX={frame.hex(' ')}")
        frame = cli.play_track(track)
        _assert_frame("play_track", frame, build_frame(0x41, bytes([0x00, max(1, min(int(track), 255))])))
        print(f"play_track[{track}] TX={frame.hex(' ')}")
        print(f"Waiting up to {playback_timeout_s:.1f}s for track playback to finish...")
        response = cli.query_play_status()
        print(f"query_play_status TX={response.request.hex(' ')} RX={response.raw.hex(' ')} ASCII={response.text}")
        if response.raw:
            status_code = _decode_play_status(response.text)
            if status_code == 1:
                completed = _wait_for_track_completion(cli, playback_timeout_s, poll_interval_s)
                if not completed:
                    print("Track did not report a completed state before timeout.")
                    if require_query_response:
                        return False
            elif status_code is None and require_query_response:
                print("Unable to decode play status response.")
                return False
        elif require_query_response:
            print("Query response is empty.")
            return False
        frame = cli.stop()
        _assert_frame("stop", frame, build_frame(0x0E))
        print(f"stop TX={frame.hex(' ')}")
        if not response.raw:
            print("Query response is empty, but TX frames were verified.")
        return True
    finally:
        ser.close()


def _sleep_with_countdown(seconds: float, label: str) -> None:
    if seconds <= 0:
        return
    print(f"{label}: holding for {seconds:.1f}s")
    time.sleep(seconds)


def _launch_controller(port: str, baudrate: int, storage_target: str, volume: int, tracks):
    cmd = [
        "ros2",
        "run",
        "inspection_alarm",
        "alarm_controller",
        "--ros-args",
        "-p",
        "mock_backend:=false",
        "-p",
        f"speaker_port:={port}",
        "-p",
        f"speaker_baudrate:={baudrate}",
        "-p",
        f"speaker_volume:={volume}",
        "-p",
        f"speaker_storage_target:={storage_target}",
        "-p",
        "log_serial_frames:=true",
        "-p",
        f"speaker_tracks.gas_warning:={tracks['gas_warning']}",
        "-p",
        f"speaker_tracks.thermal_warning:={tracks['thermal_warning']}",
        "-p",
        f"speaker_tracks.manual_test:={tracks['manual_test']}",
    ]
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    thread = threading.Thread(target=_pump_output, args=(proc, "alarm_controller"), daemon=True)
    thread.start()
    return proc, thread


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="BY-F820 speaker acceptance script")
    parser.add_argument("--port", default="", help="Serial port path; auto-detect if empty.")
    parser.add_argument("--baudrate", type=int, default=9600)
    parser.add_argument("--storage-target", default="flash", choices=["current", "none", "flash", "udisk"])
    parser.add_argument("--volume", type=int, default=30)
    parser.add_argument("--manual-track", type=int, default=1)
    parser.add_argument("--gas-track", type=int, default=1)
    parser.add_argument("--thermal-track", type=int, default=2)
    parser.add_argument(
        "--phase",
        default="both",
        choices=["serial", "service", "both"],
        help="Choose whether to validate raw serial, ROS service flow, or both.",
    )
    parser.add_argument(
        "--track-id",
        type=int,
        default=0,
        help="Optional track override for the serial phase, or for the selected --single-mode.",
    )
    parser.add_argument("--wait-service", type=float, default=20.0)
    parser.add_argument("--require-query-response", action="store_true")
    parser.add_argument("--serial-playback-timeout", type=float, default=30.0)
    parser.add_argument("--serial-poll-interval", type=float, default=1.0)
    parser.add_argument("--mode-hold-seconds", type=float, default=8.0)
    parser.add_argument(
        "--single-mode",
        default="",
        choices=["", "manual_test", "gas_warning", "thermal_warning"],
        help="If set, only verify one ROS mode and then stop.",
    )
    args = parser.parse_args(argv)

    try:
        port = detect_serial_port(args.port)
        tracks = {
            "gas_warning": args.gas_track,
            "thermal_warning": args.thermal_track,
            "manual_test": args.manual_track,
        }
        serial_track = args.manual_track
        if args.track_id > 0:
            serial_track = args.track_id
            if args.single_mode:
                tracks[args.single_mode] = args.track_id

        if args.phase in {"serial", "both"}:
            print("=== Serial smoke test ===")
            if not _serial_smoke_test(
                port,
                args.baudrate,
                args.storage_target,
                args.volume,
                serial_track,
                args.require_query_response,
                args.serial_playback_timeout,
                args.serial_poll_interval,
            ):
                print("Serial smoke test failed.")
                return 1

        if args.phase in {"service", "both"}:
            print("=== ROS service test ===")
            controller, thread = _launch_controller(
                port,
                args.baudrate,
                args.storage_target,
                args.volume,
                tracks,
            )
            try:
                if not _wait_for_service(args.wait_service):
                    print("Service /alarm/set_mode did not become available.")
                    return 1

                sequence = []
                if args.single_mode:
                    sequence.append((args.single_mode, True))
                    sequence.append(("idle", False))
                else:
                    sequence.extend(
                        [
                            ("manual_test", True),
                            ("gas_warning", True),
                            ("thermal_warning", True),
                            ("idle", False),
                        ]
                    )

                for mode, enabled in sequence:
                    res = _ros_service_call(mode, enabled)
                    print(res.stdout.strip())
                    if res.returncode != 0 or "success=True" not in res.stdout:
                        print(f"Service test failed for mode={mode}.")
                        return 1
                    if enabled:
                        _sleep_with_countdown(args.mode_hold_seconds, f"Mode {mode}")
            finally:
                controller.terminate()
                try:
                    controller.wait(timeout=5.0)
                except subprocess.TimeoutExpired:
                    controller.kill()
                thread.join(timeout=1.0)

        return 0
    except Exception as exc:
        print(f"Acceptance script failed: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
