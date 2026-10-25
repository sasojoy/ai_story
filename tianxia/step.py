"""本週卡第三行「你這一步」（減法季整合設計 6.1；計畫 Task 3c-3，欄位表 main.step）。

來源照順序：未完成的託付（批 6 接，現在是空的）→ 軍令（這一週還沒達成的，自己還沒出過力的排前面）→ 揭了的懸賞 → 伏筆的下一步
（聽過片段、此刻做得了的那一趟）→ 新手目標（newbie 的八條，最上面三條）→ 去投靠（散人、沒選「就當散人」）。
每天換一次：一天裡「換一件事」（step:next）往下挑一個，隔天（pill_day，台灣 00:00 換日）從頭來；換的次數記在
PlayerState.step_day／step_skip（都是 0 時不寫進存檔）。減法季批 3c 開著的季才有（rules.jianfa 的 four_wins；關著沒有這個鍵）。
只讀遊戲的狀態、不改任何東西（skip 只改那兩個欄位）；引擎接線見 Game.step_view 與 Game.choose。"""
from __future__ import annotations

from typing import TYPE_CHECKING

from . import atlas, bounties, foreshadow, newbie, orders, prologue
from .rules import jianfa

if TYPE_CHECKING:
    from .engine import Game
    from .state import Order

NEXT = "step:next"  # 「換一件事」：不在選單上（假人碰不到），Game.choose 先接走
SOURCES = ("errand", "order", "bounty", "foreshadow", "newbie", "join")  # 欄位表 main.step.source，照這個順序挑
# 寫給玩家的字（待 joy 潤）
ORDER_TEXT = "軍令：{title}"
BOUNTY_TEXT = "懸賞：{title}"
FORESHADOW_WHY = "你聽來的那幾段話，指向這一步。"
NEWBIE_WHY = "新手目標：做到了給{reward}。"
JOIN_TEXT = "到{place}投靠{faction}"
JOIN_WHY = "先投一方：官軍、黃巾、地方豪強各怎麼贏、贏了給什麼，看三方卡。"


def on(game: Game) -> bool:
    """這一季有「你這一步」：減法季批 3c 的子開關 four_wins 開著（總開關＋開季的章＋子開關；子開關關掉時這一批一個字都不變），
    季還沒收。批 6 接託付時要不要改掛總開關，等 PM 定。"""
    w = game.state.world
    return jianfa(game.content, w, "four_wins") and not w.ended


def _target(game: Game, loc_id: str | None) -> dict | None:
    """目標地點：{"location", "name", "minutes"}（minutes 是走過去要現實幾分鐘，Game.place_minutes；就在這裡是 0、走不到是 None）。"""
    if loc_id is None or loc_id not in game.content.locations:
        return None
    return {"location": loc_id, "name": game.content.locations[loc_id].name, "minutes": game.place_minutes(loc_id)}


def _row(source: str, text: str, why: str, target: dict | None = None, **extra) -> dict:
    """一件事：text、why、source、target，加上 id（哪一道軍令、哪一張懸賞……）；新手目標帶去分頁的另有 tab。沒有值的鍵不放。"""
    return {"text": text, "why": why, "source": source, "target": target, **{k: v for k, v in extra.items() if v is not None}}


def _errands(game: Game) -> list[dict]:
    """未完成的託付（減法季設計 5.5）：批 6（tianxia/errands.py）接上之前是空的。"""
    return []


def _order_places(game: Game, o: Order) -> set[str]:
    """這道軍令去哪裡做（只列摸清了的地方：同軍令卡，不洩漏沒摸清的地點）。"""
    s, c = game.state, game.content
    if o.template == "strike":
        place = atlas._strike_place(s, c, o)  # noqa: SLF001  同軍令卡的「他現在在哪」（讀人物此刻的所在）
        places = [place] if place is not None else []
    elif o.template == "siege":
        places = orders.siege_places(c, o.faction, o.front, s.world) if o.front else []
    elif o.template == "defend":
        places = orders.defend_places(c, s.world, o)
    elif o.template == "escort":
        places = [o.end if s.player.convoy is not None and s.player.convoy.order == o.id else o.start]
    else:
        places = [o.location]
    return {loc for loc in places if loc in c.locations and atlas.is_known(s, c, loc)}


