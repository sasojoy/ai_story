"""江湖頁的三方卡（減法季批 1，整合設計 3.4；main.sides_card）：只讀、只組字，不改狀態、不擲骰。全部拆包第 66 批從 tianxia/weekcard.py 搬進陣營包
（核心不能 import 包，舊名不留別名；main 表〔core/features.py 的 STATUS_ORDER〕的 sides_card 那一格叫它）。

官軍、黃巾（減法季四個勝利條件開著的季多地方豪強）各一欄：要做到、現在、贏了給、投靠在哪。還沒投靠的人江湖頁最上面就是它。
畫面的改動不掛開關（整合設計第十二章）：每一種季都是這張卡；規則關著的季三方卡只寫兩軍。
豪強的「此刻幫誰」與兩本帳是批 3c 的欄位：四勝利開著的季照 ending_actions.sides_card 補（`lean` 是此刻幫的那一軍 id，豪強那一格「現在」寫兩本帳，
「贏了給」照 Config.jianfa.tiers，多 `join_at` 投靠點的分鐘）；拿不到那一份時那一格照舊寫 HAOQIANG_NOW_PENDING。
字待 joy 潤。
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from tianxia import prologue as prologue_rules
from tianxia import rules, wins
from tianxia.rules import STANCE_NAMES

from . import ending_actions

if TYPE_CHECKING:
    from tianxia.engine import Game

HAOQIANG_NOW_PENDING = "替官軍、替黃巾各記一本帳"  # 待 joy 潤：兩本帳（批 3c）接上之前豪強那一格「現在」
# 「贏了給」（整合設計 3.3 的四階；四個勝利條件開著的季才照這張寫，關著的季照舊是陣營輸贏與出力）
WIN_GIVES = {
    "guan": "出力最高的一成拿第一階；其餘照出力拿第三、四階",
    "huang": "出力最高的一成拿第一階；其餘照出力拿第三、四階",
    "haoqiang": "替贏的那一軍出力最多的一成拿第二階；其餘拿第三、四階",
}
WIN_GIVES_OLD = "季末照陣營輸贏與你出的力論功行賞"  # 待 joy 潤：規則關著的季
HAOQIANG_GOAL = "挑一軍幫：幫的那一軍贏了就算你贏；季末只算你替贏的那一軍出的力；換邊隨時換，不算叛逃"


def _bar(content, side: str) -> tuple[int, str] | None:
    """這一方到幾分就是哪一種結局（第一季的結局表；只取寫得成「這一方幾分以上」的那一種，同 rules.stance_rule_note）。"""
    best = None
    for e in content.scenario.endings:
        if not e.season_one:
            continue
        bar = rules._one_bar(e)
        if bar is not None and bar[0] == side and (best is None or bar[1] < best[0]):
            best = (bar[1], e.title)
    return best


def _goal(content, side: str, other: str) -> str:
    text = f"季末態勢高過{STANCE_NAMES[other]}"
    bar = _bar(content, side)
    if bar is not None:
        text += f"；{'壓' if side == 'guan' else '推'}到 {bar[0]} 就是「{bar[1]}」"
    return text


def _places(game: Game, faction) -> list[str]:
    locs = game.content.locations
    return [locs[x].name for x in faction.join_at if x in locs]


def sides_card(game: Game) -> dict | None:
    """三方卡（整合設計 3.4）：劇本沒有陣營、序章裡、休季是 None。欄位：
    {"cols": [{"id", "name", "goal", "now", "gives", "where": [地名], "mine"}], "joined": bool, "lean": None}；
    官軍、黃巾兩欄多 bar（這一方到幾分就收季，沒有是 None）與 bar_title（那一種結局）。
    四勝利開著的季（批 3c）：每一欄多 join_at、gives 照四階寫、豪強那一欄的 now 寫兩本帳；lean 是豪強此刻幫的那一軍 id；
    投靠了的人多 tier_hint（「第三階・還差 40」）、豪強多 ledger（{"guan": 120, "huang": 40}）。"""
    s, c = game.state, game.content
    if not c.scenario.factions or s.world.ended or prologue_rules.active(s, c) or game._opening_pending():  # noqa: SLF001  開局三選一還沒選：先不畫（批 7）；經 ctx（services.py 有寫）
        return None
    four = rules.jianfa(c, s.world)
    standing = rules.stances(s, c) if rules.season_one(c, s.world) else None
    mine = s.player.faction
    extra = ending_actions.sides_card(game) if four else None  # 批 3c（ending_actions.sides_card）：豪強那一格的「現在」、贏了給（照 Config.jianfa.tiers）、投靠點的分鐘
    cols = []
    for f in c.scenario.factions:
        if f.id in ("guan", "huang"):
            other = "huang" if f.id == "guan" else "guan"
            now = f"態勢 {standing[f.id]}" if standing is not None else ""
            bar = _bar(c, f.id)  # 本週卡的拔河條兩端畫這一線（Joy 2026-11-07「能知道是哪一方佔上風」）
            cols.append({"id": f.id, "name": STANCE_NAMES[f.id], "goal": _goal(c, f.id, other), "now": now,
                         "gives": WIN_GIVES[f.id] if four else WIN_GIVES_OLD, "where": _places(game, f), "mine": mine == f.id,
                         "bar": bar[0] if bar else None, "bar_title": bar[1] if bar else ""})
        elif four:  # 地方豪強（整合設計 3.1：兩本帳、幫哪一軍隨時換）
            cols.append({"id": f.id, "name": f.name, "goal": HAOQIANG_GOAL, "now": HAOQIANG_NOW_PENDING,
                         "gives": WIN_GIVES["haoqiang"], "where": _places(game, f), "mine": mine == f.id})
    # 批 3c 接上了：贏了給照四階的稱號與比例寫、多一份投靠點的分鐘（join_at），豪強那一格「現在」寫兩本帳（看的人是豪強）或兩邊各幾人
    for col in cols:
        got = extra.get(col["id"]) if extra else None
        if got is not None:
            col["gives"], col["join_at"] = got["reward"], got["join_at"]
            if c.scenario.faction(col["id"]).allies:
                col["now"] = got["now"]
    lean = wins.lean_of(s.player, c) if four else None  # 「你此刻幫誰」（批 3c）：豪強此刻幫的那一軍 id；其他人、關著是 None
    out = {"cols": cols, "joined": mine is not None, "lean": lean}
    if four:  # 批 3c：此刻就收季拿第幾階・離上一階還差多少（投靠了的人）、豪強的兩本帳（數字；那一格的「現在」是同一份的字）
        hint = ending_actions.tier_hint(game)
        if hint is not None:
            out["tier_hint"] = hint
        ledger = wins.ledger_view(s.player, c)
        if ledger is not None:
            out["ledger"] = ledger
    return out
