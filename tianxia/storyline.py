"""一條線（特殊事件與特殊頓悟的底座；企劃者 2026-10-26，特殊事件設計稿「一條線」）。

一條線是一串段（StoryStage）：事件、答題、打一場、等一件事做成。每一段走完照這條線自己記下的記號（marks）往下一段或某一個結局；
段可以有期限（這一季的遊戲日，照季長），過了往 late。結局一定寫進傳（annals.STORY），失敗的也寫；季末還沒收的寫「此事未了」。

線有兩種來源：
- 內容寫的（content/storylines.json）：在 start.where 做得了的地方探索，條件成立、擲中 start.chance 就開（Game._explore_one）。
- 程式組的（start(...)）：特殊頓悟這種在跑的時候才決定內容的線，整份 StoryDef 存在進度裡（StoryProgress.custom）。

同時開著幾條照 kind 分開算（Config.jianfa.story_caps）。各種類可以掛鉤子（照 StoryDef.kind 登記）：
- FIGHT_HOOKS[kind](state, content, progress, stage, record)：fight 段打完那一下（贏輸都叫），記號自己寫進 progress.marks。
- END_HOOKS[kind](state, content, world, progress, ending) -> list[str]：收在任何一個結局那一下（失敗與季末未了也叫；
  季末未了時 ending 是 None）。回的話接在收尾那幾句後面。
- TASKS[name](state, content, world, progress, stage) -> bool：task 段寫了 task 這個名字時，回真就算做成。

規則掛在 Config.jianfa.storylines（rules.jianfa）：關著時內容寫的線不開、start 回空的、已經開了的線也不往下走。
所有擲骰用呼叫端給的亂數，引擎不讀時鐘：時間一律是 state.world.time。

長篇奇事（企劃者 2026-10-27「寫入人心的那種」）多的幾樣：
- 文字照記號換段落（vary）：{?線.記號:有記的寫這段|沒記的寫這段}、{!線.記號:沒記才寫}，可以巢狀；{said:線} 是這條線裡自己寫的第一句話
  （{said:線.1} 第二句）。事件本文、選項結果、卡、結局、傳都經過 rules.fill_marks，所以哪裡都能寫。
- 多日段（StoryStage.wait_days）：進段之後再過幾天才按得下去。
- 餘波（StoryEnding.after）：收了之後過幾天、人走到某地，跳一張卡。
- 紀念物（StoryStep.keepsake、StoryEnding.keepsakes）與跨季旗標（StoryEnding.lasting），換季時跟著角色。
"""

from __future__ import annotations

import re
from collections.abc import Callable

from . import annals, calendar
from .atlas import region_of
from .models import Content, StoryDef, StoryEnding, StoryPlace, StoryStage
from .rules import apply_effect, check_condition, day_seconds, fill_marks, jianfa
from .state import GameState, StoryCard, StoryProgress
from .world_state import WorldStateStore

UNFINISHED = "未了"  # StoryProgress.ending：季末還沒收
OPTION = "story"  # 選單的 id 開頭：story:<線>、story:<線>:a<答案>、story:<線>:later
LATER = "later"
PENDING_HEAD = "未了之事"  # 選單與「你這一步」那一行的開頭（待 joy 潤）
RETRY_NOTE = "（再等 {left}才能再試）"
RETRY_SOON = "（再等一下就能再試）"  # 剩不到一分鐘  # fight 段打輸了還沒到再試的時候；{left} 照 retry_at 算（待 joy 潤）
WAIT_NOTE = "（還要 {left}）"  # task 段要等時間的那幾種：還要多久（待 joy 潤）
WAIT_SOON = "（就快了）"  # 剩不到一分鐘
# task 段「還要等多久」的鉤子（StoryStage.task → 一個函式，回還差幾世界秒，到了或不是這一種回 None）：
# task 段沒有鈕、要去做別的事，但靠時間的那幾種（例：頓悟的小試「靜候」）玩家看不出還要多久，
# 不寫倒數的話看起來就是卡住了（FB-902）。靠動作的那幾種（打贏一場、靜坐、探訪）不註冊，只寫 hint。
TASK_LEFT: dict[str, Callable[[GameState, Content, StoryProgress], float | None]] = {}


