"""門下與隊伍（sanguo-companions 合併大幅重寫）：玩家與最多 4 個已招募同伴的單一隊伍，
每人最多一門內功、一門武學，練功（鍛鍊）與心得升級，串接 encounter.py 的單次判定。

同伴不再是玩家存檔裡的副本——他們全服唯一，等級/武學是共用資料（world_state.py 的
CompanionProgress），這裡的函式凡是要讀寫同伴進度都要帶一個 WorldStateStore 參數。
"""
from __future__ import annotations

import hashlib
import json
import math
import random
import threading
from collections import OrderedDict
from contextlib import contextmanager
from contextvars import ContextVar
from collections.abc import Callable

from . import armor, calendar, encounter, equipment, mounts, rounds, seal_acts, signature, styles, tactics, traits, treasures, weapons
from . import growth  # 減法季三道閘、屬性五段的純規則（growth 只在函式裡反過來 import team）
from . import terrain as terrain_mod  # 地利（_styled_fighters 的參數 terrain 是開關，模組另取名字）
from .martial_arts import MAX_LEVEL, MartialArt, content_art, counters, power_at, with_quality
from .models import Content, FollowerDef, InsightDef, Squad, TacticBond, TacticDef
from .state import PLAYER, MAX_TEAM_COMPANIONS, FollowerDrill, GameState, LevelUps, Member
from .world_state import CompanionProgress, WorldStateStore

ESTIMATE_RUNS = 40
ESTIMATE_SEED = 20260929  # 固定種子：同樣的情況每次都算出同樣的勝算，畫面不會跳動
WIN_TIERS = {"大勝", "險勝"}
DRAW_TIERS = {"僵持"}
ODDS = ((90, "穩勝"), (65, "有把握"), (35, "五五波"), (10, "凶險"))  # 勝率（%）門檻；再低就是必敗


COMBAT_STATS = ("str", "agi", "con", "wis", "lore")  # 五屬性：升級給點、狀態列、＋鈕、事件檢定都照這份與這個順序；
# 前四項另外各管一件戰力（武學與成長設計 6.1；同伴、部下也吃，人物資質設計 14.3）：臂力管外功、根骨管內功與氣血、身法管損耗、
# 悟性管修練與悟意境（悟性只有本人用）；第五項博聞管武學與意境的持有上限（6.3），不進戰力
LORE = "lore"
BASE_STAT = 5  # 屬性的基準：開局都是 5，比它多才有加成（武學與成長設計 6.1、6.3）


RATE_KEYS = {  # 每一點屬性的效果：減法季（Config.jianfa.stat_rates）的鍵 → 舊的 Config 欄位（設計 4.5「每點加倍」）
    "bonus_per_point": "stat_bonus_per_point",
    "dodge_per_point": "dodge_per_point",
    "sense_rate_per_wis": "sense_rate_per_wis",
    "holding_per_lore_point": "holding_per_lore_point",
}


def per_point(content: Content, season, key: str) -> float:
    """每一點屬性的效果（key 是 RATE_KEYS 的鍵）：這一季（season＝WorldState）蓋了減法季的章、屬性五段開著（Config.jianfa 的
    stat_milestones）讀 Config.jianfa.stat_rates（每點加倍），其餘照 Config 的舊數字。season 是 None 一律舊數字（純函式、量表）。
    本人、同伴、部下同一個數字（傳功給同伴與部下的那一點也照它，chuangong）。"""
    if season is not None and _season_rates(content, season):
        return getattr(content.config.jianfa.stat_rates, key)
    return getattr(content.config, RATE_KEYS[key])


def _season_rates(content: Content, season) -> bool:
    from . import rules  # noqa: PLC0415  rules 反過來 import 這裡

    return rules.jianfa(content, season, "stat_milestones")


def stat_bonus(content: Content, value: float, season=None) -> float:
    """屬性比基準每多一點加 stat_bonus_per_point（預設 3%）；比基準少是負的。要乘上去的倍數用 stat_factor；
    要減掉的（身法減損耗、根骨減內傷）由呼叫端寫成 1 − 加成，夾在 0 以上。season（這一季的 WorldState）給了照 per_point
    （減法季每點加倍）；沒給照舊。"""
    if season is None:
        return content.config.stat_bonus_per_point * (value - BASE_STAT)
    return per_point(content, season, "bonus_per_point") * (value - BASE_STAT)


def stat_factor(content: Content, value: float, season=None) -> float:
    """屬性乘上去的倍數：1＋加成，再低也夾在 encounter.BOOST_FLOOR（0.1），不會讓任何量變成負的或 0。
    氣血上限（根骨）、修練機率（悟性）、探索悟意境的比重（悟性）都用這一個。season 同 stat_bonus。"""
    return max(encounter.BOOST_FLOOR, 1 + stat_bonus(content, value, season))


def con_of(state: GameState, content: Content, world: WorldStateStore, key: str) -> float:
    """名冊上這個人（key：PLAYER 或同伴的 id）的根骨，只從這裡讀：氣血四個函式的 con、內功的加成、一場的內傷。
    本人照存檔；同伴照 member_stats（內容的起始值加每級成長，人物資質設計 14.2；原本一律是基準）。
    認 key 不認物件：拿到玩家 Member 的複本也照樣是本人。"""
    if key == PLAYER:
        return float(state.player.stats.get("con", BASE_STAT))
    return member_stats(state, content, world, key)["con"]


def member_name(state: GameState, content: Content, key: str) -> str:
    return state.player.name if key == PLAYER else content.characters[key].name


def member_stats(state: GameState, content: Content, world: WorldStateStore, key: str) -> dict[str, float]:
    """這個人的五屬性。玩家本人就是存檔裡的數字（升級給點、自己分配，武學與成長設計 6.2，不再每級自動長）；
    同伴照舊是第 1 級的屬性加上每級成長，同伴的內容沒寫的屬性（博聞）當基準。"""
    if key == PLAYER:
        return {k: float(state.player.stats.get(k, 0)) for k in COMBAT_STATS}
    character = content.characters[key]
    progress = world.get_companion(key)
    steps = growth_steps(content.config, progress.level)  # 30 級以後每 2 級長一步，同本人的屬性點
    return {k: character.stats.get(k, BASE_STAT) + character.growth.get(k, 0.0) * steps + progress.taught.get(k, 0)  # taught：傳功
            for k in COMBAT_STATS}


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
        return content_art(skill_id, s.name, s.kind, s.attribute, s.quality, special=s.special, traits=s.traits, lean=s.lean, affinity=s.affinity)
    return world.get_skill(skill_id)


def art_quality(state: GameState, art: MartialArt) -> str:
    """玩家手上這一份是什麼品質：修練過就照自己的，沒修練過照全服登記的。"""
    return state.player.art_quality.get(art.id, art.quality)


def player_art(state: GameState, content: Content, world: WorldStateStore, skill_id: str | None) -> MartialArt | None:
    """玩家自己那一份：品質與威力照自己修練到的品質。本命武學再乘 Config.signature_arts.power_scale
    （signature.scale；只乘玩家自己那一份，同伴練的本命武學照內容）。"""
    art = resolve_art(skill_id, content, world)
    if art is None:
        return None
    from . import arts as arts_mod  # arts 會 import 這個模組

    mine = arts_mod.apply(state, content, world, with_quality(art, art_quality(state, art)))
    k = signature.scale(content, art.id)
    if k == 1.0:
        return mine
    return mine.model_copy(update={"base_power": mine.base_power * k, "top_power": mine.top_power * k})


def team_arts(state: GameState, content: Content, world: WorldStateStore) -> dict[str, MartialArt]:
    """本隊每個人的內功/武學（含部下），蒐集成一份 id -> MartialArt 給 encounter.py 用。
    玩家的兩門照自己修練到的品質（player_art）；同伴、部下只有內容武學，照內容的品質。"""
    arts: dict[str, MartialArt] = {}
    for skill_id in (state.player.member.neigong_id, state.player.member.wugong_id):
        art = player_art(state, content, world, skill_id)
        if art:
            arts[skill_id] = art
    others = {unit.wugong_id for unit in follower_units(state, content)}
    companions = world.companions()
    for key in state.player.team:
        progress = companions.get(key, CompanionProgress())
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
    companions = world.companions()
    return [state.player.member] + [companions.get(k, CompanionProgress()) for k in state.player.team]


FOLLOWER_KEY = "follower:"  # 名冊裡部下的 key：follower:<在 PlayerState.followers 裡的位置>（同一種部下可以有兩個）


def follower_rows(state: GameState, content: Content) -> list[tuple[str, FollowerDef]]:
    """部下（計畫 T5）：(名冊的 key, 模板)。第一季才有，開關關著時是空的。"""
    if not state.player.followers or not calendar.season_one_on(state.world, content):  # 同 rules.season_one（rules 會 import team）
        return []
    return [(f"{FOLLOWER_KEY}{i}", content.followers[fid]) for i, fid in enumerate(state.player.followers)
            if fid in content.followers]


def drill_of(state: GameState, key: str | None) -> FollowerDrill:
    """名冊上這名部下（key：follower:<位置>）傳功傳了什麼（PlayerState.follower_drill，跟 followers 同位置）；沒傳過、key 不是部下是空的。
    只讀：要改的走 chuangong.teach（它把清單補長再寫）。"""
    if key is None or not key.startswith(FOLLOWER_KEY):
        return FollowerDrill()
    index = int(key[len(FOLLOWER_KEY):])
    drills = state.player.follower_drill
    return drills[index] if 0 <= index < len(drills) else FollowerDrill()


def follower_line(state: GameState, content: Content, follower: FollowerDef) -> int:
    """部下的武學照等級長的那條線：跟著本人的等級長（Config.follower.levels_per_cheng），不低於模板寫的、最多十成。"""
    grown = state.player.member.level // content.config.follower.levels_per_cheng
    return min(MAX_LEVEL, max(follower.wugong_level, grown))


def follower_level(state: GameState, content: Content, follower: FollowerDef, key: str | None = None) -> int:
    """部下的武學成數：照等級長的那條線（follower_line）再加傳功多練的成數（drill_of），最多十成。key 是名冊上的 key，不給當沒傳過功。"""
    return min(MAX_LEVEL, follower_line(state, content, follower) + drill_of(state, key).cheng)


def follower_units(state: GameState, content: Content) -> list[Member]:
    """部下照模板建成跟 Member 同形狀的威力貢獻者（武學照模板、成數照 follower_level、沒有內功）。只算威力：不在 team_keys 裡，
    所以不擋檢定、不扣氣血（take_encounter_toll）、不吃經驗；氣血係數一律 1.0。"""
    return [Member(wugong_id=f.wugong, wugong_level=follower_level(state, content, f, key)) for key, f in follower_rows(state, content)]


def follower_power(
    state: GameState, content: Content, world: WorldStateStore, follower: FollowerDef, key: str | None = None,
) -> float:
    """一名部下此刻的威力（不看對手：沒有相剋、沒有路數；角色卡寫它）。key 是名冊上的 key（算傳功），不給當沒傳過功。"""
    unit = Member(wugong_id=follower.wugong, wugong_level=follower_level(state, content, follower, key))
    return encounter.member_power(
        unit, team_arts(state, content, world), None, 1.0, follower_boost(content, follower, drill_of(state, key), state.world))


