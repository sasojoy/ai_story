"""傳功門下（企劃者 2026-10-14「心得大量溢出，需要想個可以大量消耗的地方」，決策卡選「傳功門下」；數字在 Config.chuangong）：
用心得替同伴、部下練武學、加屬性。隊伍變強，本人的威力一點都不動（本人那兩門照舊自己練成，team.practice）。

- 同伴：練他自己的內功、武學（CompanionProgress 的 neigong_level／wugong_level，第 N 成升一成 mate_art_xinde × N）；
  傳臂力、身法、根骨（CompanionProgress.taught，第 k 點 mate_stat_xinde × k，k 算三項合計；每項最多 mate_stat_max 點）。
  悟性不傳：同伴不修練、不悟意境、事件檢定只看本人，傳了沒有用。傳過的功記在他身上（全服共用），被放走、被別人招去都帶著走。
- 部下：在照等級長的那條線（team.follower_line）之上多練一成（第 k 成 follower_cheng_xinde × k，線＋多練的最多十成）；
  傳臂力（第 k 點 follower_str_xinde × k，臂力最多 stat_cap）。記在 PlayerState.follower_drill（跟 followers 同位置）。
  全服決戰的份量照部下的人數算（Game._battle_troops），不看部下的威力，所以傳功不動決戰的份量；同伴本來就不進決戰。

修練頁名冊點一個人，人物卡底下一排「傳功」鈕（lessons），寫價錢與效果；按下去走 Game.chuangong（MENXIA_ACTIONS["chuangong"]）。
整季機器人與假人照 cheapest 挑最便宜的一項（bot.teach）。只 import models、state、world_state、martial_arts、team。"""
from __future__ import annotations

from dataclasses import dataclass

from . import team
from .martial_arts import MAX_LEVEL, power_at
from .models import Content
from .state import PLAYER, FollowerDrill, GameState
from .world_state import WorldStateStore

MATE_STATS = ("str", "agi", "con")  # 同伴傳得了的屬性（悟性不傳，見模組說明；博聞不進戰力）
FOLLOWER_STATS = ("str",)  # 部下只吃臂力（team.follower_boost）
ARTS = ("neigong", "wugong")  # 練武學的那兩項：內功、武學
ART_KIND = {"neigong": "內功", "wugong": "武學"}
STAT_EFFECT = {  # 傳一點屬性的效果那一句（跟 team.STAT_USES 同一套規則）
    "str": "武學威力 +{pct}",
    "agi": "一場仗少扣一點氣血",
    "con": "內功威力與氣血上限 +{pct}",
}

OFF = "傳功的規矩這一季沒開。"
NOT_YOURS = "名冊裡沒有這個人。"
SELF = "本人的功夫自己練（練成），傳功是傳給同伴與部下的。"
NO_ART = "他還沒有{kind}，沒東西可練。"
ART_FULL = "【{name}】已經練到第十成。"
STAT_FULL = "{stat}已經傳滿 {cap} 點。"
STRENGTH_FULL = "臂力已經到頂（{cap}）。"
LINE_FULL = "武學已經到第十成，再多練也長不上去。"
SHORT = "心得不足：要 {price} 點，你只有 {have} 點。"
UNKNOWN = "傳不了這一項。"
ART_DONE = "你把心得傳給{name}：【{art}】精進至第{level}成。"
STAT_DONE = "你把心得傳給{name}：{stat} +1（現在 {value}）。"
LINE_DONE = "你帶著{name}多練了一成：【{art}】第{level}成（照你的等級是第{line}成）。"


@dataclass(frozen=True)
class Lesson:
    """名冊上一個人的一項傳功：what 是 "neigong"／"wugong"（練成）或屬性鍵；label 寫在鈕上（含價錢），effect 寫這一下多了什麼；
    problem 是按不下去的原因（None＝按得下去）。price 是 None 時這一項已經滿了。"""

    key: str
    what: str
    label: str
    effect: str
    price: int | None
    problem: str | None


def on(content: Content) -> bool:
    return content.config.chuangong.enabled


def _owned(state: GameState, world: WorldStateStore, key: str) -> bool:
    if key.startswith(team.FOLLOWER_KEY):
        return False
    return world.get_companion(key).owner == state.player.name


def _pct(value: float) -> str:
    return f"{value:.0%}"


def _short(state: GameState, price: int) -> str | None:
    have = state.player.stats.get("xinde", 0)
    return SHORT.format(price=price, have=have) if have < price else None


def mate_lessons(state: GameState, content: Content, world: WorldStateStore, key: str) -> list[Lesson]:
    """一位同伴的傳功：內功、武學各練一成，臂力、身法、根骨各傳一點。"""
    cfg, rule = content.config, content.config.chuangong
    progress = world.get_companion(key)
    name = content.characters[key].name
    out = []
    for what in ARTS:
        art_id, level = getattr(progress, f"{what}_id"), getattr(progress, f"{what}_level")
        kind = ART_KIND[what]
        art = team.resolve_art(art_id, content, world)
        if art is None:
            out.append(Lesson(key, what, f"練{kind}", "", None, NO_ART.format(kind=kind)))
            continue
        if level >= MAX_LEVEL:
            out.append(Lesson(key, what, f"練{kind}（已滿）", "", None, ART_FULL.format(name=art.name)))
            continue
        price = rule.mate_art_xinde * level
        gain = power_at(art, level + 1) - power_at(art, level)
        out.append(Lesson(key, what, f"練{kind}・{price} 心得", f"【{art.name}】第{level}成→第{level + 1}成，威力 +{gain:.1f}",
                          price, _short(state, price)))
    taught = sum(progress.taught.values())
    stats = team.member_stats(state, content, world, key)
    for stat in MATE_STATS:
        label = cfg.stat_names.get(stat, stat)
        if progress.taught.get(stat, 0) >= rule.mate_stat_max:
            out.append(Lesson(key, stat, f"傳{label}（已滿）", "", None, STAT_FULL.format(stat=label, cap=rule.mate_stat_max)))
            continue
        price = rule.mate_stat_xinde * (taught + 1)
        effect = f"{name}的{label} {stats[stat]:.0f}→{stats[stat] + 1:.0f}：" + STAT_EFFECT[stat].format(pct=_pct(cfg.stat_bonus_per_point))
        out.append(Lesson(key, stat, f"傳{label}・{price} 心得", effect, price, _short(state, price)))
    return out


