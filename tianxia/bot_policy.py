"""伺服器假人的行為（伺服器假人設計第七節）：照陣營目標替選項打分數，強度旋鈕決定多常挑最高分。

只透過 engine.Game 的公開行動（choose／create_skill／practice／heal）做事，跟真人按按鈕走同一條
路；不接 LLM（呼叫端把 game.client 設成 None）。全服戰鬥裡假人是一般參戰者，每回合從固定戰法裡挑，
不寫自由文字。
"""
from __future__ import annotations

import random

from . import atlas, rules, server_bots
from .bot import wants_heal
from .engine import FREE_TEXT_OPTION, Game, Option
from .models import Content, Effect, FactionDef
from .state import BotProfile

REWARD_STATS = ("str", "agi", "con", "wis", "silver", "fame", "xinde")
TREND_WEIGHT = 10.0  # 推大勢一點，抵得過十點獎勵
JOIN_BATTLE_SCORE = 100.0
ACT_SCORES = {"explore": 1.0, "socialize": 0.8}
TRAIN_SCORE = 0.6  # 遊歷本身的分數（低於探索）；對自己陣營有利的地點再加上大勢分
HOME_MOVE_SCORE = 0.3  # 往自己陣營的地盤走（投靠點一帶；第一季濃縮版是輸得最多的那條戰線，離得還遠時是往那邊的下一站）
AWAY_MOVE_SCORE = 0.1
TRAIN_MOVE_SCORE = 0.5  # 往「遊歷對自己陣營有利」的地點走，額外加分
PRACTICE_CHANCE = 0.2  # 每次行動順便鍛鍊一門的機率（練功不花心得，不能每次都練）
SKILL_NAME_TRIES = 5


def take_turn(game: Game, profile: BotProfile, rng: random.Random) -> list[str]:
    """做一個動作（外加不受強度影響的照顧動作）；沒有能做的事（例如體力不夠）就什麼都不做，回傳空清單。
    在路上的假人這一輪跳過，連照顧動作都不做（地圖擴充設計 3.4）。"""
    game.options(odds=False)  # 每一輪先替全服戰鬥追趕一次時間（集結截止、回合逾時），跟真人的畫面刷新一樣；在路上、趕路的假人也不例外
    if game.state.player.journey is not None:
        return []
    look_after(game, rng)
    s = game.state
    if s.player.pending_companion:
        return game.choose("talk:leave")
    rally = _toward_battle(game)
    if rally is not None:
        return rally
    options = [  # road: 開頭的是路上的選項：假人不改道、不做路上小事（路上設計 3.5）
        o for o in game.options(odds=False, tick=False)
        if o.enabled and o.id not in ("act:rest", "act:halt", FREE_TEXT_OPTION) and not o.id.startswith("road:")
    ]
    if not options:
        return []
    ids = [o.id for o in options]
    battle = game.world.get_battle()
    if battle is not None and s.player.name not in battle.participants:
        join = next((i for i in ids if i.startswith("battle:join")), None)
        if join is not None:  # 集結時選單照常有別的事可做（FB-009）；假人一看到加入就加入，不交給強度旋鈕碰運氣
            return game.choose(join)
    elif battle is not None and battle.phase == "muster":
        # 已經參戰：不換邊（不分陣營的劇本集結時還看得到另一邊的加入），也不走出決戰的大區
        options = [o for o in _staying_for_the_battle(game, battle.battle_id, options) if not o.id.startswith("battle:join")]
        if not options:
            return []
        ids = [o.id for o in options]
    if s.player.faction is None and profile.faction is not None and not s.pending_event \
            and not any(i.startswith("battle:") for i in ids):
        step = _toward_faction(game, profile.faction, ids)
        if step is not None:
            return game.choose(step)
    choice = pick(game, options, profile, rng)
    return game.choose(choice) if choice else []


def look_after(game: Game, rng: random.Random) -> None:
    """照顧動作（不受強度旋鈕影響）：有內傷先療傷；沒學過的功法先自創（取一個像樣的名字），
    學過的偶爾鍛鍊一成。"""
    if wants_heal(game):
        game.heal()
    for kind, slot in (("內功", "neigong_id"), ("武學", "wugong_id")):
        if getattr(game.state.player.member, slot) is None:
            for _ in range(SKILL_NAME_TRIES):
                game.create_skill(server_bots.make_skill_name(rng, kind), kind)
                if getattr(game.state.player.member, slot) is not None:
                    break
        elif rng.random() < PRACTICE_CHANCE:
            game.practice(kind)


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
    """選項的分數；None＝假人不會選（別的陣營的投靠、閒聊或求見大勢人物、只會被擋在門外的交友、投靠的確認畫面另外處理）。"""
    kind, _, arg = option.id.partition(":")
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
        return 0.0 if arg == "back" else None  # 假人不求見大勢人物（不呼叫模型）；萬一停在求見選單上，只會按返回
    if kind == "move":
        base = HOME_MOVE_SCORE if arg == _front_hop(game, profile) or arg in _home(game, profile) else AWAY_MOVE_SCORE
        return base + (TRAIN_MOVE_SCORE if _train_value(game, profile, arg) > 0 else 0.0)
    if kind == "act":
        if arg == "call":
            return None
        if arg == "socialize" and (game.socialize_starts_dialogue() or game.socialize_is_futile()):
            return None
        if arg == "train":
            return TRAIN_SCORE + _train_value(game, profile)
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
    hop = next_hop(game, _faction(game, faction_id).join_at)
    return f"move:{hop}" if hop is not None and f"move:{hop}" in ids else None


def _battle_score(game: Game, arg: str) -> float | None:
    """集結或遲到時加入（一定站自己陣營那邊，引擎只給這個選項）；交戰中照戰法對自己這邊的推力打分數，
    同推力時氣血損耗少的優先。"""
    kind, _, tag = arg.partition(":")
    if kind in ("join", "join_late"):
        return JOIN_BATTLE_SCORE
    if kind != "act":
        return None
    battle = game.world.get_battle()
    definition = game.content.battles[battle.battle_id]
    effect = definition.action_tags.get(tag)
    if effect is None:
        return 0.0
    me = battle.participants.get(game.state.player.name)
    direction = 1 if me is not None and me.faction == definition.factions[0].id else -1
    return direction * effect.trend_delta - effect.neili_damage / 100


def _faction(game: Game, faction_id: str) -> FactionDef:
    return next(f for f in game.content.scenario.factions if f.id == faction_id)


def _goals(game: Game, profile: BotProfile) -> dict[str, int]:
    faction_id = game.state.player.faction or profile.faction
    if faction_id is None:
        return {}
    return rules.resolve_goals(game.content, game.state.world, _faction(game, faction_id).goals)  # 開關關著時三條戰線都算黃巾聲勢


def _home(game: Game, profile: BotProfile) -> set[str]:
    """陣營的地盤（假人往這一帶走）。第一季濃縮版（開關開著）：己方輸得最多的那條戰線上的所有地點（第一季設計
    第七節：假人照陣營目標往前線去）；陣營對戰線沒有目標（豪強）或開關關著時：投靠點與相鄰的地點。"""
    faction_id = game.state.player.faction or profile.faction
    if faction_id is None:
        return set()
    front = _losing_front(game, faction_id)
    if front is not None:
        return set(_front_locations(game.content, front))
    join_at = _faction(game, faction_id).join_at
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
    goals = _faction(game, faction_id).goals
    fronts = [front for front in rules.front_ids(content) if goals.get(front)]
    if not fronts:
        return None
    return max(fronts, key=lambda front: -goals[front] * rules.trend_value(game.state, content, front))
