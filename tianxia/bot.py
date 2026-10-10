"""亂數機器人：玩完一整季，用於整季測試與平衡模擬。

sanguo-companions 合併大幅重寫：拿掉抽卡、收徒、多隊派遣——招募到新同伴後不用機器人
額外處理，roster.attempt_recruit/recruit 已經自動把人加進隊伍（見 roster.py）。大多數
時候隨機選一個可用的選項（含深度對話的 talk:N，模型叫不動時那輪對話會直接結束，不需要真的連
Ollama）；只有「結識」一定接受；心得攢夠一定步數就拿去練成、合成，體力有餘就修練（見 spend_xinde、forge_and_cultivate）。
"""
from __future__ import annotations

import random
from collections.abc import Callable
from typing import NamedTuple

from . import bounties, cultivation, fusion, glyph, insights, library, naming, sensing, team, traits, weapons
from . import prologue as prologue_rules
from .engine import FREE_TEXT_OPTION, SAY_OPTION, Game, Option
from .martial_arts import MartialArt, next_quality
from .models import Content
from .sqlite_world import open_world
from .world_state import WorldStateStore

HALF_HOUR = 1800
SPEND_XINDE_EVERY = 5  # 每幾步檢查一次要不要拿心得去練功/療傷
FORESHADOW_OPTIONS = ("fs:", "talk:clue:", "opp:", "talk:opp:")  # 伏筆的最後一步、對話的片段與機緣（正式版乙一）：機器人不做

FORGE_TRIES = 4  # 武學＋意境、武學＋武學、意境＋意境各試幾組（被擋下就換一組）
SENSE_RIGHT = 0.6  # 有所感時挑到選得對的做法的機會（其餘從全部做法裡隨便挑，可能也挑對）：看得懂場景的玩家大多挑得對
SENSE_DRAW = 0.8  # 進了感悟狀態之後真的畫一筆（其餘順其自然，落回做法那個基本意境）
MERGE_SHARE = 0.3  # 手上有兩個以上意境時，這麼多的機會改做合併
FORGE_RESERVE = 20  # 三種合成都花體力（武學與成長設計 12.1）：體力留這麼多給探索與遊歷，多出來的才拿去合成
BLEND_SHARE = 0.3  # 沒做合併、手上有兩門以上武學時，這麼多的機會改做武學＋武學（沒有意境可合成時一定做）
CULTIVATE_RESERVE = 60  # 體力留這麼多給探索與遊歷，多出來的才拿去修練
TRAIT_WEIGHT = 0.05  # 機器人選身上那門時，每一層功效（乘過品質）、每個特別功效算多少比例的威力（武學與成長設計 13.7）


def wants_heal(game: Game) -> bool:
    """有內傷、而且付得起才療傷：療傷照內傷計價（見 team.heal_cost）。氣血低但沒有內傷時會自己回，
    付不起時去療傷只會寫一筆「銀兩不足」。"""
    cost = team.heal_cost(game.content, game.state.player.member)
    return 0 < cost <= game.state.player.stats.get("silver", 0)


def can_practise(game: Game, kind: str) -> bool:
    """身上這一門還沒第十成、而且付得起下一成的心得（練成花心得，武學與成長設計 4.2）。"""
    return team.can_practise(game.state, game.content, kind)


PILL_BELOW = 10  # 回體丹（內測贈送）：體力掉到連一次探索、遊歷都不夠時才吃一顆，跟急著玩的真人一樣；夾在上限，不會吃在半滿的時候浪費


def take_pill(game: Game) -> None:
    """體力見底、手上有回體丹就服一顆（只走 Game.take_stamina_pill，跟真人按體力條上的「丹」一樣）。整季機器人與伺服器假人共用。
    pill_only=True：測試期間 Config.beta_free_refill 打開時，真人按同一顆鈕是免費補滿；機器人與假人不吃那個，照舊只吃丹
    （沒有丹就不補），整季模擬與平衡量表不因為測試期間的免費補滿而變。開關關著時 pill_only 沒有作用。"""
    p = game.state.player
    if p.stamina_pills > 0 and p.stamina < PILL_BELOW:
        game.take_stamina_pill(pill_only=True)


def allocate_points(game: Game, rng: random.Random) -> None:
    """升級得到的屬性點隨機分掉（還沒到頂的那幾項裡挑）。走 Game.allocate_stat——真人按按鈕的同一條路。
    迴圈有界：它在全服寫入鎖裡跑，空轉會凍住伺服器。最多試「手上有幾點」次；全到頂、或 allocate_stat
    拒絕了（賽季籌備中等，點數沒少）就停，剩下的點留著。"""
    p, cap = game.state.player, game.content.config.stat_cap
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