def task_note(state: GameState, content: Content, progress: StoryProgress, stage: StoryStage) -> str:
    """task 段那一行後面的倒數（沒有鉤子、或已經到了就是空字串）。世界秒 ÷ time_scale 才是玩家感覺到的時間。"""
    hook = TASK_LEFT.get(stage.task or "")
    left = hook(state, content, progress) if hook is not None else None
    if left is None:
        return ""
    real = max(0.0, left) / (content.config.time_scale or 1.0)
    return WAIT_SOON if real <= 60 else WAIT_NOTE.format(left=calendar.span_text(real))


def retry_note(state: GameState, content: Content, progress: StoryProgress) -> str:
    """還要等多久才能再打那一場（給玩家看的字）。以前這一句是寫死的「一個時辰」，照 StoryStage.retry_days
    的預設 1/12 寫；心魔那一關用 Config.epiphany.retry_days 覆蓋它（曾經是 1.0＝一整天），字就騙人
    （FB-900）。現在照 retry_at 算，怎麼調都對。世界秒 ÷ time_scale 才是玩家感覺到的時間。"""
    left = (progress.retry_at or 0) - state.world.time
    scale = content.config.time_scale or 1.0
    real = max(0.0, left) / scale
    if real <= 60:
        return RETRY_SOON
    return RETRY_NOTE.format(left=calendar.span_text(real))
LATER_LABEL = "先擱著"  # 答題答到一半先走（待 joy 潤）
JOURNAL = "奇事"  # 同步時往下走的那幾句另起一則江湖紀錄的標題（待 joy 潤）

AFTER_JOURNAL = "後來"  # 餘波那一則江湖紀錄與卡的標題開頭
_VARY = re.compile(r"\{([?!])([^{}:.]+)\.([^{}:]+):")
_SAID = re.compile(r"\{said:([^{}.]+)(?:\.(-?\d+))?\}")

FightHook = Callable[..., None]
EndHook = Callable[..., list[str]]
TaskCheck = Callable[..., bool]
FIGHT_HOOKS: dict[str, FightHook] = {}
END_HOOKS: dict[str, EndHook] = {}
TASKS: dict[str, TaskCheck] = {}


def on(content: Content, state: GameState) -> bool:
    return jianfa(content, state.world, "storylines")


# 程式組的線每次讀出來要照設定重算的數字（kind → 一個函式，拿 content 與那一份 StoryDef，回新的）：
# custom 的線把整個定義存進存檔（progress.custom），不這樣做的話改了設定只對之後新開的線有效
# （線上踩到：心魔的 retry_days 從一天改成一個時辰、削弱也加了，正在走的人卻完全沒吃到）。
REFRESH_HOOKS: dict[str, Callable[[Content, StoryDef], StoryDef]] = {}


def definition(content: Content, progress: StoryProgress) -> StoryDef | None:
    if progress.custom is None:
        return content.storylines.get(progress.line)
    refresh = REFRESH_HOOKS.get(progress.custom.kind)
    return refresh(content, progress.custom) if refresh is not None else progress.custom


def active(state: GameState) -> list[StoryProgress]:
    """還沒收的線（照開的順序）。"""
    return [pr for pr in state.player.storylines.values() if pr.ending is None]


def room(state: GameState, content: Content, kind: str) -> bool:
    """這一種還能再開一條嗎（Config.jianfa.story_caps；沒列的種類不限）。"""
    cap = content.config.jianfa.story_caps.get(kind)
    if cap is None:
        return True
    return sum(1 for pr in active(state) if (d := definition(content, pr)) is not None and d.kind == kind) < cap


def here(state: GameState, content: Content, place: StoryPlace) -> bool:
    """人此刻站在這個地方嗎（在路上一律不算；三樣都空的是哪裡都行）。"""
    p = state.player
    if p.location is None or p.journey is not None:
        return False
    if place.empty():
        return True
    loc = content.locations[p.location]
    if loc.id in place.locations or set(loc.tags) & set(place.tags):
        return True
    region = region_of(content, loc.id) if place.regions else None
    return region is not None and region.id in place.regions


