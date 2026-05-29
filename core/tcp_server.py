"""
TCP 远程控制服务器

外部程序可通过 TCP 连接，使用 JSON 协议远程控制步进电机。
协议文档见《远程控制协议》文件。

架构说明：
  - TcpServer(QObject)    — 主线程管理对象，对外暴露 Qt 信号/槽接口
  - _ServerThread         — 后台线程，负责监听 TCP 连接并分派
  - _ClientHandler        — 每个客户端独立线程，解析 JSON 并调用执行回调
  - _CommandRequest       — 线程间同步容器（threading.Event）

线程安全：
  _cmd_lock 保证同一时刻最多只有一条命令在等待串口响应，
  防止多客户端并发写入串口造成混乱。
"""

import json
import socket
import threading
from typing import Optional, Callable

from PyQt5.QtCore import QObject, pyqtSignal


VERSION = "1.0.0"
DEFAULT_PORT = 9527


# ── 线程间同步容器 ────────────────────────────────────────────────────────────

class _CommandRequest:
    """封装一次远程命令请求及其响应，用于 TCP 线程与主线程间同步。"""

    def __init__(self, opcode: str, params: dict):
        self.opcode: str = opcode
        self.params: dict = params
        self.response: Optional[dict] = None
        self._event = threading.Event()

    def set_response(self, response: dict):
        """主线程调用：设置响应并唤醒等待的 TCP 线程。"""
        self.response = response
        self._event.set()

    def wait(self, timeout: float = 35.0) -> bool:
        """TCP 线程调用：阻塞等待响应，超时返回 False。"""
        return self._event.wait(timeout)


# ── 客户端处理线程 ────────────────────────────────────────────────────────────

class _ClientHandler(threading.Thread):
    """每个 TCP 客户端独立的处理线程，按行解析 JSON 请求。"""

    def __init__(self, conn: socket.socket, addr,
                 execute_fn: Callable, log_fn: Callable,
                 on_disconnect: Callable):
        super().__init__(daemon=True)
        self._conn = conn
        self._addr = addr
        self._execute = execute_fn    # fn(opcode: str, params: dict) -> dict
        self._log = log_fn            # fn(msg: str)
        self._on_disconnect = on_disconnect

    def run(self):
        buf = ""
        try:
            while True:
                chunk = self._conn.recv(4096)
                if not chunk:
                    break
                buf += chunk.decode("utf-8", errors="replace")
                while "\n" in buf:
                    line, buf = buf.split("\n", 1)
                    line = line.strip()
                    if line:
                        resp = self._dispatch(line)
                        out = json.dumps(resp, ensure_ascii=False) + "\n"
                        self._conn.sendall(out.encode("utf-8"))
        except (ConnectionResetError, BrokenPipeError, OSError):
            pass
        finally:
            try:
                self._conn.close()
            except Exception:
                pass
            self._on_disconnect()

    def _dispatch(self, raw: str) -> dict:
        try:
            msg = json.loads(raw)
        except json.JSONDecodeError:
            return {"IsSuccessful": False, "Value": "", "ErrorMessage": "无效的 JSON 格式"}

        opcode = msg.get("opcode", "")
        params = msg.get("parameter", {})
        if not isinstance(params, dict):
            params = {}

        if not opcode:
            return {"IsSuccessful": False, "Value": "", "ErrorMessage": "缺少 opcode 字段"}

        return self._execute(opcode, params)


# ── TCP 监听线程 ──────────────────────────────────────────────────────────────