class ForgePlan(NamedTuple):
    """挑好的一爐（還沒開）：武學＋意境是 (武學, (意境,), None)、武學＋武學是 (第一門, (), 第二門)、意境＋意境是 (None, (甲, 乙), None)。"""

    art_id: str | None
    insight_ids: tuple[str, ...]
    other_art: str | None


def pick_forge(
    game: Game, rng: random.Random, merge_share: float | None = None, blend_share: float | None = None,
) -> ForgePlan | None:
    """挑一爐（整季機器人與伺服器假人共用）：體力低於 FORGE_RESERVE、或什麼都合不了就是 None。只挑、不開爐，什麼都不改。
    亂數的擲法跟原本寫在 forge_and_cultivate 裡的一模一樣（見那邊的說明），整季機器人的結果不變。
    兩個份額是引數（伺服器假人的武學＋武學份額比較低）；沒給就在呼叫的當下讀模組常數 MERGE_SHARE、BLEND_SHARE
    （不是定義時綁死：量平衡的腳本改這兩個常數要有效）。"""
    merge_share = MERGE_SHARE if merge_share is None else merge_share
    blend_share = BLEND_SHARE if blend_share is None else blend_share
    state, content, world = game.state, game.content, game.world
    p = state.player
    arts = library.owned_arts(state)
    can_fuse, can_blend = bool(p.insights and arts), len(arts) >= 2
    if not (can_fuse or can_blend) or p.stamina < FORGE_RESERVE:
        return None
    if len(p.insights) >= 2 and rng.random() < merge_share:
        for _ in range(FORGE_TRIES):
            a, b = rng.choice(p.insights), rng.choice(p.insights)
            if fusion.merge_problem(state, content, world, a, b) is None:
                return ForgePlan(None, (a, b), None)
        return None
    if can_blend and (not can_fuse or rng.random() < blend_share):
        for _ in range(FORGE_TRIES):
            a, b = rng.sample(arts, 2)
            if fusion.blend_problem(state, content, world, a, b) is None:
                return ForgePlan(a, (), b)
        return None
    for _ in range(FORGE_TRIES):
        art_id, insight_id = rng.choice(arts), rng.choice(p.insights)
        if fusion.fuse_problem(state, content, world, art_id, insight_id) is None:
            return ForgePlan(art_id, (insight_id,), None)
    return None


def forge_and_cultivate(game: Game, rng: random.Random) -> None:
    """機器人的武學：等著定名的先定名；滿了先熔最弱的；體力有餘就合成（武學＋意境為主，偶爾合併、偶爾武學＋武學）；
    改練更強的；體力再有餘就修練一次。機器人會用到這套玩法很重要——不然整季模擬碰不到合成與修練，量出來的平衡沒有意義
    （CLAUDE.md「第三層」的教訓）。
    亂數的用法：MERGE_SHARE 那一擲只在手上有兩個以上意境時才擲，BLEND_SHARE 那一擲只在武學＋意境與武學＋武學都能做時才擲，
    所以只有一門武學、一個意境的機器人，亂數的用法跟以前一模一樣——前提是體力有到 FORGE_RESERVE：低於保留量就整段不合成、
    一次亂數也不擲（保留量是武學＋武學那一刀才加的，以前機器人想合就合）。"""
    state, content, world = game.state, game.content, game.world
    p = state.player
    if p.naming is not None:
        game.name_mastered(naming.fallback_name(content, f"定名|{p.naming}", "武學", salt=rng.randint(0, 99)))
    if library.full(state, content):
        melt_the_weakest(game)
    plan = pick_forge(game, rng)
    if plan is not None:
        game.forge(plan.art_id, list(plan.insight_ids), other_art=plan.other_art)
    switch_to_the_strongest(game)
    if p.stamina >= CULTIVATE_RESERVE:
        for art_id in worn_first(game):
            pill = takes_the_pill(game, art_id)
            if cultivation.cultivate_problem(state, content, world, art_id, use_legend=pill) is None:
                game.cultivate(art_id, use_legend=pill)
                break


def worn_first(game: Game) -> list[str]:
    """修練挑哪一門：身上的兩門先（武學、內功），再照功法庫的順序。成數門檻（方案 A）與火候（方案 C）都綁在練成上，
    身上那兩門才練得上去；契機也只看身上那兩門。整季機器人與伺服器假人共用。"""
    member, owned = game.state.player.member, library.owned_arts(game.state)
    worn = [a for a in (member.wugong_id, member.neigong_id) if a in owned]
    return worn + [a for a in owned if a not in worn]


