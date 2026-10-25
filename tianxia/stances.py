"""人物心意（減法季整合設計 5.4、5.9，主機側計畫 Task 6-1；企劃者 2026-10-24 定）。

每位大勢人物有 2～3 個封閉的心意（FigureDef.stances：速戰、持重、恤民……）。跟他說話那一輪（選上一輪的選項、自己說），模型除了照舊
回話，多歸一次「玩家這一步在勸他哪一種」（companion_agent 的 stance 欄位，只能是清單上的 id 或 none）；引擎記一筆：
- 一人一天一筆（PlayerState.stance_notes，天是 rules.game_day），全服這一週的計數在 WorldState.stance_counts；
- 這一週有心意到門檻（StanceDef.threshold，沒寫照 Config.jianfa.stance_threshold 30【預設】），他照最多的那一個改做事
  （WorldState.stance_active）：推線乘倍（figures.tick 讀 push_scale）、每天 00:00 拉下他那一條線上自家塊的對面進度（daily）、
  幾條痕跡記一筆算幾筆（rules.add_marks 讀 mark_scale）；那一刻發一則天下大事（不列名字）、記一筆江湖史，這一週勸過那一個心意的人
  各在下一次同步記一則行狀（annals.STANCE，酒肆打聽不到）；
- 每週一 00:00（world.WEEK_HOOKS；7 天的季照段）歸零重算：計數與他此刻照哪一個做事一起清掉。
心意不是情誼：情誼是他喜不喜歡你，心意是他聽了大家的話之後做什麼。記一筆另記陣營貢獻（Config.jianfa.stance_contribution，
跟分岔的後果同一本每日上限；Game 記）。假人不說話，照名號雜湊每天 bot_stance_chance 的機會直接記一筆（bot_pick，企劃者 2026-10-24 第 5 件）。

開關是 rules.jianfa(content, world, "stances")；關著每個函式都當沒有這回事（季上的欄位不讀不寫、提示詞一個字不變）。
只 import models、state、rules、calendar、conquest（延後）；engine、companion_agent、figures、world、bot_policy、server 叫它。字待 joy 潤。"""
from __future__ import annotations

import random

from . import calendar, rules
from .models import Content, StanceDef
from .state import GameState, StanceNote, StanceOn, WorldState

NONE = "none"  # 模型歸不進任何一種心意時填的
HEARD = "（{name}把你的話記在心上：{stance}。）"  # 待 joy 潤：記到一筆那一輪的紀錄
ANNAL = "眾人勸{name}{stance}，你也是其中之一：{rumor}"  # 待 joy 潤：到門檻那一刻勸過的人的行狀


def on(content: Content, world: WorldState | None) -> bool:
    return rules.jianfa(content, world, "stances")


def defs(content: Content, fid: str) -> list[StanceDef]:
    fig = content.figures.get(fid)
    return list(fig.stances) if fig is not None else []


def find(content: Content, fid: str, sid: str | None) -> StanceDef | None:
    return next((x for x in defs(content, fid) if x.id == sid), None)


def figure_of(content: Content, cid: str) -> str | None:
    """這個對話人物是哪一位有心意的大勢人物（人物表 id）；沒有心意的是 None。"""
    return next((fid for fid, fig in content.figures.items() if fig.character == cid and fig.stances), None)


def ids_for(state: GameState, content: Content, cid: str) -> tuple[str, ...]:
    """跟 cid 說話時要模型多歸的那幾個心意 id（companion_agent 照它加 schema 與提示）；關著、沒有心意是空的。"""
    fid = figure_of(content, cid) if on(content, state.world) else None
    return tuple(x.id for x in defs(content, fid)) if fid is not None else ()


def threshold(content: Content, d: StanceDef) -> int:
    return d.threshold if d.threshold is not None else content.config.jianfa.stance_threshold


def week_of(content: Content, world: WorldState) -> int:
    """這一刻是季曆第幾週（7 天的季是第幾段）：計數照它歸零。"""
    return calendar.point(world.time, content, world).week


def _roll_week(content: Content, world: WorldState) -> int:
    """計數是上一週的就先清掉（週初掛鉤沒跑到時的保險：一律照此刻的週）。回這一週。"""
    week = week_of(content, world)
    if world.stance_week != week:
        world.stance_counts, world.stance_active, world.stance_week = {}, {}, week
    return week


def _note(state: GameState, fid: str, week: int) -> StanceNote:
    note = state.player.stance_notes.get(fid)
    if note is None or note.week != week:
        note = state.player.stance_notes[fid] = StanceNote(week=week)
    return note


def heard_today(state: GameState, content: Content, fid: str) -> str | None:
    """你今天跟他記過的那一筆（人物頁的 my_stance_today）；沒記過、上一週的、關著是 None。"""
    note = state.player.stance_notes.get(fid)
    if not on(content, state.world) or note is None or note.week != week_of(content, state.world):
        return None
    if note.day != rules.game_day(content, state.world) or not note.said:
        return None
    return note.said[-1]


