"""擂台賽（隨時挑擂；docs/superpowers/specs/2026-10-14-擂台賽-design.md）。Joy 2026-10-14：「我再想開一個擂台賽，讓他們可以報名，然後可以
對戰，但是如何對戰我還沒想好，因為很難兩個人都同時在線」，在選擇卡選了「隨時挑擂」：報名的人留下一份守擂的分身，別人隨時來挑，
對的是分身，照積分排名，只算本季。

- 守擂的人記在這一季的 WorldState.arena（名號鍵 → ArenaEntry）；換季整個重來。
- 一場（ArenaFight，挑的人身上）照頭目戰與奪璽單挑的純函式打：duel.push_of、harm_of、gamble_roll、verdict_at；分身的招照奪璽單挑的
  代打（份量的 proxy_power 次方加權），回合開始時擲好、給挑的人看一句架勢。兩邊的池子都從滿的開始，打完不扣回角色。
- 亂數全用自己的（「擂台|季|名號|場次|回合|用途」），不碰 Game.rng。
- 積分是 Elo（ArenaTuning.start_rating、k）：挑的人贏 1、僵持 0.5、輸 0，守的人反過來，兩邊一起改。

只算數字與句子、改傳進來的 ArenaFight 與 WorldState；付體力、戰報、江湖紀錄、補送在 Game（engine.py 的「擂台」那一段）。
"""
from __future__ import annotations

import random

from . import battle_instance
from . import duel as duel_rules
from .characters import name_key
from .models import MOVES, ArenaTuning, Content, DuelTuning
from .state import ArenaEntry, ArenaFight, ArenaSide, GameState, WorldState

DAY = 86400
WIN_TIERS = ("大勝", "險勝")
SCORES = {"大勝": 1.0, "險勝": 1.0, "僵持": 0.5, "落敗": 0.0}
FLIP = {"大勝": "落敗", "險勝": "落敗", "僵持": "僵持", "落敗": "險勝"}  # 守的人那一邊（挑的人落敗時守的人照氣勢再分，見 defender_tier）

# 待 joy 潤
ARENA = "擂台"
JOIN = "報名守擂（留下此刻的身手當分身）"
UPDATE = "更新守擂分身（換成此刻的身手）"
BACK = "返回"
YIELD = "認輸下台（算落敗）"
NO_ARTS = "你身上還沒有武學，上不了擂台。"
JOINED = "你在擂台登記了名號，留下一份分身守擂：{arts}。別人隨時可以來挑。"
UPDATED = "你換了一份守擂的分身：{arts}。積分與戰績照舊。"
JOIN_FIRST = "先報名守擂"
COOLING = "剛挑過，過一陣子再來"
PROTECTED = "今天已守滿 {n} 場"
TIRED = "體力不夠"
MORE = "還有 {n} 人守擂，打完一場再看"
NOBODY = "擂台上還沒有別人守擂。"
OPENING = "{foe}的分身跳上擂台，抱拳道：「請。」"
FOE_ARTS = "他守擂用的是{arts}。"
TELL_NOTE = "（架勢不一定是真的。）"
HOWTO = "固守剋強攻、強攻剋奇襲、奇襲剋固守；也可以在下面寫一句，放手一搏。"
YIELDED = "你拱手認輸，跳下擂台。"
STANDING = "你的積分 {rating}，{record}{place}。"
UNRANKED = "你還沒打過擂台。"
TOP = "擂台前列：{names}。"
GAMBLE_NOTE = "寫得越險，成了越能扭轉局面；失手時氣勢倒退，重傷的是你自己。這一回合他的招不算。"
PROMPT = "放手一搏：寫下你要怎麼對付他（20 字以內）"
SETTING = "江湖擂台上一對一比武的"  # 給 battle_instance.assess_gamble
PLACE = "擂台"
UPSET = "擂台爆冷：{winner}擊敗了積分高出一截的{loser}。"
STREAK = "{name}在擂台上連勝 {n} 場，一時無人能擋。"
HIGHLIGHT = "擂台上最令人印象深刻的一幕：{name}放手一搏——「{text}」，竟然成了！"
DEFENDED = "{name}上擂台挑你留下的分身。"
UNSETTLED = "這一季收了，擂台上沒打完的那一場不算。"
SEASON_TOP = "本季擂台前三名：{names}。"
PRIZE = "本季擂台第 {place} 名：名望 +{fame}、{pill} +{pills}。"


def on(content: Content) -> bool:
    return content.config.arena.enabled


def town(content: Content, loc_id: str) -> bool:
    """擂台在城鎮（同懸賞榜那一種城鎮：bounties.is_town）。"""
    loc = content.locations.get(loc_id)
    return loc is not None and content.config.explore_mix_of(loc.tags).kind == "town"


def here(state: GameState, content: Content) -> bool:
    """此刻打得開擂台：開關開著、季在跑、人在城鎮、不在路上。"""
    p = state.player
    return on(content) and not state.world.ended and p.journey is None and town(content, p.location)


def entry_of(world: WorldState, name: str) -> ArenaEntry | None:
    return world.arena.get(name_key(name))


