"""論武掛上玩家卡（玩家互動第二層，企劃者 2026-10-08）：social.ACTIONS 登記一種互動 "discuss"。
卡上照兩人之間的邀請畫鈕：沒有邀請時每一樣你出得了的一顆「論武・以X」（arg＝invite:<鍵>；按不下去時只畫一顆灰的寫為什麼）；
他邀了你：每一樣你出得了的一顆「以X應之」（arg＝yes:<鍵>）與「婉拒」；你邀了他：「收回論武邀請」。同一種互動好幾顆鈕，
網頁可以照 arg 收成一個挑選清單。規則都在 Game（discuss_refusal、discuss_invite、discuss_request、answer_invite、_discuss）。
答應時的首創取名走三段式：request 是 A 段（Game.discuss_request），伺服器在鎖外取名，取好的放進 params["proposed"]。"""
from __future__ import annotations

from typing import TYPE_CHECKING

from . import invites, social
from .characters import name_key
from .rules import season_one

if TYPE_CHECKING:
    from .engine import Game

KIND = "discuss"


def _pending(game: Game, other: Game):
    return invites.between(game.state.world, game.state.player.name, other.state.player.name, KIND)


def _price_note(game: Game) -> str:
    xinde, stamina = game._discuss_cost()
    return f"心得 {xinde}、體力 {stamina}（各付一半）"


def buttons(game: Game, other: Game) -> list[social.CardButton]:
    if not season_one(game.content, game.state.world):
        return []
    inv = _pending(game, other)
    items = game.discuss_items()
    if inv is not None and name_key(inv.target) == name_key(game.state.player.name):
        theirs = dict(other.discuss_items()).get(inv.payload.get("item", ""), "那一樣")
        note = f"他出{theirs}・{_price_note(game)}"
        return [
            *(social.CardButton(action=KIND, arg=f"yes:{key}", label=f"以{label}應之", note=note, group="以此應之", pick=label)
              for key, label in items),
            social.CardButton(action=KIND, arg="no", label="婉拒論武"),
        ]
    if inv is not None:
        return [social.CardButton(action=KIND, arg="cancel", label="收回論武邀請", note="等他回覆")]
    problem = game.discuss_refusal(other)
    if problem is not None or not items:
        return [social.CardButton(action=KIND, arg="invite", label="論武", note=problem or "你身上沒有東西可出", enabled=False)]
    note = _price_note(game)
    return [
        social.CardButton(action=KIND, arg=f"invite:{key}", label=f"論武・以{label}", note=note, group="論武", pick=label)
        for key, label in items
    ]


def _parse(game: Game, other: Game, params: dict):
    """（動詞, 你出的那一樣, 那張邀請）；對不上是 None。"""
    verb, _, item = str(params.get("arg", "")).partition(":")
    inv = _pending(game, other)
    mine = inv is not None and name_key(inv.sender) == name_key(game.state.player.name)
    if verb == "invite":
        return verb, item, None
    if inv is None or verb not in ("yes", "no", "cancel") or (verb == "cancel") != mine:
        return None
    return verb, item, inv


def request(game: Game, other: Game, params: dict):
    parsed = _parse(game, other, params)
    if parsed is None or parsed[0] != "yes":
        return None
    return game.discuss_request(parsed[2], other, parsed[1])


def run(game: Game, other: Game, params: dict) -> list[str]:
    parsed = _parse(game, other, params)
    if parsed is None:
        return ["這份邀請已經不在了。"]
    verb, item, inv = parsed
    if verb == "invite":
        return game.discuss_invite(other, item)
    return game.answer_invite(inv, other, verb, item=item, proposed=params.get("proposed"))


social.register(social.CardAction(id=KIND, buttons=buttons, run=run, order=55, request=request))
