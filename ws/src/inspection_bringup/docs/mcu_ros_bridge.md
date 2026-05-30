# ROS 上位机与下位机串口桥接建议

这份说明面向当前仓库的 ROS 2 结构：

- 控制类接口：`/alarm/set_mode`
- 状态类接口：`/env/air_state`、`/env/temperature_humidity`

如果后续把喇叭、灯光、传感器统一收口到一个下位机，推荐把上位机拆成三层：

1. `transport` 层：只负责打开串口、收发字节流
2. `protocol` 层：只负责组帧、解帧、校验、命令字分发
3. `ros node` 层：只负责把 ROS service/topic 映射到协议命令

## 推荐职责划分

### 1. 下发命令

适合这类操作：

- 打开/关闭爆闪灯
- 打开/关闭补光灯
- 切换喇叭模式
- 请求下位机返回一次完整状态

推荐走 `service` 或订阅控制 topic 后调用同步发送函数。

### 2. 接收上报

适合这类数据：

- 气体 / 温湿度传感器实时值
- IO 当前状态
- 故障码 / 心跳

推荐由下位机主动上报，上位机持续读串口并发布 ROS topic。

## 推荐帧结构

如果你还没完全定死协议，建议尽量统一成这种格式：

```text
SOF(2) | LEN(1) | TYPE(1) | CMD(1) | SEQ(1) | PAYLOAD(N) | CRC16(2)
```

说明：

- `SOF`：帧头，比如 `0xAA 0x55`
- `LEN`：从 `TYPE` 到 `PAYLOAD` 的总长度
- `TYPE`：`REQ / ACK / RSP / REPORT`
- `CMD`：命令字
- `SEQ`：请求序号，用来匹配应答
- `CRC16`：建议 `CRC16/MODBUS`

这样做的好处是：

- 命令下发和主动上报能共用一个解帧器
- 上位机能靠 `SEQ` 匹配哪个请求收到了应答
- 后续扩展更多外设时不需要重写框架

## 你现在这个下位机已经实现的实际协议

根据你仓库里的下位机代码：

