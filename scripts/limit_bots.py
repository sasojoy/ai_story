"""極限假人（企劃者 2026-11-11「假人要對於各種狀態去測試我們功能的極限，才能做出真正的平衡」；11/12 定：陪玩假人不混極端玩法、
模型評分用固定分、「有問題」拿測試玩家的進度對比）。設計稿 https://claude.ai/artifact/8dTN9XbvR2Vr9FX1fCcxbM。

一個極限假人一個世界：正式內容、伺服器假人照常補人（普通玩家的那一群），再放一個「只追一件事」的角色，現實時鐘 1:1 跑完整季，
每一個遊戲日量一次身家（scripts/limit_metrics.py，測試玩家用同一支），季末在同一個世界裡跟每個普通假人用擂台打一輪（同 balance_matrix）。
極限假人只走 Game 的公開行動（跟真人按鈕同一條路，bot_policy.take_turn），不改任何規則：做法是替 bot_policy 的打分數加一層
「只追這一件」的偏好（boost／damp），強度旋鈕拉滿（永遠挑最高分），每天在線 hours 個鐘頭、每 tick 動一下。
跟人物說話要模型評分：照 Joy「可以都固定分」，交情那幾條用固定的三個話題分類（--talk loose|mid|strict）頂替模型，挑情誼最多的那一句。

只量不改；整季要跑好幾分鐘，不進平常的整套（tests/season/test_limit_bots.py 是 slow）。
執行：python scripts/limit_bots.py --profile week7 --focus all --seeds 1 2 --out <資料夾>
     （--jobs 4 平行；結果每個（設定, 極限假人, 種子）一個 json，scripts/limit_report.py 合成報告）
"""
from __future__ import annotations

import argparse
import io
import json
import os
import random
import shutil
import statistics
import sys
import tempfile
import time
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from contextlib import ExitStack
from dataclasses import dataclass, field
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from limit_metrics import snapshot  # noqa: E402
from tianxia import bot, bot_base, bot_policy, database, naming, server_bots, tactics, team  # noqa: E402
from tianxia.bot_runner import BotRunner  # noqa: E402
from tianxia.characters import open_characters  # noqa: E402
from tianxia.content import load_content  # noqa: E402
from tianxia.engine import Game  # noqa: E402
from tianxia.features.bout import arena_actions  # noqa: E402
from tianxia.features.bout import arena_rules as arena  # noqa: E402
from tianxia.features.companions import companion_agent  # noqa: E402
from tianxia.features.peers import bots as peer_bots  # noqa: E402
from tianxia.features.peers import raid_actions  # noqa: E402
from tianxia.core import bounty_base  # noqa: E402
from tianxia.models import AFFINITY_TAG_DELTAS, MOVES  # noqa: E402
from tianxia.sqlite_world import open_world  # noqa: E402
from tianxia.state import ArenaFight, BotProfile  # noqa: E402

START = 1_791_198_000.0  # 2026-10-05 19:00 台灣時間（同 sim_server_bots）
DAY = 86400.0
TZ = 8 * 3600
WIN = {"大勝", "險勝"}
MAX_REAL_DAYS = 30
HUNT_FROM = 15  # 專截殺幾級起才去找人
HUNT_SHARE = 0.25


@dataclass(frozen=True)
class Focus:
    """一個極限假人：label 給人看；boost 是「選項 id 前綴 → 加幾分」（只加在原本會按的選項上，force 裡的前綴原本不按也照加）；
    damp 的前綴分數打兩成（不是不按：該走的路、該療的傷照舊）；hours 每天在線幾小時；raid 是不是專截殺；talk 要不要跟人物說話；
    smith 路過城鎮就把鐵匠鋪的事做完（含淬煉）。"""

    label: str
    boost: dict[str, float] = field(default_factory=dict)
    force: tuple[str, ...] = ()
    damp: tuple[str, ...] = ()
    hours: float = 8.0
    raid: bool = False
    talk: bool = False
    smith: bool = False
    arts_every_turn: bool = False
    fixed: dict[str, float | None] = field(default_factory=dict)  # 前綴 → 直接給這個分數（None＝不按）；比 boost 先看，最長的前綴優先
    guard_pick: bool = False  # 親衛那一件事攤開了：挑情分漲最多的做法（真人追滿專長就這麼挑）
    smith_silver: int = 0  # smith 開著時，身上銀兩到這麼多才進鐵匠鋪（不然整天卡在鋪子裡、沒錢也沒出門賺）