def record(state: GameState, content: Content, fid: str, sid: str) -> bool:
    """記一筆：開著、他有這個心意、你今天還沒跟他記過。記了就看到門檻沒（check）。回有沒有記。"""
    w = state.world
    if not on(content, w) or find(content, fid, sid) is None or heard_today(state, content, fid) is not None:
        return False
    week = _roll_week(content, w)
    book = w.stance_counts.setdefault(fid, {})
    book[sid] = book.get(sid, 0) + 1
    note = _note(state, fid, week)
    note.day = rules.game_day(content, w)
    if sid not in note.said:
        note.said.append(sid)
    check(state, content, fid)
    return True


def bump(state: GameState, content: Content, fid: str, sid: str | None) -> None:
    """替他的這個心意加一筆，不佔你一天一筆的額度（託付辦成了的「心意 +1」，整合設計 5.5）。"""
    w = state.world
    if sid is None or not on(content, w) or find(content, fid, sid) is None:
        return
    week = _roll_week(content, w)
    book = w.stance_counts.setdefault(fid, {})
    book[sid] = book.get(sid, 0) + 1
    note = _note(state, fid, week)
    if sid not in note.said:
        note.said.append(sid)
    check(state, content, fid)


def check(state: GameState, content: Content, fid: str) -> StanceDef | None:
    """這一週到門檻的心意裡照最多的那一個（同數照內容的順序）；跟他此刻照著做的不一樣才換、發天下大事（不列名字）、記江湖史。
    都沒到是 None（此刻照著做的照留：歸零只在週初）。"""
    w = state.world
    book = w.stance_counts.get(fid, {})
    rows = defs(content, fid)
    reached = [(book.get(d.id, 0), -i, d) for i, d in enumerate(rows) if book.get(d.id, 0) >= threshold(content, d)]
    if not reached:
        return None
    best = max(reached, key=lambda x: (x[0], x[1]))[2]
    now = w.stance_active.get(fid)
    if now is None or now.stance != best.id:
        w.stance_active[fid] = StanceOn(stance=best.id, at=w.time, week=w.stance_week or week_of(content, w))
        loc = content.figures[fid].location
        rules.add_rumor(state, best.rumor, loc, content=content, layer="world", named=False)
        rules.add_chronicle(state, best.chronicle or best.rumor)
    return best


def active(state: GameState, content: Content, fid: str) -> StanceDef | None:
    """他此刻照哪一個心意做事；關著、沒有是 None。"""
    if not on(content, state.world):
        return None
    now = state.world.stance_active.get(fid)
    return find(content, fid, now.stance) if now is not None else None


def push_scale(state: GameState, content: Content, fid: str) -> float:
    """他每天推線乘幾倍（figures.tick）：照著做的心意的 push；沒有、關著是 1。"""
    d = active(state, content, fid)
    return d.action.push if d is not None else 1.0


def mark_scale(state: GameState, content: Content, key: str) -> int:
    """這一條痕跡（「地點 id:痕跡名」）記一筆算幾筆：有人物照著做的心意寫了它就照它（取最大的），否則 1；關著是 1。"""
    if not on(content, state.world):
        return 1
    scale = 1
    for fid in state.world.stance_active:
        d = active(state, content, fid)
        if d is not None:
            scale = max(scale, d.action.marks.get(key, 1))
    return scale


def daily(state: GameState, content: Content) -> list[str]:
    """每天 00:00 的掛鉤（world.DAY_HOOKS，21 天季與 7 天的季）：照著做的心意寫了 guard 的人物，他那一條線上自家佔著的塊，
    每個攻方的進度各拉下 guard 點（領地爭奪的條；同 conquest.decay 直接改條、被戰書凍結的不動，不經 conquest.push：不記守城帳、
    不分紅）。關著、領地爭奪關著什麼都不做。不回訊息（背景的事）。"""
    from . import conquest, figures  # noqa: PLC0415  conquest → territory → rules

    w = state.world
    if not on(content, w) or not conquest.on(content, w):
        return []
    for fid in list(w.stance_active):
        d = active(state, content, fid)
        if d is None or d.action.guard <= 0:
            continue
        side, line = content.figures[fid].faction, figures.state_of(state, content, fid).front
        if line is None:
            continue
        for loc in conquest.blocks(content):
            if conquest.line_of(w, content, loc) != line or conquest.holder(w, content, loc) != side:
                continue
            fight = conquest.fight_of(w, loc)
            if fight is None or not fight.bars or conquest.frozen(w, loc) is not None:
                continue
            for other, bar in list(fight.bars.items()):
                bar.value = max(0.0, bar.value - d.action.guard)
                if bar.value <= 1e-9:
                    del fight.bars[other]
            if not fight.bars:
                fight.guards, fight.alarm = {}, False
    return []