# ── 照記號換段落 ──────────────────────────────────────────

def _close_brace(text: str, start: int) -> int:
    """text[start] 之後第一個沒配對的 }（巢狀的 {…} 跳過）；沒有是 -1。"""
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            if depth == 0:
                return i
            depth -= 1
    return -1


def _split_else(body: str) -> tuple[str, str]:
    """「有記的|沒記的」：只認最外層的 |。"""
    depth = 0
    for i, ch in enumerate(body):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
        elif ch == "|" and depth == 0:
            return body[:i], body[i + 1:]
    return body, ""


def vary(text: str, state: GameState, marks: dict[str, dict[str, int]] | None = None) -> str:
    """{?線.記號:A|B}、{!線.記號:A}、{said:線}（模組說明）。marks 給了就用它（線 id → 記號），否則讀這個人的進度；
    「說」是虛擬的記號：這條線裡寫過話就算有。寫壞的（沒有收尾的 }）原樣留著。"""
    def has(line: str, mark: str) -> bool:
        if marks is not None and line in marks:
            got = marks[line]
        else:
            progress = state.player.storylines.get(line)
            if progress is None:
                return False
            got = dict(progress.marks)
            if progress.said:
                got["說"] = 1
        return got.get(mark, 0) > 0

    out, pos = [], 0
    while (m := _VARY.search(text, pos)) is not None:
        end = _close_brace(text, m.end())
        if end < 0:
            break
        out.append(text[pos:m.start()])
        yes, no = _split_else(text[m.end():end])
        hit = has(m.group(2), m.group(3))
        out.append(vary(yes if hit == (m.group(1) == "?") else no, state, marks))
        pos = end + 1
    out.append(text[pos:])
    text = "".join(out)

    def said(m: re.Match) -> str:
        progress = state.player.storylines.get(m.group(1))
        n = int(m.group(2) or 0)
        return progress.said[n] if progress is not None and -len(progress.said) <= n < len(progress.said) else ""

    return _SAID.sub(said, text)


# ── 開頭 ──────────────────────────────────────────────

def roll_start(state: GameState, content: Content, rng) -> StoryDef | None:
    """探索那一下擲內容寫的線（Game._explore_one）：這一季還沒開過、站在開頭的地方、條件成立、這一種還有空位，照檔案順序各擲一次，
    第一個擲中的就是這一趟。關著、一條都沒有是 None（不動 rng）。"""
    if not on(content, state) or not content.storylines:
        return None
    for line in content.storylines.values():
        start = line.start
        if start is None or line.id in state.player.storylines or not room(state, content, line.kind):
            continue
        if not here(state, content, start.where) or not check_condition(start.condition, state, content):
            continue
        if rng.random() < start.chance:
            return line
    return None


def start(state: GameState, content: Content, line: StoryDef, custom: bool = True) -> StoryProgress | None:
    """開一條線：進第一段、排一張開頭的卡。custom 是程式組的線（整份 StoryDef 存進進度；內容寫的線由 roll_start 擲中後給 False）。
    關著、這一季開過同一條、這一種沒有空位都是 None。第一段是事件而且人就在那裡時，由呼叫端端出來（ready_event）。"""
    p = state.player
    if not on(content, state) or line.id in p.storylines or not room(state, content, line.kind):
        return None
    progress = StoryProgress(line=line.id, started=state.world.time, custom=line if custom else None)
    p.storylines[line.id] = progress
    p.story_cards.append(StoryCard(line=line.id, kind="start", title=line.title, text=fill_marks(line.intro, state), image=line.image))
    _enter(state, content, progress, line, line.stages[0].id)  # 第一段若有段落卡，排在開頭那張後面
    return progress


