"""入伍段（新手引導重做設計第四節）：第一次投靠時由那一邊的引薦人帶兩步——看戰局（看過軍令卡）、第一道軍令。
不佔 tutorial_step：記在 PlayerState.enlist_step（None＝還沒開始）。只在第一季開始（beta 季沒有軍令）。"""
from __future__ import annotations

from collections.abc import Callable, Collection

from . import calendar, orders, rules
from .models import Content, Recruiter
from .rules import season_one
from .state import GameState
from .world_state import WorldStateStore


def _steps(content: Content):
    e = content.tutorial.enlist
    return e.steps if e is not None else []


def recruiter(state: GameState, content: Content) -> Recruiter | None:
    e, faction = content.tutorial.enlist, state.player.faction
    return e.recruiters.get(faction) if e is not None and faction is not None else None


def active(state: GameState, content: Content) -> bool:
    """入伍段進行中。按過「略過新手引導」的人永遠不是：略過在沒有入伍段的內容上存的 enlist_step 是 0（＝步數 0 的「走完」），
    之後內容加了入伍段，0 不能被讀成「第一步」（不然他一投靠，主線那一欄永遠寫著引薦人的話）。"""
    step = state.player.enlist_step
    return step is not None and step < len(_steps(content)) and not state.player.guide_skipped


def waiting(state: GameState, content: Content) -> bool:
    """入伍段還沒開始、也還能開始：內容有入伍段、這個人還沒開始過、沒略過、這一季是第一季。Game.skip_tutorial 看它：
    引導走完、還沒投靠的人按「略過」也不是什麼都不做（設計 7.3：略過＝序章與入伍段都略過）。"""
    p = state.player
    return bool(_steps(content)) and p.enlist_step is None and not p.guide_skipped and season_one(content, state.world)


def done(state: GameState, content: Content) -> bool:
    step = state.player.enlist_step
    return step is not None and step >= len(_steps(content)) > 0


def begin_if_joined(state: GameState, content: Content) -> bool:
    """剛投靠（有陣營、入伍段還沒開始、這一季是第一季、沒有略過引導、這一邊有引薦人）：開始入伍段。回傳有沒有開始。
    「剛」是呼叫端的事：Game.choose／answer_event 只在這一下動作之前還沒有陣營時才叫它——已經投靠的舊存檔、叛投都不會被拉進來
    （設計 7.2；preflight F1）。"""
    p = state.player
    if p.enlist_step is not None or p.guide_skipped or not season_one(content, state.world):
        return False
    if recruiter(state, content) is None:
        return False
    p.enlist_step = 0
    p.enlist_since = state.world.time
    return True


ONBOARDING = 3  # 入伍段上線的版本章（state.ONBOARDING_VERSION 升到 3 的那一版）；比它小的存檔是入伍段上線之前存的


def mark_veteran(state: GameState, content: Content) -> bool:
    """換版當下已經投靠的角色不走入伍段（設計 7.2）：讀檔時把「入伍段上線之前就有陣營」的人蓋成走完（enlist_step ＝步數），
    沒有框、也不寫任何話。認的是 PlayerState.onboarding 的版本章（比 ONBOARDING 小＝入伍段上線之前存的）：換版之後建的角色、
    章一開始就是新的，在 beta 季投靠、入伍段沒開始的人也不會被當成老手（他還沒走過，下一季投靠時照常走）。
    沒投靠的老存檔、走到一半的（enlist_step 不是 None）、略過的都不動；內容沒有入伍段什麼都不蓋。
    要在換季之前叫（Game._drop_stale_references 一開頭）：換季會把陣營清掉，之後就認不出他是老手；蓋了走完的 enlist_step 換季會帶過去
    （_reset_player_for_new_season），下一季再投靠不重走。回傳有沒有蓋。"""
    p = state.player
    if not _steps(content) or p.faction is None or p.enlist_step is not None or p.onboarding >= ONBOARDING:
        return False
    p.enlist_step = len(_steps(content))
    return True


def skip(state: GameState, content: Content) -> None:
    """略過新手引導（設計 7.3）：入伍段也算走完，不畫框、之後投靠也不開始。"""
    state.player.enlist_step = len(_steps(content))
    state.player.enlist_end = False


TICK = "✔ 引導完成"


def _texts(who: Recruiter, i: int) -> list[str]:
    """第 i 步框上說的話，一段一段：第一步是入營、看戰局兩段，其餘是那一步交代的一句。"""
    return [who.intro, who.briefing] if i == 0 else [who.order_hint]


def told(state: GameState, content: Content) -> list[str]:
    """此刻眼前這一步（剛走完的是結尾）引薦人說的話，寫成江湖紀錄那一種「【名字】話」的行（設計 6.2：說過的話都記進見聞），
    跟說書人的步驟一樣記在那一則的 guide。呼叫端在這一步「成為眼前這一步」的那一刻記一次：投靠開始入伍段、往下一步、走完。
    其餘時候（框上的話只是重畫）不記。沒有在進行、也不是剛走完的是空的。"""
    who = recruiter(state, content)
    if who is None:
        return []
    if active(state, content):
        texts = _texts(who, state.player.enlist_step)
    elif state.player.enlist_end and done(state, content):
        texts = [who.done]
    else:
        texts = []
    return [f"【{who.name}】{text}" for text in texts]