def weekly_reset(state: GameState, content: Content, week: int) -> list[str]:
    """週初的掛鉤（world.WEEK_HOOKS，week 是剛跨進的那一週）：計數與他此刻照哪一個做事歸零。關著不碰季。不回訊息。"""
    w = state.world
    if not on(content, w):
        return []
    if w.stance_week != week:
        w.stance_counts, w.stance_active, w.stance_week = {}, {}, week
    return []


def view(state: GameState, content: Content, fid: str) -> dict | None:
    """人物頁的心意條（主機側計畫 1.3 的 figure.stances）：{"stances": [{id, name, count, threshold, active}], "my_stance_today"}。
    關著、他沒有心意是 None。計數是這一週的（上一週的當 0）。"""
    w = state.world
    rows = defs(content, fid)
    if not on(content, w) or not rows:
        return None
    current = w.stance_week == week_of(content, w)
    book = w.stance_counts.get(fid, {}) if current else {}
    now = w.stance_active.get(fid) if current else None
    return {
        "stances": [{"id": d.id, "name": d.name, "count": book.get(d.id, 0), "threshold": threshold(content, d),
                     "active": now is not None and now.stance == d.id} for d in rows],
        "my_stance_today": heard_today(state, content, fid),
    }


def hear(state: GameState, content: Content, cid: str, said: str | None) -> list[str]:
    """跟 cid 說話的一輪收尾（companion_agent._apply_turn，選選項、自己說那兩種；開口那一輪不算）：模型歸的心意記一筆，回紀錄那一句。
    none、清單外、今天記過、關著都是空的。"""
    fid = figure_of(content, cid) if on(content, state.world) else None
    d = find(content, fid, said) if fid is not None else None
    if d is None or not record(state, content, fid, d.id):
        return []
    return [HEARD.format(name=content.figures[fid].name, stance=d.name)]


def prompt_lines(state: GameState, content: Content, cid: str) -> str:
    """對話提示多的一段（companion_agent.build_system_prompt）：他眼下在拿什麼主意、有哪幾種說法、要模型多填 stance。關著是空的。"""
    fid = figure_of(content, cid) if on(content, state.world) else None
    if fid is None:
        return ""
    name = content.figures[fid].name
    rows = "".join(f"- {d.id}（{d.name}）：{d.hint}\n" for d in defs(content, fid))
    return (
        f"【{name}正在拿的主意】眼下好幾種說法都在他耳邊，他會照多數人勸的去做：\n{rows}"
        f"另外在 stance 欄位填玩家這一步（說的這句話或選的這個做法）最像在勸{name}哪一種，只能填上面的 id；"
        f"不是在勸他這幾件事的填 {NONE}。這一欄只是歸類，不要在敘事裡提到它。\n"
    )


def annals_due(state: GameState, content: Content) -> list[tuple[str, StanceDef]]:
    """你這一週勸過、而且到了門檻、還沒記過行狀的那幾個（人物表 id, 心意）；記下來之後標成記過了。關著是空的（Game 寫行狀）。"""
    w = state.world
    if not on(content, w):
        return []
    out = []
    for fid, note in state.player.stance_notes.items():
        now = w.stance_active.get(fid)
        if now is None or note.week != now.week or now.stance not in note.said or now.stance in note.told:
            continue
        d = find(content, fid, now.stance)
        if d is not None:
            note.told.append(now.stance)
            out.append((fid, d))
    return out


def bot_pick(state: GameState, content: Content) -> tuple[str, str] | None:
    """假人今天要不要直接記一筆心意、記哪一位的哪一個（企劃者 2026-10-24 第 5 件：不說話、不寫字，讓人少的服心意也會動）：
    照名號＋今天的雜湊擲 bot_stance_chance；人物挑自己這一邊的（散人哪一邊都行），心意照名號＋人物的雜湊挑（同一個假人對同一位人物
    一直勸同一種，像有個性）。同一天擲幾次都是同一個結果；不碰 Game.rng。關著、沒得挑是 None。"""
    w, p = state.world, state.player
    if not on(content, w):
        return None
    day = rules.game_day(content, w)
    rng = random.Random(f"心意|{w.tianji}|{p.name}|{day}")
    if rng.random() >= content.config.jianfa.bot_stance_chance:
        return None
    from . import figures  # noqa: PLC0415  figures → stances（figures.tick 延後 import 這裡）

    side = p.ally if p.ally is not None else p.faction
    pool = [fid for fid, fig in content.figures.items() if fig.stances and (side not in ("guan", "huang") or fig.faction == side)
            and figures.state_of(state, content, fid).status == "active"]  # 下獄、退場、還沒出場的人物不勸
    if not pool:
        return None
    fid = rng.choice(sorted(pool))
    rows = defs(content, fid)
    return fid, rows[random.Random(f"心意|{p.name}|{fid}").randrange(len(rows))].id