def _enter(state: GameState, content: Content, progress: StoryProgress, line: StoryDef, stage_id: str) -> None:
    stage = line.stage(stage_id)
    progress.stage, progress.opened, progress.go = stage_id, False, None
    progress.tries, progress.retry_at, progress.step = 0, None, 0
    progress.entered = state.world.time
    wait = stage.wait_days * day_seconds(content, state.world)
    progress.due = None if stage.days is None else state.world.time + wait + stage.days * day_seconds(content, state.world)
    if stage.card:
        state.player.story_cards.append(StoryCard(line=line.id, kind="stage", title=line.title, text=fill_marks(stage.card, state),
                                                  image=stage.image))


# ── 這一段做得了嗎、選單 ──────────────────────────────────

def current(content: Content, progress: StoryProgress) -> tuple[StoryDef, StoryStage] | None:
    line = definition(content, progress)
    if line is None or progress.ending is not None:
        return None
    stage = line.stage(progress.stage)
    return None if stage is None else (line, stage)


def stage_art(state: GameState, content: Content) -> str | None:
    """眼前端出來的事件是某條線事件段的那一則（含它接下去的 next_event）、那一段寫了 image 時，場景卡用那張專屬圖
    （Game.scene_art；web/img/<image>.webp）。沒有是 None，場景卡照事件自己的類型圖。"""
    for progress in active(state):
        pair = current(content, progress)
        if pair is not None and progress.opened and pair[1].kind == "event" and pair[1].image:
            return pair[1].image
    return None


def waiting(state: GameState, content: Content, progress: StoryProgress, stage: StoryStage) -> bool:
    """多日段還沒到時候（StoryStage.wait_days）。"""
    if not stage.wait_days or progress.entered is None:
        return False
    return state.world.time < progress.entered + stage.wait_days * day_seconds(content, state.world)


def doable(state: GameState, content: Content, progress: StoryProgress) -> bool:
    """這一段此刻在這裡按得下去：event、quiz、fight 才有鈕（task 是去做別的事），還沒端出來、等完了、站在對的地方。"""
    pair = current(content, progress)
    if pair is None or progress.opened:
        return False
    _, stage = pair
    return stage.kind != "task" and not waiting(state, content, progress, stage) and here(state, content, stage.where)


def ready_event(state: GameState, content: Content) -> str | None:
    """剛進的那一段是事件、寫了 immediate、人就站在那裡：要直接端出來的事件 id（一次一則）。"""
    for progress in active(state):
        pair = current(content, progress)
        if pair is None or progress.opened:
            continue
        _, stage = pair
        if stage.kind == "event" and stage.immediate and not waiting(state, content, progress, stage) and here(state, content, stage.where):
            progress.opened = True
            return stage.event
    return None


def label(content: Content, progress: StoryProgress) -> str:
    line, stage = current(content, progress)
    return f"{PENDING_HEAD}：{line.title}" + (f"・{stage.hint}" if stage.hint else "")


def options(state: GameState, content: Content) -> list[tuple[str, str, bool]]:
    """地點上的選單多的那幾顆（不花體力）：每一條此刻做得了的線一顆。fight 段打輸了還沒到再試的時候灰掉。"""
    if not on(content, state):
        return []
    out = []
    for progress in active(state):
        pair = current(content, progress)
        if pair is None or progress.opened:
            continue
        _, stage = pair
        if stage.kind == "task":
            # task 段沒有鈕（要去做別的事），但**灰著列一行**：不列的話玩家完全看不到自己卡在哪一步，
            # 整條線從他那邊看就是消失了（FB-902，上班想下班停在小試「靜候」一天什麼都看不到）。
            # 灰的選項引擎本來就擋（choose 的 not option.enabled → 「此刻無法這麼做」），假人也只挑亮的
            out.append((f"{OPTION}:{progress.line}",
                        label(content, progress) + task_note(state, content, progress, stage), False))
            continue
        if not doable(state, content, progress):
            continue
        waiting = stage.kind == "fight" and progress.retry_at is not None and state.world.time < progress.retry_at
        note = retry_note(state, content, progress) if waiting else ""
        out.append((f"{OPTION}:{progress.line}", label(content, progress) + note, not waiting))
    return out


