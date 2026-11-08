"""切磋掛上玩家卡（玩家互動第二層，企劃者 2026-10-08）：social.ACTIONS 登記一種互動 "spar"。
卡上照兩人之間的邀請畫鈕：沒有邀請時一顆「切磋」（按不下去時寫為什麼）；他邀了你：「答應」「婉拒」；你邀了他：「收回」。
規則都在 spar_actions（refusal、send、spar）與 invite_actions.answer_invite；這裡只畫鈕、照 arg 分派。真人假人同一套話。
（原本是 tianxia/spar.py，全部拆包第 38 批搬進玩家互動包；載入這一包就登記進 social.ACTIONS。）"""
from __future__ import annotations

from typing import TYPE_CHECKING

from tianxia import gender
from tianxia.characters import name_key
from tianxia.core import identity_base  # 綁手機才能切磋（帳號與客服第 205 批）：發起與答應的鈕灰掉寫同一句
from tianxia.rules import season_one

from . import invite_actions, invites, social, spar_actions

if TYPE_CHECKING:
    from tianxia.engine import Game

KIND = "spar"


def _pending(game: Game, other: Game):
    return invites.between(game.state.world, game.state.player.name, other.state.player.name, KIND)


def buttons(game: Game, other: Game) -> list[social.CardButton]:
    if not season_one(game.content, game.state.world) or game.state.world.ended:  # 休季不畫（FB-169，同 FB-163 的截殺）
        return []
    cost = game.content.config.action_cost["train"]
    inv = _pending(game, other)
    if inv is not None and name_key(inv.target) == name_key(game.state.player.name):
        tired = game.state.player.stamina < cost
        if not identity_base.phone_ok(game, KIND):  # 只問答應的人（第 205 批）；婉拒照舊
            return [
                social.CardButton(action=KIND, arg="yes", label="答應切磋", note=identity_base.PHONE_NEEDED, enabled=False),
                social.CardButton(action=KIND, arg="no", label="婉拒"),
            ]
        return [
            social.CardButton(action=KIND, arg="yes", label="答應切磋", note=f"體力 {cost}", enabled=not tired),
            social.CardButton(action=KIND, arg="no", label="婉拒"),
        ]
    if inv is not None:
        return [social.CardButton(action=KIND, arg="cancel", label="收回切磋邀請", note=f"等{gender.pronoun(other.state)}回覆")]
    problem = identity_base.PHONE_NEEDED if not identity_base.phone_ok(game, KIND) else spar_actions.refusal(game, other)
    return [social.CardButton(
        action=KIND, arg="invite", label="切磋", note=f"體力 {cost}" if problem is None else problem, enabled=problem is None,
    )]


def run(game: Game, other: Game, params: dict) -> list[str]:
    arg = params.get("arg", "")
    if arg == "invite":
        return spar_actions.send(game, other)
    inv = _pending(game, other)
    mine = inv is not None and name_key(inv.sender) == name_key(game.state.player.name)
    if inv is None or arg not in ("yes", "no", "cancel") or (arg == "cancel") != mine:
        return ["這份邀請已經不在了。"]
    return invite_actions.answer_invite(game, inv, other, arg)


social.register(social.CardAction(id=KIND, buttons=buttons, run=run, order=50))
