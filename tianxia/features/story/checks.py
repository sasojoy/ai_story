"""長篇奇事包的內容驗證（第二輪第 100 批從核心 content.py 搬來，本體照搬）：content.validate 在原位經 features.check_at 叫（格在 core/features.py 的 CONTENT_SLOTS），先後不變；關著的包照驗。"""
from __future__ import annotations

import re

from tianxia.core.content_base import event_effects, stage_events
from tianxia.models import Content, Effect, Event


STORY_ART = re.compile(r"^stories/[a-z0-9_]+$")  # 一條線、段落卡與結局的專屬圖（web/img/stories/<鍵>.webp；頓悟是 dunwu_*）


def event_endings(ev: Event) -> list[Effect]:
    """一則事件了結時真的會套的那幾個效果：每個選項的成套（有檢定或開打的再加敗套）、隨口應對的成敗或分岔每一種後果的成敗。"""
    out = []
    for ch in ev.choices:
        out += [ch.effect] + ([ch.fail_effect] if ch.check is not None or ch.combat is not None else [])
    free = ev.free_text
    if free is not None:
        out += [e for o in free.outcomes for e in [o.effect] + ([o.fail_effect] if o.kind in ("check", "combat") else [])]
        if not free.outcomes_only:
            out += [free.effect, free.fail_effect]
    return out


def check_storylines(c: Content, need) -> None:
    """一條線（content/storylines.json，特殊事件設計稿；tianxia/storyline.py）：段與結局的 id 不重複、往哪裡都指得到、
    段落事件只能接在這條線上（actions 寫 []、只屬於一條線），fight 寫得出打哪一路、打贏打輸往哪裡，task 寫得出等什麼。
    效果的 story 只准寫在段落事件上，line 要是那一條線。"""
    owner: dict[str, str] = {}
    for line in c.storylines.values():
        lw = f"一條線 {line.id}"
        ids = [st.id for st in line.stages] + [e.id for e in line.endings]
        need(len(ids) == len(set(ids)), f"{lw}：段與結局的 id 有重複")
        known_ids = set(ids)
        for img in [line.image] + [e.image for e in line.endings] + [st.image for st in line.stages]:
            need(img is None or bool(STORY_ART.match(img)), f"{lw}：image「{img}」要寫成 stories/<鍵>")
        if line.start is not None:
            check_story_place(c, need, f"{lw} 的開頭", line.start.where)
        need(any(not e.failed for e in line.endings), f"{lw}：至少要有一個不是失敗的結局")
        if line.chapter is not None:
            check_chapter(c, need, line)
        for end in line.endings:
            need(end.effect.story is None, f"{lw} 結局 {end.id}：結局的效果不能再寫 story")
            need(bool(end.annal.strip()), f"{lw} 結局 {end.id}：annal（寫進傳的那一句）是空的")

        def target(where: str, go: str | None) -> None:
            need(go is None or go in known_ids, f"{where}：往「{go}」指不到這條線的段或結局")

        for st in line.stages:
            sw = f"{lw} 段 {st.id}"
            check_story_place(c, need, sw, st.where)
            for name in ("next", "late", "win", "lose"):
                target(f"{sw} 的 {name}", getattr(st, name))
            for route in st.routes:
                target(f"{sw} 的 routes", route.go)
            need(st.days is None or st.late is not None, f"{sw}：寫了期限 days 就要寫過期往哪裡（late）")
            routed = st.next is not None or bool(st.routes)
            if st.kind == "event":
                ev = c.events.get(st.event or "")
                need(ev is not None, f"{sw}：事件「{st.event}」不存在")
                if ev is None:
                    continue
                for eid, from_stage in stage_events(c, line).items():
                    if from_stage != st.id:
                        continue
                    chained = c.events[eid]
                    need(chained.actions == [], f"{sw}：事件 {eid} 的 actions 要寫 []（只由這條線端出來）")
                    need(owner.setdefault(eid, line.id) == line.id, f"{sw}：事件 {eid} 已經是一條線 {owner[eid]} 的段落")
                    for eff in event_effects(chained):
                        if eff.story is not None:
                            need(eff.story.line == line.id, f"{sw}：事件 {eid} 的 story.line 要是 {line.id}")
                            target(f"{sw} 事件 {eid} 的 story.go", eff.story.go)
                # 選項都寫了往哪裡（或事件串到下一則）才可以不寫 routes／next
                need(routed or all((eff.story is not None and eff.story.go) or eff.next_event for eff in event_endings(ev)),
                     f"{sw}：有選項沒寫 story.go，這一段又沒寫 next 或 routes（走完不知道往哪裡）")
            elif st.kind == "quiz":
                need(bool(st.questions), f"{sw}：quiz 要寫 questions")
                need(routed, f"{sw}：quiz 要寫 next 或 routes")
            elif st.kind == "fight":
                need(st.squad in c.squads, f"{sw}：打的那一路「{st.squad}」不在 squads")
                need(st.win is not None and st.lose is not None, f"{sw}：fight 要寫 win 與 lose")
            else:
                need(st.until is not None or bool(st.task), f"{sw}：task 要寫 until（條件）或 task（登記的判斷名）")
                need(routed, f"{sw}：task 要寫 next 或 routes")
    for ev in c.events.values():
        if ev.id in owner:
            continue
        need(all(eff.story is None for eff in event_effects(ev)), f"事件 {ev.id}：story 只能寫在一條線的段落事件上")


def check_chapter(c: Content, need, line) -> None:
    """章回主線的一回（tianxia/chapters.py）：kind 寫「章回」、陣營在劇本裡、beat／after_beat 是時刻表的大事、after 是同一方的別回，
    最後一段是 wait（task chapter_beat），有 missed 結局。"""
    from tianxia import chapters  # noqa: PLC0415

    lw, spec = f"章回 {line.id}", line.chapter
    timetable_ids = {e.id for e in c.timetable}
    need(line.kind == chapters.KIND, f"{lw}：kind 要寫「{chapters.KIND}」")
    need(line.start is None, f"{lw}：章回由時刻表開，不寫 start")
    need(spec.side in {f.id for f in c.scenario.factions}, f"{lw}：陣營「{spec.side}」不在劇本裡")
    need(spec.beat in timetable_ids, f"{lw}：beat「{spec.beat}」不是時刻表的大事")
    need(spec.after_beat is None or spec.after_beat in timetable_ids, f"{lw}：after_beat「{spec.after_beat}」不是時刻表的大事")
    for before in spec.after:
        prev = c.storylines.get(before)
        need(prev is not None and prev.chapter is not None and prev.chapter.side == spec.side, f"{lw}：after「{before}」不是同一方的章回")
    last = line.stages[-1]
    need(last.id == chapters.WAIT and last.kind == "task" and last.task == chapters.TASK,
         f"{lw}：最後一段要是 {chapters.WAIT}（task {chapters.TASK}）")
    need(all(st.id != chapters.WAIT for st in line.stages[:-1]), f"{lw}：{chapters.WAIT} 只能是最後一段")
    need(line.ending(chapters.MISSED) is not None, f"{lw}：要有 {chapters.MISSED} 結局（大事結算了還沒做成）")


def check_story_place(c: Content, need, where: str, place) -> None:
    for lid in place.locations:
        need(lid in c.locations, f"{where}：地點「{lid}」不存在")
    regions = {r.id for r in c.map.regions}
    for rid in place.regions:
        need(rid in regions, f"{where}：大區「{rid}」不存在")
