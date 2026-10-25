"""減法季批 4：地方痕跡看得見（整合設計 5.2；主機側計畫 Task 4-3 的純規則那一半）。

痕跡（WorldState.marks，「地點 id:痕跡名」→ 全服累計幾筆；rules.add_marks 記，一個人一個遊戲日一次）以前只有事件條件讀。
這裡讓它看得見：
- fire_due：痕跡規則（content/mark_rules.json，MarkRule）累計到門檻那一刻發一則地方傳聞（不列名字）與世界層一句，寫了 trend 的
  照原本的量推一次線（只有「趕走散兵」那一類，企劃者 2026-10-24 第 8 件 b；一季只發一次，同 source="event_once" 不照季長縮放），
  記在 WorldState.marks_fired，之後不再發；
- describe：地點描寫後面多接一段——地點自己寫的 desc_marks 與過了門檻的痕跡規則一起比，挑門檻最高的那一段（同門檻挑人數多的）；
- xingshi_facts：〈天下形勢〉的事實多一類，上一篇以後過門檻的各一句；
- close_season：江湖史在季末寫（PM 2026-10-25 第 4 件，照整合設計 5.2）——每個地點挑最高的那一條痕跡寫一句。
公開的只有後果與痕跡：傳聞、江湖史、描寫都不帶名字，也不寫玩家寫的句子。

只 import models、rules、state；接線在 engine（Game.location_text、_save_season／sync／world_tick 叫 fire_due、跨過門檻那一刻出過力的人的
行狀 annals.MARK）、xingshi.facts、world.end_season（close_season）。開關是 rules.jianfa(content, world, "marks_visible")。
"""
from __future__ import annotations

from .models import Content, Location, MarkRule
from .rules import add_chronicle, add_rumor, change_trend, jianfa, resolve_trends
from .state import GameState, WorldState


def place_of(mark: str) -> str:
    """痕跡鍵的地點 id（「地點 id:痕跡名」的前半）。"""
    return mark.partition(":")[0]


def due(world: WorldState, content: Content) -> list[MarkRule]:
    """累計到門檻、這一季還沒發過的痕跡規則（照內容的順序）。"""
    return [r for r in content.mark_rules if r.mark not in world.marks_fired and world.marks.get(r.mark, 0) >= r.threshold]


def fire_due(state: GameState, content: Content) -> list[MarkRule]:
    """把過了門檻的痕跡規則各發一次：地方傳聞（記在那個地點、不具名）、世界層一句（xingshi，沒寫照傳聞那一句；〈天下形勢〉也照它）、
    推線（寫了才推，front 是那個地點的戰線；照原本的量、不照季長縮放，同 source="event_once"）。江湖史不在這裡寫：季末才寫
    （close_season，PM 2026-10-25 第 4 件）。回這一次發了哪幾條。推線那一句不回：這是天下的事，不是哪一個人推的（同大勢門檻）。
    開關由呼叫端問（engine 的掛點都先問 rules.jianfa(..., "marks_visible")）。"""
    fired = due(state.world, content)
    for rule in fired:
        state.world.marks_fired[rule.mark] = state.world.time
        place = place_of(rule.mark)
        add_rumor(state, rule.rumor, place, content=content, layer="local", named=False)
        add_rumor(state, rule.xingshi or rule.rumor, place, content=content, layer="world", named=False)
        for trend_id, delta in resolve_trends(content, state.world, rule.trend, place).items():
            change_trend(state, content, trend_id, delta)
    return fired


def season_lines(world: WorldState, content: Content) -> list[str]:
    """季末的江湖史（整合設計 5.2）：每個地點挑最高的那一條痕跡——過了門檻的痕跡規則裡人數最多的（同人數照內容的順序）——各一句
    （chronicle，沒寫照傳聞那一句），照地點在內容裡的順序。都沒過門檻的地點不寫。"""
    best: dict[str, tuple[tuple[int, int], MarkRule]] = {}
    for order, rule in enumerate(content.mark_rules):
        count = world.marks.get(rule.mark, 0)
        if count < rule.threshold:
            continue
        place, key = place_of(rule.mark), (count, -order)
        if place not in best or key > best[place][0]:
            best[place] = (key, rule)
    return [best[loc][1].chronicle or best[loc][1].rumor for loc in content.locations if loc in best]


def close_season(state: GameState, content: Content) -> None:
    """收季那一刻（world.end_season 叫）：痕跡看得見開著的季，把 season_lines 寫進江湖史；關著什麼都不做。"""
    if jianfa(content, state.world, "marks_visible"):
        for line in season_lines(state.world, content):
            add_chronicle(state, line)


def segment(loc: Location, world: WorldState, content: Content) -> str | None:
    """這個地點此刻照痕跡多接的那一段：desc_marks 與這個地點的痕跡規則裡，人數到了門檻的挑門檻最高的（同門檻挑人數多的，再同照內容的順序）；
    都沒到是 None。"""
    candidates = [(text.min, world.marks.get(text.mark, 0), text.text) for text in loc.desc_marks]
    candidates += [
        (rule.threshold, world.marks.get(rule.mark, 0), rule.describe)
        for rule in content.mark_rules if place_of(rule.mark) == loc.id
    ]
    reached = [(need, count, -order, text) for order, (need, count, text) in enumerate(candidates) if count >= need]
    return max(reached)[3] if reached else None


def describe(loc: Location, world: WorldState, content: Content) -> str:
    """地點此刻的描寫（Location.describe 照世界旗標挑的那一版），照痕跡多接的那一段另起一段接在後面；沒有就一個字不變。"""
    base = loc.describe(world.flags)
    extra = segment(loc, world, content)
    return f"{base}\n\n{extra}" if extra else base


def xingshi_facts(world: WorldState, content: Content, since: float) -> list[str]:
    """〈天下形勢〉的事實多一類（痕跡過門檻）：世界秒 since 以後過門檻的痕跡規則各一句（xingshi，沒寫照傳聞那一句），照過門檻的先後。"""
    rules = {r.mark: r for r in content.mark_rules}
    fired = sorted((at, mark) for mark, at in world.marks_fired.items() if at >= since and mark in rules)
    return [rules[mark].xingshi or rules[mark].rumor for _, mark in fired]
