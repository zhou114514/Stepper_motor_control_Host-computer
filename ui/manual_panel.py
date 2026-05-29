"""
手动控制面板
提供：使能切换、方向选择、分辨率选择（下拉框 / 拨码开关两种模式）、
角度输入、频率输入，以及发送命令按钮。
"""

from typing import Optional

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QPushButton, QLabel, QComboBox, QSpinBox,
    QButtonGroup, QRadioButton, QStackedWidget,
    QGroupBox, QFrame, QSizePolicy,
)
from PyQt5.QtCore import pyqtSignal, Qt
from PyQt5.QtGui import QFont

from core import subdivision
from ui.switch_widget import SwitchWidget


# ── 使能切换按钮 ──────────────────────────────────────────────────────────────

class _EnableButton(QPushButton):
    _STYLE_ON = """
        QPushButton {
            background-color: #27ae60; color: white;
            border: 2px solid #1e8449; border-radius: 6px;
            font-size: 12px; font-weight: bold; padding: 4px 14px;
        }
        QPushButton:hover { background-color: #2ecc71; }
    """
    _STYLE_OFF = """
        QPushButton {
            background-color: #e74c3c; color: white;
            border: 2px solid #c0392b; border-radius: 6px;
            font-size: 12px; font-weight: bold; padding: 4px 14px;
        }
        QPushButton:hover { background-color: #c0392b; }
    """

    enable_changed = pyqtSignal(int)  # 0 or 1

    def __init__(self, parent=None):
        super().__init__(parent)
        self._enabled = False
        self._refresh()
        self.clicked.connect(self._toggle)

    def _toggle(self):
        self._enabled = not self._enabled
        self._refresh()
        self.enable_changed.emit(1 if self._enabled else 0)

    def _refresh(self):
        if self._enabled:
            self.setText("已使能 ●")
            self.setStyleSheet(self._STYLE_ON)
        else:
            self.setText("未使能 ○")
            self.setStyleSheet(self._STYLE_OFF)

    def value(self) -> int:
        return 1 if self._enabled else 0

    def set_value(self, v: int):
        self._enabled = bool(v)
        self._refresh()


# ── 手动控制面板 ──────────────────────────────────────────────────────────────

