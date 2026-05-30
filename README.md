# unitree-peripherel

`unitree-peripherel` 是一个面向 `Jetson Orin Nano + Ubuntu 22.04 + ROS 2 Humble`
的外设接入工作区，用来先完成台架联调，再迁移到 `Unitree B2` 机器狗平台。

当前仓库已经接入或预留了这些外设链路：

- `4` 路 USB 工业摄像头
- `1` 路热像仪
- `CJ702` 七合一环境传感器
- `BY-F820` 语音喇叭
- `3` 路继电器下位机，用于爆闪灯 / 补光灯等开关量
- 后续迁移到 `B2` 所需的网络与接线适配

## 当前状态

- 已完成 ROS 2 工作区骨架、消息定义、启动文件和桥接节点
- `CJ702` 已按 `9600 8N1`、`17` 字节帧接入
- `BY-F820` 已按真实串口协议接入
- 继电器下位机已按固定 `6` 字节协议接入
- 热像后端已接入 `SenXor MI48 USB`，并保留 mock 回退
- 默认仍支持 `mock` 模式，未接真机也可以直接 `build` 和 `launch`

## 目录结构

```text
ws/
├── src/
│   ├── inspection_msgs/      # 自定义 msg / srv
│   ├── inspection_bringup/   # launch、参数、文档、验收脚本
│   ├── inspection_vision/    # USB 相机占位发布器、热像桥接
│   ├── inspection_env/       # 气体 / 温湿度桥接
│   └── inspection_alarm/     # 喇叭 / 继电器 / 告警控制
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

## 如何拉仓库并复现

### 1. 克隆仓库

HTTPS：

```bash
git clone https://github.com/WenYuZhou123/unitree-peripherel.git
cd unitree-peripherel
```

SSH：

```bash
git clone git@github.com:WenYuZhou123/unitree-peripherel.git
cd unitree-peripherel
```

### 2. 进入工作区并安装依赖

```bash
cd ws
source /opt/ros/humble/setup.bash
python3 -m pip install --user pyserial numpy
```

如果你的系统还没有 `colcon`，先安装：

```bash
sudo apt update
sudo apt install -y python3-colcon-common-extensions
```

### 3. 构建工作区

```bash
cd /path/to/unitree-peripherel/ws
source /opt/ros/humble/setup.bash
colcon build --symlink-install
```

### 4. 进入运行环境

```bash
cd /path/to/unitree-peripherel/ws
source /opt/ros/humble/setup.bash
source install/setup.bash
```

### 5. 复现整套台架框架

```bash
ros2 launch inspection_bringup bench.launch.py
```

说明：

- `bench.launch.py` 会启动热像、环境、告警和相机相关节点
- 默认配置下仍可能启用 `mock` 参数，所以做真机验收时请优先使用下面的单项验收命令

## 串口识别

如果当前机器已经把 USB 串口都接好，先看系统识别到的串口：

```bash
ls -l /dev/ttyCH341USB* /dev/ttyUSB* /dev/ttyACM* 2>/dev/null
```

本仓库最近一次实机验收时，对应关系是：

- `CJ702`：`/dev/ttyCH341USB0`
- `BY-F820`：`/dev/ttyCH341USB1`
- 继电器下位机：`/dev/ttyCH341USB2`

这组端口号不是协议的一部分，换机器、换插口或重新枚举后可能变化。
如果要长期稳定使用，建议按 [udev_rules.example](/home/wyz/peripherel/ws/src/inspection_bringup/docs/udev_rules.example:1)
配置固定别名。

## 快速验证功能

### 1. 启动告警服务后手动切模式

```bash
ros2 service call /alarm/set_mode inspection_msgs/srv/SetAlarmMode \
  "{mode: thermal_warning, enabled: true}"
```

### 2. 直接播放喇叭音频

```bash
ros2 run inspection_bringup speaker_play_file \
  --port /dev/ttyCH341USB1 \
  --track-id 1
```

### 3. 查询继电器板状态

```bash
ros2 run inspection_alarm relay_cli \
  --port /dev/ttyCH341USB2 \
  --action query
```

## 单项验收命令

下面这些命令是现场验收时最直接可用的版本。执行前先进入环境：

```bash
cd /path/to/unitree-peripherel/ws
source /opt/ros/humble/setup.bash
source install/setup.bash
```

### 空气质量传感器 `CJ702`

完整验收：

```bash
ros2 run inspection_bringup env_acceptance \
  --phase both \
  --port /dev/ttyCH341USB0
```

只验串口原始收数：

```bash
ros2 run inspection_bringup env_acceptance \
  --phase serial \
  --port /dev/ttyCH341USB0
```

只验 ROS 话题：

```bash
ros2 run inspection_bringup env_acceptance \
  --phase topic \
  --port /dev/ttyCH341USB0
```

通过标准：

- 串口阶段连续读到合法 `17` 字节帧
- 话题阶段打印 `device_ok=True`
- `/env/air_state` 与 `/env/temperature_humidity` 有真实数值，不是全零

### 语音喇叭 `BY-F820`

完整验收：

```bash
ros2 run inspection_bringup speaker_acceptance \
  --phase both \
  --port /dev/ttyCH341USB1
