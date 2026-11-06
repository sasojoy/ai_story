"""機緣與伏筆的底座（全部拆包第 34 批「軍情二」；主人：軍情包 features/military；手冊 3.3、3.10 的查詢服務）。

核心與共用規則層讀機緣、伏筆的「只讀」那一小半留在這裡：核心的 rules（晉升條件的糧草換算）、content（驗內容讀天機表與題目）、
共用規則層待收的 ranks（召見問「這一階的機緣做過沒」）、叛投確認畫面（defection：手上有沒有沒收場的密謀）都經它，不 import 軍情包
（核心與共用規則層不准 import 包）。軍情包的 fs_rules、opp_rules 從這裡 re-export 同一批名字，所以舊名
`tianxia.foreshadow.need`、`tianxia.opportunities.done_for_rank` 照舊拿到同一個函式。

原本寫在 tianxia/foreshadow.py（GUANYIN、TIANJI、FIGURE_SLOT、TIANJI_ANSWER、scale、need、trips、_asks、asks_of）與
tianxia/opportunities.py（done_for_rank、_live、in_plot），一個字沒改。與 event_check 同樣不進 MODULES（tianxia/core/ 底下的檔本來就是核心）。

# core_world2：伏筆與機緣「讀」的那一半第 40 批再收（檔尾那一段）：fs_active（原 fs_rules.active）、event_ids、held_items、
heard_texts（與填字的 fill、_fragment_text、_version、_front、chain、_event、_figure_name、tianji_answer、_tianji、TIANJI_SLOTS）、
opp_active（原 opp_rules.active）、heard_clues，加上新的 clue_count（條件 clue_items 讀的）。events、narration、rumor_view、
server、rules.check_condition 讀它；軍情包的 fs_rules、opp_rules re-export 同一批（active 照原名）。要的共用依賴（calendar、
timetable、figures、rules.season_one）都在函式裡 import：這一份被 content、rules 早早載入。
"""
from __future__ import annotations

import hashlib
import math
from collections.abc import Iterator
from typing import TYPE_CHECKING

from ..models import Content, FsAsk, FsChain, FsFinal, FsFragment, FsItem, FsStep
from ..state import GameState, Plot

if TYPE_CHECKING:
    from ..world_state import WorldStateStore

GUANYIN = "guanyin"  # 官銀的計數鍵（PlayerState.fs_counters）
# 天機（伏筆文件 2.9）：同一個天機、同一個 key 永遠同一個答案。廣宗的內鬼（mole）是黃巾第 4 階機緣「營中的內鬼」
# （正式版乙二，opportunities 的推理型）用的，伏筆的鏈沒有用它
TIANJI: dict[str, tuple[str, ...]] = {
    "wind": ("東", "南", "西", "北"),
    "disguise": ("鹽車", "棺木", "香客", "商隊"),
    "mole": ("clerk", "priest", "strongman"),  # 廣宗的內鬼（伏筆文件 2.9；黃巾第 4 階機緣「營中的內鬼」）
}
FIGURE_SLOT = "{人物}"  # 最後一步的敘事裡「出面的那位」：figure 在那條戰線上就是他，否則是 stand_in
TIANJI_ANSWER = "tianji:"  # 答案寫成 tianji:<key>


# ── 伏筆：換算與題目 ───────────────────────────────────────


def scale(content: Content) -> float:
    """需求量的係數（伏筆文件 2.8、Config.foreshadow_tiers）：人數上限未滿哪一檔就用那一檔；都不是（1000 人以上）是 1。"""
    players = content.config.server_max_players
    for bound, factor in content.config.foreshadow_tiers:
        if players < bound:
            return factor
    return 1.0


def need(content: Content, base: int) -> int:
    """基準量換算成這個伺服器的需求量：乘上係數、無條件進位、最少 1。基準量 0（或更少）就是不要，回 0。"""
    if base <= 0:
        return 0
    return max(1, math.ceil(round(base * scale(content), 9)))


def trips(final: FsFinal) -> list[FsStep]:
    """最後一步的每一趟：寫了 steps 就是 steps，否則 final 自己就是那一趟。"""
    return list(final.steps) if final.steps else [final]


def _asks(trip: FsStep) -> list[FsAsk]:
    if not trip.question:
        return []
    main = FsAsk.model_construct(question=trip.question, options=list(trip.options), answer=trip.answer or "")
    return [main, *trip.then]


def asks_of(c: FsChain) -> Iterator[tuple[str, FsAsk]]:
    """每一趟的每一道題（給內容檢查用）：(哪裡, 題)。"""
    for i, trip in enumerate(trips(c.final)):
        for j, ask in enumerate(_asks(trip)):
            yield f"第 {i + 1} 趟第 {j + 1} 題", ask


