"""玩家互動：此地還有誰、玩家卡、玩家卡上的鈕按下去（原本 Game 上的 peers_here、_peer、peer_card、peer_request、peer_act、calls_here；
全部拆包第 37 批搬進來，行為一個字不變）。Game 留一行委派（server、假人、測試與還沒搬的切磋、論武、截殺、結伴同行照舊叫它們）。

替對方寫東西（收到的禮、邀請、招呼）在同一把行動鎖裡讀他的存檔、改完存回去；不替他補算時間——補算會把他的 last_real 推到此刻，
下了線的人就會一直掛在名單上。真人假人一樣對待（伺服器假人設計第五節）：名單、卡、按鈕、拒絕的話一律不看 PlayerState.bot。
「此地還有」的判斷本身在核心的查詢服務 tianxia/core/presence.py（窗口 Config.presence_seconds）。
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from tianxia import naming
from tianxia.characters import CharacterStore, name_key

from . import social

if TYPE_CHECKING:
    from tianxia.engine import Game


def peers_here(ctx) -> list[dict]:
    """場景底下「此地還有誰」：[{name, side}]，照名號排序。路上、序章裡看不到人（social.here）。"""
    return [{"name": o.player.name, "side": social.side(o, ctx.content)} for o in social.here(ctx)]


def peer(ctx, name: str) -> Game | None:
    """此刻在你這裡的那個人那一份 Game（不叫模型、不補算時間，賽季接上你這一份）；不在這裡是 None。"""
    key = name_key(name)
    for state in social.here(ctx):
        if name_key(state.player.name) == key:
            other = type(ctx)(ctx.content, state, ctx.rng, ctx.world)
            other.client = None
            other.state.world = ctx.state.world
            return other
    return None


def peer_card(ctx, name: str) -> dict | None:
    """玩家卡（social.card）；他不在這裡了是 None（網頁照 social.GONE 那一句說）。"""
    other = peer(ctx, name)
    return None if other is None else social.card(ctx, other)


def peer_request(ctx, name: str, action: str, params: dict | None = None) -> naming.NamingRequest | None:
    """玩家卡上的鈕按下去之前要不要先請模型（social.CardAction.request；論武的首創取名）：三段式的 A 段，只讀。
    對方不在這裡、這一種互動沒有登記或不需要模型，是 None。"""
    handler = social.ACTIONS.get(action)
    other = None if handler is None or handler.request is None else peer(ctx, name)
    return None if other is None else handler.request(ctx, other, dict(params or {}))


def peer_act(ctx, name: str, action: str, params: dict | None = None) -> list[str]:
    """按了玩家卡上的一顆鈕：對方還在這裡、這一種互動有登記，才交給它做（social.CardAction.run），做完存回對方的存檔。
    按的人的江湖紀錄由各個互動自己寫（拒絕的話只回給按的人，不記）。"""
    ctx.peer_brief = None
    other = peer(ctx, name)
    if other is None:
        return ctx._log([social.GONE])
    handler = social.ACTIONS.get(action)
    if handler is None:
        return ctx._log(["（沒有這個動作。）"])
    msgs = handler.run(ctx, other, dict(params or {}))
    CharacterStore(ctx.world.db).save(other.state)
    ctx.touched.add(other.state.player.name)  # 他開著的分頁也刷新（server._tell_tabs）
    return ctx._log(msgs)


def calls_here(ctx) -> list[dict]:
    """場景底下「別人遞給你、還沒回的」打招呼、結伴、切磋邀請（social.calls）。"""
    return social.calls(ctx)


def carry_season(ctx: Game, old, fresh) -> None:
    """season.carry 的 peers 那一格（core_seams，全部拆包第 55 批；照原位搬，不看開關）。名帖（Joy 2026-10-19）：自己那一張、收到的、藏起來的、不接誰的挑釁話都是自己的東西，
    跨季保留；一天的次數照回體丹不能換季多一輪。這一季值得留名的頭銜寫進 title_book（「第N季 天下第一」）由這一包的 on_season_start 接（全部拆包第 37 批）。"""
    fresh.player.mingtie, fresh.player.mingtie_box = old.player.mingtie, old.player.mingtie_box
    fresh.player.mingtie_hidden, fresh.player.taunt_muted = old.player.mingtie_hidden, old.player.taunt_muted
    fresh.player.mingtie_day, fresh.player.mingtie_made, fresh.player.mingtie_sent = (
        old.player.mingtie_day, old.player.mingtie_made, old.player.mingtie_sent)
    fresh.player.gift_day, fresh.player.gifts_today = old.player.gift_day, old.player.gifts_today
