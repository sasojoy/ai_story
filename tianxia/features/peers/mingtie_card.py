"""遞名帖掛上玩家卡（Joy 2026-10-19，取代抱拳）：social.ACTIONS 登記一種互動 "mingtie"。
卡上照兩人之間的名帖畫鈕：他遞給你的還沒回：「回帖」「婉拒」；你遞給他的還在等：一顆灰的；其餘一顆「遞名帖」（換過的寫「換新帖」，
按不下去時寫為什麼）。規則都在 mingtie_actions（send_problem、send、swap）；這裡只畫鈕、照 arg 分派。真人假人同一套話。"""
from __future__ import annotations

from typing import TYPE_CHECKING

from tianxia.characters import name_key

from . import invite_actions, invites, mingtie, mingtie_actions, social

if TYPE_CHECKING:
    from tianxia.engine import Game

KIND = "mingtie"


def _pending(game: Game, other: Game):
    return invites.between(game.state.world, game.state.player.name, other.state.player.name, KIND)


def buttons(game: Game, other: Game) -> list[social.CardButton]:
    c = game.content
    if not c.config.mingtie.enabled:
        return []
    inv = _pending(game, other)
    if inv is not None and name_key(inv.target) == name_key(game.state.player.name):
        mine = game.state.player.mingtie is not None
        return [
            social.CardButton(action=KIND, arg="yes", label="回帖", enabled=mine, note="" if mine else mingtie.NO_CARD),
            social.CardButton(action=KIND, arg="no", label="婉拒"),
        ]
    renew = mingtie.given(game.state, other.state.player.name) > 0
    problem = mingtie_actions.send_problem(game, other)
    left = mingtie.sent_left(game.state, c, game._pill_day())
    return [social.CardButton(
        action=KIND, arg="send", label="換新帖" if renew else "遞名帖", enabled=problem is None,
        note=problem or f"今天還能遞 {left} 張",
    )]


def run(game: Game, other: Game, params: dict) -> list[str]:
    arg = params.get("arg", "")
    if arg == "send":
        return mingtie_actions.send(game, other)
    inv = _pending(game, other)
    if inv is None or name_key(inv.target) != name_key(game.state.player.name) or arg not in ("yes", "no"):
        return ["這份邀請已經不在了。"]
    return invite_actions.answer_on_card(game, inv, other, arg)


social.register(social.CardAction(id=KIND, buttons=buttons, run=run, order=15))