def pending_lines(state: GameState, content: Content) -> list[dict]:
    """還沒收的線（「你這一步」的金色那一行、奇事分頁用）：線名、這一步要做什麼、期限（世界秒）、此刻在不在做得了的地方。"""
    if not on(content, state):
        return []
    out = []
    for progress in active(state):
        pair = current(content, progress)
        if pair is None:
            continue
        line, stage = pair
        out.append({"line": line.id, "title": line.title, "kind": line.kind, "hint": stage.hint, "due": progress.due,
                    "here": doable(state, content, progress), "image": line.image,
                    "wait": waiting(state, content, progress, stage)})
    return out


# ── 答題（quiz）──────────────────────────────────────────

def quiz_menu(state: GameState, content: Content) -> list[tuple[str, str]]:
    progress = state.player.storylines.get(state.player.story_open or "")
    pair = None if progress is None else current(content, progress)
    if pair is None or pair[1].kind != "quiz":
        return []
    question = pair[1].questions[progress.step]
    return [(f"{OPTION}:{progress.line}:a{i}", a.text) for i, a in enumerate(question.answers)] + [
        (f"{OPTION}:{progress.line}:{LATER}", LATER_LABEL),
    ]


def question_text(state: GameState, content: Content) -> str | None:
    progress = state.player.storylines.get(state.player.story_open or "")
    pair = None if progress is None else current(content, progress)
    if pair is None or pair[1].kind != "quiz":
        return None
    return fill_marks(pair[1].questions[progress.step].text, state)


def open_quiz(state: GameState, content: Content, progress: StoryProgress) -> list[str]:
    state.player.story_open = progress.line
    progress.opened = True
    return [question_text(state, content)]


def answer(state: GameState, content: Content, line_id: str, arg: str) -> list[str]:
    """答一題（a<答案序號>）或先擱著（later：這一段留著，下次按那一顆從這一題接著答）。答完最後一題這一段就走完，照 routes／next。"""
    p = state.player
    progress = p.storylines.get(line_id)
    pair = None if progress is None else current(content, progress)
    if pair is None or pair[1].kind != "quiz":
        p.story_open = None
        return []
    _, stage = pair
    if arg == LATER:
        p.story_open, progress.opened = None, False
        return []
    chosen = stage.questions[progress.step].answers[int(arg.removeprefix("a"))]
    _add_marks(progress, chosen.marks)
    progress.step += 1
    msgs = [f"▸ {chosen.text}"]
    if progress.step < len(stage.questions):
        return msgs + [question_text(state, content)]
    p.story_open = None
    progress.go = route(stage, progress)
    return msgs


# ── 打一場（fight）──────────────────────────────────────

def wait_text(days: float) -> str:
    """「過多久」寫給玩家看的那一截：一天以上寫「N 天」，不到一天寫「N 個時辰」（一天十二個時辰，至少一個）。"""
    if days >= 1:
        return f"{round(days, 1):g} 天"
    return f"{max(1, round(days * 12))} 個時辰"


def fought(state: GameState, content: Content, progress: StoryProgress, won: bool, record) -> list[str]:
    """fight 段打完那一下（Game._story_fight）：先叫這一種的 fight 鉤子寫記號；贏了往 win，輸了算一次，輸滿 retries 次往 lose，
    沒滿就過 retry_days 才能再打——那一段寫了 fail 時跳一張卡、記一行行狀，回江湖紀錄那一行（其餘回空的）。"""
    line, stage = current(content, progress)
    hook = FIGHT_HOOKS.get(line.kind)
    if hook is not None:
        hook(state, content, progress, stage, record)
    progress.opened = False
    if won:
        progress.go = stage.win
        return []
    progress.tries += 1
    if progress.tries >= stage.retries:
        progress.go = stage.lose
        return []
    progress.retry_at = state.world.time + stage.retry_days * day_seconds(content, state.world)
    fail = stage.fail
    if fail is None:
        return []
    days = wait_text(stage.retry_days)
    state.player.story_cards.append(StoryCard(line=line.id, kind="retry", title=fail.title, text=fill_marks(fail.card.replace("{days}", days), state),
                                              image=fail.image, failed=True))
    annals.note(state, content, annals.STORY, fail.annal.replace("{name}", state.player.name), 1)
    return [fail.log.replace("{days}", days)] if fail.log else []


