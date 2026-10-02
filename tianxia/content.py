"""載入 content/ 底下的 JSON，並檢查所有交叉引用。內容寫錯時在載入當下就報錯。

sanguo-companions 合併大幅簡化了這裡的驗證規則（見設計文件開放決策記錄）：舊制度圍繞
天地玄黃品階/統御區間/流派資質 S 級數量/招賢卡池/收徒地點的一大批交叉檢查全部拿掉，
因為新制度（同伴全服唯一、無抽卡、無多隊、無舊武學品階系統）根本沒有這些概念。只保留
基本的交叉引用完整性檢查（id 存在、不重複、地點互相連通等），細緻的內容規則之後好玩
再視需要補回來。
"""
from __future__ import annotations

import json
from pathlib import Path

from pydantic import ValidationError

from .companion_agent import DIALOGUE_TAGS
from .models import (
    STATS, BattleDef, CharacterDef, Condition, Config, Content, Effect, Event, Location, MapLayout,
    Scenario, Sect, SimRumor, SkillDef, Squad, Tutorial,
)


class ContentError(Exception):
    pass


def load_content(root: Path) -> Content:
    root = Path(root)
    events: dict[str, Event] = {}
    for path in sorted((root / "events").glob("*.json")):
        for raw in _read(path):
            event = _build(Event, raw)
            if event.id in events:
                raise ContentError(f"事件 id 重複：{event.id}（{path.name}）")
            events[event.id] = event
    content = Content(
        config=Config(**_read(root / "config.json")),
        scenario=Scenario(**_read(root / "scenario.json")),
        locations=_index(Location, _read(root / "locations.json")),
        skills=_index(SkillDef, _read(root / "skills.json")),
        sects=_index(Sect, _read(root / "sects.json")),
        characters=_index(CharacterDef, _read(root / "characters.json")),
        squads=_index(Squad, _read(root / "squads.json")),
        battles=_index(BattleDef, _read(root / "battles.json")) if (root / "battles.json").exists() else {},
        events=events,
        map=MapLayout(**_read(root / "map.json")),
        tutorial=Tutorial(**_read(root / "tutorial.json")),
    )
    validate(content)
    return content


