"""門下與隊伍（sanguo-companions 合併大幅重寫）：玩家與最多 4 個已招募同伴的單一隊伍，
每人最多一門內功、一門武學，練功（鍛鍊）與心得升級，串接 encounter.py 的單次判定。

同伴不再是玩家存檔裡的副本——他們全服唯一，等級/武學是共用資料（world_state.py 的
CompanionProgress），這裡的函式凡是要讀寫同伴進度都要帶一個 WorldStateStore 參數。
"""
from __future__ import annotations

import math
import random

from . import calendar, encounter
from .martial_arts import MAX_LEVEL, MartialArt, content_art, counters, with_quality
from .models import Content, FollowerDef, Squad
from .state import PLAYER, MAX_TEAM_COMPANIONS, GameState, Member
from .world_state import CompanionProgress, WorldStateStore

ESTIMATE_RUNS = 40
ESTIMATE_SEED = 20260929  # 固定種子：同樣的情況每次都算出同樣的勝算，畫面不會跳動
WIN_TIERS = {"大勝", "險勝"}
DRAW_TIERS = {"僵持"}
ODDS = ((90, "穩勝"), (65, "有把握"), (35, "五五波"), (10, "凶險"))  # 勝率（%）門檻；再低就是必敗


COMBAT_STATS = ("str", "agi", "con", "wis")  # 四屬性：事件檢定用的就是它們（數字照舊，不吃下面的加成）；
# 玩家本人的四項另外各管一件事（武學與成長設計 6.1）：臂力管外功、根骨管內功與氣血、身法管損耗、悟性管修練與悟意境
BASE_STAT = 5  # 四屬性的基準：開局都是 5，比它多才有加成（武學與成長設計 6.1）


def stat_bonus(content: Content, value: float) -> float:
    """屬性比基準每多一點加 stat_bonus_per_point（預設 3%）；比基準少是負的。要乘上去的倍數用 stat_factor；
    要減掉的（身法減損耗、根骨減內傷）由呼叫端寫成 1 − 加成，夾在 0 以上。"""
    return content.config.stat_bonus_per_point * (value - BASE_STAT)


def stat_factor(content: Content, value: float) -> float:
    """屬性乘上去的倍數：1＋加成，再低也夾在 encounter.BOOST_FLOOR（0.1），不會讓任何量變成負的或 0。
    氣血上限（根骨）、修練機率（悟性）、探索悟意境的比重（悟性）都用這一個。"""
    return max(encounter.BOOST_FLOOR, 1 + stat_bonus(content, value))


def con_of(state: GameState, key: str) -> float:
    """名冊上這個人（key：PLAYER 或同伴的 id）的根骨。本人的根骨只從這裡讀（氣血四個函式的 con、內功的加成、
    一場的內傷）；同伴一律是基準，不吃屬性加成（計畫二「實作決定」：同伴的平衡在氣血設計 §1.4 調過，不連帶動）。
    認 key 不認物件：拿到玩家 Member 的複本也照樣是本人。"""
    return float(state.player.stats.get("con", BASE_STAT)) if key == PLAYER else BASE_STAT


def member_name(state: GameState, content: Content, key: str) -> str:
    return state.player.name if key == PLAYER else content.characters[key].name


def member_stats(state: GameState, content: Content, world: WorldStateStore, key: str) -> dict[str, float]:
    """這個人的四屬性。玩家本人就是存檔裡的數字（升級給點、自己分配，武學與成長設計 6.2，不再每級自動長）；
    同伴照舊是第 1 級的屬性加上每級成長。"""
    if key == PLAYER:
        return {k: float(state.player.stats.get(k, 0)) for k in COMBAT_STATS}
    character = content.characters[key]
    level = world.get_companion(key).level
    return {k: character.stats[k] + character.growth.get(k, 0.0) * (level - 1) for k in COMBAT_STATS}


