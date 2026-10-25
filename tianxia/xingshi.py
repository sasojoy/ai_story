"""領地爭奪第三批 A：〈天下形勢〉——每天 22:00 換天那一刻一篇的旁白（設計 3.10；計畫第五章 Task 16、17，第六章 6.3、6.4）。

開單（Game._xingshi_open，_conquest_tick 換天〔conquest_day.day_turn〕之後）：事實（facts）是上一篇以來的 day_log——收場的易手、守住、相持
（DayNote.result）、推滿當場易手（by="flip"，翻地與爭搶）、補缺退回原主（by="mend"，玉璽碎片改版第 3 批，不寫是誰）、攻方沒人到的作罷、
誰下了戰書約戰哪裡（by="letter"；第二批的眾議與主將定奪輿圖第三版第 5 批收掉了，認不得的那一筆略過）
——加上傍晚還沒打完的那幾場、三條戰線比上一篇往哪一邊動（寫「略偏黃巾」這種詞，不寫數字）、上一篇以來的天下大事
（不帶數字、不是〈天下形勢〉自己那一句的）；「是日：…」那一句（summary_line）照收場的那幾筆寫。
伺服器鎖外請模型照事實寫一篇（write；三段式 Game.xingshi_request → write → Game.settle_xingshi），過 clean（轉繁體、去標記、一百二十到八百字、
不能有阿拉伯數字或假名）；寫不出來、或過 Config.xingshi.grace_seconds 沒交回，照固定段（rule_text）。收下那一刻天下大事一則、江湖史一筆。
模型只寫文章：不給任何數字、不定任何勝負；假人程式的 Game 沒有 client，不叫模型。句型在 content/xingshi_lines.json（全部待 joy 潤）。
只 import models、state、battle_instance（守軍的名字）、conquest、conquest_day（day_log 的種類）、rules、siege（攻城戰那幾句天下大事的開頭）、
territory（易手那一句）、zh；engine、server、content 反過來呼叫它。"""
from __future__ import annotations

import hashlib
import re

from pydantic import BaseModel

from . import conquest, conquest_day, rules, siege, territory, zh
from .battle_instance import GUARD, GUARD_SIDE
from .models import Content
from .state import DayNote, WorldState

HEAD = "天下形勢・第 {n} 篇"  # 待 joy 潤：見聞「形勢」頁每一篇攤開時的標題
SUMMARY_HEAD = "是日："  # 一篇一行的那一句：「是日：黃巾軍拿下南陽官道；官軍守住潁川郊野。」
RUMOR_HEAD = "天下形勢："  # 待 joy 潤：收下那一刻的天下大事與江湖史，接「是日」後面那一段
ESSAY_MIN, ESSAY_MAX = 120, 800  # 模型寫的文章幾個字算數（不算換行）
NUM_PREDICT = 1400  # 八百字的文章加 JSON 外殼：只加不減（模型與假人那一份導覽「num_predict 只加不減」）
RULE_FACTS = 12  # 固定段最多拼幾條事實（四條一段）
LEAN_STRONG, LEAN_UP, LEAN_SLIGHT = 30, 15, 5  # 【開發】戰線離中線幾點算「佔盡上風」「漸佔上風」「略偏」，不到 SLIGHT 是「兩軍相持」
MOVE_AT = 3  # 【開發】比上一篇動了幾點以上才寫「往某一邊推了一截」
NIGHT_FROM, NIGHT_UNTIL = 18, 6  # 【開發】當地幾點到幾點開的單算入夜（每天 22:00 那一篇都是；管理者白天開的不是，正在打的那一場不寫「打到入夜」）