```

只验串口协议发送：

```bash
ros2 run inspection_bringup speaker_acceptance \
  --phase serial \
  --port /dev/ttyCH341USB1
```

只验 ROS 服务联动：

```bash
ros2 run inspection_bringup speaker_acceptance \
  --phase service \
  --port /dev/ttyCH341USB1
```

指定播放单个音频文件：

```bash
ros2 run inspection_bringup speaker_play_file \
  --port /dev/ttyCH341USB1 \
  --track-id 1
```

如果要让单条语音完整播完再结束：

```bash
ros2 run inspection_bringup speaker_acceptance \
  --port /dev/ttyCH341USB1 \
  --phase service \
  --single-mode manual_test \
  --mode-hold-seconds 20
```

通过标准：

- 串口阶段 `stop / set_volume / play_track` 发送帧正常
- 服务阶段 `manual_test / gas_warning / thermal_warning / idle` 返回 `success=True`
- 现场能听到对应语音

### 继电器下位机

查询状态：

```bash
ros2 run inspection_alarm relay_cli \
  --port /dev/ttyCH341USB2 \
  --action query
```

打开第 `1` 路：

```bash
ros2 run inspection_alarm relay_cli \
  --port /dev/ttyCH341USB2 \
  --action set-one \
  --channel 1 \
  --state 1
```

关闭第 `1` 路：

```bash
ros2 run inspection_alarm relay_cli \
  --port /dev/ttyCH341USB2 \
  --action set-one \
  --channel 1 \
  --state 0
```

打开第 `2` 路：

```bash
ros2 run inspection_alarm relay_cli \
  --port /dev/ttyCH341USB2 \
  --action set-one \
  --channel 2 \
  --state 1
```

关闭第 `2` 路：

```bash
ros2 run inspection_alarm relay_cli \
  --port /dev/ttyCH341USB2 \
  --action set-one \
  --channel 2 \
  --state 0
```

打开第 `3` 路：

```bash
ros2 run inspection_alarm relay_cli \
  --port /dev/ttyCH341USB2 \
  --action set-one \
  --channel 3 \
  --state 1
```

关闭第 `3` 路：

```bash
ros2 run inspection_alarm relay_cli \
  --port /dev/ttyCH341USB2 \
  --action set-one \
  --channel 3 \
  --state 0
```

全部打开：

```bash
ros2 run inspection_alarm relay_cli \
  --port /dev/ttyCH341USB2 \
  --action set-all \
  --mask 0x07
```

全部关闭：

```bash
ros2 run inspection_alarm relay_cli \
  --port /dev/ttyCH341USB2 \
  --action set-all \
  --mask 0x00
```

通过标准：

- `query` 能拿到合法回包
- 单路开关后 `mask` 与实际继电器状态一致
- `set-all 0x07` 后三路全开
- `set-all 0x00` 后三路全关

## 已验证

以下流程已经在本机通过：

- `python3 -m pip install --user pyserial numpy`
- `colcon build --symlink-install`
- `ros2 launch inspection_bringup bench.launch.py`
- `/alarm/set_mode` 服务调用
- `CJ702` 真机串口与 ROS 话题验收
- `BY-F820` 真机串口与 ROS 服务验收
- 继电器下位机 `query / set-one / set-all` 收发验收

## 代码入口

比较关键的代码文件如下：

- [env_bridge.py](/home/wyz/peripherel/ws/src/inspection_env/inspection_env/env_bridge.py:1)
- [cj702.py](/home/wyz/peripherel/ws/src/inspection_env/inspection_env/cj702.py:1)
- [alarm_controller.py](/home/wyz/peripherel/ws/src/inspection_alarm/inspection_alarm/alarm_controller.py:1)
- [by_f820.py](/home/wyz/peripherel/ws/src/inspection_alarm/inspection_alarm/by_f820.py:1)
- [relay_mcu.py](/home/wyz/peripherel/ws/src/inspection_alarm/inspection_alarm/relay_mcu.py:1)
- [speaker_acceptance.py](/home/wyz/peripherel/ws/src/inspection_bringup/inspection_bringup/speaker_acceptance.py:1)
- [env_acceptance.py](/home/wyz/peripherel/ws/src/inspection_bringup/inspection_bringup/env_acceptance.py:1)

## 相关文档

- [b2_migration.md](/home/wyz/peripherel/ws/src/inspection_bringup/docs/b2_migration.md:1)
- [udev_rules.example](/home/wyz/peripherel/ws/src/inspection_bringup/docs/udev_rules.example:1)
- [mcu_ros_bridge.md](/home/wyz/peripherel/ws/src/inspection_bringup/docs/mcu_ros_bridge.md:1)

## 下一步

- 给 `CJ702 / BY-F820 / relay MCU` 配稳定 `udev` 别名
- 把继电器下位机进一步接入 `/alarm/set_mode` 联动链路
- 接入真实 `v4l2_camera` 驱动和 `4` 路 USB 工业相机
- 接入真实 `SenXor MI48 USB` 热像设备
- 完成 `B2` 上车时的网络、供电和固定点适配
