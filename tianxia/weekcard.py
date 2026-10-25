"""江湖頁最上面的本週卡與三方卡（減法季批 1，整合設計 6.1、3.4、6.8）：只讀、只組字，不改狀態、不擲骰。

- 本週卡（week_card）吃掉以前那一排小標裡的主線、態勢、簽到與狀態列的「下一件」、黃底提示句。三行：
  第 N 週＋兩軍的態勢；這一週的主題一句（Scenario.week_themes，21 天季三週各一句，7 天的季照季長切成前、中、後段）；
  「你這一步」：未完成的託付（委託）→ 軍令 → 揭了的懸賞 → 伏筆的下一步 → 新手目標 → 去投靠，照順序列出來，網頁的「換一件事」挑下一個。
- 三方卡（sides_card）：官軍、黃巾（減法季四個勝利條件開著的季多地方豪強）各一欄：要做到、現在、贏了給、投靠在哪。
  還沒投靠的人江湖頁最上面就是它。

畫面的改動不掛開關（整合設計第十二章）：每一種季都是這張卡；規則關著的季三方卡只寫兩軍。
豪強的「此刻幫誰」與兩本帳是批 3c 的欄位（PlayerState.lean、兩本帳），還沒有時那一格寫 HAOQIANG_NOW_PENDING。
字待 joy 潤。
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from . import calendar, foreshadow, rules
from . import opening as opening_rules
from . import prologue as prologue_rules
from .rules import STANCE_NAMES

if TYPE_CHECKING:
    from .engine import Game

JOIN_STEP = "先投一方：{places}。"  # 待 joy 潤：散人「你這一步」最後的退路
HAOQIANG_NOW_PENDING = "替官軍、替黃巾各記一本帳"  # 待 joy 潤：兩本帳（批 3c）接上之前豪強那一格「現在」
# 「贏了給」（整合設計 3.3 的四階；四個勝利條件開著的季才照這張寫，關著的季照舊是陣營輸贏與出力）
WIN_GIVES = {
    "guan": "出力最高的一成拿第一階；其餘照出力拿第三、四階",
    "huang": "出力最高的一成拿第一階；其餘照出力拿第三、四階",
    "haoqiang": "替贏的那一軍出力最多的一成拿第二階；其餘拿第三、四階",
}
WIN_GIVES_OLD = "季末照陣營輸贏與你出的力論功行賞"  # 待 joy 潤：規則關著的季
HAOQIANG_GOAL = "挑一軍幫：幫的那一軍贏了就算你贏；季末只算你替贏的那一軍出的力；換邊隨時換，不算叛逃"
HAOQIANG_GOAL_OLD = "季末割據的態勢夠高是群雄並起"  # 規則關著、有割據那一條線的季


def phase(week: int, weeks: int) -> int:
    """這一季走到前、中、後哪一段（0、1、2）：21 天季是第幾週，7 天的季是第幾段（季曆本來就分三段），週末式的十二週照比例切。"""
    return max(0, min(2, (week - 1) * 3 // max(1, weeks)))


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
    {"cols": [{"id", "name", "goal", "now", "gives", "where": [地名], "mine"}], "joined": bool, "lean": None}。"""
    s, c = game.state, game.content
    if not c.scenario.factions or s.world.ended or prologue_rules.active(s, c) or opening_rules.pending(s, c):  # 開局三選一還沒選：先不畫（批 7）
        return None
    four = rules.jianfa(c, s.world, "four_wins")
    standing = rules.stances(s, c) if rules.season_one(c, s.world) else None
    mine = s.player.faction
    cols = []
    for f in c.scenario.factions:
        if f.id in ("guan", "huang"):
            other = "huang" if f.id == "guan" else "guan"
            now = f"態勢 {standing[f.id]}" if standing is not None else ""
            cols.append({"id": f.id, "name": STANCE_NAMES[f.id], "goal": _goal(c, f.id, other), "now": now,
                         "gives": WIN_GIVES[f.id] if four else WIN_GIVES_OLD, "where": _places(game, f), "mine": mine == f.id})
        elif four:  # 地方豪強（整合設計 3.1：兩本帳、幫哪一軍隨時換）
            cols.append({"id": f.id, "name": f.name, "goal": HAOQIANG_GOAL, "now": HAOQIANG_NOW_PENDING,
                         "gives": WIN_GIVES["haoqiang"], "where": _places(game, f), "mine": mine == f.id})
        elif standing is not None and "haoqiang" in standing:  # 規則關著、割據那一條線還在的季：照舊三方
            cols.append({"id": f.id, "name": STANCE_NAMES["haoqiang"], "goal": HAOQIANG_GOAL_OLD, "now": f"態勢 {standing['haoqiang']}",
                         "gives": WIN_GIVES_OLD, "where": _places(game, f), "mine": mine == f.id})
    return {"cols": cols, "joined": mine is not None, "lean": None}


