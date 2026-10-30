"""亂數機器人：玩完一整季，用於整季測試與平衡模擬。

sanguo-companions 合併大幅重寫：拿掉抽卡、收徒、多隊派遣——招募到新同伴後不用機器人
額外處理，roster.attempt_recruit/recruit 已經自動把人加進隊伍（見 roster.py）。大多數
時候隨機選一個可用的選項（含深度對話的 talk:N，模型叫不動時那輪對話會直接結束，不需要真的連
Ollama）；只有「結識」一定接受；心得攢夠一定步數就拿去練成、合成，體力有餘就修練（見 spend_xinde、forge_and_cultivate）。
"""
from __future__ import annotations

import hashlib
import random
from collections.abc import Callable
from typing import NamedTuple

from . import arts as arts_mod, allied, armor, bounties, checkin, chuangong, clinic, create, cultivation, economy, equipment, explore_modes, forge_secrets, four_tiers, fusion, glyph, insights, library, mounts, naming, sensing, smithing, team, traits, treasures, weapons
from . import prologue as prologue_rules
from . import sortie_duel, tactics  # 出陣約戰（減法季批 3b）：封三招
from . import growth  # 減法季屬性五段：假人照路配點（stat_path、plan_points）
from . import outing  # 走一趟：假人挑段數（outing_segments）
from .engine import ARENA_YIELD, DUEL_FLEE, FREE_TEXT_OPTION, TEXT_TALKS, Game, Option
from .rules import jianfa
from .core import features as features_core
from .martial_arts import MartialArt, next_quality
from .models import MOVES, Content
from .models import Outcome  # 減法季批 4：pick_outcome 的位子
from .state import PLAYER
from .sqlite_world import open_world
from .world_state import WorldStateStore

HALF_HOUR = 1800
CHALLENGE_ODDS = ("穩勝", "有把握")  # 挑戰本人只挑這兩種勝算（整季機器人與伺服器假人共用；bot_policy 從這裡拿，挑戰每季都有設計第九節）
SPEND_XINDE_EVERY = 5  # 每幾步檢查一次要不要拿心得去練功/療傷
FORESHADOW_OPTIONS = ("fs:", "talk:clue:", "opp:", "talk:opp:")  # 伏筆的最後一步、對話的片段與機緣（正式版乙一）：機器人不做

FORGE_TRIES = 4  # 意境＋意境試幾組（被擋下就換一組）
SENSE_RIGHT = 0.6  # 有所感時挑到選得對的做法的機會（其餘從全部做法裡隨便挑，可能也挑對）：看得懂場景的玩家大多挑得對
SENSE_DRAW = 0.8  # 進了感悟狀態之後真的畫一筆（其餘順其自然，落回做法那個基本意境）
MERGE_SHARE = 0.3  # 手上有兩個以上意境時，這麼多的機會開一爐（煉製只剩意境＋意境）
FORGE_RESERVE = 20  # 三種合成都花體力（武學與成長設計 12.1）：體力留這麼多給探索與遊歷，多出來的才拿去合成
CULTIVATE_RESERVE = 60  # 體力留這麼多給探索與遊歷，多出來的才拿去修練
MOUNT_SILVER_RESERVE = 30  # 買了馬至少還留幾兩（療傷用；同 bot_policy.LEARN_SILVER_RESERVE）：設計第九節「100＋保留額度」
# 素材與經濟（計畫 B5）：整季機器人與假人賣、升、捐都留這麼多（修兵器、餵馬、糧草吃一階；二階留著升三階），三階一個都不賣不捐
TRADE_KEEP = {1: 12, 2: 10, 3: 5}  # 三階只在素材四階開著時算（trade_keep）：留夠一次三換四
TIER3_WANT = 2  # 素材四階關著（舊規則）：那個屬性的三階少於這麼多才升三階（一把神器要兩個三階）
TIER4_WANT = 2  # 素材四階：那個屬性的四階少於這麼多才三換四（一件神器要主輔兩個四階，正式季整合 8.1）
TRADE_SILVER_RESERVE = 30  # 升階付完工錢至少還留幾兩（療傷用，同 MOUNT_SILVER_RESERVE）
TRADE_MOVES = 24  # 一次在鐵匠鋪最多升、賣幾下（保險：每一下都會讓背包離留的量更近，本來就停得下來）
TRAIT_WEIGHT = 0.05  # 機器人選身上那門時，每一層功效（乘過品質）、每個特別功效算多少比例的威力（武學與成長設計 13.7）


CLINIC_AT = 0.15  # 內傷到氣血上限的這麼多（約兩三場落敗）就繞去醫館（企劃者 2026-10-12 療傷只在醫館）；整季機器人與假人共用
CLINIC_MIN_SILVER = 20  # 付不起全治時（team.heal_plan 治一部分）手上至少這麼多才去、才療：不然每賺一兩就進醫館花掉
CLINIC_URGENT = 0.25  # 到這麼多就先去醫館、排在軍令前面（PM 2026-10-12：假人被軍令拉走、帶著三四成內傷打一整季）；整季機器人在 CLINIC_AT 就一律先去


def wants_heal(game: Game) -> bool:
    """人在醫館、有內傷、付得起（can_pay_clinic）才療傷：療傷照內傷計價（見 team.heal_cost），付不起全治時治一部分。
    氣血低但沒有內傷時會自己回；不在醫館按了只會寫「這裡沒有醫館」。"""
    return can_pay_clinic(game) and clinic.here(game.state, game.content)


def can_pay_clinic(game: Game) -> bool:
    """有內傷，而且付得起全治、或手上至少 CLINIC_MIN_SILVER 兩（治一部分，team.heal_plan）。"""
    cost = team.heal_cost(game.content, game.state.player.member, game.state)
    return cost > 0 and game.state.player.stats.get("silver", 0) >= min(cost, CLINIC_MIN_SILVER)


def injury_share(game: Game) -> float:
    """本人的內傷佔氣血上限的幾成（醫館的兩道門檻 CLINIC_AT、CLINIC_URGENT 都跟它比）。"""
    s, c = game.state, game.content
    _, cap = team.member_neili(c, s.player.member, team.con_of(s, c, game.world, PLAYER), season=s.world)
    return s.player.member.injury / cap if cap > 0 else 0.0


def clinic_hop(game: Game) -> str | None:
    """內傷到 CLINIC_AT、付得起（can_pay_clinic）、人不在醫館也不在路上：往最近的醫館走的下一站（clinic.nearest）；不必去、走不到是 None。"""
    s, c = game.state, game.content
    if not clinic.on(c) or s.player.journey is not None or clinic.here(s, c):
        return None
    if not can_pay_clinic(game) or injury_share(game) < CLINIC_AT:
        return None
    route = clinic.nearest(s, c)
    return None if route is None else route.path[0]


