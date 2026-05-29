"""
协议解析模块
负责解析 ESP32-S3 步进电机控制固件的串口响应，
并提供可扩展接口以支持后续远程控制协议。

固件协议约定（见 README）：
  发送格式: "{en} {res} {dir} {angle} {freq}\n"
  正常响应序列:
    1. 命令回显行       —— 与发送内容完全一致
    2. 状态行           —— "正在运行: N 脉冲 @ 半周期 T µs (F Hz)"
    3. 完成确认行       —— "{command} OK"
  错误响应:
    "ERROR: <说明>" 或 "ERROR <说明>"

扩展方式：
  - 调用 register_classifier(fn) 注入自定义行分类器（优先级高于默认逻辑）
  - 子类重写 _classify_line() 可完全替换协议逻辑
"""

import re
from typing import Optional, Callable, List

from PyQt5.QtCore import QObject, QTimer, pyqtSignal


# ── 响应数据结构 ──────────────────────────────────────────────────────────────

class CommandResult:
    """
    单次命令的完整响应记录，可用于日志、远程协议转发等。

    字段：
      cmd          — 原始发送命令（去除换行）
      echo         — 设备回显的行（通常与 cmd 相同）
      status_lines — 中间状态行列表（如"正在运行..."）
      ok           — 是否成功完成
      error_msg    — 设备返回的错误信息（无错误时为空字符串）
      timed_out    — 是否因超时终止
      timeout_reason — 超时原因描述
      unknown_lines  — 无法分类的其他行
    """

    def __init__(self, cmd: str):
        self.cmd: str = cmd
        self.echo: str = ""
        self.status_lines: List[str] = []
        self.ok: bool = False
        self.error_msg: str = ""
        self.timed_out: bool = False
        self.timeout_reason: str = ""
        self.unknown_lines: List[str] = []

    def to_dict(self) -> dict:
        """序列化为字典，便于远程协议转发。"""
        return {
            "cmd": self.cmd,
            "echo": self.echo,
            "status": self.status_lines,
            "ok": self.ok,
            "error": self.error_msg,
            "timed_out": self.timed_out,
            "timeout_reason": self.timeout_reason,
            "unknown": self.unknown_lines,
        }


# ── 协议处理器 ────────────────────────────────────────────────────────────────

