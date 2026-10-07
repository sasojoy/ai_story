"""第四階席次與每週輪替（第一季設計 5.4；計畫 2026-10-06-第一季正式版-丁）。

有資格的人（PlayerState.qualified，計畫丙一）每週一照上一週的貢獻排名，前 N 名上任（N＝factions.rank4_seats）。
排名要讀每個人上一週的貢獻，可是週一的掛鉤只拿得到共用的賽季：所以有資格的人每次行動、同步時把自己每週的貢獻
抄進 WorldState.seat_ledger（report），週一照這本帳排（之後的任務）。有空缺時當下補上。只有第一季的規則開著才有。

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