def can_practise(game: Game, kind: str) -> bool:
    """身上這一門還沒第十成、而且付得起下一成的心得（練成花心得，武學與成長設計 4.2）。"""
    return team.can_practise(game.state, game.content, kind)


PILL_BELOW = 10  # 回體丹（內測贈送）：體力掉到連一次探索、遊歷都不夠時才吃一顆，跟急著玩的真人一樣；夾在上限，不會吃在半滿的時候浪費


def take_pill(game: Game) -> None:
    """體力見底、手上有回體丹就服一顆（只走 Game.take_stamina_pill，跟真人按體力條上的「丹」一樣）。整季機器人與伺服器假人共用。
    pill_only=True：測試期間 Config.beta_free_refill 打開時，真人按同一顆鈕是免費補滿；機器人與假人不吃那個，照舊只吃丹
    （沒有丹就不補），整季模擬與平衡量表不因為測試期間的免費補滿而變。開關關著時 pill_only 沒有作用。"""
    p = game.state.player
    if p.stamina_pills > 0 and p.stamina < PILL_BELOW and game.pills_left_today() != 0:  # 一天的上限照真人（今天服滿了就等明天）
        game.take_stamina_pill(pill_only=True)


def check_in(game: Game) -> None:
    """每日簽到（21 天季，正式季整合 8.1）：今天還沒簽就簽，四階的日子照名號＋季數的種子挑屬性（checkin.bot_attribute）。只走
    Game.check_in（真人按「簽到」小標的同一條路）；畫面沒有簽到（關著、序章裡、休季）或今天簽過了都不叫。整季機器人與伺服器假人共用。"""
    view = game.checkin_view()
    if view is None or view["done"]:
        return
    p = game.state.player
    game.check_in(checkin.bot_attribute(game.content, p.name, p.season_number) if view["pick"] else "")


def allocate_points(game: Game, rng: random.Random) -> None:
    """升級得到的屬性點隨機分掉（還沒到頂的那幾項裡挑）。走 Game.allocate_stat——真人按按鈕的同一條路。
    迴圈有界：它在全服寫入鎖裡跑，空轉會凍住伺服器。最多試「手上有幾點」次；全到頂、或 allocate_stat
    拒絕了（賽季籌備中等，點數沒少）就停，剩下的點留著。"""
    p, cap = game.state.player, game.content.config.stat_cap
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


def spend_xinde(game: Game, rng: random.Random) -> None:
    """有內傷先療傷；接著身上兩門各練一成——付得起才練（練成花心得，開局就有基礎武學，沒有空欄位要自創了）。
    不追求最優策略，只求機器人不會把心得放著不用，也不會一直去撞「心得不足」。"""
    if wants_heal(game):
        game.heal()
    for kind in ("內功", "武學"):
        if can_practise(game, kind):
            game.practice(kind)
    teach(game)


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


class ForgePlan(NamedTuple):
    """挑好的一爐（還沒開）：兩個意境（煉製只剩意境＋意境，Joy 2026-10-21）。"""

    insight_ids: tuple[str, ...]


def pick_forge(game: Game, rng: random.Random, merge_share: float | None = None) -> ForgePlan | None:
    """挑一爐（整季機器人與伺服器假人共用）：體力低於 FORGE_RESERVE、手上不到兩個意境、或什麼都合不了就是 None。
    只挑、不開爐，什麼都不改。merge_share 沒給就在呼叫的當下讀模組常數 MERGE_SHARE（量平衡的腳本改它要有效）。"""
    merge_share = MERGE_SHARE if merge_share is None else merge_share
    state, content, world = game.state, game.content, game.world
    p = state.player
    if len(p.insights) < 2 or p.stamina < FORGE_RESERVE or rng.random() >= merge_share:
        return None
    for _ in range(FORGE_TRIES):
        a = rng.choice(p.insights)  # 意境效果池：同一份放兩次合不了，第二格從其餘的挑（同一種的另一份就是揣摩）
        b = rng.choice([i for i in p.insights if i != a])
        if fusion.merge_problem(state, content, world, a, b) is None:
            return ForgePlan((a, b))
    return None


def forge_and_cultivate(game: Game, rng: random.Random) -> None:
    """機器人的武學：等著定名的先定名；滿了先熔最弱的；體力有餘就開一爐意境（合併或揣摩）；自創；改練更強的；
    意境裝進空槽；體力再有餘就衝絕學一次。機器人會用到這套玩法很重要——不然整季模擬碰不到合成與修練，量出來的平衡沒有意義
    （CLAUDE.md「第三層」的教訓）。MERGE_SHARE 那一擲只在手上有兩個以上意境、體力到 FORGE_RESERVE 時才擲。"""
    state, content, world = game.state, game.content, game.world
    p = state.player
    if p.naming is not None:
        game.name_mastered(naming.fallback_name(content, f"定名|{p.naming}", "武學", salt=rng.randint(0, 99)))
    if library.full(state, content):
        melt_the_weakest(game)
    plan = pick_forge(game, rng)
    if plan is not None:
        game.forge(None, list(plan.insight_ids))
    create_art(game, rng)
    switch_to_the_strongest(game)
    slot_insights(game)  # 武學重構：悟到的意境裝進身上兩門的空槽
    if p.stamina >= CULTIVATE_RESERVE:
        for art_id in worn_first(game):
            way = break_way(game, art_id)
            if way and cultivation.cultivate_problem(state, content, world, art_id, **way) is None:
                game.cultivate(art_id, **way)
                break


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


CREATE_RESERVE = 50  # 自創付完心得要剩這麼多（練成、揣摩還要用）
CREATE_INTENTS = ("風過林梢，影不留痕", "山不動而勢壓人", "一息吐納，百脈皆通", "水無常形，隨勢而走", "烈火燎原，一往無前")


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


