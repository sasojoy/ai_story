"""通緝掛上玩家卡（懸賞榜，bounties.py；PM 2026-10-08 派工「加強散人玩法」）：social.ACTIONS 登記一種互動 "wanted"。
只有你投靠了陣營、對方是敵對陣營的人時才畫一顆「通緝」：按下去填賞金（押在懸賞榜上，沒人揭成就退回）。
規則都在 bounties（post_problem、post）與 Game.post_wanted；這裡只畫鈕。"""
from __future__ import annotations

from typing import TYPE_CHECKING

from . import bounties, social

if TYPE_CHECKING:
    from .engine import Game

KIND = "wanted"


def buttons(game: Game, other: Game) -> list[social.CardButton]:
    s, o = game.state, other.state
    if not bounties.active(s, game.content) or s.player.faction is None or o.player.faction in (None, s.player.faction):
        return []
    problem = bounties.post_problem(s, game.content, o)
    if problem is not None:
        return [social.CardButton(action=KIND, label="通緝", note=problem, enabled=False)]
    cfg = game.content.config.bounties
    top = min(cfg.post_max, s.player.stats.get("silver", 0))
    return [social.CardButton(
        action=KIND, label="通緝", amount=top,
        note=f"賞金 {cfg.post_min}～{top} 兩，押在懸賞榜上；沒人揭成就退回",
        confirm=f"真的要花錢通緝{o.player.name}？",
    )]


def run(game: Game, other: Game, params: dict) -> list[str]:
    try:
        amount = int(params.get("amount", 0))
    except (TypeError, ValueError):
        amount = 0
    return game.post_wanted(other, amount)


social.register(social.CardAction(id=KIND, buttons=buttons, run=run, order=65))
