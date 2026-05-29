"""
快速控制面板
从 config/presets.json 加载预设，每个预设生成一张卡片，
支持一键发送、刷新预设列表、用系统编辑器打开配置文件。
"""

import json
import os
import subprocess
import sys

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QScrollArea, QFrame, QMessageBox, QSizePolicy,
    QGroupBox,
)
from PyQt5.QtCore import pyqtSignal, Qt
from PyQt5.QtGui import QFont

from core import subdivision

if getattr(sys, 'frozen', False):
    _PRESETS_PATH = os.path.join(sys._MEIPASS, "config", "presets.json")
else:
    _PRESETS_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config", "presets.json")


# ── 单张预设卡片 ──────────────────────────────────────────────────────────────

class _PresetCard(QFrame):
    """单张预设卡片，包含名称、参数摘要和执行按钮。"""

    execute_clicked = pyqtSignal(dict)  # 发射完整 preset 字典

    def __init__(self, preset: dict, parent=None):
        super().__init__(parent)
        self._preset = preset
        self.setFrameShape(QFrame.StyledPanel)
        self.setFrameShadow(QFrame.Raised)
        self.setStyleSheet("""
            QFrame {
                background-color: #ffffff;
                border: 1px solid #d0d7de;
                border-radius: 10px;
            }
        """)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._setup_ui()

    def _setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(10)

        # 信息区
        info_col = QVBoxLayout()
        info_col.setSpacing(3)

        name_label = QLabel(self._preset.get("name", "未命名预设"))
        name_font = QFont()
        name_font.setBold(True)
        name_font.setPointSize(11)
        name_label.setFont(name_font)
        info_col.addWidget(name_label)

        desc = self._preset.get("description", "")
        if desc:
            desc_label = QLabel(desc)
            desc_label.setStyleSheet("color: #586069; font-size: 11px;")
            info_col.addWidget(desc_label)

        # 参数摘要
        params = self._build_params_text()
        params_label = QLabel(params)
        params_label.setFont(QFont("Consolas", 9))
        params_label.setStyleSheet("color: #24292f; background: #f6f8fa; border-radius: 4px; padding: 2px 5px;")
        params_label.setWordWrap(True)
        info_col.addWidget(params_label)

        layout.addLayout(info_col, stretch=1)

        # 执行按钮
        execute_btn = QPushButton("▶ 执行")
        execute_btn.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Preferred)
        execute_btn.setStyleSheet("""
            QPushButton {
                background-color: #2980b9; color: white;
                border: none; border-radius: 6px;
                font-size: 12px; font-weight: bold;
                padding: 4px 14px;
            }
            QPushButton:hover { background-color: #3498db; }
            QPushButton:pressed { background-color: #1a6fa8; }
        """)
        execute_btn.clicked.connect(lambda: self.execute_clicked.emit(self._preset))
        layout.addWidget(execute_btn, alignment=Qt.AlignVCenter)

    def _build_params_text(self) -> str:
        p = self._preset
        en = p.get("enable", 1)
        res = p.get("resolution", "?")
        direction = "顺时针↻" if p.get("direction", 1) == 1 else "逆时针↺"
        angle = p.get("angle", "?")
        freq = p.get("frequency", "?")
        sub = subdivision.subdivision_for_resolution(res) if isinstance(res, int) else None
        sub_str = f" ×{sub}" if sub is not None else ""
        return (
            f"使能={en}  分辨率={res}{sub_str}脉冲/圈  "
            f"{direction}  角度={angle}°  频率={freq}Hz"
        )


# ── 快速控制面板 ──────────────────────────────────────────────────────────────