def pair_key(me: str, foe: str) -> str:
    return f"{name_key(me)}>{name_key(foe)}"


def defended_today(entry: ArenaEntry, day: int) -> int:
    return entry.defended[1] if len(entry.defended) == 2 and entry.defended[0] == day else 0


def day_of(world: WorldState) -> int:
    return int(world.time // DAY)


def challenge_problem(world: WorldState, me: str, foe: ArenaEntry, cfg: ArenaTuning) -> str | None:
    """挑不挑得了這個人（體力、閒不閒由 Game 看）：先報名、冷卻、他今天被挑滿了沒有。None＝可以。"""
    if entry_of(world, me) is None:
        return JOIN_FIRST
    last = world.arena_pairs.get(pair_key(me, foe.name))
    if last is not None and 0 <= world.time - last < cfg.pair_cooldown_seconds:
        return COOLING
    if defended_today(foe, day_of(world)) >= cfg.defend_per_day:
        return PROTECTED.format(n=cfg.defend_per_day)
    return None


def note_challenge(world: WorldState, me: str, foe: ArenaEntry) -> None:
    """開打那一刻記冷卻與他今天被挑了幾場（同截殺：開打就算，認輸、沒打完也算）。"""
    world.arena_pairs[pair_key(me, foe.name)] = world.time
    day = day_of(world)
    foe.defended = [day, defended_today(foe, day) + 1]


def expected(mine: float, theirs: float) -> float:
    """Elo 的期望得分（照積分算的勝率）。"""
    return 1 / (1 + 10 ** ((theirs - mine) / 400))


def rated(challenger: float, defender: float, score: float, k: float) -> tuple[float, float]:
    """一場打完兩邊的新積分（score 是挑的人的得分）：兩邊加減同一個數。"""
    delta = k * (score - expected(challenger, defender))
    return challenger + delta, defender - delta


def ranked(world: WorldState) -> list[ArenaEntry]:
    """打過至少一場的人照積分排（同分照勝場多、先報名的）。"""
    rows = [e for e in world.arena.values() if e.bouts > 0]
    return sorted(rows, key=lambda e: (-e.rating, -e.wins, e.joined, name_key(e.name)))


def place_of(world: WorldState, name: str) -> int | None:
    k = name_key(name)
    return next((i for i, e in enumerate(ranked(world), 1) if name_key(e.name) == k), None)


def record_text(entry: ArenaEntry) -> str:
    text = f"{entry.wins} 勝 {entry.losses} 負" + (f" {entry.draws} 和" if entry.draws else "")
    return text + (f"・連勝 {entry.streak}" if entry.streak >= 2 else "")


def board(world: WorldState, cfg: ArenaTuning) -> list[dict]:
    """擂台榜（見聞「榜單」分頁的一張）：名次、名號、積分、勝、負、和、連勝。"""
    return [
        {"rank": i, "name": e.name, "rating": round(e.rating), "wins": e.wins, "losses": e.losses, "draws": e.draws, "streak": e.streak}
        for i, e in enumerate(ranked(world)[:cfg.board_size], 1)
    ]


def standing(world: WorldState, name: str) -> list[str]:
    """打開擂台時的頭一句：你的積分、戰績與名次，加上前三名。"""
    lines = []
    me = entry_of(world, name)
    if me is None or me.bouts == 0:
        lines.append(UNRANKED)
    else:
        place = place_of(world, name)
        lines.append(STANDING.format(rating=round(me.rating), record=record_text(me), place=f"，第 {place} 名" if place else ""))
    top = ranked(world)[:3]
    if top:
        lines.append(TOP.format(names="、".join(f"{e.name}（{round(e.rating)}）" for e in top)))
    return lines


def strength_words(content: Content, mine: float, theirs: float) -> str:
    """身手跟你比（字同奪璽單挑的 foe_line）。"""
    tuning = content.config.battle
    ratio = battle_instance.strength(tuning, theirs) / max(1.0, battle_instance.strength(tuning, mine))
    return ("遠比你強" if ratio >= 1.5 else "比你強" if ratio >= 1.1 else "跟你不相上下" if ratio > 0.9
            else "比你弱" if ratio > 0.6 else "遠比你弱")


def foe_line(me: ArenaSide, foe: ArenaSide, content: Content) -> str:
    """給模型評成功率的那一行（同奪璽單挑 seal_duel.foe_line：只寫比較）。"""
    words = strength_words(content, me.power, foe.power).replace("你", "玩家")
    hurt = "，已經帶傷" if foe.hp < foe.hp_cap * 0.5 else ""
    return f"{foe.name}（身手{words}{hurt}）"


def rng_for(season: int, name: str, fight: ArenaFight, what: str) -> random.Random:
    return random.Random(f"擂台|{season}|{name_key(name)}|{fight.id}|{fight.round + 1}|{what}")


def roll_next(fight: ArenaFight, rng: random.Random, cfg: ArenaTuning, tuning: DuelTuning) -> None:
    """分身下一回合的招與你看到的架勢（同奪璽單挑的代打：先取招、再取真假、再取句子）。"""
    values = [max(0.0, fight.foe.scores.get(m, 0.0)) for m in MOVES]
    top = max(values)
    weights = [(v / top) ** cfg.proxy_power for v in values] if top > 0 else [1.0] * len(MOVES)
    fight.move = rng.choices(MOVES, weights=weights)[0]
    shown = fight.move if rng.random() < tuning.tell_truth else rng.choice([m for m in MOVES if m != fight.move])
    fight.tell = rng.choice(duel_rules.TELLS[shown])


def _weight(side: ArenaSide, move: str, content: Content) -> float:
    return side.scores.get(move) or battle_instance.strength(content.config.battle, side.power) * content.config.duel.foe_fit


def _clamp(edge: float) -> float:
    return max(0.0, min(100.0, edge))


def exchange(fight: ArenaFight, move: str, content: Content, rng: random.Random) -> tuple[int, int, int, int]:
    """你出一招、分身出他擲好的那一招：（氣勢推了多少, 你掉多少, 他掉多少, 剋）。兩邊各扣自己的池子（同奪璽單挑）。"""
    tuning, battle = content.config.duel, content.config.battle
    me, foe = fight.me, fight.foe
    mine, theirs = _weight(me, move, content), _weight(foe, fight.move, content)
    beat = duel_rules.counter(move, fight.move)
    push = duel_rules.push_of(mine, theirs, beat, me.role, tuning, battle, rng.uniform(-tuning.luck, tuning.luck), foe_role=foe.role)
    my_hp = min(me.hp, duel_rules.harm_of(me.hp_cap, mine, theirs, beat, tuning))
    foe_hp = min(foe.hp, duel_rules.harm_of(foe.hp_cap, theirs, mine, -beat, tuning))
    me.hp -= my_hp
    foe.hp -= foe_hp
    before = fight.edge
    fight.edge = _clamp(fight.edge + push)
    return round(fight.edge - before), my_hp, foe_hp, beat


def gamble(fight: ArenaFight, rate: int, content: Content, rng: random.Random) -> tuple[bool, int, int, int]:
    """放手一搏（同頭目戰：分身這一回合的招不算、他不扣血）：（成了沒有, 氣勢推了多少, 你掉多少, 實際的成功率）。"""
    me = fight.me
    won, delta, hp, rate = duel_rules.gamble_roll(rate, me.hp_cap, me.power, me.role, content.config.duel, content.config.battle, rng)
    hp = min(me.hp, hp)
    me.hp -= hp
    before = fight.edge
    fight.edge = _clamp(fight.edge + delta)
    return won, round(fight.edge - before), hp, rate


def verdict(fight: ArenaFight, tuning: DuelTuning) -> str | None:
    """分出勝負沒有（挑的人的角度，同奪璽單挑）：你的池子見底或氣勢到底落敗；他的池子見底大勝；氣勢到頂提前大勝（寫大勝）；
    打滿看氣勢。還沒是 None。"""
    if fight.me.hp <= 0 or fight.edge <= tuning.early_lose:
        return "落敗"
    if fight.foe.hp <= 0 or fight.edge >= tuning.early_win:
        return "大勝"
    return duel_rules.verdict_at(fight.edge, fight.me.hp, fight.round, fight.rounds, tuning)


def defender_tier(tier: str, edge: float, tuning: DuelTuning) -> str:
    """守的人那一邊的結果（戰報那一格）：挑的人落敗時照收場的氣勢分大勝、險勝（同奪璽單挑的 side_tier）。"""
    if tier == "落敗":
        return "大勝" if 100 - edge >= tuning.big else "險勝"
    return FLIP[tier]


def note_result(entry: ArenaEntry, score: float) -> None:
    """記一場的戰績與連勝（挑、守都走這裡）。"""
    if score >= 1:
        entry.wins += 1
        entry.streak += 1
        entry.best_streak = max(entry.best_streak, entry.streak)
    elif score > 0:
        entry.draws += 1
        entry.streak = 0
    else:
        entry.losses += 1
        entry.streak = 0


def scene_text(fight: ArenaFight) -> str:
    return (f"第 {fight.round + 1}／{fight.rounds} 回合，{duel_rules.edge_words(fight.edge)}。"
            f"你的氣血 {fight.me.hp:.0f}／{fight.me.hp_cap:.0f}，他 {fight.foe.hp:.0f}／{fight.foe.hp_cap:.0f}。{fight.tell}")


def scene(fight: ArenaFight) -> duel_rules.Scene:
    """assess_gamble 讀的 title 與 text。"""
    return duel_rules.Scene(f"擂台・{fight.foe.name}的分身", scene_text(fight))


def close_season(world: WorldState, cfg: ArenaTuning) -> str | None:
    """收季那一刻（world.end_season）：前三名記名次（補獎勵看它），回江湖史那一句；沒人打過是 None。只排一次。"""
    if world.arena_closed:
        return None
    world.arena_closed = True
    top = ranked(world)[:len(cfg.prizes)]
    for i, e in enumerate(top, 1):
        e.place = i
    if not top:
        return None
    return SEASON_TOP.format(names="、".join(f"{e.name}（{round(e.rating)}）" for e in top))
