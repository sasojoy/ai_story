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

「你這一步」的候選由各包登記的格組（全部拆包第 36 批：step.items 照 core/features.py 的 STEP_ORDER 一格一格叫，懸賞榜兩格核心代叫），
這裡不再直接叫包、讀包的欄位。核心本體（第 36 批收進 MODULES）：不 import 功能包；章回（chapters）是共用規則層（第 40 批收進）。
- scripts/test_for.py：改這個檔跑核心測試＋煙霧＋自己檔名的 tests/map/test_weekcard.py（NOT_CORE_TESTS：改別的核心模組不多跑它）。
- 不寫 weekcard 檔名的混合檔 test_for 挑不到，另外跑（-n 4，不含 slow）：tests/bots/test_step.py、tests/core/test_chapters.py、
  tests/figures/test_week_unlock.py、tianxia/features/companions/tests/test_errands_weekcard.py、tianxia/features/guide/tests/test_opening.py；
  slow 的 tianxia/features/faction/tests/test_sides_card.py、tests/web/test_week_card_web.py 要跑就 --slow。
- 反過來，改這裡 import 的 chapters（共用規則層）時 test_for 只挑它自己檔名的 test_chapters＋煙霧＋邊界，上面那一串照舊另外跑：
  見 step.py 說明「反過來也挑不到」那一條（bounties、atlas、orders 等一起在那裡）。
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from . import calendar, story_base, week_unlock
from . import chapters  # 共用規則層（章回，全部拆包第 40 批收進）
from . import step as step_rules
from . import prologue as prologue_rules
from .week_unlock import phase  # noqa: F401  前、中、後段：批 5 搬到 week_unlock（功能解鎖也照它），舊名照舊從這裡讀得到

if TYPE_CHECKING:
    from .engine import Game

# JOIN_STEP（去投靠那一件）、ORDER_GAIN（軍令那一件的 reward）第 36 批跟著那一格搬進陣營包 join_actions、軍情包 order_actions，字一個不改

def _steps(game: Game, status: dict, orders: list[dict]) -> list[dict]:
    """「眼下要事」（以前叫「你這一步」，Joy 2026-10-26 改名）的候選，照整合設計 6.1 的順序：託付（委託）→ 軍令 → 揭了的懸賞 → 伏筆 → 新手目標 → 去投靠。
    每一件多一個 reward：做完拿什麼（託付、懸賞、新手目標原本的賞；軍令寫記功幾次；伏筆、去投靠沒有這個鍵）。卡本身不另給獎勵。
    託付的正式來源（減法季批 6，errands.step_items：身上還在辦的人物託付，多 id 與 target）排在最前面，懸賞列裡的委託接在後面；
    託付關著是空的，一個字都不變。
    每一件掛一個內部的 _ref（哪一張、哪一道），step.finish 拿它補批 3c 的目標與 id（四勝利開著）、或直接拿掉（關著一個字都不變）。
    全部拆包第 36 批：候選照 core/features.py 的 STEP_ORDER 組（step.items：各包登記自己那一格——託付是人物情誼包、軍令與伏筆是軍情包、
    新手目標是新手引導包、去投靠是陣營包——懸賞榜的委託與懸賞兩格核心代叫），先後跟換之前一段一段接的一樣。"""
    rest = step_rules.finish(game, step_rules.items(game, status, orders))
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
        want = f"{story_base.OPTION}:{card['line']}"
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
    if s.world.ended or prologue_rules.active(s, c) or (c.opening is not None and s.pending_event == c.opening.event):  # 開局三選一還沒選：本週卡在信收起來之後才出現（批 7）
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