FIGHT = {"act:train": 25.0, "act:explore": 18.0, "act:challenge": 22.0}
SHOPS = ("act:tavern", "act:market", "act:dadian", "act:arena", "act:socialize", "act:smith", "guard:", "act:donate")
FOCUSES: dict[str, Focus] = {
    "control": Focus("對照組（普通打分、永遠挑最好的、同樣在線）"),
    "level": Focus("練級狂", boost=FIGHT, damp=SHOPS),
    "insight": Focus("意境狂", boost={"sense": 40.0, "act:explore": 20.0, "learn": 15.0}, damp=("act:tavern", "act:market", "act:dadian", "act:arena"),
                     arts_every_turn=True),
    "friend": Focus("交情狂", boost={"act:socialize": 30.0, "call:": 30.0, "feast": 20.0, "errand:deliver": 25.0, "errand:scout": 25.0},
                    force=("act:socialize", "call:", "errand:deliver", "errand:scout"), damp=("act:arena", "act:dadian", "act:market"), talk=True),
    "silver": Focus("財神", boost={"act:explore": 15.0, "bounty": 20.0, "act:bounties": 20.0, "act:smith": 10.0},
                    damp=("act:tavern", "act:dadian", "act:arena"), smith=True, smith_silver=300),
    "raid": Focus("截殺狂", damp=("act:tavern", "act:dadian", "act:arena", "act:socialize"), raid=True),
    "merit": Focus("功勞狂", boost={"act:duty": 30.0, "act:train": 25.0, "act:convoy": 30.0, "act:summons": 30.0, "act:rank2": 25.0,
                                   "bounty": 20.0, "act:bounties": 20.0}, damp=("act:tavern", "act:dadian", "act:arena", "act:market")),
    # 親衛：做法挑情分漲最多的那一顆（_guard_pick）、每天教、求學去處照假人的偏好；放著、離開、以後再說不按
    "guard": Focus("親衛狂", boost={"act:explore": 15.0}, damp=("act:tavern", "act:dadian", "act:arena"),
                   fixed={"guard:teach": 45.0, "guard:leave": None, "guard:part": None,
                          "guard:later": None, "guard:stay": None}, guard_pick=True),
    # 疊起來的三條
    "strongest": Focus("最強戰力（意境＋打造＋親衛＋練級）", boost={**FIGHT, "sense": 30.0, "act:smith": 10.0},
                       damp=("act:tavern", "act:dadian", "act:market"), smith=True, smith_silver=300, arts_every_turn=True,
                       fixed={"guard:leave": None, "guard:part": None, "guard:later": None}, guard_pick=True),
    "grinder": Focus("肝帝（普通玩法、每天 16 小時）", hours=16.0),
    "overlord": Focus("霸主（功勞＋截殺＋交情）", boost={"act:duty": 25.0, "act:train": 25.0, "act:convoy": 25.0, "act:socialize": 20.0,
                                                      "call:": 20.0, "bounty": 15.0}, force=("call:",), raid=True, talk=True, hours=12.0),
}

# 固定分的話題分類（Joy 11/12「模型評分另外測，可以都固定分」）：三句話各歸一類，假人挑情誼最多的那一句
TALK_TIERS: dict[str, tuple[str, str, str]] = {
    "loose": ("雪中送炭", "坦誠相待", "真誠請教"),
    "mid": ("由衷讚賞", "尋常寒暄", "真誠請教"),
    "strict": ("尋常寒暄", "冷漠敷衍", "由衷讚賞"),
}


