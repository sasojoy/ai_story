"""亂數機器人：玩完一整季，用於整季測試與平衡模擬。

sanguo-companions 合併大幅重寫：拿掉抽卡、收徒、多隊派遣——招募到新同伴後不用機器人
額外處理，roster.attempt_recruit/recruit 已經自動把人加進隊伍（見 roster.py）。大多數
時候隨機選一個可用的選項（含深度對話的 talk:N，模型叫不動時那輪對話會直接結束，不需要真的連
Ollama）；只有「結識」一定接受；心得攢夠一定步數就拿去練成、合成，體力有餘就修練（見 spend_xinde、forge_and_cultivate）。
"""
from __future__ import annotations

import random
from collections.abc import Callable

from . import cultivation, fusion, library, naming, team
from .engine import FREE_TEXT_OPTION, Game, Option
from .martial_arts import next_quality
from .models import Content
from .world_state import WorldStateStore

HALF_HOUR = 1800
SPEND_XINDE_EVERY = 5  # 每幾步檢查一次要不要拿心得去練功/療傷
FORESHADOW_OPTIONS = ("fs:", "talk:clue:")  # 伏筆的最後一步、對話的片段選項：機器人不做伏筆

FORGE_TRIES = 4  # 合成、合併各試幾組（被擋下就換一組）
MERGE_SHARE = 0.3  # 手上有兩個以上意境時，這麼多的機會改做合併
FORGE_RESERVE = 20  # 三種合成都花體力（武學與成長設計 12.1）：體力留這麼多給探索與遊歷，多出來的才拿去合成
BLEND_SHARE = 0.3  # 沒做合併、手上有兩門以上武學時，這麼多的機會改做武學＋武學（沒有意境可合成時一定做）
CULTIVATE_RESERVE = 60  # 體力留這麼多給探索與遊歷，多出來的才拿去修練


def wants_heal(game: Game) -> bool:
    """有內傷、而且付得起才療傷：療傷照內傷計價（見 team.heal_cost）。氣血低但沒有內傷時會自己回，
    付不起時去療傷只會寫一筆「銀兩不足」。"""
    cost = team.heal_cost(game.content, game.state.player.member)
    return 0 < cost <= game.state.player.stats.get("silver", 0)


def can_practise(game: Game, kind: str) -> bool:
    """身上這一門還沒第十成、而且付得起下一成的心得（練成花心得，武學與成長設計 4.2）。"""
    return team.can_practise(game.state, game.content, kind)


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


def forge_and_cultivate(game: Game, rng: random.Random) -> None:
    """機器人的武學：等著定名的先定名；滿了先熔最弱的；體力有餘就合成（武學＋意境為主，偶爾合併、偶爾武學＋武學）；
    改練更強的；體力再有餘就修練一次。機器人會用到這套玩法很重要——不然整季模擬碰不到合成與修練，量出來的平衡沒有意義
    （CLAUDE.md「第三層」的教訓）。
    亂數的用法：MERGE_SHARE 那一擲只在手上有兩個以上意境時才擲，BLEND_SHARE 那一擲只在武學＋意境與武學＋武學都能做時才擲，
    所以只有一門武學、一個意境的機器人，亂數的用法跟以前一模一樣。"""
    state, content, world = game.state, game.content, game.world
    p = state.player
    if p.naming is not None:
        game.name_mastered(naming.fallback_name(content, f"定名|{p.naming}", "武學", salt=rng.randint(0, 99)))
    if library.full(state, content):
        _melt_the_weakest(game)
    arts = library.owned_arts(state)
    can_fuse, can_blend = bool(p.insights and arts), len(arts) >= 2
    if (can_fuse or can_blend) and p.stamina >= FORGE_RESERVE:
        if len(p.insights) >= 2 and rng.random() < MERGE_SHARE:
            for _ in range(FORGE_TRIES):
                a, b = rng.choice(p.insights), rng.choice(p.insights)
                if fusion.merge_problem(state, content, world, a, b) is None:
                    game.forge(None, [a, b])
                    break
        elif can_blend and (not can_fuse or rng.random() < BLEND_SHARE):
            for _ in range(FORGE_TRIES):
                a, b = rng.sample(arts, 2)
                if fusion.blend_problem(state, content, world, a, b) is None:
                    game.forge(a, [], other_art=b)
                    break
        else:
            for _ in range(FORGE_TRIES):
                art_id, insight_id = rng.choice(arts), rng.choice(p.insights)
                if fusion.fuse_problem(state, content, world, art_id, insight_id) is None:
                    game.forge(art_id, [insight_id])
                    break
    _switch_to_the_strongest(game)
    if p.stamina >= CULTIVATE_RESERVE:
        for art_id in library.owned_arts(state):
            if cultivation.cultivate_problem(state, content, world, art_id) is None:
                game.cultivate(art_id, use_legend=_goes_for_a_peerless_art_with_a_pill(game, art_id))
                break


