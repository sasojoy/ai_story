"""載入 content/ 底下的 JSON，並檢查所有交叉引用。內容寫錯時在載入當下就報錯。"""
from __future__ import annotations

import json
from pathlib import Path

from pydantic import ValidationError

from .models import (
    COMPANION_TIERS, STATS, CharacterDef, Condition, Config, Content, Effect, Event, Location, MapLayout,
    Scenario, Sect, SimRumor, Skill, Squad, Tutorial, in_gacha_pool,
)

# 同伴的品階規則（設計文件 1c §1.2）：統御範圍、本命品質（黃品沒有本命）、流派資質
TIER_COMMAND = {"天": (6, 7), "地": (4, 6), "玄": (3, 4), "黃": (1, 3)}
TIER_INNATE = {"天": "上", "地": "中", "玄": "下", "黃": None}
TIER_S = {"天": 2, "地": 1}  # 流派資質裡剛好要有幾項 S
TIER_TOP = {"玄": "A", "黃": "B"}  # 流派資質最高到哪一級
GRADES = "SABC"
# 取得管道只給哪些品階；開局、招賢不限
SOURCE_TIERS = {"收徒": ("黃", "玄"), "交遊": ("玄", "地"), "福緣": ("地",), "奇遇": ("地", "天"), "招降": ("地", "天")}
BROUGHT = ("交遊", "奇遇", "福緣", "招降")  # 要有事件或敵方隊伍真的帶得來的管道


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
        skills=_index(Skill, _read(root / "skills.json")),
        sects=_index(Sect, _read(root / "sects.json")),
        characters=_index(CharacterDef, _read(root / "characters.json")),
        squads=_index(Squad, _read(root / "squads.json")),
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
                need(c.characters[eff.recruit].tier != "敵", f"{where}：結識的 {eff.recruit} 不是同伴")

    brought: dict[str, set[str]] = {}  # 人物 id → 真的帶得來他的管道（事件、敵方隊伍）

    def bring(cid: str, source: str, where: str) -> None:
        if cid in c.characters and c.characters[cid].tier != "敵":
            brought.setdefault(cid, set()).add(source)
            need(source in c.characters[cid].sources, f"{where}：{source}帶來的 {cid} 要有「{source}」管道")

    def check_companion(ch: CharacterDef) -> None:
        where = f"人物 {ch.id}"
        low, high = TIER_COMMAND[ch.tier]
        got = "沒有填 command" if ch.command is None else f"現在是 {ch.command}"
        need(ch.command is not None and low <= ch.command <= high, f"{where}：{ch.tier}品的統御要在 {low}～{high}（{got}）")
        quality = TIER_INNATE[ch.tier]
        if quality is None:
            need(ch.innate is None, f"{where}：黃品沒有本命武學")
        elif ch.innate is None:
            errors.append(f"{where}：{ch.tier}品要有本命武學")
        elif ch.innate in c.skills:
            innate = c.skills[ch.innate]
            need(innate.quality == quality, f"{where}：{ch.tier}品的本命要是{quality}品（{innate.name} 是{innate.quality}品）")
        grades = list(ch.aptitude.values())
        if ch.tier in TIER_S:
            need(grades.count("S") == TIER_S[ch.tier], f"{where}：{ch.tier}品的流派資質要剛好 {TIER_S[ch.tier]} 項 S")
        else:
            top = TIER_TOP[ch.tier]
            need(all(GRADES.index(g) >= GRADES.index(top) for g in grades), f"{where}：{ch.tier}品的流派資質最高 {top}")
        if ch.tier == "天":
            need(ch.trait is not None, f"{where}：天品要有特性 trait")
        elif ch.trait is not None:
            errors.append(f"{where}：只有天品有特性")
        if ch.trait is not None:
            known(where, [ch.trait], c.skills, "武學")
            trait = c.skills.get(ch.trait)
            if trait is not None:
                need(
                    trait.kind == "心法" and all(e.top is None for e in trait.effects),
                    f"{where}：特性 {ch.trait} 要是效果固定（不寫 top）的心法",
                )
        need(bool(ch.sources), f"{where}：同伴要寫取得管道 sources")
        if ch.sources:
            need(any(s != "招賢" for s in ch.sources), f"{where}：至少要有一條招賢以外的免費管道")
        need(("開局" in ch.sources) == (ch.id in cfg.start_companions), f"{where}：「開局」管道要和 config.start_companions 一致")
        for source in ch.sources:
            if source in SOURCE_TIERS:
                tiers = SOURCE_TIERS[source]
                need(ch.tier in tiers, f"{where}：「{source}」管道只給{'、'.join(t + '品' for t in tiers)}")
            if source in BROUGHT:
                what = "敵方隊伍" if source == "招降" else "事件"
                need(source in brought.get(ch.id, set()), f"{where}：「{source}」管道沒有{what}帶得來")
        need(not ch.recruit_at or "收徒" in ch.sources, f"{where}：有收徒地點 recruit_at 就要有「收徒」管道")
        for loc_id in ch.recruit_at:
            if loc_id not in c.locations:
                errors.append(f"{where}：未知的地點 {loc_id}")
            else:
                need(
                    bool(set(c.locations[loc_id].tags) & set(cfg.apprentice_tags)),
                    f"{where}：收徒地點 {loc_id} 不是{'或'.join(cfg.apprentice_tags)}",
                )

    cfg = c.config
    for action in ("explore", "train", "socialize"):
        need(action in cfg.action_cost, f"config.action_cost 缺少 {action}")
    for stat in STATS:
        need(stat in cfg.start_stats, f"config.start_stats 缺少 {stat}")
    known("config.starter_skills", cfg.starter_skills, c.skills, "武學")
    if cfg.player_innate:
        known("config.player_innate", [cfg.player_innate], c.skills, "武學")
    known("config.start_companions", cfg.start_companions, c.characters, "人物")
    known("config.vision_skills", cfg.vision_skills, c.skills, "武學")
    known("config.player_aptitude", cfg.player_aptitude, ("剛", "柔", "快", "巧"), "流派")
    for key in cfg.start_companions:
        if key in c.characters:
            need(c.characters[key].tier != "敵", f"config.start_companions：{key} 是敵人，不是同伴")
    need(
        bool(cfg.team_counts) and len(cfg.team_counts) == len(cfg.command_caps),
        "config.team_counts 與 config.command_caps 要一樣長，而且不能是空的",
    )
    need(
        all(n >= 1 for n in cfg.team_counts) and cfg.team_counts == sorted(cfg.team_counts)
        and cfg.command_caps == sorted(cfg.command_caps),
        "config.team_counts 與 config.command_caps 不能遞減，而且至少要有一隊",
    )
    known("config.apprentice_weights", cfg.apprentice_weights, ("黃", "玄"), "品階")
    need(set(cfg.duplicate_xinde) == set(COMPANION_TIERS), "config.duplicate_xinde 要寫齊天地玄黃")
    need(min(cfg.duplicate_xinde.values(), default=0) >= 0, "config.duplicate_xinde 的心得不能是負的")
    rates = cfg.gacha_rates
    need(
        set(rates) == set(COMPANION_TIERS) and min(rates.values(), default=0) >= 0 and abs(sum(rates.values()) - 100) < 1e-6,
        "config.gacha_rates 要寫齊天地玄黃、不能是負的，加起來是 100（%）",
    )
    for tier in COMPANION_TIERS:
        if rates.get(tier, 0) > 0:
            need(
                any(ch.tier == tier and in_gacha_pool(ch) for ch in c.characters.values()),
                f"config.gacha_rates：{tier}品的機率大於 0，卡池裡卻沒有{tier}品（人物的 sources 要有「招賢」）",
            )
    need(rates.get(COMPANION_TIERS[0], 0) > 0, "config.gacha_rates：天品的機率要大於 0（保底必得天品）")
    need(cfg.gacha_ten_floor in COMPANION_TIERS, f"config.gacha_ten_floor：未知的品階 {cfg.gacha_ten_floor}")
    need(set(cfg.gacha_silver) == set(COMPANION_TIERS), "config.gacha_silver 要寫齊天地玄黃")
    need(min(cfg.gacha_silver.values(), default=0) >= 0, "config.gacha_silver 的銀兩不能是負的")
    need(min(cfg.gacha_single, cfg.gacha_ten, cfg.gacha_pity) >= 1, "config.gacha_single、gacha_ten、gacha_pity 至少要是 1")
    need(cfg.test_yuanbao >= 1, "config.test_yuanbao 至少要是 1")
    need(0 <= cfg.gacha_xinde_half <= cfg.gacha_xinde_cap, "config.gacha_xinde_half 要在 0 到 gacha_xinde_cap 之間")
    known("config.provisional", cfg.provisional, Config.model_fields, "設定")

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
                known(cw, [ch.combat], c.squads, "敵方隊伍")
            if ch.check:
                known(cw, [ch.check.stat], STATS, "屬性")
        recruits = {eff.recruit for ch in ev.choices for eff in (ch.effect, ch.fail_effect) if eff.recruit}
        for cid in sorted(recruits):
            need(
                cid in ev.condition.members_none,
                f"{where}：結識 {cid} 的事件，condition.members_none 要列出 {cid}（已入門就不該再遇到）",
            )
            bring(cid, "福緣" if ev.fortune else "奇遇" if ev.qiyu else "交遊", where)
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

    for skill in c.skills.values():
        where = f"武學 {skill.id}"
        if skill.kind in ("絕招", "連招"):
            need(skill.chance_base > 0, f"{where}：絕招／連招必須有發動率 chance_base")
        if skill.kind == "心法":
            need(skill.chance_base == 0 and skill.prep == 0, f"{where}：心法不能有發動率或準備回合")
        for eff in skill.effects:
            if eff.kind in ("buff", "debuff"):
                need(eff.stat is not None, f"{where}：{eff.kind} 效果必須指定 stat")
            if eff.kind == "control":
                need(eff.control is not None, f"{where}：control 效果必須指定 control")
    for ch in c.characters.values():
        where = f"人物 {ch.id}"
        for stat in ("str", "agi", "con", "wis"):
            need(stat in ch.stats, f"{where}：stats 缺少 {stat}")
        known(where, ch.aptitude, ("剛", "柔", "快", "巧"), "流派")
        if ch.innate:
            known(where, [ch.innate], c.skills, "武學")
        if ch.sect:
            known(where, [ch.sect], c.sects, "門派")
        if ch.tier == "敵":
            need(
                ch.command is None and not ch.sources and not ch.recruit_at and ch.trait is None,
                f"{where}：敵人不能有統御、取得管道、收徒地點或特性",
            )
    for squad in c.squads.values():
        where = f"敵方隊伍 {squad.id}"
        known(where, [m.character for m in squad.members], c.characters, "人物")
        if squad.surrender:
            cid = squad.surrender.character
            known(where, [cid], c.characters, "人物")
            if cid in c.characters:
                need(c.characters[cid].tier != "敵", f"{where}：招降的 {cid} 不是同伴")
                bring(cid, "招降", where)
    for ch in c.characters.values():
        if ch.tier != "敵":
            check_companion(ch)
    need(
        any(ch.tier == "地" and "福緣" in ch.sources for ch in c.characters.values()),
        "至少要有一名標了「福緣」的地品（新立門戶福緣要送的人）",
    )

    if errors:
        raise ContentError("內容檔有誤：\n" + "\n".join(errors))
