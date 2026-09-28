"""載入 content/ 底下的 JSON，並檢查所有交叉引用。內容寫錯時在載入當下就報錯。"""
from __future__ import annotations

import json
from pathlib import Path

from .models import (
    STATS, Condition, Config, Content, Effect, Enemy, Event, Location, MapLayout, Scenario, Sect, Skill,
    Tutorial,
)


class ContentError(Exception):
    pass


def load_content(root: Path) -> Content:
    root = Path(root)
    events: dict[str, Event] = {}
    for path in sorted((root / "events").glob("*.json")):
        for raw in _read(path):
            event = Event(**raw)
            if event.id in events:
                raise ContentError(f"事件 id 重複：{event.id}（{path.name}）")
            events[event.id] = event
    content = Content(
        config=Config(**_read(root / "config.json")),
        scenario=Scenario(**_read(root / "scenario.json")),
        locations=_index(Location, _read(root / "locations.json")),
        skills=_index(Skill, _read(root / "skills.json")),
        sects=_index(Sect, _read(root / "sects.json")),
        enemies=_index(Enemy, _read(root / "enemies.json")),
        events=events,
        map=MapLayout(**_read(root / "map.json")),
        tutorial=Tutorial(**_read(root / "tutorial.json")),
    )
    validate(content)
    return content


