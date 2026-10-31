"""本週卡「你這一步」的批 3c 那一半（減法季整合設計 6.1；計畫 Task 3c-3）。

畫面只有一份「你這一步」：批 1 的 weekcard._steps（main.week_card.steps，照 託付 → 軍令 → 揭了的懸賞 → 伏筆 → 新手目標 → 去投靠 排好，
每一件 {"kind", "text", …}）。四勝利開著的季（on）這裡替每一件補（finish）：
- target：要去的地點 {"location", "name", "minutes"}（走過去的現實分鐘，Game.place_minutes；就在那裡 0、走不到 null）；沒有地點是 null；
- id：哪一道軍令、哪一張懸賞或委託、哪一條伏筆、哪一條新手目標、投靠哪一方；
- then：護糧軍令還沒接糧車時（target 是起點）多這一個，糧車要送到的終點 {"location", "name"}：輿圖把兩點都框進畫面（Joy 2026-10-31）；

並照「換一件事」（step:next，Game.choose 先接走、不在選單上）今天按了幾次從那一件排起（PlayerState.step_day／step_skip，pill_day 換日從頭）。
關著的季 weekcard 一個字都不變（finish 只拿掉 weekcard 內部的 _ref）。只讀，skip 只改那兩個欄位。"""
from __future__ import annotations

from typing import TYPE_CHECKING

from . import atlas, bounties, foreshadow, orders
from .rules import jianfa

if TYPE_CHECKING:
    from .engine import Game
    from .state import Bounty, Order

NEXT = "step:next"  # 「換一件事」：不在選單上（假人碰不到），Game.choose 先接走
REF = "_ref"  # weekcard._steps 掛在每一件上、給 finish 找目標的內部鍵；送出去之前一定拿掉


def on(game: Game) -> bool:
    """這一季「你這一步」有批 3c 那一半：四勝利開著（減法季的總開關＋開季的章），季還沒收。"""
    w = game.state.world
    return jianfa(game.content, w) and not w.ended


def place(game: Game, loc_id: str | None) -> dict | None:
    """目標地點：{"location", "name", "minutes"}；不是地圖上的地點是 None。"""
    if loc_id is None or loc_id not in game.content.locations:
        return None
    return {"location": loc_id, "name": game.content.locations[loc_id].name, "minutes": game.place_minutes(loc_id)}


def _order_places(game: Game, o: Order) -> set[str]:
    """這道軍令去哪裡做（只列摸清了的地方：同軍令卡，不洩漏沒摸清的地點）。"""
    s, c = game.state, game.content
    if o.template == "strike":
        where = atlas._strike_place(s, c, o)  # noqa: SLF001  同軍令卡的「他現在在哪」（讀人物此刻的所在）
        places = [where] if where is not None else []
    elif o.template == "siege":
        places = orders.siege_places(c, o.faction, o.front, s.world) if o.front else []
    elif o.template == "defend":
        places = orders.defend_places(c, s.world, o)
    elif o.template == "escort":
        places = [o.end if s.player.convoy is not None and s.player.convoy.order == o.id else o.start]
    else:
        places = [o.location]
    return {loc for loc in places if loc in c.locations and atlas.is_known(s, c, loc)}


def _bounty(game: Game, bounty_id: str | None) -> Bounty | None:
    """懸賞列上的那一張（懸賞榜的、人物的委託與求援）；找不到是 None。"""
    s, c = game.state, game.content
    pool = [*bounties.open_commissions(s, c), *bounties.rallies(s, c), *s.world.bounties]
    return next((b for b in pool if b.id == bounty_id), None) if bounty_id else None


def _target(game: Game, ref: tuple) -> tuple[str | None, dict | None]:
    """（id, target）：照 weekcard 掛的 _ref 找。"""
    s, c = game.state, game.content
    kind = ref[0]
    if kind == "order":
        o = next((x for x in s.world.orders if x.id == ref[1]), None)
        places = _order_places(game, o) if o is not None else set()
        return ref[1], place(game, game._nearest_to(places) if places else None)  # noqa: SLF001
    if kind in ("errand", "bounty"):
        b = _bounty(game, ref[1])
        if b is None:
            return ref[1], None
        return b.id, place(game, b.end if b.kind == "escort" else b.location if b.kind in ("strike", "scout") else None)
    if kind == "foreshadow":
        found = foreshadow.next_trip(s, c)
        return (found[0].id, place(game, found[1].location)) if found is not None else (None, None)
    if kind == "newbie":
        return ref[1], place(game, (ref[2] or {}).get("move"))
    if kind == "join":
        joins = {loc: f for f in reversed(c.scenario.factions) for loc in f.join_at if loc in c.locations}  # 一樣近照劇本陣營的順序
        where = game._nearest_to(set(joins)) if joins else None  # noqa: SLF001
        return (joins[where].id, place(game, where)) if where is not None else (None, None)
    return None, None


def _then(game: Game, ref: tuple) -> dict | None:
    """護糧軍令還沒接糧車：糧車要送到的終點 {"location", "name"}（target 是起點）；其他都是 None。"""
    s, c = game.state, game.content
    if ref[0] != "order":
        return None
    o = next((x for x in s.world.orders if x.id == ref[1]), None)
    if o is None or o.template != "escort" or (s.player.convoy is not None and s.player.convoy.order == o.id):
        return None
    if o.end not in c.locations or not atlas.is_known(s, c, o.end):
        return None
    return {"location": o.end, "name": c.locations[o.end].name}


def skipped(game: Game) -> int:
    """今天按了幾次「換一件事」（隔天從 0 算）。"""
    p = game.state.player
    return p.step_skip if p.step_day == game._pill_day() else 0  # noqa: SLF001


def finish(game: Game, items: list[dict]) -> list[dict]:
    """weekcard._steps 排好的那一串：每一件拿掉 _ref；四勝利開著時補 target（沒有地點是 null）與 id，再照今天換了幾次從那一件排起。
    已經帶了 target 的那一件照留（人物的託付：errands.step_items 自己寫好 id 與 target、沒有 _ref，減法季批 6）。"""
    live = on(game)
    out = []
    for item in items:
        ref = item.pop(REF, None)
        if live and "target" not in item:
            ident, target = _target(game, ref) if ref else (None, None)
            item["target"] = target
            if ident is not None:
                item["id"] = ident
            then = _then(game, ref) if ref else None
            if then is not None and target is not None:
                item["then"] = then
        out.append(item)
    k = skipped(game) % len(out) if live and out else 0
    return out[k:] + out[:k]


def skip(game: Game) -> list[str]:
    """「換一件事」：今天換的次數 +1（隔天重來）；本週卡的 steps 就從下一件排起。規則關著什麼都不做。不花體力、不寫江湖紀錄，回空的。"""
    if not on(game):
        return []
    p, day = game.state.player, game._pill_day()  # noqa: SLF001
    p.step_skip = (p.step_skip if p.step_day == day else 0) + 1
    p.step_day = day
    return []
