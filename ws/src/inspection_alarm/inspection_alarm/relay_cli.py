import argparse

from inspection_alarm.relay_mcu import RelayMcuClient, status_to_text
from inspection_alarm.serial_ports import detect_serial_port, open_serial


def _print_response(label: str, response) -> None:
    print(
        f"{label} "
        f"RX={response.raw.hex(' ')} "
        f"cmd=0x{response.command:02X} "
        f"status={status_to_text(response.status)} "
        f"mask=0x{response.state_mask:02X} "
        f"r1={int(response.channel_enabled(1))} "
        f"r2={int(response.channel_enabled(2))} "
        f"r3={int(response.channel_enabled(3))}"
    )


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Relay MCU serial tool")
    parser.add_argument("--port", default="", help="Serial port path; auto-detect if empty.")
    parser.add_argument("--baudrate", type=int, default=9600)
    parser.add_argument("--timeout", type=float, default=1.0)
    parser.add_argument(
        "--action",
        default="query",
        choices=["query", "set-one", "set-all"],
        help="Which MCU command to send.",
    )
    parser.add_argument("--channel", type=int, default=1, help="Relay channel for set-one, 1..3.")
    parser.add_argument(
        "--state",
        type=int,
        default=1,
        choices=[0, 1],
        help="Relay state for set-one, 0=off 1=on.",
    )
    parser.add_argument(
        "--mask",
        type=lambda value: int(value, 0),
        default=0,
        help="Relay state mask for set-all, e.g. 0x03 means R1/R2 on.",
    )
    args = parser.parse_args(argv)

    try:
        port = detect_serial_port(args.port)
        ser = open_serial(port, args.baudrate, timeout=args.timeout)
        client = RelayMcuClient(ser)
        try:
            print(f"Using serial port: {port}")
            if args.action == "query":
                response = client.query_state(timeout_s=args.timeout)
                _print_response("query_state", response)
            elif args.action == "set-one":
                tx = client.send_command(
                    0x01,
                    arg1=args.channel,
                    arg2=args.state,
                    expect_response=False,
                )
                print(f"set_one TX={tx.hex(' ')}")
                response = client.read_response(timeout_s=args.timeout)
                _print_response("set_one", response)
            else:
                tx = client.send_command(0x02, arg1=args.mask, expect_response=False)
                print(f"set_all TX={tx.hex(' ')}")
                response = client.read_response(timeout_s=args.timeout)
                _print_response("set_all", response)
            return 0
        finally:
            ser.close()
    except Exception as exc:
        print(f"relay CLI failed: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