# letter／letter_plain、flip／flip_plain：翻地與爭搶（dev/flip-1）的 day_log 多的兩種 by——下戰書（reason 是下戰書的人；管理者的沒有名號）、
# 推滿當場易手（reason 是推最多的人；這一輪沒人推過就翻的沒有名號）。第二批的 plan_vote、plan_commander（眾議、主將定奪）第 5 批收掉了。
# letter_done／letter_done_plain：那一場已經打完、作罷或正在打的戰書，寫成已經發生的事、照時間順序排在結果前面（FB-610）；
# fighting_day：白天開的單（管理者「現在就開一篇」）正在打的那一場，不寫「打到入夜」
# mended／mended_late、summary 的 taken_mended／mended：補缺當場退回原主（by="mend"，玉璽碎片改版第 3 批；不點名起用的人，FB-646，待 joy 潤）——
# 同一篇裡先被翻走（推滿、攻城戰拿下）的接在那一筆後面寫「旋即又退回」、「是日」併成「某軍拿下某地，旋即被補回」；翻走是上一篇以前的事寫 *_late／mended
FACT_KEYS = ("taken", "taken_blow", "held", "stalemate", "void", "fighting", "fighting_day", "letter",
             "letter_plain", "letter_done", "letter_done_plain", "flip", "flip_plain", "mended", "mended_late", "line")
SUMMARY_KEYS = ("taken", "taken_mended", "mended", "held", "stalemate", "void", "none")
LEAN_KEYS = ("strong", "up", "slight", "even")
MOVE_KEYS = ("toward", "still")
# content.check_xingshi_lines 拿它填一次每一句：填得進去、填完沒有阿拉伯數字
SAMPLE = {
    "side": "官軍", "margin": "大勝", "place": "荒丘", "who": "沈浪", "keeper": "守軍", "attackers": "官軍、黃巾軍",
    "line": "南陽", "lean": "兩軍相持", "move": "，這一日大致未動",
}
# 天下大事裡攻城戰自己的那幾句（集結號角、守住、相持、補上最後一刀）不收：收場的結果 day_log 已經有了，集結那一句只是雜訊
SIEGE_PREFIX = siege.TITLE.split("{", 1)[0]
_DIGITS = re.compile(r"[0-9０-９]")
_KANA = re.compile(r"[぀-ヿㇰ-ㇿ]")

SYSTEM = (
    "你是東漢末年的史官，每天替天下寫一篇〈天下形勢〉。只照使用者給的事實寫：這一天哪裡被拿下、哪裡守住了、哪裡還在拉鋸，"
    "三條戰線各偏向哪一邊，誰下了戰書、下一仗約在哪裡。半文言、繁體中文，兩百到五百字，分兩三段，有史家的筆法與感慨。"
    "不要寫阿拉伯數字（數目寫成國字），不要編造事實裡沒有的人名、地名與勝負，不要列點、不要標題、不要評分。"
    "回傳 essay：整篇文章。"
)


def lines(content: Content) -> dict:
    """句型（content/xingshi_lines.json）。"""
    return content.xingshi_lines


def on(content: Content, world: WorldState | None) -> bool:
    """這一季有〈天下形勢〉：主機的開關（Config.xingshi.enabled）、內容有句型、這一季照領地爭奪的規則（conquest.on）。"""
    return bool(content.config.xingshi.enabled and content.xingshi_lines and conquest.on(content, world))


def _pick(pool: list[str], seed: str) -> str:
    """照種子挑一句（決定性，不碰任何亂數）。"""
    return pool[int(hashlib.sha256(seed.encode()).hexdigest(), 16) % len(pool)] if pool else ""


def _side(content: Content, side: str) -> str:
    """陣營的名字；中立地的守將（guard）寫守軍。"""
    if side == GUARD:
        return GUARD_SIDE
    return content.scenario.faction_name(side, side)


def _place(content: Content, loc_id: str) -> str:
    loc = content.locations.get(loc_id)
    return loc.name if loc is not None else loc_id


def _sides(content: Content, sides: list[str]) -> str:
    return "、".join(_side(content, s) for s in sides)


