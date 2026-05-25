# unitree-peripherel

`unitree-peripherel` 是一个面向 `Jetson Orin Nano + Ubuntu 22.04 + ROS 2 Humble`
的外设接入工作区，用来先完成台架联调，再迁移到 `Unitree B2` 机器狗平台。

当前仓库已经把一批真实外设链路落到了同一套 ROS 2 工程里：

- `4` 路 USB 工业摄像头
- `1` 路热像仪
- `CJ702` 七合一环境传感器
- 语音喇叭
- 爆闪灯 / 补光灯
- 后续迁移到 `B2` 所需的网络与接线适配

## 当前状态

- 已完成 ROS 2 工作区骨架、消息定义、启动文件和桥接节点
- `CJ702` 已按 `UART 串口 17 字节帧` 接入
- 热像已按 `SenXor MI48 USB` 后端接入，并保留 mock 回退
- `BY-F820` 已按 `UART/串口自由协议` 接入
- 默认仍支持 `mock` 模式，未接真机也可以直接 `build` 和 `launch`
- 相机链路优先适配 `v4l2_camera`，未安装该包时自动回退到占位发布器

## 目录结构

```text
ws/
├── src/
│   ├── inspection_msgs/      # 自定义 msg / srv
│   ├── inspection_bringup/   # launch、参数、udev 示例、B2 迁移说明
│   ├── inspection_vision/    # USB 相机占位发布器、热像桥接
│   ├── inspection_env/       # 气体 / 温湿度桥接
│   └── inspection_alarm/     # 喇叭 / 爆闪灯 / 补光灯控制
├── build/
├── install/
└── log/
```

## ROS 2 接口

### Topics

- `/cam/front/image_raw`
- `/cam/rear/image_raw`
- `/cam/left/image_raw`
- `/cam/right/image_raw`
- `/thermal/image_temperature`
- `/thermal/image_preview`
- `/thermal/hotspot`
- `/env/air_state`
- `/env/temperature_humidity`
- `/alarm/current_mode`

### Services

- `/alarm/set_mode`

### 自定义接口

- `inspection_msgs/msg/AirState`
- `inspection_msgs/msg/TempHumidity`
- `inspection_msgs/msg/ThermalHotspot`
- `inspection_msgs/srv/SetAlarmMode`

## 快速开始

### 1. 构建

```bash
cd /home/wyz/peripherel/ws
source /opt/ros/humble/setup.bash
python3 -m pip install --user pyserial numpy
colcon build --symlink-install
```

### 2. 启动整套台架框架

```bash
cd /home/wyz/peripherel/ws
source /opt/ros/humble/setup.bash
source install/setup.bash
ros2 launch inspection_bringup bench.launch.py
```

### 3. 测试告警服务

```bash
ros2 service call /alarm/set_mode inspection_msgs/srv/SetAlarmMode \
  "{mode: thermal_warning, enabled: true}"
```

## 包说明

### `inspection_msgs`

定义整个系统共享的消息和服务。当前 `AirState` 已经对齐到 `CJ702` 的
`eCO2/eCH2O/TVOC/PM2.5/PM10` 数据模型。

### `inspection_bringup`

包含：

- `bench.launch.py`：台架一键启动入口
- `config/*.yaml`：热像、环境、告警、相机参数
- `docs/udev_rules.example`：稳定设备命名示例
- `docs/b2_migration.md`：迁移到 B2 的网络和接线说明

### `inspection_vision`

包含两类节点和一个真实热像后端：

- `thermal_bridge`：热像桥接，支持 `mock` 和 `senxor_usb`
- `camera_placeholder`：当 `v4l2_camera` 未安装时的占位相机节点

后续接入真实 USB 工业相机时，优先使用 `v4l2_camera`，只需要把设备路径和参数改到
`inspection_bringup/config/cameras.yaml` 与 udev 规则里。

### `inspection_env`

`env_bridge` 当前按 `CJ702` 七合一模块实现，默认走 `9600 8N1` 的
`UART` 单路输入，并同时输出：

- `/env/air_state`
- `/env/temperature_humidity`

### `inspection_alarm`

`alarm_controller` 提供 `/alarm/set_mode` 服务，统一控制语音喇叭、爆闪灯、补光灯。
本轮已实现 `BY-F820` 的串口自由协议喇叭驱动；灯光仍保留占位联动状态。
当前支持的模式：

- `idle`
- `gas_warning`
- `thermal_warning`
- `manual_test`

## 设备接入约定

- USB 工业相机默认按 `1280x720@15fps` 规划
- 热像仪走 `USB`，不强行并入串口总线
- `CJ702` 走 `UART`，`BY-F820` 走串口通信
- 喇叭已经按 `BY-F820` 真实串口协议驱动；灯具仍保留占位逻辑

## 配置入口

优先调整这些文件来对接真实硬件：

- `ws/src/inspection_bringup/config/cameras.yaml`
- `ws/src/inspection_bringup/config/thermal.yaml`
- `ws/src/inspection_bringup/config/env.yaml`
- `ws/src/inspection_bringup/config/alarm.yaml`
- `ws/src/inspection_bringup/docs/udev_rules.example`

## 已验证

以下流程已经在本机通过：

- `python3 -m pip install --user pyserial numpy`
- `colcon build --symlink-install`
- `ros2 launch inspection_bringup bench.launch.py`
- `/alarm/set_mode` 服务调用
- mock 模式下的 topic 与 service 注册

### 喇叭验收

```bash
source /opt/ros/humble/setup.bash
source /home/wyz/peripherel/ws/install/setup.bash
ros2 run inspection_bringup speaker_acceptance --port /dev/ttyCH341USB0
```

默认会先校验 BY-F820 的发送帧，再拉起 `/alarm/set_mode` 做模式联动测试。
如果要完整播放一个音频再结束，推荐：

```bash
ros2 run inspection_bringup speaker_acceptance \
  --port /dev/ttyACM0 \
  --phase service \
  --single-mode manual_test \
  --mode-hold-seconds 20
```

如果只是想指定播放某一个文件，推荐直接用：

```bash
ros2 run inspection_bringup speaker_play_file \
  --port /dev/ttyACM0 \
  --track-id 7
```

## 下一步

- 接入真实 `v4l2_camera` 驱动和 4 路 USB 相机
- 接入真实 `SenXor MI48 USB` 设备联调热像
- 接入真实 `CJ702` 与 `BY-F820` 做串口实机联调
- 对接 DO 控制板，替换爆闪灯与补光灯的占位逻辑
- 完成 B2 上车时的网络、供电和固定点适配
