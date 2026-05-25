# unitree-peripherel

`unitree-peripherel` 是一个面向 `Jetson Orin Nano + Ubuntu 22.04 + ROS 2 Humble`
的外设接入工作区，用来先完成台架联调，再迁移到 `Unitree B2` 机器狗平台。

当前仓库先提交一版可构建、可启动、接口稳定的框架，重点把以下外设统一纳入同一套
ROS 2 工程：

- `4` 路 USB 工业摄像头
- `1` 路热像仪
- 气体检测传感器
- 温湿度传感器
- 语音喇叭
- 爆闪灯 / 补光灯
- 后续迁移到 `B2` 所需的网络与接线适配

## 当前状态

- 已完成 ROS 2 工作区骨架、消息定义、启动文件和桥接节点框架
- 默认支持 `mock` 模式，未接真机也可以直接 `build` 和 `launch`
- 相机链路优先适配 `v4l2_camera`，未安装该包时自动回退到占位发布器
- 热像、环境传感器、告警控制都预留了串口桥接入口，设备到手后只需要补底层协议

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

定义整个系统共享的消息和服务，保证台架验证和后续上狗时上层接口不变。

### `inspection_bringup`

包含：

- `bench.launch.py`：台架一键启动入口
- `config/*.yaml`：热像、环境、告警、相机参数
- `docs/udev_rules.example`：稳定设备命名示例
- `docs/b2_migration.md`：迁移到 B2 的网络和接线说明

### `inspection_vision`

包含两类节点：

- `thermal_bridge`：热像仪桥接，默认发布 `32FC1` 温度图和热点信息
- `camera_placeholder`：当 `v4l2_camera` 未安装时的占位相机节点

后续接入真实 USB 工业相机时，优先使用 `v4l2_camera`，只需要把设备路径和参数改到
`inspection_bringup/config/cameras.yaml` 与 udev 规则里。

### `inspection_env`

`env_bridge` 统一输出气体与温湿度数据。当前默认使用 mock 数据，也支持后续接
`UART / USB / RS485` 串口桥接。

### `inspection_alarm`

`alarm_controller` 提供 `/alarm/set_mode` 服务，统一控制语音喇叭、爆闪灯、补光灯。
当前支持的模式：

- `idle`
- `gas_warning`
- `thermal_warning`
- `manual_test`

## 设备接入约定

- USB 工业相机默认按 `1280x720@15fps` 规划
- 热像仪与普通 RGB 相机分开处理，不共用驱动抽象
- 气体 / 温湿度传感器先统一上层接口，底层协议待实物补齐
- 喇叭 / 灯具默认通过隔离型 `USB/串口 DO` 控制板驱动，不直接挂 Jetson GPIO

## 配置入口

优先调整这些文件来对接真实硬件：

- `ws/src/inspection_bringup/config/cameras.yaml`
- `ws/src/inspection_bringup/config/thermal.yaml`
- `ws/src/inspection_bringup/config/env.yaml`
- `ws/src/inspection_bringup/config/alarm.yaml`
- `ws/src/inspection_bringup/docs/udev_rules.example`

## 已验证

以下流程已经在本机通过：

- `colcon build --symlink-install`
- `ros2 launch inspection_bringup bench.launch.py`
- `/alarm/set_mode` 服务调用
- mock 模式下的 topic 与 service 注册

## 下一步

- 接入真实 `v4l2_camera` 驱动和 4 路 USB 相机
- 根据实物协议补全热像仪串口解析
- 根据传感器型号补全环境数据解析
- 对接 DO 控制板，替换告警 mock 后端
- 完成 B2 上车时的网络、供电和固定点适配