def _read(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _build(model, raw: dict):
    """建立一筆有 id 的內容；欄位錯誤時改報 ContentError，並指出是哪一筆。"""
    try:
        return model(**raw)
    except ValidationError as e:
        raise ContentError(f"{model.__name__} {raw.get('id', '?')}：{e}") from e


def _index(model, items: list[dict]) -> dict:
    result = {}
    for raw in items:
        obj = _build(model, raw)
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
        known(where, cond.members_none, c.characters, "人物")
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
        if eff.recruit:
            known(where, [eff.recruit], c.characters, "人物")
            if eff.recruit in c.characters:
                need(c.characters[eff.recruit].kind == "recruitable", f"{where}：結識的 {eff.recruit} 不是可招募的同伴")

    cfg = c.config
    for action in ("explore", "train", "socialize"):
        need(action in cfg.action_cost, f"config.action_cost 缺少 {action}")
    for stat in STATS:
        need(stat in cfg.start_stats, f"config.start_stats 缺少 {stat}")

    for loc in c.locations.values():
        where = f"地點 {loc.id}"
        for dest in loc.connections:
            if dest not in c.locations:
                errors.append(f"{where}：連到不存在的地點 {dest}")
            elif loc.id not in c.locations[dest].connections:
                errors.append(f"地點 {loc.id} 連到 {dest}，但 {dest} 沒有連回來")
        known(where, loc.enemies, c.squads, "敵方隊伍")
        known(where, loc.train_trend, trend_ids, "大勢線")
        need(
            0 <= loc.x <= c.map.width and 0 <= loc.y <= c.map.height,
            f"{where}：座標 ({loc.x}, {loc.y}) 超出地圖範圍",
        )
    need(c.scenario.start_location in c.locations, f"劇本起點 {c.scenario.start_location} 不存在")

    for sect in c.sects.values():
        known(f"門派 {sect.id}", [sect.location], c.locations, "地點")

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
                known(cw, [ch.combat], c.squads, "敵方隊伍")
            if ch.check:
                known(cw, [ch.check.stat], STATS, "屬性")
        recruits = {eff.recruit for ch in ev.choices for eff in (ch.effect, ch.fail_effect) if eff.recruit}
        for cid in sorted(recruits):
            need(
                cid in ev.condition.members_none,
                f"{where}：結識 {cid} 的事件，condition.members_none 要列出 {cid}（已入門就不該再遇到）",
            )
        if ev.fortune:
            need(not ev.actions, f"{where}：福緣事件只由交遊觸發，actions 要是空的")
            need(all(ch.effect.recruit for ch in ev.choices), f"{where}：福緣事件的每個選項都要結識一個人")
            for i, ch in enumerate(ev.choices):
                need(
                    ch.check is None and ch.combat is None,
                    f"{where} 選項{i}：福緣事件的選項不能有檢定或戰鬥（福緣自己送上門時直接套用第一個選項的效果）",
                )

    region_ids = [region.id for region in c.map.regions]
    duplicated = sorted({rid for rid in region_ids if region_ids.count(rid) > 1})
    need(not duplicated, f"大區 id 重複：{'、'.join(duplicated)}")
    for region in c.map.regions:
        where = f"大區 {region.id}"
        known(where, region.trends, trend_ids, "大勢線")
        need(
            len(region.points) >= 3 and all(len(point) == 2 for point in region.points),
            f"{where}：多邊形至少要有 3 個 [x, y] 點",
        )

    for th in c.scenario.thresholds:
        where = f"門檻 {th.id}"
        known(where, [th.trend], trend_ids, "大勢線")
        if th.location:
            known(where, [th.location], c.locations, "地點")
        if th.starts_battle:
            known(where, [th.starts_battle], c.battles, "戰鬥")
        need(
            not (th.trend in hidden and th.op == "<="),
            f"{where}：隱藏大勢線不能用 <= 門檻（未浮現時數值為 0，會立刻觸發）",
        )
    for sim in c.scenario.sim_players:
        where = f"虛擬玩家 {sim.name}"
        known(where, sim.trend, trend_ids, "大勢線")
        if sim.requires_revealed:
            known(where, [sim.requires_revealed], trend_ids, "大勢線")
        known(where, sim.haunts, c.locations, "地點")
        for rumor in sim.rumors:
            if isinstance(rumor, SimRumor):
                known(f"{where} 的傳聞「{rumor.text}」", [rumor.location], c.locations, "地點")
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
            known(aw, act.places, c.locations, "地點")
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
        if event.location:
            known(f"世界事件 {event.id}", [event.location], c.locations, "地點")
        if event.starts_battle:
            known(f"世界事件 {event.id}", [event.starts_battle], c.battles, "戰鬥")

    scenario_faction_ids = [f.id for f in c.scenario.factions]
    need(len(set(scenario_faction_ids)) == len(scenario_faction_ids), "劇本：陣營 id 重複")
    for faction in c.scenario.factions:
        known(f"陣營 {faction.id}", faction.join_at, c.locations, "地點")
        known(f"陣營 {faction.id}", faction.sects, c.sects, "門派")
        known(f"陣營 {faction.id}", faction.goals, trend_ids, "大勢線")
        need(all(d in (-1, 1) for d in faction.goals.values()), f"陣營 {faction.id}：goals 的方向只能是 1 或 -1")

    for battle in c.battles.values():
        where = f"戰鬥 {battle.id}"
        faction_ids = [f.id for f in battle.factions]
        need(len(set(faction_ids)) == len(faction_ids), f"{where}：陣營 id 重複")
        if scenario_faction_ids:
            known(where, faction_ids, scenario_faction_ids, "陣營")
        act_ids = [a.id for a in battle.acts]
        need(len(set(act_ids)) == len(act_ids), f"{where}：幕 id 重複")
        for i, act in enumerate(battle.acts):
            aw = f"{where} {act.id}"
            if i == len(battle.acts) - 1:
                need(act.advance_when is None, f"{aw}：最後一幕不能有 advance_when")
            else:
                need(act.advance_when is not None, f"{aw}：非最後一幕必須有 advance_when")
            for option in act.options:
                if not option.free_text:  # free_text 選項不查表，機制走 FreeTextGamble 擲骰，不需要 action_tags 裡有對應的 tag
                    known(f"{aw} 選項「{option.text}」", [option.tag], battle.action_tags, "行動分類")
                if option.faction is not None:
                    known(f"{aw} 選項「{option.text}」", [option.faction], faction_ids, "陣營")
        need(
            battle.free_text_gamble is not None or not any(o.free_text for a in battle.acts for o in a.options),
            f"{where}：有 free_text 選項，必須設定 free_text_gamble",
        )
        for outcome in battle.outcomes:
            known(f"{where} 結果「{outcome.title}」", [outcome.faction], faction_ids, "陣營")
            known(f"{where} 結果「{outcome.title}」", outcome.trend_delta, trend_ids, "大勢線")
        need(
            battle.outcomes[-1].trend_min is None and battle.outcomes[-1].trend_max is None,
            f"{where}：最後一個結果必須沒有數值門檻（作為保底結果，一定要能命中）",
        )

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

    for ch in c.characters.values():
        where = f"人物 {ch.id}"
        for stat in ("str", "agi", "con", "wis"):
            need(stat in ch.stats, f"{where}：stats 缺少 {stat}")
        if ch.sect:
            known(where, [ch.sect], c.sects, "門派")
        if ch.starting_wugong:
            known(where, [ch.starting_wugong], c.skills, "武學")
            if ch.starting_wugong in c.skills:
                need(c.skills[ch.starting_wugong].kind == "武學", f"{where}：starting_wugong 要指向 kind=武學 的武學")
        if ch.starting_neigong:
            known(where, [ch.starting_neigong], c.skills, "武學")
            if ch.starting_neigong in c.skills:
                need(c.skills[ch.starting_neigong].kind == "內功", f"{where}：starting_neigong 要指向 kind=內功 的武學")
        need(
            ch.kind is not None or ch.starting_wugong is None,
            f"{where}：敵人（kind 沒填）不需要 starting_wugong，那是同伴才有的欄位",
        )
        if ch.recruit_at:
            known(where, [ch.recruit_at], c.locations, "地點")
            need(ch.kind == "recruitable", f"{where}：只有 kind=recruitable 的同伴需要 recruit_at")
        if ch.talk_at:
            known(where, [ch.talk_at], c.locations, "地點")
            need(ch.kind == "locked", f"{where}：只有 kind=locked 的龍頭人物需要 talk_at（可招募的同伴用 recruit_at）")
        if ch.affinity_tag_deltas:
            for tag in ch.affinity_tag_deltas:
                need(tag in DIALOGUE_TAGS, f"{where}：affinity_tag_deltas 的 {tag!r} 不是合法的交遊 tag")
    for squad in c.squads.values():
        where = f"敵方隊伍 {squad.id}"
        need(squad.difficulty >= 0, f"{where}：difficulty 不能是負的")

    if errors:
        raise ContentError("內容檔有誤：\n" + "\n".join(errors))
