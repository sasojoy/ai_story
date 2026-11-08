"""假人的配點、傳功、修練、改練、熔煉、學藝與定名的 A 段（第二輪第 101 批：CULTIVATE_RESERVE、TRAIT_WEIGHT、growth_key、allocate_points、TEACH_RESERVE、TEACH_MAX、teach、worn_first、awaits_chance、break_way、takes_the_pill、melt_the_weakest、_worth、slot_insights、switch_to_the_strongest 從 bot 搬來，
LEARN_ROOM、LEARN_SILVER_RESERVE、_learn_here、_too_dear、_master 從 bot_policy 搬來；舊名 re-export 同一批物件）。
沒有掛鉤：bot.forge_and_cultivate、bot.spend_xinde、bot_policy.tend_arts、bot_policy.look_after 經舊名叫，先後留在殼（它們同時排煉製、修練、鐵匠鋪三包的事，包不准 import 包）。bot.pick 讀舊名 awaits_chance，測試換 bot 的那一份打得到。
jianfa 照舊 from tianxia.rules import（same_behavior 的 whetstone 軌換這個名字）。取名的單子（MasterJob、NamingSlot）四包開單，在共用層 bot_base，一律寫 `bot_base.X`。**模組層不准碰 engine 與假人殼**（bot、bot_policy 模組層 import 這個檔）。
"""
from __future__ import annotations

import hashlib
import random
from typing import TYPE_CHECKING

from tianxia import arts as arts_mod, attrset, bot_base, growth, library, team, traits
from tianxia.rules import jianfa

from . import chuangong, cultivation

if TYPE_CHECKING:
    from tianxia.engine import Game
    from tianxia.martial_arts import MartialArt
    from tianxia.models import Content, SkillDef

CULTIVATE_RESERVE = 60  # 體力留這麼多給探索與遊歷，多出來的才拿去修練
TRAIT_WEIGHT = 0.05  # 機器人選身上那門時，每一層功效（乘過品質）、每個特別功效算多少比例的威力（武學與成長設計 13.7）
LEARN_ROOM = 3  # 學藝之後，功法庫至少還留幾格給合成
LEARN_SILVER_RESERVE = 30  # 付完學費至少留幾兩（療傷用）


def growth_key(game: Game) -> str:
    """假人這一季挑哪一套成長配比：照名號挑五套預設之一（不擲骰；allocate_points 與開季準備卡的 growth: 鈕同一個）。"""
    presets = game.content.config.attributes.v2.presets
    return presets[int(hashlib.md5(game.state.player.name.encode("utf-8")).hexdigest(), 16) % len(presets)].key


def allocate_points(game: Game, rng: random.Random) -> None:
    """升級得到的屬性點隨機分掉（還沒到頂的那幾項裡挑）。走 Game.allocate_stat——真人按按鈕的同一條路。
    迴圈有界：它在全服寫入鎖裡跑，空轉會凍住伺服器。最多試「手上有幾點」次；全到頂、或 allocate_stat
    拒絕了（賽季籌備中等，點數沒少）就停，剩下的點留著。"""
    p, cap = game.state.player, game.content.config.stat_cap
    if attrset.on(game.content, game.state.world):
        # 五項屬性的季（屬性與跨季架構 v2 3.1）：照名號挑一套配比（不擲骰，跟真人一樣按「成長」那一排），送的點全配在那一套最重的那一項
        if p.growth_preset is None:
            game.pick_growth(growth_key(game))
        split = attrset.split(game.state, game.content)
        top = max(attrset.keys(game.content), key=lambda k: split.get(k, 0))
        for _ in range(p.stat_points):
            before = p.stat_points
            game.allocate_stat(top)
            if p.stat_points >= before:
                return
        return
    if jianfa(game.content, game.state.world, "stat_milestones"):
        # 減法季屬性五段（設計 4.5「配滿一項是一條路」）：照名號挑一條路（growth.stat_path：力、巧、韌、悟、博排個先後），第一項配滿再第二項；
        # 不擲骰。整季機器人與伺服器假人同一個（bot_policy.look_after 叫這裡）
        for stat in growth.plan_points(p.stats, p.stat_points, cap, growth.stat_path(p.name)):
            before = p.stat_points
            game.allocate_stat(stat)
            if p.stat_points >= before:  # 被拒絕：再試也一樣
                return
        return
    for _ in range(p.stat_points):
        open_stats = [k for k in team.COMBAT_STATS if p.stats.get(k, 0) < cap]
        if not open_stats:
            return
        before = p.stat_points
        game.allocate_stat(rng.choice(open_stats))
        if p.stat_points >= before:  # 被拒絕：再試也一樣
            return


