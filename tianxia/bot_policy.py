"""伺服器假人的行為（伺服器假人設計第七節）：照陣營目標替選項打分數，強度旋鈕決定多常挑最高分。

只透過 engine.Game 的公開行動（choose／practice／heal／forge／cultivate…）做事，跟真人按按鈕走同一條
路；不接 LLM（呼叫端把 game.client 設成 None）；例外是首創配方的取名與絕學定名，在鎖外由 bot_runner 做
（見 tend_arts、apply_job）。全服戰鬥裡假人是一般參戰者，每回合從固定戰法裡挑，不寫自由文字。
"""
from __future__ import annotations

import random
from dataclasses import dataclass

from . import atlas, battle_instance, bot, cultivation, library, naming, orders, rules, sensing, server_bots, team
from .bot import allocate_points, can_practise, wants_heal
from .engine import FREE_TEXT_OPTION, Game, Option
from .models import Content, Effect, SkillDef
from .state import BotProfile

REWARD_STATS = ("str", "agi", "con", "wis", "silver", "fame", "xinde")  # 博聞不在內：它只靠升級的點數增加，事件不給
TREND_WEIGHT = 10.0  # 推大勢一點，抵得過十點獎勵
JOIN_BATTLE_SCORE = 100.0
ACT_SCORES = {"explore": 1.0, "socialize": 0.8}
TRAIN_SCORE = 0.6  # 遊歷本身的分數（低於探索）；對自己陣營有利的地點再加上大勢分
HOME_MOVE_SCORE = 0.3  # 往自己陣營的地盤走（投靠點一帶；第一季濃縮版是輸得最多的那條戰線，離得還遠時是往那邊的下一站）
AWAY_MOVE_SCORE = 0.1
TRAIN_MOVE_SCORE = 0.5  # 往「遊歷對自己陣營有利」的地點走，額外加分
# 挑戰打得贏的大勢人物本人（T4）：比探索、交友高，比推大勢的遊歷低（一點大勢抵十分）——前線上照舊遊歷，
# 前線以外遇上了才打；「打擊大勢人物」軍令讓假人專程去找人是 T6 的事
CHALLENGE_SCORE = 1.5
CHALLENGE_ODDS = ("穩勝", "有把握")  # 假人只挑這兩種勝算的人物（輸了要賠銀兩、扣氣血）
# 軍令（計畫 T6）：替這週的軍令記一次，比推三點大勢還值得；往軍令要去的地方走，比就地推一點大勢值得——
# 不然假人永遠就地遊歷推大勢，軍令湊不滿（整季模擬 T11 照實回報）
ORDER_SCORE = 30.0
ORDER_MOVE_SCORE = 12.0
DUTY_SCORE = 0.5  # 守勢行動本身（不替軍令記功時）：低於探索，不然假人整天巡哨
# 召見（計畫 T5）：一季一次、演完才晉升帶部下，到了就應召、沒到就往那裡走，都比軍令優先
SUMMONS_SCORE = 50.0
SUMMONS_MOVE_SCORE = 15.0
STRIKE_ODDS = CHALLENGE_ODDS + ("五五波",)  # 有打擊軍令點名這位人物時，五五波也去打
PRACTICE_CHANCE = 0.2  # 每次行動順便練成一門的機率（付得起心得才練，見 look_after；不是每次行動都練）
FORGE_CHANCE = 0.25  # 每一輪合成一爐的機會（有東西可合、體力有餘時才擲）【預設】
SERVER_BLEND_SHARE = 0.15  # 武學＋武學的份額：比整季機器人低，持有 30 門就有 435 對、每一對都是首創要叫模型【預設】
CULTIVATE_CHANCE = 0.2  # 每一輪修練一次的機會（體力有 bot.CULTIVATE_RESERVE、有東西可修時才擲）【預設】
INVITE_YES = 0.7  # 有人邀切磋時答應的機會（付得起體力才算）【預設】
LEARN_ROOM = 3  # 學藝之後，功法庫至少還留幾格給合成
LEARN_SILVER_RESERVE = 30  # 付完學費至少留幾兩（療傷用）
MASTER_TRIES = 5  # 定名時模型的名字用不了，字表最多另組幾個
NO_NAME: tuple[str | None, str] = (None, "")  # 開爐的 C 段不必取名：鎖內一定不叫模型（同 server.NO_NAME）