class Driver:
    """一個極限假人的身分與這一季的量測。"""

    def __init__(self, focus: Focus, talk_tier: str, seed: int):
        self.focus = focus
        self.tier = TALK_TIERS[talk_tier]
        self.rng = random.Random(seed + 7000)
        self.curve: list[dict] = []
        self.raids = Counter()
        self.turns = 0
        self.errors = Counter()
        self.hunt: Counter | None = None  # 專截殺：此刻每個地點站著幾個人（量測這一邊每一輪重算）
        self.unstuck = Counter()  # 打分數挑不出來、改照真人或整季機器人按的次數（照前綴）

    def online(self, now: float) -> bool:
        """每天從台灣早上 9 點起連著在線 hours 個鐘頭。"""
        hour = ((now + TZ) % DAY) / 3600
        return 9.0 <= hour < 9.0 + self.focus.hours if self.focus.hours < 24 else True


def _matches(option_id: str, prefixes) -> str | None:
    return next((p for p in prefixes if option_id.startswith(p)), None)


def _focused_score(real, focus: Focus):
    fixed = sorted(focus.fixed, key=len, reverse=True)

    def score(game, option, profile):
        hit = next((p for p in fixed if option.id.startswith(p)), None)
        if hit is not None:
            return focus.fixed[hit]
        value = real(game, option, profile)
        hit = _matches(option.id, focus.boost)
        if hit is not None and (value is not None or _matches(option.id, focus.force)):
            return (value or 0.0) + focus.boost[hit]
        if value is not None and _matches(option.id, focus.damp) and not option.id.startswith("move:"):
            return value * 0.2
        return value
    return score


def _fixed_turn(tier):
    """頂替模型的一輪對話：三句固定的話、三個固定的分類（tier），心意與性子填「沒有」。"""
    def generate_turn(client, messages, required=(), stances=(), persona=()):
        model = companion_agent.turn_model(stances, persona) if (stances or persona) else companion_agent.CompanionTurn
        data = {"narrative": "他點點頭，跟你聊了幾句。", "options": ["談兵", "問安", "請教"], "option_tags": list(tier),
                "relationship_note_update": None, "talk_memo": "聊了幾句"}
        if stances:
            data["stance"] = "none"
        if persona:
            data["persona"] = persona[-1]
        return model.model_validate(data)
    return generate_turn


def _talk(game: Game, driver: Driver) -> list[str] | None:
    """正在跟人物說話：挑情誼最多的那一句；今天長不了情誼了就告辭。"""
    p = game.state.player
    cid = p.pending_companion
    if cid is None:
        return None
    ids = {o.id for o in game.options(odds=False, tick=False) if o.enabled}
    _, tags = companion_agent.offered(game.state, cid)
    if game._talk_idle(cid) or not tags:
        return game.choose("talk:leave")
    best = max(range(len(tags)), key=lambda i: AFFINITY_TAG_DELTAS.get(tags[i], 0))
    return game.choose(f"talk:{best}") if f"talk:{best}" in ids else game.choose("talk:leave")


def _turn(game: Game, profile: BotProfile, driver: Driver) -> None:
    focus = driver.focus
    bot.take_pill(game)
    if focus.talk and game.state.player.pending_companion is not None:
        _talk(game, driver)
        return
    if focus.raid and driver.hunt is not None and _hunt(game, driver):
        return
    if focus.guard_pick and _guard_pick(game, driver.rng):
        return
    if focus.smith and game.state.player.stats.get("silver", 0) >= focus.smith_silver:
        bot.visit_smith(game)  # 兵器頁、防具頁的事做完再出門（含淬煉；整季機器人那一套）
    if focus.arts_every_turn:
        bot.forge_and_cultivate(game, driver.rng)
        bot.spend_xinde(game, driver.rng)
    slot = bot_base.NamingSlot(open=True, model=False)  # 有所感、首創、定名要取名：沒有 slot 的話停在有所感裡一整季
    msgs = bot_policy.take_turn(game, profile, driver.rng, slot)
    if slot.job is not None:
        bot_policy.apply_job(game, slot.job, _fake_name(game, slot.job))
    elif not msgs and game.state.player.journey is None:
        _unstick(game, driver)