class QuickPanel(QWidget):
    """
    快速控制面板。
    信号：
      command_ready(str)  — 用户点击执行时携带完整命令字符串（不含换行）
    """

    command_ready = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()
        self._load_presets()

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        # 工具栏
        toolbar = QHBoxLayout()
        title = QLabel("快速预设控制")
        title_font = QFont()
        title_font.setBold(True)
        title_font.setPointSize(13)
        title.setFont(title_font)
        toolbar.addWidget(title)
        toolbar.addStretch()

        refresh_btn = QPushButton("🔄 刷新预设")
        refresh_btn.setStyleSheet(self._btn_style("#27ae60", "#1e8449"))
        refresh_btn.clicked.connect(self._load_presets)
        toolbar.addWidget(refresh_btn)

        edit_btn = QPushButton("✏ 编辑配置")
        edit_btn.setStyleSheet(self._btn_style("#7f8c8d", "#5d6d7e"))
        edit_btn.clicked.connect(self._open_config)
        toolbar.addWidget(edit_btn)

        root.addLayout(toolbar)

        hint = QLabel(f"配置文件：{_PRESETS_PATH}")
        hint.setStyleSheet("color: gray; font-size: 10px;")
        root.addWidget(hint)

        # 滚动区域放卡片
        self._scroll_area = QScrollArea()
        self._scroll_area.setWidgetResizable(True)
        self._scroll_area.setFrameShape(QFrame.NoFrame)

        self._card_container = QWidget()
        self._card_layout = QVBoxLayout(self._card_container)
        self._card_layout.setSpacing(10)
        self._card_layout.setContentsMargins(0, 0, 0, 0)
        self._card_layout.addStretch()

        self._scroll_area.setWidget(self._card_container)
        root.addWidget(self._scroll_area, stretch=1)

    @staticmethod
    def _btn_style(bg: str, hover: str) -> str:
        return f"""
            QPushButton {{
                background-color: {bg}; color: white;
                border: none; border-radius: 6px;
                padding: 6px 14px; font-size: 12px;
            }}
            QPushButton:hover {{ background-color: {hover}; }}
        """

    def _load_presets(self):
        # 清空旧卡片（保留末尾 stretch）
        while self._card_layout.count() > 1:
            item = self._card_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        try:
            with open(_PRESETS_PATH, encoding="utf-8") as f:
                data = json.load(f)
            presets = data.get("presets", [])
        except FileNotFoundError:
            self._show_empty("未找到配置文件，请检查 config/presets.json")
            return
        except json.JSONDecodeError as e:
            self._show_empty(f"配置文件解析失败：{e}")
            return

        if not presets:
            self._show_empty("配置文件中没有预设项（presets 列表为空）")
            return

        for preset in presets:
            card = _PresetCard(preset)
            card.execute_clicked.connect(self._on_execute)
            self._card_layout.insertWidget(self._card_layout.count() - 1, card)

    def _show_empty(self, msg: str):
        label = QLabel(msg)
        label.setAlignment(Qt.AlignCenter)
        label.setStyleSheet("color: #e74c3c; font-size: 12px;")
        self._card_layout.insertWidget(0, label)

    def _on_execute(self, preset: dict):
        try:
            en = int(preset["enable"])
            res = int(preset["resolution"])
            direction = int(preset["direction"])
            angle = int(preset["angle"])
            freq = int(preset["frequency"])
        except (KeyError, ValueError) as e:
            QMessageBox.warning(self, "预设参数错误", f"预设字段缺失或类型错误：{e}")
            return

        if not subdivision.is_valid_resolution(res):
            QMessageBox.warning(
                self, "无效分辨率",
                f"预设中的分辨率 {res} 不在合法列表中，请检查配置文件。"
            )
            return

        cmd = f"{en} {res} {direction} {angle} {freq}"
        self.command_ready.emit(cmd)

    def _open_config(self):
        try:
            if sys.platform.startswith("win"):
                os.startfile(_PRESETS_PATH)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", _PRESETS_PATH])
            else:
                subprocess.Popen(["xdg-open", _PRESETS_PATH])
        except Exception as e:
            QMessageBox.warning(self, "无法打开文件", f"无法用系统编辑器打开配置文件：{e}")
