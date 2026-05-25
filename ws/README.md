# Workspace Notes

Build and launch from this directory:

```bash
source /opt/ros/humble/setup.bash
python3 -m pip install --user pyserial numpy
colcon build
source install/setup.bash
ros2 launch inspection_bringup bench.launch.py
```

The default launch is intentionally runnable without external hardware. Replace
mock parameters and `/dev` paths in `src/inspection_bringup/config/` as devices
arrive. `CJ702` is expected on `UART`, `BY-F820` on serial/UART, and the
SenXor thermal camera on `USB`.

For speaker acceptance, use:

```bash
ros2 run inspection_bringup speaker_acceptance --port /dev/ttyCH341USB0
```

The speaker framework now defaults to `FLASH` playback storage and treats
serial-open failures as real failures when `mock_backend:=false`.

To let a full clip finish before switching modes, use:

```bash
ros2 run inspection_bringup speaker_acceptance \
  --port /dev/ttyACM0 \
  --phase service \
  --single-mode manual_test \
  --mode-hold-seconds 20
```

To play one chosen track directly without running the full acceptance flow, use:

```bash
ros2 run inspection_bringup speaker_play_file \
  --port /dev/ttyACM0 \
  --track-id 7
```
