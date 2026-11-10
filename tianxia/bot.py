"""亂數機器人：玩完一整季，用於整季測試與平衡模擬。

sanguo-companions 合併大幅重寫：拿掉抽卡、收徒、多隊派遣——招募到新同伴後不用機器人
額外處理，roster.attempt_recruit/recruit 已經自動把人加進隊伍（見 roster.py）。大多數
時候隨機選一個可用的選項（含深度對話的 talk:N，模型叫不動時那輪對話會直接結束，不需要真的連
Ollama）；只有「結識」一定接受；心得攢夠一定步數就拿去練成、合成，體力有餘就修練（見 spend_xinde、forge_and_cultivate）。
"""
from __future__ import annotations

import random
from collections.abc import Callable

from . import allied, clinic
from .features.cultivation import cultivation
from . import library, naming
from .features.sense import sensing
from . import team
from . import prologue as prologue_rules
from .features.sortie import duel_rules as sortie_duel  # 出陣約戰（減法季批 3b）
from .engine import FREE_TEXT_OPTION, GROWTH_PREFIX, Game, Option
from .core import features as features_core
from .models import Content
from .models import Outcome  # 減法季批 4：pick_outcome 的位子
from .sqlite_world import open_world
from .world_state import WorldStateStore
# 別包也讀的、包自己讀的第二輪第 89 批搬走了（bot_base 與各包的 bots.py；包不再跳回這個檔），每包的按法第二輪第 101 批也搬走了。舊名留著，同一批物件：這個檔自己照舊叫（play_season、forge_and_cultivate、pick……），測試與腳本讀；
# 讀者留在這個檔的（pick 讀 awaits_chance、forge_and_cultivate 讀 pick_forge）換這裡打得到，讀者搬走的（pick_forge 讀 MERGE_SHARE、FORGE_RESERVE，sense_pick 讀 SENSE_DRAW）要換新位置那一份。
# forge_and_cultivate、spend_xinde、wants_heal、can_practise、take_pill 留在這裡：同時排幾包的事，或碰 Game 本體的療傷、服丹；包不准 import 包
from .bot_base import CLINIC_MIN_SILVER, CLINIC_URGENT, TRADE_KEEP, TRADE_MOVES, can_pay_clinic, injury_share, trade_keep  # noqa: F401
from .features.battle.bots import enlist_pick  # noqa: F401
from .features.bounties.bots import take_bounties  # noqa: F401
from .features.checkin.bots import check_in  # noqa: F401
from .features.craft.bots import CREATE_INTENTS, CREATE_RESERVE, FORGE_RESERVE, FORGE_TRIES, MERGE_SHARE, ForgePlan, _name_draft, create_art, infuse_spare, pick_forge  # noqa: F401
from .features.cultivation.bots import (  # noqa: F401
    CULTIVATE_RESERVE, TEACH_MAX, TEACH_RESERVE, TRAIT_WEIGHT, _worth, allocate_points, awaits_chance, break_way, growth_key, melt_the_weakest, slot_insights,
    switch_to_the_strongest, takes_the_pill, teach, worn_first,
)
from .features.explore.bots import OUTING_SAY_CHANCE, OUTING_WEIGHTS, outing_say, outing_segments  # noqa: F401
from .features.figure_acts.bots import CHALLENGE_ODDS  # noqa: F401
from .features.gear.bots import MOUNT_SILVER_RESERVE, feed_mount, market_want, visit_market, wear_better  # noqa: F401
from .features.outlets.bots import donate_spare, donate_want  # noqa: F401
from .features.sense.bots import SENSE_DRAW, SENSE_RIGHT, sense_draw, sense_pick, sense_stroke  # noqa: F401
from .features.smithy.bots import (  # noqa: F401
    FORGE_SILVER_RESERVE, TIER3_WANT, TIER4_WANT, TRADE_SILVER_RESERVE, _forge_plans, forge_ready, forge_step, keep_book_names, smith_want, trade_at_smith, trade_want, visit_smith,
)
from .features.sortie.bots import duel_moves  # noqa: F401
from .features.travel.bots import CLINIC_AT, clinic_hop  # noqa: F401

HALF_HOUR = 1800
SPEND_XINDE_EVERY = 5  # 每幾步檢查一次要不要拿心得去練功/療傷


def wants_heal(game: Game) -> bool:
    """人在醫館、有內傷、付得起（can_pay_clinic）才療傷：療傷照內傷計價（見 team.heal_cost），付不起全治時治一部分。
    氣血低但沒有內傷時會自己回；不在醫館按了只會寫「這裡沒有醫館」。"""
    return can_pay_clinic(game) and clinic.here(game.state, game.content)


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


def spend_xinde(game: Game, rng: random.Random) -> None:
    """有內傷先療傷；接著身上兩門各練一成——付得起才練（練成花心得，開局就有基礎武學，沒有空欄位要自創了）。
    不追求最優策略，只求機器人不會把心得放著不用，也不會一直去撞「心得不足」。"""
    if wants_heal(game):
        game.heal()
    for kind in ("內功", "武學"):
        if can_practise(game, kind):
            game.practice(kind)
    teach(game)


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
    infuse_spare(game)  # 意境合成改版：同一路的凡、佳化進最深的一份（不擲亂數；改版沒開什麼都不做）
    plan = pick_forge(game, rng)
    if plan is not None:
        extra = {"pour": True} if getattr(plan, "pour", False) else {}  # 改版：傾注、立意（PourPlan；沒開時是 ForgePlan，照舊那一行）
        if getattr(plan, "intent", None):
            extra["intent"] = plan.intent
        game.forge(None, list(plan.insight_ids), **extra)
    create_art(game, rng)
    switch_to_the_strongest(game)
    slot_insights(game)  # 武學重構：悟到的意境裝進身上兩門的空槽
    if p.stamina >= CULTIVATE_RESERVE:
        for art_id in worn_first(game):
            way = break_way(game, art_id)
            if way and cultivation.cultivate_problem(state, content, world, art_id, **way) is None:
                game.cultivate(art_id, **way)
                break


def explore_choice(ids, want: str = "material") -> str | None:
    """要探索時按哪一顆：act:explore，不在選單上是 None。量表與腳本共用；want 留著（量表與 same_behavior 帶它）。"""
    return "act:explore" if "act:explore" in ids else None


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
    if any(o.id.startswith(GROWTH_PREFIX) for o in options):  # 開季準備卡：照名號挑配比（不按「自己配」）
        return f"{GROWTH_PREFIX}{growth_key(game)}"
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
    options = [o for o in options if o.id != FREE_TEXT_OPTION]  # 隨口應對要寫一句話，機器人寫不出有意義的做法（同決戰的 free_text）；這一行要在下面的 int() 之前（choice:free 不是數字）
    if s.pending_event:
        choices = game.content.events[s.pending_event].choices
        for option in options:
            if option.id.startswith("choice:") and choices[int(option.id.partition(":")[2])].effect.recruit:
                return option.id
    # 永遠按得下去的（沒有別的事可做時按了也白按，不排除的話「沒事可做就推進時間」的訊號會失效）：各包宣告（Feature.bot_always、Feature.bot_idle、Verb.bot_skip、Verb.tail_bot_skip；全部拆包第 60 批）。
    # act:heal 沒有主人（第 57 批第四節）：療傷走 spend_xinde，這一個字面留在這裡
    options = [o for o in options if o.id != "act:heal" and not features_core.bot_idle(game, o)]
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