CN_DIGITS = "零一兩三四五六七八九十"


def mate_power(state: GameState, content: Content, world: WorldStateStore, key: str) -> float:
    """一位同伴此刻的威力（不看對手、氣血係數照滿的）：他自己的兩門武學、他自己的加成（mate_boost）。
    決戰的隨行同伴照它算份量（歷史武將同行第五節，Game._escort_of）。"""
    progress = world.get_companion(key)
    arts = {sid: art for sid in (progress.neigong_id, progress.wugong_id) if sid and (art := resolve_art(sid, content, world))}
    return encounter.member_power(progress, arts, None, 1.0, mate_boost(state, content, world, key))


def mate_pool(state: GameState, content: Content, world: WorldStateStore, key: str) -> float:
    """一位同伴的氣血池（決戰加入時快照）：他的氣血上限，照他自己的等級與根骨（member_neili，不乘螭首）。"""
    _, cap = member_neili(content, world.get_companion(key), con_of(state, content, world, key), plain=True, season=state.world)
    return cap


def mate_side(state: GameState, content: Content, world: WorldStateStore, key: str) -> tactics.BoutSide | None:
    """一位同伴在決戰帶的本命戰法：只算他自己身上的兩門（照決戰的規矩，tactics.war_round）；沒有是 None。"""
    progress = world.get_companion(key)
    holders = tactics.holders_of(content, [(content.characters[key].name, key, progress.wugong_id, progress.neigong_id)])
    if not holders:
        return None
    agility = member_stats(state, content, world, key).get("agi", BASE_STAT)
    return tactics.side_for(holders, tactics.Ctx(
        foe="", our_agility=float(agility), night=calendar.is_night(state.world.time, content, state.world), team=[key],
    ))


def follower_share(state: GameState, content: Content, world: WorldStateStore, squad: Squad) -> tuple[float, float]:
    """這一場（照對手算：相剋、路數都在，同 fight）部下的威力合計與其餘的人（本人、同伴）的威力合計。沒有部下是 (0, 全隊)。"""
    rows = follower_rows(state, content)
    arts = team_arts(state, content, world)
    members, conditions, boosts = _styled_fighters(state, content, world, arts, squad)
    powers = [encounter.member_power(m, arts, squad.attribute, c, b) for m, c, b in zip(members, conditions, boosts, strict=True)]
    theirs = sum(powers[len(powers) - len(rows):]) if rows else 0.0
    return theirs, sum(powers) - theirs


def aid_line(state: GameState, content: Content, world: WorldStateStore, squad: Squad) -> str:
    """戰報那一句「持矛鄉勇、弩手鄉勇助陣，威力多了兩成。」：部下讓全隊威力比不帶他們多了幾成（follower_share）。
    沒有部下、或部下一點威力都沒有是空字串。只寫一句話、帶一個數字，不寫成數字標籤（PM 2026-10-12）。"""
    rows = follower_rows(state, content)
    if not rows:
        return ""
    theirs, ours = follower_share(state, content, world, squad)
    if theirs <= 0:
        return ""
    return f"{troop_names([f for _, f in rows])}助陣，威力{_more(theirs / ours if ours > 0 else None)}。"


def troop_names(followers: list[FollowerDef]) -> str:
    """部下的名字照模板併在一起：「兩名持矛鄉勇、弩手鄉勇」（照第一次出現的順序；一名的不寫數量）。"""
    counts: dict[str, int] = {}
    for f in followers:
        counts[f.name] = counts.get(f.name, 0) + 1
    return "、".join(name if n == 1 else f"{CN_DIGITS[n] if n <= 10 else n}名{name}" for name, n in counts.items())


def _more(ratio: float | None) -> str:
    """多了幾成的說法：不到半成「多了一點」、一成到九成「多了N成」、一倍以上「翻了N倍」（一位小數四捨五入成整倍）；
    本人一點威力都沒有（ratio 是 None）時「全靠他們撐著」。"""
    if ratio is None:
        return "全靠他們撐著"
    tenths = math.floor(ratio * 10 + 0.5)
    if tenths < 1:
        return "多了一點"
    if tenths < 10:
        return f"多了{CN_DIGITS[tenths]}成"
    times = math.floor(ratio + 0.5)
    return f"翻了{CN_DIGITS[times]}倍" if times <= 10 else f"翻了{times}倍"


def _fighters(
    state: GameState, content: Content, world: WorldStateStore, *, seal: bool = True,
) -> tuple[list, list[float], list[encounter.Boost]]:
    """打一場的陣容、各自的氣血係數與加成：本人、出戰的同伴，再加上部下（滿血）。
    每個人的加成吃他自己的屬性（本人、同伴、部下各一份，見 team_boosts），不吃別人的。
    三份一樣長（encounter.team_power 會檢查），部下才不會被默默漏掉（F17）。seal 見 player_boost。"""
    followers = follower_units(state, content)
    return (
        team_participants(state, world) + followers,
        team_conditions(state, content, world) + [1.0] * len(followers),
        team_boosts(state, content, world, seal=seal),
    )


def lineup(
    state: GameState, content: Content, world: WorldStateStore,
) -> list[tuple[str, MartialArt | None, MartialArt | None]]:
    """上陣的每一個人：（名字, 武學, 內功）。本人在前（照自己那一份，player_art），再來是帶著的同伴、部下（部下沒有內功）——
    跟 _fighters 算威力的是同一份名冊，部下也上陣（F17）。回合演出（fighters）與大場面判讀的陣容（Game.fight_request，
    武學與成長設計 8.3）都從這裡走，兩邊不會一邊有部下、一邊沒有（計畫三 G7）。只給畫面與模型看，不算威力。"""
    p = state.player
    mine = [player_art(state, content, world, skill_id) for skill_id in (p.member.wugong_id, p.member.neigong_id)]
    out = [(p.name, *mine)]
    companions = world.companions()
    for key in p.team:
        progress = companions.get(key, CompanionProgress())
        out.append((
            content.characters[key].name,
            resolve_art(progress.wugong_id, content, world), resolve_art(progress.neigong_id, content, world),
        ))
    for _, follower in follower_rows(state, content):
        out.append((follower.name, resolve_art(follower.wugong, content, world), None))
    return out


def fighters(state: GameState, content: Content, world: WorldStateStore) -> list[rounds.Fighter]:
    """回合演出的我方陣容（武學與成長設計 8.2）：lineup 的每一個人報身上那門武學的名字與屬性；沒學武學的是 None。"""
    return [
        rounds.Fighter(name=name, art=art.name if art else None, attribute=art.attribute if art else None)
        for name, art, _ in lineup(state, content, world)
    ]


# ── 隊伍組成 ─────────────────────────────────────────────


def add_to_team(state: GameState, companion_id: str) -> list[str]:
    if companion_id in state.player.team:
        return []
    if len(state.player.team) >= MAX_TEAM_COMPANIONS:
        return [f"隊伍已經滿了（最多帶 {MAX_TEAM_COMPANIONS} 個夥伴），先讓一位夥伴離隊才能換人。"]
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
    pair_before = _worn_pairing(state, content, world)
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
    pair_after = _worn_pairing(state, content, world)
    if pair_after != pair_before:  # 換上之後內外搭配變了（同屬加成、相剋打折、或不再有）：多一句，數字是引擎的 pairing（FB-088）
        still, word, pct = _pairing_words(pair_before, pair_after)
        msgs.append(
            f"你的內功與武學現在{word}，整體威力 {pct}。" if still else f"你的內功與武學不再{word}，整體威力不再 {pct}。"
        )
    return msgs


def _worn_pairing(state: GameState, content: Content, world: WorldStateStore, swap: MartialArt | None = None) -> float:
    """身上這兩門現在的內外搭配（pairing）；swap 給了，就當作那一門換上身（同種類的那一欄換成它）再算。少一門是 1。"""
    member = state.player.member
    wugong, neigong = player_art(state, content, world, member.wugong_id), player_art(state, content, world, member.neigong_id)
    if swap is not None:
        wugong, neigong = (wugong, swap) if swap.kind == "內功" else (swap, neigong)
    return pairing(content, wugong, neigong)


def _signed_pct(ratio: float) -> str:
    """搭配的百分比，帶正負號（減號用 −）：同屬 +20%、相剋 −20%；整數不寫「.0」。跟 skillview 的 _pct 同一個寫法。"""
    return f"{ratio:+.1%}".replace(".0%", "%").replace("-", "−")


def _pairing_words(before: float, after: float) -> tuple[bool, str, str]:
    """（搭配還在不在, 同屬或相剋, 百分比）：換上後還有搭配就說換上後的樣子（−20% 換成 +20% 寫「同屬 +20%」，跟門下卡的
    「內外搭配」同一個數）；換上後沒有了，就說原本的那一個不再有（「不再相剋、不再 −20%」）。"""
    shown = after if after != 1 else before
    return after != 1, "同屬" if shown > 1 else "相剋", _signed_pct(shown - 1)


# 新武學跟身上那門比的那一句（W6；待 joy 潤）：「比身上的【甲】：威力 −0.3（第一成）、多了〔先手〕、少了〔厚〕」
COMPARE_HEAD = "比身上的【{worn}】：{power}（第一成）"
COMPARE_POWER = "威力 {diff}"
COMPARE_SAME_POWER = "威力相同"
COMPARE_MORE = "多了{names}"
COMPARE_LESS = "少了{names}"


def _trait_names(content: Content, art: MartialArt) -> list[str]:
    """這門武學帶的功效的名字（一般功效照屬性的清單、去掉重複的層數，再加特別功效、空格擲到的中階與高階），內容沒有那個功效就略過。
    只看「有沒有」：層數不同不算不同（功法卡的「功效」那一行才寫數字）。art 要是 player_art 那一份（槽已經填上）。"""
    names = []
    for attribute in dict.fromkeys(traits.traits_of(art)):
        trait = next((t for t in content.traits.general if t.key == attribute), None)
        if trait is not None:
            names.append(trait.name)
    sp = traits.special(content, art.special)
    if sp is not None:
        names.append(sp.name)
    for sid in art.extra_specials:
        extra = traits.special(content, sid)
        if extra is not None and extra.name not in names:
            names.append(extra.name)
    for top in traits.highs_of(content, art):
        names.append(top.name)
    return names


