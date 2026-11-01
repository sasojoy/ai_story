"""江湖頁最上面的本週卡與三方卡（減法季批 1，整合設計 6.1、3.4、6.8）：只讀、只組字，不改狀態、不擲骰。

- 本週卡（week_card）吃掉以前那一排小標裡的主線、態勢、簽到與狀態列的「下一件」、黃底提示句。三行：
  第 N 週＋兩軍的態勢；這一週的主題一句（Scenario.week_themes，21 天季三週各一句，7 天的季照季長切成前、中、後段）；
  「你這一步」：未完成的託付（委託）→ 軍令 → 揭了的懸賞 → 伏筆的下一步 → 新手目標 → 去投靠，照順序列出來，網頁的「換一件事」挑下一個。
- 三方卡（sides_card）：官軍、黃巾（減法季四個勝利條件開著的季多地方豪強）各一欄：要做到、現在、贏了給、投靠在哪。
  還沒投靠的人江湖頁最上面就是它。

畫面的改動不掛開關（整合設計第十二章）：每一種季都是這張卡；規則關著的季三方卡只寫兩軍。
豪強的「此刻幫誰」與兩本帳是批 3c 的欄位：四勝利開著的季照 Game.sides_card 補（`lean` 是此刻幫的那一軍 id，豪強那一格「現在」寫兩本帳，
「贏了給」照 Config.jianfa.tiers，多 `join_at` 投靠點的分鐘）；拿不到那一份時那一格照舊寫 HAOQIANG_NOW_PENDING。
字待 joy 潤。
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from . import calendar, chapters, errands, foreshadow, rules, storyline, week_unlock, wins
from . import step as step_rules
from . import opening as opening_rules
from . import prologue as prologue_rules
from .rules import STANCE_NAMES
from .week_unlock import phase  # noqa: F401  前、中、後段：批 5 搬到 week_unlock（功能解鎖也照它），舊名照舊從這裡讀得到

if TYPE_CHECKING:
    from .engine import Game

JOIN_STEP = "先投一方：{places}。"  # 待 joy 潤：散人「眼下要事」最後的退路
ORDER_GAIN = "陣營記功 {n}／{quota}"  # 待 joy 潤：軍令那一件做完拿什麼（軍令本人不另給賞：照做一次替陣營記一次，湊滿套效果）
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
    {"cols": [{"id", "name", "goal", "now", "gives", "where": [地名], "mine"}], "joined": bool, "lean": None}。
    四勝利開著的季（批 3c）：每一欄多 join_at、gives 照四階寫、豪強那一欄的 now 寫兩本帳；lean 是豪強此刻幫的那一軍 id；
    投靠了的人多 tier_hint（「第三階・還差 40」）、豪強多 ledger（{"guan": 120, "huang": 40}）。"""
    s, c = game.state, game.content
    if not c.scenario.factions or s.world.ended or prologue_rules.active(s, c) or opening_rules.pending(s, c):  # 開局三選一還沒選：先不畫（批 7）
        return None
    four = rules.jianfa(c, s.world)
    standing = rules.stances(s, c) if rules.season_one(c, s.world) else None
    mine = s.player.faction
    extra = game.sides_card() if four else None  # 批 3c（Game.sides_card）：豪強那一格的「現在」、贏了給（照 Config.jianfa.tiers）、投靠點的分鐘
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
        hint = game.tier_hint()
        if hint is not None:
            out["tier_hint"] = hint
        ledger = wins.ledger_view(s.player, c)
        if ledger is not None:
            out["ledger"] = ledger
    return out


