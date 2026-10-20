"""領地爭奪第二批：攻城戰（設計 3.6、4.4；計畫第四章 Task 10～11）——決戰引擎的縮小版。

每個有區塊的大區一筆範本（content/battles.json 的 siege_<大區>，BattleDef.siege）：一幕 5 回合、偏離中線 40 提前收場。這一場打哪一塊、
誰攻、開集結那一刻誰佔著記在 BattleInstance.siege（battle_instance.SiegeInfo）；攻城另存一串（SharedWorldState.sieges），跟時刻表決戰、
別的攻城戰同時打。名字一律「攻城・地點」（title）。"""
from __future__ import annotations

from .battle_instance import SiegeInfo
from .models import Content

TITLE = "攻城・{place}"  # 待 joy 潤：畫面、戰報、天下大事一律走 title


def title(content: Content, info: SiegeInfo) -> str:
    """這一場的名字（「攻城・淯水河畔」）。"""
    loc = content.locations.get(info.loc)
    return TITLE.format(place=loc.name if loc is not None else info.loc)