def _goes_for_a_peerless_art_with_a_pill(game: Game, art_id: str) -> bool:
    """這一次衝的是絕學、手上又有破境丹：服（企劃者：丹由玩家自己決定哪一次服，機器人有就服）。
    只在這一步傳 use_legend：別的步驟用不上丹，傳了只會多一句「這一回沒服」。要不要算丹由 cultivation.boost_for 決定。"""
    state, content, world = game.state, game.content, game.world
    art = team.player_art(state, content, world, art_id)
    target = next_quality(art.quality) if art is not None else None
    return target is not None and cultivation.boost_for(state, content, target, use_legend=True) > 0


def _melt_the_weakest(game: Game) -> None:
    """滿了：熔掉功法庫裡第十成威力最低的一門；庫是空的就化掉一個沒有武學靠它修練的意境。"""
    state, content, world = game.state, game.content, game.world
    spare = [(team.player_art(state, content, world, a), a) for a in state.player.arts]
    spare = [(art.top_power, a) for art, a in spare if art is not None]
    if spare:
        game.melt_art(min(spare)[1])
        return
    needed = {
        art.insight for art in (team.resolve_art(a, content, world) for a in library.owned_arts(state))
        if art is not None and art.insight
    }
    loose = [i for i in state.player.insights if i not in needed]
    if loose:
        game.melt_insight(loose[0])


def _switch_to_the_strongest(game: Game) -> None:
    """功法庫裡有比身上這門強的（同一種、照自己修練到的品質算第十成威力）就改練上去。"""
    state, content, world = game.state, game.content, game.world
    for art_id in list(state.player.arts):
        art = team.player_art(state, content, world, art_id)
        if art is None:
            continue
        slot = "neigong_id" if art.kind == "內功" else "wugong_id"
        current = team.player_art(state, content, world, getattr(state.player.member, slot))
        if current is None or art.top_power > current.top_power:
            game.switch_art(art_id)


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
    battle = game.world.get_battle()
    if battle is not None and s.player.name not in battle.participants:
        for option in options:  # 集結時選單照常有別的事可做（FB-009）；還沒參戰就先加入，跟以前選單只剩加入時一樣
            if option.id.startswith("battle:join"):
                return option.id
    options = [o for o in options if o.id != FREE_TEXT_OPTION]  # 隨口應對要寫一句話，機器人寫不出有意義的做法（同決戰的 free_text）
    # 伏筆的最後一步與對話的片段選項：這一版假人不做伏筆（計畫 T7），同隨口應對一樣排除
    options = [o for o in options if not o.id.startswith(FORESHADOW_OPTIONS)]
    if s.pending_event:
        choices = game.content.events[s.pending_event].choices
        for option in options:
            if option.id.startswith("choice:") and choices[int(option.id.partition(":")[2])].effect.recruit:
                return option.id
    options = [o for o in options if o.id not in ("act:rest", "act:halt") and not o.id.startswith("road:")]
    # 會被打發的求見（名望不夠）永遠按得下去，不排除的話「沒事可做就推進時間」的訊號會失效（同 act:rest）
    options = [
        o for o in options
        if not (o.id.startswith("call:") and o.id != "call:back" and not game.can_meet_figure(o.id.partition(":")[2]))
    ]
    return rng.choice(options).id if options else None


def play_season(
    content: Content, seed: int, max_steps: int = 20000, observe: Callable[[Game], None] | None = None,
    world: WorldStateStore | None = None, now: float = 0.0,
) -> Game:
    """玩完一季：隨機挑選項、遇到結識一定接受、每隔幾步把攢下的心得拿去練成、合成與修練。
    observe 不是 None 時，開始玩之前呼叫一次（開季的樣子），之後每一步之後都呼叫一次
    （模擬器用來記錄名冊與交手的時間點）。"""
    game = Game.new(content, f"機器人{seed}", rng=random.Random(seed), world=world)
    game.now = now  # 賽季開幕與之後開的決戰用同一個時鐘
    game.world.open_season(game.content, now=now)  # 模擬時機器人自己就是管理者：籌備中就直接開季，已經開了則什麼都不做
    rng = random.Random(seed)
    if observe is not None:
        observe(game)
    for step in range(max_steps):
        if game.state.world.ended:
            break
        options = [o for o in game.options(odds=False) if o.enabled]
        choice = pick(game, options, rng) if options else None
        if choice is not None:
            game.choose(choice)
            if step % SPEND_XINDE_EVERY == 0:
                allocate_points(game, rng)
                spend_xinde(game, rng)
                forge_and_cultivate(game, rng)
        if choice is None or step % 4 == 0:
            game.advance(HALF_HOUR)
        if observe is not None:
            observe(game)
    return game