def _unstick(game: Game, driver: Driver) -> None:
    """伺服器假人碰不到、只有真人才會冒出來的那幾件（例：主線的答題 story:，假人不打分數）：照真人一樣答一題；
    其餘照整季機器人隨機挑一顆（bot.pick）。真的沒事可做（體力不夠）什麼都不做。"""
    options = [o for o in game.options(odds=False, tick=False) if o.enabled]
    answers = [o.id for o in options if o.id.startswith("story:") and not o.id.endswith(":later")]
    if answers:
        driver.unstuck["story"] += 1
        game.choose(driver.rng.choice(answers))
        return
    if options and all(o.id.startswith(("road:", "act:rest")) for o in options):
        return
    choice = bot.pick(game, options, driver.rng) if options else None
    if choice:
        driver.unstuck[choice.split(":")[0]] += 1
        game.choose(choice)


def _fake_name(game: Game, job):
    """取名的 B 段不叫模型（同 sim_server_bots 的假取名）：有候選挑第一個，要新名字照字表組；有所感照沒有模型的路（C 段走退路字表）。"""
    if isinstance(job, bot_base.SenseJob):
        return None, ""
    request = job.request
    if getattr(request, "choices", None):
        return request.choices[0], ""
    return naming.fallback_name(game.content, f"極限|{request.key}", request.name_kind, salt=game.state.player.sense_serial), ""


def _hunt(game: Game, driver: Driver) -> bool:
    """專截殺：此地沒有截得了的人時，往「此刻最多人站著的野地」走一步（真人會挑人多的要道蹲）。
    人在哪只拿來挑去處（driver.hunt 是量測這一邊給的、每一輪重算的人數表），動手照舊走 bot_policy 的 _raid（玩家卡同一條路）。"""
    if game.state.player.journey is not None:
        return False
    here_targets = [name for name, odds in raid_actions.targets(game) if odds in ("穩勝", "有把握", "五五波")]
    if here_targets and game.state.player.stamina >= game.content.config.raid.stamina:
        from tianxia.features.peers import actions as peer_actions
        peer_actions.peer_act(game, here_targets[0], "raid")  # 玩家卡上那一顆（真人看到勝算五五波以上就動手）
        return True
    if raid_actions.targets(game):
        return False
    if game.state.player.member.level < HUNT_FROM or driver.rng.random() >= HUNT_SHARE:
        return False  # 新手期截不了人（也不能被截）：先練起來；之後四分之一的輪往人多的地方去，其餘照常練
    here = game.state.player.location
    spots = [loc for loc, _ in driver.hunt.most_common() if loc != here and not bounty_base.is_town(game.content, loc)]
    if not spots:
        return False
    hop = bot_base.next_hop(game, spots[:1])
    ids = {o.id for o in game.options(odds=False, tick=False) if o.enabled}
    if hop is None or f"move:{hop}" not in ids:
        return False
    driver.raids["往人多的野地"] += 1
    game.choose(f"move:{hop}")
    return True