@dataclass(frozen=True)
class ForgeJob:
    """要請模型取名（或挑一個）的一爐：A 段在鎖內開的單，交給 bot_runner 在鎖外取名、再拿鎖開爐。"""

    art_id: str | None
    insight_ids: tuple[str, ...]
    other_art: str | None
    request: naming.NamingRequest


@dataclass(frozen=True)
class MasterJob:
    """要請模型另取新名字的絕學定名（企劃者 2026-10-06：不沿用原名）：A 段在鎖內開的單，交給 bot_runner。"""

    art_id: str
    request: naming.NamingRequest


@dataclass(frozen=True)
class SenseJob:
    """有所感畫完那一筆、要請模型取名的私有意境（悟意境設計 0.2b 第 9 點：假人的首悟也要叫模型取名，不然首悟紀錄的名字是
    字表的樣子）：A 段在鎖內開的單（sensing.SenseRequest），交給 bot_runner 在鎖外取名、再拿鎖交回 Game.sense_draw。"""

    request: object  # sensing.SenseRequest


@dataclass
class NamingSlot:
    """這一輪這個假人能不能把一件取名交給模型（首創的爐或絕學定名；bot_runner 給：一次一件、兩件之間要隔一段時間）。
    open 時開成單子放進 job；不 open 時那一爐不開、那個名先不定，skipped 加一（只是數字，主控台只印總數）。"""

    open: bool = False
    job: ForgeJob | MasterJob | SenseJob | None = None
    skipped: int = 0


def take_turn(game: Game, profile: BotProfile, rng: random.Random, slot: NamingSlot | None = None) -> list[str]:
    """做一個動作（外加不受強度影響的照顧動作、武學的事）；沒有能做的事（例如體力不夠）就什麼都不做，回傳空清單。
    在路上的假人這一輪跳過，連照顧動作都不做（地圖擴充設計 3.4）。
    slot 是這一輪的取名名額（見 NamingSlot）：武學的事開出要取名的單時放進 slot.job，這一輪就只做到那裡。"""
    game.options(odds=False)  # 每一輪先替全服戰鬥追趕一次時間（集結截止、回合逾時），跟真人的畫面刷新一樣；在路上、趕路的假人也不例外
    if game.state.player.journey is not None:
        return []
    look_after(game, rng)
    msgs = tend_arts(game, rng, slot)
    if slot is not None and slot.job is not None:
        return msgs  # 這一輪在爐前等名字，不做別的（不然體力可能花掉，C 段開不成）
    s = game.state
    if s.player.sensing is not None:
        return msgs + _sense(game, rng, slot)
    if s.player.pending_companion:
        return msgs + game.choose("talk:leave")
    answer = _answer_invite(game, rng)
    if answer is not None:
        return msgs + game.choose(answer)
    rally = _toward_battle(game)
    if rally is not None:
        return msgs + rally
    options = [  # road: 開頭的是路上的選項：假人不改道、不做路上小事（路上設計 3.5）
        o for o in game.options(odds=False, tick=False)
        if o.enabled and o.id not in ("act:rest", "act:halt", FREE_TEXT_OPTION)
        and not o.id.startswith(("road:", "defect:", "battle:enlist:", "invite:"))  # 叛投：假人不換陣營（計畫甲）；散人的假人不臨時投效
        # 邀請由上面的 _answer_invite 答，不交給打分數亂按
    ]
    if not options:
        return msgs
    ids = [o.id for o in options]
    battle = game.world.get_battle()
    if battle is not None and s.player.name not in battle.participants:
        join = next((i for i in ids if i.startswith("battle:join")), None)
        if join is not None:  # 集結時選單照常有別的事可做（FB-009）；假人一看到加入就加入，不交給強度旋鈕碰運氣
            return msgs + game.choose(join)
    elif battle is not None and battle.phase == "muster":
        # 已經參戰：不換邊（不分陣營的劇本集結時還看得到另一邊的加入），也不走出決戰的大區
        options = [o for o in _staying_for_the_battle(game, battle.battle_id, options) if not o.id.startswith("battle:join")]
        if not options:
            return msgs
        ids = [o.id for o in options]
    if s.player.faction is None and profile.faction is not None and not s.pending_event \
            and not any(i.startswith("battle:") for i in ids):
        step = _toward_faction(game, profile.faction, ids)
        if step is not None:
            return msgs + game.choose(step)
    choice = pick(game, options, profile, rng)
    return msgs + game.choose(choice) if choice else msgs