class _ServerThread(threading.Thread):
    """后台 TCP 服务器线程：绑定端口、接受连接、分派到 _ClientHandler。"""

    def __init__(self, port: int, execute_fn: Callable, log_fn: Callable,
                 on_client_connected: Callable, on_client_disconnected: Callable):
        super().__init__(daemon=True)
        self._port = port
        self._execute = execute_fn
        self._log = log_fn
        self._on_connected = on_client_connected
        self._on_disconnected = on_client_disconnected
        self._sock: Optional[socket.socket] = None
        self._running = False
        self.start_error: Optional[str] = None   # 启动失败时记录原因
        self._started_event = threading.Event()  # 等待服务器真正启动

    def run(self):
        try:
            self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self._sock.bind(("0.0.0.0", self._port))
            self._sock.listen(5)
            self._sock.settimeout(1.0)
            self._running = True
        except OSError as e:
            self.start_error = str(e)
            self._started_event.set()
            return

        self._started_event.set()
        self._log(f"TCP 远程控制服务已启动，监听端口 {self._port}")

        while self._running:
            try:
                conn, addr = self._sock.accept()
            except socket.timeout:
                continue
            except OSError:
                break

            addr_str = f"{addr[0]}:{addr[1]}"
            self._on_connected(addr_str)
            handler = _ClientHandler(
                conn, addr,
                self._execute,
                self._log,
                on_disconnect=lambda a=addr_str: self._on_disconnected(a),
            )
            handler.start()

    def stop(self):
        self._running = False
        if self._sock:
            try:
                self._sock.close()
            except Exception:
                pass
            self._sock = None

    def wait_started(self, timeout: float = 3.0) -> bool:
        """等待服务器线程完成绑定（成功或失败），返回是否成功启动。"""
        self._started_event.wait(timeout)
        return self._running


# ── 主对象（运行于主线程）────────────────────────────────────────────────────

class TcpServer(QObject):
    """
    TCP 远程控制服务器（Qt 对象，在主线程中管理）。

    使用方式：
      1. 创建实例并连接信号
      2. 将 execute_requested 信号连接到主窗口的命令分发槽
      3. 调用 start(port) 启动服务
      4. 主窗口收到命令后执行，完成时调用 request.set_response()

    信号：
      execute_requested(request) — 收到远程命令，投递到主线程执行（_CommandRequest）
      client_connected(addr)     — 客户端已连接，addr = "ip:port"
      client_disconnected(addr)  — 客户端已断开
      server_started(port)       — 服务器成功启动
      server_stopped()           — 服务器已停止
      server_error(msg)          — 启动失败（端口占用等）
      log_message(text)          — 日志消息
    """

    execute_requested   = pyqtSignal(object)  # _CommandRequest
    client_connected    = pyqtSignal(str)
    client_disconnected = pyqtSignal(str)
    server_started      = pyqtSignal(int)
    server_stopped      = pyqtSignal()
    server_error        = pyqtSignal(str)
    log_message         = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._thread: Optional[_ServerThread] = None
        self._cmd_lock = threading.Lock()
        self._port = DEFAULT_PORT

    @property
    def port(self) -> int:
        return self._port

    # ── 服务控制 ──────────────────────────────────────────────────────────────

    def start(self, port: int = DEFAULT_PORT):
        """启动 TCP 服务器，若已运行则先停止。"""
        if self.is_running():
            self.stop()

        self._port = port
        thread = _ServerThread(
            port=port,
            execute_fn=self._execute_command,
            log_fn=lambda msg: self.log_message.emit(msg),
            on_client_connected=lambda addr: self.client_connected.emit(addr),
            on_client_disconnected=lambda addr: self.client_disconnected.emit(addr),
        )
        thread.start()

        # 等待绑定完成（最多 3 秒）
        if thread.wait_started():
            self._thread = thread
            self.server_started.emit(port)
        else:
            err = thread.start_error or "未知错误"
            self.server_error.emit(f"TCP 服务器启动失败：{err}")

    def stop(self):
        """停止 TCP 服务器。"""
        if self._thread:
            self._thread.stop()
            self._thread = None
        self.server_stopped.emit()

    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    # ── 命令执行（在 TCP 工作线程中调用）────────────────────────────────────

    def _execute_command(self, opcode: str, params: dict) -> dict:
        """
        TCP 线程调用，序列化命令并等待主线程执行结果。
        _cmd_lock 保证同一时刻只有一条命令在等待串口响应。
        """
        with self._cmd_lock:
            req = _CommandRequest(opcode, params)
            # 跨线程信号：Qt 自动将其投递到主线程事件循环
            self.execute_requested.emit(req)
            if req.wait(timeout=35.0):
                return req.response
            return {
                "IsSuccessful": False,
                "Value": "",
                "ErrorMessage": "命令执行超时，设备可能无响应",
            }