def awaits_chance(game: Game) -> bool:
    """身上有一門火候滿了、等著契機（方案 C）：機器人這時有挑戰本人可打就去打（見 pick）。"""
    state, content, world = game.state, game.content, game.world
    rule, member = content.config.breakthrough, state.player.member
    if rule.heat <= 0 or state.player.naming is not None:
        return False
    for art_id, level in ((member.wugong_id, member.wugong_level), (member.neigong_id, member.neigong_level)):
        art = team.resolve_art(art_id, content, world) if art_id else None
        if art is None or next_quality(team.art_quality(state, art)) != "絕學":
            continue
        if level >= content.config.cultivate_min_level.get("絕學", 0) and state.player.art_mastery.get(art_id, 0) >= rule.heat:
            return True
    return False


def takes_the_pill(game: Game, art_id: str) -> bool:
    """這一次衝的是絕學、手上又有破境丹：服（企劃者：丹由玩家自己決定哪一次服，機器人有就服；方案 C 開著時是火候滿了才服）。
    只在這一步傳 use_legend：別的步驟用不上丹，傳了只會多一句「這一回沒服」。要不要算丹由 cultivation.boost_for 決定。"""
    state, content, world = game.state, game.content, game.world
    art = team.player_art(state, content, world, art_id)
    target = next_quality(art.quality) if art is not None else None
    if cultivation.heat_mode(content, target):  # 方案 C：火候滿了才服（強行衝關）；還在添火候時服了也沒用
        return state.player.legend_items > 0 and state.player.art_mastery.get(art_id, 0) >= content.config.breakthrough.heat
    return target is not None and cultivation.boost_for(state, content, target, use_legend=True) > 0


def melt_the_weakest(game: Game) -> None:
    """滿了：熔掉功法庫裡第十成威力最低的一門；庫是空的就化掉一個沒有武學靠它修練的意境。"""
    state, content, world = game.state, game.content, game.world
    spare = [(team.player_art(state, content, world, a), a) for a in state.player.arts]
    spare = [(art.top_power, a) for art, a in spare if art is not None]
    if spare:
        game.melt_art(min(spare)[1])
        return
    needed = {
        used.id for used in (
            insights.for_cultivation(state, content, world, art)
            for art in (team.resolve_art(a, content, world) for a in library.owned_arts(state)) if art is not None
        ) if used is not None
    }
    loose = [i for i in state.player.insights if i not in needed]
    if loose:
        game.melt_insight(loose[0])


def _worth(content: Content, art: MartialArt) -> float:
    """機器人眼中這門武學的價值：第十成威力，加上功效（設計 13.7：不看功效就量不出功效的價值）。每一層一般功效（乘過這一份的
    品質倍數，跟遊戲裡算層數同一份 traits.multiplier）、每個特別功效，各加 TRAIT_WEIGHT 的威力。內容沒有功效就只看威力。"""
    if not content.traits.general:
        return art.top_power
    layers = len(traits.traits_of(art)) * traits.multiplier(content, art.quality) + (1 if art.special else 0)
    return art.top_power * (1 + TRAIT_WEIGHT * layers)


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