def compare_with_worn(state: GameState, content: Content, world: WorldStateStore, art: MartialArt) -> str:
    """新武學（功法庫裡的一門）跟身上同一種（武學對武學、內功對內功）那一門比的一句話（W6）；只顯示、不動任何數字。
    沒有東西可比（那一欄空著、這門就是身上那門、找不到資料）是空字串。

    比的是**第一成對第一成**，不是現在這一成：合成出來的從第一成起，身上那門常常已經練到更高，拿現在的威力比，
    新的永遠像退步；同在第一成比，看到的才是兩門功夫本身的差別（品質、微調）。數字是 martial_arts.power_at 照
    玩家自己那一份的品質（player_art）算的，跟功法卡寫的威力同一個來源。功效只列有沒有：新的多出來的、少掉的。"""
    member = state.player.member
    worn_id = member.neigong_id if art.kind == "內功" else member.wugong_id
    if worn_id is None or worn_id == art.id:
        return ""
    worn, mine = player_art(state, content, world, worn_id), player_art(state, content, world, art.id)
    if worn is None or mine is None:
        return ""
    diff = power_at(mine, 1) - power_at(worn, 1)
    power = COMPARE_SAME_POWER if round(diff, 1) == 0 else COMPARE_POWER.format(diff=f"{diff:+.1f}".replace("-", "−"))
    parts = [COMPARE_HEAD.format(worn=worn.name, power=power)]
    have = _trait_names(content, mine)  # 槽裡裝了什麼（player_art 已經填上）
    had = _trait_names(content, worn)
    more, less = [n for n in have if n not in had], [n for n in had if n not in have]
    if more:
        parts.append(COMPARE_MORE.format(names="".join(f"〔{n}〕" for n in more)))
    if less:
        parts.append(COMPARE_LESS.format(names="".join(f"〔{n}〕" for n in less)))
    line = "、".join(parts)
    # 換上後內外搭配變不變（FB-088；待 joy 潤）：跟另一種那門比，同屬加成、相剋打折、或原本的沒有了；沒變就不多說
    now, then = _worn_pairing(state, content, world), _worn_pairing(state, content, world, swap=mine)
    if now != then:
        still, word, pct = _pairing_words(now, then)
        other = "武學" if art.kind == "內功" else "內功"
        line += f"；換上後跟{other}{word}，整體 {pct}" if still else f"；換上後跟{other}不再{word}，整體不再 {pct}"
    return line


def practice_price(content: Content, level: int, scale: float = 1.0) -> int:
    """練成的價錢：第 level 成升 level+1 成要幾點心得（武學與成長設計 4.2）。只看第幾成、不看品質：
    升品時成不變，品質越高越貴的話，玩家會先趁下品把成練滿再修練，價錢就被繞過去。
    scale 是雲篆的折扣（treasures.amount(..., "practice")，玉璽碎片設計 7.1）：照 round(原價 × scale)、最少 1；熔煉照原價退，不傳。"""
    base = content.config.practice_xinde_per_level * level
    return base if scale == 1.0 else max(1, round(base * scale))


def can_practise(state: GameState, content: Content, kind: str) -> bool:
    """身上這一欄有武學、還沒第十成、而且付得起下一成的心得（練成花心得，設計 4.2）。
    機器人要不要練（bot.can_practise）與主畫面的提示（skillview.practice_hint）共用這一個條件。"""
    member = state.player.member
    slot, level_slot = ("neigong_id", "neigong_level") if kind == "內功" else ("wugong_id", "wugong_level")
    level = getattr(member, level_slot)
    return (
        getattr(member, slot) is not None and level < MAX_LEVEL
        and state.player.stats.get("xinde", 0) >= practice_price(content, level, treasures.amount(state, content, "practice"))
    )


def practice(
    state: GameState, content: Content, world: WorldStateStore, kind: str, rng: random.Random, safe: bool = False,
) -> list[str]:
    """練成：身上這一門加深一成，花心得（設計 4.2），累積受傷風險（設計文件六.2）。
    safe：序章裡的練功不受傷（新手引導計畫一），連受傷那一次亂數也不擲；序章外的亂數序列一個都沒動。"""
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
    price = practice_price(content, level, treasures.amount(state, content, "practice"))
    xinde = state.player.stats.get("xinde", 0)
    if xinde < price:
        return [
            f"心得不足：【{name}】從第{level}成練到第{level + 1}成要 {price} 點心得，"
            f"你只有 {xinde} 點，還差 {price - xinde} 點。"
        ]
    state.player.stats["xinde"] = xinde - price
    setattr(member, level_slot, level + 1)
    msgs = [f"【{name}】精進至第{level + 1}成。", f"心得 -{price}"]
    if not safe and rng.random() < cfg.practice_injury_chance:
        now, _cap = member_neili(content, member, con_of(state, content, world, PLAYER), season=state.world)
        member.injury += cfg.practice_injury_amount
        member.neili = max(0.0, now - cfg.practice_injury_amount)
        msgs.append(f"這一番苦練傷了氣血，氣血 -{cfg.practice_injury_amount:.0f}（累積內傷，需要療傷才能回到滿血）。")
    return msgs


def neili_cap(content: Content, level: int, con: float = BASE_STAT, scale: float = 1.0, season=None) -> float:
    """氣血上限：基礎＋每級加成，再乘上根骨的加成（武學與成長設計 6.1：上限 ×（1＋3%×（根骨−5））），
    四捨五入成整數——每個呼叫端拿到的、狀態列與角色卡寫出來的都是同一個數（根骨 6：329.6 → 330）。
    con 是根骨，從 con_of 讀（本人照存檔、同伴照他自己的，人物資質設計 14.3）；不傳就是基準。
    scale 是本人帶螭首時的倍數（Member.cap_scale，玉璽碎片設計 7.1），在四捨五入之前乘。
    season（這一季的 WorldState）：減法季每點加倍（per_point）；氣血的這一串（_cap_of、neili_ceiling、member_neili、regen_neili、
    _apply_toll）都照它往下傳，呼叫端一律給 state.world，狀態列、角色卡、打起來才是同一個數。"""
    cfg = content.config
    return float(round((cfg.neili_base + level * cfg.neili_per_level) * stat_factor(content, con, season) * scale))


def _cap_of(content: Content, member, con: float, plain: bool, season=None) -> float:
    """這個人的氣血上限：本人帶螭首時乘 Member.cap_scale（同伴是 CompanionProgress，沒有這一欄、不吃）；plain 時不乘（決戰的池子）。"""
    return neili_cap(content, member.level, con, 1.0 if plain else getattr(member, "cap_scale", 1.0), season)


MIN_CEILING_RATIO = 0.1  # 內傷再重，能回到的氣血上蓋也不低於上限的一成（氣血設計 §1.3：再低也照樣能出戰）


def neili_ceiling(content: Content, member, con: float = BASE_STAT, plain: bool = False, season=None) -> float:
    """內傷之後氣血自己能回到哪裡（上限 − 內傷，但不低於上限的一成）。con 是根骨，從 con_of 讀。
    本人帶螭首時上限乘 Member.cap_scale（同伴不吃）；plain 不乘。season 見 neili_cap。"""
    cap = _cap_of(content, member, con, plain, season)
    return max(cap * MIN_CEILING_RATIO, cap - getattr(member, "injury", 0.0))


def member_neili(content: Content, member, con: float = BASE_STAT, plain: bool = False, season=None) -> tuple[float, float]:
    """回傳（目前氣血, 上限）。member 可以是玩家的 Member 或同伴的 CompanionProgress。
    con 是根骨，從 con_of 讀。本人帶螭首時上限乘 Member.cap_scale（同伴是 CompanionProgress，沒有這一欄、不吃）；
    plain 不乘（決戰的池子，Game._battle_neili_cap）。season 見 neili_cap。

    `neili is None` 代表「回滿了」——有內傷時的「滿」是上蓋（上限 − 內傷），不是上限本身。
    所以根骨變高時：沒滿血的人目前氣血不變、上限變大；本來就滿的人照舊是滿的（跟升級一樣）。
    """
    cap = _cap_of(content, member, con, plain, season)
    ceiling = neili_ceiling(content, member, con, plain, season)
    now = ceiling if member.neili is None else min(member.neili, ceiling)
    return now, cap


def _price_here(state: GameState | None, content: Content) -> float:
    """療傷的價錢倍數：地盤福利（出陣探索與地盤設計 4.3 第 3 點：自己陣營的地盤便宜、別人的貴）× 名望的店家折扣（名聲設計 4.1）
    × 俠的醫館折扣（名聲 5.2，renown.clinic_factor）；state 是 None（純函式的呼叫）照原價。
    territory → rules → team：延後 import，避免循環。"""
    if state is None:
        return 1.0
    from . import clinic, figure_life, renown, territory  # noqa: PLC0415

    return (territory.price_here(state, content, heal=True) * renown.clinic_factor(state, content)  # price_here 照依附那一軍算自家地盤
            * figure_life.healer_factor(state, content)  # 華佗坐診的醫館
            * clinic.zhongjing_factor(state, content))  # 仲景欠你一次（《符水與湯藥》）


def heal_cost(content: Content, member, state: GameState | None = None) -> int:
    """療傷要多少銀兩：按內傷點數計價（氣血設計 §二，預設每 2 點內傷 1 兩，無條件進位）。

    刻意只看內傷、不看「目前氣血離上限多遠」——輕傷本來就會自己回，付錢去買它沒有意義
    （改之前就是這樣：療傷等於花錢跳過兩小時的等待，而內傷根本不存在）。
    state 給了照所在地的地盤福利打折或加價（_price_here）。
    """
    injury = max(0.0, getattr(member, "injury", 0.0))
    # 先 round 到小數第 9 位再無條件進位：10 × 1.2 的浮點雜訊（12.000000000000002）不能多收一兩
    return math.ceil(round(injury / max(1.0, content.config.heal_neili_per_silver) * _price_here(state, content), 9))


HEAL_FREE = "這一帶承露，醫館分文不取"  # 待 joy 潤：承露（玉璽碎片改版第 2 批）那一區療傷不收錢，療傷那一句的括號
HEAL_FREE_NOTE = "承露・分文不取"  # 待 joy 潤：療傷鈕上價錢那一格（skillview.heal_note）


def heal_free(state: GameState, content: Content) -> bool:
    """此刻療傷不收錢：人在承露降的那一區（seal_acts.dew_clinic；改版關著、沒有承露一律是假）。價錢（heal_cost）照舊算——
    heal_cost 是 0 會被 heal_problem 當成「氣血無恙」，所以只在 heal_plan 收 0、說法換一句。"""
    return seal_acts.dew_clinic(state, content)


def heal_plan(state: GameState, content: Content, member) -> tuple[int, int, int]:
    """這一次療傷治多少：（治幾點, 收幾兩, 還剩幾點）。銀兩夠就全治（收 heal_cost）；不夠時能治多少治多少
    （PM 2026-10-12：療傷只在醫館之後，窮的人內傷越疊越多、一次付不起就永遠治不了），每一兩治 heal_neili_per_silver 點。
    承露那一區（heal_free）全治、收 0。"""
    if heal_free(state, content):
        return round(max(0.0, getattr(member, "injury", 0.0))), 0, 0
    rate = max(1.0, content.config.heal_neili_per_silver) / _price_here(state, content)
    injury = max(0.0, getattr(member, "injury", 0.0))
    silver = max(0, state.player.stats.get("silver", 0))
    full = heal_cost(content, member, state)
    if silver >= full:
        return round(injury), full, 0
    points = min(injury, silver * rate)
    return int(points), silver, max(0, round(injury - points))