def _steps(game: Game, status: dict, orders: list[dict]) -> list[dict]:
    """「眼下要事」（以前叫「你這一步」，Joy 2026-10-26 改名）的候選，照整合設計 6.1 的順序：託付（委託）→ 軍令 → 揭了的懸賞 → 伏筆 → 新手目標 → 去投靠。
    每一件多一個 reward：做完拿什麼（託付、懸賞、新手目標原本的賞；軍令寫記功幾次；伏筆、去投靠沒有這個鍵）。卡本身不另給獎勵。
    託付的正式來源（減法季批 6，errands.step_items：身上還在辦的人物託付，多 id 與 target）排在最前面，懸賞列裡的委託接在後面；
    託付關著是空的，一個字都不變。
    每一件掛一個內部的 _ref（哪一張、哪一道），step.finish 拿它補批 3c 的目標與 id（四勝利開著）、或直接拿掉（關著一個字都不變）。"""
    s, c = game.state, game.content
    out: list[dict] = errands.step_items(s, c)
    rows = status.get("bounties") or []
    for b in rows:
        if b.get("commission"):
            out.append({"kind": "errand", "text": f"{b['title']}：{b['how']}", "who": b.get("issuer", ""), "reward": b.get("reward", ""),
                        step_rules.REF: ("errand", b.get("id"))})
    for o in orders:
        if not o.get("done"):
            out.append({"kind": "order", "text": f"{o['title']}：{o.get('how') or o['text']}",
                        "reward": ORDER_GAIN.format(n=o.get("progress", 0), quota=o.get("quota", 0)), step_rules.REF: ("order", o.get("id"))})
    for b in rows:
        if not b.get("commission") and not b.get("have"):
            out.append({"kind": "bounty", "text": f"{b['title']}：{b['how']}", "reward": b.get("reward", ""), step_rules.REF: ("bounty", b.get("id"))})
    step = foreshadow.next_step(s, c)
    if step:
        out.append({"kind": "foreshadow", "text": step, step_rules.REF: ("foreshadow",)})
    newbie = status.get("newbie")
    if newbie:
        for i, r in enumerate(newbie["rows"]):
            out.append({"kind": "newbie", "text": r["text"], "i": i, "reward": r.get("reward", ""), step_rules.REF: ("newbie", r.get("key"), r.get("go"))})
    if s.player.faction is None and c.scenario.factions and not s.world.ended:
        places = "、".join(f"{STANCE_NAMES.get(f.id, f.name)}在{_places(game, f)[0]}" for f in c.scenario.factions if _places(game, f))
        out.append({"kind": "join", "text": JOIN_STEP.format(places=places), step_rules.REF: ("join",)})
    rest = step_rules.finish(game, out)
    chapter = chapter_card(game)
    if chapter is None or chapter["waiting"]:
        return rest
    # 章回主線那一步永遠排第一（企劃者 2026-10-29 同意設計稿第四節）：不跟著「換一件事」輪
    return [{"kind": "chapter", "text": CHAPTER_STEP.format(no=chapter["no"], title=chapter["title"], hint=chapter["hint"]),
             "id": chapter["line"], "target": chapter["target"]}] + rest


CHAPTER_STEP = "第{no}回・{title}：{hint}"  # 眼下要事第一件（文字第一個全形冒號前是標題，web 照它拆）


def _showdown_live(game: Game, event_id: str) -> str | None:
    """時刻表上這一件大事的決戰此刻在集結（"muster"）或開打（"active"）；沒在打、或正在打的是別場是 None（章回卡的 live）。"""
    battle = game.world.get_battle()
    if battle is None or battle.phase not in ("muster", "active"):
        return None
    definition = game.content.battles.get(battle.battle_id)
    return battle.phase if definition is not None and definition.timetable_event == event_id else None


def chapter_card(game: Game) -> dict | None:
    """章回卡（main.week_card.chapter，chapters.card）：章回主線關著、手上沒有回是 None。"""
    card = chapters.card(game.state, game.content, game.stamp, lambda loc: step_rules.place(game, loc), lambda beat: _showdown_live(game, beat))
    if card is not None and card["here"]:  # 「去做」按的是選單上那一顆：選單此刻沒有它（例：豪強還沒挑一邊）就不畫
        want = f"{storyline.OPTION}:{card['line']}"
        card["here"] = any(o.id == want and o.enabled for o in game.options())
    return card


def week_card(game: Game, status: dict, orders: list[dict]) -> dict | None:
    """本週卡（整合設計 6.1）：序章裡、休季是 None（休季是結算卡）。欄位：
    {"label": "本週"／"今日", "when": "第 N 週"／"第 N 天", "theme": 主題一句（沒寫是空字串）,
     "sides": {"guan": 55, "huang": 45} 或 None, "steps": [{kind, text, (i)}]（四勝利開著的季每一件多 target、id，照 step:next 從今天
     那一件排起，step.finish）, "next": 下一件（給「為什麼」）或 None,
     "unlock": 第 2 週的功能剛開了那一句或 None, "locked": 還沒開的那一句（給「為什麼」）或 None,
     "cap": 45 級之後那一句或 None, "gap": 第 3 週「離贏還差多少」或 None（批 5；week_unlock）}。"""
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
    names = game.week_unlock_names()  # 這一季真的開著的第 2 週功能（減法季 6.6）
    card = {"label": label, "when": when, "theme": theme, "sides": sides, "steps": _steps(game, status, orders),
            "next": None if nxt is None else f"{nxt['title']}・{nxt['at']}" if nxt.get("at") else nxt["title"],
            "unlock": week_unlock.card_line(s, c, names), "locked": week_unlock.locked_line(s, c, names),
            "cap": week_unlock.cap_note(s, c), "gap": week_unlock.win_gap(s, c)}
    chapter = chapter_card(game)
    if chapter is not None:  # 章回主線（關著、手上沒有回時沒有這個鍵）
        card["chapter"] = chapter
    return card