def note(state: GameState, content: Content, world: WorldStateStore, action: str) -> list[str]:
    """跟 guide.note_action 同一個做法：符合這一步就往下一步，一路到不符合為止；走完設 enlist_end（框上換結尾）。
    回傳：每完成一步一個 TICK，接著是新的這一步（或結尾）引薦人說的話（told）。"""
    from .guide import goal_met  # guide 也 import 這裡：放在函式裡避免循環

    msgs: list[str] = []
    todo = _steps(content)
    while active(state, content) and goal_met(state, content, world, todo[state.player.enlist_step].done_when, action):
        state.player.enlist_step += 1
        state.player.enlist_since = state.world.time  # 新的這一步從這一刻開始算（最後一步一週做不完就收，expire）
        msgs.append(TICK)
    if msgs and done(state, content):
        state.player.enlist_end = True
    return msgs + (told(state, content) if msgs else [])


def expire(state: GameState, content: Content) -> list[str]:
    """最後一步（第一道軍令）從開始算起一週（季曆）還沒做完，引薦人照樣說結語、入伍段關起來（FB-094）：不然這一週做不到的人
    （豪強一開始只有打不贏的打擊軍令）框會一直掛在那裡。看世界時間（Game.sync 傳進來的現在），引擎不讀電腦時鐘；暫停中世界時間
    不走，所以不會被暫停吃掉。只動最後一步：看軍令卡那一步由網頁自己送。這一版之前存的角色沒有 enlist_since：這一次才從現在算起。
    回傳引薦人的結語（江湖紀錄的那一行，跟 note 走完時一樣）；沒收就是空的。"""
    p = state.player
    if not active(state, content) or p.enlist_step != len(_steps(content)) - 1:
        return []
    if p.enlist_since is None:
        p.enlist_since = state.world.time
        return []
    if state.world.time - p.enlist_since < calendar.WEEK / calendar.cal_scale(content, state.world):
        return []
    p.enlist_step = len(_steps(content))
    p.enlist_end = True
    return told(state, content)


def how_here(state: GameState, content: Content, enabled: Callable[[], Collection[str]] | None = None) -> str:
    """第一道軍令那一步框上多的一句（FB-093）：你腳下這裡這週的軍令做得了的行動（orders.doable_here）；一個都做不了寫 how_none。
    內容沒寫這兩句（Enlist.how_here）就是空字串，框跟以前一樣。
    enabled：回傳「選單上此刻按得下去的鈕的 id」的函式（Game 給的；只在要寫這一句時才叫）。給了就只點名按得下去的：沒有糧草的人
    不能被指去接糧車、體力見底的人不能被指去巡哨——點名一顆灰的鈕比什麼都不說更糟（審查 Minor 3）。沒給就不過濾（只看軍令與地點）。"""
    e = content.tutorial.enlist
    if e is None or not e.how_here:
        return ""
    p = state.player
    acts = orders.doable_here(state, content, p.faction, p.location)
    duty = orders.duty_name(content, p.faction)  # 守勢行動現在也算第一道（FB-094）：在有戰線的地方，不管這週有沒有守城軍令
    if duty and (duty, "act:duty") not in acts and rules.front_of(content, p.location) is not None:
        acts.append((duty, "act:duty"))
    if enabled is not None:
        pressable = set(enabled())
        acts = [act for act in acts if act[1] in pressable]
    names = list(dict.fromkeys(name for name, _ in acts))
    return e.how_here.replace("{做法}", "、".join(names)) if names else e.how_none


def box(state: GameState, content: Content, enabled: Callable[[], Collection[str]] | None = None) -> dict | None:
    """入伍段的對話框：進行中是這一步的話（第一步前面接入營那一段）；剛走完是結尾、等「知道了」。其他是 None。
    key 是這一步的 id（結尾是 "enlist_end"），跟說書人的框同一個欄位（FB-076：網頁記收起記的是它）；
    眼前有事件還沒了結時話換成「先把眼前的「…」了結」、pending 標 True、收起來那一行送空字串（跟說書人的框一樣，FB-063／FB-076，
    網頁預設把這一句收成一行）；結尾永遠是 False。
    full：引薦人的話不被切掉（設計 6.2 對序章與入伍段：「話不會被切掉」）——網頁不套說書人那種長話收成三行（FB-076）；每個框都帶。
    paged：入營＋看戰局那種兩段以上的步驟，網頁照空一行分頁、一次一段（跟師父的出師那一步同一個做法，指示在最後一頁），不然兩段放下去
    行動列就被擠到分頁列底下（375×812 量過）；只有分頁的才帶這個鍵（跟說書人的框一樣）。"""
    from .guide import pending_line

    who = recruiter(state, content)
    if who is None:
        return None
    p = state.player
    if active(state, content):
        i = p.enlist_step
        step = _steps(content)[i]
        blocked = pending_line(state, content)
        paragraphs = _texts(who, i)
        sentence = how_here(state, content, enabled) if step.done_when.action == "order" and blocked is None else ""
        if sentence:  # 第一道軍令那一步：框上多一句，指出你腳下這裡做得了什麼（FB-093）；接在同一段後面，不分頁
            paragraphs[-1] = paragraphs[-1].rstrip("。") + "。" + sentence
        box = {
            "speaker": who.name, "key": step.id, "scene": "", "text": blocked or "\n\n".join(paragraphs),
            "line": "" if blocked else (who.lines[i] if i < len(who.lines) else ""),
            "done": list(p.guide_done), "end": False, "pending": blocked is not None, "full": True,
        }
        if step.glow:  # 這一步要按的鈕發光（FB-093）；網頁只亮畫面上真的有、按得下去的那顆
            box["glow"] = list(step.glow)
        if len(paragraphs) > 1 and blocked is None:
            box["paged"] = True
        return box
    if p.enlist_end:
        return {
            "speaker": who.name, "key": "enlist_end", "scene": "", "text": who.done, "line": "", "done": list(p.guide_done),
            "end": True, "pending": False, "full": True,
        }
    return None