def practice_bonus(state: GameState, content: Content, check) -> int:
    """本人做這件事的熟練加成（Check.practice，例如惡名）：名聲每 per 點 +1，最多 +cap；沒寫 practice 是 0。
    check 也可能是隨口應對（FreeTextChoice），它沒有 practice。"""
    kind = getattr(check, "practice", None)
    rule = content.config.practice_bonus.get(kind) if kind else None
    if rule is None:
        return 0
    return min(rule.cap, max(0, int(state.player.stats.get(kind, 0))) // rule.per)


def check_value(state: GameState, content: Content, world: WorldStateStore, key: str, stat: str) -> float:
    if stat in COMBAT_STATS:
        return member_stats(state, content, world, key)[stat]
    return float(state.player.stats.get(stat, 0))


def team_keys(state: GameState) -> list[str]:
    """本隊成員：玩家本人在最前，其餘是目前帶著出戰的同伴（最多 MAX_TEAM_COMPANIONS 位）。"""
    return [PLAYER] + list(state.player.team)


def resolve_art(skill_id: str | None, content: Content, world: WorldStateStore) -> MartialArt | None:
    """skill_id 指向內容裡的武學（本命武學、基礎武學）或全服登記的武學（合成、舊的自創與煉製）。
    回傳的是全服共享的那一份；玩家自己那一份的品質見 player_art。"""
    if skill_id is None:
        return None
    if skill_id in content.skills:
        s = content.skills[skill_id]
        return content_art(skill_id, s.name, s.kind, s.attribute, s.quality)
    return world.get_skill(skill_id)


def art_quality(state: GameState, art: MartialArt) -> str:
    """玩家手上這一份是什麼品質：修練過就照自己的，沒修練過照全服登記的。"""
    return state.player.art_quality.get(art.id, art.quality)


def player_art(state: GameState, content: Content, world: WorldStateStore, skill_id: str | None) -> MartialArt | None:
    """玩家自己那一份：品質與威力照自己修練到的品質。"""
    art = resolve_art(skill_id, content, world)
    return None if art is None else with_quality(art, art_quality(state, art))


def team_arts(state: GameState, content: Content, world: WorldStateStore) -> dict[str, MartialArt]:
    """本隊每個人的內功/武學（含部下），蒐集成一份 id -> MartialArt 給 encounter.py 用。
    玩家的兩門照自己修練到的品質（player_art）；同伴、部下只有內容武學，照內容的品質。"""
    arts: dict[str, MartialArt] = {}
    for skill_id in (state.player.member.neigong_id, state.player.member.wugong_id):
        art = player_art(state, content, world, skill_id)
        if art:
            arts[skill_id] = art
    others = {unit.wugong_id for unit in follower_units(state, content)}
    shared = world.read()
    for key in state.player.team:
        progress = shared.companions.get(key, CompanionProgress())
        others |= {progress.neigong_id, progress.wugong_id}
    for skill_id in others:
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


def _fighters(
    state: GameState, content: Content, world: WorldStateStore,
) -> tuple[list, list[float], list[encounter.Boost]]:
    """打一場的陣容、各自的氣血係數與加成：本人、出戰的同伴，再加上部下（滿血、不吃本人的加成）。
    三份一樣長（encounter.team_power 會檢查），部下才不會被默默漏掉（F17）。"""
    followers = follower_units(state, content)
    return (
        team_participants(state, world) + followers,
        team_conditions(state, content, world) + [1.0] * len(followers),
        team_boosts(state, content, world),
    )


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


# ── 練功：改練／鍛鍊（設計文件六.2；自創武學已作廢，見武學與成長設計 3.8）──────────────────────


def switch_art(state: GameState, content: Content, world: WorldStateStore, art_id: str) -> list[str]:
    """改練：把功法庫裡的一門換上身，被換下來的回庫，兩邊的熟練度**各自保留**。

    合成（fusion.py）、學藝會讓同一個人擁有超過一門內功／武學，但每人同時只能練一門（設計文件
    六.4），所以需要這個動作——在這之前整個 team.py 連散功都沒有，拿到好功法卻裝不上去。
    熟練度存在 `PlayerState.art_levels`（換下來時寫進去、換上去時取出來），所以換回來不用
    重練；舊存檔沒有這個欄位時，庫裡的功法一律從第一成算起。
    """
    p = state.player
    if art_id not in p.arts:
        return ["你的功法庫裡沒有這一門。"]
    art = player_art(state, content, world, art_id)
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


def practice_price(content: Content, level: int) -> int:
    """練成的價錢：第 level 成升 level+1 成要幾點心得（武學與成長設計 4.2）。只看第幾成、不看品質：
    升品時成不變，品質越高越貴的話，玩家會先趁下品把成練滿再修練，價錢就被繞過去。"""
    return content.config.practice_xinde_per_level * level


def can_practise(state: GameState, content: Content, kind: str) -> bool:
    """身上這一欄有武學、還沒第十成、而且付得起下一成的心得（練成花心得，設計 4.2）。
    機器人要不要練（bot.can_practise）與主畫面的提示（skillview.practice_hint）共用這一個條件。"""
    member = state.player.member
    slot, level_slot = ("neigong_id", "neigong_level") if kind == "內功" else ("wugong_id", "wugong_level")
    level = getattr(member, level_slot)
    return (
        getattr(member, slot) is not None and level < MAX_LEVEL
        and state.player.stats.get("xinde", 0) >= practice_price(content, level)
    )


def practice(
    state: GameState, content: Content, world: WorldStateStore, kind: str, rng: random.Random,
) -> list[str]:
    """練成：身上這一門加深一成，花心得（設計 4.2），累積受傷風險（設計文件六.2）。"""
    cfg, member = content.config, state.player.member
    slot = "neigong_id" if kind == "內功" else "wugong_id"
    level_slot = slot.replace("_id", "_level")
    skill_id = getattr(member, slot)
    if skill_id is None:
        return [f"你還沒學{kind}，沒東西可以練。"]
    level = getattr(member, level_slot)
    art = player_art(state, content, world, skill_id)
    name = art.name if art else skill_id
    if level >= MAX_LEVEL:
        return [f"【{name}】已經練到第十成，練無可練。"]
    price = practice_price(content, level)
    xinde = state.player.stats.get("xinde", 0)
    if xinde < price:
        return [
            f"心得不足：【{name}】從第{level}成練到第{level + 1}成要 {price} 點心得，"
            f"你只有 {xinde} 點，還差 {price - xinde} 點。"
        ]
    state.player.stats["xinde"] = xinde - price
    setattr(member, level_slot, level + 1)
    msgs = [f"【{name}】精進至第{level + 1}成。", f"心得 -{price}"]
    if rng.random() < cfg.practice_injury_chance:
        now, _cap = member_neili(content, member, con_of(state, PLAYER))
        member.injury += cfg.practice_injury_amount
        member.neili = max(0.0, now - cfg.practice_injury_amount)
        msgs.append(f"這一番苦練傷了氣血，氣血 -{cfg.practice_injury_amount:.0f}（累積內傷，需要療傷才能回到滿血）。")
    return msgs


def neili_cap(content: Content, level: int, con: float = BASE_STAT) -> float:
    """氣血上限：基礎＋每級加成，再乘上根骨的加成（武學與成長設計 6.1：上限 ×（1＋3%×（根骨−5））），
    四捨五入成整數——每個呼叫端拿到的、狀態列與角色卡寫出來的都是同一個數（根骨 6：329.6 → 330）。
    con 是根骨，只有玩家本人傳（con_of）；同伴照預設的基準，上限跟以前一樣。"""
    cfg = content.config
    return float(round((cfg.neili_base + level * cfg.neili_per_level) * stat_factor(content, con)))


MIN_CEILING_RATIO = 0.1  # 內傷再重，能回到的氣血上蓋也不低於上限的一成（氣血設計 §1.3：再低也照樣能出戰）


def neili_ceiling(content: Content, member, con: float = BASE_STAT) -> float:
    """內傷之後氣血自己能回到哪裡（上限 − 內傷，但不低於上限的一成）。con 是根骨，只有玩家本人傳。"""
    cap = neili_cap(content, member.level, con)
    return max(cap * MIN_CEILING_RATIO, cap - getattr(member, "injury", 0.0))


def member_neili(content: Content, member, con: float = BASE_STAT) -> tuple[float, float]:
    """回傳（目前氣血, 上限）。member 可以是玩家的 Member 或同伴的 CompanionProgress。
    con 是根骨，只有玩家本人傳（con_of）。

    `neili is None` 代表「回滿了」——有內傷時的「滿」是上蓋（上限 − 內傷），不是上限本身。
    所以根骨變高時：沒滿血的人目前氣血不變、上限變大；本來就滿的人照舊是滿的（跟升級一樣）。
    """
    cap = neili_cap(content, member.level, con)
    ceiling = neili_ceiling(content, member, con)
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
    （neili_cap：基礎＋每級加成，本人再乘上根骨）由等級算出來，升級就跟著變高（氣血設計 A1：等級只買氣血上限）；
    目前氣血不變，不順便回血。"""
    p = state.player
    before = p.member.level
    msgs = add_exp(content, p.member, amount, p.name)
    gained = p.member.level - before
    if gained > 0:  # 升級給屬性點（武學與成長設計 6.2）：一次升好幾級就給好幾點，只給本人
        p.stat_points += gained * content.config.stat_points_per_level
        msgs.append(f"你有 {p.stat_points} 點屬性可以分配（點名號展開）。")
    for companion_id in state.player.team:
        name = content.characters[companion_id].name
        levels: list[str] = []
        world.update_companion(companion_id, lambda progress: levels.extend(add_exp(content, progress, amount, name)))
        msgs += levels
    return msgs


def regen_neili(content: Content, member, fraction: float, con: float = BASE_STAT) -> None:
    """氣血隨時間回復——只回到上蓋（上限 − 內傷），內傷那部分要療傷才清得掉。con 是根骨，只有玩家本人傳。"""
    if member.neili is None:
        return
    cap = neili_cap(content, member.level, con)
    ceiling = neili_ceiling(content, member, con)
    member.neili += cap * fraction  # 回復速度照上限算，所以內傷不會讓回復變慢
    if member.neili >= ceiling:
        member.neili = None


# ── 遭遇/劇情戰：串接 encounter.py 的單次判定 ───────────────


def team_conditions(state: GameState, content: Content, world: WorldStateStore) -> list[float]:
    """本隊每個人的氣血狀態係數，順序跟 team_participants 一致（氣血設計 §1.1：帶傷出手較弱）。"""
    return [
        encounter.condition_of(*member_neili(content, member, con_of(state, key)))
        for key, member in zip(team_keys(state), team_participants(state, world), strict=True)
    ]


def pairing(content: Content, wugong: MartialArt | None, neigong: MartialArt | None) -> float:
    """內功與武學的搭配（武學與成長設計 5.1）：同屬性加成、相剋的一對打折、其他不變；少一門就不算。
    加成與打折兩支都夾在 encounter.BOOST_FLOOR 以上（設定寫錯也一樣），不會讓整個人的威力變成負的。"""
    if wugong is None or neigong is None:
        return 1.0
    cfg = content.config
    if wugong.attribute == neigong.attribute:
        return max(encounter.BOOST_FLOOR, 1 + cfg.pairing_bonus)
    if counters(wugong.attribute, neigong.attribute):
        return max(encounter.BOOST_FLOOR, 1 - cfg.pairing_penalty)
    return 1.0


def resonance(state: GameState, content: Content, art: MartialArt | None) -> float:
    """正邪共鳴（設計 7.4）：正派功法吃現在的善名、邪派吃惡名，名聲 ÷ 2 %、最多 resonance_cap；
    沒有正邪、或用了反的那一派，就是 1（不反噬，名聲是負的也一樣）。"""
    stat = {"正": "good", "邪": "evil"}.get(art.lean) if art is not None else None
    if stat is None:
        return 1.0
    cfg = content.config
    return 1 + min(cfg.resonance_cap, max(0.0, state.player.stats.get(stat, 0) * cfg.resonance_per_point))


def player_boost(state: GameState, content: Content, world: WorldStateStore) -> encounter.Boost:
    """玩家本人的加成：臂力管外功、根骨管內功（武學與成長設計 6.1）；整個人再乘上內外搭配與兩門各自的
    正邪共鳴（5.1、7.4）。搭配至少是 BOOST_FLOOR、共鳴至少是 1，所以乘出來的 factor 不會低於下限。"""
    stats, member = state.player.stats, state.player.member
    wugong = player_art(state, content, world, member.wugong_id)
    neigong = player_art(state, content, world, member.neigong_id)
    return encounter.Boost(
        outer=stat_bonus(content, stats.get("str", BASE_STAT)),
        inner=stat_bonus(content, con_of(state, PLAYER)),
        factor=pairing(content, wugong, neigong) * resonance(state, content, wugong) * resonance(state, content, neigong),
    )


def team_boosts(state: GameState, content: Content, world: WorldStateStore) -> list[encounter.Boost]:
    """跟 _fighters 的陣容一一對應：本人有加成；出戰的同伴與部下沒有（計畫二「實作決定」），但一個都不能少——
    少一個 encounter.team_power 就會報錯，而不是默默漏算部下（F17、計畫二 G1）。"""
    others = len(state.player.team) + len(follower_units(state, content))
    return [player_boost(state, content, world)] + [encounter.Boost() for _ in range(others)]


def take_encounter_toll(
    state: GameState, content: Content, world: WorldStateStore, tier: str, *, wild: bool = False,
) -> list[str]:
    """一場遭遇戰打完的氣血代價（氣血設計 §1.3）：按結果扣氣血，其中一部分變成內傷。

    沒有這一段的話戰鬥是**沒有損耗的免費收入**——而那正是「遊歷」復活之後最明顯的破口：
    打得越多拿得越多，卻完全不必付出什麼。扣掉的量按上限的比例算，所以等級（上限）
    決定的是「撐得住幾場」，不是「打得多痛」。

    wild：探索時撞上的野怪（探索三選一設計 4.2），扣的量再乘上 `wild_neili_loss_factor`；
    內傷是扣掉的量的固定幾成，所以照同一個比例變少。遊歷與劇情戰不帶這個旗標，一點都不變。

    玩家本人的身法讓一場少掉一點氣血（閃得開）、根骨讓其中變成內傷的少一點（武學與成長設計 6.1）；
    同伴照舊，不吃本人的屬性。
    """
    cfg = content.config
    fraction = cfg.encounter_neili_loss.get(tier, 0.0) * (cfg.wild_neili_loss_factor if wild else 1.0)
    if fraction <= 0:
        return []
    stats = state.player.stats
    msgs = []
    for key in team_keys(state):
        if key == PLAYER:
            lost, hurt = _apply_toll(
                content, state.player.member, fraction,
                agi=stats.get("agi", BASE_STAT), con=con_of(state, PLAYER),
            )
            msgs.append(f"氣血 -{lost:.0f}")  # 照既有慣例寫變化量（跟「銀兩 -5」「心得 +12」同一串）
            if hurt >= 1:
                msgs.append(f"內傷 +{hurt:.0f}")
        else:
            world.update_companion(key, lambda progress: _apply_toll(content, progress, fraction))
    return msgs


def _apply_toll(
    content: Content, member, fraction: float, agi: float = BASE_STAT, con: float = BASE_STAT,
) -> tuple[float, float]:
    """扣一場的氣血，回傳（實際掉了多少氣血, 其中變成內傷的量）。身法減一場的損耗、根骨減其中變成內傷的
    比例，各 ×（1−3%×（屬性−5）），夾在 0 以上；氣血上限也照根骨算。同伴不傳 agi、con，跟以前一樣。"""
    now, cap = member_neili(content, member, con)
    loss = cap * fraction * max(0.0, 1 - stat_bonus(content, agi))
    hurt = loss * content.config.injury_share * max(0.0, 1 - stat_bonus(content, con))
    member.injury += hurt
    member.neili = max(0.0, now - loss)
    after, _ = member_neili(content, member, con)
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


def _with_attribute(
    fighters: tuple[list, list[float], list[encounter.Boost]], arts: dict[str, MartialArt], attribute: str | None,
) -> tuple:
    """encounter.team_power 的參數順序：陣容、武學、對手屬性、氣血係數、加成。"""
    members, conditions, boosts = fighters
    return members, arts, attribute, conditions, boosts
