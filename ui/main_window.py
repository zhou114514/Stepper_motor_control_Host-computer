"""
主窗口
包含：顶部串口连接栏、TCP 远程控制栏、中部 Tab（手动控制 / 快速控制）、底部日志面板。
"""

import json
import os
import sys
from datetime import datetime
from typing import Optional

from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QComboBox, QTabWidget,
    QTextEdit, QSplitter, QStatusBar, QMessageBox, QSpinBox,
)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QFont, QTextCursor

from core.serial_manager import SerialManager
from core.protocol import CommandResult
from core.tcp_server import TcpServer, _CommandRequest, VERSION as TCP_VERSION
from core import subdivision
from ui.manual_panel import ManualPanel
from ui.quick_panel import QuickPanel

if getattr(sys, 'frozen', False):
    _PRESETS_PATH = os.path.join(sys._MEIPASS, "config", "presets.json")
else:
    _PRESETS_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config", "presets.json")


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("步进电机控制上位机")
        self.setMinimumSize(560, 480)
        self.resize(780, 660)

        self._serial = SerialManager(self)
        self._tcp = TcpServer(self)

        # 当前等待串口响应的 TCP 命令请求（同一时刻至多一个）
        self._pending_tcp_req: Optional[_CommandRequest] = None

        self._setup_ui()
        self._connect_signals()
        self._refresh_ports()

        # 定时刷新 COM 口列表（每 3 秒）
        self._port_timer = QTimer(self)
        self._port_timer.timeout.connect(self._refresh_ports)
        self._port_timer.start(3000)

        # 自动启动 TCP 远程控制服务
        self._tcp.start(self._tcp_port_spin.value())

    # ── UI 搭建 ──────────────────────────────────────────────────────────────

    def _setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # 串口连接栏
        root.addWidget(self._build_serial_bar())

        # TCP 远程控制栏
        root.addWidget(self._build_tcp_bar())

        # 主体：Tab + 日志（可拖动分割）
        splitter = QSplitter(Qt.Vertical)
        splitter.setHandleWidth(4)

        # Tab
        self._tab = QTabWidget()
        self._tab.setTabPosition(QTabWidget.North)
        self._tab.setStyleSheet("""
            QTabBar::tab { padding: 5px 16px; font-size: 12px; }
            QTabBar::tab:selected { font-weight: bold; }
        """)

        self._manual_panel = ManualPanel()
        self._quick_panel = QuickPanel()
        self._tab.addTab(self._manual_panel, "🎛  手动控制")
        self._tab.addTab(self._quick_panel, "⚡  快速控制")
        splitter.addWidget(self._tab)

        # 日志面板
        splitter.addWidget(self._build_log_panel())
        splitter.setSizes([480, 200])

        root.addWidget(splitter, stretch=1)

        # 状态栏
        self._status_bar = QStatusBar()
        self.setStatusBar(self._status_bar)
        self._status_bar.showMessage("未连接")

    def _build_serial_bar(self) -> QWidget:
        bar = QWidget()
        bar.setStyleSheet("background-color: #2c3e50;")
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(12, 4, 12, 4)
        layout.setSpacing(8)

        label_style = "color: #ecf0f1; font-size: 12px;"

        port_lbl = QLabel("串口：")
        port_lbl.setStyleSheet(label_style)
        layout.addWidget(port_lbl)

        self._port_combo = QComboBox()
        self._port_combo.setStyleSheet("background: white; padding: 1px 4px; font-size: 12px;")
        layout.addWidget(self._port_combo)

        baud_lbl = QLabel("波特率：")
        baud_lbl.setStyleSheet(label_style)
        layout.addWidget(baud_lbl)

        self._baud_combo = QComboBox()
        for b in ["9600", "19200", "38400", "57600", "115200", "230400", "460800"]:
            self._baud_combo.addItem(b, int(b))
        self._baud_combo.setCurrentText("115200")
        self._baud_combo.setStyleSheet("background: white; padding: 1px 4px; font-size: 12px;")
        layout.addWidget(self._baud_combo)

        self._refresh_btn = QPushButton("刷新")
        self._refresh_btn.setStyleSheet("""
            QPushButton { background:#7f8c8d; color:white; border:none; border-radius:4px;
                          font-size:11px; padding: 3px 10px; }
            QPushButton:hover { background:#95a5a6; }
        """)
        self._refresh_btn.clicked.connect(self._refresh_ports)
        layout.addWidget(self._refresh_btn)

        layout.addStretch()

        self._connect_btn = QPushButton("连接")
        self._connect_btn.setStyleSheet(self._conn_btn_style(False))
        layout.addWidget(self._connect_btn)

        self._conn_status = QLabel("●")
        self._conn_status.setStyleSheet("color: #e74c3c; font-size: 16px;")
        layout.addWidget(self._conn_status)

        return bar

    def _build_tcp_bar(self) -> QWidget:
        bar = QWidget()
        bar.setStyleSheet("background-color: #1a252f; border-top: 1px solid #34495e;")
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(12, 3, 12, 3)
        layout.setSpacing(8)

        label_style = "color: #bdc3c7; font-size: 12px;"

        tcp_lbl = QLabel("TCP 远程：")
        tcp_lbl.setStyleSheet(label_style)
        layout.addWidget(tcp_lbl)

        port_lbl = QLabel("端口：")
        port_lbl.setStyleSheet(label_style)
        layout.addWidget(port_lbl)

        self._tcp_port_spin = QSpinBox()
        self._tcp_port_spin.setRange(1024, 65535)
        self._tcp_port_spin.setValue(9527)
        self._tcp_port_spin.setFixedWidth(72)
        self._tcp_port_spin.setStyleSheet(
            "background: white; padding: 1px 3px; font-size: 12px; border-radius: 3px;"
        )
        layout.addWidget(self._tcp_port_spin)

        self._tcp_restart_btn = QPushButton("重启")
        self._tcp_restart_btn.setToolTip("修改端口后点击重启服务")
        self._tcp_restart_btn.setStyleSheet("""
            QPushButton { background:#7f8c8d; color:white; border:none; border-radius:4px;
                          font-size:11px; padding: 2px 10px; }
            QPushButton:hover { background:#95a5a6; }
        """)
        layout.addWidget(self._tcp_restart_btn)

        self._tcp_status = QLabel("●")
        self._tcp_status.setStyleSheet("color: #7f8c8d; font-size: 16px;")
        layout.addWidget(self._tcp_status)

        self._tcp_client_lbl = QLabel("启动中…")
        self._tcp_client_lbl.setStyleSheet("color: #7f8c8d; font-size: 11px;")
        layout.addWidget(self._tcp_client_lbl)

        layout.addStretch()

        hint_lbl = QLabel("协议文档：远程控制协议")
        hint_lbl.setStyleSheet("color: #566573; font-size: 10px;")
        layout.addWidget(hint_lbl)

        return bar

    def _build_log_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(8, 4, 8, 8)
        layout.setSpacing(4)

        header = QHBoxLayout()
        log_title = QLabel("通信日志")
        log_font = QFont()
        log_font.setBold(True)
        log_title.setFont(log_font)
        header.addWidget(log_title)
        header.addStretch()

        clear_btn = QPushButton("清空")
        clear_btn.setStyleSheet("""
            QPushButton { background:#bdc3c7; border:none; border-radius:4px;
                          font-size:11px; padding: 2px 8px; }
            QPushButton:hover { background:#95a5a6; }
        """)
        clear_btn.clicked.connect(lambda: self._log.clear())
        header.addWidget(clear_btn)
        layout.addLayout(header)

        self._log = QTextEdit()
        self._log.setReadOnly(True)
        self._log.setFont(QFont("Consolas", 10))
        self._log.setStyleSheet(
            "background:#1e1e1e; color:#d4d4d4; border:1px solid #444; border-radius:4px;"
        )
        layout.addWidget(self._log)
        return panel

    # ── 信号连接 ──────────────────────────────────────────────────────────────

    def _connect_signals(self):
        self._connect_btn.clicked.connect(self._toggle_connection)

        # 底层串口信号
        self._serial.connected.connect(self._on_connected)
        self._serial.disconnected.connect(self._on_disconnected)
        self._serial.data_received.connect(self._on_data_received)
        self._serial.error_occurred.connect(self._on_error)

        # 协议级信号
        self._serial.cmd_echo.connect(self._on_cmd_echo)
        self._serial.cmd_status.connect(self._on_cmd_status)
        self._serial.cmd_ok.connect(self._on_cmd_ok)
        self._serial.cmd_error.connect(self._on_cmd_error)
        self._serial.cmd_timeout.connect(self._on_cmd_timeout)
        self._serial.cmd_unknown.connect(self._on_cmd_unknown)

        # 手动控制面板发命令
        self._manual_panel.command_ready.connect(self._send_command)

        # 快速控制面板发命令
        self._quick_panel.command_ready.connect(self._send_command)

        # TCP 远程控制服务器
        self._tcp_restart_btn.clicked.connect(self._restart_tcp_server)
        self._tcp.server_started.connect(self._on_tcp_started)
        self._tcp.server_stopped.connect(self._on_tcp_stopped)
        self._tcp.server_error.connect(self._on_tcp_error)
        self._tcp.client_connected.connect(self._on_tcp_client_connected)
        self._tcp.client_disconnected.connect(self._on_tcp_client_disconnected)
        self._tcp.log_message.connect(self._on_tcp_log)
        self._tcp.execute_requested.connect(self._on_tcp_execute)

    # ── 串口操作 ──────────────────────────────────────────────────────────────

    def _refresh_ports(self):
        current = self._port_combo.currentText()
        ports = SerialManager.available_ports()
        self._port_combo.blockSignals(True)
        self._port_combo.clear()
        if ports:
            self._port_combo.addItems(ports)
            if current in ports:
                self._port_combo.setCurrentText(current)
        else:
            self._port_combo.addItem("（无可用串口）")
        self._port_combo.blockSignals(False)

    def _toggle_connection(self):
        if self._serial.is_connected():
            self._serial.disconnect()
        else:
            port = self._port_combo.currentText()
            baud = self._baud_combo.currentData()
            if not port or port.startswith("（"):
                self._append_log("[错误] 请先选择有效串口", error=True)
                return
            self._serial.connect(port, baud)

    def _send_command(self, cmd: str):
        if not self._serial.is_connected():
            self._append_log("[错误] 串口未连接，无法发送命令。", error=True)
            return
        ok = self._serial.send_command(cmd)
        if ok:
            self._append_log(f"[发送] {cmd}", sent=True)

    # ── 串口回调 ──────────────────────────────────────────────────────────────

    def _on_connected(self, port: str):
        self._connect_btn.setText("断开")
        self._connect_btn.setStyleSheet(self._conn_btn_style(True))
        self._conn_status.setStyleSheet("color: #27ae60; font-size: 18px;")
        self._status_bar.showMessage(f"已连接：{port}  @  {self._baud_combo.currentText()} bps")
        self._append_log(f"[系统] 已连接 {port}，波特率 {self._baud_combo.currentText()}")

    def _on_disconnected(self):
        self._connect_btn.setText("连接")
        self._connect_btn.setStyleSheet(self._conn_btn_style(False))
        self._conn_status.setStyleSheet("color: #e74c3c; font-size: 18px;")
        self._status_bar.showMessage("未连接")
        self._append_log("[系统] 串口已断开")

    def _on_data_received(self, text: str):
        self._append_log(f"[接收] {text}", received=True)

    def _on_error(self, msg: str):
        self._append_log(f"[串口错误] {msg}", error=True)
        self._status_bar.showMessage(f"错误：{msg}")

    # ── 协议级回调 ────────────────────────────────────────────────────────────

    def _on_cmd_echo(self, cmd: str):
        self._append_log(f"[回显] 设备已收到命令，开始执行…", proto=True)

    def _on_cmd_status(self, line: str):
        self._append_log(f"[状态] {line}", proto=True)

    def _on_cmd_ok(self, result: CommandResult):
        status_summary = "；".join(result.status_lines) if result.status_lines else "（无状态行）"
        self._append_log(f"[完成] 命令执行成功 ✓  {status_summary}", ok=True)
        self._status_bar.showMessage("命令执行完成")
        self._complete_tcp_request(True, {"status": result.status_lines}, "Null")

    def _on_cmd_error(self, result: CommandResult):
        msg = result.error_msg or "（设备未提供错误详情）"
        self._append_log(f"[设备错误] {msg}", error=True)
        self._status_bar.showMessage(f"设备错误：{msg}")
        from_tcp = self._pending_tcp_req is not None
        self._complete_tcp_request(False, "", msg)
        if not from_tcp:
            self._show_warning(
                "设备返回错误",
                f"设备报告了一个错误：\n\n{msg}\n\n"
                f"发送的命令：{result.cmd}"
            )

    def _on_cmd_timeout(self, result: CommandResult):
        reason = result.timeout_reason
        if not result.echo:
            title = "设备无响应"
            detail = (
                f"发送命令后未收到设备回显。\n\n"
                f"可能原因：\n"
                f"  • 串口连接已断开或不稳定\n"
                f"  • 波特率与设备不匹配（当前：{self._baud_combo.currentText()} bps）\n"
                f"  • 连接的设备不是 ESP32-S3 步进电机控制器\n\n"
                f"发送的命令：{result.cmd}"
            )
        else:
            title = "等待响应超时"
            detail = (
                f"设备已回显命令，但超过预估时间后未收到完成确认。\n\n"
                f"可能原因：\n"
                f"  • 电机仍在运行（角度/速度参数导致时间过长）\n"
                f"  • 设备在运行中出现异常\n\n"
                f"发送的命令：{result.cmd}\n"
                f"详情：{reason}"
            )
        self._append_log(f"[超时] {reason}", error=True)
        self._status_bar.showMessage(f"超时：{title}")
        from_tcp = self._pending_tcp_req is not None
        self._complete_tcp_request(False, "", reason)
        if not from_tcp:
            self._show_warning(title, detail)

    def _on_cmd_unknown(self, line: str):
        self._append_log(f"[未知] {line}", proto=True)

    # ── TCP 服务器控制 ────────────────────────────────────────────────────────

    def _restart_tcp_server(self):
        """用当前端口值重启 TCP 服务（修改端口后使用）。"""
        port = self._tcp_port_spin.value()
        self._tcp_restart_btn.setEnabled(False)
        self._tcp.start(port)

    def _on_tcp_started(self, port: int):
        self._tcp_status.setStyleSheet("color: #27ae60; font-size: 16px;")
        self._tcp_port_spin.setEnabled(True)
        self._tcp_restart_btn.setEnabled(True)
        self._tcp_client_lbl.setText("等待客户端连接…")
        self._tcp_client_lbl.setStyleSheet("color: #27ae60; font-size: 11px;")
        self._append_log(f"[TCP] 远程控制服务已启动，端口 {port}")

    def _on_tcp_stopped(self):
        self._tcp_status.setStyleSheet("color: #e67e22; font-size: 16px;")
        self._tcp_client_lbl.setText("服务已停止")
        self._tcp_client_lbl.setStyleSheet("color: #e67e22; font-size: 11px;")
        self._append_log("[TCP] 远程控制服务已停止")

    def _on_tcp_error(self, msg: str):
        self._append_log(f"[TCP 错误] {msg}", error=True)
        self._show_warning("TCP 服务器错误", msg)

    def _on_tcp_client_connected(self, addr: str):
        self._tcp_client_lbl.setText(f"客户端：{addr}")
        self._tcp_client_lbl.setStyleSheet("color: #3498db; font-size: 11px;")
        self._append_log(f"[TCP] 客户端已连接：{addr}")

    def _on_tcp_client_disconnected(self, addr: str):
        self._tcp_client_lbl.setText("等待客户端连接…")
        self._tcp_client_lbl.setStyleSheet("color: #27ae60; font-size: 11px;")
        self._append_log(f"[TCP] 客户端已断开：{addr}")

    def _on_tcp_log(self, msg: str):
        self._append_log(f"[TCP] {msg}")

    # ── TCP 命令分发（主线程执行）────────────────────────────────────────────

    def _on_tcp_execute(self, req: _CommandRequest):
        """主线程中处理来自 TCP 客户端的命令请求。"""
        opcode = req.opcode
        params = req.params
        self._append_log(f"[TCP 指令] opcode={opcode}  params={params}", proto=True)

        # ── 无需串口的即时命令 ──────────────────────────────────────────────

        if opcode == "check":
            req.set_response({
                "IsSuccessful": True,
                "Value": {"version": TCP_VERSION},
                "ErrorMessage": "Null",
            })
            return

        if opcode == "ConnectDevice":
            connected = self._serial.is_connected()
            req.set_response({
                "IsSuccessful": connected,
                "Value": "",
                "ErrorMessage": "Null" if connected else "串口未连接",
            })
            return

        # ── 需要串口的命令 ───────────────────────────────────────────────────

        if opcode == "Move":
            self._tcp_do_move(req, params)
            return

        if opcode == "RunPreset":
            self._tcp_do_run_preset(req, params)
            return

        req.set_response({
            "IsSuccessful": False,
            "Value": "",
            "ErrorMessage": f"未知 opcode: {opcode}",
        })

    def _tcp_do_move(self, req: _CommandRequest, params: dict):
        """解析 Move 参数并通过串口发送，结果由 _complete_tcp_request 回传。"""
        try:
            en = int(params.get("enable", 1))
            res = int(params["resolution"])
            direction = int(params["direction"])
            angle = int(params["angle"])
            freq = int(params["frequency"])
        except (KeyError, ValueError) as e:
            req.set_response({
                "IsSuccessful": False,
                "Value": "",
                "ErrorMessage": f"参数错误: {e}",
            })
            return

        if not subdivision.is_valid_resolution(res):
            req.set_response({
                "IsSuccessful": False,
                "Value": "",
                "ErrorMessage": f"无效分辨率: {res}",
            })
            return

        cmd = f"{en} {res} {direction} {angle} {freq}"
        self._pending_tcp_req = req
        ok = self._serial.send_command(cmd)
        if not ok:
            self._pending_tcp_req = None
            req.set_response({
                "IsSuccessful": False,
                "Value": "",
                "ErrorMessage": "串口未连接或发送失败",
            })
            return
        self._append_log(f"[TCP→发送] {cmd}", sent=True)
        # 响应将在 _on_cmd_ok / _on_cmd_error / _on_cmd_timeout 中通过
        # _complete_tcp_request 设置。

    def _tcp_do_run_preset(self, req: _CommandRequest, params: dict):
        """按名称查找预设并执行，逻辑同 Move。"""
        name = params.get("name", "")
        try:
            with open(_PRESETS_PATH, encoding="utf-8") as f:
                data = json.load(f)
            presets = data.get("presets", [])
        except Exception as e:
            req.set_response({
                "IsSuccessful": False,
                "Value": "",
                "ErrorMessage": f"读取预设文件失败: {e}",
            })
            return

        preset = next((p for p in presets if p.get("name") == name), None)
        if preset is None:
            req.set_response({
                "IsSuccessful": False,
                "Value": "",
                "ErrorMessage": f"未找到预设: {name}",
            })
            return

        # 复用 Move 逻辑
        self._tcp_do_move(req, {
            "enable":    preset.get("enable", 1),
            "resolution": preset["resolution"],
            "direction": preset["direction"],
            "angle":     preset["angle"],
            "frequency": preset["frequency"],
        })

    def _complete_tcp_request(self, success: bool, value, error_msg: str):
        """在 cmd_ok / cmd_error / cmd_timeout 中调用，完成 TCP 请求。"""
        req = self._pending_tcp_req
        self._pending_tcp_req = None
        if req is not None:
            req.set_response({
                "IsSuccessful": success,
                "Value": value,
                "ErrorMessage": error_msg,
            })

    # ── 日志 ─────────────────────────────────────────────────────────────────

    def _append_log(self, text: str, sent: bool = False, received: bool = False,
                    error: bool = False, ok: bool = False, proto: bool = False):
        ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        if sent:
            color = "#4ec9b0"   # 青色：发送
        elif received:
            color = "#ce9178"   # 橙色：原始接收
        elif error:
            color = "#f44747"   # 红色：错误/超时
        elif ok:
            color = "#b5cea8"   # 浅绿：成功
        elif proto:
            color = "#c586c0"   # 紫色：协议状态（回显/未知等）
        else:
            color = "#9cdcfe"   # 蓝色：系统信息
        html = (
            f'<span style="color:#6a9955;">[{ts}]</span> '
            f'<span style="color:{color};">{text}</span>'
        )
        self._log.append(html)
        self._log.moveCursor(QTextCursor.End)

    def _show_warning(self, title: str, detail: str):
        """显示非模态警告气泡（状态栏）+ 模态对话框（严重时）。"""
        dlg = QMessageBox(self)
        dlg.setIcon(QMessageBox.Warning)
        dlg.setWindowTitle(title)
        dlg.setText(detail)
        dlg.setStandardButtons(QMessageBox.Ok)
        dlg.exec_()

    # ── 样式辅助 ──────────────────────────────────────────────────────────────

    @staticmethod
    def _conn_btn_style(connected: bool) -> str:
        if connected:
            return """
                QPushButton { background:#e74c3c; color:white; border:none; border-radius:5px;
                              font-size:12px; font-weight:bold; padding: 3px 14px; }
                QPushButton:hover { background:#c0392b; }
            """
        return """
            QPushButton { background:#27ae60; color:white; border:none; border-radius:5px;
                          font-size:12px; font-weight:bold; padding: 3px 14px; }
            QPushButton:hover { background:#2ecc71; }
        """

    # ── 关闭事件 ──────────────────────────────────────────────────────────────

    def closeEvent(self, event):
        self._port_timer.stop()
        if self._tcp.is_running():
            self._tcp.stop()
        if self._serial.is_connected():
            self._serial.disconnect()
        event.accept()
