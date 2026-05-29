"""
拨码开关图形化组件
可视化显示 SW5-SW8 四个开关，点击切换 ON/OFF 状态，
自动通过 subdivision 模块查询对应分辨率并通过信号通知外部。
"""

from typing import Dict, Optional

from PyQt5.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QPushButton, QLabel, QFrame,
)
from PyQt5.QtCore import pyqtSignal, Qt
from PyQt5.QtGui import QFont

from core import subdivision


# ── 单个拨码开关按钮 ──────────────────────────────────────────────────────────

class _SwitchButton(QPushButton):
    """单个拨码开关，点击切换 ON/OFF，外观区分状态。"""

    toggled_state = pyqtSignal(str, str)  # (switch_name, state)

    _STYLE_ON = """
        QPushButton {
            background-color: #27ae60;
            color: white;
            border: 2px solid #1e8449;
            border-radius: 5px;
            font-weight: bold;
            font-size: 11px;
            padding: 4px 6px;
        }
        QPushButton:hover { background-color: #2ecc71; }
    """
    _STYLE_OFF = """
        QPushButton {
            background-color: #bdc3c7;
            color: #7f8c8d;
            border: 2px solid #95a5a6;
            border-radius: 5px;
            font-weight: bold;
            font-size: 11px;
            padding: 4px 6px;
        }
        QPushButton:hover { background-color: #95a5a6; }
    """

    def __init__(self, name: str, initial: str = "OFF", parent=None):
        super().__init__(parent)
        self._name = name
        self._state = initial.upper()
        self._refresh_ui()
        self.clicked.connect(self._toggle)

    def _toggle(self):
        self._state = "OFF" if self._state == "ON" else "ON"
        self._refresh_ui()
        self.toggled_state.emit(self._name, self._state)

    def _refresh_ui(self):
        self.setText(f"{self._name}\n{self._state}")
        self.setStyleSheet(self._STYLE_ON if self._state == "ON" else self._STYLE_OFF)
        self.setMinimumSize(56, 44)
        self.setSizePolicy(
            self.sizePolicy().horizontalPolicy(),
            self.sizePolicy().verticalPolicy(),
        )

    def state(self) -> str:
        return self._state

    def set_state(self, state: str, silent: bool = False):
        """外部设置状态，silent=True 时不触发 toggled_state 信号。"""
        new_state = state.upper()
        if new_state == self._state:
            return
        self._state = new_state
        self._refresh_ui()
        if not silent:
            self.toggled_state.emit(self._name, self._state)


# ── 拨码开关组合组件 ──────────────────────────────────────────────────────────

class SwitchWidget(QWidget):
    """
    SW5-SW8 四个拨码开关的组合组件。
    信号：
      resolution_changed(int)   — 开关状态对应的有效分辨率
      invalid_combination()     — 当前开关组合无对应分辨率时发射
    """

    resolution_changed = pyqtSignal(int)
    invalid_combination = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._switches: Dict[str, _SwitchButton] = {}
        self._setup_ui()

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(8)

        # 开关行 + 结果水平排列
        row = QHBoxLayout()
        row.setSpacing(8)
        for name in ("SW5", "SW6", "SW7", "SW8"):
            btn = _SwitchButton(name, "OFF")
            btn.toggled_state.connect(self._on_switch_toggled)
            self._switches[name] = btn
            row.addWidget(btn)

        row.addSpacing(12)

        result_label = QLabel("分辨率：")
        self._result_value = QLabel("—")
        self._result_value.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        result_font = QFont()
        result_font.setBold(True)
        self._result_value.setFont(result_font)
        row.addWidget(result_label)
        row.addWidget(self._result_value, stretch=1)
        root.addLayout(row)

        self._update_result()

    def _on_switch_toggled(self, name: str, state: str):
        self._update_result()

    def _update_result(self):
        sw5 = self._switches["SW5"].state()
        sw6 = self._switches["SW6"].state()
        sw7 = self._switches["SW7"].state()
        sw8 = self._switches["SW8"].state()
        res = subdivision.resolution_for_switches(sw5, sw6, sw7, sw8)
        if res is not None:
            label = subdivision.display_label(res)
            self._result_value.setText(label)
            self._result_value.setStyleSheet("color: #27ae60;")
            self.resolution_changed.emit(res)
        else:
            self._result_value.setText("无效组合")
            self._result_value.setStyleSheet("color: #e74c3c;")
            self.invalid_combination.emit()

    # ── 外部接口 ──────────────────────────────────────────────────────────────

    def current_resolution(self) -> Optional[int]:
        """返回当前开关组合对应的分辨率，无效时返回 None。"""
        sw5 = self._switches["SW5"].state()
        sw6 = self._switches["SW6"].state()
        sw7 = self._switches["SW7"].state()
        sw8 = self._switches["SW8"].state()
        return subdivision.resolution_for_switches(sw5, sw6, sw7, sw8)

    def set_resolution(self, resolution: int):
        """根据分辨率自动设置四个开关状态（静默，不触发重复信号）。"""
        state = subdivision.switches_for_resolution(resolution)
        if state is None:
            return
        sw5, sw6, sw7, sw8 = state
        self._switches["SW5"].set_state(sw5, silent=True)
        self._switches["SW6"].set_state(sw6, silent=True)
        self._switches["SW7"].set_state(sw7, silent=True)
        self._switches["SW8"].set_state(sw8, silent=True)
        self._update_result()