def _guard_pick(game: Game, rng) -> bool:
    """親衛隊長那一頁（真人在網頁上按的那幾顆，不在此地可為；伺服器假人從選單上按，極限假人是真人身分、選單上沒有）：
    攤開眼前那一件、做法挑情分漲最多的那一顆（引擎夾過的數字就在做法上，畫面上看不到，真人靠試）、每天教一樣、長大了送去求學。"""
    from tianxia.features.guard import actions as guard_actions
    b = getattr(game.state.player, "guard", None)
    if b is None or b.stage in ("met", "saved", "left"):
        return False  # 撞見、救不救、收不收在選單上，take_turn 會按
    ctx = game
    if not guard_actions._free(ctx):
        return False  # 眼前有事（在路上、事件攤開著）：那一頁的鈕按了也是「沒有這回事」，先照常把眼前的事做完
    if b.event is not None and not b.event.shown and b.stage in guard_actions.EVENT_STAGES:
        return bool(game.choose("guard:open"))
    if b.event is not None and b.event.shown and b.event.choices:
        best = max(range(len(b.event.choices)), key=lambda i: b.event.choices[i].qing)
        return bool(game.choose(f"guard:pick:{best}"))
    if b.stage == "grow" and b.picking:
        picks = [x for x in guard_actions._school_picks(ctx, b) if x["enabled"]]
        return bool(game.choose(rng.choice(picks)["id"] if picks else "guard:stay"))
    if guard_actions._can_study(ctx, b):
        return bool(game.choose("guard:study"))
    lessons = guard_actions._lessons(ctx, b)
    if lessons:
        game.choose(rng.choice(lessons)["id"])
        return False  # 教一樣不花體力：照樣出門
    return False


def _record_raids(driver: Driver, me: str):
    real = Game._raid_record

    def record(self, result, rival, rival_power, rival_game, spoils, *, attacker, **kw):
        if self.state.player.name == me:
            driver.raids["打" if attacker else "被打"] += 1
            if attacker and spoils is not None and spoils.winner == me:
                driver.raids["搶到銀兩"] += spoils.lost
        return real(self, result, rival, rival_power, rival_game, spoils, attacker=attacker, **kw)
    return record


# ── 季末擂台（同 scripts/balance_matrix.py 的 fight／share：真的擂台快照、本命戰法、照分身的出招法）──
def _fight(a: Game, b: Game, rng: random.Random) -> str:
    c = a.content
    me, foe = arena_actions.arena_side(a), arena_actions.arena_side(b)
    f = ArenaFight(id=1, foe_key="b", me=me, foe=foe, rounds=c.config.arena.rounds, edge=c.config.duel.start)
    arena_actions.faced(c, f.me, f.foe)
    f.bout = tactics.open_bout(team.self_side(a.state, c, a.world), team.self_side(b.state, c, b.world), "你", b.state.player.name, pvp=True)
    cfg = c.config.arena
    while True:
        arena.roll_next(f, rng, cfg, c.config.duel)
        values = [max(0.0, f.me.scores.get(m, 0.0)) for m in MOVES]
        top = max(values) or 1.0
        move = rng.choices(MOVES, weights=[(v / top) ** cfg.proxy_power for v in values])[0]
        banned = tactics.locks(f.bout).no_moves
        if move in banned:
            move = next((m for m in MOVES if m not in banned), move)
        arena.exchange_full(f, move, c, rng, rng)
        f.round += 1
        tier = arena.verdict(f, c.config.duel)
        if tier is not None:
            return tier


def share(a: Game, b: Game, n: int, seed: int) -> float:
    """a 對 b 的贏面：a 挑 b 一半、b 挑 a 一半（同 balance_matrix.share）。"""
    rng = random.Random(seed)
    won = 0
    for i in range(n):
        won += (_fight(a, b, rng) in WIN) if i % 2 == 0 else (_fight(b, a, rng) == "落敗")
    return won / n