# ── 效果與自己寫的話 ─────────────────────────────────────

def _add_marks(progress: StoryProgress, marks: dict[str, int]) -> None:
    for key, value in marks.items():
        progress.marks[key] = progress.marks.get(key, 0) + value


def heard(state: GameState, content: Content, event_id: str, text: str) -> None:
    """隨口應對寫的那一句：眼前這一則是哪一條線端出來的段落，就記進那條線的 said（結尾與模型用）。"""
    for progress in active(state):
        pair = current(content, progress)
        if pair is not None and progress.opened and pair[1].kind == "event":  # 段落事件或它串接下去的（next_event）都算
            progress.said.append(text)
            return


def route(stage: StoryStage, progress: StoryProgress) -> str | None:
    """這一段走完往哪裡：routes 照順序第一個記號都到了的，都不成立是 next。"""
    for r in stage.routes:
        if all(progress.marks.get(k, 0) >= v for k, v in r.when.items()):
            return r.go
    return stage.next


# ── 結算（每個動作之後、同步時）──────────────────────────────

def tick(state: GameState, content: Content, world: WorldStateStore) -> tuple[list[str], str | None]:
    """把每一條還沒收的線往前推：事件段了結了（眼前沒有事件）、答題答完、打完，照記下的那一步走；task 段的事做成了往下；
    期限過了往 late；休季了還沒收的收成「此事未了」。回 (要說的話, 要端出來的事件 id)。關著時什麼都不做。"""
    if not on(content, state):
        return [], None
    msgs: list[str] = aftermath(state, content)
    for progress in active(state):
        line = definition(content, progress)
        if line is None:
            continue
        if state.world.ended:
            msgs += close(state, content, world, progress, line)
            continue
        for _ in range(len(line.stages) + 1):  # 一下最多走過每一段一次（task 接 task 都成立時不會無限走）
            target = _next_step(state, content, world, progress, line)
            if target is None:
                break
            msgs += _advance(state, content, world, progress, line, target)
            if progress.ending is not None:
                break
    return msgs, ready_event(state, content) if state.pending_event is None else None


def _next_step(state: GameState, content: Content, world: WorldStateStore, progress: StoryProgress, line: StoryDef) -> str | None:
    stage = line.stage(progress.stage)
    if stage is None:
        return None
    if progress.go is not None:
        return progress.go
    if stage.kind == "event" and progress.opened and state.pending_event is None:  # 事件了結了，選項沒寫往哪裡：照 routes／next
        return route(stage, progress) or stage.late
    if progress.due is not None and state.world.time >= progress.due and not progress.opened:
        return stage.late
    if stage.kind == "task":
        check = TASKS.get(stage.task or "")
        done = (stage.until is not None and check_condition(stage.until, state, content)) or (
            check is not None and check(state, content, world, progress, stage))
        return route(stage, progress) if done else None
    return None


def _advance(state: GameState, content: Content, world: WorldStateStore, progress: StoryProgress, line: StoryDef, target: str) -> list[str]:
    ending = line.ending(target)
    if ending is not None:
        return finish(state, content, world, progress, line, ending)
    _enter(state, content, progress, line, target)
    return []