def _answer_invite(game: Game, rng: random.Random) -> str | None:
    """有人在這裡邀假人切磋（玩家互動第二層）：跟真人一樣在自己這一輪看到才答——付得起體力時 INVITE_YES 的機會答應，
    其餘婉拒（真人也會婉拒，假人不能每一張都答應，不然看得出來）。一次只答一張，最早的那張。沒有邀請是 None。"""
    incoming = [o for o in game.options(odds=False, tick=False) if o.id.startswith("invite:yes:")]
    if not incoming:
        return None
    first = incoming[0]
    if first.enabled and rng.random() < INVITE_YES:
        return first.id
    return "invite:no:" + first.id.removeprefix("invite:yes:")


def look_after(game: Game, rng: random.Random) -> None:
    """照顧動作（不受強度旋鈕影響）：升級的屬性點先配掉（只走 Game.allocate_stat，跟真人一樣）；有內傷先療傷；身上的兩門（開局送的基礎武學）偶爾練成一成，付得起心得才練。
    合成、修練、學藝、改練、熔煉、定名在 tend_arts。"""
    allocate_points(game, rng)
    bot.take_pill(game)  # 體力見底、手上有回體丹就吃一顆（內測贈送，真人假人一樣拿到）
    if wants_heal(game):
        game.heal()
    for kind in ("內功", "武學"):
        if can_practise(game, kind) and rng.random() < PRACTICE_CHANCE:
            game.practice(kind)


def tend_arts(game: Game, rng: random.Random, slot: NamingSlot | None = None) -> list[str]:
    """假人的武學（修練頁與煉製頁上的事），每一輪主要行動之前做；只走 Game 的公開行動，跟真人按按鈕一樣：
    1. 練成絕學、輪到自己定名：請模型另取新名字（企劃者 2026-10-06：不沿用原名），輪得到就開單交給假人程式、這一輪到此為止；
       輪不到先不定（見 _master）；
    2. 這裡教、自己同一種還沒有這個屬性的，學一門（見 _learn_here）；
    3. 庫滿了熔最弱的一門；
    4. 有東西可合、體力有餘時，FORGE_CHANCE 的機會合一爐（挑法同整季機器人，武學＋武學的份額低一點；
       首創的要叫模型，見 _forge）；
    5. 功法庫裡有更強的就改練；
    6. 體力有餘、有東西可修時，CULTIVATE_CHANCE 的機會修練一次（衝絕學、手上有破境丹就服）。
    亂數只在真的有事可做時才擲（有東西可合才擲合成的機會、有東西可修才擲修練的機會）：什麼武學都沒有的假人一次都不擲。
    注意：正式內容開局送兩門基礎武學，所以真的假人從第一輪起就有東西可合、每一輪都擲一次合成的機會
    （假人程式共用的亂數順序因此跟加這個之前不一樣）。"""
    state, content, world = game.state, game.content, game.world
    p = state.player
    msgs: list[str] = []
    if p.naming is not None:
        _master(game, slot)
        if slot is not None and slot.job is not None:
            return msgs  # 這個名在等模型：別的等定完名再說
    msgs += _learn_here(game)
    if library.full(state, content):
        bot.melt_the_weakest(game)
    arts = library.owned_arts(state)
    forgeable = bool(p.insights and arts) or len(arts) >= 2
    if forgeable and p.stamina >= bot.FORGE_RESERVE and rng.random() < FORGE_CHANCE:
        plan = bot.pick_forge(game, rng, blend_share=SERVER_BLEND_SHARE)
        if plan is not None:
            msgs += _forge(game, plan, slot)
            if slot is not None and slot.job is not None:
                return msgs  # 這一爐在等名字：改練與修練等開完爐再說
    bot.switch_to_the_strongest(game)
    if p.stamina >= bot.CULTIVATE_RESERVE:
        ready = [
            a for a in bot.worn_first(game)
            if cultivation.cultivate_problem(state, content, world, a, use_legend=bot.takes_the_pill(game, a)) is None
        ]
        if ready and rng.random() < CULTIVATE_CHANCE:
            msgs += game.cultivate(ready[0], use_legend=bot.takes_the_pill(game, ready[0]))
    return msgs


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


