"""門下與隊伍：人物數值、內力、組隊作戰、經驗、心得升級與散功、武學配置。"""
from __future__ import annotations

import math
import random

from .battle import Art, BattleResult, Eff, Rules, Unit, run_battle
from .models import Check, Content, Skill, Squad
from .state import PLAYER, GameState

COMBAT_STATS = ("str", "agi", "con", "wis")
STYLES = ("剛", "柔", "快", "巧")
APTITUDE = {"S": 1.2, "A": 1.0, "B": 0.85, "C": 0.7}
FREE_SLOTS = 2
MAX_SKILL_LEVEL = 10
MIN_NEILI_RATIO = 0.1  # 內力再低，上陣時也至少有一成：戰敗只會變弱，不會無法行動
ESTIMATE_RUNS = 40
ESTIMATE_SEED = 20260929  # 固定種子：同樣的情況每次都算出同樣的勝算，畫面不會跳動
NEILI_STEPS = 20  # 估勝算時內力以 5% 為一級（無條件捨去），回復中的內力不會每次重畫都重算
ESTIMATE_CACHE_LIMIT = 256
ODDS = ((90, "穩勝"), (65, "有把握"), (35, "五五波"), (10, "凶險"))  # 勝率（%）門檻；再低就是必敗


def skill_value(base: float, top: float | None, level: int) -> float:
    """第 1 成是 base、第 10 成是 top，中間線性。"""
    if top is None:
        return base
    return base + (top - base) * (level - 1) / 9


def art_from_skill(skill: Skill, level: int) -> Art:
    return Art(
        name=skill.name,
        kind=skill.kind,
        style=skill.style,
        chance=skill_value(skill.chance_base, skill.chance_top, level),
        prep=skill.prep,
        effects=[
            Eff(kind=e.kind, value=skill_value(e.base, e.top, level), target=e.target,
                stat=e.stat, control=e.control, rounds=e.rounds)
            for e in skill.effects
        ],
    )


def aptitude_table(grades: dict[str, str]) -> dict[str, float]:
    return {style: APTITUDE[grades.get(style, "B")] for style in STYLES}


def member_name(state: GameState, content: Content, key: str) -> str:
    return state.player.name if key == PLAYER else content.characters[key].name


def innate_of(state: GameState, content: Content, key: str) -> str | None:
    return content.config.player_innate if key == PLAYER else content.characters[key].innate


def member_style(content: Content, key: str) -> tuple[str, dict[str, str]]:
    """（流派, 資質等級）；資質沒列出的流派算 B。"""
    if key == PLAYER:
        return content.config.player_style, content.config.player_aptitude
    character = content.characters[key]
    return character.style, character.aptitude


def slot_skill(state: GameState, key: str, slot: int) -> str | None:
    """某人第 slot 個自選欄（從 0 起算）裡的武學 id；空欄或沒有這一欄時回傳 None。"""
    slots = state.player.loadouts.get(key) or []
    return slots[slot] if 0 <= slot < len(slots) else None


def team_keys(state: GameState, index: int = 0) -> list[str]:
    """第 index 隊（預設本隊）的成員，第一位是隊長；略過已不在門下的人。1c-1 只有本隊會出手。"""
    teams = state.player.teams
    if not 0 <= index < len(teams):
        return []
    return [key for key in teams[index].members if key in state.player.members]


def team_of(state: GameState, key: str) -> int | None:
    """key 在第幾隊（從 0 起算，0 是本隊）；候補（不在任何一隊）時為 None。"""
    return next((i for i, t in enumerate(state.player.teams) if key in t.members), None)


def teammates(state: GameState, key: str) -> list[str]:
    """和 key 同一隊的人（含自己）；候補只有自己。"""
    index = team_of(state, key)
    return [key] if index is None else team_keys(state, index)


def lined_up(state: GameState) -> list[str]:
    """所有隊伍裡的人，依隊伍順序；候補不算。"""
    return [key for index in range(len(state.player.teams)) for key in team_keys(state, index)]


def trait_of(content: Content, key: str) -> str | None:
    """天品的特性（一門心法）；其他人沒有。"""
    return None if key == PLAYER else content.characters[key].trait


def check_actor(state: GameState, content: Content, check: Check) -> str:
    """檢定由誰出手（回傳門下 key）。本人檢定，或檢定的是銀兩、名望這類只有本人才有的屬性時，一律本人；
    隊伍檢定取本隊中這項屬性目前數值（含等級成長）最高的人，同分時本人優先、其餘依隊伍順序。"""
    if check.by == "self" or check.stat not in COMBAT_STATS:
        return PLAYER
    keys = sorted(team_keys(state), key=lambda k: k != PLAYER) or [PLAYER]
    return max(keys, key=lambda k: member_stats(state, content, k)[check.stat])


