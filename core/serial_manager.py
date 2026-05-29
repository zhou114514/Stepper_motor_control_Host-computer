"""
串口管理模块
提供串口连接、断开、命令发送，以及 QThread 异步读取串口返回数据。
集成 ProtocolHandler 解析设备响应，透出协议级别信号。
"""

import serial
import serial.tools.list_ports
from typing import List, Optional
from PyQt5.QtCore import QThread, pyqtSignal, QObject

from core.protocol import ProtocolHandler, CommandResult


class SerialReader(QThread):
    """后台线程：持续读取串口数据并通过信号推送到主线程。"""

    data_received  = pyqtSignal(str)
    error_occurred = pyqtSignal(str)

    def __init__(self, ser: serial.Serial):
        super().__init__()
        self._ser = ser
        self._running = False

    def run(self):
        self._running = True
        while self._running:
            try:
                if self._ser and self._ser.is_open:
                    if self._ser.in_waiting:
                        raw  = self._ser.readline()
                        text = raw.decode("utf-8", errors="replace").strip()
                        if text:
                            self.data_received.emit(text)
                    else:
                        self.msleep(20)
                else:
                    break
            except serial.SerialException as e:
                self.error_occurred.emit(f"串口读取错误: {e}")
                break
            except Exception as e:
                self.error_occurred.emit(f"未知错误: {e}")
                break

    def stop(self):
        self._running = False
        self.wait(500)


class SerialManager(QObject):
    """
    串口管理器，供 UI 层调用。

    底层信号（原始串口数据）：
      connected(port)       — 成功连接
      disconnected()        — 已断开
      data_received(text)   — 收到串口原始行
      error_occurred(msg)   — 串口层错误

    协议级信号（由 ProtocolHandler 解析后发出）：
      cmd_echo(cmd)           — 设备回显了命令（表示设备已收到并开始处理）
      cmd_status(line)        — 设备发来中间状态行
      cmd_ok(result)          — 命令成功完成，result 为 CommandResult
      cmd_error(result)       — 设备返回 ERROR，result 为 CommandResult
      cmd_timeout(result)     — 超时（无回显/无 OK），result 为 CommandResult
      cmd_unknown(line)       — 无法归类的行
    """

    # ── 底层信号 ─────────────────────────────────────────────────────────────
    connected      = pyqtSignal(str)
    disconnected   = pyqtSignal()
    data_received  = pyqtSignal(str)
    error_occurred = pyqtSignal(str)

    # ── 协议级信号 ───────────────────────────────────────────────────────────
    cmd_echo    = pyqtSignal(str)     # 设备回显
    cmd_status  = pyqtSignal(str)     # 中间状态行
    cmd_ok      = pyqtSignal(object)  # CommandResult（成功）
    cmd_error   = pyqtSignal(object)  # CommandResult（设备错误）
    cmd_timeout = pyqtSignal(object)  # CommandResult（超时）
    cmd_unknown = pyqtSignal(str)     # 未知行

    def __init__(self, parent=None):
        super().__init__(parent)
        self._ser:    Optional[serial.Serial]  = None
        self._reader: Optional[SerialReader]   = None

        # 协议解析器
        self._protocol = ProtocolHandler(self)
        self._protocol.echo_received.connect(self.cmd_echo)
        self._protocol.status_received.connect(self.cmd_status)
        self._protocol.command_ok.connect(self.cmd_ok)
        self._protocol.command_error.connect(self.cmd_error)
        self._protocol.command_timeout.connect(self.cmd_timeout)
        self._protocol.unknown_line.connect(self.cmd_unknown)

    # ── 静态工具 ─────────────────────────────────────────────────────────────

    @staticmethod
    def available_ports() -> List[str]:
        """返回当前系统可用 COM 口列表，如 ['COM3', 'COM4']。"""
        ports = serial.tools.list_ports.comports()
        return [p.device for p in sorted(ports, key=lambda x: x.device)]

    # ── 连接 / 断开 ──────────────────────────────────────────────────────────

    def connect(self, port: str, baudrate: int = 115200) -> bool:
        """
        打开串口并启动后台读取线程。
        成功返回 True 并发射 connected 信号，失败发射 error_occurred。
        """
        if self.is_connected():
            self.disconnect()
        try:
            self._ser = serial.Serial(
                port=port,
                baudrate=baudrate,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=0.1,
            )
            self._reader = SerialReader(self._ser)
            self._reader.data_received.connect(self._on_raw_data)
            self._reader.error_occurred.connect(self._on_reader_error)
            self._reader.start()
            self.connected.emit(port)
            return True
        except serial.SerialException as e:
            self.error_occurred.emit(f"无法打开串口 {port}: {e}")
            return False

    def disconnect(self):
        """停止后台线程并关闭串口，同时重置协议状态。"""
        self._protocol.reset()
        if self._reader is not None:
            self._reader.stop()
            self._reader = None
        if self._ser is not None:
            try:
                self._ser.close()
            except Exception:
                pass
            self._ser = None
        self.disconnected.emit()

    def is_connected(self) -> bool:
        return self._ser is not None and self._ser.is_open

    # ── 发送命令 ──────────────────────────────────────────────────────────────

    def send_command(self, cmd: str) -> bool:
        """
        发送一条命令（自动追加换行），并通知协议处理器开始计时。
        成功返回 True，未连接或发送失败返回 False。
        """
        if not self.is_connected():
            self.error_occurred.emit("串口未连接，无法发送命令。")
            return False
        try:
            line = cmd.strip() + "\n"
            self._ser.write(line.encode("utf-8"))
            self._protocol.command_sent(cmd)
            return True
        except serial.SerialException as e:
            self.error_occurred.emit(f"发送失败: {e}")
            return False

    # ── 协议扩展接口 ──────────────────────────────────────────────────────────

    def register_classifier(self, fn):
        """
        注册自定义行分类器，用于扩展协议（远程控制、调试协议等）。
        fn(line: str, result: Optional[CommandResult]) -> bool
        """
        self._protocol.register_classifier(fn)

    # ── 内部槽 ────────────────────────────────────────────────────────────────

    def _on_raw_data(self, text: str):
        self.data_received.emit(text)
        self._protocol.feed(text)

    def _on_reader_error(self, msg: str):
        self.error_occurred.emit(msg)
        self.disconnect()
