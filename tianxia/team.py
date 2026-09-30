"""門下與隊伍（sanguo-companions 合併大幅重寫）：玩家與最多 4 個已招募同伴的單一隊伍，
每人最多一門內功、一門武學，練功（自創／鍛鍊）與心得升級，串接 encounter.py 的單次判定。

同伴不再是玩家存檔裡的副本——他們全服唯一，等級/武學是共用資料（world_state.py 的
CompanionProgress），這裡的函式凡是要讀寫同伴進度都要帶一個 WorldStateStore 參數。
"""
from __future__ import annotations

import math
import random

from . import encounter
from .martial_arts import MAX_LEVEL, MartialArt, generate_from_name, historical_art
from .models import Content, Squad
from .state import PLAYER, MAX_TEAM_COMPANIONS, GameState
from .world_state import CompanionProgress, WorldStateStore

ESTIMATE_RUNS = 40
ESTIMATE_SEED = 20260929  # 固定種子：同樣的情況每次都算出同樣的勝算，畫面不會跳動
WIN_TIERS = {"大勝", "險勝"}
DRAW_TIERS = {"僵持"}
ODDS = ((90, "穩勝"), (65, "有把握"), (35, "五五波"), (10, "凶險"))  # 勝率（%）門檻；再低就是必敗


COMBAT_STATS = ("str", "agi", "con", "wis")  # Check 系統（辦事/修行類事件選項）用的屬性；跟遭遇/劇情戰的
# 判定（encounter.py，威力/屬性相剋）無關，見設計文件六.3


def member_name(state: GameState, content: Content, key: str) -> str:
    return state.player.name if key == PLAYER else content.characters[key].name


def member_stats(state: GameState, content: Content, world: WorldStateStore, key: str) -> dict[str, float]:
    if key == PLAYER:
        base = {k: float(state.player.stats.get(k, 0)) for k in COMBAT_STATS}
        growth, level = content.config.player_growth, state.player.member.level
    else:
        character = content.characters[key]
        base, growth = dict(character.stats), character.growth
        level = world.get_companion(key).level
    return {k: base[k] + growth.get(k, 0.0) * (level - 1) for k in COMBAT_STATS}


def check_actor(state: GameState, content: Content, world: WorldStateStore, check) -> str:
    """檢定由誰出手：本人檢定，或檢定的是銀兩、名望這類只有本人才有的屬性時，一律本人；
    隊伍檢定取本隊中這項屬性目前數值最高的人，同分時本人優先、其餘依隊伍順序。"""
    if check.by == "self" or check.stat not in COMBAT_STATS:
        return PLAYER
    keys = team_keys(state)
    return max(keys, key=lambda k: member_stats(state, content, world, k)[check.stat])


def check_value(state: GameState, content: Content, world: WorldStateStore, key: str, stat: str) -> float:
    if stat in COMBAT_STATS:
        return member_stats(state, content, world, key)[stat]
    return float(state.player.stats.get(stat, 0))


def team_keys(state: GameState) -> list[str]:
    """本隊成員：玩家本人在最前，其餘是目前帶著出戰的同伴（最多 MAX_TEAM_COMPANIONS 位）。"""
    return [PLAYER] + list(state.player.team)


def resolve_art(skill_id: str | None, content: Content, world: WorldStateStore) -> MartialArt | None:
    """skill_id 可能指向內容裡的本命武學（歷史人物固定武學）或玩家自創、存在共用世界狀態
    裡的武學（見設計文件六.2；自創功法的 id 就是它的名字，兩邊用同一個 dict 鍵）。"""
    if skill_id is None:
        return None
    if skill_id in content.skills:
        s = content.skills[skill_id]
        return historical_art(skill_id, s.name, s.kind, s.attribute)
    return world.read().created_skills.get(skill_id)


