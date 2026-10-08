"""截殺掛上玩家卡（企劃者 2026-10-08 在決策卡選「有限制地開」）：social.ACTIONS 登記一種互動 "raid"。
只有兩個人都投靠了陣營、而且是敵對陣營時才畫一顆「截殺」（按不下去時寫為什麼；按得下去寫體力與勝算），按下去先問一次。
不必對方同意，規則都在 Game（raid_shown、raid_refusal、raid_odds、raid）；這裡只畫鈕。真人假人同一套話。"""
from __future__ import annotations

from typing import TYPE_CHECKING

from . import social

if TYPE_CHECKING:
    from .engine import Game

KIND = "raid"


def buttons(game: Game, other: Game) -> list[social.CardButton]:
    if not game.raid_shown(other):
        return []
    problem = game.raid_refusal(other)
    if problem is not None:
        return [social.CardButton(action=KIND, label="截殺", note=problem, enabled=False)]
    cost = game.content.config.raid.stamina
    name = other.state.player.name
    return [social.CardButton(
        action=KIND, label="截殺", note=f"體力 {cost}・勝算 {game.raid_odds(other)}",
        confirm=f"真的要對{name}下手？輸了要丟銀兩、掉氣血。",
    )]


def run(game: Game, other: Game, params: dict) -> list[str]:
    return game.raid(other)


social.register(social.CardAction(id=KIND, buttons=buttons, run=run, order=60))