def heal_problem(state: GameState, content: Content, member, where: str | None = None) -> str | None:
    """療傷做不了的原因；None＝可以。heal 與修練頁的療傷鈕（skillview.heal_button）走同一個判斷，鈕上寫的跟按下去回的是同一句。
    where 是呼叫端問過 clinic.problem 的那一句（不在醫館；None＝在醫館或開關關著），排在「氣血無恙」之後、銀兩之前。"""
    cost = heal_cost(content, member, state)
    if cost <= 0:
        return "氣血無恙，不用療傷。"
    if where is not None:
        return where
    if state.player.stats.get("silver", 0) < 1 and not heal_free(state, content):  # 不夠全治時治一部分（heal_plan），一兩都沒有才做不了
        return f"銀兩不足：療傷需要 {cost} 兩。"
    return None


def heal(state: GameState, content: Content, member, where: str | None = None) -> list[str]:
    problem = heal_problem(state, content, member, where)
    if problem is not None:
        return [problem]
    points, cost, left = heal_plan(state, content, member)
    p = state.player
    p.stats["silver"] -= cost
    member.neili = None
    from . import clinic  # noqa: PLC0415

    if left > 0:
        member.injury = max(0.0, member.injury - points)
        return [f"銀兩只夠治一部分：內傷 -{points}，還剩 {left} 點（銀兩 -{cost}）。"] + clinic.zhongjing_note(state)
    healed = member.injury
    member.injury = 0.0
    if cost == 0 and heal_free(state, content):
        return [f"療傷完畢，內傷 -{healed:.0f}、氣血回滿（{HEAL_FREE}）。"]
    return [f"療傷完畢，內傷 -{healed:.0f}、氣血回滿（銀兩 -{cost}）。"] + clinic.zhongjing_note(state)


# ── 經驗與等級 ────────────────────────────────────────────


def level_cost(cfg, level: int) -> int:
    """第 level 級升 level+1 級要多少經驗：level_exp × level；到了 late_level_from（30）以後再乘
    （1＋late_exp_step ×（level − late_level_from ＋ 1）），越後面越陡（企劃者 2026-10-14「50 級加陡」）。
    升到第 30 級之前一個字都不變。"""
    base = cfg.level_exp * level
    if level < cfg.late_level_from:
        return base
    return round(base * (1 + cfg.late_exp_step * (level - cfg.late_level_from + 1)))


def growth_steps(cfg, level: int) -> int:
    """從第 1 級長到第 level 級，屬性長了幾「步」：第 late_level_from（30）級以前一級一步，之後每 late_stat_every（2）級一步
    （企劃者 2026-10-14：31 級後屬性點每 2 級 1 點）。本人的屬性點（× stat_points_per_level）與同伴的每級成長都照它。"""
    early = min(level, cfg.late_level_from) - 1
    return max(0, early) + max(0, level - cfg.late_level_from) // cfg.late_stat_every


def points_between(cfg, before: int, after: int) -> int:
    """從第 before 級升到第 after 級，本人拿到幾點屬性（舊規則；升級的每一個地方都走 level_points，它關著時叫這一個）。"""
    return (growth_steps(cfg, after) - growth_steps(cfg, before)) * cfg.stat_points_per_level


def level_points(state: GameState, content: Content, before: int, after: int) -> int:
    """本人從第 before 級升到第 after 級拿到幾點屬性（升級的五個地方都走這一個：grant_team_exp、決戰軍餉、翻地分紅、切磋、頭目戰）。
    減法季屬性五段（Config.jianfa 的 stat_milestones）開著：升級不給點，跨過一個境界（milestone_levels）給 stat_points_per_milestone，
    跨過的最後那一級記進 PlayerState.milestone_due（境界卡，Game.milestone_card；配完點清掉）；關著照 points_between。"""
    if not _jianfa(state, content, "stat_milestones"):
        return points_between(content.config, before, after)
    cfg = content.config.jianfa
    hit = growth.reached(cfg, before, after)
    if hit:
        state.player.milestone_due = hit[-1]
    return growth.milestone_points(cfg, before, after)


def exp_view(content: Content, member) -> dict | None:
    """狀態列展開時那一行：這一級攢了多少、升下一級要多少；滿級是 None。"""
    cfg = content.config
    if member.level >= cfg.max_level:
        return None
    return {"have": int(member.exp), "need": level_cost(cfg, member.level)}


MAXED_XINDE = "已達頂級，經驗化作心得 +{n}。"  # 待 joy 潤：滿級之後的經驗換成心得那一句（正式季整合 3.5，江湖紀錄）


def maxed(content: Content, member) -> bool:
    """這個人滿級了（Config.max_level）。"""
    return member.level >= content.config.max_level


def as_xinde(content: Content, exp: int) -> int:
    """滿級之後這一筆經驗換得幾點心得（3.5：Config.maxed_exp_per_xinde 換 1，不足的捨去）。只算、不給。"""
    return max(0, exp) // content.config.maxed_exp_per_xinde


CAPPED_XINDE = "境界已到，再往上只能打出來，經驗化作心得 +{n}。"  # 待 joy 潤：45 級以後不是仗的經驗換成心得那一句（減法季整合設計 4.2）


def _jianfa(state: GameState, content: Content, part: str) -> bool:
    """減法季的子開關在這一季開了沒（rules.jianfa；rules 反過來 import 這裡，延後 import）。"""
    from . import rules  # noqa: PLC0415

    return rules.jianfa(content, state.world, part)


def player_exp(state: GameState, content: Content, amount: int, source: str = "battle") -> tuple[int, int]:
    """本人這一筆經驗拆成（算經驗的, 換心得的）（減法季三道閘的第三道，整合設計 4.2）：source 是這一筆從哪裡來（growth.exp_source 認得的
    那幾種；不認得的當場炸，接線寫錯一看就知道）。三道閘開著（Config.jianfa 的 drill_gates）、不是仗的經驗到 drill_level_cap（45）為止，
    跨過去的那一截與 45 級以後的整筆換心得（growth.capped_exp）；仗的經驗、關著的季、已經滿級（照舊交給 maxed_xinde）原數回去。只算、不給。"""
    kind = growth.exp_source(source)
    member = state.player.member
    if kind == growth.BATTLE or amount <= 0 or maxed(content, member) or not _jianfa(state, content, "drill_gates"):
        return amount, 0
    cfg = content.config.jianfa
    return growth.capped_exp(cfg, member.level, amount, kind, room=growth.room_to_cap(cfg, content.config, member))


def maxed_xinde(state: GameState, content: Content, exp: int, source: str = "battle") -> int:
    """本人這一筆經驗換成心得的那一份（3.5，第 8 批通用）：已經滿級整筆照 5 換 1；減法季三道閘開著、不是仗的經驗過了 45 級的那一截也照換
    （player_exp）。記進心得、回換了幾點；都不換回 0（經驗照舊走 add_exp）。升到滿級那一下剩下的經驗不換（照舊丟掉）。
    同伴不換，照拿經驗（grant_team_exp）。"""
    p = state.player
    if not maxed(content, p.member):
        over = player_exp(state, content, exp, source)[1]
        gained = as_xinde(content, over) if over else 0
    else:
        gained = as_xinde(content, exp)
    if gained:
        p.stats["xinde"] = p.stats.get("xinde", 0) + gained
    return gained


def xinde_line(content: Content, member, n: int) -> str:
    """經驗換成心得那一句：滿級寫 MAXED_XINDE，還沒滿級（45 級的閘換的）寫 CAPPED_XINDE。"""
    return (MAXED_XINDE if maxed(content, member) else CAPPED_XINDE).format(n=n)


def add_exp(content: Content, member, amount: int, name: str, source: str = "battle") -> list[str]:
    """這個人（本人的 Member 或同伴的 CompanionProgress）加 amount 經驗，照升級表升級，回升級的那幾句。source 是這一筆從哪裡來
    （growth.exp_source；只驗認不認得——本人不是仗的經驗過 45 級的那一截，呼叫端先用 player_exp 拆掉）。"""
    growth.exp_source(source)
    cfg = content.config
    msgs: list[str] = []
    if member.level >= cfg.max_level or amount <= 0:
        return msgs
    member.exp += amount
    while member.exp >= level_cost(cfg, member.level) and member.level < cfg.max_level:
        member.exp -= level_cost(cfg, member.level)
        member.level += 1
        msgs.append(f"{name}升到第 {member.level} 級！")
    return msgs


def grant_team_exp(
    state: GameState, content: Content, world: WorldStateStore, amount: int, source: str = "battle",
) -> tuple[list[str], LevelUps | None]:
    """本隊每個人（本人與帶著出戰的同伴）各得 amount 經驗，照同一套 add_exp 規則升級；回傳（升級訊息, 誰升到第幾級）。
    訊息本人在前、同伴照隊伍順序（試玩回饋 FB-002：戰報一直寫「經驗 +N（每人）」，以前只有本人真的拿到）。
    誰升到第幾級另外結構化地回（LevelUps，FB-074）：戰鬥卡片拿它畫一行簡短的，訊息照舊一句一級、給戰報頁與江湖紀錄；
    沒有人升級是 None。

    同伴的等級與經驗存在全服共用的 CompanionProgress（world.update_companion 當場寫回共用世界，
    跟著那一筆交易存檔），所以換頁、重新登入都還在；換季時跟其他同伴進度一起清空。氣血上限
    （neili_cap：基礎＋每級加成，本人再乘上根骨）由等級算出來，升級就跟著變高（氣血設計 A1：等級只買氣血上限）；
    目前氣血不變，不順便回血。
    source 是這一筆從哪裡來（growth.exp_source）：減法季三道閘開著時本人不是仗的經驗只加到 45 級（player_exp；換心得的那一截由呼叫端
    先叫 maxed_xinde 記），同伴照拿全額。"""
    p = state.player
    ups = LevelUps()
    before = p.member.level
    msgs = add_exp(content, p.member, player_exp(state, content, amount, source)[0], p.name)  # source 在 player_exp 驗過
    gained = p.member.level - before
    if gained > 0:  # 升級給屬性點（武學與成長設計 6.2）：一次升好幾級就給好幾點，只給本人
        points = level_points(state, content, before, p.member.level)  # 30 級以後兩級一點（減法季：只有境界那一級給）：升了一級可能沒有點
        p.stat_points += points
        if points:
            msgs.append(f"你有 {p.stat_points} 點屬性可以分配（點名號展開）。")
        ups.you, ups.points = p.member.level, p.stat_points
    mate = treasures.amount(state, content, "mate_exp")  # 歸心：同伴拿到的經驗 ×1.1（玉璽碎片設計 7.1）
    for companion_id in state.player.team:
        name = content.characters[companion_id].name
        levels: list[str] = []

        def gain(progress, name=name, levels=levels) -> None:
            was = progress.level
            levels.extend(add_exp(content, progress, round(amount * mate), name))
            if progress.level > was:
                ups.mates.append((name, progress.level))

        world.update_companion(companion_id, gain)
        msgs += levels
    ups.lines = list(msgs)
    return msgs, (ups if msgs else None)


def add_team_exp(state: GameState, content: Content, world: WorldStateStore, amount: int, source: str = "battle") -> list[str]:
    """同 grant_team_exp，只回升級訊息（操練等不畫戰鬥卡片的地方用）。"""
    return grant_team_exp(state, content, world, amount, source)[0]


