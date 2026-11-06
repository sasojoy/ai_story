"""移動包：玩法說明移動那一條（全部拆包第 59 批；原 tianxia/howto.py，字一個不動；順序在核心 HOWTO_ORDER）。"""
from __future__ import annotations

def travel_section() -> list[str]:
    """玩法說明移動那一條（HOWTO_ORDER 的 travel）。"""
    return [
        "- **移動**：步行不花體力、只花時間；疾行立刻到、要花體力。步行時，每一段路可以邊走邊想、"
        + "沿途打聽、路邊採集各一次。",  # 全圖開放拿掉了留意地形
    ]