def note_fact(content: Content, note: DayNote, over: bool = False) -> str | None:
    """day_log 的一筆寫成一條事實；認不得的是 None。over：那一場已經打完（或作罷、正在打）的戰書，寫成已經發生的事（FB-610）；
    補缺那一筆是這一篇裡它被翻走之後的事（「旋即又退回」，FB-646）。"""
    fact = lines(content)["fact"]
    place = _place(content, note.loc)
    if note.by == conquest_day.MEND:  # 補缺：不寫是誰（持有者要藏）
        return fact["mended" if over else "mended_late"].format(side=_side(content, note.side), place=place)
    if note.result == "taken":
        key = "taken_blow" if note.blow else "taken"
        return fact[key].format(side=_side(content, note.taken), margin=note.margin, place=place, who=note.blow)
    if note.result == "held":
        return fact["held"].format(keeper=_side(content, note.keeper), place=place, attackers=_sides(content, note.attackers or [note.side]))
    if note.result == "stalemate":
        return fact["stalemate"].format(place=place, attackers=_sides(content, note.attackers or [note.side]))
    if note.void:
        return fact["void"].format(side=_side(content, note.side), place=place)
    if note.by in (conquest_day.LETTER, conquest_day.FLIP):  # 下戰書、推滿易手（翻地與爭搶）：有名號寫名號，沒有寫不帶名號的那一句
        key = ("letter_done" if over else "letter") if note.by == conquest_day.LETTER else "flip"
        return fact[key if note.reason else f"{key}_plain"].format(who=note.reason, side=_side(content, note.side), place=place)
    return None


def lean_text(content: Content, line: str, value: int) -> str:
    """這條線此刻偏向哪一邊（不寫數字）：離中線不到 LEAN_SLIGHT 是兩軍相持。"""
    words = lines(content)["lean"]
    low, high = territory.sides(content, line)
    gap = value - 50
    if abs(gap) < LEAN_SLIGHT or (high if gap > 0 else low) is None:
        return words["even"]
    key = "strong" if abs(gap) >= LEAN_STRONG else "up" if abs(gap) >= LEAN_UP else "slight"
    return words[key].format(side=_side(content, high if gap > 0 else low))


def move_text(content: Content, line: str, now: int, then: int | None) -> str:
    """比上一篇往哪一邊動（不寫數字）；沒有上一篇的值是空的。"""
    if then is None:
        return ""
    words = lines(content)["move"]
    low, high = territory.sides(content, line)
    side = high if now > then else low
    if abs(now - then) < MOVE_AT or side is None:
        return words["still"]
    return words["toward"].format(side=_side(content, side))


