"""截殺掛上玩家卡（企劃者 2026-10-08 在決策卡選「有限制地開」）：social.ACTIONS 登記一種互動 "raid"。
兩個人都投靠了陣營、而且是敵對陣營時（或你揭了通緝他的懸賞）才畫一顆「截殺」（按不下去時寫為什麼；按得下去寫體力與勝算），按下去先問一次。
每季都有、不看第一季開關（懸賞榜設計 2.2）；Config.raid.enabled 關著時不畫（Game.raid_shown）。
不必對方同意，規則都在 Game（raid_shown、raid_refusal、raid_odds、raid）；這裡只畫鈕。真人假人同一套話。"""
from __future__ import annotations

from typing import TYPE_CHECKING

from . import mounts, social

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
    confirm = f"真的要對{name}下手？輸了要丟銀兩、掉氣血。"
    flee = game.raid_flee_odds(other)
    if flee > 0:  # 他的馬比你快（裝備四欄 5.10）：人就在眼前，看得到他騎什麼；幾成跟 raid() 擲的同一個數
        confirm += mounts.RAID_FLEE_ASK.format(odds=mounts.odds_text(flee))
    return [social.CardButton(action=KIND, label="截殺", note=f"體力 {cost}・勝算 {game.raid_odds(other)}", confirm=confirm)]


def run(game: Game, other: Game, params: dict) -> list[str]:
    return game.raid(other)


social.register(social.CardAction(id=KIND, buttons=buttons, run=run, order=60))