def check_value(state: GameState, content: Content, key: str, stat: str) -> float:
    """出手者這項屬性的目前數值：戰鬥屬性含等級成長；其他屬性只有本人有，直接讀本人的。"""
    if stat in COMBAT_STATS:
        return member_stats(state, content, key)[stat]
    return float(state.player.stats.get(stat, 0))


def innate_level(state: GameState, content: Content, key: str) -> int:
    """本人的本命記在已習武學裡；同伴的本命成數記在門下資料裡。"""
    if key == PLAYER:
        return state.player.skills.get(content.config.player_innate, 1)
    return state.player.members[key].innate_level


def member_stats(state: GameState, content: Content, key: str) -> dict[str, float]:
    level = state.player.members[key].level
    if key == PLAYER:
        base = {k: float(state.player.stats.get(k, 0)) for k in COMBAT_STATS}
        growth = content.config.player_growth
    else:
        character = content.characters[key]
        base, growth = dict(character.stats), character.growth
    return grown_stats(base, growth, level)


def grown_stats(base: dict[str, float], growth: dict[str, float], level: int) -> dict[str, float]:
    """第 1 級為基礎值，之後每升一級加上成長量。"""
    return {k: base[k] + growth.get(k, 0.0) * (level - 1) for k in COMBAT_STATS}


def neili_cap(content: Content, stats: dict[str, float], level: int) -> float:
    cfg = content.config
    return cfg.neili_base + stats["con"] * cfg.neili_per_con + level * cfg.neili_per_level


def member_neili(state: GameState, content: Content, key: str) -> tuple[float, float]:
    """回傳（目前內力, 上限）。"""
    member = state.player.members[key]
    cap = neili_cap(content, member_stats(state, content, key), member.level)
    return (cap if member.neili is None else min(member.neili, cap)), cap


def build_unit(state: GameState, content: Content, key: str, leader: bool) -> Unit:
    p = state.player
    stats = member_stats(state, content, key)
    now, cap = member_neili(state, content, key)
    style, grades = member_style(content, key)
    arts = []
    innate = innate_of(state, content, key)
    if innate:
        arts.append(art_from_skill(content.skills[innate], innate_level(state, content, key)))
    trait = trait_of(content, key)
    if trait:
        arts.append(art_from_skill(content.skills[trait], 1))  # 效果固定（內容檢查保證不寫 top）
    for skill_id in p.loadouts.get(key, []):
        if skill_id:
            arts.append(art_from_skill(content.skills[skill_id], p.skills[skill_id]))
    return Unit(
        name=member_name(state, content, key), atk=stats["str"], dfn=stats["con"], spd=stats["agi"],
        wis=stats["wis"], hp=max(now, cap * MIN_NEILI_RATIO), hp_max=cap, style=style,
        aptitude=aptitude_table(grades), arts=arts, leader=leader, key=key,
    )