def team_arts(state: GameState, content: Content, world: WorldStateStore) -> dict[str, MartialArt]:
    """本隊每個人的內功/武學，蒐集成一份 id -> MartialArt 給 encounter.py 用。"""
    arts: dict[str, MartialArt] = {}
    ids = {state.player.member.neigong_id, state.player.member.wugong_id}
    shared = world.read()
    for key in state.player.team:
        progress = shared.companions.get(key, CompanionProgress())
        ids |= {progress.neigong_id, progress.wugong_id}
    for skill_id in ids:
        if skill_id and skill_id not in arts:
            art = resolve_art(skill_id, content, world)
            if art:
                arts[skill_id] = art
    return arts


def team_participants(state: GameState, world: WorldStateStore) -> list:
    """本隊每個人的「威力貢獻者」物件（玩家的 Member、同伴的 CompanionProgress），
    直接餵給 encounter.team_power——兩者欄位形狀相同（見 encounter.HasMartialArts）。"""
    shared = world.read()
    return [state.player.member] + [shared.companions.get(k, CompanionProgress()) for k in state.player.team]


# ── 隊伍組成 ─────────────────────────────────────────────


def add_to_team(state: GameState, companion_id: str) -> list[str]:
    if companion_id in state.player.team:
        return []
    if len(state.player.team) >= MAX_TEAM_COMPANIONS:
        return [f"隊伍已經滿了（最多帶 {MAX_TEAM_COMPANIONS} 個夥伴），先讓someone離隊才能換人。"]
    state.player.team.append(companion_id)
    return []


def remove_from_team(state: GameState, companion_id: str) -> list[str]:
    if companion_id in state.player.team:
        state.player.team.remove(companion_id)
    return []


# ── 練功：自創功法／鍛鍊（設計文件六.2）──────────────────────


def create_skill(
    state: GameState, content: Content, world: WorldStateStore, name: str, kind: str,
) -> tuple[MartialArt | None, str]:
    """自創功法：名字即配方（martial_arts.generate_from_name），全服不能重名。成功時把
    新武學配進玩家對應的欄位（如果那一欄還空著）並回傳 (art, 訊息)；名字被占用或欄位已經
    有人時回傳 (None, 原因)。"""
    name = name.strip()
    if not name:
        return None, "得先取個名字。"
    member = state.player.member
    slot = "neigong_id" if kind == "內功" else "wugong_id"
    if getattr(member, slot) is not None:
        return None, f"你已經有一門{kind}了，同時只能練一門。"
    if world.is_skill_name_taken(name) or name in content.skills:
        return None, f"【{name}】這個名字已經有人取走了，換一個吧。"
    art = generate_from_name(name, kind, name)
    if not world.claim_skill_name(art):
        return None, f"【{name}】這個名字已經有人取走了，換一個吧。"
    setattr(member, slot, art.id)
    setattr(member, slot.replace("_id", "_level"), 1)
    return art, f"你自創了一門{kind}【{name}】（{art.quality}，屬{art.attribute}）！"


def practice(
    state: GameState, content: Content, world: WorldStateStore, kind: str, rng: random.Random,
) -> list[str]:
    """鍛鍊：目前已學會的內功或武學加深一成，累積受傷風險（設計文件六.2）。"""
    cfg, member = content.config, state.player.member
    slot = "neigong_id" if kind == "內功" else "wugong_id"
    level_slot = slot.replace("_id", "_level")
    skill_id = getattr(member, slot)
    if skill_id is None:
        return [f"你還沒學{kind}，沒東西可以練。"]
    level = getattr(member, level_slot)
    art = resolve_art(skill_id, content, world)
    name = art.name if art else skill_id
    if level >= MAX_LEVEL:
        return [f"【{name}】已經練到第十成，練無可練。"]
    setattr(member, level_slot, level + 1)
    msgs = [f"【{name}】精進至第{level + 1}成。"]
    if rng.random() < cfg.practice_injury_chance:
        now, cap = member_neili(content, member)
        member.neili = max(0.0, now - cfg.practice_injury_amount)
        msgs.append(f"這一番苦練傷了氣血，氣血 -{cfg.practice_injury_amount:.0f}（累積內傷，需要療傷才能回到滿血）。")
    return msgs


