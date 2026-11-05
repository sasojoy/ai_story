"""論武掛上玩家卡（玩家互動第二層，企劃者 2026-10-08）：social.ACTIONS 登記一種互動 "discuss"。
卡上照兩人之間的邀請畫鈕：沒有邀請時每一樣你出得了的一顆「論武・以X」（arg＝invite:<鍵>；按不下去時只畫一顆灰的寫為什麼）；
他邀了你：每一樣你出得了的一顆「以X應之」（arg＝yes:<鍵>；合不成的那一樣灰掉寫原因，FB-117）與「婉拒」；你邀了他：「收回論武邀請」。
同一種互動好幾顆鈕，網頁照 group 收成一個挑選清單。規則都在 discuss_actions（refusal、send、request、
invite_problem、item_problem、discuss）與 invite_actions.answer_invite。
答應時的首創取名走三段式：request 是 A 段（discuss_actions.request），伺服器在鎖外取名，取好的放進 params["proposed"]。
（原本是 tianxia/discuss.py，全部拆包第 38 批搬進玩家互動包；載入這一包就登記進 social.ACTIONS。）"""
from __future__ import annotations

from typing import TYPE_CHECKING

from tianxia import gender
from tianxia.characters import name_key
from tianxia.rules import season_one

from . import discuss_actions, invite_actions, invites, social

if TYPE_CHECKING:
    from tianxia.engine import Game

KIND = "discuss"


def _pending(game: Game, other: Game):
    return invites.between(game.state.world, game.state.player.name, other.state.player.name, KIND)


def _price_note(game: Game) -> str:
    xinde, stamina = discuss_actions.cost_of(game)
    return f"心得 {xinde}、體力 {stamina}（各付一半）"


ANSWER_GROUP = "以此應之"
ANSWER_NONE = "答應論武"  # 一樣都答不了時那一顆灰鈕（FB-117；待 joy 潤）
NONE_FITS = "你身上沒有一樣能跟{theirs}合得成：{why}"  # 每一樣都合不成、原因又不只一種（FB-117；待 joy 潤）


def _none_fits(rows: list[tuple[str, str, str]], theirs: str) -> str:
    """每一樣都合不成時灰鈕上寫的為什麼：原因都一樣就寫那一句；不一樣就列前三樣各自的兩三個字。"""
    reasons = {str(why) for _, _, why in rows}
    if len(reasons) == 1:
        return reasons.pop()
    shown = "、".join(f"{label}{getattr(why, 'short', '') or '合不成'}" for _, label, why in rows[:3])
    return NONE_FITS.format(theirs=theirs, why=shown + ("……" if len(rows) > 3 else ""))


def _answer_buttons(game: Game, other: Game, inv, items: list[tuple[str, str]]) -> list[social.CardButton]:
    """他邀了你：每一樣你出得了的一顆「以X應之」（網頁照 group 收成一個下拉清單）與「婉拒論武」。
    每一樣先驗過合不合得成（Game.discuss_item_problem）：合不成的那一項灰掉、後面寫兩三個字的原因，下拉清單預設是第一樣合得成的
    （FB-117：以前清單預設第一項，兩個新手都是【基礎吐納】在前，照預設按下去一定是「出的是同一樣」）。這一張邀請本身成不了
    （他正忙、論滿了……），或你身上一樣都合不成，只畫一顆灰的「答應論武」寫為什麼。"""
    theirs = dict(discuss_actions.items(other)).get(inv.payload.get("item", ""), "那一樣")
    decline = social.CardButton(action=KIND, arg="no", label="婉拒論武")
    problem = discuss_actions.invite_problem(game, inv, other)
    rows = [] if problem is not None else [(key, label, discuss_actions.item_problem(game, inv, other, key)) for key, label in items]
    if problem is None and not any(why is None for _, _, why in rows):
        problem = _none_fits(rows, theirs) if rows else "你身上沒有東西可出"
    if problem is not None:
        return [social.CardButton(action=KIND, arg="yes", label=ANSWER_NONE, note=problem, enabled=False), decline]
    note = f"{gender.pronoun(other.state)}出{theirs}・{_price_note(game)}"
    return [
        *(social.CardButton(
            action=KIND, arg=f"yes:{key}", label=f"以{label}應之", note=note, group=ANSWER_GROUP,
            pick=label if why is None else f"{label}（{getattr(why, 'short', '') or '合不成'}）", enabled=why is None,
        ) for key, label, why in rows),
        decline,
    ]


def buttons(game: Game, other: Game) -> list[social.CardButton]:
    if not season_one(game.content, game.state.world) or game.state.world.ended:  # 休季不畫（FB-169，同 FB-163 的截殺）
        return []
    inv = _pending(game, other)
    items = discuss_actions.items(game)
    if inv is not None and name_key(inv.target) == name_key(game.state.player.name):
        return _answer_buttons(game, other, inv, items)
    if inv is not None:
        return [social.CardButton(action=KIND, arg="cancel", label="收回論武邀請", note=f"等{gender.pronoun(other.state)}回覆")]
    problem = discuss_actions.refusal(game, other)
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
    return discuss_actions.request(game, parsed[2], other, parsed[1])


def run(game: Game, other: Game, params: dict) -> list[str]:
    parsed = _parse(game, other, params)
    if parsed is None:
        return ["這份邀請已經不在了。"]
    verb, item, inv = parsed
    if verb == "invite":
        return discuss_actions.send(game, other, item)
    return invite_actions.answer_invite(game, inv, other, verb, item=item, proposed=params.get("proposed"))


social.register(social.CardAction(id=KIND, buttons=buttons, run=run, order=55, request=request))