class ProtocolHandler(QObject):
    """
    ESP32-S3 步进电机控制协议解析器。

    信号：
      echo_received(cmd)              — 收到设备对命令的回显
      status_received(line)           — 收到中间状态行
      command_ok(result)              — 命令成功完成，携带 CommandResult
      command_error(result)           — 设备返回 ERROR，携带 CommandResult
      command_timeout(result)         — 超时，携带 CommandResult
      unknown_line(line)              — 无法归类的行
    """

    echo_received    = pyqtSignal(str)           # 收到回显
    status_received  = pyqtSignal(str)           # 收到状态行
    command_ok       = pyqtSignal(object)        # CommandResult（成功）
    command_error    = pyqtSignal(object)        # CommandResult（设备错误）
    command_timeout  = pyqtSignal(object)        # CommandResult（超时）
    unknown_line     = pyqtSignal(str)           # 未知行

    # 等待首次回显的超时（ms）— 超过视为连接异常或设备不匹配
    ECHO_TIMEOUT_MS: int = 3000
    # 最长等待完成时间（ms）— 兜底上限
    MAX_COMPLETION_MS: int = 300_000

    def __init__(self, parent=None):
        super().__init__(parent)
        self._result: Optional[CommandResult] = None

        self._echo_timer = QTimer(self)
        self._echo_timer.setSingleShot(True)
        self._echo_timer.timeout.connect(self._on_echo_timeout)

        self._completion_timer = QTimer(self)
        self._completion_timer.setSingleShot(True)
        self._completion_timer.timeout.connect(self._on_completion_timeout)

        # 自定义行分类器列表，fn(line, result) -> bool
        self._classifiers: List[Callable] = []

    # ── 外部接口 ──────────────────────────────────────────────────────────────

    def command_sent(self, cmd: str):
        """
        命令发出后立即调用，启动回显超时计时器。
        若上一条命令尚未完成，将以超时方式结束它。
        """
        if self._result is not None:
            self._finish_timeout("新命令发出时上一命令尚未完成（可能已丢失响应）")

        self._result = CommandResult(cmd.strip())
        self._echo_timer.start(self.ECHO_TIMEOUT_MS)

    def feed(self, line: str):
        """
        将串口收到的一行喂入协议处理器。
        可在任意线程调用（信号会自动切换到主线程）。
        """
        line = line.strip()
        if not line:
            return

        # 优先走自定义分类器
        for fn in self._classifiers:
            try:
                if fn(line, self._result):
                    return
            except Exception:
                pass

        self._classify_line(line)

    def register_classifier(self, fn: Callable):
        """
        注册自定义行分类器，用于扩展协议（如远程控制协议）。

        fn(line: str, result: Optional[CommandResult]) -> bool
          返回 True  — 行已处理，不再走默认逻辑
          返回 False — 继续走默认分类
        """
        self._classifiers.append(fn)

    def reset(self):
        """取消所有等待状态（断开连接时调用）。"""
        self._echo_timer.stop()
        self._completion_timer.stop()
        self._result = None

    # ── 核心分类逻辑（子类可覆盖）────────────────────────────────────────────

    def _classify_line(self, line: str):
        result = self._result
        cmd = result.cmd if result else ""

        # 1. ERROR 行
        if re.match(r'^ERROR', line, re.IGNORECASE):
            error_body = re.sub(r'^ERROR[:\s]*', '', line, flags=re.IGNORECASE).strip()
            if result:
                result.error_msg = error_body or line
                self._finish_error()
            else:
                # 无待命令时的 ERROR 行，仍发出信号
                r = CommandResult("")
                r.error_msg = error_body or line
                self.command_error.emit(r)
            return

        # 2. 命令回显行
        if result and line == cmd:
            result.echo = line
            self._echo_timer.stop()
            ms = self._estimate_completion_ms(cmd)
            self._completion_timer.start(ms)
            self.echo_received.emit(line)
            return

        # 3. 完成确认行："{cmd} OK"
        if result and line == f"{cmd} OK":
            result.ok = True
            self._finish_ok()
            return

        # 4. 状态行（固件格式："正在运行: N 脉冲 @ ..."）
        if re.search(r'正在运行|脉冲|Running|Pulse', line, re.IGNORECASE):
            if result:
                result.status_lines.append(line)
            self.status_received.emit(line)
            return

        # 5. 兜底：未知行
        if result:
            result.unknown_lines.append(line)
        self.unknown_line.emit(line)

    # ── 完成 / 超时 ───────────────────────────────────────────────────────────

    def _finish_ok(self):
        self._echo_timer.stop()
        self._completion_timer.stop()
        r, self._result = self._result, None
        self.command_ok.emit(r)

    def _finish_error(self):
        self._echo_timer.stop()
        self._completion_timer.stop()
        r, self._result = self._result, None
        self.command_error.emit(r)

    def _finish_timeout(self, reason: str):
        self._echo_timer.stop()
        self._completion_timer.stop()
        r, self._result = self._result, None
        if r:
            r.timed_out = True
            r.timeout_reason = reason
            self.command_timeout.emit(r)

    def _on_echo_timeout(self):
        self._finish_timeout(
            "设备无响应：发送命令后 {:.1f} 秒内未收到回显，"
            "请检查串口连接、波特率设置或目标设备是否正确。".format(
                self.ECHO_TIMEOUT_MS / 1000
            )
        )

    def _on_completion_timeout(self):
        self._finish_timeout(
            "等待超时：命令已被设备回显，但超过预估运行时间后仍未收到完成确认（OK），"
            "电机可能仍在运行或设备出现异常。"
        )

    # ── 运行时间估算 ──────────────────────────────────────────────────────────

    @staticmethod
    def _estimate_completion_ms(cmd: str) -> int:
        """
        根据命令参数（分辨率、角度、频率）估算电机运行时间（ms）。
        格式: "en res dir angle freq"
        结果加 2 秒余量，并限制在 [5 s, MAX_COMPLETION_MS] 范围内。
        """
        try:
            parts = cmd.split()
            resolution = int(parts[1])
            angle      = int(parts[3])
            freq       = int(parts[4])
            if freq <= 0:
                raise ValueError
            pulses = round(angle / 360.0 * resolution)
            run_ms = int(pulses / freq * 1000) + 2000
            return min(max(run_ms, 5000), ProtocolHandler.MAX_COMPLETION_MS)
        except Exception:
            return 30_000  # 默认 30 秒
