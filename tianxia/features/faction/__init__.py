"""陣營（功能包；開發規範手冊 3.2）。這一包做什麼、導覽在哪一節、設計稿是哪一份：README.md。

掛鉤照 tianxia/core/features.py 的表；用得到哪一個才寫哪一個。功能包只 import 核心（tianxia/core/ 與手冊 3.1 的核心模組）。
新寫給玩家看的字標「待 joy 潤」。
"""
from __future__ import annotations

from tianxia.core.features import Feature


class FactionFeature(Feature):
    name = "faction"
    prefix = "faction"  # 選項 id 的前綴：faction:…（核心只把這個前綴的 id 交給這一包）
    player_fields: tuple[str, ...] = ()  # 認領的 PlayerState 欄位（新欄位放自己的子模型，手冊 3.5）
    carried: tuple[str, ...] = ()  # 上面那些裡換季照帶走的

    def enabled(self, ctx) -> bool:
        return False  # 接上 Config.faction.enabled（Config 加欄位先過 PM：手冊 3.5）


FEATURE = FactionFeature()