class ManualPanel(QWidget):
    """
    手动控制面板。
    信号：
      command_ready(str)  — 用户点击发送时携带完整命令字符串（不含换行）
    """

    command_ready = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()
        self._sync_dropdown_to_switch()

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)

        # ── 1. 使能 & 方向 ────────────────────────────────────────────────────
        top_group = QGroupBox("基本控制")
        top_layout = QHBoxLayout(top_group)
        top_layout.setContentsMargins(8, 6, 8, 6)
        top_layout.setSpacing(12)

        self._enable_btn = _EnableButton()
        self._enable_btn.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        top_layout.addWidget(self._enable_btn)

        top_layout.addSpacing(12)

        dir_label = QLabel("方向：")
        self._dir_cw = QRadioButton("顺时针 ↻")
        self._dir_ccw = QRadioButton("逆时针 ↺")
        self._dir_cw.setChecked(True)
        dir_group = QButtonGroup(self)
        dir_group.addButton(self._dir_cw, 1)
        dir_group.addButton(self._dir_ccw, 0)
        top_layout.addWidget(dir_label)
        top_layout.addWidget(self._dir_cw)
        top_layout.addWidget(self._dir_ccw)
        top_layout.addStretch()
        root.addWidget(top_group)

        self._dir_group = dir_group

        # ── 2. 分辨率区 ───────────────────────────────────────────────────────
        res_group = QGroupBox("细分分辨率")
        res_layout = QVBoxLayout(res_group)
        res_layout.setContentsMargins(8, 6, 8, 6)
        res_layout.setSpacing(6)

        # 模式切换单选
        mode_row = QHBoxLayout()
        self._mode_dropdown_rb = QRadioButton("下拉框选择")
        self._mode_switch_rb = QRadioButton("拨码开关配置")
        self._mode_dropdown_rb.setChecked(True)
        mode_btn_group = QButtonGroup(self)
        mode_btn_group.addButton(self._mode_dropdown_rb, 0)
        mode_btn_group.addButton(self._mode_switch_rb, 1)
        mode_row.addWidget(QLabel("选择方式："))
        mode_row.addWidget(self._mode_dropdown_rb)
        mode_row.addWidget(self._mode_switch_rb)
        mode_row.addStretch()
        res_layout.addLayout(mode_row)

        # 模式内容堆叠
        self._stacked = QStackedWidget()

        # 页 0：下拉框
        dropdown_page = QWidget()
        dp_layout = QHBoxLayout(dropdown_page)
        dp_layout.setContentsMargins(0, 0, 0, 0)
        dp_layout.addWidget(QLabel("分辨率："))
        self._res_combo = QComboBox()
        self._res_combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        for res in subdivision.all_resolutions():
            self._res_combo.addItem(subdivision.display_label(res), res)
        dp_layout.addWidget(self._res_combo)
        self._stacked.addWidget(dropdown_page)

        # 页 1：拨码开关
        self._switch_widget = SwitchWidget()
        self._stacked.addWidget(self._switch_widget)

        res_layout.addWidget(self._stacked)
        root.addWidget(res_group)

        # 绑定模式切换
        self._mode_dropdown_rb.toggled.connect(self._on_mode_changed)
        # 下拉框变化时同步开关
        self._res_combo.currentIndexChanged.connect(self._sync_dropdown_to_switch)
        # 开关变化时同步下拉框
        self._switch_widget.resolution_changed.connect(self._sync_switch_to_dropdown)

        # ── 3. 角度 & 频率 ────────────────────────────────────────────────────
        param_group = QGroupBox("运动参数")
        param_layout = QGridLayout(param_group)
        param_layout.setContentsMargins(8, 6, 8, 6)
        param_layout.setSpacing(6)

        param_layout.addWidget(QLabel("角度（°）："), 0, 0)
        self._angle_spin = QSpinBox()
        self._angle_spin.setRange(1, 36000)
        self._angle_spin.setValue(90)
        self._angle_spin.setSuffix(" °")
        self._angle_spin.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        param_layout.addWidget(self._angle_spin, 0, 1)

        angle_hint = QLabel("1 ~ 36000°")
        angle_hint.setStyleSheet("color: gray; font-size: 10px;")
        param_layout.addWidget(angle_hint, 0, 2)

        param_layout.addWidget(QLabel("频率（Hz）："), 1, 0)
        self._freq_spin = QSpinBox()
        self._freq_spin.setRange(1, 416666)
        self._freq_spin.setValue(1000)
        self._freq_spin.setSuffix(" Hz")
        self._freq_spin.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        param_layout.addWidget(self._freq_spin, 1, 1)

        freq_hint = QLabel("最高 416666 Hz")
        freq_hint.setStyleSheet("color: gray; font-size: 10px;")
        param_layout.addWidget(freq_hint, 1, 2)

        param_layout.setColumnStretch(1, 1)
        root.addWidget(param_group)

        # ── 4. 命令预览 & 发送（同一行）─────────────────────────────────────
        send_group = QGroupBox("发送")
        send_layout = QHBoxLayout(send_group)
        send_layout.setContentsMargins(8, 6, 8, 6)
        send_layout.setSpacing(8)

        send_layout.addWidget(QLabel("预览："))
        self._preview_label = QLabel("")
        self._preview_label.setFont(QFont("Consolas", 10))
        self._preview_label.setStyleSheet(
            "background: #f0f0f0; border: 1px solid #ccc; border-radius: 4px; padding: 2px 6px;"
        )
        self._preview_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        send_layout.addWidget(self._preview_label, stretch=1)

        self._send_btn = QPushButton("发送 ▶")
        self._send_btn.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self._send_btn.setStyleSheet("""
            QPushButton {
                background-color: #2980b9; color: white;
                border: none; border-radius: 6px;
                font-size: 12px; font-weight: bold;
                padding: 4px 16px;
            }
            QPushButton:hover { background-color: #3498db; }
            QPushButton:pressed { background-color: #1a6fa8; }
        """)
        self._send_btn.clicked.connect(self._on_send)
        send_layout.addWidget(self._send_btn)
        root.addWidget(send_group)

        root.addStretch()

        # 初始更新预览
        self._update_preview()

        # 连接所有参数变化到预览更新
        self._enable_btn.enable_changed.connect(lambda _: self._update_preview())
        self._dir_group.buttonClicked.connect(lambda _: self._update_preview())
        self._res_combo.currentIndexChanged.connect(lambda _: self._update_preview())
        self._switch_widget.resolution_changed.connect(lambda _: self._update_preview())
        self._switch_widget.invalid_combination.connect(lambda: self._update_preview())
        self._angle_spin.valueChanged.connect(lambda _: self._update_preview())
        self._freq_spin.valueChanged.connect(lambda _: self._update_preview())

    # ── 模式切换 ──────────────────────────────────────────────────────────────

    def _on_mode_changed(self, checked: bool):
        if self._mode_dropdown_rb.isChecked():
            self._stacked.setCurrentIndex(0)
            # 将开关当前分辨率同步到下拉框
            res = self._switch_widget.current_resolution()
            if res is not None:
                idx = self._res_combo.findData(res)
                if idx >= 0:
                    self._res_combo.setCurrentIndex(idx)
        else:
            self._stacked.setCurrentIndex(1)
            # 将下拉框当前分辨率同步到开关
            self._sync_dropdown_to_switch()

    def _sync_dropdown_to_switch(self):
        res = self._res_combo.currentData()
        if res is not None:
            self._switch_widget.set_resolution(res)

    def _sync_switch_to_dropdown(self, resolution: int):
        if self._mode_switch_rb.isChecked():
            idx = self._res_combo.findData(resolution)
            if idx >= 0:
                self._res_combo.blockSignals(True)
                self._res_combo.setCurrentIndex(idx)
                self._res_combo.blockSignals(False)

    # ── 命令构造 ──────────────────────────────────────────────────────────────

    def _current_resolution(self) -> Optional[int]:
        if self._mode_dropdown_rb.isChecked():
            return self._res_combo.currentData()
        else:
            return self._switch_widget.current_resolution()

    def _build_command(self) -> Optional[str]:
        en = self._enable_btn.value()
        res = self._current_resolution()
        if res is None:
            return None
        direction = self._dir_group.checkedId()
        angle = self._angle_spin.value()
        freq = self._freq_spin.value()
        return f"{en} {res} {direction} {angle} {freq}"

    def _update_preview(self):
        cmd = self._build_command()
        if cmd:
            self._preview_label.setText(cmd)
            self._preview_label.setStyleSheet(
                "background: #f0f0f0; border: 1px solid #ccc; border-radius: 4px; padding: 4px 8px; color: #222;"
            )
        else:
            self._preview_label.setText("—（当前开关组合无效）")
            self._preview_label.setStyleSheet(
                "background: #fdecea; border: 1px solid #e74c3c; border-radius: 4px; padding: 4px 8px; color: #e74c3c;"
            )

    def _on_send(self):
        cmd = self._build_command()
        if cmd:
            self.command_ready.emit(cmd)

    # ── 外部接口（供快速控制面板预填参数）──────────────────────────────────────

    def apply_preset(self, enable: int, resolution: int, direction: int,
                     angle: int, frequency: int):
        """将预设参数填入控件（不自动发送）。"""
        self._enable_btn.set_value(enable)
        idx = self._res_combo.findData(resolution)
        if idx >= 0:
            self._res_combo.setCurrentIndex(idx)
            self._switch_widget.set_resolution(resolution)
        self._dir_group.button(direction).setChecked(True)
        self._angle_spin.setValue(angle)
        self._freq_spin.setValue(frequency)
        self._update_preview()