def _sense(game: Game, rng: random.Random, slot: NamingSlot | None) -> list[str]:
    """有所感：挑做法照整季機器人（bot.sense_pick）。要畫的時候，輪得到取名名額就隨手畫一筆——要取名的開成單交給假人程式；
    輪不到就畫一筆跟做法同屬性的（一定落回這裡的基本意境、不用取名），不拿字表名字悟出私有意境。"""
    choice = bot.sense_pick(game, rng)
    if choice is None:
        return []
    if choice != sensing.DRAW:
        return game.choose(choice)
    can_name = slot is not None and slot.open and slot.job is None
    req = game.sense_request(bot.sense_stroke(game, rng, same=not can_name))
    if isinstance(req, str):
        return game.choose(sensing.LET_GO)
    if req.needs_name:
        if can_name:
            slot.job = SenseJob(req)
            return []
        if slot is not None:
            slot.skipped += 1
        return game.choose(sensing.LET_GO)
    return game.sense_draw(req, NO_NAME)


def _forge(game: Game, plan: bot.ForgePlan, slot: NamingSlot | None) -> list[str]:
    """開一爐。要模型取名（或挑）的：輪得到就開單交給假人程式（B、C 段在 bot_runner），輪不到這一爐不開——
    用字表的名字搶下首創，名字的樣子看得出是假人（企劃者 2026-10-05）。不必叫模型的（配方有了、只有一個候選）照開，
    給 NO_NAME，鎖內一定不叫模型。"""
    insight_ids = list(plan.insight_ids)
    request = game.forge_request(plan.art_id, insight_ids, other_art=plan.other_art, named_outside=True)
    if request is None:
        return game.forge(plan.art_id, insight_ids, proposed=NO_NAME, other_art=plan.other_art)
    if slot is not None and slot.open and slot.job is None:
        slot.job = ForgeJob(plan.art_id, plan.insight_ids, plan.other_art, request)
    elif slot is not None:
        slot.skipped += 1
    return []


def _master(game: Game, slot: NamingSlot | None) -> None:
    """絕學定名的 A 段：輪得到就開單交給假人程式；輪不到先不定（不沿用原名：江湖史那一行同一個名字出現兩次，
    真人那一步是自己填的，看得出是假人；企劃者 2026-10-06）。"""
    request = game.mastery_request()
    if request is None:
        return
    if slot is not None and slot.open and slot.job is None:
        slot.job = MasterJob(game.state.player.naming, request)
    elif slot is not None:
        slot.skipped += 1


def apply_job(game: Game, job: ForgeJob | MasterJob | SenseJob, proposed: tuple[str | None, str]) -> list[str]:
    """C 段（bot_runner 在鎖內、重讀角色之後呼叫）：
    - 首創的爐：交給 Game.forge(proposed=...) 整個重驗再登記（等名字的時候配方被別人登記了，照查到的給、不收第二次）。
      取新名字的單（沒有候選）要是沒有過得了過濾的名字（模型沒取到、或這時重驗過不了），這一爐不開、不收費：
      Game.forge 會走字表名字搶下首創，那正是看得出是假人的樣子（真人在模型掛掉時走字表，假人不行）。
      挑一個的單（有候選）沒挑到照常開，由規則挑，不產生新名字；
    - 絕學定名：還輪到這一門才定。模型的名字先過一次完整的過濾（naming.recheck），跟原名一樣、過不了、或定的時候
      被用掉了，就用退路字表另組（salt 從 0 起），最多 MASTER_TRIES 個，一定跟原名不同。都定不成就留著，下次再來。"""
    state, content, world = game.state, game.content, game.world
    if isinstance(job, SenseJob):  # 取不到名字照樣交回：私有意境走退路字表，不記首悟（Game._sense_apply 只記模型取的）
        return game.sense_draw(job.request, proposed)
    if isinstance(job, ForgeJob):
        if not job.request.choices and naming.recheck(content, proposed, world.is_character_name)[0] is None:
            return []  # 取新名字的那一爐沒有名字可用：不開，不用字表名字搶下首創（見下面的說明）
        return game.forge(job.art_id, list(job.insight_ids), proposed=proposed, other_art=job.other_art)
    if state.player.naming != job.art_id:
        return []
    old = team.resolve_art(job.art_id, content, world)
    if old is None:
        return []
    name, _ = naming.recheck(content, proposed, world.is_character_name)
    candidates = ([name] if name else []) + [
        naming.fallback_name(content, f"定名|{job.art_id}", old.kind, salt=i) for i in range(MASTER_TRIES)
    ]
    for candidate in candidates:
        if candidate == old.name:
            continue
        msgs = game.name_mastered(candidate)
        if state.player.naming is None:
            return msgs
    return []