def regen_neili(content: Content, member, fraction: float, con: float = BASE_STAT, plain: bool = False, season=None) -> None:
    """氣血隨時間回復——只回到上蓋（上限 − 內傷），內傷那部分要療傷才清得掉。con 是根骨，從 con_of 讀。
    本人帶螭首時上限乘 Member.cap_scale（同伴不吃）。season 見 neili_cap。"""
    if member.neili is None:
        return
    cap = _cap_of(content, member, con, plain, season)
    ceiling = neili_ceiling(content, member, con, plain, season)
    member.neili += cap * fraction  # 回復速度照上限算，所以內傷不會讓回復變慢
    if member.neili >= ceiling:
        member.neili = None


def heal_fraction(state: GameState, content: Content, world: WorldStateStore, fraction: float) -> list[str]:
    """本人回氣血上限的 fraction（吸取、回春，武學與成長設計 13.2、13.4）；回到天花板（上限 − 內傷）為止，內傷照舊要療傷
    才清得掉。回到天花板就是「滿」，記成 None（member_neili 的約定：之後升級、根骨變高，滿的人照舊是滿的）。
    回傳「氣血 +N」，回不到 1 點不寫（氣血照樣回了）。"""
    member = state.player.member
    con = con_of(state, content, world, PLAYER)
    now, cap = member_neili(content, member, con, season=state.world)
    ceiling = neili_ceiling(content, member, con, season=state.world)
    after = min(ceiling, now + cap * fraction)
    member.neili = None if after >= ceiling else after
    gained = after - now
    return [f"氣血 +{gained:.0f}"] if gained >= 1 else []


def shift_hp(state: GameState, content: Content, world: WorldStateStore, key: str, fraction: float) -> list[str]:
    """本命戰法回（fraction 正）或自扣（負）這個人氣血上限的幾成（tactics.Clash.hp）。回的照 heal_fraction（回到上限 − 內傷為止）；
    自扣的不變成內傷、扣到 0 為止。本人回傳「氣血 +N」「氣血 -N」（不到 1 點不寫），同伴照改、不寫。"""
    if not fraction:
        return []
    if key == PLAYER and fraction > 0:
        return heal_fraction(state, content, world, fraction)
    con = con_of(state, content, world, key)

    season = state.world

    def move(member) -> float:
        now, cap = member_neili(content, member, con, season=season)
        after = min(neili_ceiling(content, member, con, season=season), max(0.0, now + cap * fraction))
        member.neili = None if after >= neili_ceiling(content, member, con, season=season) else after
        return after - now

    if key == PLAYER:
        changed = move(state.player.member)
        return [f"氣血 {changed:+.0f}"] if abs(changed) >= 1 else []
    world.update_companion(key, move)
    return []


# ── 遭遇/劇情戰：串接 encounter.py 的單次判定 ───────────────


def team_conditions(state: GameState, content: Content, world: WorldStateStore) -> list[float]:
    """本隊每個人的氣血狀態係數，順序跟 team_participants 一致（氣血設計 §1.1：帶傷出手較弱）。
    本人身上帶【厚】時，見底的下限高一點（武學與成長設計 13.2）；同伴照舊。"""
    floor = encounter.CONDITION_FLOOR + traits.amount(content, traits.loadout(state, content, world), "condition_floor")
    return [
        encounter.condition_of(
            *member_neili(content, member, con_of(state, content, world, key), season=state.world),
            floor=floor if key == PLAYER else encounter.CONDITION_FLOOR,
        )
        for key, member in zip(team_keys(state), team_participants(state, world), strict=True)
    ]


def trait_mods(content: Content, lo: traits.Loadout) -> encounter.Mods:
    """本人身上的功效換成遭遇戰的數字（武學與成長設計 13.2、13.4）。沒有功效的人是空的 Mods（單次判定跟以前一模一樣）。

    特別功效目前照「掛點」記在 Loadout.specials（一個掛點一個，content.check_traits 擋共用）。名將本命絕學（13.5）的獨特
    特別功效進來時，若要改成照 id 記，下面每一處「按掛點讀」都要跟著改——全部的清單（讀的是 lo.specials 的鍵或值）：
    - traits.py：loadout（寫入，同一個掛點只留第一個）、has（`hook in lo.specials`）。
    - team.py：trait_mods（`.get("power_from_difficulty")`、`"double_luck" in`）、fight（`"no_loss" in`）、
      take_encounter_toll（`"no_injury" in`）。
    - engine.py：_battle_rewards（`.get("win_xinde")`）、_take_toll（`.get("heal_after")`）、_action_costs（`.get("train_stamina")`）、
      _play_rounds（`.get("no_loss")`）、_trait_lines（`double_luck`、`power_from_difficulty`、`no_injury`、`win_xinde`、
      `heal_after`、`train_stamina` 各一處 `in` 或 `[...]`）。
    - 一般功效不在這裡：它們照屬性記層數、數字由 traits.amount 讀。"""
    # 本命戰法第三批（定案 /mnt/project-files/plan/武學與兵器戰法定案.md）：先手、破甲、險、連環、借力改成回合裡的戰法（tactics.py），
    # 不在單次判定裡另算一次；只剩穩把這一場的運氣縮小（回合裡的起伏就是從這一場的運氣攤出來的）
    return encounter.Mods(luck_scale=1 - traits.amount(content, lo, "luck_narrow"))


def pairing(content: Content, wugong: MartialArt | None, neigong: MartialArt | None) -> float:
    """內功與武學的搭配（武學與成長設計 5.1）：同屬性加成、相剋的一對打折、其他不變；少一門就不算。
    加成與打折兩支都夾在 encounter.BOOST_FLOOR 以上（設定寫錯也一樣），不會讓整個人的威力變成負的。"""
    if wugong is None or neigong is None or not wugong.attribute or not neigong.attribute:  # 兼容並蓄的武學沒有屬性：不搭也不剋
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


_BACKED: ContextVar[float] = ContextVar("backed", default=1.0)


@contextmanager
def backed(factor: float):
    """NPC 智能 2.0的並肩出陣（parley.py）：這一仗之內本人的威力乘 factor（Game._act 的出陣包著它；1 是一個位元都不動）。"""
    token = _BACKED.set(factor)
    try:
        yield
    finally:
        _BACKED.reset(token)


def player_boost(state: GameState, content: Content, world: WorldStateStore, *, seal: bool = True) -> encounter.Boost:
    """玩家本人的加成：臂力管外功、根骨管內功（武學與成長設計 6.1）；整個人再乘上內外搭配與兩門各自的
    正邪共鳴（5.1、7.4）。搭配至少是 BOOST_FLOOR、共鳴至少是 1，所以乘出來的 factor 不會低於下限。
    再乘身上兵器的加成（兵器設計第三節）與玉璽碎片的戰力（改版第三章，treasures.power_scale：沒碎片、開關關著是 1）。
    seal=False 不乘碎片：奪璽單挑的快照與江湖水漲的浮動難度照這一份（改版：碎片搶得走、強者的 +10% 不被對手同步吃掉）。"""
    stats, member = state.player.stats, state.player.member
    wugong = player_art(state, content, world, member.wugong_id)
    neigong = player_art(state, content, world, member.neigong_id)
    factor = (pairing(content, wugong, neigong) * resonance(state, content, wugong) * resonance(state, content, neigong)
              * (1 + weapons.bonus(state.player.weapon, wugong, content, world)))  # 兵器（兵器設計 3.1）：配不上是 1
    scale = treasures.power_scale(state, content) if seal else 1.0
    if scale != 1.0:  # 沒碎片時一個位元也不動（不多乘一次 1.0 之外的東西）
        factor *= scale
    if _BACKED.get() != 1.0:  # 並肩出陣：同上，沒有人陪的仗一個位元也不動
        factor *= _BACKED.get()
    return encounter.Boost(  # 每一點的效果照這一季（stat_bonus 的 season：減法季每點加倍）
        outer=stat_bonus(content, stats.get("str", BASE_STAT), state.world),
        inner=stat_bonus(content, con_of(state, content, world, PLAYER), state.world),
        factor=factor,
    )


def mate_boost(state: GameState, content: Content, world: WorldStateStore, key: str) -> encounter.Boost:
    """同伴的加成（人物資質設計 14.3）：吃跟本人同一套——他自己的臂力管他的武學、根骨管他的內功，再乘上他自己那兩門的
    內外搭配（同伴的天分就是他那一路武學）。正邪共鳴看的是你的善名惡名、功效只算本人，所以同伴不吃。"""
    progress = world.get_companion(key)
    wugong = resolve_art(progress.wugong_id, content, world)
    neigong = resolve_art(progress.neigong_id, content, world)
    return encounter.Boost(
        outer=stat_bonus(content, member_stats(state, content, world, key)["str"], state.world),
        inner=stat_bonus(content, con_of(state, content, world, key), state.world),  # 根骨只從 con_of 讀
        factor=pairing(content, wugong, neigong),
    )


def follower_strength(content: Content, follower: FollowerDef, drill: FollowerDrill | None = None) -> int:
    """部下的臂力：模板的加上傳功傳的（drill.arm），最多 stat_cap。"""
    return min(content.config.stat_cap, follower.stats.get("str", BASE_STAT) + (drill.arm if drill else 0))


def follower_boost(content: Content, follower: FollowerDef, drill: FollowerDrill | None = None, season=None) -> encounter.Boost:
    """部下的加成（人物資質設計 14.3）：只有一門武學，吃模板的臂力（加傳功傳的）；沒有內功、不算搭配與共鳴。部下以前完全沒有加成。
    season 見 stat_bonus（減法季每點加倍）。"""
    return encounter.Boost(outer=stat_bonus(content, follower_strength(content, follower, drill), season))


def team_boosts(state: GameState, content: Content, world: WorldStateStore, *, seal: bool = True) -> list[encounter.Boost]:
    """跟陣容一一對應（本人、出戰的同伴、部下），一個都不能少——少一個 encounter.team_power 就會報錯，
    而不是默默漏算（F17、計畫二 G1）。同伴、部下吃自己的屬性（人物資質設計 14.3；原本是空的加成）。
    seal 見 player_boost（只動本人那一份；同伴、部下本來就不吃碎片）。"""
    return (
        [player_boost(state, content, world, seal=seal)]
        + [mate_boost(state, content, world, key) for key in state.player.team]
        + [follower_boost(content, follower, drill_of(state, key), state.world) for key, follower in follower_rows(state, content)]
    )


def dodge_chance(state: GameState, content: Content) -> float:
    """本人的身法讓落敗有機會閃成僵持（人物資質設計 14.4）：比 5 每多一點 dodge_per_point，夾在 0～1；同伴不另外算。
    金角 +3 個百分點（玉璽碎片設計 7.1）。每一點照這一季（per_point：減法季每點加倍）。"""
    agi = float(state.player.stats.get("agi", BASE_STAT))
    rate = per_point(content, getattr(state, "world", None), "dodge_per_point")
    return min(1.0, max(0.0, (agi - BASE_STAT) * rate + treasures.amount(state, content, "dodge")))


