"""結伴同行的底座（全部拆包第 50 批「輿圖二」；主人：移動包 features/travel 的 party；手冊 3.3、3.10 的查詢服務）。

安排前往（共用規則層 atlas.travel_block）要擋「跟著別人走在路上，要改道先分道揚鑣」，得知道玩家是不是跟著誰同行。
結伴（PlayerState.tagalong）是移動包認領的欄位（第 48 批），共用規則層不准碰它，所以只讀的這一小半留在核心，atlas 問這裡；
移動包照舊自己寫、自己清（party），並且 re-export 同一個函式。同 omen_base、convoy_base 不進 MODULES（tianxia/core/ 底下的檔本來就是核心）。
"""
from __future__ import annotations

from ..state import GameState


def following(state: GameState) -> str | None:
    """跟著誰走在路上：答應了結伴（tagalong）而且已經在路上（journey）時回帶頭的人的名號，不然 None（跟著但還沒動身不算）。"""
    p = state.player
    if p.tagalong is not None and p.journey is not None:
        return p.tagalong.leader
    return None