TEACH_RESERVE = 30  # 傳功之後至少留幾點心得：合成一爐 5、練成下一成 2×N，留著不至於為了傳功把自己的路堵死
TEACH_MAX = 20  # 一次最多傳幾下（價錢越後越貴，通常幾下就停；這只是保險）


def teach(game: Game, limit: int = TEACH_MAX) -> int:
    """傳功門下（整季機器人與假人共用）：名冊上最便宜、按得下去的那一項（chuangong.cheapest），付完還剩 TEACH_RESERVE 才傳；
    一直傳到付不起或 limit 下為止。只走 Game.chuangong，不擲亂數。回傳傳了幾下。"""
    done = 0
    while done < limit:
        lesson = chuangong.cheapest(game.state, game.content, game.world)
        if lesson is None or game.state.player.stats.get("xinde", 0) - lesson.price < TEACH_RESERVE:
            break
        game.chuangong(lesson.key, lesson.what)
        done += 1
    return done


def worn_first(game: Game) -> list[str]:
    """修練挑哪一門：身上的兩門先（武學、內功），再照功法庫的順序。成數門檻（方案 A）與火候（方案 C）都綁在練成上，
    身上那兩門才練得上去；契機也只看身上那兩門。整季機器人與伺服器假人共用。"""
    member, owned = game.state.player.member, library.owned_arts(game.state)
    worn = [a for a in (member.wugong_id, member.neigong_id) if a in owned]
    return worn + [a for a in owned if a not in worn]


def awaits_chance(game: Game) -> bool:
    """身上有一門上品到了極處（cultivation.ready：第十成）、等著契機：機器人這時有挑戰本人可打就去打（見 pick）。"""
    state, content, world = game.state, game.content, game.world
    member = state.player.member
    if content.config.breakthrough.chance <= 0 or state.player.naming is not None:
        return False
    return any(
        art_id and cultivation.ready(state, content, world, art_id)[0] for art_id in (member.wugong_id, member.neigong_id)
    )


def break_way(game: Game, art_id: str) -> dict:
    """這一門到了極處要怎麼強行衝關（cultivate 的關鍵字）：手上有丹就服（use_legend）；沒丹是空的，等契機
    （Joy 2026-10-21 拿掉心得衝關；萬寶閣的破境丹假人不買）。整季機器人與假人共用。"""
    return {"use_legend": True} if takes_the_pill(game, art_id) else {}


def takes_the_pill(game: Game, art_id: str) -> bool:
    """這一門到了極處、手上又有破境丹：服（企劃者：丹由玩家自己決定哪一次服，機器人有就服）。
    只在這一步傳 use_legend：別的門用不上丹。"""
    state, content, world = game.state, game.content, game.world
    return state.player.legend_items > 0 and cultivation.ready(state, content, world, art_id)[0]


def melt_the_weakest(game: Game) -> None:
    """滿了：熔掉功法庫裡第十成威力最低的一門；庫是空的就化掉一個沒有武學靠它修練的意境。"""
    state, content, world = game.state, game.content, game.world
    spare = [(team.player_art(state, content, world, a), a) for a in state.player.arts]
    spare = [  # 熔不得的（本命武學）不挑
        (art.top_power, a) for art, a in spare
        if art is not None and library.melt_problem(state, a, art.name, content=content) is None
    ]
    if spare:
        game.melt_art(min(spare)[1])
        return
    loose = [i for i in state.player.insights if arts_mod.where_slotted(state, i) is None]  # 裝在武學上的不熔
    if loose:
        game.melt_insight(loose[0])