# ── 機緣：召見與叛投確認畫面問的 ───────────────────────────


def done_for_rank(state: GameState, content: Content, rank: int) -> bool:
    """這一季替目前陣營完成過第 rank 階的任一種機緣（同一階完成任一種就夠，機緣文件第一節）；計畫丙的召見讀它。"""
    p = state.player
    return any(o.rank == rank and o.faction == p.faction and o.id in p.opp_done for o in content.opportunities)


def _live(state: GameState, plot: Plot) -> bool:
    """還在進行：開著、沒過期、而且這一季還沒落幕（休季什麼都不能再加）。"""
    return plot.status == "open" and state.world.time <= plot.deadline and not state.world.ended


def in_plot(state: GameState) -> bool:
    """響應或牽頭過、還沒收場也沒領的密謀：還開著（沒過期）的，或已經完成但自己還沒結算的。叛投的確認畫面讀它。"""
    p = state.player
    return any(
        p.name in x.members and x.id not in p.opp_settled and x.faction == p.faction and (_live(state, x) or x.status == "done")
        for x in state.world.plots
    )


# ── core_world2：伏筆與機緣「讀」的那一半（全部拆包第 40 批；軍情包 fs_rules、opp_rules 搬來、re-export 同一批）──
# 事件出不出現（events）、旁白挑事件（narration）、見聞的個人線索（rumor_view）、門下頁的伏筆物品（server）、
# 條件 clue_items（rules.check_condition）都讀這裡，不 import 軍情包。函式本體一個字沒改，只改名兩個：fs_rules.active → fs_active、opp_rules.active → opp_active。


TIANJI_SLOTS = {"{風向}": "wind", "{偽裝}": "disguise"}  # 文字裡的插槽


def tianji_answer(world_tianji: int, key: str) -> str:
    """本季的天機答案（伏筆文件 2.9）：天機與 key 的 sha256 決定候選裡的哪一個。用 hashlib，不用 Python 內建的 hash
    （那個每次執行都不同）。不認得的 key 丟 KeyError。"""
    candidates = TIANJI[key]
    digest = hashlib.sha256(f"{world_tianji}|tianji|{key}".encode()).digest()
    return candidates[int.from_bytes(digest[:8], "big") % len(candidates)]


def _tianji(world: WorldStateStore | None) -> int:
    return world.tianji() if world is not None else 0


def fs_active(state: GameState, content: Content) -> bool:
    """伏筆有沒有在跑：第一季開關開著、這一季開季時也是開的（蓋了章），而且 foreshadows.json 至少有一條鏈。
    所有入口都只看這一個判斷（審查 M4）。"""
    from .. import calendar  # noqa: PLC0415  omen_base 被 content、rules 早早載入：共用的依賴一律函式裡 import
    return bool(content.foreshadows.chains) and calendar.season_one_on(state.world, content)


def chain(content: Content, chain_id: str) -> FsChain | None:
    return next((c for c in content.foreshadows.chains if c.id == chain_id), None)


def _event(content: Content, event_id: str):
    return next((e for e in content.timetable if e.id == event_id), None)


def held_items(state: GameState, content: Content) -> list[tuple[FsItem, int]]:
    """手上的伏筆物品（煉製頁素材旁的「伏筆物品」畫面用，T7b）：照 foreshadows.json 的順序、不列數量 0 的。
    伏筆沒在跑（active 不成立：開關關著、這一季沒蓋章、沒有鏈）時是空的，就算背包裡有東西。"""
    if not fs_active(state, content):
        return []
    bag = state.player.clue_items
    return [(item, bag[item.id]) for item in content.foreshadows.items if bag.get(item.id, 0) > 0]


def event_ids(content: Content) -> set[str]:
    """伏筆的事件：片段的來源事件，以及任何選項會給伏筆物品或伏筆計數的事件（準備事件、豪強的起點）。
    開關關著時這些事件不出現（events.event_candidates），beta 那一季一個字都不變。"""
    found = {f.event for c in content.foreshadows.chains for f in c.fragments if f.event}
    for event in content.events.values():
        effects = [eff for ch in event.choices for eff in (ch.effect, ch.fail_effect)]
        if event.free_text is not None:
            effects += [event.free_text.effect, event.free_text.fail_effect]
        if any(eff.clue_items or eff.fs_counters for eff in effects):
            found.add(event.id)
    return found


