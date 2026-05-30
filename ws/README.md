# Workspace Notes

在这个目录下构建和运行：

```bash
source /opt/ros/humble/setup.bash
python3 -m pip install --user pyserial numpy
colcon build --symlink-install
source install/setup.bash
```

整套台架框架启动命令：

```bash
ros2 launch inspection_bringup bench.launch.py
```

如果是做真机验收，不建议只依赖 `bench.launch.py`，因为部分配置仍支持 `mock` 回退。
优先直接跑下面这些单项命令。

## 当前机器最近一次实机验收端口示例

- `CJ702`：`/dev/ttyCH341USB0`
- `BY-F820`：`/dev/ttyCH341USB1`
- 继电器下位机：`/dev/ttyCH341USB2`

先查看机器当前串口：

```bash
ls -l /dev/ttyCH341USB* /dev/ttyUSB* /dev/ttyACM* 2>/dev/null
```

## 单项验收

空气质量传感器：

```bash
ros2 run inspection_bringup env_acceptance --phase both --port /dev/ttyCH341USB0
```

喇叭：

```bash
ros2 run inspection_bringup speaker_acceptance --phase both --port /dev/ttyCH341USB1
```

播放单个喇叭音频：

```bash
ros2 run inspection_bringup speaker_play_file --port /dev/ttyCH341USB1 --track-id 1
```

继电器下位机状态查询：

```bash
ros2 run inspection_alarm relay_cli --port /dev/ttyCH341USB2 --action query
```

继电器下位机全开：

```bash
ros2 run inspection_alarm relay_cli --port /dev/ttyCH341USB2 --action set-all --mask 0x07
```

继电器下位机全关：

```bash
ros2 run inspection_alarm relay_cli --port /dev/ttyCH341USB2 --action set-all --mask 0x00
```

更完整的复现步骤、接口说明和全部验收命令见仓库根目录的 [README.md](/home/wyz/peripherel/README.md:1)。
