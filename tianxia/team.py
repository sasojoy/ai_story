"""門下與隊伍（sanguo-companions 合併大幅重寫）：玩家與最多 4 個已招募同伴的單一隊伍，
每人最多一門內功、一門武學，練功（自創／鍛鍊）與心得升級，串接 encounter.py 的單次判定。

同伴不再是玩家存檔裡的副本——他們全服唯一，等級/武學是共用資料（world_state.py 的
CompanionProgress），這裡的函式凡是要讀寫同伴進度都要帶一個 WorldStateStore 參數。
"""
from __future__ import annotations

import math
import random

from . import calendar, encounter
from .martial_arts import MAX_LEVEL, MartialArt, generate_from_name, historical_art
from .models import Content, FollowerDef, Squad
from .state import PLAYER, MAX_TEAM_COMPANIONS, GameState, Member
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
        return historical_art(skill_id, s.name, s.kind, s.attribute, s.quality)
    return world.get_skill(skill_id)


def team_arts(state: GameState, content: Content, world: WorldStateStore) -> dict[str, MartialArt]:
    """本隊每個人的內功/武學（含部下），蒐集成一份 id -> MartialArt 給 encounter.py 用。"""
    arts: dict[str, MartialArt] = {}
    ids = {state.player.member.neigong_id, state.player.member.wugong_id}
    ids |= {unit.wugong_id for unit in follower_units(state, content)}
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
    直接餵給 encounter.team_power——兩者欄位形狀相同（見 encounter.HasMartialArts）。部下另外接在後面（follower_units）。"""
    shared = world.read()
    return [state.player.member] + [shared.companions.get(k, CompanionProgress()) for k in state.player.team]


FOLLOWER_KEY = "follower:"  # 名冊裡部下的 key：follower:<在 PlayerState.followers 裡的位置>（同一種部下可以有兩個）


def follower_rows(state: GameState, content: Content) -> list[tuple[str, FollowerDef]]:
    """部下（計畫 T5）：(名冊的 key, 模板)。第一季才有，開關關著時是空的。"""
    if not state.player.followers or not calendar.season_one_on(state.world, content):  # 同 rules.season_one（rules 會 import team）
        return []
    return [(f"{FOLLOWER_KEY}{i}", content.followers[fid]) for i, fid in enumerate(state.player.followers)
            if fid in content.followers]


def follower_units(state: GameState, content: Content) -> list[Member]:
    """部下照模板建成跟 Member 同形狀的威力貢獻者（武學照模板、沒有內功）。只算威力：不在 team_keys 裡，
    所以不擋檢定、不扣氣血（take_encounter_toll）、不吃經驗；氣血係數一律 1.0。"""
    return [Member(wugong_id=f.wugong, wugong_level=f.wugong_level) for _, f in follower_rows(state, content)]


def _fighters(state: GameState, content: Content, world: WorldStateStore) -> tuple[list, list[float]]:
    """打一場的陣容與各自的氣血係數：本人、出戰的同伴，再加上部下（滿血）。"""
    followers = follower_units(state, content)
    return team_participants(state, world) + followers, team_conditions(state, content, world) + [1.0] * len(followers)


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
    art = generate_from_name(name, kind, name, world.read().tianji)
    if not world.claim_skill_name(art):
        return None, f"【{name}】這個名字已經有人取走了，換一個吧。"
    setattr(member, slot, art.id)
    setattr(member, slot.replace("_id", "_level"), 1)
    return art, f"你自創了一門{kind}【{name}】（{art.quality}，屬{art.attribute}）！"


def switch_art(state: GameState, content: Content, world: WorldStateStore, art_id: str) -> list[str]:
    """改練：把功法庫裡的一門換上身，被換下來的回庫，兩邊的熟練度**各自保留**。

    煉製（craft.py）會讓同一個人擁有超過一門內功／武學，但每人同時只能練一門（設計文件
    六.4），所以需要這個動作——在這之前整個 team.py 連散功都沒有，煉出絕學卻裝不上去。
    熟練度存在 `PlayerState.art_levels`（換下來時寫進去、換上去時取出來），所以換回來不用
    重練；舊存檔沒有這個欄位時，庫裡的功法一律從第一成算起。
    """
    p = state.player
    if art_id not in p.arts:
        return ["你的功法庫裡沒有這一門。"]
    art = resolve_art(art_id, content, world)
    if art is None:
        return ["（找不到這門功法的資料。）"]
    member = p.member
    slot = "neigong_id" if art.kind == "內功" else "wugong_id"
    level_slot = slot.replace("_id", "_level")
    current_id = getattr(member, slot)
    msgs = []
    if current_id is not None:
        p.art_levels[current_id] = getattr(member, level_slot)
        p.arts.append(current_id)
        current = resolve_art(current_id, content, world)
        msgs.append(f"你收起了【{current.name if current else current_id}】（第{p.art_levels[current_id]}成，再換回來不用重練）。")
    p.arts.remove(art_id)
    level = p.art_levels.get(art_id, 1)
    setattr(member, slot, art_id)
    setattr(member, level_slot, level)
    msgs.append(f"你改練【{art.name}】（{art.quality}・屬{art.attribute}），目前第{level}成。")
    return msgs


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
        now, _cap = member_neili(content, member)
        member.injury += cfg.practice_injury_amount
        member.neili = max(0.0, now - cfg.practice_injury_amount)
        msgs.append(f"這一番苦練傷了氣血，氣血 -{cfg.practice_injury_amount:.0f}（累積內傷，需要療傷才能回到滿血）。")
    return msgs


def neili_cap(content: Content, level: int) -> float:
    cfg = content.config
    return cfg.neili_base + level * cfg.neili_per_level


MIN_CEILING_RATIO = 0.1  # 內傷再重，能回到的氣血上蓋也不低於上限的一成（氣血設計 §1.3：再低也照樣能出戰）


def neili_ceiling(content: Content, member) -> float:
    """內傷之後氣血自己能回到哪裡（上限 − 內傷，但不低於上限的一成）。"""
    cap = neili_cap(content, member.level)
    return max(cap * MIN_CEILING_RATIO, cap - getattr(member, "injury", 0.0))


def member_neili(content: Content, member) -> tuple[float, float]:
    """回傳（目前氣血, 上限）。member 可以是玩家的 Member 或同伴的 CompanionProgress。

    `neili is None` 代表「回滿了」——有內傷時的「滿」是上蓋（上限 − 內傷），不是上限本身。
    """
    cap = neili_cap(content, member.level)
    ceiling = neili_ceiling(content, member)
    now = ceiling if member.neili is None else min(member.neili, ceiling)
    return now, cap


def heal_cost(content: Content, member) -> int:
    """療傷要多少銀兩：按內傷點數計價（氣血設計 §二，預設每 2 點內傷 1 兩，無條件進位）。

    刻意只看內傷、不看「目前氣血離上限多遠」——輕傷本來就會自己回，付錢去買它沒有意義
    （改之前就是這樣：療傷等於花錢跳過兩小時的等待，而內傷根本不存在）。
    """
    injury = max(0.0, getattr(member, "injury", 0.0))
    return math.ceil(injury / max(1.0, content.config.heal_neili_per_silver))


def heal(state: GameState, content: Content, member) -> list[str]:
    cost = heal_cost(content, member)
    if cost <= 0:
        return ["氣血無恙，不用療傷。"]
    p = state.player
    if p.stats.get("silver", 0) < cost:
        return [f"銀兩不足：療傷需要 {cost} 兩。"]
    p.stats["silver"] -= cost
    healed = member.injury
    member.injury = 0.0
    member.neili = None
    return [f"療傷完畢，內傷 -{healed:.0f}、氣血回滿（銀兩 -{cost}）。"]


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


def add_team_exp(state: GameState, content: Content, world: WorldStateStore, amount: int) -> list[str]:
    """本隊每個人（本人與帶著出戰的同伴）各得 amount 經驗，照同一套 add_exp 規則升級；回傳升級訊息，
    本人在前、同伴照隊伍順序（試玩回饋 FB-002：戰報一直寫「經驗 +N（每人）」，以前只有本人真的拿到）。

    同伴的等級與經驗存在全服共用的 CompanionProgress（world.update_companion 當場寫回共用世界，
    跟著那一筆交易存檔），所以換頁、重新登入都還在；換季時跟其他同伴進度一起清空。氣血上限
    （neili_cap：基礎＋每級加成）由等級算出來，升級就跟著變高（氣血設計 A1：等級只買氣血上限）；
    目前氣血不變，不順便回血。"""
    msgs = add_exp(content, state.player.member, amount, state.player.name)
    for companion_id in state.player.team:
        name = content.characters[companion_id].name
        levels: list[str] = []
        world.update_companion(companion_id, lambda progress: levels.extend(add_exp(content, progress, amount, name)))
        msgs += levels
    return msgs


def regen_neili(content: Content, member, fraction: float) -> None:
    """氣血隨時間回復——只回到上蓋（上限 − 內傷），內傷那部分要療傷才清得掉。"""
    if member.neili is None:
        return
    cap = neili_cap(content, member.level)
    ceiling = neili_ceiling(content, member)
    member.neili += cap * fraction  # 回復速度照上限算，所以內傷不會讓回復變慢
    if member.neili >= ceiling:
        member.neili = None


# ── 遭遇/劇情戰：串接 encounter.py 的單次判定 ───────────────


def team_conditions(state: GameState, content: Content, world: WorldStateStore) -> list[float]:
    """本隊每個人的氣血狀態係數，順序跟 team_participants 一致（氣血設計 §1.1：帶傷出手較弱）。"""
    return [
        encounter.condition_of(*member_neili(content, member))
        for member in team_participants(state, world)
    ]


def take_encounter_toll(
    state: GameState, content: Content, world: WorldStateStore, tier: str, *, wild: bool = False,
) -> list[str]:
    """一場遭遇戰打完的氣血代價（氣血設計 §1.3）：按結果扣氣血，其中一部分變成內傷。

    沒有這一段的話戰鬥是**沒有損耗的免費收入**——而那正是「遊歷」復活之後最明顯的破口：
    打得越多拿得越多，卻完全不必付出什麼。扣掉的量按上限的比例算，所以等級（上限）
    決定的是「撐得住幾場」，不是「打得多痛」。

    wild：探索時撞上的野怪（探索三選一設計 4.2），扣的量再乘上 `wild_neili_loss_factor`；
    內傷是扣掉的量的固定幾成，所以照同一個比例變少。遊歷與劇情戰不帶這個旗標，一點都不變。
    """
    cfg = content.config
    fraction = cfg.encounter_neili_loss.get(tier, 0.0) * (cfg.wild_neili_loss_factor if wild else 1.0)
    if fraction <= 0:
        return []
    msgs = []
    for key in team_keys(state):
        if key == PLAYER:
            member = state.player.member
            lost, hurt = _apply_toll(content, member, fraction)
            msgs.append(f"氣血 -{lost:.0f}")  # 照既有慣例寫變化量（跟「銀兩 -5」「心得 +12」同一串）
            if hurt >= 1:
                msgs.append(f"內傷 +{hurt:.0f}")
        else:
            world.update_companion(key, lambda progress: _apply_toll(content, progress, fraction))
    return msgs


def _apply_toll(content: Content, member, fraction: float) -> tuple[float, float]:
    """扣一場的氣血，回傳（實際掉了多少氣血, 其中變成內傷的量）。"""
    now, cap = member_neili(content, member)
    loss = cap * fraction
    hurt = loss * content.config.injury_share
    member.injury += hurt
    member.neili = max(0.0, now - loss)
    after, _ = member_neili(content, member)
    return now - after, hurt


def fight(
    state: GameState, content: Content, world: WorldStateStore, squad_id: str, rng: random.Random,
    *, difficulty: float | None = None,
) -> encounter.EncounterResult:
    """difficulty 給了就取代隊伍的難度（挑戰大勢人物本人：難度跟著聲威走，見 figures.difficulty）。"""
    squad = content.squads[squad_id]
    arts = team_arts(state, content, world)
    power = encounter.team_power(*_with_attribute(_fighters(state, content, world), arts, squad.attribute))
    return encounter.resolve_encounter(power, squad.difficulty if difficulty is None else difficulty, rng)


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


def estimate(
    state: GameState, content: Content, world: WorldStateStore, squad_id: str, *, difficulty: float | None = None,
) -> str:
    """勝算的文字；difficulty 同 fight。"""
    squad = content.squads[squad_id]
    if difficulty is not None:
        squad = squad.model_copy(update={"difficulty": difficulty})
    arts = team_arts(state, content, world)
    power = encounter.team_power(*_with_attribute(_fighters(state, content, world), arts, squad.attribute))
    return odds_word(power, squad)


def _with_attribute(fighters: tuple[list, list[float]], arts: dict[str, MartialArt], attribute: str | None) -> tuple:
    """encounter.team_power 的參數順序：陣容、武學、對手屬性、氣血係數。"""
    members, conditions = fighters
    return members, arts, attribute, conditions