def _steps(game: Game, status: dict, orders: list[dict]) -> list[dict]:
    """「你這一步」的候選，照整合設計 6.1 的順序：託付（委託）→ 軍令 → 揭了的懸賞 → 伏筆 → 新手目標 → 去投靠。"""
    s, c = game.state, game.content
    out: list[dict] = []
    rows = status.get("bounties") or []
    for b in rows:
        if b.get("commission"):
            out.append({"kind": "errand", "text": f"{b['title']}：{b['how']}", "who": b.get("issuer", "")})
    for o in orders:
        if not o.get("done"):
            out.append({"kind": "order", "text": f"{o['title']}：{o.get('how') or o['text']}"})
    for b in rows:
        if not b.get("commission") and not b.get("have"):
            out.append({"kind": "bounty", "text": f"{b['title']}：{b['how']}"})
    step = foreshadow.next_step(s, c)
    if step:
        out.append({"kind": "foreshadow", "text": step})
    newbie = status.get("newbie")
    if newbie:
        for i, r in enumerate(newbie["rows"]):
            out.append({"kind": "newbie", "text": r["text"], "i": i})
    if s.player.faction is None and c.scenario.factions and not s.world.ended:
        places = "、".join(f"{STANCE_NAMES.get(f.id, f.name)}在{_places(game, f)[0]}" for f in c.scenario.factions if _places(game, f))
        out.append({"kind": "join", "text": JOIN_STEP.format(places=places)})
    return out


def week_card(game: Game, status: dict, orders: list[dict]) -> dict | None:
    """本週卡（整合設計 6.1）：序章裡、休季是 None（休季是結算卡）。欄位：
    {"label": "本週"／"今日", "when": "第 N 週"／"第 N 天", "theme": 主題一句（沒寫是空字串）,
     "sides": {"guan": 55, "huang": 45} 或 None, "steps": [{kind, text, (i)}], "next": 下一件（給「為什麼」）或 None}。"""
    s, c = game.state, game.content
    if s.world.ended or prologue_rules.active(s, c) or opening_rules.pending(s, c):  # 開局三選一還沒選：本週卡在信收起來之後才出現（批 7）
        return None
    cal = status.get("calendar")
    if cal is None:  # 規則關著的季（beta）沒有季曆：寫第幾天
        label, when, theme_at = "今日", f"第 {status['day']} 天", 0
    else:
        w7 = calendar.week7_on(s.world, c)
        label = calendar.WEEK_WORDS["this"][1 if w7 else 0]  # 本週／這一段
        when = f"第 {cal['week']} {'段' if w7 else '週'}"
        theme_at = phase(cal["week"], len(c.config.season_segments) if w7 else cal["weeks"])
    themes = c.scenario.week_themes
    theme = themes[min(theme_at, len(themes) - 1)] if themes else ""
    stances = status.get("stances")
    sides = {k: stances[k] for k in ("guan", "huang") if k in stances} if stances else None
    nxt = status.get("next_event")
    return {"label": label, "when": when, "theme": theme, "sides": sides, "steps": _steps(game, status, orders),
            "next": None if nxt is None else f"{nxt['title']}・{nxt['at']}" if nxt.get("at") else nxt["title"]}
