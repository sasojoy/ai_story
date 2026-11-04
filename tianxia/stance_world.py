"""人物心意的世界那一半（全部拆包第 19 批「先做」：總表附錄甲「stances 拆兩半」；原本在 tianxia/stances.py，函式本體一字不改）。

這一半讀寫的是季上的欄位（WorldState.stance_counts、stance_active、stance_week）與它們對世界的影響，核心與還沒搬的舊模組都讀：
核心 rules（痕跡一筆算幾筆 mark_scale）、核心 event_check（人物開的事件端到眼前 met）、events（抽不到的事件 closed_events）、figures（推線的倍數 push_scale）、
world（每天 00:00、每週一的掛鉤 daily、weekly_reset）。放進哪一包都會變成核心 import 包，所以是共用規則層（registry.SHARED）。
行動那一半（玩家跟人物說話記一筆、人物頁、假人挑心意）在功能包 tianxia/features/companions/stances.py，舊名 tianxia.stances 是它的別名、也 re-export 這裡的名字。
規則的說明在包裡那一份的開頭與導覽〈大勢人物與賽季〉「人物心意與託付」。

開關是 rules.jianfa(content, world, "stances")；關著每個函式都當沒有這回事（季上的欄位不讀不寫）。
只 import models、state、rules、calendar、conquest 與 figures（延後；figures 第 40 批收進共用規則層，邊界測試 SHARED_PENDING）。"""
from __future__ import annotations

from . import calendar, rules
from .models import Content, StanceDef
from .state import GameState, StanceNote, StanceOn, WorldState


def on(content: Content, world: WorldState | None) -> bool:
    return rules.jianfa(content, world, "stances")


def defs(content: Content, fid: str) -> list[StanceDef]:
    fig = content.figures.get(fid)
    return list(fig.stances) if fig is not None else []


def find(content: Content, fid: str, sid: str | None) -> StanceDef | None:
    return next((x for x in defs(content, fid) if x.id == sid), None)


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


def _best(content: Content, world: WorldState, fid: str) -> StanceDef | None:
    """這一週到門檻的心意裡最多的那一個（同數照內容的順序）；都沒到是 None。他已經照某一個做事時，同票不換手
    （check：要別的心意票數超過他此刻照著做的才換），這裡的「同數照內容的順序」只管第一次過門檻與挑戰者之間。"""
    book = world.stance_counts.get(fid, {})
    reached = [(book.get(d.id, 0), -i, d) for i, d in enumerate(defs(content, fid)) if book.get(d.id, 0) >= threshold(content, d)]
    return max(reached, key=lambda x: (x[0], x[1]))[2] if reached else None


def check(state: GameState, content: Content, fid: str, *, midnight: bool = False) -> StanceDef | None:
    """到門檻的心意裡照最多的那一個（_best）。他這一週還沒照哪一個做事：過門檻那一刻就生效，發天下大事（不列名字）、記江湖史。
    已經照某一個做事了：換手只在每天 00:00 重算（midnight，daily 叫；FB-826，PM 2026-10-26——不然兩個都過門檻之後一筆換一次），
    換了照發天下大事；江湖史同一位人物一週只記一次（就是生效的那一刻；週初歸零之後重來）。
    換手要「追過才換」（減法季 7e，PM 2026-10-26）：別的心意票數超過他此刻照著做的才換，追平不換——不然兩個心意同票時，
    排在內容前面的那一個追平就搶走、排在後面的追平不會，對兩個心意不公平。
    回他此刻照著做的那一個；都沒到、還沒生效是 None（此刻照著做的照留：歸零只在週初）。"""
    w = state.world
    best, now = _best(content, w, fid), w.stance_active.get(fid)
    if best is None or (now is not None and (now.stance == best.id or not midnight)):
        return find(content, fid, now.stance) if now is not None else None
    if now is not None:
        book = w.stance_counts.get(fid, {})
        if book.get(best.id, 0) <= book.get(now.stance, 0):  # 追平不換（best 是最多的，沒有誰超過他此刻照著做的）
            return find(content, fid, now.stance)
    w.stance_active[fid] = StanceOn(stance=best.id, at=w.time, week=w.stance_week or week_of(content, w))
    loc = content.figures[fid].location
    rules.add_rumor(state, best.rumor, loc, content=content, layer="world", named=False)
    if now is None:
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
    """每天 00:00 的掛鉤（world.DAY_HOOKS，21 天季與 7 天的季）：先重算換手（已經照某一個做事的人物，最多的那一個不一樣了才換，
    check(midnight=True)；FB-826），再替照著做的心意寫了 guard 的人物，把他那一條線上自家佔著的塊、每個攻方的進度各拉下 guard 點
    （領地爭奪的條；同 conquest.decay 直接改條、被戰書凍結的不動，不經 conquest.push：不記守城帳、不分紅；領地爭奪關著不拉）。
    關著什麼都不做。不回訊息（背景的事）。"""
    from . import conquest, figures  # noqa: PLC0415  conquest → territory → rules

    w = state.world
    if not on(content, w):
        return []
    if w.stance_week == week_of(content, w):  # 計數是上一週的（週初的掛鉤還沒跑）就不重算：歸零之後重來
        for fid in sorted(w.stance_active):
            check(state, content, fid, midnight=True)
    if not conquest.on(content, w):
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


def closed_events(state: GameState, content: Content) -> set[str]:
    """人物心意開的事件（StanceAction.event_daily：速戰的「盧植急攻」、恤民的「收容流民」）此刻抽不到的那幾則（events.event_candidates
    當成藏起來的）：心意關著是全部（關著的季一個字都不變）；開著時，他此刻沒照那個心意做事、或你今天碰過了（met，每人每天一則）的。"""
    live, w = on(content, state.world), state.world
    out: set[str] = set()
    for fid, fig in content.figures.items():
        for d in fig.stances:
            if d.action.event_daily is None:
                continue
            now = w.stance_active.get(fid) if live else None
            note = state.player.stance_notes.get(fid)
            met_today = (note is not None and note.week == week_of(content, w)
                         and note.event_day == rules.game_day(content, w)) if live else False
            if now is None or now.stance != d.id or met_today:
                out.add(d.action.event_daily)
    return out


def met(state: GameState, content: Content, event_id: str) -> None:
    """人物心意開的那一則端到你眼前（Game._present，從池子抽的那一下）：記今天碰過了，今天不再抽到。不是這種事件、關著什麼都不做。"""
    w = state.world
    if not on(content, w):
        return
    for fid, fig in content.figures.items():
        if any(d.action.event_daily == event_id for d in fig.stances):
            _note(state, fid, week_of(content, w)).event_day = rules.game_day(content, w)


def weekly_reset(state: GameState, content: Content, week: int) -> list[str]:
    """週初的掛鉤（world.WEEK_HOOKS，week 是剛跨進的那一週）：計數與他此刻照哪一個做事歸零。關著不碰季。不回訊息。"""
    w = state.world
    if not on(content, w):
        return []
    if w.stance_week != week:
        w.stance_counts, w.stance_active, w.stance_week = {}, {}, week
    return []
