# Workspace Notes

Build and launch from this directory:

```bash
source /opt/ros/humble/setup.bash
colcon build
source install/setup.bash
ros2 launch inspection_bringup bench.launch.py
```

The default launch is intentionally runnable without external hardware. Replace
mock parameters and `/dev` paths in `src/inspection_bringup/config/` as devices
arrive.
