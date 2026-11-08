"""通緝掛上玩家卡（懸賞榜，rules.py；PM 2026-10-08 派工「加強散人玩法」）：核心的 cards.ACTIONS 登記一種互動 "wanted"。
只有你投靠了陣營、對方是敵對陣營的人時才畫一顆「通緝」：按下去填賞金（押在懸賞榜上，沒人揭成就退回）。每季都有（懸賞榜設計 2.2）；
截殺關著（Config.raid.enabled）時不畫：通緝只能靠截殺交差，畫了也是交不了的單。
規則都在 rules（post_problem、post）與 actions.post_wanted；這裡只畫鈕。載入懸賞榜包就登記（__init__.py；原本 engine.py 頂端 import 它），頂端只碰核心的登記表，rules、actions 在函式裡才拿。"""
from __future__ import annotations

from typing import TYPE_CHECKING

from tianxia.core import cards

if TYPE_CHECKING:
    from tianxia.engine import Game

KIND = "wanted"


def buttons(game: Game, other: Game) -> list[cards.CardButton]:
    from tianxia.core import bounty_base  # noqa: PLC0415

    from . import rules  # noqa: PLC0415

    s, o = game.state, other.state
    if not bounty_base.active(s, game.content) or not game.content.config.raid.enabled:
        return []
    mine, theirs = game._side(), other._side()  # 豪強分屬兩軍：照依附那一軍分敵我
    if mine is None or theirs in (None, mine):
        return []
    from tianxia.core import identity_base  # noqa: PLC0415  綁手機才能通緝（帳號與客服第 205 批）：頂端只碰核心的登記表，同上

    problem = identity_base.PHONE_NEEDED if not identity_base.phone_ok(game, KIND) else rules.post_problem(s, game.content, o)
    if problem is not None:
        return [cards.CardButton(action=KIND, label="通緝", note=problem, enabled=False)]
    cfg = game.content.config.bounties
    top = min(cfg.post_max, s.player.stats.get("silver", 0))
    return [cards.CardButton(
        action=KIND, label="通緝", amount=top, amount_min=cfg.post_min,  # 輸入框從 post_min 起（FB-121 第 6 件）
        note=f"賞金 {cfg.post_min}～{top} 兩，押在懸賞榜上；沒人揭成就退回",
        confirm=f"真的要花錢通緝{o.player.name}？",
    )]


def run(game: Game, other: Game, params: dict) -> list[str]:
    from . import actions  # noqa: PLC0415

    try:
        amount = int(params.get("amount", 0))
    except (TypeError, ValueError):
        amount = 0
    return actions.post_wanted(game, other, amount)


cards.register(cards.CardAction(id=KIND, buttons=buttons, run=run, order=65))