def create_art(game: Game, rng: random.Random) -> bool:
    """自創一門（tianxia/create.py 五步一次走完）：心得付完還剩 CREATE_RESERVE 才做。種類挑身上那一門比較弱的那一種；
    兵器照身上武學的種類（推不出來隨機），行功之法隨機；架式從預設的幾個挑一個再稍微動一下；意從 CREATE_INTENTS 挑、
    照關鍵字表讀（假人不叫模型）；名字走退路字表（看得出來是假人：之後要補模型取名）。伺服器假人與整季機器人共用。"""
    state, content, world = game.state, game.content, game.world
    p = state.player
    if p.creating is not None and p.creating.paid and p.creating.step == "name":
        return _name_draft(game)  # 立意時付過心得的單子（上一次取名取不到）：接著取名，不丟掉
    if create.allowed(state, content) is not None or p.stats.get("xinde", 0) - create.price(state, content) < CREATE_RESERVE:
        return False
    if p.creating is not None:
        game.create_cancel()
    worn = [(team.player_art(state, content, world, a), k) for a, k in ((p.member.wugong_id, "武學"), (p.member.neigong_id, "內功"))]
    kind = min(worn, key=lambda x: x[0].top_power if x[0] is not None else 0)[1]
    forms = [f.key for f in create.forms_of(content, kind)]
    if not forms:
        return False
    form = weapons.art_weapon(p.member.wugong_id, content, world) if kind == "武學" else None
    game.create_begin(kind, form if form in forms else rng.choice(forms))
    if p.creating is None:
        return False
    names = [x.name for x in content.create_forms.presets] or [create.DEFAULT_PRESET]
    pose = create.preset(content, rng.choice(names))
    pose = {k: v + rng.uniform(-15, 15) for k, v in pose.items()}
    game.create_pose(pose)
    game.create_intent(rng.choice(CREATE_INTENTS))
    if p.creating is None or p.creating.step != "name":
        game.create_cancel()
        return False
    return _name_draft(game)


def _name_draft(game: Game) -> bool:
    """替成了形的單子取名（退路字表）。都撞名就留著單子（心得立意時付過了），下一次接著取：第一次用原本那一批，
    之後照這一刻的時辰換一批（不然每次都撞同幾個名字）。"""
    p = game.state.player
    draft = p.creating
    seed = f"自創|{p.name}|{p.created_count}" + (f"|{int((game.now or 0) // 3600)}" if draft.name_tries else "")
    draft.name_tries += 1
    for salt in range(naming.CLAIM_ATTEMPTS):
        name = naming.fallback_name(game.content, seed, draft.kind, salt=salt)
        game.create_name(name)
        if p.creating is None:
            return True
    return False


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


def sense_pick(game: Game, rng: random.Random) -> str | None:
    """有所感的時候挑什麼（整季機器人與伺服器假人共用，悟意境設計 0.4）：還沒選做法就挑一個（SENSE_RIGHT 的機會挑選得對的），
    進了感悟狀態就畫（sensing.DRAW，呼叫端要接著 sense_draw）或順其自然。不在有所感是 None。"""
    got = sensing.current(game.state, game.content)
    if got is None:
        return None
    s, scene, loc = got
    if s.stage == "draw":
        return sensing.DRAW if rng.random() < SENSE_DRAW else sensing.LET_GO
    pool = insights.pool_attributes(loc, game.content)
    right = [i for i, j in enumerate(s.order) if scene.prologue or scene.methods[j].attribute in pool]
    if right and rng.random() < SENSE_RIGHT:
        return f"{sensing.PREFIX}{rng.choice(right)}"
    return f"{sensing.PREFIX}{rng.randrange(len(s.order))}"


def sense_stroke(game: Game, rng: random.Random, same: bool = False) -> list[list[float]]:
    """機器人不會畫：照它想要的屬性挑一筆現成的（glyph.SAMPLES）。same＝畫跟做法一樣的屬性（一定落回基本意境、不用取名）。"""
    s = game.state.player.sensing
    attribute = s.method if same and s is not None and s.method in glyph.SAMPLES else rng.choice(sorted(glyph.SAMPLES))
    return glyph.SAMPLES[attribute]


def sense_draw(game: Game, rng: random.Random) -> list[str]:
    """整季機器人畫一筆：A 段開單、C 段直接交回（沒給名字：Game.sense_draw 在鎖內用短逾時問一次，取不到走退路字表）。"""
    req = game.sense_request(sense_stroke(game, rng))
    if isinstance(req, str):
        return game.choose(sensing.LET_GO)
    return game.sense_draw(req)


def enlist_pick(game: Game, option_ids: list[str]) -> str | None:
    """投靠了陣營、卻不是交戰兩軍的機器人（地方豪強）怎麼臨時投效（Joy 2026-10-13「豪強在大決戰還是要加入某一陣營」）：
    投人少的那一軍，一樣多照名號＋這一場的雜湊挑（不碰亂數）。散人不走這裡（散人的假人不投效）；選單上沒有投效鈕是 None。"""
    battle = game.battle_now()  # 有攻城戰時是自己看的那一場（領地爭奪第二批）
    sides = [i for i in option_ids if i.startswith("battle:enlist:")]
    if battle is None or not sides or game.state.player.faction is None:
        return None
    counts = {  # 鈕 id 可能帶「@流水號」（同一個大區兩場以上，領地爭奪第二批）
        i: sum(1 for p in battle.participants.values() if p.faction == i.removeprefix("battle:enlist:").partition("@")[0]) for i in sides
    }

    def tie(option_id: str) -> str:
        return hashlib.sha256(f"{game.state.player.name}|{battle.battle_id}|{option_id}".encode()).hexdigest()

    return min(sides, key=lambda i: (counts[i], tie(i)))


def explore_choice(ids, want: str = "material") -> str | None:
    """要探索時按哪一顆：三選一開著是找素材（explore:gather），關著是 act:explore；都不在選單上是 None。量表與腳本共用。
    want="exp"（要經驗）：一類一顆開著、選單上有練功（explore:practice）就按它，沒有退回上面那樣（正式季整合 9.2）。
    打探懸賞照預設（練功不算打探）。
    找素材分支（第 32 項）：選單上有分支（explore:gather:<id>）時「找素材」只是入口，回第一條分支（不回「自己說」）；
    ids 是有順序的（list、tuple）照選單的順序，set 照字排，結果才固定。"""
    practice = explore_modes.option_id(explore_modes.PRACTICE)
    if want == "exp" and practice in ids:
        return practice
    gather = explore_modes.option_id(explore_modes.GATHER)
    order = list(ids) if isinstance(ids, (list, tuple)) else sorted(ids)
    branch = next((i for i in order if i.startswith(f"{gather}:") and i != explore_modes.SAY_ID), None)
    if branch is not None:
        return branch
    return gather if gather in ids else "act:explore" if "act:explore" in ids else None


def duel_moves(rng: random.Random) -> list[str]:
    """約戰封的三招（減法季批 3b；設計 5.7「假人可以應約戰、封招」，計畫 Task 3b-3）：對面封的招看不到，每一回合先猜一招，出剋它的那一招
    （tactics.best_against），其中隨機一回合換成隨便一招；不撤退（撤退是真人看形勢用的）。整季機器人與伺服器假人共用。"""
    random_round = rng.randrange(3)
    moves = []
    for i in range(3):
        guess = rng.choice(MOVES)
        moves.append(rng.choice(MOVES) if i == random_round else tactics.best_against([guess], list(MOVES)))
    return moves