def armor_cut(state: GameState, content: Content, world: WorldStateStore) -> float:
    """本人身上那件防具這一場少扣幾成氣血（裝備四欄設計 4.1、4.2）：照身上那門內功（自己那一份）算對上內功的 ±，開關關著、沒穿是 0。
    take_encounter_toll、toll_saved 與截殺輸的一方（Game._raid_spoils）都讀它；armor 不能 import team，內功在這裡解好再傳進去。"""
    return armor.cut(state.player.armor, player_art(state, content, world, state.player.member.neigong_id), content)


def take_encounter_toll(
    state: GameState, content: Content, world: WorldStateStore, tier: str, *, wild: bool = False, share: float = 1.0,
) -> list[str]:
    """一場遭遇戰打完的氣血代價（氣血設計 §1.3）：按結果扣氣血，其中一部分變成內傷。

    沒有這一段的話戰鬥是**沒有損耗的免費收入**——而那正是「遊歷」復活之後最明顯的破口：
    打得越多拿得越多，卻完全不必付出什麼。扣掉的量按上限的比例算，所以等級（上限）
    決定的是「撐得住幾場」，不是「打得多痛」。

    wild：探索時撞上的野怪（探索三選一設計 4.2），扣的量再乘上 `wild_neili_loss_factor`；
    內傷是扣掉的量的固定幾成，所以照同一個比例變少。遊歷與劇情戰不帶這個旗標，一點都不變。

    玩家本人的身法讓一場少掉一點氣血（閃得開）、根骨讓其中變成內傷的少一點（武學與成長設計 6.1）；
    同伴照他自己的身法、根骨（人物資質設計 14.3）。本人身上的防具（裝備四欄設計 4.3）跟化勁相加，合計夾在
    `Config.armor.total_cap`；同伴不吃防具。
    share：對手真的打到你的回合佔幾成（本命戰法讓他定身、打空、打到自己、化影的回合不算，tactics.Clash.blocked_share）；平常是 1。
    本人帶螭首（玉璽碎片改版，treasures.amount 的 injury）時變成內傷的那一份再乘它；同伴不吃。
    """
    cfg = content.config
    fraction = cfg.encounter_neili_loss.get(tier, 0.0) * (cfg.wild_neili_loss_factor if wild else 1.0) * max(0.0, share)
    if fraction <= 0:
        return []
    stats = state.player.stats
    msgs = []
    for key in team_keys(state):
        if key == PLAYER:
            lo = traits.loadout(state, content, world)
            # 化勁（13.2）＋防具（裝備四欄 4.3），合計夾在 total_cap；防具關著時 armor_cut 是 0、化勁上限 50% 本來就低於 60%，數字不變
            cut = min(cfg.armor.total_cap, traits.amount(content, lo, "toll_cut") + armor_cut(state, content, world))
            lost, hurt = _apply_toll(
                content, state.player.member, fraction * (1 - cut),
                agi=stats.get("agi", BASE_STAT), con=con_of(state, content, world, PLAYER),
                injury=treasures.amount(state, content, "injury"),  # 螭首（玉璽碎片改版）：變成內傷的減半；沒帶是 1
                season=state.world,
            )
            if round(lost) > 0:  # 本來就見底、一滴都沒得扣時不寫「氣血 -0」（零的變化是雜訊）；內傷照樣寫
                msgs.append(f"氣血 -{lost:.0f}")  # 照既有慣例寫變化量（跟「銀兩 -5」「心得 +12」同一串）
            if hurt >= 1:
                msgs.append(f"內傷 +{hurt:.0f}")
        else:
            agi = member_stats(state, content, world, key)["agi"]
            con = con_of(state, content, world, key)  # 根骨只從 con_of 讀
            world.update_companion(
                key, lambda progress, agi=agi, con=con: _apply_toll(content, progress, fraction, agi=agi, con=con, season=state.world),
            )
    return msgs


def toll_saved(
    state: GameState, content: Content, world: WorldStateStore, tier: str, *, wild: bool = False, share: float = 1.0,
) -> tuple[int, int]:
    """（化勁少扣的氣血, 不動免掉的內傷）（FB-084）：這一場本人真的扣的，跟拿掉那一個功效照一般算的差。
    各自只拿掉它自己那一個（化勁看氣血、不動看內傷），所以兩個數字不互相混。防具（裝備四欄設計 4.3）不是功效、一直留著：
    化勁的對照組是「只有防具」，真的扣的是「防具加化勁、夾在 Config.armor.total_cap」，所以防具省下的不會被算成化勁的。
    只讀、不動狀態：在 take_encounter_toll 之前呼叫，量的是還沒扣的那一刻；用本人的複本照 _apply_toll 同一套算，四捨五入跟
    「氣血 -N」「內傷 +N」的寫法一樣，所以「少扣了 N」加上畫面上的「氣血 -M」剛好是只有防具時的 N+M。
    沒有這兩個功效（只有防具也算沒有）、或這個結果不扣氣血，是 (0, 0)。"""
    cfg = content.config
    fraction = cfg.encounter_neili_loss.get(tier, 0.0) * (cfg.wild_neili_loss_factor if wild else 1.0) * max(0.0, share)
    lo = traits.loadout(state, content, world)
    cut, still = traits.amount(content, lo, "toll_cut"), False  # 不動以前免內傷；第三批起改成不受定身、卸勁（tactics.py），這裡恆為 False
    if fraction <= 0 or (cut <= 0 and not still):
        return 0, 0
    worn = min(cfg.armor.total_cap, armor_cut(state, content, world))
    total = min(cfg.armor.total_cap, cut + worn)
    agi, con = state.player.stats.get("agi", BASE_STAT), con_of(state, content, world, PLAYER)

    def toll(cut_: float, injury: float) -> tuple[float, float]:
        return _apply_toll(
            content, state.player.member.model_copy(), fraction * (1 - cut_), agi=agi, con=con, injury=injury, season=state.world,
        )

    real_lost, real_hurt = toll(total, 0.0 if still else 1.0)
    saved = round(toll(worn, 0.0 if still else 1.0)[0]) - round(real_lost) if cut > 0 else 0
    spared = round(toll(total, 1.0)[1]) - round(real_hurt) if still else 0
    return max(0, saved), max(0, spared)


def _apply_toll(
    content: Content, member, fraction: float, agi: float = BASE_STAT, con: float = BASE_STAT, injury: float = 1.0,
    season=None,
) -> tuple[float, float]:
    """扣一場的氣血，回傳（實際掉了多少氣血, 其中變成內傷的量）。身法減一場的損耗、根骨減其中變成內傷的
    比例，各 ×（1−3%×（屬性−5）），夾在 0 以上；氣血上限也照根骨算。同伴傳他自己的（人物資質設計 14.3）。
    injury 是變成內傷的倍數（預設 1；本人帶【不動】時是 0，扣的氣血全算輕傷，武學與成長設計 13.4）。season 見 neili_cap。"""
    now, cap = member_neili(content, member, con, season=season)
    loss = cap * fraction * max(0.0, 1 - stat_bonus(content, agi, season))
    hurt = loss * content.config.injury_share * max(0.0, 1 - stat_bonus(content, con, season)) * injury
    member.injury += hurt
    member.neili = max(0.0, now - loss)
    after, _ = member_neili(content, member, con, season=season)
    return now - after, hurt


def fight(
    state: GameState, content: Content, world: WorldStateStore, squad_id: str, rng: random.Random,
    *, difficulty: float | None = None, shift: float = 0.0, dodge: bool = True, tier: str | None = None,
    draw_floor: float | None = None,
) -> encounter.EncounterResult:
    """difficulty 給了就取代隊伍的難度（挑戰大勢人物本人：難度跟著聲威走，見 figures.difficulty）。
    tier 給了（序章雪恥那一場，新手引導計畫一）結果就照寫好的：數字照舊算、功效照舊折進去，判定出來之後只把結果換掉；
    換在護命與閃避之前，所以那兩樣都不動它（也就不會標 guarded）。
    shift 是大場面判讀的優勢換算成的判定差距平移（encounter.advantage_shift，武學與成長設計 8.3，照沒有功效的運氣範圍算）；
    平常是 0。本人的功效改了運氣範圍時，resolve_encounter 會把它等比例縮放，同一個優勢推的百分點不變（Task 3 審查 I1）。
    結果定了（優勢平移也算進去）之後，本人的身法才有機會把落敗閃成僵持（dodge_chance，人物資質設計 14.4）；
    dodge=False 不擲閃避、也不動那一次亂數——劇情戰的勝敗是人寫好的（僵持也算敗），閃了只會自相矛盾（最終審查 I1）。"""
    squad = content.squads[squad_id]
    arts = team_arts(state, content, world)
    power = encounter.team_power(*_with_attribute(_styled_fighters(state, content, world, arts, squad), arts, squad.attribute))
    lo = traits.loadout(state, content, world)
    mods = trait_mods(content, lo)
    if draw_floor is not None:  # 挑戰大勢人物本人：僵持收窄（rise.draw_floor）
        mods = mods.model_copy(update={"draw_floor": draw_floor})
    result = encounter.resolve_encounter(power, squad.difficulty if difficulty is None else difficulty, rng, shift=shift, mods=mods)
    if tier is not None:
        return result.model_copy(update={"tier": tier})
    # 一回合一回合打（tactics.py，Joy 2026-10-15 選「全部改回合制」）：擲出來的差距攤成回合，本命戰法在回合裡改氣勢；
    # 亂數是自己一份（名號｜這一場的戰報流水號｜回合），不碰 Game.rng。沒有戰法時結果一個字都不變
    seed = random.Random(f"{state.player.name}|{state.battle_seq + 1}|回合")
    ctx = tactic_ctx(state, content, world, squad, result.difficulty)
    result = clash_result(result, mods, tactic_holders(state, content, world), ctx, content, seed,
                          foe=foe_tactics(state, content, squad, ctx))
    if not dodge:
        return result
    return encounter.dodge(result, dodge_chance(state, content), rng)  # 先平移、結果定了才閃（14.4）；勝算（estimate）不含


def clash_result(
    result: encounter.EncounterResult, mods: encounter.Mods, holders: list[tactics.Holder], ctx: tactics.Ctx, content: Content,
    rng: random.Random, foe: tuple[list[tactics.Holder], tactics.Ctx] | None = None,
) -> encounter.EncounterResult:
    """單次判定擲出的結果一回合一回合打一遍（tactics.play）：回合數照擲出來的結果（rounds.ROUNDS），收場的差距照門檻重判。
    foe 是對手那一方的本命戰法（foe_tactics：挑戰大勢人物本人）。兩邊都沒有本命戰法時差距原樣回來、結果不變。"""
    effective = result.difficulty * (1 - mods.difficulty_cut)
    low, high = rounds.ROUNDS[result.tier]
    foe_holders, foe_ctx = foe if foe is not None else ([], None)
    clash = tactics.play(result.margin, effective, rng.randint(low, high), holders, ctx, content.config.tactics, rng,
                         foe_holders=foe_holders, foe_ctx=foe_ctx)
    if clash.margin == result.margin:
        return result.model_copy(update={"clash": clash})
    return result.model_copy(update={"clash": clash, "margin": clash.margin, "tier": encounter.tier_of(clash.margin, effective, mods)})