def finish(state: GameState, content: Content, world: WorldStateStore, progress: StoryProgress, line: StoryDef,
           ending: StoryEnding) -> list[str]:
    """收在一個結局：給結局的東西、寫進傳、排一張入傳的卡、叫這一種的收尾鉤子。"""
    p = state.player
    text = fill_marks(ending.text, state)  # 還沒收之前換段落（記號、寫過的話都還讀得到）
    annal = fill_marks(ending.annal, state).replace("{name}", p.name)
    progress.ending, progress.stage, progress.go, progress.due = ending.id, "", None, None
    progress.ended_at = state.world.time
    if p.story_open == progress.line:
        p.story_open = None
    msgs = [text] + apply_effect(ending.effect, state, content, world)
    for item in ending.keepsakes:
        if item not in p.keepsakes:
            p.keepsakes.append(item)
            msgs.append(f"（收進行囊：{item}）")
    for flag in ending.lasting:
        p.flags.add(flag)
        if flag not in p.lasting:
            p.lasting.append(flag)
    annals.note(state, content, annals.STORY, annal, ending.weight)
    p.story_cards.append(StoryCard(
        line=line.id, kind="end", title=line.title, text=text, image=ending.image or line.image,
        ending=ending.title, failed=ending.failed,
    ))
    hook = END_HOOKS.get(line.kind)
    return msgs + (hook(state, content, world, progress, ending) if hook is not None else [])


def aftermath(state: GameState, content: Content) -> list[str]:
    """收了的線的餘波（StoryEnding.after）：時候到了、人站在那裡、記號對得上，跳一張卡（kind="after"），回要記進江湖紀錄的那幾句。
    過了 within 的記成看過（不再出現）。一次同步每條線最多跳一段。"""
    msgs: list[str] = []
    p, now = state.player, state.world.time
    for progress in p.storylines.values():
        if progress.ending is None or progress.ending == UNFINISHED or progress.ended_at is None:
            continue
        line = definition(content, progress)
        ending = None if line is None else line.ending(progress.ending)
        if ending is None:
            continue
        day = day_seconds(content, state.world)
        for i, beat in enumerate(ending.after):
            if i in progress.after_seen or now < progress.ended_at + beat.days * day:
                continue
            if beat.within is not None and now > progress.ended_at + (beat.days + beat.within) * day:
                progress.after_seen.append(i)
                continue
            if any(progress.marks.get(k, 0) < v for k, v in beat.when.items()):
                progress.after_seen.append(i)
                continue
            if not here(state, content, beat.where):
                continue
            progress.after_seen.append(i)
            text = vary(fill_marks(beat.text, state), state, {line.id: _marks_with_said(progress)})
            title = beat.title or f"{AFTER_JOURNAL}・{line.title}"
            p.story_cards.append(StoryCard(line=line.id, kind="after", title=line.title, text=text, image=beat.image or ending.image or line.image,
                                           ending=beat.title))
            if beat.keepsake_drop in p.keepsakes:
                p.keepsakes.remove(beat.keepsake_drop)
            msgs += [f"【{title}】", text]
            break
    return msgs


def _marks_with_said(progress: StoryProgress) -> dict[str, int]:
    got = dict(progress.marks)
    if progress.said:
        got["說"] = 1
    return got


def close(state: GameState, content: Content, world: WorldStateStore | None, progress: StoryProgress, line: StoryDef,
          card: bool = True) -> list[str]:
    """季末還沒收：寫一則「此事未了」進傳（份量 3），排一張此事未了的卡，收尾鉤子拿到的結局是 None。"""
    p = state.player
    progress.ending, progress.go, progress.due = UNFINISHED, None, None
    if p.story_open == progress.line:
        p.story_open = None
    annals.note(state, content, annals.STORY, line.unfinished.replace("{name}", p.name), 3)
    if card:
        p.story_cards.append(StoryCard(line=line.id, kind="unfinished", title=line.title, text=line.unfinished.replace("{name}", p.name),
                                       image=line.image))
    hook = END_HOOKS.get(line.kind)
    return hook(state, content, world, progress, None) if hook is not None else []


def close_season(state: GameState, content: Content) -> None:
    """換季那一刻（Game._reset_player_for_new_season，存上一季的行狀之前）：還沒收的線一律寫「此事未了」（不排卡、鉤子拿不到資料庫）。
    關著的季也照寫：線是開著的季開的，傳要記得。"""
    for progress in active(state):
        line = definition(content, progress)
        if line is not None:
            close(state, content, None, progress, line, card=False)


def seen(state: GameState) -> None:
    """跳出來的卡看過了：清掉。"""
    state.player.story_cards = []