def _version(state: GameState, content: Content, c: FsChain) -> str | None:
    from .. import timetable  # noqa: PLC0415  同上
    event = _event(content, c.event)
    return timetable._version(state, event) if event is not None else None  # noqa: SLF001  同一個套件


def _figure_name(content: Content, fid: str | None) -> str:
    character = content.characters.get(fid) if fid else None
    return character.name if character is not None else ""


def _front(content: Content, c: FsChain) -> str | None:
    if c.front is not None:
        return c.front
    event = _event(content, c.event)
    return event.front if event is not None else None


def fill(state: GameState, content: Content, c: FsChain, text: str, world: WorldStateStore | None) -> str:
    """填文字裡的插槽：{風向}、{偽裝} 是本季的天機；{人物} 是最後一步出面的那位（figure 在那條戰線上就是他，否則是 stand_in）。"""
    from .. import figures  # noqa: PLC0415  同上（共用規則層）
    for slot, key in TIANJI_SLOTS.items():
        if slot in text:
            text = text.replace(slot, tianji_answer(_tianji(world), key))
    if FIGURE_SLOT in text:
        final = c.final
        front = _front(content, c)
        present = final.figure is not None and (front is None or figures.on_front(state, final.figure, front))
        fid = final.figure if present or final.stand_in is None else final.stand_in
        text = text.replace(FIGURE_SLOT, _figure_name(content, fid))
    return text


def _fragment_text(state: GameState, content: Content, c: FsChain, fragment: FsFragment, world) -> str:
    text = fragment.versions.get(_version(state, content, c) or "", fragment.text)
    return fill(state, content, c, text, world)


def heard_texts(state: GameState, content: Content, world: WorldStateStore | None = None) -> list[str]:
    """聽過的線索片段（見聞頁的「個人線索」，傳聞分層設計第六節）：照鏈與片段的順序，文字照片段的寫法填好天機與出面的人
    （偷聽到的不再加「聽說誰說過」）。只有自己看得到；伏筆沒在跑（開關關著、沒有鏈）時是空的。"""
    if not fs_active(state, content):
        return []
    heard = state.player.fragments
    return [
        _fragment_text(state, content, c, c.fragments[i], world)
        for c in content.foreshadows.chains for i in sorted(heard.get(c.id, [])) if 0 <= i < len(c.fragments)
    ]


def opp_active(state: GameState, content: Content) -> bool:
    from ..rules import season_one  # noqa: PLC0415  rules 最外層不 import 這裡，反過來延後
    return season_one(content, state.world) and bool(content.opportunities)


def heard_clues(state: GameState, content: Content) -> list[str]:
    """聽過的機緣線索（見聞頁的「個人線索」，FB-086）：天時地利型的線索加上推理型內鬼的特徵片段，照聽到的先後（opp_clues 的順序），
    字跟當時寫進江湖紀錄的那一句一樣（hear_clues 的 text，只是不帶「你聽到一件事：」，跟伏筆片段 foreshadow.heard_texts 的寫法一致）。
    只有這個人自己聽過的（opp_clues 是他的存檔）；機緣完成了、時段過了照舊留著（跟伏筆完成之後片段還在一樣，不標記）；
    叛投之後舊陣營的線索也留著（clear 不清 opp_clues，企劃者裁決 E5.2），只是那些機緣做不了了。內容裡已經沒有的機緣或特徵（改版拿掉）略過。
    機緣沒在跑（開關關著、沒有機緣）時是空的。"""
    if not opp_active(state, content):
        return []
    texts: dict[str, str] = {}
    for o in content.opportunities:
        if o.kind == "timing":
            texts[o.id] = o.timing.clue
        elif o.kind == "deduce":
            texts.update({f"{o.id}:{t.key}": t.text for t in o.deduce.traits})
    return [texts[key] for key in state.player.opp_clues if key in texts]


def clue_count(state: GameState, item_id: str) -> int:
    """手上某一種伏筆物品的數量（PlayerState.clue_items，軍情包認領）：條件 clue_items（rules.check_condition）照它讀——
    核心不直接讀包的欄位（全部拆包第 40 批）。"""
    return state.player.clue_items.get(item_id, 0)


# ── map2：安排前往問的（全部拆包第 50 批；軍情包 fs_rules re-export）──
def fs_answering(state: GameState) -> bool:
    """正在答最後一步的題（PlayerState.fs_asking，軍情包認領）：共用規則層 atlas.travel_block 照它擋「先作罷才能安排前往」——
    共用層不直接讀包的欄位（全部拆包第 50 批，照第 40 批 clue_count）。"""
    return state.player.fs_asking is not None