def tactic_holders(state: GameState, content: Content, world: WorldStateStore) -> list[tactics.Holder]:
    """這一場誰帶著戰法：本人身上練著的兩門本命、出戰同伴練著的兩門（同伴照自己練的，本命武學是他自己的），
    再加本人自己的武學功效與身上兵器、防具的特技（own_extras，第三批）。"""
    rows = [(state.player.name, PLAYER, state.player.member.wugong_id, state.player.member.neigong_id)]
    for key in state.player.team:
        mate = world.get_companion(key)
        rows.append((member_name(state, content, key), key, mate.wugong_id, mate.neigong_id))
    return own_extras(state, content, world, tactics.holders_of(content, rows, world, own_levels(state), own_copies(state, content, world)))


def own_levels(state: GameState) -> dict[str, int]:
    """本人身上兩門練到第幾成（自創的招前幾成還生，tactics.holders_of）。"""
    m = state.player.member
    return {k: v for k, v in ((m.wugong_id, m.wugong_level), (m.neigong_id, m.neigong_level)) if k}


def own_copies(state: GameState, content: Content, world: WorldStateStore) -> dict[str, MartialArt]:
    """本人身上兩門裡自創的那幾門，自己那一份（player_art：品級照自己修到的，破境了招升為絕招）。"""
    out: dict[str, MartialArt] = {}
    m = state.player.member
    for sid in (m.wugong_id, m.neigong_id):
        if sid and sid not in content.skills:
            art = player_art(state, content, world, sid)
            if art is not None:
                out[sid] = art
    return out


def gear_tactics(state: GameState, content: Content) -> list[tuple[str, TacticDef, str | None]]:
    """身上兵器與防具的特技（第三批）：（裝備 id, 特技, 名將本命兵器的人物 id）。照 tactics.item_tactic（神器原品照內容寫、仿品發動率
    乘 Config.tactics.copy_rate，名將本命兵器照 gear.json 的 signature_arms；一般兵器、名器沒有）。那一欄的裝備開關關著不算。"""
    out: list[tuple[str, TacticDef, str | None]] = []
    for item, slot in ((state.player.weapon, "weapon"), (state.player.armor, "armor")):
        if item is None or not equipment.on(content, slot):
            continue
        found = tactics.item_tactic(content, item)
        if found is not None:
            out.append((item.id, found[0], found[2]))
    return out


def gear_bond(content: Content, art: MartialArt, item) -> tuple[TacticBond, str] | None:
    """鑄器配招（玩家武學追上本命）：這件裝備讓那一門絕招變強多少：（加強, 怎麼來的）。神器原品綁了這一門（以器配招）照功效寫的
    ultimate_bond；名器（隱藏配方打的、不是神器）屬性跟這一門相同是小一截的人器合一（發動率 +Config.tactics.named_bond_rate）。
    其餘是 None。"""
    trait = traits.ultimate_trait(content, art)
    if item is None or trait is None:
        return None
    if item.original and item.secret and item.bound_art == art.id and trait.ultimate_bond is not None:
        return trait.ultimate_bond, BOUND_SOURCE
    if equipment.is_named(item) and item.attribute == art.attribute:  # 隱藏配方的名器與四階名器（正式季整合 5.2：好處照現在的名器）
        rate = content.config.tactics.named_bond_rate
        return TacticBond(desc=NAMED_BOND.format(pct=round(rate * 100)), rate=rate), NAMED_SOURCE
    return None


BOUND_SOURCE = "以器配招"
NAMED_SOURCE = "名器同氣"
NAMED_BOND = "屬性相同，絕招發動率 +{pct}%"


def ultimate_tactics(state: GameState, content: Content, world: WorldStateStore) -> list[tuple[str, TacticDef]]:
    """絕學立招：本人身上兩門裡自己合成、練成絕學的那幾門的絕招（traits.ultimate_of），再照身上的兵器與防具加強
    （gear_bond：以器配招的神器原品先算，沒有才看名器；一門只吃一件）。回（武學 id, 絕招）。"""
    out: list[tuple[str, TacticDef]] = []
    p = state.player
    gear = [item for item, slot in ((p.weapon, "weapon"), (p.armor, "armor")) if item is not None and equipment.on(content, slot)]
    for skill_id in (p.member.wugong_id, p.member.neigong_id):
        art = player_art(state, content, world, skill_id)
        ult = traits.ultimate_of(content, art)
        if ult is None:
            continue
        bonds = [b for b in (gear_bond(content, art, item) for item in gear) if b is not None]
        bonds.sort(key=lambda b: b[1] != BOUND_SOURCE)
        out.append((skill_id, tactics.bonded(ult, bonds[0][0]) if bonds else ult))
    return out


def own_extras(state: GameState, content: Content, world: WorldStateStore, holders: list[tactics.Holder]) -> list[tactics.Holder]:
    """本命戰法之後接本人自己的：名將本命兵器的人器合一（身上也練著那位名將的本命時，他那一門照 bond 加強）、武學功效（traits.tactic_defs）、
    兵器與防具的特技。同名的只算一個（holders_of 同一條）。"""
    name = state.player.name
    gear = gear_tactics(state, content)
    bonds = {figure: arm.bond for arm in content.gear.signature_arms for _id, _t, figure in gear
             if figure == arm.character and arm.bond is not None}
    out = [  # 只加強卡上寫的那一門（tactics.bond_fits，PM 2026-10-16），那位名將的另一門照舊
        h.model_copy(update={"tactic": tactics.bonded(h.tactic, bonds[h.figure])})
        if h.key == PLAYER and h.figure in bonds and tactics.bond_fits(h, h.figure, bonds[h.figure]) else h
        for h in holders
    ]
    seen = {h.tactic.name for h in out}
    extra = ultimate_tactics(state, content, world)  # 絕學立招排在功效前面（同名時算它）
    extra += [(f"trait:{t.name}", t) for t in traits.tactic_defs(content, traits.loadout(state, content, world))]
    extra += [(item_id, t) for item_id, t, _f in gear]
    for skill, tactic in extra:
        if tactic.name in seen:
            continue
        seen.add(tactic.name)
        out.append(tactics.Holder(who=name, key=PLAYER, skill=skill, tactic=tactic))
    return out


def foe_tactics(
    state: GameState, content: Content, squad: Squad, ctx: tactics.Ctx,
) -> tuple[list[tactics.Holder], tactics.Ctx] | None:
    """對手那一方的本命戰法：這一路是大勢人物本人的隊伍（FigureDef.squad，人物表寫了 character）時，他自己的本命武學與本命內功
    照樣發動（本命戰法第二批）。條件從他那一邊看：身法照難度、對手是你的陣營、這裡歸他的陣營算他的地盤。
    Config.tactics.foe_tactics 關著、或不是大勢人物本人是 None。"""
    if not content.config.tactics.foe_tactics:
        return None
    figure = next((f for f in content.figures.values() if f.squad == squad.id and f.character), None)
    char = content.characters.get(figure.character) if figure is not None else None
    if char is None:
        return None
    own = tactics.figure_arts(content, char)  # 只認本命（FB-640：起始帶的學來的武學不算）
    wugong = char.starting_wugong if char.starting_wugong in own else None
    neigong = char.starting_neigong if char.starting_neigong in own else None
    holders = tactics.holders_of(content, [(figure.name, tactics.FOE_KEY, wugong, neigong)])
    if not holders:
        return None
    from . import territory  # territory → rules → team：照用的時候才 import

    owner = territory.controller(state.world, content, state.player.location)
    return holders, tactics.Ctx(
        foe=tactics.OUR_SIDE, our_agility=ctx.foe_agility, foe_agility=ctx.our_agility, night=ctx.night,
        foe_faction=state.player.faction, own_turf=owner is not None and owner == figure.faction,
    )


def tactic_ctx(state: GameState, content: Content, world: WorldStateStore, squad: Squad, difficulty: float) -> tactics.Ctx:
    """這一場戰法要看的條件：雙方身法（對手照難度，同回合演出）、夜裡、坐騎的階、善名惡名、部下幾人、對手陣營、這裡歸不歸你的陣營、開打時的氣血。"""
    from . import territory  # territory → rules → team：照用的時候才 import

    p = state.player
    now, cap = member_neili(content, p.member, con_of(state, content, world, PLAYER), season=state.world)
    mount = p.mount if mounts.on(content) else None
    owner = territory.controller(state.world, content, p.location) if p.faction else None
    return tactics.Ctx(
        foe=squad.name, our_agility=float(p.stats.get("agi", BASE_STAT)), foe_agility=rounds.foe_agility(difficulty),
        night=calendar.is_night(state.world.time, content, state.world), mount_tier=mount.tier if mount is not None else 0,
        good=int(p.stats.get("good", 0)), evil=int(p.stats.get("evil", 0)), followers=len(follower_rows(state, content)),
        foe_faction=squad.faction, own_turf=owner is not None and owner == p.faction,
        hp_ratio=now / cap if cap > 0 else 1.0, team=team_keys(state),
    )


def self_side(state: GameState, content: Content, world: WorldStateStore, *, mounted: bool = False, troops: bool = False) -> tactics.BoutSide | None:
    """自己挑招的仗（頭目戰、擂台、奪璽單挑）與決戰帶的本命戰法：只算本人身上的兩門（同伴不上這幾種仗）。條件照 tactic_ctx，
    對手的名字與身法開打時才換上（tactics.open_bout）；mounted、troops 是這種仗算不算坐騎與部下（決戰算、單挑不算）。
    本人沒有本命戰法是 None。"""
    p = state.player
    holders = own_extras(state, content, world, tactics.holders_of(content, [(p.name, PLAYER, p.member.wugong_id, p.member.neigong_id)], world, own_levels(state), own_copies(state, content, world)))
    if not holders:
        return None
    mount = p.mount if mounted and mounts.on(content) else None
    return tactics.side_for(holders, tactics.Ctx(
        foe="", our_agility=float(p.stats.get("agi", BASE_STAT)), night=calendar.is_night(state.world.time, content, state.world),
        mount_tier=mount.tier if mount is not None else 0, good=int(p.stats.get("good", 0)), evil=int(p.stats.get("evil", 0)),
        followers=len(follower_rows(state, content)) if troops else 0, foe_faction=None, team=[PLAYER],
    ))


def odds_word(
    power: float, squad: Squad, rng_seed: int = ESTIMATE_SEED, mods: encounter.Mods | None = None,
    plan: tuple[list[tactics.Holder], tactics.Ctx, Content] | None = None,
    foe: tuple[list[tactics.Holder], tactics.Ctx] | None = None,
) -> str:
    """依固定種子模擬 ESTIMATE_RUNS 場的結果分佈換算勝算文字（大勝/險勝算勝、僵持算平手）。mods 是本人的功效換算
    （trait_mods）：每一場都照它擲。plan 是本命戰法（誰帶著、這一場的條件）：有的話每一場照打起來一樣一回合一回合打
    （回合的亂數另一份固定種子，判定的那一顆照舊，所以沒有戰法時勝算一個字都不變）。"""
    rng = random.Random(rng_seed)
    wins = draws = 0
    for i in range(ESTIMATE_RUNS):
        result = encounter.resolve_encounter(power, squad.difficulty, rng, mods=mods)
        if plan is not None and (plan[0] or foe):
            result = clash_result(result, mods or encounter.Mods(), plan[0], plan[1], plan[2], random.Random(f"{rng_seed}|{i}"),
                                  foe=foe)
        wins += result.tier in WIN_TIERS
        draws += result.tier in DRAW_TIERS
    return _odds_text(wins, draws, ESTIMATE_RUNS)