def duel_go(game: Game, option_id: str, rng: random.Random) -> str:
    """出陣那一格（act:train）在約戰開著、不是截糧時只是打開出陣前那張卡（按了什麼都不做）：換成 sortie:go:<三招>，真的貼一張。其餘照原樣。"""
    if option_id == "act:train" and game.duel_on() and not game.duel_convoy_here():
        return f"{sortie_duel.PREFIX}go:{','.join(duel_moves(rng))}"
    return option_id


def pick_outcome(game: Game, outcomes: list[Outcome], rng: random.Random) -> str | None:
    """假人挑隨口應對分岔的後果（減法季整合設計 5.1、5.7「假人可以挑後果、挑心意、應約戰、封招，不可以寫字」）：**這一版不做**
    （企劃者 2026-10-24 第 5 件：歸類要句子，假人不寫字），一律回 None——pick 照舊把隨口應對（choice:free）排除，伺服器假人
    （bot_policy.take_turn）也照舊不按。留著位子：之後要做就照個性挑一種的 id，直接交給 Game.answer_event 的 outcome
    （不經模型、不寫字；江湖紀錄與行狀照真人一樣只寫類名，看不出是假人）。"""
    return None


OUTING_WEIGHTS = {1: 1, 3: 3, 5: 2}  # 假人走一趟挑幾段的比重（只在體力夠的段數裡挑）【預設】


def outing_segments(game: Game, rng: random.Random) -> int:
    """假人走一趟挑幾段（tianxia/outing.py）：體力夠走的段數照 OUTING_WEIGHTS 挑一種；一段都走不起是 0。"""
    c, p = game.content, game.state.player
    ok = [n for n in outing.segments(c) if p.stamina >= outing.cost(c, n)]
    if not ok:
        return 0
    return rng.choices(ok, weights=[OUTING_WEIGHTS.get(n, 1) for n in ok])[0]


OUTING_SAY_CHANCE = 0.15  # 假人走完一趟留一句預設句的機會（不寫自己的話，同名帖自題從句庫挑）【預設】


def outing_say(game: Game, rng: random.Random) -> list[str]:
    """假人走完一趟（剛收、還能留言）有 OUTING_SAY_CHANCE 的機會留一句預設句（Game.outing_say，免費）；其餘什麼都不做。"""
    if outing.say_ok(game.state) is None or rng.random() >= OUTING_SAY_CHANCE:
        return []
    return game.outing_say(rng.randrange(len(outing.PRESETS)))


def pick(game: Game, options: list[Option], rng: random.Random) -> str | None:
    """結識（choice 的 effect.recruit）一定接受；其餘隨機挑一個。沒得挑時回傳 None。

    故意排除 act:rest：以前是打坐（真人玩家體力見底時的保底，2026-10-12 拿掉），現在只剩序章那一下調息；
    留著這條排除是同一個道理——永遠按得下去的選項，機器人要是跟其他選項一樣隨機挑，
    「沒有其他選項可選」這個訊號就永遠不會成立，下面 play_season() 用這個訊號決定要不要
    呼叫 game.advance() 推進遊戲時間的節奏會被打亂（體力耗盡的頻率大幅降低，時間推進
    跟著變少，一整季要跑完所需的步數暴增到頂到 max_steps 才停，拖垮整個測試套件）。
    act:halt（喊停）同理：機器人只走單站、它不會出現，萬一出現了也不能讓它成為「有選項可選」。
    路上的選項（road: 開頭：折返、路上小事）也一樣排除：機器人不改道、不折返、不做路上小事（路上設計第六節），
    而折返在路上永遠按得下去，不排除的話「在路上沒事可做就推進時間」這個訊號會失效。
    名望不夠的求見（call:<人物>）同理：求見一直都在、按下去只是被打發（武學與成長設計 9.1），機器人不白按。"""
    s = game.state
    side = allied.pick_side(s.player.name, [o.id for o in options if o.enabled], game.world.roll_counts())
    if side is not None:  # 豪強分屬兩軍：投靠豪強、拜入曹氏莊院之後挑依附哪一軍，挑人少的那一邊（設計第十三節）
        return side
    if s.player.sensing is not None and any(o.id.startswith(sensing.PREFIX) for o in options):
        return sense_pick(game, rng)  # 有所感的卡擋著：先了結它（畫的那一步回 sensing.DRAW，play_season 接著 sense_draw）
    battle = game.battle_now()  # 有攻城戰時是自己看的那一場（領地爭奪第二批）
    if battle is not None and s.player.name not in battle.participants:
        for option in options:  # 集結時選單照常有別的事可做（FB-009）；還沒參戰就先加入，跟以前選單只剩加入時一樣
            if option.id.startswith("battle:join"):
                return option.id
        enlist = enlist_pick(game, [o.id for o in options])
        if enlist is not None:
            return enlist
    options = [o for o in options if o.id != FREE_TEXT_OPTION and o.id not in TEXT_TALKS]  # 隨口應對、對話的「自己說」要寫一句話，機器人寫不出有意義的做法（同決戰的 free_text）
    # 伏筆的最後一步與對話的片段選項、機緣的選項與話題：這一版假人不做伏筆（計畫 T7）也不做機緣，同隨口應對一樣排除
    options = [o for o in options if not o.id.startswith(FORESHADOW_OPTIONS)]
    if any(o.id.startswith(explore_modes.PREFIX) for o in options):
        # 探索三選一開著：「探索」只是展開三顆的入口，按了什麼都不做、不花體力（同 act:rest 的道理：永遠按得下去的空按會讓
        # 「沒得按就推進時間」的訊號失效）
        options = [o for o in options if o.id != "act:explore"]
    gather = explore_modes.option_id(explore_modes.GATHER)
    if any(o.id.startswith(f"{gather}:") for o in options):
        # 找素材分支（第 32 項）：「找素材」那時只是展開分支的入口（同 act:explore，按了不做事）；「自己說」要寫一句話（同隨口應對）。
        # 分支只留一條（照 explore_seq 輪，不擲骰）：隨機挑時找素材的份量跟沒有分支層時一樣是一顆，不因為多了幾條路多去找素材
        branches = [o.id for o in options if o.id.startswith(f"{gather}:") and o.id != explore_modes.SAY_ID]
        keep = branches[s.player.explore_seq % len(branches)] if branches else None
        options = [o for o in options if o.id not in (gather, explore_modes.SAY_ID) and (not o.id.startswith(f"{gather}:") or o.id == keep)]
    if s.pending_event:
        choices = game.content.events[s.pending_event].choices
        for option in options:
            if option.id.startswith("choice:") and choices[int(option.id.partition(":")[2])].effect.recruit:
                return option.id
    # 叛投（defect:）：機器人不換陣營；選單上一直有，不排除的話「沒事可做就推進時間」的訊號會失效（同 act:rest）
    # 邀請（invite:）：整季機器人不跟別人切磋，收回自己的邀請也一直按得下去，同 act:rest
    # 懸賞榜（act:bounties）在城裡一直按得下去（只是打開第二層選單）：同 act:rest 排除；揭懸賞走 take_bounties
    # 鐵匠鋪（act:smith）同懸賞榜：只是打開選單；買修換走 visit_smith。鐵匠鋪的切頁（smith:page:）也只是換一頁（裝備四欄設計第九節）
    # 馬市（act:market）同鐵匠鋪：只是打開選單；買、換、餵走 visit_market、feed_mount
    # 捐軍備（act:donate，素材與經濟設計第六節）同鐵匠鋪：在大本營一直按得下去；捐走 donate_spare，軍需官那一串（donate:）不隨機按
    # 設伏、修工事、屯糧（ambush:、works:，後期體力玩法）：體力夠就一直按得下去、收伏一直按得下去；整季機器人只有一個人，劫不到誰，不做
    # 護衛、犒軍、探望（aid:，figure_aid）：體力夠就按得下去；整季機器人不做（同 works:）；宴客（feast:）不花體力、入席離席能一直按