def enemy_units(content: Content, squad: Squad) -> list[Unit]:
    """敵人的本命成數隨等級提升：第 1 級第 1 成，每 3 級加一成。"""
    units = []
    for i, member in enumerate(squad.members):
        character = content.characters[member.character]
        stats = grown_stats(character.stats, character.growth, member.level)
        cap = neili_cap(content, stats, member.level)
        arts = []
        if character.innate:
            level = min(MAX_SKILL_LEVEL, 1 + member.level // 3)
            arts.append(art_from_skill(content.skills[character.innate], level))
        units.append(Unit(
            name=character.name, atk=stats["str"], dfn=stats["con"], spd=stats["agi"], wis=stats["wis"],
            hp=cap, hp_max=cap, style=character.style, aptitude=aptitude_table(character.aptitude),
            arts=arts, leader=i == 0, key=character.id,
        ))
    return units


def battle_rules(content: Content) -> Rules:
    cfg = content.config
    return Rules(max_rounds=cfg.battle_rounds, atk_factor=cfg.battle_atk_factor, def_factor=cfg.battle_def_factor)


def team_units(state: GameState, content: Content) -> list[Unit]:
    """本隊的戰鬥單位，順序同 team_keys；第一位是隊長。"""
    return [build_unit(state, content, key, leader=i == 0) for i, key in enumerate(team_keys(state))]


def fight(state: GameState, content: Content, squad_id: str, rng: random.Random) -> BattleResult:
    """本隊對上一支敵方隊伍；戰後內力保留剩餘值。戰鬥紀錄由 engine 透過 battlelog 建立。"""
    p = state.player
    squad = content.squads[squad_id]
    result = run_battle(team_units(state, content), enemy_units(content, squad), rng, battle_rules(content))
    for key, hp in zip(team_keys(state), result.hp):
        p.members[key].neili = hp
    return result


# ── 戰前情報：勝算 ─────────────────────────────────────


def odds_word(wins: int, draws: int, runs: int) -> str:
    """依勝率分五段：≥90% 穩勝、≥65% 有把握、≥35% 五五波、≥10% 凶險，其餘必敗；
    勝率 < 35% 且平手率 ≥ 50% 時改判「難分勝負」（多半打不完，不算真的必敗）。"""
    if wins * 100 < 35 * runs and draws * 100 >= 50 * runs:
        return "難分勝負"
    for pct, word in ODDS:
        if wins * 100 >= pct * runs:
            return word
    return "必敗"


def _estimate_units(state: GameState, content: Content) -> list[Unit]:
    """估勝算用的我方單位：和實戰相同，只是內力捨去到 5% 的整數倍（最少仍有一成）。"""
    units = team_units(state, content)
    for u in units:
        step = math.floor(u.hp / u.hp_max * NEILI_STEPS) / NEILI_STEPS
        u.hp = u.hp_max * max(MIN_NEILI_RATIO, step)
    return units


def estimate(state: GameState, content: Content, squad_id: str, cache: dict[str, str] | None = None) -> str:
    """以目前的隊伍、配置、成數、等級與內力，用固定種子模擬 ESTIMATE_RUNS 場，回傳勝算（平手不算勝）。

    cache 的鍵是「我方單位、敵方單位、戰鬥規則」的完整內容，這些都沒變時直接用上次的結果；
    不會動到遊戲本身的亂數。
    """
    squad = content.squads[squad_id]
    rules = battle_rules(content)
    key = repr((squad_id, _estimate_units(state, content), enemy_units(content, squad), rules))
    if cache is not None and key in cache:
        return cache[key]
    rng = random.Random(ESTIMATE_SEED)
    wins = draws = 0
    for _ in range(ESTIMATE_RUNS):
        result = run_battle(_estimate_units(state, content), enemy_units(content, squad), rng, rules)
        wins += result.outcome == "win"
        draws += result.outcome == "draw"
    word = odds_word(wins, draws, ESTIMATE_RUNS)
    if cache is not None:
        if len(cache) >= ESTIMATE_CACHE_LIMIT:
            cache.clear()
        cache[key] = word
    return word


def add_exp(state: GameState, content: Content, amount: int) -> list[str]:
    """本隊（打這一場的隊伍）的每個人都獲得經驗；候補與其他隊伍不長經驗。"""
    cfg, p = content.config, state.player
    msgs = []
    for key in team_keys(state):
        member = p.members[key]
        if member.level >= cfg.max_level or amount <= 0:
            continue
        member.exp += amount
        while member.exp >= cfg.level_exp * member.level and member.level < cfg.max_level:
            member.exp -= cfg.level_exp * member.level
            member.level += 1
            msgs.append(f"{member_name(state, content, key)}升到第 {member.level} 級！")
    return msgs


def regen_neili(state: GameState, content: Content, fraction: float) -> None:
    """每個人回復上限的 fraction；回滿時記為 None。"""
    for key, member in state.player.members.items():
        if member.neili is None:
            continue
        _, cap = member_neili(state, content, key)
        member.neili += cap * fraction
        if member.neili >= cap:
            member.neili = None


# ── 心得：升級與散功 ─────────────────────────────────────


def upgrade_cost(content: Content, level: int) -> int:
    return content.config.xinde_cost_factor * level


def _target_info(state: GameState, content: Content, target: str) -> tuple[str, int] | None:
    """target 是 "skill:<武學id>" 或 "innate:<同伴key>"；回傳（武學名稱, 目前成數）。"""
    kind, _, ident = target.partition(":")
    p = state.player
    if kind == "skill" and ident in p.skills:
        return content.skills[ident].name, p.skills[ident]
    if kind == "innate" and ident in p.members and ident != PLAYER:
        innate = innate_of(state, content, ident)
        if innate:
            return content.skills[innate].name, p.members[ident].innate_level
    return None


def target_level(state: GameState, content: Content, target: str) -> int | None:
    """target 目前的成數；沒有這門武學時回傳 None。"""
    info = _target_info(state, content, target)
    return info[1] if info else None


def target_name(state: GameState, content: Content, target: str) -> str | None:
    """target 的武學名稱；沒有這門武學時回傳 None。"""
    info = _target_info(state, content, target)
    return info[0] if info else None


def _set_level(state: GameState, target: str, level: int) -> None:
    kind, _, ident = target.partition(":")
    if kind == "skill":
        state.player.skills[ident] = level
    else:
        state.player.members[ident].innate_level = level


def upgrade(state: GameState, content: Content, target: str) -> list[str]:
    info = _target_info(state, content, target)
    if info is None:
        return ["沒有這門武學。"]
    name, level = info
    if level >= MAX_SKILL_LEVEL:
        return [f"【{name}】已經練到第十成。"]
    cost = upgrade_cost(content, level)
    p = state.player
    if p.stats.get("xinde", 0) < cost:
        return [f"心得不足：【{name}】升到第{level + 1}成需要 {cost}。"]
    p.stats["xinde"] -= cost
    _set_level(state, target, level + 1)
    return [f"【{name}】精進至第{level + 1}成（心得 −{cost}）。"]


def is_innate(content: Content, target: str) -> bool:
    """本人的本命（skill:<player_innate>）或同伴的本命（innate:<key>）。"""
    kind, _, ident = target.partition(":")
    return kind == "innate" or (kind == "skill" and ident == content.config.player_innate)


def innate_target(state: GameState, content: Content, key: str) -> str | None:
    """這個人的本命在武學庫裡的 target；沒有本命時回傳 None。"""
    if key == PLAYER:
        innate = content.config.player_innate
        return f"skill:{innate}" if innate and innate in state.player.skills else None
    return f"innate:{key}" if key in state.player.members and innate_of(state, content, key) else None


def dispel_refund(content: Content, level: int) -> int:
    """從第 level 成散回第一成時返還的心得。"""
    spent = sum(upgrade_cost(content, n) for n in range(1, level))
    return int(spent * content.config.dispel_refund)


def dispel(state: GameState, content: Content, target: str) -> list[str]:
    info = _target_info(state, content, target)
    if info is None:
        return ["沒有這門武學。"]
    if is_innate(content, target):
        return ["本命武學不能散功。"]
    name, level = info
    if level <= 1:
        return [f"【{name}】尚在第一成，無功可散。"]
    refund = dispel_refund(content, level)
    _set_level(state, target, 1)
    state.player.stats["xinde"] = state.player.stats.get("xinde", 0) + refund
    return [f"你散去【{name}】的功力，退回第一成，返還心得 {refund}。"]


def upgrade_options(state: GameState, content: Content) -> list[tuple[str, str]]:
    """（顯示文字, target）：已習武學在前，同伴本命在後。"""
    p = state.player
    opts = [(f"{content.skills[sid].name} 第{level}成", f"skill:{sid}") for sid, level in p.skills.items()]
    for key in p.members:
        if key != PLAYER:
            info = _target_info(state, content, f"innate:{key}")
            if info:
                opts.append((f"{member_name(state, content, key)}・本命{info[0]} 第{info[1]}成", f"innate:{key}"))
    return opts


# ── 武學配置 ─────────────────────────────────────────────


def set_loadout(state: GameState, content: Content, key: str, slot: int, skill_id: str | None) -> list[str]:
    """同一門武學同時只能配給一個人（跨隊也一樣），配給新的人時會從原本的人身上移走；
    某人的本命武學不能再配給他同一隊的人（各隊各自判斷，候補只看自己）。"""
    p = state.player
    if key not in p.members or not 0 <= slot < FREE_SLOTS:
        return ["沒有這個武學欄。"]
    if skill_id is not None:
        if skill_id not in p.skills:
            return ["你尚未習得這門武學。"]
        if any(innate_of(state, content, k) == skill_id for k in teammates(state, key)):
            return [f"【{content.skills[skill_id].name}】是隊中某人的本命武學，不能重複配置。"]
        for other_key, slots in p.loadouts.items():
            for i, sid in enumerate(slots):
                if sid == skill_id and (other_key, i) != (key, slot):
                    slots[i] = None
    slots = p.loadouts.setdefault(key, [None] * FREE_SLOTS)
    slots[slot] = skill_id
    label = content.skills[skill_id].name if skill_id else "（空）"
    return [f"{member_name(state, content, key)}的第{slot + 1}個武學欄：{label}"]
