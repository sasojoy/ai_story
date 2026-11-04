"""城外分級（新手引導重做，Joy 2026-10-22 同意設計稿 https://claude.ai/artifact/Eb25MwPveJMYSf5Ge4mDyx；Config.training）：
一類一顆（precise.on）開著、Config.training.enabled 也開著才有：照這裡最弱的對手分一、二、三級，玩家看不到「幾級」，每一級寫成一句
江湖話（TIER_WORDS），寫在輿圖的地點詳情（PLACE_LINE）。城裡操練（act:drill）與尋敵鈕全部拆包第 13 批拿掉；這裡剩下的分級是共用規則層（registry.SHARED；全部拆包第 18 批）。
這裡放不看引擎的純規則，engine.Game 接線。"""
from __future__ import annotations

from . import precise
from .models import Content, Location, Training
from .state import WorldState

PRACTICE = "尋敵"  # 以前叫練功（Joy 2026-10-22 改名）；戰報的標籤（引導的提示讀）
# 一、二、三級的江湖話（Joy 2026-10-22：不寫「幾級練功點」，移動清單也不寫）：輿圖的地點詳情。待 joy 潤
TIER_WORDS = ("宵小出沒", "匪寇橫行", "兇徒盤據")
PLACE_LINE = "此地{tier}。"  # 輿圖地點詳情最後那一句（Game.place_detail）


def on(content: Content, world: WorldState | None) -> bool:
    return content.config.training.enabled and precise.on(content, world)


def tier_of(cfg: Training, difficulty: float) -> int:
    """最弱的對手難度 → 第幾級（0、1、2）。"""
    low, mid = cfg.tier_bounds
    return 0 if difficulty <= low else 1 if difficulty <= mid else 2


def is_town(content: Content, loc: Location) -> bool:
    return precise.is_town(content, loc)