def pick(game: Game, options: list[Option], rng: random.Random) -> str | None:
    """結識（choice 的 effect.recruit）一定接受；其餘隨機挑一個。沒得挑時回傳 None。

    故意排除 act:rest：那是修給真人玩家的保底（體力見底時選單不會整排 disabled），
    機器人不需要、也不該選——act:rest 永遠 enabled，機器人要是跟其他選項一樣隨機挑，
    「沒有其他選項可選」這個訊號就永遠不會成立，下面 play_season() 用這個訊號決定要不要
    呼叫 game.advance() 推進遊戲時間的節奏會被打亂（體力耗盡的頻率大幅降低，時間推進
    跟著變少，一整季要跑完所需的步數暴增到頂到 max_steps 才停，拖垮整個測試套件）。
    act:halt（喊停）同理：機器人只走單站、它不會出現，萬一出現了也不能讓它成為「有選項可選」。
    路上的選項（road: 開頭：折返、路上小事）也一樣排除：機器人不改道、不折返、不做路上小事（路上設計第六節），
    而折返在路上永遠按得下去，不排除的話「在路上沒事可做就推進時間」這個訊號會失效。
    名望不夠的求見（call:<人物>）同理：求見一直都在、按下去只是被打發（武學與成長設計 9.1），機器人不白按。"""
    s = game.state
    if s.player.sensing is not None and any(o.id.startswith(sensing.PREFIX) for o in options):
        return sense_pick(game, rng)  # 有所感的卡擋著：先了結它（畫的那一步回 sensing.DRAW，play_season 接著 sense_draw）
    battle = game.world.get_battle()
    if battle is not None and s.player.name not in battle.participants:
        for option in options:  # 集結時選單照常有別的事可做（FB-009）；還沒參戰就先加入，跟以前選單只剩加入時一樣
            if option.id.startswith("battle:join"):
                return option.id
    options = [o for o in options if o.id not in (FREE_TEXT_OPTION, SAY_OPTION)]  # 隨口應對、對話的「自己說」要寫一句話，機器人寫不出有意義的做法（同決戰的 free_text）
    # 伏筆的最後一步與對話的片段選項、機緣的選項與話題：這一版假人不做伏筆（計畫 T7）也不做機緣，同隨口應對一樣排除
    options = [o for o in options if not o.id.startswith(FORESHADOW_OPTIONS)]
    if s.pending_event:
        choices = game.content.events[s.pending_event].choices
        for option in options:
            if option.id.startswith("choice:") and choices[int(option.id.partition(":")[2])].effect.recruit:
                return option.id
    # 叛投（defect:）：機器人不換陣營；選單上一直有，不排除的話「沒事可做就推進時間」的訊號會失效（同 act:rest）
    # 邀請（invite:）：整季機器人不跟別人切磋，收回自己的邀請也一直按得下去，同 act:rest
    # 懸賞榜（act:bounties）在城裡一直按得下去（只是打開第二層選單）：同 act:rest 排除；揭懸賞走 take_bounties
    # 鐵匠鋪（act:smith）同懸賞榜：只是打開選單；買修換走 visit_smith
    options = [
        o for o in options
        if o.id not in ("act:rest", "act:halt", "act:bounties", "act:smith") and not o.id.startswith(("road:", "defect:", "invite:"))
    ]
    # 會被打發的求見（名望不夠）永遠按得下去，不排除的話「沒事可做就推進時間」的訊號會失效（同 act:rest）
    options = [
        o for o in options
        if not (o.id.startswith("call:") and o.id != "call:back" and not game.can_meet_figure(o.id.partition(":")[2]))
    ]
    if awaits_chance(game):  # 火候滿了、等契機：有挑戰本人可打就去打一場硬仗（打不贏、閉門不見的按不下去，本來就不在這裡）
        hard = [o for o in options if o.id.startswith("act:challenge:")]
        if hard:
            return rng.choice(hard).id
    return rng.choice(options).id if options else None


def take_bounties(game: Game) -> None:
    """城裡的懸賞榜上有揭得下的就揭（打開、揭、返回，走 Game 的選單；不花體力）。做不做得成看之後隨機走到哪裡。"""
    s, c = game.state, game.content
    if s.pending_event or not bounties.board_here(s, c):
        return
    if not any(bounties.can_take(s, b) and bounties.take_problem(s, c, b) is None for b in bounties.open_bounties(s, c)):
        return
    if "act:bounties" not in {o.id for o in game.options(odds=False) if o.enabled}:
        return
    game.choose("act:bounties")
    for option in game.options(odds=False):
        if option.enabled and option.id.startswith("bounty:take:"):
            game.choose(option.id)
    if s.player.picking_bounty:
        game.choose("bounty:back")


def visit_smith(game: Game) -> None:
    """城裡有鐵匠鋪就看一眼（兵器設計第六節）：照 weapons.wanted 一顆一顆按到沒事做，再離開。不花體力。"""
    s, c = game.state, game.content
    art = team.player_art(s, c, game.world, s.player.member.wugong_id)
    if s.pending_event or weapons.wanted(s, c, game.world, art) is None:
        return
    if "act:smith" not in {o.id for o in game.options(odds=False) if o.enabled}:
        return
    game.choose("act:smith")
    for _ in range(4):  # 換、買、修最多各一次，夠了
        move = weapons.wanted(s, c, game.world, team.player_art(s, c, game.world, s.player.member.wugong_id))
        if move is None or move not in {o.id for o in game.options(odds=False) if o.enabled}:
            break
        game.choose(move)
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
        take_pill(game)
        options = [o for o in game.options(odds=False) if o.enabled]
        choice = pick(game, options, rng) if options else None
        if choice is not None:
            if choice == sensing.DRAW:
                sense_draw(game, rng)
            else:
                game.choose(choice)
            if step % SPEND_XINDE_EVERY == 0:
                allocate_points(game, rng)
                spend_xinde(game, rng)
                forge_and_cultivate(game, rng)
            take_bounties(game)  # 路過城鎮就看一眼懸賞榜（揭不了的時候什麼都不做）
            visit_smith(game)  # 路過城鎮就看一眼鐵匠鋪（沒事要買要修要換的時候什麼都不做）
        if choice is None or step % 4 == 0:
            game.advance(HALF_HOUR)
        if observe is not None:
            observe(game)
    return game