def pick(game: Game, options: list[Option], profile: BotProfile, rng: random.Random) -> str | None:
    """以強度旋鈕的機率挑最高分的選項（同分隨機），否則從假人會選的選項裡隨便挑。"""
    scored = [(score(game, o, profile), o.id) for o in options]
    scored = [(value, option_id) for value, option_id in scored if value is not None]
    if not scored:
        return None
    if rng.random() < server_bots.strength(game.content.config, profile):
        best = max(value for value, _ in scored)
        return rng.choice([option_id for value, option_id in scored if value == best])
    return rng.choice([option_id for _, option_id in scored])


def score(game: Game, option: Option, profile: BotProfile) -> float | None:
    """選項的分數；None＝假人不會選（別的陣營的投靠、叛投、閒聊或求見大勢人物、只會被擋在門外的交友、投靠的確認畫面另外處理）。"""
    kind, _, arg = option.id.partition(":")
    if kind == "defect":
        return None  # 假人不叛投（計畫甲）
    if kind == "opp":
        return None  # 機緣：假人不做（正式版乙一）；對話裡的 talk:opp: 落在下面 talk 的 None
    if kind == "battle":
        return _battle_score(game, arg)
    if kind == "choice":
        event = game.content.events[game.state.pending_event]
        effect = event.choices[int(arg)].effect
        moved = rules.resolve_trends(game.content, game.state.world, effect.trend, game.state.player.location)
        return effect_score(effect, _goals(game, profile), moved)
    if kind == "talk":
        return 0.0 if arg == "leave" else None
    if kind == "call":
        # 假人不求見大勢人物（不呼叫模型）；名望不夠的求見永遠按得下去（只是被打發，武學與成長設計 9.1），更不能給分；
        # 萬一停在求見選單上，只會按返回
        return 0.0 if arg == "back" else None
    if kind == "move":
        base = HOME_MOVE_SCORE if arg == _front_hop(game, profile) or arg in _home(game, profile) else AWAY_MOVE_SCORE
        order_hop = ORDER_MOVE_SCORE if arg.partition(":")[0] == _order_hop(game) else 0.0  # 往軍令要去的地方（計畫 T6）
        summons_hop = SUMMONS_MOVE_SCORE if arg.partition(":")[0] == _summons_hop(game) else 0.0  # 往召見的地點（計畫 T5）
        return base + order_hop + summons_hop + (TRAIN_MOVE_SCORE if _train_value(game, profile, arg) > 0 else 0.0)
    if kind == "act":
        if arg.startswith("challenge:"):  # 挑戰本人：打得贏才去（打不贏的、閉門不見的按不下去，本來就不在候選裡）
            fid = arg.partition(":")[2]
            odds = game.challenge_odds(fid)
            if orders.strike_on(game.state, game.content, game.state.player.faction, fid):  # 打擊軍令點名他（計畫 T6）
                return ORDER_SCORE + CHALLENGE_SCORE if odds in STRIKE_ODDS else None
            return CHALLENGE_SCORE if odds in CHALLENGE_ODDS else None
        if arg == "call":
            return None
        if arg == "socialize" and (game.socialize_starts_dialogue() or game.socialize_is_futile()):
            return None
        if arg == "train":
            s = game.state
            bonus = ORDER_SCORE if orders.win_counts(s, game.content, s.player.faction, s.player.location) else 0.0
            return TRAIN_SCORE + _train_value(game, profile) + bonus
        if arg == "duty":  # 守勢行動（計畫 T6）：替守城記功才值得做
            s = game.state
            return DUTY_SCORE + (ORDER_SCORE if orders.duty_counts(s, game.content, s.player.faction, s.player.location) else 0.0)
        if arg == "rank2":  # 第 2 階行動（正式版乙一）：跟守勢行動一樣的底分；替軍令記功的加分是計畫戊的事
            return DUTY_SCORE
        if arg == "convoy":  # 接下糧車：只在有護糧軍令的起點出現
            return ORDER_SCORE
        if arg == "summons":  # 應召（計畫 T5）：只在召見的地點出現
            return SUMMONS_SCORE
        return ACT_SCORES.get(arg, 0.0)
    return None