def is_night(real_now: float, content: Content) -> bool:
    """這一刻（現實秒）在當地（pill_day_utc_offset_hours）算不算入夜：NIGHT_FROM 點以後、NIGHT_UNTIL 點以前。"""
    hour = int((real_now + content.config.pill_day_utc_offset_hours * 3600) % 86400 // 3600)
    return hour >= NIGHT_FROM or hour < NIGHT_UNTIL


def line_values(world: WorldState, content: Content) -> dict[str, int]:
    """三條戰線此刻的值（XingshiMark.lines 記它）。"""
    return {line: rules.world_trend_value(world, content, line) for line in rules.front_ids(content)}


def facts(world: WorldState, content: Content, notes: list[DayNote], lines_then: dict[str, int], rumors_from: int = 0,
          night: bool = True, marks_from: int | None = None) -> list[str]:
    """這一篇的事實（新的一張單；照順序、最多 Config.xingshi.facts_max 條）：已經發生的事照時間順序（day_log 的順序：收場、作罷、推滿易手、
    補缺退回〔不寫是誰，FB-646〕，與那一場已經打完、作罷或正在打的戰書〔寫成「某某下戰書攻某地」，FB-610〕）→ 還沒打完的那幾場（night 是假〔白天開的單〕不寫「打到入夜」）
    → 三條戰線各一句（偏向、比上一篇往哪一邊動）→ 下一仗打哪裡（還沒開打的戰書）→ 上一篇以來的
    天下大事（rumors_from 之後，新的在前；帶數字的〔公告的時刻〕與〈天下形勢〉自己那一句不收）。每一條都不帶阿拉伯數字。
    痕跡看得見開著的季（減法季批 4）：天下大事之前多一類「痕跡過門檻」——WorldState.marks_fired 從第 marks_from 條起（上一篇開單那一刻
    已經有幾條，XingshiMark.fired）的痕跡各一句（marks.xingshi_facts）。過門檻那一刻不再寫世界層的傳聞（PM 2026-10-25 修正輪），
    所以這一類是痕跡進〈天下形勢〉唯一的路，按條數切才每一條恰好進一篇；marks_from 沒給或關著時一個字都不變。"""
    out: list[str] = []
    over = {i for i, n in enumerate(notes) if _letter_over(world, notes, i) or _mend_after(notes, i)}
    done = [(n, i in over) for i, n in enumerate(notes) if _happened(n) or i in over]
    plans = [n for i, n in enumerate(notes) if not _happened(n) and i not in over]
    for note, past in done:
        out.append(note_fact(content, note, over=past))
    if world.conquest is not None:
        fighting = lines(content)["fact"]["fighting" if night else "fighting_day"]
        out += [fighting.format(place=_place(content, s.loc)) for s in world.conquest.schedule if s.status == "open"]
    names = {t.id: t.name for t in content.scenario.trends}
    line_fact = lines(content)["fact"]["line"]
    for line, value in line_values(world, content).items():
        out.append(line_fact.format(line=names.get(line, line), lean=lean_text(content, line, value),
                                    move=move_text(content, line, value, lines_then.get(line))))
    for note in plans:
        out.append(note_fact(content, note))
    if marks_from is not None and rules.jianfa(content, world, "marks_visible"):
        from . import marks  # noqa: PLC0415  只有這一類用得到，延後 import

        out += [line for line in marks.xingshi_facts(world, content, marks_from) if line not in out]
    seen = set(out)
    for note, _ in done:  # 易手那一刻 territory 另發的「落入／收復」：跟收場（推滿易手、補缺退回）那一條是同一件事
        if _taken(note) or note.by == conquest_day.MEND:
            place, side = _place(content, note.loc), _side(content, note.taken or note.side)
            seen |= {territory.FLIP_LINE.format(place=place, side=side), territory.RETAKE_LINE.format(place=place, side=side)}
    for rumor in reversed(world.rumors[rumors_from:]):
        text = rumor.text.strip()
        if (rumor.layer != "world" or not text or _DIGITS.search(text) or text in seen
                or text.startswith(RUMOR_HEAD) or text.startswith(SIEGE_PREFIX)):
            continue
        seen.add(text)
        out.append(text)
    return [f for f in out if f and not _DIGITS.search(f)][: content.config.xingshi.facts_max]


def _happened(note: DayNote) -> bool:
    """這一筆是已經發生的事（收場、作罷、推滿易手、補缺退回），不是排下的下一仗（戰書）。"""
    return bool(note.result or note.void or note.by in (conquest_day.FLIP, conquest_day.MEND))


def _taken(note: DayNote) -> bool:
    """這一筆是易手給攻方（攻城戰拿下、推滿當場易手）。"""
    return note.result == "taken" or note.by == conquest_day.FLIP


def _mend_after(notes: list[DayNote], i: int) -> bool:
    """notes[i] 是補缺退回，而同一塊在這一篇裡、它前面被翻走過（FB-646：「旋即又退回」）。"""
    note = notes[i]
    return note.by == conquest_day.MEND and any(_taken(n) and n.loc == note.loc for n in notes[:i])


def _letter_over(world: WorldState, notes: list[DayNote], i: int) -> bool:
    """notes[i] 是一張戰書（還沒有結果的那一筆），而那一場已經不是「下一仗」了（FB-610）：這一篇的窗口裡，它後面同一塊有收場或作罷的那一筆，
    或同一邊對同一塊又下了一張（一邊一塊同時只有一場，前一張一定收了）；不然看時程表上這一塊還有沒有自己那一邊在攻、還沒開集結的那一場
    （開了集結正在打、作罷〔換天時辰已過、管理者取消，這兩種不記 day_log〕都算已經不是下一仗）。"""
    note = notes[i]
    if note.by != conquest_day.LETTER or _happened(note):
        return False
    for later in notes[i + 1:]:
        if later.loc == note.loc and (later.result or later.void or (later.by == conquest_day.LETTER and later.side == note.side)):
            return True
    schedule = world.conquest.schedule if world.conquest is not None else []
    return not any(s.loc == note.loc and s.status in conquest_day.LIVE and note.side in s.attackers for s in schedule)


def summary_line(notes: list[DayNote], content: Content) -> str:
    """「是日：…」那一句：這一天收場的那幾場（拿下、守住、相持）、推滿當場易手的（寫成拿下）與攻方沒人到作罷的；都沒有寫「各路按兵」。
    補缺退回（FB-646）照時間順序：同一篇裡前面拿下的那一句換成「某軍拿下某地，旋即被補回」（taken_mended），前面沒有的寫「某軍補回某地」。"""
    words = lines(content)["summary"]
    parts: list[str] = []
    taken_at: dict[str, tuple[int, str]] = {}  # 地點 → 拿下那一句在 parts 的第幾個、拿下的那一軍（還沒被補回的）
    for note in notes:
        place = _place(content, note.loc)
        if note.by == conquest_day.MEND:
            if note.loc in taken_at:
                i, taker = taken_at.pop(note.loc)
                parts[i] = words["taken_mended"].format(side=taker, place=place)
                continue
            part = words["mended"].format(side=_side(content, note.side), place=place)
        elif _taken(note):
            taker = _side(content, note.taken or note.side)
            part = words["taken"].format(side=taker, place=place)
            taken_at[note.loc] = (parts.index(part) if part in parts else len(parts), taker)
        elif note.result == "held":
            part = words["held"].format(keeper=_side(content, note.keeper), place=place)
        elif note.result == "stalemate":
            part = words["stalemate"].format(place=place)
        elif note.void:
            part = words["void"].format(place=place)
        else:
            continue
        if part not in parts:  # 兩軍併成一場、都沒人到：兩筆作罷，寫一次
            parts.append(part)
    return f"{SUMMARY_HEAD}{'；'.join(parts) if parts else words['none']}。"


def rumor_text(line: str) -> str:
    """收下那一刻的天下大事與江湖史：「天下形勢：」接「是日：」後面那一段。"""
    return RUMOR_HEAD + line.removeprefix(SUMMARY_HEAD)


def rule_text(fact_list: list[str], content: Content, seed: str) -> str:
    """模型寫不出來時的固定段：開頭一句、事實四條一段（最多 RULE_FACTS 條）、收尾一句，照種子挑（決定性）。"""
    words = lines(content)
    opening, closing = _pick(words["open"], f"{seed}|開頭"), _pick(words["close"], f"{seed}|收尾")
    body = fact_list[:RULE_FACTS]
    paras = ["".join(body[i:i + 4]) for i in range(0, len(body), 4)]
    paras = [opening + (paras[0] if paras else "")] + paras[1:] + [closing]
    return "\n".join(p for p in paras if p)


def clean(text: str | None) -> str | None:
    """模型寫的文章能不能用：轉繁體、去 markdown 的標記、去空行；一百二十到八百字（不算換行）、沒有阿拉伯數字或假名才收，否則 None。"""
    out = zh.to_traditional(str(text or ""))
    out = re.sub(r"^[#>*\-\s]+", "", out, flags=re.MULTILINE)
    out = re.sub(r"[*_`#]", "", out)
    paras = [p.strip() for p in out.split("\n")]
    out = "\n".join(p for p in paras if p)
    size = len(out.replace("\n", ""))
    if not (ESSAY_MIN <= size <= ESSAY_MAX) or _DIGITS.search(out) or _KANA.search(out):
        return None
    return out


# ── 模型寫文章（鎖外；server.write_xingshi）──────────────


class XingshiRequest(BaseModel):
    """A 段（Game.xingshi_request）：這一張單的篇次、哪一天、「是日：…」與事實。C 段照篇次與 key 認同一張。"""

    n: int
    key: int
    line: str
    facts: list[str]


class XingshiReply(BaseModel):
    essay: str = ""


def write(client, request: XingshiRequest) -> str | None:
    """B 段：請模型照事實寫一篇。寫壞了（過不了 clean）、叫不動、沒有 client 都是 None（C 段照固定段）。不碰狀態。"""
    if client is None:
        return None
    listing = "\n".join(f"- {f}" for f in request.facts)
    messages = [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": f"{request.line}\n這一天的事實：\n{listing}"},
    ]
    try:
        reply = client.chat_structured(messages, XingshiReply, temperature=0.8, num_predict=NUM_PREDICT,
                                       required_fields=["essay"], require_in_schema=True)
    except Exception:  # noqa: BLE001 — 模型叫不動、答壞了：照固定段
        return None
    return clean(reply.essay)