def _vs_benming(content, me: Game, n: int, seed: int, driver: Driver) -> float | None:
    """季末的它對「本命」（scripts/balance_matrix 的「絕學」那一套：關羽的武學、董卓的內功，均衡配點，同等級）的擂台贏面。
    企劃者的目標是本命對最強玩家配置 50～52%：這裡印的是極限假人那一邊的贏面，48～50% 就是在目標裡。"""
    try:
        with mock.patch.object(io, "TextIOWrapper", lambda *a, **k: sys.stdout):  # balance_matrix 一 import 就換 stdout，別讓它關掉這一份
            import balance_matrix as bm  # noqa: PLC0415
        rival = bm.make(content, bm.Kit(content), "均衡", "絕學", me.state.player.member.level, [seed * 1000])
        return share(me, rival, n, seed + 77)
    except Exception as exc:  # 組不起來（例：內容改了名字）就不印，報告寫「—」
        driver.errors[f"本命:{type(exc).__name__}"] += 1
        return None


def _bots_row(states) -> dict:
    """普通假人（伺服器假人）這一刻：每一欄的中位數與最高。"""
    snaps = [snapshot(s) for s in states]
    if not snaps:
        return {}
    return {k: {"median": statistics.median(x[k] for x in snaps), "max": max(x[k] for x in snaps)} for k in snaps[0]}


def run_one(profile: str, focus_key: str, seed: int, tick: float, talk_tier: str, fights: int, acts: int = 4) -> dict:
    focus = FOCUSES[focus_key]
    content = load_content(ROOT / "content", profile=profile)
    content.config.time_scale = 1.0
    content.config.bot_tick_seconds = tick
    workdir = Path(tempfile.mkdtemp(prefix="limit-"))
    db_path = workdir / "tianxia.db"
    world, characters = open_world(db_path), open_characters(db_path)
    now = [START]
    driver = Driver(focus, talk_tier, seed)
    name = "極限甲"
    faction = ("guan", "huang")[seed % 2]
    prof = BotProfile(personality="積極", seed=seed + 9000, faction=faction, season_number=1)
    real_score, real_strength = bot_policy.score, server_bots.strength
    focused = _focused_score(real_score, focus)
    in_focus = [False]
    t0 = time.time()
    with ExitStack() as stack:
        stack.enter_context(mock.patch.dict(os.environ, {database.ENV_VAR: str(db_path)}))
        stack.enter_context(mock.patch.object(bot_policy, "score", lambda g, o, p: (focused if in_focus[0] else real_score)(g, o, p)))
        stack.enter_context(mock.patch.object(server_bots, "strength", lambda cfg, p: 1.0 if in_focus[0] else real_strength(cfg, p)))
        stack.enter_context(mock.patch.object(Game, "_raid_record", _record_raids(driver, name)))
        if focus.raid:
            stack.enter_context(mock.patch.object(peer_bots, "RAID_ODDS", ("穩勝", "有把握", "五五波")))
        if focus.talk:
            stack.enter_context(mock.patch.object(companion_agent, "generate_turn", _fixed_turn(driver.tier)))
        world.seed_first_season(content)
        world.open_season(content, now[0])
        me = Game.new(content, name, rng=random.Random(seed + 3000), world=world)
        me.client = None
        characters.save(me.state)
        runner = BotRunner(content, world, characters, random.Random(seed + 1000), clock=lambda: now[0], client=None)
        next_day = 1
        while not world.get_season().ended and now[0] - START < MAX_REAL_DAYS * DAY:
            runner.tick()
            if driver.online(now[0]):
                if focus.raid:
                    driver.hunt = Counter(s.player.location for s in characters.all() if s.player.name != name and s.player.journey is None)
                with world.action_lock():
                    state = characters.load(name)
                    game = Game(content, state, me.rng, world)
                    game.client = None
                    game.sync(now[0])
                    if not game.state.world.ended:
                        in_focus[0] = True
                        try:
                            with mock.patch.object(peer_bots, "RAID_CHANCE", 1.0) if focus.raid else ExitStack():
                                for _ in range(acts):  # 真人體力夠就一直按：一輪最多按 acts 下，在路上就停（路上的時間照走）
                                    if game.state.player.journey is not None or game.state.world.ended:
                                        break
                                    _turn(game, prof, driver)
                                    driver.turns += 1
                        except Exception as exc:  # 一步出錯不讓整季倒下（同 bot_runner）：記種類，報告上寫
                            driver.errors[type(exc).__name__] += 1
                        finally:
                            in_focus[0] = False
                    characters.save(game.state)
            season_day = world.get_season().time / DAY
            if season_day >= next_day:
                state = characters.load(name)
                bots = characters.all(bots_only=True)
                driver.curve.append({"day": next_day, "me": snapshot(state), "bots": _bots_row(bots)})
                next_day += 1
            now[0] += tick
        season = world.get_season()
        state = characters.load(name)
        final_me = Game(content, state, random.Random(1), world)
        bots = [s for s in characters.all(bots_only=True) if s.player.member.level > 1]
        vs = []
        for i, b in enumerate(bots):
            try:
                vs.append(share(final_me, Game(content, b, random.Random(1), world), fights, seed * 100 + i))
            except Exception as exc:  # 擂台快照組不起來（例：沒有武學）的那一位跳過
                driver.errors[f"擂台:{type(exc).__name__}"] += 1
        final = snapshot(state)
        bots_final = _bots_row(bots)
        benming = _vs_benming(content, final_me, fights * 2, seed, driver)
    database.close_all()
    shutil.rmtree(workdir, ignore_errors=True)
    return {
        "profile": profile, "focus": focus_key, "label": focus.label, "seed": seed, "talk": talk_tier, "hours": focus.hours, "acts": acts,
        "season_days": season.time / DAY, "ended": season.ended, "ending": season.ending_title, "faction": faction,
        "turns": driver.turns, "errors": dict(driver.errors), "unstuck": dict(driver.unstuck), "raids": dict(driver.raids),
        "curve": driver.curve, "final": final, "bots_final": bots_final, "bots": len(bots),
        "vs_benming": benming,
        "arena_vs_bots": {"mean": statistics.mean(vs) if vs else None, "min": min(vs) if vs else None, "max": max(vs) if vs else None, "n": len(vs)},
        "seconds": round(time.time() - t0),
    }


