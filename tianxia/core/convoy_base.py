"""押糧的底座（全部拆包第 35 批「陣營」；主人：軍情包 features/military 的 convoy_actions；手冊 3.3、3.10 的查詢服務）。

叛投確認畫面（陣營包 defection.prompt）要寫「押著的糧車作廢」，得知道玩家手上押著糧車沒有。糧車（PlayerState.convoy）是軍情包認領的欄位，
陣營包不准碰它，所以只讀的這一小半留在核心，陣營包問這裡；軍情包照舊自己寫、自己清（convoy_actions）。
同 omen_base 不進 MODULES（tianxia/core/ 底下的檔本來就是核心）。
"""
from __future__ import annotations

from ..state import GameState


def held(state: GameState) -> bool:
    """手上押著糧車嗎（還沒送到、也沒作廢）。"""
    return state.player.convoy is not None