def effect_score(effect: Effect, goals: dict[str, int], trend: dict[str, int] | None = None) -> float:
    """選項效果的分數：把大勢往陣營想要的方向推，一點抵十分；能力、心得、銀兩、名望等獎勵每點 0.1 分。
    trend 是照 rules.resolve_trends 換過鍵的推動（front 換成所在戰線）；不給就照效果原本寫的。"""
    pushes = effect.trend if trend is None else trend
    push = sum(goals.get(trend_id, 0) * delta for trend_id, delta in pushes.items())
    reward = sum(max(0, effect.stats.get(key, 0)) for key in REWARD_STATS)
    return TREND_WEIGHT * push + reward / 10


def _train_value(game: Game, profile: BotProfile, loc_id: str | None = None) -> float:
    """在這個地點（預設所在地）遊歷對自己陣營的大勢分（同 effect_score 的一點抵十分）。"""
    goals = _goals(game, profile)
    return TREND_WEIGHT * sum(goals.get(t, 0) * d for t, d in game.train_trend_push(loc_id).items())


def _toward_battle(game: Game) -> list[str] | None:
    """自己這一方的全服決戰在集結或開打、自己人卻不在現場（見 Game.rally_region）：往那個大區路程最近的地點走一站，體力夠就趕路、
    不夠就步行（地圖擴充設計 3.4：陣營目標急的時候趕路；假人不疾行）。不是這種情況、走不過去、或現在不能
    安排前往（例如有事件待處理）就回傳 None，照平常挑選項。"""
    region = game.rally_region()
    if region is None:
        return None
    hop = next_hop(game, atlas.region_locations(game.content, region))
    if hop is None:
        return None
    ways = {option.mode: option for option in game.travel_options(hop) or []}
    for mode in ("hurry", "walk"):
        if mode in ways and ways[mode].enabled:
            return game.travel(hop, mode)
    return None


def _staying_for_the_battle(game: Game, battle_id: str, options: list[Option]) -> list[Option]:
    """已經參戰的假人在集結時不走出決戰的大區：集結時選單照常有前往（FB-009），但以前選單只有加入、假人一直待在
    現場，開打時人都在；區內站與站之間照常走。決戰不限地點時不用管。"""
    definition = game.content.battles.get(battle_id)
    region = definition.region if definition is not None else None
    if region is None:
        return options

    def leaves(option_id: str) -> bool:
        if not option_id.startswith("move:"):
            return False
        dest = atlas.region_of(game.content, option_id[len("move:"):].partition(":")[0])
        return dest is None or dest.id != region

    return [o for o in options if not leaves(o.id)]


def next_hop(game: Game, targets: list[str]) -> str | None:
    """從所在地往路程最近的目標走的下一站：照地圖連線走路程最短的路（地圖擴充設計 3.2）、跳過還沒開放的地點
    （不管摸清了沒）；已經在目標上或走不到時回傳 None。"""
    if game.state.player.location in targets:
        return None
    found = atlas.shortest_routes(game.state, game.content)
    reachable = [found[t] for t in targets if t in found and found[t].path]
    if not reachable:
        return None
    best = min(reachable, key=lambda route: (round(route.minutes, 6), len(route.path), route.path))
    return best.path[0]


def _toward_faction(game: Game, faction_id: str, ids: list[str]) -> str | None:
    """還沒投靠這一季效力的陣營：確認畫面就確認（不是自己的陣營就作罷）；在投靠點就投靠；
    不然往最近的投靠點走一站（走不過去就回傳 None）。"""
    p = game.state.player
    if p.pending_faction is not None:
        return "faction:confirm" if p.pending_faction == faction_id else "faction:cancel"
    if f"faction:{faction_id}" in ids:
        return f"faction:{faction_id}"
    hop = next_hop(game, game.content.scenario.faction(faction_id).join_at)
    return f"move:{hop}" if hop is not None and f"move:{hop}" in ids else None


