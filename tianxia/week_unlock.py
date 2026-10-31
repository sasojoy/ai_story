"""功能照週解鎖與三週主題（減法季整合設計 6.6、6.8；批 5）：只讀、只組字，不改狀態、不擲骰。

- 這一季走到前、中、後哪一段（`phase`、`phase_now`）：21 天季是第幾週，7 天的季是第幾段（季曆本來就分三段 [2, 2, 3]），
  週末式的十二週照比例切。本週卡的主題句（Scenario.week_themes）、功能解鎖、第 3 週那一句都照它。
- 第 2 週才開的功能（`WEEK2`：擂台、懸賞榜；鐵匠鋪 2026-10-27、自創 2026-10-28 起開季就有）：第 1 週的探索、出陣、交友、移動、此地（醫館、酒肆）、鐵匠鋪、自創、商城照舊開季就有。
  `open(state, content, feature)`：規則關著（`rules.jianfa(..., "week_unlock")` 是假：總開關、這一季的章、子開關任一個關著）一律開、一個字都不變；
  開著時要這一季走到第 2 段**而且**自己的新手期過了（roster.newbie，Config.newbie_real_hours 48 小時從自己加入那一刻算）——
  「新手期內照自己的時鐘開」（6.6）：第 2 週才來的人也先有兩天只做第 1 週的事，不是一進來什麼都有。
  入口（arena.here、bounties.board_here）各自問它；假人走同一條（bot.py 問的是同幾個入口）。
- 開了的那一刻（Game._week_unlock_tick）江湖紀錄一行（`JOURNAL`）、本週卡一句（`CARD`，開了之後一個季曆天內寫）；還沒開的本週卡
  「為什麼」裡寫哪幾樣第 2 週開（`LOCKED`）。
- 第 3 週「離贏還差多少」（`win_gap`）：要主機側批 3c 的勝利條件數字（官軍離平定還差 12、黃巾離當立還差 28），先留位、
  用現有的結局門檻那一句（rules.stance_rule_note）頂著；本週卡與輿圖天下層寫同一句。
- 45 級之後那一句（`cap_note`，設計 4.2）：三道閘開著、本人到了 drill_level_cap（45）寫「境界已到，再往上只能打出來」；
  批 2 接上之後給經驗的段落結尾也寫同一句（同一個常數）。drill_level_cap 現在在主機側批 2 的 jianfa_numbers，Config.jianfa 還沒有，
  先照它的預設（`cap_level`）。
字待 joy 潤。
"""
from __future__ import annotations

from . import calendar, rules
from .models import Content
from .state import GameState, WorldState

# 第 2 段才開的功能（設計 6.6、6.8）：入口的鍵 → 寫給玩家看的名字（紀錄那一行、本週卡那一句照這個順序列）
WEEK2 = {"arena": "擂台", "bounties": "懸賞榜"}  # 鐵匠鋪不鎖（企劃者 2026-10-27「把鐵匠放回來」）；自創不鎖（企劃者 2026-10-28「開季就有」）
STAGE = {k: 1 for k in WEEK2}  # 哪一段（0 起）開；不在表上的功能是 0（開季就有）

TITLE = "江湖新事"  # 開了那一則江湖紀錄的標題。待 joy 潤
JOURNAL = "{when}起，{names}開了。"  # 待 joy 潤：when 是「第 2 週」／「第 2 段」；新手期過了才開的人也寫這一週
CARD = "{names}開了。"  # 本週卡那一句（開了之後一個季曆天內）。待 joy 潤
LOCKED = "{names}：{when}起開（新手期過了）。"  # 還沒開的本週卡「為什麼」。待 joy 潤
CAP_NOTE = "境界已到，再往上只能打出來。"  # 45 級之後那一句（設計 4.2）。待 joy 潤
CARD_DAYS = 1.0  # 開了之後本週卡那一句寫幾個季曆天
DEFAULT_CAP_LEVEL = 45  # jianfa_numbers.JianfaNumbers.drill_level_cap 的預設；Config.jianfa 接上那個數字之前先照它


