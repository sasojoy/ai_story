"""結伴同行的底座（全部拆包第 50 批「輿圖二」；主人：移動包 features/travel 的 party；手冊 3.3、3.10 的查詢服務）。

安排前往（共用規則層 atlas.travel_block）要擋「跟著別人走在路上，要改道先分道揚鑣」，得知道玩家是不是跟著誰同行。
結伴（PlayerState.tagalong）是移動包認領的欄位（第 48 批），共用規則層不准碰它，所以只讀的這一小半留在核心，atlas 問這裡；
移動包照舊自己寫、自己清（party），並且 re-export 同一個函式。同 omen_base、convoy_base 不進 MODULES（tianxia/core/ 底下的檔本來就是核心）。
另外跑：改這一個 scripts/test_for.py 照核心挑（核心測試＋煙霧），挑不到本體還在 party 時挑的移動包 tianxia/features/travel/tests
（3 個檔），另外跑那一包的 tests（第 50 批審查）。
"""
from __future__ import annotations

from dataclasses import dataclass

from ..state import GameState


@dataclass(frozen=True)
class TravelBlock:
    """現在不能安排前往的原因（話只寫一次，在 atlas.travel_block 那張順序表 MENU_ORDER["block"] 的那一格）。to_jianghu：要回江湖頁了結才解得開（待處理的事件、交談中、
    求見中、投靠或叛投待確認、答話中；FB-063），頁面照這個旗標多給「回江湖」，不去解析中文。閉關、賽季結束不是。
    core_seams（全部拆包第 56 批）：動身被擋的格分到各包，都要回它，所以從 atlas 搬來；atlas re-export 同一個類別（tests/map/test_atlas.py 從 atlas 拿）。"""

    reason: str
    to_jianghu: bool = False


def following(state: GameState) -> str | None:
    """跟著誰走在路上：答應了結伴（tagalong）而且已經在路上（journey）時回帶頭的人的名號，不然 None（跟著但還沒動身不算）。"""
    p = state.player
    if p.tagalong is not None and p.journey is not None:
        return p.tagalong.leader
    return None