def _job(args):
    profile, focus, seed, tick, talk, fights, acts, out = args
    try:
        result = run_one(profile, focus, seed, tick, talk, fights, acts)
    except Exception as exc:
        result = {"profile": profile, "focus": focus, "seed": seed, "crash": repr(exc)}
    path = Path(out) / f"{profile}-{focus}-{seed}.json"
    path.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    return path.name, result.get("seconds"), result.get("crash")


def main() -> None:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", nargs="+", default=["week7"])
    parser.add_argument("--focus", nargs="+", default=["all"])
    parser.add_argument("--seeds", type=int, nargs="+", default=[1, 2])
    parser.add_argument("--tick", type=float, default=120.0, help="假時鐘每一輪走幾秒（極限假人每一輪動一下）")
    parser.add_argument("--talk", default="loose", choices=sorted(TALK_TIERS), help="跟人物說話的固定分：寬鬆、普通、嚴格")
    parser.add_argument("--fights", type=int, default=60, help="季末對每個普通假人打幾場擂台")
    parser.add_argument("--acts", type=int, default=4, help="極限假人每一輪最多按幾下（真人體力夠就一直按）")
    parser.add_argument("--jobs", type=int, default=1)
    parser.add_argument("--out", default=str(ROOT / ".local" / "limit"))
    args = parser.parse_args()
    focuses = list(FOCUSES) if args.focus == ["all"] else args.focus
    Path(args.out).mkdir(parents=True, exist_ok=True)
    jobs = [(p, f, s, args.tick, args.talk, args.fights, args.acts, args.out) for p in args.profile for f in focuses for s in args.seeds]
    if args.jobs > 1:
        with ProcessPoolExecutor(args.jobs) as pool:
            for name, secs, crash in pool.map(_job, jobs):
                print(name, secs, crash or "", flush=True)
    else:
        for job in jobs:
            print(*_job(job), flush=True)


if __name__ == "__main__":
    main()