# （宴客搬進功能包：排除的前綴改由那一包宣告，features_core.bot_always）
    # 酒肆（act:tavern、tavern:）同鐵匠鋪：在城裡一直按得下去；整季機器人只有一個人，打聽不到誰，不進
    # 拜入門派（sect:，一類一顆）：不花體力、婉拒之後還在，同 act:rest；只在第一次看到那一則時按得下去（還是隨機挑，婉拒的就不再按）
    options = [o for o in options if not o.id.startswith("sect:") or o.id.partition(":")[2] not in s.player.seen_events]
    options = [
        o for o in options
        if o.id not in ("act:rest", "act:halt", "act:bounties", "act:smith", "act:market", "act:heal", "act:arena", "act:donate", "act:dadian",
                        "act:tavern", DUEL_FLEE, ARENA_YIELD)
        and not o.id.startswith(("road:", "defect:", "invite:", "smith:page:", "donate:", "dadian:", "ambush:", "works:", "aid:", "tavern:",
                                 "act:recruit:", "errand:", "faction:lean:") + features_core.bot_always())  # 功能包宣告的永遠按得下去
    ]  # 招募歷史武將（act:recruit:<id>，歷史武將同行第七節）：整季機器人不招。託付（errand:，減法季批 6）：機器人不收託付，萬一有也不按（勸降要寫字）。頭目戰的抽身退走（DUEL_FLEE）：打到一半一直按得下去，機器人照出招打完
    # 豪強改幫另一軍（faction:lean:，三陣營四勝利）：隨時按得下去、不花體力，同叛投排除（機器人不換邊）
    # 一條線答題的「先擱著」（story:<線>:later）：擱著之後那一顆又按得下去，同 act:rest 排除（答題照隨機答完）
    options = [o for o in options if not (o.id.startswith("story:") and o.id.endswith(":later"))]
    # 特殊頓悟取名的「自己寫」（dunwu:own）：要寫字，按了只回一句叫出輸入框，一直按得下去；機器人先按靜心思名、再從三個候選裡挑
    options = [o for o in options if o.id != "dunwu:own"]
    # 會被打發的求見（名望不夠）永遠按得下去，不排除的話「沒事可做就推進時間」的訊號會失效（同 act:rest）
    options = [
        o for o in options
        if not (o.id.startswith("call:") and o.id != "call:back" and not game.can_meet_figure(o.id.partition(":")[2]))
    ]
    # 挑戰本人照勝算挑（挑戰每季都有設計第九節）：隨機挑選時只留「穩勝」「有把握」的（同假人）；火候滿了等契機時五五波以上都打。
    # 勝算只對此地按得下去的挑戰鈕算（一個地點最多兩位，一次 40 場模擬），其他步驟不多算
    chance = awaits_chance(game)
    keep = CHALLENGE_ODDS + (("五五波",) if chance else ())
    options = [o for o in options if not o.id.startswith("act:challenge:") or game.challenge_odds(o.id.rpartition(":")[2]) in keep]
    if chance:  # 火候滿了、等契機：有挑戰本人可打就去打一場硬仗（打不贏、閉門不見的按不下去，本來就不在這裡）
        hard = [o for o in options if o.id.startswith("act:challenge:")]
        if hard:
            return rng.choice(hard).id
    # 約戰開著（減法季批 3b）：挑到出陣那一格換成真的貼一張（封好三招）；那一格每貼一次就扣次數、起冷卻，不是永遠按得下去
    return duel_go(game, rng.choice(options).id, rng) if options else None


def take_bounties(game: Game) -> None:
    """城裡的懸賞榜上有揭得下的就揭、有交得出的求兵就交（打開、揭、一張一張挑一件交、返回，走 Game 的選單；不花體力）。
    交照 bounties.give_choice（最不值錢的那一件，跟伺服器假人同一個挑法）；求兵不揭（take_problem 擋）。
    揭的做不做得成看之後隨機走到哪裡。"""
    s, c = game.state, game.content

    def enabled() -> set[str]:
        return {o.id for o in game.options(odds=False) if o.enabled}

    if s.pending_event or not bounties.board_here(s, c):
        return
    takeable = any(bounties.can_take(s, b) and bounties.take_problem(s, c, b) is None for b in bounties.open_bounties(s, c))
    if not takeable and bounties.give_choice(s, c, game.world) is None:
        return  # 沒得揭，也沒得交
    if "act:bounties" not in enabled():
        return
    game.choose("act:bounties")
    for option in game.options(odds=False):
        if option.enabled and option.id.startswith("bounty:take:"):
            game.choose(option.id)
    for _ in range(c.config.bounties.give_list):  # 交到沒得交為止（一張一人一次：每交一張就少一張）
        move = bounties.give_choice(s, c, game.world)
        if move is None or f"bounty:pick:{move[0]}" not in enabled():
            break
        game.choose(f"bounty:pick:{move[0]}")
        give = f"bounty:give:{move[0]}:{move[1]}"
        if give not in enabled():
            game.choose("bounty:unpick")
            break
        game.choose(give)
    if s.player.picking_bounty:
        game.choose("bounty:back")