def _orders(game: Game) -> list[dict]:
    """這一週（照現實天的季是今天）自己那一方還沒達成的軍令；自己還沒出過力的排前面，其餘照發令的順序。"""
    s, c = game.state, game.content
    side = game._side()  # noqa: SLF001  豪強分屬兩軍：依附那一軍的軍令（同軍令卡）
    if side is None:
        return []
    found = [o for o in orders.current(s, c, side) if not o.done]
    found.sort(key=lambda o: o.progress.get(s.player.name, 0) > 0)
    rows = []
    for o in found:
        places = _order_places(game, o)
        where = game._nearest_to(places) if places else None  # noqa: SLF001
        rows.append(_row("order", ORDER_TEXT.format(title=orders.title(c, o)), atlas.order_how(s, c, o), _target(game, where), id=o.id))
    return rows


def _bounties(game: Game) -> list[dict]:
    """手上揭著、還沒交差的懸賞（bounties.mine）：討伐、打探去那裡，護送去終點，通緝沒有地點。"""
    s, c = game.state, game.content
    rows = []
    for b in bounties.mine(s, c):
        where = b.end if b.kind == "escort" else b.location if b.kind in ("strike", "scout") else None
        rows.append(_row("bounty", BOUNTY_TEXT.format(title=bounties.title(c, b)), bounties.how(c, b, s), _target(game, where), id=b.id))
    return rows


def _foreshadows(game: Game) -> list[dict]:
    """伏筆的下一步（foreshadow.next_trips）：聽過片段的鏈、此刻做得了的那一趟。"""
    s, c = game.state, game.content
    return [
        _row("foreshadow", trip.label, FORESHADOW_WHY, _target(game, trip.location), id=chain.id)
        for chain, trip in foreshadow.next_trips(s, c, s.world.time)
    ]


def _newbie(game: Game) -> list[dict]:
    """新手目標（newbie：八條，最上面三條沒拿過的）：「去做」帶去哪照任務卡（Game._newbie_go）；帶去分頁的寫 tab。"""
    s, c = game.state, game.content
    if not newbie.active(s, c) or prologue.onboard_step(s, c) is not None:
        return []
    rows = []
    for goal in newbie.todo(s):
        if newbie.met(s, goal):
            continue
        go = game._newbie_go(goal.go)  # noqa: SLF001
        why = NEWBIE_WHY.format(reward=newbie.reward_text(c, goal))
        rows.append(_row("newbie", goal.text, why, _target(game, go.get("move")), id=goal.key, tab=go.get("tab")))
    return rows


def _join(game: Game) -> list[dict]:
    """去投靠：還是散人、劇本有陣營、沒在任務卡選「就當散人」；最近的那一個投靠點（照劇本陣營的順序同樣近照先後）。"""
    s, c = game.state, game.content
    p = s.player
    if p.faction is not None or not c.scenario.factions or newbie.DRIFTER in p.newbie_marks:
        return []
    joins = {loc: f for f in reversed(c.scenario.factions) for loc in f.join_at if loc in c.locations}
    where = game._nearest_to(set(joins))  # noqa: SLF001
    if where is None:
        return []
    faction = joins[where]
    text = JOIN_TEXT.format(place=c.locations[where].name, faction=faction.name)
    return [_row("join", text, JOIN_WHY, _target(game, where), id=faction.id)]


FINDERS = {"errand": _errands, "order": _orders, "bounty": _bounties, "foreshadow": _foreshadows, "newbie": _newbie, "join": _join}


def candidates(game: Game) -> list[dict]:
    """此刻排得上的每一件事，照 SOURCES 的順序。"""
    return [row for source in SOURCES for row in FINDERS[source](game)]


def skipped(game: Game) -> int:
    """今天按了幾次「換一件事」（隔天從 0 算）。"""
    p = game.state.player
    return p.step_skip if p.step_day == game._pill_day() else 0  # noqa: SLF001


def next_step(game: Game) -> dict | None:
    """欄位表 main.step：{"text", "why", "source", "target": {"location", "name", "minutes"} | None, "id", "tab"?}，另加 "left"
    （今天還有幾件可以換）。今天按過「換一件事」就往下挑（排到底再從頭）；什麼都排不上、規則關著是 None。"""
    if not on(game):
        return None
    rows = candidates(game)
    if not rows:
        return None
    return {**rows[skipped(game) % len(rows)], "left": len(rows) - 1}


def skip(game: Game) -> list[str]:
    """「換一件事」：今天換的次數 +1（隔天重來）。規則關著、沒得換什麼都不做。不花體力、不寫江湖紀錄，回空的。"""
    if not on(game) or len(candidates(game)) < 2:
        return []
    p, day = game.state.player, game._pill_day()  # noqa: SLF001
    p.step_skip = (p.step_skip if p.step_day == day else 0) + 1
    p.step_day = day
    return []