def follower_lessons(state: GameState, content: Content, key: str) -> list[Lesson]:
    """一名部下的傳功：武學多練一成、臂力傳一點。"""
    cfg, rule = content.config, content.config.chuangong
    follower = dict(team.follower_rows(state, content)).get(key)
    if follower is None:
        return []
    drill = team.drill_of(state, key)
    out = []
    level = team.follower_level(state, content, follower, key)
    if level >= MAX_LEVEL:
        out.append(Lesson(key, "wugong", "多練一成（已滿）", "", None, LINE_FULL))
    else:
        price = rule.follower_cheng_xinde * (drill.cheng + 1)
        out.append(Lesson(key, "wugong", f"多練一成・{price} 心得", f"武學第{level}成→第{level + 1}成（照你的等級是第"
                          f"{team.follower_line(state, content, follower)}成，多練的跟著帶上去）", price, _short(state, price)))
    strength = team.follower_strength(content, follower, drill)
    label = cfg.stat_names.get("str", "臂力")
    if strength >= cfg.stat_cap:
        out.append(Lesson(key, "str", f"傳{label}（已滿）", "", None, STRENGTH_FULL.format(cap=cfg.stat_cap)))
    else:
        price = rule.follower_str_xinde * (drill.arm + 1)
        out.append(Lesson(key, "str", f"傳{label}・{price} 心得",
                          f"{label} {strength}→{strength + 1}：" + STAT_EFFECT["str"].format(pct=_pct(cfg.stat_bonus_per_point)),
                          price, _short(state, price)))
    return out


def lessons(state: GameState, content: Content, world: WorldStateStore, key: str | None) -> list[Lesson]:
    """名冊上這個人（同伴或部下）的傳功鈕；本人、別人的同伴、開關關著是空的。"""
    if key is None or key == PLAYER or not on(content):
        return []
    if key.startswith(team.FOLLOWER_KEY):
        return follower_lessons(state, content, key)
    if key not in content.characters or not _owned(state, world, key):
        return []
    return mate_lessons(state, content, world, key)


def teach(state: GameState, content: Content, world: WorldStateStore, key: str, what: str) -> list[str]:
    """傳一次功：照 lessons 那一項驗（同一個判斷，鈕上寫的跟按下去回的是同一句），扣心得、寫進去。回傳訊息。"""
    if not on(content):
        return [OFF]
    if key == PLAYER:
        return [SELF]
    rows = lessons(state, content, world, key)
    if not rows:
        return [NOT_YOURS]
    lesson = next((row for row in rows if row.what == what), None)
    if lesson is None:
        return [UNKNOWN]
    if lesson.problem is not None:
        return [lesson.problem]
    p = state.player
    p.stats["xinde"] = p.stats.get("xinde", 0) - lesson.price
    tail = f"心得 -{lesson.price}"
    if key.startswith(team.FOLLOWER_KEY):
        follower = dict(team.follower_rows(state, content))[key]
        index = int(key[len(team.FOLLOWER_KEY):])
        while len(p.follower_drill) <= index:
            p.follower_drill.append(FollowerDrill())
        drill = p.follower_drill[index]
        if what == "wugong":
            drill.cheng += 1
            art = team.resolve_art(follower.wugong, content, world)
            return [LINE_DONE.format(name=follower.name, art=art.name if art else follower.wugong,
                                     level=team.follower_level(state, content, follower, key),
                                     line=team.follower_line(state, content, follower)), tail]
        drill.arm += 1
        return [STAT_DONE.format(name=follower.name, stat=content.config.stat_names.get("str", "臂力"),
                                 value=team.follower_strength(content, follower, drill)), tail]
    name = content.characters[key].name
    if what in ARTS:
        def up(progress) -> None:
            setattr(progress, f"{what}_level", getattr(progress, f"{what}_level") + 1)

        progress = world.update_companion(key, up)
        art = team.resolve_art(getattr(progress, f"{what}_id"), content, world)
        return [ART_DONE.format(name=name, art=art.name if art else "", level=getattr(progress, f"{what}_level")), tail]

    def give(progress) -> None:
        progress.taught[what] = progress.taught.get(what, 0) + 1

    world.update_companion(key, give)
    value = team.member_stats(state, content, world, key)[what]
    return [STAT_DONE.format(name=name, stat=content.config.stat_names.get(what, what), value=f"{value:.0f}"), tail]


def cheapest(state: GameState, content: Content, world: WorldStateStore) -> Lesson | None:
    """名冊上所有同伴、部下裡最便宜、按得下去的一項（整季機器人與假人用）；同價照名冊的先後。沒有是 None。不擲亂數。"""
    best = None
    for _, key in _roster(state, content, world):
        for lesson in lessons(state, content, world, key):
            if lesson.problem is None and lesson.price is not None and (best is None or lesson.price < best.price):
                best = lesson
    return best


def _roster(state: GameState, content: Content, world: WorldStateStore) -> list[tuple[str, str]]:
    from . import roster  # roster import 了很多東西（ranger、rules…），放在這裡免得循環

    return [(label, key) for label, key in roster.roster_lines(state, content, world) if key != PLAYER]
