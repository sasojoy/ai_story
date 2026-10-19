"""人物之間的關係（大勢人物擴充第二批「人與人」；Joy 2026-10-18「做」；設計稿
https://claude.ai/code/artifact/03df3760-b4bd-417c-935f-96dda0f500c2 第四節；內容在 content/relations.json）。

兄弟（張角三兄弟、桃園三人）、師生（盧植與劉備、公孫瓚）、上下（皇甫嵩與傅燮、曹操）都算盟友；仇敵（秦頡與張曼成、王允與張讓、
唐周與黃巾）。這裡只查表與照事實算心事（倒下的時刻記在 FigureState.fell_at，不另存）；倒下那一刻的反應在 figure_life.on_fall。
人物都用對話人物的 id（大勢人物的 id 跟對話人物一樣，check_figures 擋）。只 import models、state。"""
from __future__ import annotations

from .models import Content
from .state import GameState

KIN = {"brother": "兄弟", "mentor": "師生", "chief": "上下"}  # 盟友的三種


def side_of(content: Content, cid: str) -> str | None:
    """站哪一方：大勢人物照人物表的陣營，其他人照 CharacterDef.side（同 figure_life.side_of；這裡不能 import figure_life）。"""
    fig = content.figures.get(cid)
    if fig is not None:
        return fig.faction
    ch = content.characters.get(cid)
    return ch.side if ch is not None else None


def link(content: Content, a: str, b: str) -> str | None:
    """a 與 b 的關係：brother／mentor／chief（盟友，mentor 與 chief 不分誰是師長）、foe，沒有是 None。一對人寫在好幾條時盟友優先。"""
    if a == b:
        return None
    found = None
    for rel in content.relations:
        group = rel.members + ([rel.head] if rel.head else [])
        if rel.kind in KIN:
            if rel.kind == "brother" and a in rel.members and b in rel.members:
                return rel.kind
            if rel.head is not None and {a, b} <= set(group) and rel.head in (a, b):
                return rel.kind
        elif rel.faction is not None:
            if (a in rel.members and side_of(content, b) == rel.faction) or (b in rel.members and side_of(content, a) == rel.faction):
                found = "foe"
        elif a in rel.members and b in rel.members:
            found = "foe"
    return found


def allies(content: Content, cid: str) -> list[str]:
    """cid 的盟友（照人物表的順序）。"""
    return [other for other in content.characters if link(content, cid, other) in KIN]


def foes(content: Content, cid: str) -> list[str]:
    return [other for other in content.characters if link(content, cid, other) == "foe"]


def mood(state: GameState, content: Content, cid: str, span: float) -> str | None:
    """跟關係有關的心事：盟友 span 之內剛倒下是悲憤，仇敵剛倒下是得意（悲憤優先）；都沒有是 None。倒下的人只有大勢人物（fell_at）。"""
    w = state.world
    glad = False
    for fid, there in w.figures.items():
        if fid == cid or there.fell_at is None or w.time - there.fell_at > span:
            continue
        fallen = content.figures[fid].character if fid in content.figures else None
        if fallen is None:
            continue
        kind = link(content, cid, fallen)
        if kind in KIN:
            return "悲憤"
        glad = glad or kind == "foe"
    return "得意" if glad else None
