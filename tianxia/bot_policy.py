"""伺服器假人的行為（伺服器假人設計第七節）：照陣營目標替選項打分數，強度旋鈕決定多常挑最高分。

只透過 engine.Game 的公開行動（choose／create_skill／practice／heal）做事，跟真人按按鈕走同一條
路；不接 LLM（呼叫端把 game.client 設成 None）。全服戰鬥裡假人是一般參戰者，每回合從固定戰法裡挑，
不寫自由文字。
"""
from __future__ import annotations

import random
from collections import deque

from . import server_bots
from .bot import wants_heal
from .engine import Game, Option
from .models import Effect, FactionDef
from .state import BotProfile

REWARD_STATS = ("str", "agi", "con", "wis", "silver", "fame", "xinde")
TREND_WEIGHT = 10.0  # 推大勢一點，抵得過十點獎勵
JOIN_BATTLE_SCORE = 100.0
ACT_SCORES = {"explore": 1.0, "socialize": 0.8}
TRAIN_SCORE = 0.6  # 歷練本身的分數（低於探索）；對自己陣營有利的地點再加上大勢分
HOME_MOVE_SCORE = 0.3  # 往自己陣營投靠點一帶走
AWAY_MOVE_SCORE = 0.1
TRAIN_MOVE_SCORE = 0.5  # 往「歷練對自己陣營有利」的地點走，額外加分
PRACTICE_CHANCE = 0.2  # 每次行動順便鍛鍊一門的機率（練功不花心得，不能每次都練）
SKILL_NAME_TRIES = 5


def take_turn(game: Game, profile: BotProfile, rng: random.Random) -> list[str]:
    """做一個動作（外加不受強度影響的照顧動作）；沒有能做的事（例如體力不夠）就什麼都不做，回傳空清單。"""
    look_after(game, rng)
    s = game.state
    if s.player.pending_companion:
        return game.choose("talk:leave")
    options = [o for o in game.options(odds=False) if o.enabled and o.id != "act:rest"]
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
    """選項的分數；None＝假人不會選（別的陣營的投靠、閒聊大勢人物、投靠的確認畫面另外處理）。"""
    kind, _, arg = option.id.partition(":")
    if kind == "battle":
        return _battle_score(game, arg)
    if kind == "choice":
        event = game.content.events[game.state.pending_event]
        return effect_score(event.choices[int(arg)].effect, _goals(game, profile))
    if kind == "talk":
        return 0.0 if arg == "leave" else None
    if kind == "move":
        base = HOME_MOVE_SCORE if arg in _home(game, profile) else AWAY_MOVE_SCORE
        return base + (TRAIN_MOVE_SCORE if _train_value(game, profile, arg) > 0 else 0.0)
    if kind == "act":
        if arg == "socialize" and game.socialize_starts_dialogue():
            return None
        if arg == "train":
            return TRAIN_SCORE + _train_value(game, profile)
        return ACT_SCORES.get(arg, 0.0)
    return None


def effect_score(effect: Effect, goals: dict[str, int]) -> float:
    """選項效果的分數：把大勢往陣營想要的方向推，一點抵十分；能力、心得、銀兩、名望等獎勵每點 0.1 分。"""
    push = sum(goals.get(trend_id, 0) * delta for trend_id, delta in effect.trend.items())
    reward = sum(max(0, effect.stats.get(key, 0)) for key in REWARD_STATS)
    return TREND_WEIGHT * push + reward / 10


def _train_value(game: Game, profile: BotProfile, loc_id: str | None = None) -> float:
    """在這個地點（預設所在地）歷練對自己陣營的大勢分（同 effect_score 的一點抵十分）。"""
    goals = _goals(game, profile)
    return TREND_WEIGHT * sum(goals.get(t, 0) * d for t, d in game.train_trend_push(loc_id).items())


def next_hop(game: Game, targets: list[str]) -> str | None:
    """從所在地往最近的目標走的下一站：照地圖連線、跳過還沒開放的地點（不管摸清了沒）；
    已經在目標上或走不到時回傳 None。"""
    s, c = game.state, game.content
    start = s.player.location
    if start in targets:
        return None
    first: dict[str, str] = {}
    seen = {start}
    queue = deque([start])
    while queue:
        here = queue.popleft()
        for nxt in c.locations[here].connections:
            loc = c.locations[nxt]
            if nxt in seen or (loc.unlock_flag and loc.unlock_flag not in s.world.flags):
                continue
            seen.add(nxt)
            first[nxt] = first.get(here, nxt)
            if nxt in targets:
                return first[nxt]
            queue.append(nxt)
    return None


def _toward_faction(game: Game, faction_id: str, ids: list[str]) -> str | None:
    """還沒投靠這一季效力的陣營：確認畫面就確認（不是自己的陣營就作罷）；在投靠點就投靠；
    不然往最近的投靠點走一站（體力不夠走不了就回傳 None）。"""
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
    return _faction(game, faction_id).goals


def _home(game: Game, profile: BotProfile) -> set[str]:
    """陣營的地盤：投靠點與相鄰的地點（第一季階段二有了戰線後改成往前線去）。"""
    faction_id = game.state.player.faction or profile.faction
    if faction_id is None:
        return set()
    join_at = _faction(game, faction_id).join_at
    return set(join_at) | {n for loc_id in join_at for n in game.content.locations[loc_id].connections}
