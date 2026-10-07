"""第四階席次與每週輪替（第一季設計 5.4；計畫 2026-10-06-第一季正式版-丁）。

有資格的人（PlayerState.qualified，計畫丙一）每週一照上一週的貢獻排名，前 N 名上任（N＝factions.rank4_seats）。
排名要讀每個人上一週的貢獻，可是週一的掛鉤只拿得到共用的賽季：所以有資格的人每次行動、同步時把自己每週的貢獻
抄進 WorldState.seat_ledger（report），週一照這本帳排（rotate）。有空缺時當下補上。只有第一季的規則開著才有。

名字一律寫名號：陣營軍情不匿名（傳聞分層第七節；rules.display_name 只給地方傳聞用），所以帳上不另存顯示名。"""
from __future__ import annotations

from . import factions
from .models import Content
from .rules import add_rumor, season_one
from .state import GameState

TITLES_RANK = 4


def _title(faction: str) -> str:
    """這個陣營第 4 階的頭銜（校尉、大方渠帥、一方之主）；陣營沒有頭銜表時是空字串。"""
    from .ranks import TITLES  # noqa: PLC0415  ranks → seats：在函式裡 import，避免循環

    titles = TITLES.get(faction)
    return titles[TITLES_RANK] if titles else ""


def seated(state: GameState) -> bool:
    """自己此刻在任嗎：有陣營、在那個陣營這一週的名單上。"""
    p = state.player
    return p.faction is not None and p.name in state.world.seats.get(p.faction, [])


def report(state: GameState, content: Content) -> list[str]:
    """抄帳（Game.choose、answer_event、travel、sync 的最後呼叫）：有資格的人把每週的貢獻抄進共用賽季的帳；
    自己陣營的席次沒坐滿、自己又還沒在任時當下補上，發一則陣營軍情、回傳給自己的那一句。
    季結束後不再動（季末那一刻的名單是之後頭銜要讀的，設計 13.3）。"""
    p, w = state.player, state.world
    if not season_one(content, w) or w.ended or p.faction is None or not p.qualified:
        return []
    title = _title(p.faction)
    if not title:
        return []
    w.seat_ledger.setdefault(p.faction, {})[p.name] = dict(p.contrib_weeks)
    held = w.seats.setdefault(p.faction, [])
    if p.name in held or len(held) >= factions.rank4_seats(content.config):
        return []
    held.append(p.name)
    # 新寫，待 joy 潤：下面這一則陣營軍情與回傳給自己的那一句
    add_rumor(state, f"{p.name}補上了{title}的缺。", content=content, layer="faction", faction=p.faction)
    return [f"你補上了{title}的缺，到下週一為止。"]


def leave(state: GameState, faction: str) -> None:
    """叛投時（defection.defect）：從舊陣營的帳與這一週的名單拿掉自己，兩處都拿，不留幽靈席次——名單上留著名字，這個缺就一直被他佔著；
    帳上留著名字，週一的排名還會把一個已經不在這個陣營的人排進去。空出來的席次，下一個有資格而且還沒在任的人下次同步或行動就補上（report），
    等於補缺；週一再照上週的帳重排。只動共用賽季，不動個人（qualified 由 defection.clear_progress 清）。"""
    w, name = state.world, state.player.name
    w.seat_ledger.get(faction, {}).pop(name, None)
    held = w.seats.get(faction, [])
    if name in held:
        held.remove(name)


def rotate(state: GameState, content: Content, week: int) -> list[str]:
    """週一 00:00 的掛鉤（world.WEEK_HOOKS，排在軍令發令之前）：每個陣營照上一週（week − 1）帳上的貢獻排名，前 N 名上任；
    同分照帳上的先後（先拿到資格的優先）。每個週一都發一則陣營軍情「本週在任的校尉：甲、乙。」，名單沒變的那一週也發
    （第一季設計 晉升奇遇 §一：每週上任另外發一則；帳上沒有人的陣營沒有名單可發）。回傳空串列：名單寫在陣營軍情裡，不上天下大事。
    一個週一只發一次：掛鉤看 WorldState.hooked_week，不管幾個人同步、暫停了幾次，那一週只跑一回。
    排名讀帳、不讀存檔：週一的掛鉤只拿得到共用賽季。賽季時鐘暫停時時間不動，掛鉤自然不會跑（暫停的那一週過完才排，只排一次）。"""
    w = state.world
    if not season_one(content, w) or w.ended:
        return []
    n = factions.rank4_seats(content.config)
    for faction, ledger in w.seat_ledger.items():
        title = _title(faction)
        if not title:
            continue
        order = {name: i for i, name in enumerate(ledger)}
        ranked = sorted(order, key=lambda name: (-ledger[name].get(week - 1, 0), order[name]))
        holders = ranked[:n]
        if holders:
            # 新寫，待 joy 潤：每週在任名單的陣營軍情
            add_rumor(state, f"本週在任的{title}：{'、'.join(holders)}。", content=content, layer="faction", faction=faction)
        w.seats[faction] = holders
    return []
