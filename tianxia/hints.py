"""碰到才說（新手引導重做設計第五節）：第一次碰到某個玩法時，對話框說一兩句。每一條整個遊戲只說一次。

這裡只管「這一條此刻由誰說、說什麼」與佇列的規矩；什麼時候碰到（觸發）、對話框怎麼出、記進江湖紀錄，在 Game
（_hint、_surface_hint、guide_box、guide_ack）。純函式、不碰時鐘與模型。

「說過」是**提示上框的那一刻**（show），不是排進佇列的那一刻（控制者裁示 N1）：排著還沒上框就被清掉（不再提示、換季）的，
之後碰到還有機會聽到；佇列照 id 去重（同一條不會排兩次）。"""
from __future__ import annotations

import re
from collections.abc import Iterable

from . import calendar
from .models import Content
from .state import GameState, HintNote

# 設計 5.2 的十八條（第 7 條 h_snubbed 與第 18 條 h_mandate 不看狀態，由事件自己叫 Game._hint），加上 explain-1 的 h_bond（第一次交友、
# 第一次跟人物談話：情誼有什麼用）；content/hints.json 的 id 只能是這些。觸發條件在 Game._hint_triggers（計畫三 Task 2）
KNOWN = frozenset({
    "h_merge", "h_clash", "h_refine_fail", "h_lose", "h_injury", "h_basic_art", "h_snubbed", "h_recruit", "h_free_text",
    "h_road", "h_cap", "h_spectator", "h_foreshadow", "h_event_reveal", "h_promotion", "h_showdown", "h_figure", "h_mandate",
    "h_bond",
})


# 不看狀態、由事件發生時自己叫 Game._hint 的三條（被名將打發、玉璽碎片的秘密揭開、第一次交友或談話）；其餘都是狀態提示（Game._hint_triggers 看角色此刻的狀態）。
# 排隊的限速只管狀態提示：同一時間最多一條在框上或排著（Game._queue_triggered_hints）；事件型的當場排，不吃限速
EVENT_ONLY = frozenset({"h_snubbed", "h_mandate", "h_bond"})
STATE = KNOWN - EVENT_ONLY

# 提示裡可以寫的數字（explain-1）：句子裡寫 {名字}，上框時換成設定裡的值，句子不寫死數字（設定改了，話跟著改）
PLACEHOLDER = re.compile(r"\{(\w+)\}")


def values(content: Content) -> dict[str, str]:
    """{名字} → 設定裡的值。"""
    return {"signature": str(content.config.signature_affinity)}


def unknown(content: Content, text: str) -> list[str]:
    """這句話裡不認得的 {名字}（載入時擋，content.validate）。"""
    known = values(content)
    return [name for name in PLACEHOLDER.findall(text) if name not in known]


def fill(content: Content, text: str) -> str:
    """把 {名字} 換成設定裡的值；不認得的照原樣留著（載入時已經擋過）。"""
    known = values(content)
    return PLACEHOLDER.sub(lambda m: known.get(m.group(1), m.group(0)), text)


def defined(content: Content, hint_id: str) -> bool:
    """內容的提示表裡有這一條。每季都要說的句子（開季那一句、再投靠的招呼）不在表裡，所以不記進 hints_seen。"""
    return any(x.id == hint_id for x in content.hints.hints)


def note_for(state: GameState, content: Content, hint_id: str) -> HintNote | None:
    """這一條此刻由誰說、說什麼；說不了（散人碰到沒有散人版的陣營提示、內容沒有這一條）是 None。"""
    h = content.hints
    hint = next((x for x in h.hints if x.id == hint_id), None)
    if hint is None:
        return None
    if hint.by == "mentor":
        first = hint.season_one and calendar.season_one_on(state.world, content)  # 第一季才是真的那幾句（HintDef.season_one）
        return HintNote(id=hint_id, speaker=h.head, text=fill(content, hint.season_one if first else hint.text))
    faction = state.player.faction
    if faction is not None and faction in hint.texts:
        e = content.tutorial.enlist
        who = e.recruiters.get(faction) if e is not None else None
        name = who.name if who is not None else content.scenario.faction_name(faction, faction)  # 引薦人沒寫（測試內容）用陣營名
        return HintNote(id=hint_id, speaker=name, text=fill(content, hint.texts[faction]), by=faction)
    if faction is None and hint.drifter:
        return HintNote(id=hint_id, speaker=h.head, text=fill(content, hint.drifter))
    return None


def queue_note(state: GameState, note: HintNote) -> bool:
    """把一條已經寫好的話排進佇列（提示表以外的：再投靠的招呼）：關了提示、假人不排；同一條已經排著就不再排。排進去回 True。
    這裡不記說過：上框的那一刻才記（show），而且不在提示表裡的（每季都要說的）不記進 hints_seen。"""
    p = state.player
    if p.hints_off or p.bot or any(n.id == note.id for n in p.hint_queue):
        return False
    p.hint_queue.append(note)
    return True


def queue(state: GameState, content: Content, hint_ids: Iterable[str]) -> None:
    """把還沒說過、也還沒排著的排進去（照給的順序）。關了提示、假人都不排；說不了的不排（之後還有機會說）。
    這裡不記說過：提示上框的那一刻才記（show）。"""
    for hint_id in hint_ids:
        if hint_id in state.player.hints_seen:
            continue
        note = note_for(state, content, hint_id)
        if note is not None:
            queue_note(state, note)


def show(state: GameState, content: Content, note: HintNote) -> bool:
    """這一條上框了：記成說過（只記內容提示表裡有的；開季那一句與再投靠的招呼每季都要說，不記）。
    第一次上框回傳 True（呼叫端照這個把說的話記進江湖紀錄）；已經上過框的回傳 False。"""
    if note.shown:
        return False
    note.shown = True
    if defined(content, note.id):
        state.player.hints_seen.add(note.id)
    return True