- [Serial.c](https://raw.githubusercontent.com/WenYuZhou123/unitree-peripherel/main/peripherel/Hardware/Serial.c)
- [Relay.c](https://raw.githubusercontent.com/WenYuZhou123/unitree-peripherel/main/peripherel/Hardware/Relay.c)
- [main.c](https://raw.githubusercontent.com/WenYuZhou123/unitree-peripherel/main/peripherel/User/main.c)

当前实际协议是固定 6 字节，不是变长帧：

```text
0xFF | CMD | ARG1 | ARG2 | CHECKSUM | 0xFE
```

校验规则：

```text
CHECKSUM = CMD ^ ARG1 ^ ARG2
```

命令字：

- `0x01`：`CMD_SET_ONE`
- `0x02`：`CMD_SET_ALL`
- `0x03`：`CMD_QUERY_STATE`

下位机返回帧同样是 6 字节，但语义变成：

```text
0xFF | CMD | STATUS | STATE_MASK | CHECKSUM | 0xFE
```

状态码：

- `0x00`：成功
- `0x01`：校验错误
- `0x02`：无效命令
- `0x03`：无效通道
- `0x04`：无效状态

`STATE_MASK` 的 bit 含义：

- bit0：继电器 1
- bit1：继电器 2
- bit2：继电器 3

所以你现在 ROS 上位机的发送与接收函数，应该优先按这个固定帧协议来写，而不是按前面那种推荐的通用变长协议来写。

## 推荐 ROS 节点结构

建议新建一个统一节点，例如 `lower_machine_bridge`：

- 对外提供 service：控制灯光、喇叭、复位、请求状态
- 对外发布 topic：环境数据、IO 状态、下位机在线状态、故障状态
- 独占一个串口，不要多个 ROS 节点同时打开同一个下位机端口

当前仓库里其实已经有两个可参考模式：

- [alarm_controller.py](/home/wyz/peripherel/ws/src/inspection_alarm/inspection_alarm/alarm_controller.py:1)
  这是“ROS 请求驱动串口命令”的模式
- [env_bridge.py](/home/wyz/peripherel/ws/src/inspection_env/inspection_env/env_bridge.py:1)
  这是“串口数据驱动 ROS topic”的模式

如果统一接下位机，最终应该把这两种模式合到一个桥接节点里。

## 发送函数怎么写

发送函数要做 4 件事：

1. 按协议组帧
2. 写串口
3. 如果该命令要求应答，则按 `SEQ` 等待响应
4. 超时或 CRC 错误时返回失败

示例：

```python
from dataclasses import dataclass
import struct
import threading
import time
from typing import Dict, Optional


SOF = b"\xAA\x55"
TYPE_REQ = 0x01
TYPE_ACK = 0x02
TYPE_RSP = 0x03
TYPE_REPORT = 0x04


def crc16_modbus(data: bytes) -> int:
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 1:
                crc = (crc >> 1) ^ 0xA001
            else:
                crc >>= 1
    return crc & 0xFFFF


def build_frame(frame_type: int, cmd: int, seq: int, payload: bytes = b"") -> bytes:
    body = bytes([frame_type, cmd, seq]) + payload
    frame = SOF + bytes([len(body)]) + body
    crc = crc16_modbus(frame)
    return frame + struct.pack("<H", crc)


@dataclass
class ParsedFrame:
    frame_type: int
    cmd: int
    seq: int
    payload: bytes
    raw: bytes


class LowerMachineClient:
    def __init__(self, stream) -> None:
        self.stream = stream
        self.seq = 0
        self.pending: Dict[int, ParsedFrame] = {}
        self.lock = threading.Lock()

    def next_seq(self) -> int:
        self.seq = (self.seq + 1) & 0xFF
        return self.seq

    def send_request(self, cmd: int, payload: bytes = b"", timeout_s: float = 1.0) -> ParsedFrame:
        seq = self.next_seq()
        frame = build_frame(TYPE_REQ, cmd, seq, payload)
        with self.lock:
            self.stream.write(frame)
            self.stream.flush()

        deadline = time.time() + timeout_s
        while time.time() < deadline:
            response = self.pending.pop(seq, None)
            if response is not None:
                return response
            time.sleep(0.01)
        raise TimeoutError(f"request cmd=0x{cmd:02X} seq={seq} timed out")
```

核心点：

- `send_request()` 不负责读串口
- 它只负责发，并等待接收线程把对应 `seq` 的响应塞回 `pending`

## 接收函数怎么写

接收函数要一直运行，职责是：

1. 从串口读原始字节
2. 从缓冲区里切完整帧
3. 校验 CRC
4. 把 `RSP/ACK` 投递给等待中的请求
5. 把 `REPORT` 分发给 ROS 发布逻辑

示例：

```python
class LowerMachineClient:
    # 省略前面的定义

    def __init__(self, stream) -> None:
        self.stream = stream
        self.seq = 0
        self.pending: Dict[int, ParsedFrame] = {}
        self.rx_buffer = bytearray()
        self.lock = threading.Lock()

    def poll_once(self) -> list[ParsedFrame]:
        chunk = self.stream.read(128)
        if chunk:
            self.rx_buffer.extend(chunk)

        frames: list[ParsedFrame] = []
        while True:
            frame = self._try_parse_one()
            if frame is None:
                break
            frames.append(frame)
        return frames

    def _try_parse_one(self) -> Optional[ParsedFrame]:
        while len(self.rx_buffer) >= 2 and self.rx_buffer[:2] != SOF:
            del self.rx_buffer[0]

        if len(self.rx_buffer) < 2 + 1 + 3 + 2:
            return None

        length = self.rx_buffer[2]
        total_len = 2 + 1 + length + 2
        if len(self.rx_buffer) < total_len:
            return None

        raw = bytes(self.rx_buffer[:total_len])
        del self.rx_buffer[:total_len]

        expected_crc = struct.unpack("<H", raw[-2:])[0]
        actual_crc = crc16_modbus(raw[:-2])
        if actual_crc != expected_crc:
            raise ValueError(
                f"CRC mismatch: actual=0x{actual_crc:04X} expected=0x{expected_crc:04X}"
            )

        body = raw[3:-2]
        frame_type = body[0]
        cmd = body[1]
        seq = body[2]
        payload = body[3:]
        return ParsedFrame(frame_type, cmd, seq, payload, raw)
```

然后在 ROS 节点里开一个周期任务或后台线程：

```python
def _rx_tick(self) -> None:
    try:
        for frame in self.client.poll_once():
            self._dispatch_frame(frame)
    except Exception as exc:
        self.get_logger().warning(f"lower machine rx failed: {exc}")


def _dispatch_frame(self, frame: ParsedFrame) -> None:
    if frame.frame_type in {TYPE_ACK, TYPE_RSP}:
        self.client.pending[frame.seq] = frame
        return

    if frame.frame_type == TYPE_REPORT:
        self._handle_report(frame.cmd, frame.payload)
```

## ROS 节点里的映射怎么写

### 1. ROS service -> 下位机命令

以你现在的 `/alarm/set_mode` 为例：

```python
def _set_mode(self, request, response):
    try:
        payload = self._encode_alarm_payload(request.mode, request.enabled)
        frame = self.client.send_request(cmd=0x10, payload=payload, timeout_s=1.0)
        ok, message = self._decode_common_response(frame.payload)
        response.success = ok
        response.message = message
        return response
    except Exception as exc:
        response.success = False
        response.message = str(exc)
        return response
```

这里你要替换的只有 3 件事：

- `0x10`：下位机定义的命令字
- `_encode_alarm_payload()`：按下位机协议打包
- `_decode_common_response()`：按下位机协议解包

### 2. 下位机主动上报 -> ROS topic

假设下位机把环境数据作为 `CMD=0x20` 主动上报：

```python
def _handle_report(self, cmd: int, payload: bytes) -> None:
    if cmd == 0x20:
        sample = self._decode_env_report(payload)
        self._publish_env(sample)
        return

    if cmd == 0x21:
        status = self._decode_io_report(payload)
        self._publish_io(status)
        return
```

环境数据发布逻辑可以直接沿用现在 [env_bridge.py](/home/wyz/peripherel/ws/src/inspection_env/inspection_env/env_bridge.py:1) 的两个 publisher：

- `/env/air_state`
- `/env/temperature_humidity`

## 你现在这个仓库里最适合的写法

如果后面真的改成“ROS 只对一个下位机串口”，我建议这样落：

1. 新建一个包，比如 `inspection_bridge`
2. 在包里放两个文件：
   - `mcu_protocol.py`：组帧/解帧/CRC/命令字
   - `mcu_bridge.py`：ROS 节点、service、topic、dispatch
3. 把当前 `alarm_controller` 的模式映射逻辑迁进去
4. 把当前 `env_bridge` 的发布逻辑迁进去
5. 保留现有 msg/srv，不先大改上层接口

这样上层算法、状态机、验收脚本几乎不用跟着改。

## 我建议你优先对齐的协议字段

你把下位机代码贴出来后，我最先会对这几项：

1. 帧头是几字节
2. 长度字段是否包含 CRC
3. 校验是异或、和校验还是 `CRC16`
4. 命令字如何区分“请求 / 应答 / 主动上报”
5. 主动上报的环境数据 payload 字段顺序
6. 灯光和喇叭控制命令的 payload 格式
7. 错误码和心跳包格式

只要这 7 项齐了，上位机发送与接收函数就能很快写完。