def smith_want(game: Game) -> str | None:
    """在鐵匠鋪最該按的那一顆（整季機器人與伺服器假人共用；兵器設計第六節、裝備四欄設計第九節）：兵器頁照 weapons.wanted（換、買、修），
    防具頁照 armor.wanted（換、買、修）。停在的那一頁有事先做；這一頁沒事、另一頁有事才回切頁那一顆（smith:page:<頁>），
    下一輪再回真正的動作——不會來回切。還沒進門時照進門會停的那一頁算（equipment.first_page）。打造、淬煉、拆解不在這裡
    （伺服器假人的打造與換上打出來的那把在 forge_step，bot_policy._smith_want 接在這之後；整季機器人的打造與淬煉在 visit_smith
    另外做；淬煉、拆解假人都不做）。都沒事是 None。"""
    s, c, w = game.state, game.content, game.world
    member = s.player.member
    moves = {
        "weapon": weapons.wanted(s, c, w, team.player_art(s, c, w, member.wugong_id)),
        "armor": armor.wanted(s, c, team.player_art(s, c, w, member.neigong_id)),
    }
    here = equipment.page(s.player, c) if s.player.picking_smith else equipment.first_page(c)
    if moves.get(here) is not None:
        return moves[here]
    other = next((slot for slot, move in moves.items() if move is not None), None)
    return None if other is None else f"smith:page:{other}"


# 伺服器假人打一爐之後至少留幾兩（療傷、修）。PM 2026-10-13（FB-144）從 30 降到 10：假人到鐵匠鋪時身上多半只有幾十兩，留 30 兩
# 一整季一爐都打不成
FORGE_SILVER_RESERVE = 10


def forge_step(game: Game) -> str | None:
    """伺服器假人在鐵匠鋪打造的下一顆（打造第二批，PM 2026-10-12 決定第 3 條）：照整季機器人的 forge_plan／armor_plan 挑這一爐
    （一般組合、名器、偶然碰上的神器配方都照打；不讀口訣），回單子的下一步——打開 → 種類 → 主料 → 輔料 → 開爐（防具沒有種類）；
    單子跟這一爐對不上（存檔留下的、計畫變了）回「不打了」。沒有要打的時候，兵器頁上裝備庫裡有比手上更好的那把就換上
    （smithing.better_in_rack；防具的換上 armor.wanted 本來就會）；這一頁沒事、另一頁有一爐要打回切頁那一顆（同 smith_want）。
    工錢付了之後剩不到 FORGE_SILVER_RESERVE 兩的那一爐不打。不淬煉、不拆。沒事是 None。"""
    s, c, w = game.state, game.content, game.world
    p = s.player
    art = team.player_art(s, c, w, p.member.wugong_id)
    plans = _forge_plans(game)
    d = p.smith_draft
    if d is not None:
        plan = plans.get(smithing.slot_of(d.kind))
        if plan is None:
            return smithing.CANCEL
        kind, main, aux = plan
        if d.kind not in (None, kind) or d.main not in (None, main) or d.aux not in (None, aux):
            return smithing.CANCEL
        if d.kind is None:
            return f"{smithing.KIND}{kind}"
        if d.main is None:
            return f"{smithing.MAIN}{main}"
        if d.aux is None:
            return f"{smithing.AUX}{aux}"
        return f"{smithing.GO}{kind}:{main}:{aux}"
    here = equipment.page(p, c) if p.picking_smith else equipment.first_page(c)
    if plans.get(here) is not None:
        return smithing.OPEN
    better = smithing.better_in_rack(s, c, w, art) if here == "weapon" else None
    if better is not None:
        return f"smith:wield:{better.id}"
    other = next((slot for slot, plan in plans.items() if plan is not None and slot != here), None)
    return None if other is None else f"smith:page:{other}"


def _forge_plans(game: Game) -> dict[str, tuple[str, str, str] | None]:
    """這一刻兵器、防具各要打的那一爐（smithing.forge_plan／armor_plan），工錢付了之後剩不到 FORGE_SILVER_RESERVE 兩的當沒有。
    兩樣都要人在有鐵匠鋪的城鎮（forge_plan、armor_plan 自己會問）。"""
    s, c, w = game.state, game.content, game.world
    p = s.player

    def affordable(plan):
        if plan is None:
            return None
        cost = smithing.price(c, smithing.tier_of(c, plan[1]), smithing.slot_of(plan[0]), s)
        return plan if p.stats.get("silver", 0) - cost >= FORGE_SILVER_RESERVE else None

    return {
        "weapon": affordable(smithing.forge_plan(s, c, w, team.player_art(s, c, w, p.member.wugong_id))),
        "armor": affordable(smithing.armor_plan(s, c, w, team.player_art(s, c, w, p.member.neigong_id))),
    }


def forge_ready(game: Game) -> bool:
    """人在城鎮的鐵匠鋪、身上湊得出一爐又付得起（留得下 FORGE_SILVER_RESERVE）：bot_policy 給「進鐵匠鋪」多加 FORGE_SCORE（FB-144）。"""
    return any(plan is not None for plan in _forge_plans(game).values())


def keep_book_names(game: Game) -> None:
    """整季機器人打出神器原品：一律按「沿用譜名」（Game.name_divine(keep=True)；設計第十一節：整季機器人不上線，不用擔心看得出來）。"""
    for item_id in forge_secrets.unnamed_originals(game.state, game.world):
        game.name_divine(item_id, keep=True)


def market_want(game: Game) -> str | None:
    """在馬市最該按的那一顆（整季機器人與伺服器假人共用；裝備四欄設計第九節）：換上更快的、沒馬就買（留 MOUNT_SILVER_RESERVE）、
    飽足低於 mounts.FEED_AT 就餵。沒事是 None。"""
    return mounts.wanted(game.state, game.content, reserve=MOUNT_SILVER_RESERVE)


def visit_market(game: Game) -> None:
    """城裡有馬市就看一眼（裝備四欄設計第九節）：照 market_want 換、買、餵（最多各一次），最後離開。不花體力。
    沒事要做時連選單都不叫。假人不走這裡（bot_policy 照 market_want 給分）。"""
    s = game.state
    if s.pending_event or market_want(game) is None:
        return

    def enabled() -> set[str]:
        return {o.id for o in game.options(odds=False) if o.enabled}

    if "act:market" not in enabled():
        return
    game.choose("act:market")
    for _ in range(3):
        move = market_want(game)
        if move is None or move not in enabled():
            break
        game.choose(move)
    if s.player.picking_market:
        game.choose(mounts.BACK)


def feed_mount(game: Game) -> None:
    """飽足低於 mounts.FEED_AT 就餵（設計第九節：約每 10 段一次；走 Game.feed_mount，同修練頁的「餵」）：閒著時哪裡都能餵，
    在路上、閉關中、沒有一階素材時什麼都不做。整季機器人每一步看一次，假人在 bot_policy.look_after 看。"""
    s, c = game.state, game.content
    item = mounts.riding(s, c)
    if item is not None and item.edge < mounts.FEED_AT and mounts.feed_problem(s, c) is None:
        game.feed_mount()


