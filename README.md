# 步进电机控制上位机

基于 **PyQt5** 的 ESP32-S3 步进电机控制上位机，配合 [ESP32-S3 步进电机控制固件](https://github.com/zhou114514/Stepper_motor_control.git) 使用。通过串口与 ESP32-S3 开发板通信，支持手动控制、预设快速执行以及 TCP 远程控制三种操作方式。

---

## 配套固件

本程序是 **[ESP32S3 脉冲控制步进电机控制程序](https://github.com/zhou114514/Stepper_motor_control.git)** 的 PC 端上位机。

| 项目 | 说明 |
| --- | --- |
| 固件仓库 | [zhou114514/Stepper_motor_control](https://github.com/zhou114514/Stepper_motor_control.git) |
| 目标芯片 | ESP32-S3 |
| 通信接口 | UART（USB-C，115200 波特率，8N1） |
| 固件串口命令格式 | `使能 分辨率 方向 角度 频率\n` |

运行前请先将固件烧录到 ESP32-S3 开发板，并通过 USB-C 连接至上位机所在 PC。

---

## 功能特性

- **串口管理**：自动枚举并每 3 秒刷新可用 COM 口，支持 9600 ~ 460800 波特率
- **手动控制面板**：可视化设置使能、方向、细分分辨率（下拉框 / 拨码开关两种选择方式）、角度、频率，实时预览待发送命令
- **快速控制面板**：从 `config/presets.json` 加载预设，以卡片形式展示，一键执行
- **协议解析**：自动解析固件回显、状态行、OK 确认和 ERROR 响应，超时自动弹出提示
- **彩色通信日志**：区分发送（青色）、接收（橙色）、成功（绿色）、错误（红色）、协议状态（紫色）、系统信息（蓝色）
- **TCP 远程控制服务**：内置 JSON/TCP 服务器（默认端口 9527），允许外部程序远程控制步进电机
- **高 DPI 支持**：自动适配高分辨率屏幕

---

## 目录结构

```
步进电机控制上位机/
├── main.py                  # 程序入口
├── core/
│   ├── serial_manager.py    # 串口管理（连接、读写、信号）
│   ├── protocol.py          # 固件串口协议解析（回显、状态、OK、ERROR、超时）
│   ├── tcp_server.py        # TCP 远程控制服务器（JSON 协议）
│   └── subdivision.py       # 细分精度与拨码开关双向映射
├── ui/
│   ├── main_window.py       # 主窗口（串口栏、TCP 栏、Tab、日志面板）
│   ├── manual_panel.py      # 手动控制面板
│   ├── quick_panel.py       # 快速控制面板（预设卡片）
│   └── switch_widget.py     # 拨码开关可视化控件（SW5-SW8）
├── config/
│   └── presets.json         # 快速控制预设配置
├── 细分精度.csv              # 驱动器拨码开关与分辨率映射表
└── 远程控制协议              # TCP 远程控制协议文档（纯文本）
```

---

## 运行环境

| 依赖 | 版本要求 |
| --- | --- |
| Python | 3.8+ |
| PyQt5 | 5.x |
| pyserial | 3.x |

推荐使用 conda 管理环境：

```bash
conda create -n stepper_env python=3.10
conda activate stepper_env
pip install PyQt5 pyserial
```

或直接 pip 安装：

```bash
pip install PyQt5 pyserial
```

---

## 启动方式

```bash
python main.py
```

---

## 界面说明

### 顶部串口连接栏

| 控件 | 说明 |
| --- | --- |
| 串口下拉框 | 自动枚举系统 COM 口，每 3 秒刷新一次 |
| 波特率下拉框 | 默认 115200，与固件一致 |
| 刷新按钮 | 手动刷新 COM 口列表 |
| 连接 / 断开按钮 | 切换串口连接状态 |
| 状态指示灯（●） | 绿色=已连接，红色=未连接 |

### TCP 远程控制栏

| 控件 | 说明 |
| --- | --- |
| 端口输入框 | TCP 服务器监听端口，默认 9527，范围 1024 ~ 65535 |
| 重启按钮 | 修改端口后点击重启服务 |
| 状态指示灯（●） | 绿色=服务运行中，橙色=服务已停止 |
| 客户端状态标签 | 显示当前连接的客户端 IP:端口 |

程序启动时自动启动 TCP 服务，无需手动操作。

### 手动控制面板（Tab：🎛 手动控制）

1. **基本控制**：点击"已使能 / 未使能"按钮切换使能状态；单选按钮选择顺时针 ↻ 或逆时针 ↺
2. **细分分辨率**：支持两种选择方式——
   - **下拉框选择**：直接选择分辨率（含细分倍数说明，如 `1600 脉冲/圈（细分 ×8）`）
   - **拨码开关配置**：可视化模拟 SW5~SW8 四位拨码开关，与下拉框实时双向同步
3. **运动参数**：输入角度（1 ~ 36000°）和脉冲频率（1 ~ 416666 Hz）
4. **发送区**：实时预览待发送命令字符串，点击"发送 ▶"发出

### 快速控制面板（Tab：⚡ 快速控制）

从 `config/presets.json` 加载预设，每条预设显示为一张卡片，包含：
- 预设名称与描述
- 参数摘要（使能、分辨率、方向、角度、频率）
- "▶ 执行"按钮

支持"🔄 刷新预设"（重新加载配置文件）和"✏ 编辑配置"（用系统编辑器打开 `presets.json`）。

### 通信日志面板

显示所有通信记录，颜色区分如下：

| 颜色 | 含义 |
| --- | --- |
| 青色 | 发送的命令 |
| 橙色 | 原始串口接收数据 |
| 紫色 | 协议状态（回显确认、未知行等） |
| 浅绿 | 命令成功完成 |
| 红色 | 错误 / 超时 |
| 蓝色 | 系统信息（连接/断开/TCP 状态等） |

---

## 预设配置文件

编辑 `config/presets.json` 即可自定义快速控制面板中的预设卡片：

```json
{
  "presets": [
    {
      "name": "顺时针 90°",
      "description": "以 1000 Hz 顺时针转动 90 度",
      "enable": 1,
      "resolution": 1600,
      "direction": 1,
      "angle": 90,
      "frequency": 1000
    },
    {
      "name": "逆时针 360°",
      "description": "整圈反转",
      "enable": 1,
      "resolution": 3200,
      "direction": 0,
      "angle": 360,
      "frequency": 2000
    }
  ]
}
```

字段说明：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `name` | string | 预设名称（在快速控制面板及 TCP RunPreset 中使用） |
| `description` | string | 可选描述文字 |
| `enable` | int | 1=使能，0=关闭驱动器 |
| `resolution` | int | 分辨率（脉冲/圈），须为合法值 |
| `direction` | int | 1=顺时针，0=逆时针 |
| `angle` | int | 旋转角度（度，1 ~ 36000） |
| `frequency` | int | 脉冲频率（Hz，> 0） |

---

## 细分分辨率对照表

驱动器拨码开关（SW5~SW8）与分辨率的对应关系如下，与固件使用相同的合法值列表：

| 细分精度 | 脉冲数/圈 | SW5 | SW6 | SW7 | SW8 |
| --- | --- | --- | --- | --- | --- |
| ×2 | 400 | OFF | ON | ON | ON |
| ×4 | 800 | ON | OFF | ON | ON |
| ×8 | 1600 | OFF | OFF | ON | ON |
| ×16 | 3200 | ON | ON | OFF | ON |
| ×32 | 6400 | OFF | ON | OFF | ON |
| ×64 | 12800 | ON | OFF | OFF | ON |
| ×128 | 25600 | OFF | OFF | OFF | ON |
| ×5 | 1000 | ON | ON | ON | OFF |
| ×10 | 2000 | OFF | ON | ON | OFF |
| ×20 | 4000 | ON | OFF | ON | OFF |
| ×25 | 5000 | OFF | OFF | ON | OFF |
| ×40 | 8000 | ON | ON | OFF | OFF |
| ×50 | 10000 | OFF | ON | OFF | OFF |
| ×100 | 20000 | ON | OFF | OFF | OFF |
| ×125 | 25000 | OFF | OFF | OFF | OFF |

> **注意**：程序中设置的分辨率需与驱动器拨码开关实际位置一致，否则电机转动角度将与预期不符。

---

## TCP 远程控制协议

上位机内置 TCP 服务器（默认端口 **9527**），允许外部程序通过 JSON 消息远程控制步进电机。

### 连接参数

| 参数 | 值 |
| --- | --- |
| 地址 | 运行上位机的主机 IP |
| 端口 | 9527（可在 UI 中修改并重启） |
| 编码 | UTF-8 |
| 分隔符 | `\n`（每条消息末尾追加换行符） |
| 并发 | 支持多客户端连接，命令串行执行 |

### 消息格式

**请求**
```json
{"opcode": "<命令名>", "parameter": {<参数字典>}}
```

**响应**
```json
{"IsSuccessful": true/false, "Value": <返回值或"">, "ErrorMessage": "Null 或错误描述"}
```

### 指令列表

#### 版本检查

```json
→ {"opcode": "check", "parameter": {}}
← {"IsSuccessful": true, "Value": {"version": "1.0.0"}, "ErrorMessage": "Null"}
```

#### 串口连接状态检查

```json
→ {"opcode": "ConnectDevice", "parameter": {}}
← {"IsSuccessful": true,  "Value": "", "ErrorMessage": "Null"}       // 已连接
← {"IsSuccessful": false, "Value": "", "ErrorMessage": "串口未连接"} // 未连接
```

#### 控制电机运动（同步阻塞）

```json
→ {
    "opcode": "Move",
    "parameter": {
      "enable":     1,
      "resolution": 1600,
      "direction":  1,
      "angle":      90,
      "frequency":  1000
    }
  }
← {"IsSuccessful": true, "Value": {"status": ["正在运行: 400 脉冲 @ 500 µs (1000 Hz)"]}, "ErrorMessage": "Null"}
```

> 此命令为**同步阻塞**，上位机等待固件返回完成确认（含电机实际运行时间）后才响应，超时上限为 35 秒。

#### 执行预设

```json
→ {"opcode": "RunPreset", "parameter": {"name": "顺时针 90°"}}
← {"IsSuccessful": true, "Value": {"status": [...]}, "ErrorMessage": "Null"}
```

预设名称须与 `config/presets.json` 中的 `name` 字段完全一致。

### 常见错误响应

| ErrorMessage | 原因 |
| --- | --- |
| `无效的 JSON 格式` | 请求不是合法 JSON |
| `缺少 opcode 字段` | 请求缺少 opcode 键 |
| `参数错误: <详情>` | parameter 字段缺失或类型错误 |
| `未知 opcode: <名称>` | 不支持的操作码 |
| `串口未连接或发送失败` | 上位机未连接步进电机控制器 |
| `无效分辨率: <值>` | resolution 不在合法列表中 |
| `未找到预设: <名称>` | presets.json 中无对应名称 |
| `命令执行超时，设备可能无响应` | 35 秒内未收到设备完成信号 |

完整协议说明见项目根目录下的《**远程控制协议**》文档。

---

## 架构说明

```
主线程（PyQt5 事件循环）
  ├── MainWindow          — 主窗口，协调所有模块
  ├── SerialManager       — 串口连接/断开/发送
  │     └── SerialReader  — QThread，后台异步读串口
  ├── ProtocolHandler     — 解析固件串口响应（回显→状态→OK/ERROR/超时）
  └── TcpServer           — TCP 服务管理（Qt 对象）
        ├── _ServerThread — 后台线程，监听端口
        └── _ClientHandler — 每客户端独立线程，解析 JSON
              └── 跨线程信号 execute_requested → 主线程槽函数执行命令
```

串口命令执行全程在主线程，TCP 线程通过 `threading.Event` 阻塞等待主线程完成后再返回响应，`_cmd_lock` 保证同一时刻只有一条命令在等待串口响应。

---

## 常见问题

**Q：程序启动后找不到 COM 口**  
A：确认 ESP32-S3 通过 USB-C 连接至电脑，并已安装 CH340 驱动（或板载 USB 驱动），点击"刷新"按钮重新扫描。

**Q：发送命令后提示"设备无响应"**  
A：检查波特率是否设置为 115200，确认选择的是烧录了配套固件的 ESP32-S3 串口，而非其他设备。

**Q：TCP 服务器启动失败**  
A：端口可能被占用，在 TCP 栏修改端口号后点击"重启"按钮。Windows 防火墙可能拦截入站连接，请将上位机加入防火墙白名单。

**Q：预设卡片为空**  
A：确认 `config/presets.json` 文件存在且 JSON 格式正确，点击"🔄 刷新预设"重新加载。

---

## License

[Mozilla Public License 2.0](LICENSE)
