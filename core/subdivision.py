"""
细分精度数据模块
从 细分精度.csv 加载拨码开关（SW5-SW8）与分辨率（脉冲/圈）的双向映射关系。
"""

import csv
import os
import sys
from typing import Dict, Optional, Tuple

# 开关状态元组类型: (SW5, SW6, SW7, SW8)，值为 'ON' 或 'OFF'
SwitchState = Tuple[str, str, str, str]

if getattr(sys, 'frozen', False):
    _CSV_PATH = os.path.join(sys._MEIPASS, "细分精度.csv")
else:
    _CSV_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "细分精度.csv")

# resolution -> (SW5, SW6, SW7, SW8)
_res_to_switch: Dict[int, SwitchState] = {}
# (SW5, SW6, SW7, SW8) -> resolution
_switch_to_res: Dict[SwitchState, int] = {}
# 所有合法分辨率列表（保持 CSV 顺序）
_all_resolutions: list = []
# 细分度 -> 分辨率
_subdivision_to_res: Dict[int, int] = {}
# 分辨率 -> 细分度
_res_to_subdivision: Dict[int, int] = {}


def _load():
    global _res_to_switch, _switch_to_res, _all_resolutions
    global _subdivision_to_res, _res_to_subdivision
    _res_to_switch.clear()
    _switch_to_res.clear()
    _all_resolutions.clear()
    _subdivision_to_res.clear()
    _res_to_subdivision.clear()

    with open(_CSV_PATH, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            subdivision = int(row["细分精度"])
            resolution = int(row["脉冲数/圈"])
            sw5 = row["SW5"].strip().upper()
            sw6 = row["SW6"].strip().upper()
            sw7 = row["SW7"].strip().upper()
            sw8 = row["SW8"].strip().upper()
            state: SwitchState = (sw5, sw6, sw7, sw8)
            _res_to_switch[resolution] = state
            _switch_to_res[state] = resolution
            _all_resolutions.append(resolution)
            _subdivision_to_res[subdivision] = resolution
            _res_to_subdivision[resolution] = subdivision


_load()


def all_resolutions() -> list:
    """返回所有合法分辨率列表（脉冲/圈），保持 CSV 顺序。"""
    return list(_all_resolutions)


def switches_for_resolution(resolution: int) -> Optional[SwitchState]:
    """根据分辨率返回对应的开关状态 (SW5, SW6, SW7, SW8)，未找到返回 None。"""
    return _res_to_switch.get(resolution)


def resolution_for_switches(sw5: str, sw6: str, sw7: str, sw8: str) -> Optional[int]:
    """根据开关状态返回对应分辨率，无匹配返回 None。"""
    state: SwitchState = (sw5.upper(), sw6.upper(), sw7.upper(), sw8.upper())
    return _switch_to_res.get(state)


def subdivision_for_resolution(resolution: int) -> Optional[int]:
    """返回分辨率对应的细分度，未找到返回 None。"""
    return _res_to_subdivision.get(resolution)


def is_valid_resolution(resolution: int) -> bool:
    """检查分辨率是否在合法列表中。"""
    return resolution in _res_to_switch


def display_label(resolution: int) -> str:
    """返回用于下拉框显示的字符串，格式：'1600 脉冲/圈（细分×8）'"""
    sub = _res_to_subdivision.get(resolution)
    if sub is not None:
        return f"{resolution} 脉冲/圈（细分 ×{sub}）"
    return f"{resolution} 脉冲/圈"