def wear_better(game: Game) -> None:
    """裝備庫裡有更好的寶物或更快的馬就換上（裝備四欄設計第九節；整季機器人每一步看一次，假人在 bot_policy.look_after 看）：
    寶物照 treasures.wanted（固定順序；寶物不設限制，身上已經是最前面的就不換），馬照 mounts.better_mount（吃飽的腳力，同馬市的
    wanted；路上不換，2.3）。走 Game.wield_weapon（修練頁的「換上」），跟真人一樣。拿到新的、那一欄空著時本來就自動穿上，這裡只管換；不叫模型。"""
    s, c = game.state, game.content
    tid = treasures.wanted(s, c)
    if tid is not None:
        game.wield_weapon(tid)
    if s.player.journey is None and (horse := mounts.better_mount(s, c)) is not None:
        game.wield_weapon(horse)


def trade_want(game: Game) -> tuple | None:
    """鐵匠鋪的下一件素材買賣（素材與經濟計畫 B5；整季機器人與假人共用）：先升階、再賣，沒事是 None。
    素材四階開著時（正式季整合 8.1）：三換四是那個屬性的四階少於 TIER4_WANT、這一季還能換；其餘每一階照一般的料：高一階不夠換下一階、
    低一階比留的（trade_keep）多出一份以上；三階跟一、二階一樣多的賣、捐，四階不賣不捐（本來就不收）。關著照舊：
    升三階：那個屬性的三階少於 TIER3_WANT、二階夠換、今天還能換；升二階：二階不夠換一個三階、一階比留的（TRADE_KEEP）多出一份以上；
    升階付完工錢要剩 TRADE_SILVER_RESERVE；出來的屬性隨機（economy.upgrade_outcomes），出什麼收什麼、照舊往下算。
    賣：一階、二階多過留的量的部分。三階不賣。回 ("upgrade", 屬性, 階) 或 ("sell", 素材, 個數)。"""
    s, c = game.state, game.content
    econ = c.config.economy
    held = s.player.materials
    keep = trade_keep(c)
    if econ.upgrade:
        day = game.econ_day()
        needs = economy.upgrade_needs(c)
        four = four_tiers.on(c)
        for attribute, tier in sorted(economy.upgradable(c), key=lambda pair: -pair[1]):  # 高階先
            high, low = economy.upgrade_pair(c, attribute, tier)
            need = needs[tier]
            if tier == four_tiers.TIER:  # 三換四（正式季整合 8.1）：那個屬性的四階少於 TIER4_WANT 就換，一季照規矩
                wanted = held.get(high.id, 0) < TIER4_WANT
            elif tier >= 3 and not four:  # 素材四階關著：舊規則，三階留著湊神器
                wanted = held.get(high.id, 0) < TIER3_WANT
            else:  # 一般的料（素材四階開著時三階也是）：高一階不夠換下一階、低一階比留的多出一份以上
                wanted = held.get(high.id, 0) < needs.get(tier + 1, need) and held.get(low.id, 0) >= keep.get(low.tier, 0) + need
            affordable = s.player.stats.get("silver", 0) - economy.upgrade_cost(s, c, tier) >= TRADE_SILVER_RESERVE
            if wanted and affordable and economy.upgrade_problem(s, c, attribute, tier, day) is None:
                return ("upgrade", attribute, tier)
    if econ.sell:
        for mid, n in sorted(held.items()):
            material = c.materials.get(mid)
            spare = keep.get(material.tier) if material is not None else None
            if spare is not None and n > spare and economy.sell_price_for(s, c, material.tier) is not None:
                return ("sell", mid, n - spare)
    return None


def trade_keep(content) -> dict[int, int]:
    """每一階留幾個不賣不捐（TRADE_KEEP）：素材四階開著時三階照一、二階的規矩、留夠三換四的（正式季整合 8.1：「留兩個三階湊神器」
    改成留四階，四階本來就不收）；關著照舊只有一、二階（三階不賣不捐）。"""
    return dict(TRADE_KEEP) if four_tiers.on(content) else {t: n for t, n in TRADE_KEEP.items() if t < 3}


def trade_at_smith(game: Game) -> None:
    """人在鐵匠鋪（選單開著）時照 trade_want 升、賣到沒事為止（走店面的 Game.smith_upgrade／smith_sell，跟真人按鈕同一條）。
    不在鐵匠鋪什麼都不做：不為了它繞路。"""
    if not game.state.player.picking_smith:
        return
    for _ in range(TRADE_MOVES):
        move = trade_want(game)
        if move is None:
            return
        before = dict(game.state.player.materials)
        if move[0] == "upgrade":
            game.smith_upgrade(move[1], move[2])
        else:
            game.smith_sell(move[1], move[2])
        if game.state.player.materials == before:
            return  # 被拒絕（店那一串不在眼前之類）：不再試


