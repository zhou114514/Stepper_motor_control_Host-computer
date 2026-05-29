"""
主窗口
包含：顶部串口连接栏、中部 Tab（手动控制 / 快速控制）、底部日志面板。
"""

from datetime import datetime

from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QComboBox, QTabWidget,
    QTextEdit, QSplitter, QStatusBar, QMessageBox,
)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QFont, QTextCursor

from core.serial_manager import SerialManager
from core.protocol import CommandResult
from ui.manual_panel import ManualPanel
from ui.quick_panel import QuickPanel


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("步进电机控制上位机")
        self.setMinimumSize(560, 460)
        self.resize(780, 620)

        self._serial = SerialManager(self)
        self._setup_ui()
        self._connect_signals()
        self._refresh_ports()

        # 定时刷新 COM 口列表（每 3 秒）
        self._port_timer = QTimer(self)
        self._port_timer.timeout.connect(self._refresh_ports)
        self._port_timer.start(3000)

    # ── UI 搭建 ──────────────────────────────────────────────────────────────

    def _setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # 串口连接栏
        root.addWidget(self._build_serial_bar())

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

    def _on_cmd_error(self, result: CommandResult):
        msg = result.error_msg or "（设备未提供错误详情）"
        self._append_log(f"[设备错误] {msg}", error=True)
        self._status_bar.showMessage(f"设备错误：{msg}")
        self._show_warning(
            "设备返回错误",
            f"设备报告了一个错误：\n\n{msg}\n\n"
            f"发送的命令：{result.cmd}"
        )

    def _on_cmd_timeout(self, result: CommandResult):
        reason = result.timeout_reason
        if not result.echo:
            # 完全无回显 → 连接或设备问题
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
            # 有回显但无 OK → 设备异常或运行时间过长
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
        self._show_warning(title, detail)

    def _on_cmd_unknown(self, line: str):
        self._append_log(f"[未知] {line}", proto=True)

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
        if self._serial.is_connected():
            self._serial.disconnect()
        event.accept()