def phase(week: int, weeks: int) -> int:
    """這一季走到前、中、後哪一段（0、1、2）：21 天季是第幾週，7 天的季是第幾段（季曆本來就分三段），週末式的十二週照比例切。"""
    return max(0, min(2, (week - 1) * 3 // max(1, weeks)))


def weeks_of(content: Content, world: WorldState | None) -> int:
    """這一季的季曆分幾週（7 天的季是幾段）：phase 的分母。"""
    return len(content.config.season_segments) if calendar.week7_on(world, content) else calendar.weeks(content, world)


def phase_now(state: GameState, content: Content) -> int:
    """此刻走到哪一段。沒有季曆的季（第一季規則關著的 beta）當最後一段：什麼都不鎖。"""
    w = state.world
    if not rules.season_one(content, w):
        return 2
    return phase(calendar.point(w.time, content, w).week, weeks_of(content, w))


def stage_label(stage: int, content: Content, world: WorldState | None) -> str:
    """第幾段的寫法：「第 2 週」、7 天的季「第 2 段」。"""
    return f"第 {stage + 1} {'段' if calendar.week7_on(world, content) else '週'}"


def on(content: Content, world: WorldState | None) -> bool:
    return rules.jianfa(content, world, "week_unlock")


def own_clock_done(state: GameState, content: Content) -> bool:
    """自己的新手期過了（roster.newbie：newbie_real_hours 從 joined_at 算；沒設照 newbie_days 的季曆天）。"""
    from . import roster  # roster 與 rules 互相 import，呼叫時才取

    return not roster.newbie(state, content)


def open(state: GameState, content: Content, feature: str) -> bool:  # 入口都寫 week_unlock.open(...)
    """這個功能此刻開了沒：規則關著一律開；開著要走到那一段、而且自己的新手期過了。季收了不在這裡管（各入口自己看 ended）。"""
    stage = STAGE.get(feature, 0)
    if stage == 0 or not on(content, state.world):
        return True
    return phase_now(state, content) >= stage and own_clock_done(state, content)


def unlocked_now(state: GameState, content: Content) -> bool:
    """第 2 段的功能此刻全開了（都掛同一段、同一個時鐘，問一個就夠）。規則關著是假：不寫紀錄、不寫那一句。"""
    return on(content, state.world) and open(state, content, "arena")


def journal_line(names: list[str], content: Content, world: WorldState | None) -> str:
    return JOURNAL.format(when=stage_label(1, content, world), names="、".join(names))


def card_line(state: GameState, content: Content, names: list[str]) -> str | None:
    """本週卡那一句：開了之後 CARD_DAYS 個季曆天內寫，之後不寫。沒開過（None）、沒有一樣功能是開著的（names 空）也不寫。"""
    at = state.player.week_unlocked_at
    if at is None or not names:
        return None
    w = state.world
    if (w.time - at) * calendar.cal_scale(content, w) > CARD_DAYS * calendar.DAY:
        return None
    return CARD.format(names="、".join(names))


def locked_line(state: GameState, content: Content, names: list[str]) -> str | None:
    """還沒開的那一句（本週卡「為什麼」）：規則開著、第 2 段的功能還鎖著、有東西可開才寫。"""
    if not names or not on(content, state.world) or open(state, content, "arena"):
        return None
    return LOCKED.format(names="、".join(names), when=stage_label(1, content, state.world))


def cap_level(content: Content) -> int:
    """45 級那一道閘的等級：Config.jianfa 接上 drill_level_cap 之前照批 2 的預設。"""
    return int(getattr(content.config.jianfa, "drill_level_cap", DEFAULT_CAP_LEVEL))


def cap_note(state: GameState, content: Content) -> str | None:
    """45 級之後那一句：三道閘開著（rules.jianfa "drill_gates"）、本人到了 cap_level 才寫。"""
    if not rules.jianfa(content, state.world, "drill_gates") or state.player.member.level < cap_level(content):
        return None
    return CAP_NOTE


def win_gap(state: GameState, content: Content) -> str | None:
    """第 3 段「離贏還差多少」：留位——批 3c 的勝利條件數字接上之前用結局門檻那一句頂著（rules.stance_rule_note）；
    不是第 3 段、沒有季曆、那一句是空的都是 None。"""
    if not rules.season_one(content, state.world) or phase_now(state, content) < 2:
        return None
    if rules.jianfa(content, state.world):  # 批 3c 接上了：兩軍各自離勝利條件還差多少（wins.gap_line）
        from . import wins  # noqa: PLC0415  wins → rules：延後 import，這個模組照舊只在載入時依賴 calendar、rules

        return wins.gap_line(content, rules.stances(state, content)) or None
    return rules.stance_rule_note(state, content) or None