def _battle_score(game: Game, arg: str) -> float | None:
    """集結或晚到時加入（一定站自己陣營那邊，引擎只給這個選項）；交戰中照自己每招的份量（乘這一場的氣血狀態）打分數，
    扣血相對剩下的氣血越重扣分越多（決戰改版一）；豪強的兩招同理（決戰改版五）：趁亂搶地盤用奇襲的份量、扣 35，保存實力用
    固守的份量的一半、扣 10，所以血多時搶地盤、血少了保存實力。沒有招的選項一律 0。
    沒有快照（份量全 0）時只剩扣血的差別，損耗最低的固守（豪強是保存實力）分數最高。"""
    kind, _, tag = arg.partition(":")
    if kind in ("join", "join_late"):
        return JOIN_BATTLE_SCORE
    if kind != "act":
        return None
    battle = game.world.get_battle()
    definition = game.content.battles[battle.battle_id]
    me = battle.participants.get(game.state.player.name)
    if me is None:
        return 0.0
    tuning = game.content.config.battle
    hp = max(me.neili, 1.0)
    if tag in (battle_instance.THIRD_GRAB, battle_instance.THIRD_KEEP):  # 豪強的兩招：只有站第三方的人才有（官軍黃巾的選單上沒有）
        if not battle_instance.is_third(definition, me):
            return 0.0
        grab = tag == battle_instance.THIRD_GRAB
        move = "奇襲" if grab else "固守"
        gain = me.scores.get(move, 0.0) * battle_instance.condition(me) * (1.0 if grab else tuning.third_keep_share)
        return gain / 100 - (tuning.third_grab_damage if grab else tuning.third_keep_damage) / hp
    option = battle_instance.option_of(definition, battle.act_index, me.faction, tag)
    if option is None or option.move is None:  # 放手一搏等沒有招的：假人不選（free_text 本來就排除）
        return 0.0
    return me.scores.get(option.move, 0.0) * battle_instance.condition(me) / 100 - tuning.damage[option.move] / hp


def _goals(game: Game, profile: BotProfile) -> dict[str, int]:
    faction_id = game.state.player.faction or profile.faction
    if faction_id is None:
        return {}
    return rules.resolve_goals(game.content, game.state.world, game.content.scenario.faction(faction_id).goals)  # 開關關著時三條戰線都算黃巾聲勢


def _home(game: Game, profile: BotProfile) -> set[str]:
    """陣營的地盤（假人往這一帶走）。第一季濃縮版（開關開著）：己方輸得最多的那條戰線上的所有地點（第一季設計
    第七節：假人照陣營目標往前線去）；陣營對戰線沒有目標（豪強）或開關關著時：投靠點與相鄰的地點。"""
    faction_id = game.state.player.faction or profile.faction
    if faction_id is None:
        return set()
    front = _losing_front(game, faction_id)
    if front is not None:
        return set(_front_locations(game.content, front))
    join_at = game.content.scenario.faction(faction_id).join_at
    return set(join_at) | {n for loc_id in join_at for n in game.content.locations[loc_id].connections}


def _front_locations(content: Content, front: str) -> list[str]:
    """這條戰線上的所有地點（照內容檔的順序）。"""
    return [loc_id for loc_id in content.locations if rules.front_of(content, loc_id) == front]


def _front_hop(game: Game, profile: BotProfile) -> str | None:
    """第一季濃縮版：假人還沒到己方輸得最多的那條戰線上，往那條戰線路程最近的地點走的下一站（鄰居裡沒有戰線上的地點時，
    光看「目的地在不在地盤」沒有方向，會亂走）；已經在戰線上、走不到、沒有這種戰線（開關關著、豪強、散人）時是 None。"""
    faction_id = game.state.player.faction or profile.faction
    front = _losing_front(game, faction_id) if faction_id is not None else None
    return None if front is None else next_hop(game, _front_locations(game.content, front))


def _losing_front(game: Game, faction_id: str) -> str | None:
    """己方輸得最多的戰線：目標是壓低（官軍）就挑戰況最高的、推高（黃巾）就挑最低的，同分取劇本排前面的。
    開關關著、或這個陣營對戰線沒有目標時是 None。"""
    content = game.content
    if not rules.season_one(content, game.state.world):
        return None
    goals = game.content.scenario.faction(faction_id).goals
    fronts = [front for front in rules.front_ids(content) if goals.get(front)]
    if not fronts:
        return None
    return max(fronts, key=lambda front: -goals[front] * rules.trend_value(game.state, content, front))


def _summons_hop(game: Game) -> str | None:
    """往召見的地點，路程最近的那一站；沒有召見、已經在、走不到時是 None（計畫 T5）。"""
    summons = game.state.player.summons
    return next_hop(game, [summons.location]) if summons is not None else None


def _order_hop(game: Game) -> str | None:
    """往這週軍令要去的地方，路程最近的那一站；已經在、沒有軍令、走不到時是 None（計畫 T6）。"""
    places = orders.targets(game.state, game.content, game.state.player.faction)
    return next_hop(game, places) if places else None