def donate_want(game: Game) -> tuple[str, int] | None:
    """在自家大本營捐什麼（素材與經濟計畫 B5）：今天還有點數時，一階、二階多過留的量（TRADE_KEEP）的部分，一階先；三階不捐。
    回 (素材, 個數)（個數已經照今天剩的點數切過），沒事是 None。人在不在大本營由 donate_spare 問。"""
    s, c = game.state, game.content
    if not c.config.economy.donate:
        return None
    room = economy.donate_room(s, c, game.econ_day())
    keep = trade_keep(c)
    for tier in sorted(keep):
        for mid, n in sorted(s.player.materials.items()):
            material = c.materials.get(mid)
            points = economy.donate_points(c, mid)
            if material is None or material.tier != tier or points <= 0:
                continue
            count = min(n - keep[tier], room // points)
            if count > 0:
                return mid, count
    return None


def donate_spare(game: Game) -> None:
    """人在自家大本營、閒著時，照 donate_want 捐到沒事為止（Game.donate，跟真人同一條）；不在大本營什麼都不做：不為了它繞路。"""
    for _ in range(TRADE_MOVES):
        if not game.can_donate_here():
            return
        move = donate_want(game)
        if move is None:
            return
        before = dict(game.state.player.materials)
        game.donate(*move)
        if game.state.player.materials == before:
            return


def visit_smith(game: Game) -> None:
    """城裡有鐵匠鋪就看一眼（兵器設計第六節、四欄設計第九節）：先在兵器頁照 weapons.wanted 換、買、修，再照 smithing.forge_plan
    打一把、把裝備庫裡更好的換上、淬煉手上那把、收掉打造的單子；再切到防具頁照 armor.wanted 換、買、修，照 smithing.armor_plan 打一件
    （打出來比身上那件好就換上：armor.wanted 先看裝備庫）、淬煉身上那件、收掉單子；最後離開。兵器的事先做完才切防具頁
    （打造與淬煉的鈕各在各頁）。每一頁換買修最多按四下。不花體力。假人不走這裡（bot_policy 照 smith_want 與 forge_step，打造但不淬煉）。"""
    s, c, w = game.state, game.content, game.world

    def art():
        return team.player_art(s, c, w, s.player.member.wugong_id)

    def inner():
        return team.player_art(s, c, w, s.player.member.neigong_id)

    def enabled() -> set[str]:
        return {o.id for o in game.options(odds=False) if o.enabled}

    def press(wanted: Callable[[], str | None]) -> None:
        for _ in range(4):
            move = wanted()
            if move is None or move not in enabled():
                break
            game.choose(move)

    def finish_draft() -> None:
        if s.player.smith_draft is not None and smithing.CANCEL in enabled():
            game.choose(smithing.CANCEL)  # 單子走到一半（按不下去）：收掉，不留在單子上（單子開著時也沒有切頁鈕、沒有離開）

    if s.pending_event or not equipment.smith_open(s, c):
        return
    if (smith_want(game) is None and not smithing.has_errand(s, c, w, art()) and not smithing.armor_errand(s, c, w, inner())
            and trade_want(game) is None):
        return
    if "act:smith" not in enabled():
        return
    game.choose("act:smith")
    trade_at_smith(game)  # 素材與經濟（計畫 B5）：先升階、把多的賣掉（賣了有錢買修打）
    if equipment.page(s.player, c) == "weapon":  # 進門停在兵器頁（武器關著時直接是防具頁，這一段跳過）
        press(lambda: weapons.wanted(s, c, w, art()))
        plan = smithing.forge_plan(s, c, w, art())
        if plan is not None:
            for oid in smithing.wizard_steps(*plan):
                if oid not in enabled():
                    break
                game.choose(oid)
        better = smithing.better_in_rack(s, c, w, art())
        if better is not None and f"smith:wield:{better.id}" in enabled():
            game.choose(f"smith:wield:{better.id}")
        for _ in range(c.config.weapons.temper_max):
            if not smithing.temper_wanted(s, c, w, art()) or smithing.TEMPER not in enabled():
                break
            game.choose(smithing.TEMPER)
        finish_draft()
        if (armor.wanted(s, c, inner()) is not None or smithing.armor_errand(s, c, w, inner())) and "smith:page:armor" in enabled():
            game.choose("smith:page:armor")  # 防具的事在另一頁：兵器的事（含打造、淬煉）做完才切過去
    if equipment.page(s.player, c) == "armor":
        press(lambda: armor.wanted(s, c, inner()))
        plan = smithing.armor_plan(s, c, w, inner())
        if plan is not None:
            for oid in smithing.wizard_steps(*plan):
                if oid not in enabled():
                    break
                game.choose(oid)
            finish_draft()
            press(lambda: armor.wanted(s, c, inner()))  # 打出來進了裝備庫、比身上那件好：換上
        for _ in range(c.config.armor.temper_max):
            if not smithing.armor_temper_wanted(s, c, w, inner()) or smithing.ARMOR_TEMPER not in enabled():
                break
            game.choose(smithing.ARMOR_TEMPER)
        finish_draft()
    if s.player.picking_smith:
        game.choose("smith:back")


def play_season(
    content: Content, seed: int, max_steps: int = 20000, observe: Callable[[Game], None] | None = None,
    world: WorldStateStore | None = None, now: float = 0.0,
) -> Game:
    """玩完一季：隨機挑選項、遇到結識一定接受、每隔幾步把攢下的心得拿去練成、合成與修練。
    observe 不是 None 時，開始玩之前呼叫一次（開季的樣子），之後每一步之後都呼叫一次
    （模擬器用來記錄名冊與交手的時間點）。"""
    if prologue_rules.has(content):
        # 內容有序章：機器人走序章（graduated，離開起點時跟走完草廬的真人一樣），要在開了季的世界走，籌備中什麼都不能做。
        # 沒有序章的內容（正式內容現在就是）沒有這一段，整季跟以前一模一樣。
        world = world or open_world()
        if not world.get_season().storyline:
            world.seed_first_season(content)
        world.open_season(content, now=now)
    game = Game.new(content, f"機器人{seed}", rng=random.Random(seed), world=world, graduated=True)
    game.now = now  # 賽季開幕與之後開的決戰用同一個時鐘
    game.world.open_season(game.content, now=now)  # 模擬時機器人自己就是管理者：籌備中就直接開季，已經開了則什麼都不做
    rng = random.Random(seed)
    if observe is not None:
        observe(game)
    for step in range(max_steps):
        if game.state.world.ended:
            break
        check_in(game)  # 21 天季每天簽一次（簽過了、別的季什麼都不做）
        take_pill(game)
        options = [o for o in game.options(odds=False) if o.enabled]
        hop = clinic_hop(game)  # 內傷重了先繞去醫館（排在 pick 前面：量表包住 pick 的引導也不會把它蓋掉）
        choice = f"move:{hop}" if hop is not None and f"move:{hop}" in {o.id for o in options} else (
            pick(game, options, rng) if options else None)
        if choice is not None:
            if choice == sensing.DRAW:
                sense_draw(game, rng)
            else:
                game.choose(choice)
            if step % SPEND_XINDE_EVERY == 0:
                allocate_points(game, rng)
                spend_xinde(game, rng)
                forge_and_cultivate(game, rng)
            if wants_heal(game):  # 走進醫館就療傷（不等 spend_xinde 那一步：機器人不會在醫館裡久待）
                game.heal()
            take_bounties(game)  # 路過城鎮就看一眼懸賞榜（揭不了的時候什麼都不做）
            donate_spare(game)  # 走到自家大本營就把多的素材捐了（素材與經濟計畫 B5；不在大本營什麼都不做）
            visit_smith(game)  # 路過城鎮就看一眼鐵匠鋪（沒事要買要修要換的時候什麼都不做）
            keep_book_names(game)  # 打出神器原品就沿用譜名（打造第二批）
            visit_market(game)  # 路過馬市就看一眼（沒事要買要換要餵的時候什麼都不做）
            feed_mount(game)  # 馬餓了就餵（閒著時哪裡都能餵）
            wear_better(game)  # 裝備庫裡有更好的寶物、更快的馬就換上
        if choice is None or step % 4 == 0:
            game.advance(HALF_HOUR)
        if observe is not None:
            observe(game)
    return game
