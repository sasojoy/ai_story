"""一條線的底座與換字（共用規則層；全部拆包第 30 批，一條線搬進 tianxia/features/story/）。

從 storyline.py 原樣搬來的那一半（逐行，一行不改）：別的包與核心也要讀的——
- 核心：rules.fill_marks 換字（vary）、事件檢定記自己寫的那一句（heard）、Game 讀的幾個常數與場景圖、題目文字；
- 探索包：探索那一下擲內容寫的線（roll_start）；
- 有所感包：頓悟那一條線的鉤子登記（TASKS、TASK_LEFT、REFRESH_HOOKS、FIGHT_HOOKS、END_HOOKS）與開線、開第一題（start、open_quiz、definition、active、on）。
一條線自己的走法（選單、答題、打一場、結算、收尾、餘波）在 tianxia/features/story/storyline.py，那一份 re-export 這裡的每一個名字
（tianxia.storyline 是指到那一份的舊名別名）。這一層只 import 核心與兩個還沒搬的舊模組：atlas（here 的大區）、chapters（vary 的大事結果，函式裡）。
"""

from __future__ import annotations

import re
from collections.abc import Callable

from .atlas import region_of
from .models import Content, StoryDef, StoryPlace, StoryStage
from .rules import check_condition, day_seconds, fill_marks, jianfa
from .state import GameState, StoryCard, StoryProgress

WORLD = "世"  # vary 的虛擬線名：{?世.<世界旗標>:有|沒有}
HISTORY = "史"  # vary 的虛擬線名：{?史.<大事 id>=<結果>:…}（結果：成、不成、guan、huang）
OPTION = "story"  # 選單的 id 開頭：story:<線>、story:<線>:a<答案>、story:<線>:later
JOURNAL = "奇事"  # 同步時往下走的那幾句另起一則江湖紀錄的標題（待 joy 潤）
_VARY = re.compile(r"\{([?!])([^{}:.]+)\.([^{}:]+):")
_SAID = re.compile(r"\{said:([^{}.]+)(?:\.(-?\d+))?\}")

# task 段「還要等多久」的鉤子（StoryStage.task → 一個函式，回還差幾世界秒，到了或不是這一種回 None）：
# task 段沒有鈕、要去做別的事，但靠時間的那幾種（例：頓悟的小試「靜候」）玩家看不出還要多久，
# 不寫倒數的話看起來就是卡住了（FB-902）。靠動作的那幾種（打贏一場、靜坐、探訪）不註冊，只寫 hint。
TASK_LEFT: dict[str, Callable[[GameState, Content, StoryProgress], float | None]] = {}

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
    """{?線.記號:A|B}、{!線.記號:A}、{said:線}（模組說明）；線名寫「世」讀全服的世界旗標、寫「史」讀時刻表大事的結果。marks 給了就用它（線 id → 記號），否則讀這個人的進度；
    「說」是虛擬的記號：這條線裡寫過話就算有。寫壞的（沒有收尾的 }）原樣留著。"""
    def has(line: str, mark: str) -> bool:
        if line == WORLD:  # {?世.旗標:…}：全服的世界旗標（章回主線：別的陣營的人做了什麼，改這裡怎麼寫）
            return mark in state.world.flags
        if line == HISTORY:  # {?史.大事id=結果:…}：時刻表那一件大事結算成這樣（章回主線；結果照 chapters.outcome_mark 去掉「果」）
            from .chapters import outcome_mark  # noqa: PLC0415  chapters → storyline

            event_id, _, want = mark.partition("=")
            result = state.world.timeline.get(event_id)
            return result is not None and outcome_mark(result.key) == f"果{want}"
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

def roll_start(state: GameState, content: Content, rng, boost: float = 1.0) -> StoryDef | None:
    """探索那一下擲內容寫的線（Game._explore_one）：這一季還沒開過、站在開頭的地方、條件成立、這一種還有空位，照檔案順序各擲一次，
    第一個擲中的就是這一趟。關著、一條都沒有是 None（不動 rng）。boost：走一趟的稀有倍數（outing.rare_boost），乘在每一條的 chance 上。"""
    if not on(content, state) or not content.storylines:
        return None
    for line in content.storylines.values():
        start = line.start
        if start is None or line.id in state.player.storylines or not room(state, content, line.kind):
            continue
        if not here(state, content, start.where) or not check_condition(start.condition, state, content):
            continue
        if rng.random() < start.chance * boost:
            return line
    return None


def start(state: GameState, content: Content, line: StoryDef, custom: bool = True, card: bool = True) -> StoryProgress | None:
    """開一條線：進第一段、排一張開頭的卡（card 關著不排：章回主線開在江湖頁最上面的章回卡上，不另跳一張）。
    custom 是程式組的線（整份 StoryDef 存進進度；內容寫的線由 roll_start 擲中後給 False）。
    關著、這一季開過同一條、這一種沒有空位都是 None。第一段是事件而且人就在那裡時，由呼叫端端出來（ready_event）。"""
    p = state.player
    if not on(content, state) or line.id in p.storylines or not room(state, content, line.kind):
        return None
    progress = StoryProgress(line=line.id, started=state.world.time, custom=line if custom else None)
    p.storylines[line.id] = progress
    if card:
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


def heard(state: GameState, content: Content, event_id: str, text: str) -> None:
    """隨口應對寫的那一句：眼前這一則是哪一條線端出來的段落，就記進那條線的 said（結尾與模型用）。"""
    for progress in active(state):
        pair = current(content, progress)
        if pair is not None and progress.opened and pair[1].kind == "event":  # 段落事件或它串接下去的（next_event）都算
            progress.said.append(text)
            return