def _read(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _index(model, items: list[dict]) -> dict:
    result = {}
    for raw in items:
        obj = model(**raw)
        if obj.id in result:
            raise ContentError(f"{model.__name__} id 重複：{obj.id}")
        result[obj.id] = obj
    return result


def validate(c: Content) -> None:
    errors: list[str] = []
    trend_ids = {t.id for t in c.scenario.trends}
    hidden = {t.id for t in c.scenario.trends if t.hidden}

    def need(ok: bool, message: str) -> None:
        if not ok:
            errors.append(message)

    def known(where: str, keys, valid, kind: str) -> None:
        for key in keys:
            need(key in valid, f"{where}：未知的{kind} {key}")

    def check_condition(where: str, cond: Condition) -> None:
        known(where, [*cond.min_stats, *cond.max_stats], STATS, "屬性")
        known(where, cond.sects, c.sects, "門派")
        known(where, [*cond.skills_all, *cond.skills_none], c.skills, "武學")
        known(where, [*cond.trend_min, *cond.trend_max], trend_ids, "大勢線")
        known(where, [*cond.revealed_all, *cond.revealed_none], trend_ids, "大勢線")
        for sub in cond.any_of:
            check_condition(where, sub)

    def check_effect(where: str, eff: Effect) -> None:
        known(where, eff.stats, STATS, "屬性")
        known(where, eff.learn_skills, c.skills, "武學")
        known(where, eff.trend, trend_ids, "大勢線")
        if eff.join_sect:
            known(where, [eff.join_sect], c.sects, "門派")
        if eff.next_event:
            known(where, [eff.next_event], c.events, "事件")

    cfg = c.config
    for action in ("explore", "train", "socialize"):
        need(action in cfg.action_cost, f"config.action_cost 缺少 {action}")
    for stat in STATS:
        need(stat in cfg.start_stats, f"config.start_stats 缺少 {stat}")
    known("config.starter_skills", cfg.starter_skills, c.skills, "武學")

    for loc in c.locations.values():
        where = f"地點 {loc.id}"
        for dest in loc.connections:
            if dest not in c.locations:
                errors.append(f"{where}：連到不存在的地點 {dest}")
            elif loc.id not in c.locations[dest].connections:
                errors.append(f"地點 {loc.id} 連到 {dest}，但 {dest} 沒有連回來")
        known(where, loc.enemies, c.enemies, "敵人")
        known(where, loc.train_trend, trend_ids, "大勢線")
        need(
            0 <= loc.x <= c.map.width and 0 <= loc.y <= c.map.height,
            f"{where}：座標 ({loc.x}, {loc.y}) 超出地圖範圍",
        )
    need(c.scenario.start_location in c.locations, f"劇本起點 {c.scenario.start_location} 不存在")

    for skill in c.skills.values():
        if skill.sect:
            known(f"武學 {skill.id}", [skill.sect], c.sects, "門派")
    for sect in c.sects.values():
        known(f"門派 {sect.id}", [sect.location], c.locations, "地點")
        known(f"門派 {sect.id}", sect.starter_skills, c.skills, "武學")

    for ev in c.events.values():
        where = f"事件 {ev.id}"
        known(where, ev.locations, c.locations, "地點")
        check_condition(where, ev.condition)
        need(
            any(ch.condition == Condition() for ch in ev.choices),
            f"{where}：至少要有一個沒有條件的選項，否則玩家可能卡住",
        )
        for i, ch in enumerate(ev.choices):
            cw = f"{where} 選項{i}"
            check_condition(cw, ch.condition)
            check_effect(cw, ch.effect)
            check_effect(cw, ch.fail_effect)
            if ch.combat:
                known(cw, [ch.combat], c.enemies, "敵人")
            if ch.check:
                known(cw, [ch.check.stat], STATS, "屬性")

    for th in c.scenario.thresholds:
        where = f"門檻 {th.id}"
        known(where, [th.trend], trend_ids, "大勢線")
        need(
            not (th.trend in hidden and th.op == "<="),
            f"{where}：隱藏大勢線不能用 <= 門檻（未浮現時數值為 0，會立刻觸發）",
        )
    for sim in c.scenario.sim_players:
        where = f"虛擬玩家 {sim.name}"
        known(where, sim.trend, trend_ids, "大勢線")
        if sim.requires_revealed:
            known(where, [sim.requires_revealed], trend_ids, "大勢線")
        check_condition(where, sim.condition)
    for ending in c.scenario.endings:
        check_condition(f"結局 {ending.id}", ending.condition)

    line_ids = [s.id for s in c.scenario.storylines]
    need(len(set(line_ids)) == len(line_ids), "主線 id 重複")
    for i, line in enumerate(c.scenario.storylines):
        where = f"主線 {line.id}"
        if i == 0:
            need(line.replaces_when is None, f"{where}：第一條主線不能有 replaces_when")
        else:
            need(line.replaces_when is not None, f"{where}：支線主線必須有 replaces_when")
            if line.replaces_when is not None:
                check_condition(where, line.replaces_when)
        for j, act in enumerate(line.acts):
            aw = f"{where} 第{j + 1}幕 {act.id}"
            if j == len(line.acts) - 1:
                need(act.advance_when is None, f"{aw}：最後一幕不能有 advance_when")
            else:
                need(act.advance_when is not None, f"{aw}：非最後一幕必須有 advance_when")
                if act.advance_when is not None:
                    check_condition(aw, act.advance_when)
    for ending in c.scenario.endings:
        if ending.storyline:
            known(f"結局 {ending.id}", [ending.storyline], line_ids, "主線")
    fire_ids = [t.id for t in c.scenario.thresholds] + [e.id for e in c.scenario.world_events]
    need(len(set(fire_ids)) == len(fire_ids), "大勢門檻與世界事件的 id 重複")
    for event in c.scenario.world_events:
        check_condition(f"世界事件 {event.id}", event.condition)

    last = c.scenario.endings[-1] if c.scenario.endings else None
    need(
        last is not None and last.condition == Condition() and last.storyline is None,
        "劇本的最後一個結局必須沒有條件、也不限主線（作為保底結局）",
    )

    for milestone in c.scenario.milestones:
        check_condition(f"個人目標 {milestone.id}", milestone.condition)
    for step in c.tutorial.steps:
        where = f"新手引導 {step.id}"
        known(where, step.done_when.locations, c.locations, "地點")
        check_condition(where, step.done_when.condition)
        check_effect(where, step.reward)

    if errors:
        raise ContentError("內容檔有誤：\n" + "\n".join(errors))
