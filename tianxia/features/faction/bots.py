"""假人看到陣營的選項怎麼按（開發規範手冊 3.8；原本寫在 bot_policy.score 的 defect／sect 兩段）。
假人不叛投（計畫甲）、不拜門派（一類一顆從交友搬出來的一顆，同不叛投）；faction: 這幾顆（投靠、確認、選邊、改幫）原本落到 score 最後的 None：
投靠與確認走 _toward_faction（第二輪第 101 批從 bot_policy 搬來，舊名 re-export；take_turn 叫它的先後留在殼），不經 score。三個前綴一律回 None（不是 0.0）。
**模組層不准碰 engine 與假人殼**（bot_policy 模組層 import 這個檔）。"""
from __future__ import annotations

from typing import TYPE_CHECKING

from tianxia import bot_base
from tianxia.core.option import Option

if TYPE_CHECKING:
    from tianxia.engine import Game


def score(option: Option) -> float | None:
    """選項的分數；None＝假人不會按（defect:、sect:、faction:）。"""
    return None


def _toward_faction(game: Game, faction_id: str, ids: list[str]) -> str | None:
    """還沒投靠這一季效力的陣營：確認畫面就確認（不是自己的陣營就作罷）；在投靠點就投靠；
    不然往最近的投靠點走一站（走不過去就回傳 None）。"""
    p = game.state.player
    if p.pending_faction is not None:
        return "faction:confirm" if p.pending_faction == faction_id else "faction:cancel"
    if f"faction:{faction_id}" in ids:
        return f"faction:{faction_id}"
    hop = bot_base.next_hop(game, game.content.scenario.faction(faction_id).join_at)
    return f"move:{hop}" if hop is not None and f"move:{hop}" in ids else None