def neili_cap(content: Content, level: int) -> float:
    cfg = content.config
    return cfg.neili_base + level * cfg.neili_per_level


def member_neili(content: Content, member) -> tuple[float, float]:
    """回傳（目前氣血, 上限）。member 可以是玩家的 Member 或同伴的 CompanionProgress。"""
    cap = neili_cap(content, member.level)
    return (cap if member.neili is None else min(member.neili, cap)), cap


def heal_cost(content: Content, member) -> int:
    """療傷要多少銀兩：氣血上限跟目前值的差距，換算成內傷點數。"""
    now, cap = member_neili(content, member)
    injury = max(0.0, cap - now)
    return math.ceil(injury * content.config.heal_silver_per_injury / max(1.0, content.config.practice_injury_amount))


def heal(state: GameState, content: Content, member) -> list[str]:
    cost = heal_cost(content, member)
    if cost <= 0:
        return ["氣血無恙，不用療傷。"]
    p = state.player
    if p.stats.get("silver", 0) < cost:
        return [f"銀兩不足：療傷需要 {cost} 兩。"]
    p.stats["silver"] -= cost
    member.neili = None
    return [f"療傷完畢，氣血回滿（銀兩 -{cost}）。"]


# ── 經驗與等級 ────────────────────────────────────────────


def add_exp(content: Content, member, amount: int, name: str) -> list[str]:
    cfg = content.config
    msgs: list[str] = []
    if member.level >= cfg.max_level or amount <= 0:
        return msgs
    member.exp += amount
    while member.exp >= cfg.level_exp * member.level and member.level < cfg.max_level:
        member.exp -= cfg.level_exp * member.level
        member.level += 1
        msgs.append(f"{name}升到第 {member.level} 級！")
    return msgs


def regen_neili(content: Content, member, fraction: float) -> None:
    if member.neili is None:
        return
    _, cap = member_neili(content, member)
    member.neili += cap * fraction
    if member.neili >= cap:
        member.neili = None


# ── 遭遇/劇情戰：串接 encounter.py 的單次判定 ───────────────


def fight(
    state: GameState, content: Content, world: WorldStateStore, squad_id: str, rng: random.Random,
) -> encounter.EncounterResult:
    squad = content.squads[squad_id]
    arts = team_arts(state, content, world)
    power = encounter.team_power(team_participants(state, world), arts, squad.attribute)
    return encounter.resolve_encounter(power, squad.difficulty, rng)


def odds_word(power: float, squad: Squad, rng_seed: int = ESTIMATE_SEED) -> str:
    """依固定種子模擬 ESTIMATE_RUNS 場的結果分佈換算勝算文字（大勝/險勝算勝、僵持算平手）。"""
    rng = random.Random(rng_seed)
    wins = draws = 0
    for _ in range(ESTIMATE_RUNS):
        result = encounter.resolve_encounter(power, squad.difficulty, rng)
        wins += result.tier in WIN_TIERS
        draws += result.tier in DRAW_TIERS
    return _odds_text(wins, draws, ESTIMATE_RUNS)


def _odds_text(wins: int, draws: int, runs: int) -> str:
    if wins * 100 < 35 * runs and draws * 100 >= 50 * runs:
        return "難分勝負"
    for pct, word in ODDS:
        if wins * 100 >= pct * runs:
            return word
    return "必敗"


def estimate(state: GameState, content: Content, world: WorldStateStore, squad_id: str) -> str:
    squad = content.squads[squad_id]
    arts = team_arts(state, content, world)
    power = encounter.team_power(team_participants(state, world), arts, squad.attribute)
    return odds_word(power, squad)