def _worth(content: Content, art: MartialArt) -> float:
    """機器人眼中這門武學的價值：第十成威力，加上功效（設計 13.7：不看功效就量不出功效的價值）。每一層一般功效（乘過這一份的
    品質倍數，跟遊戲裡算層數同一份 traits.multiplier）、每個特別功效，各加 TRAIT_WEIGHT 的威力。內容沒有功效就只看威力。"""
    if not content.traits.general:
        return art.top_power
    layers = len(traits.traits_of(art)) * traits.multiplier(content, art.quality) + (1 if art.special else 0)
    return art.top_power * (1 + TRAIT_WEIGHT * layers)


def slot_insights(game: Game) -> int:
    """把手上沒裝在任何一門上的意境裝進身上兩門的空槽（武學先、內功後；收得下的才裝）。整季機器人與假人共用；
    只走 Game.slot_insight、不擲亂數。回傳裝了幾個。"""
    state, content, world = game.state, game.content, game.world
    member = state.player.member
    done = 0
    for art_id in (member.wugong_id, member.neigong_id):
        if not art_id:
            continue
        for insight_id in list(state.player.insights):
            if arts_mod.where_slotted(state, insight_id) is not None:
                continue
            if arts_mod.slot_problem(state, content, world, art_id, insight_id) is None:
                game.slot_insight(art_id, insight_id)
                done += 1
    return done


def switch_to_the_strongest(game: Game) -> None:
    """功法庫裡有比身上這門值錢的（同一種、照自己修練到的品質算第十成威力，再加上功效，設計 13.7）就改練上去。"""
    state, content, world = game.state, game.content, game.world
    for art_id in list(state.player.arts):
        art = team.player_art(state, content, world, art_id)
        if art is None:
            continue
        slot = "neigong_id" if art.kind == "內功" else "wugong_id"
        current = team.player_art(state, content, world, getattr(state.player.member, slot))
        if current is None or _worth(content, art) > _worth(content, current):
            game.switch_art(art_id)


def _learn_here(game: Game) -> list[str]:
    """學藝（武學與成長設計附錄 B）：這裡教、學得了、自己同一種（內功／武學）還沒有這個屬性的，學一門。
    付完學費要留 LEARN_SILVER_RESERVE 兩（免費的不看），庫裡至少留 LEARN_ROOM 格給合成。走選單上的「學〇〇」。
    多數地方沒有人教：先看有沒有學得了的，有才建選單。"""
    state, content, world = game.state, game.content, game.world
    if library.cap_of(state, content) - library.held_count(state) < LEARN_ROOM:
        return []
    lessons = [skill for skill, problem in library.lessons_here(state, content) if problem is None]
    if not lessons:
        return []
    have = {
        (art.kind, art.attribute)
        for art in (team.player_art(state, content, world, a) for a in library.owned_arts(state)) if art is not None
    }
    silver = state.player.stats.get("silver", 0)
    wanted = [
        skill for skill in lessons
        if (skill.kind, skill.attribute) not in have and not _too_dear(skill, silver)
    ]
    if not wanted:
        return []
    enabled = {o.id for o in game.options(odds=False, tick=False) if o.enabled}
    for skill in wanted:
        if f"learn:{skill.id}" in enabled:
            return game.choose(f"learn:{skill.id}")
    return []


def _too_dear(skill: SkillDef, silver: int) -> bool:
    """學費付完剩不到 LEARN_SILVER_RESERVE 兩（免費的不看）。"""
    fee = skill.learn.silver if skill.learn is not None else 0
    return bool(fee) and silver - fee < LEARN_SILVER_RESERVE


def _master(game: Game, slot: bot_base.NamingSlot | None) -> None:
    """絕學定名的 A 段：輪得到就開單交給假人程式；輪不到先不定（不沿用原名：江湖史那一行同一個名字出現兩次，
    真人那一步是自己填的，看得出是假人；企劃者 2026-10-06）。"""
    request = game.mastery_request()
    if request is None:
        return
    if slot is not None and slot.open and slot.job is None:
        slot.job = bot_base.MasterJob(game.state.player.naming, request)
    elif slot is not None:
        slot.skipped += 1