ODDS_MEMO_SIZE = 4096  # 勝算記住最近幾個問題：二十個人、每人四十來處地點的對手，再加換過一兩次身子的，還裝得下


class OddsMemo:
    """勝算的記憶（FB-321，joy 2026-10-17「地圖那邊現在開起來很 Lag」：打開輿圖時疊層在行動鎖裡把每個地點的勝算重算一遍，
    一次 110～140 ms，人多時排鎖）。鍵是 odds_key：模擬（odds_word）的全部輸入，一樣才拿記住的那一個字。odds_word 是固定種子的
    純函式，輸入一樣答案一定一樣，所以沒有期限：氣血、隊伍、裝備、功效、戰法、日夜一變，鍵就跟著變、重新模擬；兩個人輸入一模一樣時
    拿到的也是自己那一份算出來會得到的字。只記最近 size 個（最久沒問的先丟）。伺服器上的 Game 共用一份（server.ODDS_MEMO），
    直接建的 Game（測試、腳本、假人程式）沒有記憶、照舊每次算。執行緒池裡同時問也安全（自己一把鎖；模擬在鎖外跑）。"""

    def __init__(self, size: int = ODDS_MEMO_SIZE) -> None:
        self.size = size
        self._words: OrderedDict[bytes, str] = OrderedDict()
        self._lock = threading.Lock()

    def get(self, key: bytes, compute: Callable[[], str]) -> str:
        with self._lock:
            word = self._words.get(key)
            if word is not None:
                self._words.move_to_end(key)
                return word
        word = compute()
        with self._lock:
            self._words[key] = word
            self._words.move_to_end(key)
            while len(self._words) > self.size:
                self._words.popitem(last=False)
        return word


def odds_key(
    power: float, squad: Squad, mods: encounter.Mods | None, plan: tuple[list[tactics.Holder], tactics.Ctx, Content] | None,
    foe: tuple[list[tactics.Holder], tactics.Ctx] | None, rng_seed: int = ESTIMATE_SEED,
) -> bytes:
    """odds_word 的全部輸入寫成一把鍵（OddsMemo）：模擬幾場、種子、威力（原樣的浮點數）、對手強度與屬性、功效換算、你這一方誰帶著
    哪一門戰法與這一場的條件、戰法的設定（Config.tactics，plan 裡的內容只讀這一份）、對手那一方的戰法與條件。"""
    parts = [ESTIMATE_RUNS, rng_seed, repr(float(power)), repr(float(squad.difficulty)), squad.attribute,
             mods.model_dump_json() if mods is not None else None]
    if plan is not None:
        holders, ctx, content = plan
        parts += [[h.model_dump_json() for h in holders], ctx.model_dump_json(), content.config.tactics.model_dump_json()]
    if foe is not None:
        parts += [[h.model_dump_json() for h in foe[0]], foe[1].model_dump_json()]
    return hashlib.blake2b(json.dumps(parts, ensure_ascii=False).encode("utf-8"), digest_size=20).digest()


def _odds_text(wins: int, draws: int, runs: int) -> str:
    if wins * 100 < 35 * runs and draws * 100 >= 50 * runs:
        return "難分勝負"
    for pct, word in ODDS:
        if wins * 100 >= pct * runs:
            return word
    return "必敗"


def estimate(
    state: GameState, content: Content, world: WorldStateStore, squad_id: str, *, difficulty: float | None = None,
    draw_floor: float | None = None, memo: OddsMemo | None = None, at: str | None = None,
) -> str:
    """勝算的文字；difficulty、draw_floor 同 fight。含會改到贏的機會的功效（破甲、先手、穩、險、借力、連環、厚），不含護命與閃避：
    勝算是贏的機會，那兩個只把落敗變成僵持（人物資質設計 14.4、武學與成長設計 13.4）。memo：模擬的輸入一樣就拿記住的字（OddsMemo，
    FB-321）；輸入（威力、功效、戰法與條件）照舊每次算，只有四十場的模擬省下來。at：照哪一處的地利（輿圖替別處算，power_vs）。"""
    squad = content.squads[squad_id]
    if difficulty is not None:
        squad = squad.model_copy(update={"difficulty": difficulty})
    ctx = tactic_ctx(state, content, world, squad, squad.difficulty)
    plan = (tactic_holders(state, content, world), ctx, content)
    mods = trait_mods(content, traits.loadout(state, content, world))
    if draw_floor is not None:
        mods = mods.model_copy(update={"draw_floor": draw_floor})
    power, foe = power_vs(state, content, world, squad, at=at), foe_tactics(state, content, squad, ctx)
    if memo is None:
        return odds_word(power, squad, mods=mods, plan=plan, foe=foe)
    return memo.get(odds_key(power, squad, mods, plan, foe), lambda: odds_word(power, squad, mods=mods, plan=plan, foe=foe))


def fresh_power(state: GameState, content: Content, world: WorldStateStore) -> float:
    """全隊此刻滿血、不看對手（沒有相剋、路數、地利）的威力：配點那一刻前後各算一次寫給玩家看（減法季屬性五段，Game.allocate_stat）。"""
    arts = team_arts(state, content, world)
    members, conditions, boosts = _fighters(state, content, world)
    return encounter.team_power(members, arts, None, [1.0] * len(conditions), boosts)


def power_vs(
    state: GameState, content: Content, world: WorldStateStore, squad: Squad, fresh: bool = False,
    *, at: str | None = None, terrain: bool = True, seal: bool = True,
) -> float:
    """全隊此刻對上這一路的威力（氣血係數、加成、屬性相剋、一門打不遍、地利都算；勝算與打起來同一份）。
    fresh：氣血係數一律當滿的——江湖水漲（rise.big）照這一份浮難度，帶傷上陣照樣吃虧（不然傷得越重對手跟著越弱）。
    at、terrain 照 _styled_fighters：江湖水漲浮難度傳 terrain=False（不然地利被浮上去的難度吃掉，計畫 2026-10-18 2.1）。
    seal：江湖水漲浮難度傳 False（玉璽碎片的戰力不浮上去，PM 五之一 2），見 player_boost。"""
    arts = team_arts(state, content, world)
    members, conditions, boosts = _styled_fighters(state, content, world, arts, squad, at=at, terrain=terrain, seal=seal)
    if fresh:
        conditions = [1.0] * len(conditions)
    return encounter.team_power(*_with_attribute((members, conditions, boosts), arts, squad.attribute))


def _styled_fighters(
    state: GameState, content: Content, world: WorldStateStore, arts: dict[str, MartialArt], squad: Squad,
    *, at: str | None = None, terrain: bool = True, seal: bool = True,
) -> tuple[list, list[float], list[encounter.Boost]]:
    """_fighters，再把大場面對手的路數（styles，一門打不遍）乘進每個人的加成：照他身上那一門武學的屬性；
    最後是地利（terrain_mod.factor，計畫 2026-10-18）：本人與出戰同伴身上的武學、內功一門一門比這一地最濃的意境，部下不吃。
    at：照哪一處的地利（輿圖替別處算勝算）；不給是玩家此刻腳下（在路上沒有）。terrain=False 不算地利（江湖水漲浮難度）。
    fight 與 estimate 都走這裡，勝算才跟打起來一樣。seal 見 player_boost。"""
    members, conditions, boosts = _fighters(state, content, world, seal=seal)
    style = styles.style_of(state, content, world, squad)
    attributes = [arts[m.wugong_id].attribute if m.wugong_id in arts else None for m in members]
    boosts = styles.styled(boosts, attributes, content, style)
    # 兵器的一門打不遍（兵器設計 3.3）：只有本人有兵器，本人一定是陣容的第一個（team_participants）
    worn = weapons.style_factor(state.player.weapon, player_art(state, content, world, state.player.member.wugong_id),
                                content, world, style)
    if worn != 1.0:
        boosts = [boosts[0].model_copy(update={"factor": boosts[0].factor * worn}), *boosts[1:]]
    strong = None if not terrain else terrain_mod.here(state, content) if at is None else terrain_mod.strong_at(content, at)
    if strong is not None:
        people = 1 + len(state.player.team)  # 本人與出戰同伴在前（team_participants），部下接在後面、不吃
        boosts = [_on_terrain(b, m, arts, content, strong) if i < people else b
                  for i, (m, b) in enumerate(zip(members, boosts, strict=True))]
    return members, conditions, boosts


def _on_terrain(
    boost: encounter.Boost, member: encounter.HasMartialArts, arts: dict[str, MartialArt], content: Content, strong: InsightDef,
) -> encounter.Boost:
    """一個人的地利：武學那一門的倍數進 outer_scale、內功那一門進 inner_scale；兩門都不相干照原樣。"""
    def attribute(skill_id: str | None) -> str | None:
        return arts[skill_id].attribute if skill_id in arts else None

    outer = terrain_mod.factor(attribute(member.wugong_id), content, strong)
    inner = terrain_mod.factor(attribute(member.neigong_id), content, strong)
    if outer == 1.0 and inner == 1.0:
        return boost
    return boost.model_copy(update={"outer_scale": boost.outer_scale * outer, "inner_scale": boost.inner_scale * inner})


def terrain_attributes(
    state: GameState, content: Content, world: WorldStateStore,
) -> tuple[list[str | None], list[tuple[str, list[str | None]]]]:
    """戰報地利那一句要的屬性（terrain_mod.note）：本人身上兩門（照自己那一份）、出戰同伴每一位（名字, 兩門）。"""
    p = state.player
    mine = [art.attribute if (art := player_art(state, content, world, sid)) else None
            for sid in (p.member.wugong_id, p.member.neigong_id)]
    companions = world.companions()
    mates = []
    for key in p.team:
        progress = companions.get(key, CompanionProgress())
        mates.append((content.characters[key].name, [
            art.attribute if (art := resolve_art(sid, content, world)) else None for sid in (progress.wugong_id, progress.neigong_id)
        ]))
    return mine, mates


def worn_attribute(state: GameState, content: Content, world: WorldStateStore) -> str | None:
    """本人身上那一門武學的屬性（戰報的路數那一句、決戰的隊伍多樣性看它）；沒有武學是 None。"""
    art = player_art(state, content, world, state.player.member.wugong_id)
    return (art.attribute or None) if art is not None else None  # 兼容並蓄的沒有屬性：None（Squad 的屬性是 Literal，空字串進不去）


def _with_attribute(
    fighters: tuple[list, list[float], list[encounter.Boost]], arts: dict[str, MartialArt], attribute: str | None,
) -> tuple:
    """encounter.team_power 的參數順序：陣容、武學、對手屬性、氣血係數、加成。"""
    members, conditions, boosts = fighters
    return members, arts, attribute, conditions, boosts
