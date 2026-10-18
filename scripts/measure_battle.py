"""決戰改版一 Task 6：三招與推力的數字量一場（戰鬥系統設計 3.4【預設】）。只量、不改數字、不擋上線。

假人直接在 battle_instance 上打（不經過 Game）：每個人的威力從「新手到高手」之間抽、武學與內功屬性隨機，
份量照 move_scores 算；出招照幾種策略。每種情況打到收場（最多 9 回合），印每回合的推力與收場的戰局。
最後另量伺服器假人（bot_policy）在真實內容、新手的起手武學下，三招各出幾成。

用法：.venv/Scripts/python.exe scripts/measure_battle.py [--generals]

--generals（龍頭上陣，Joy 2026-10-17 第 2 條）：長社、宛城、廣宗三場，兩邊各 N 人（威力在 --power 之間抽），照開季的聲威派人物上陣，
量人物的份量佔自己那一邊多少、幾回合敗走、收場戰局跟沒有人物上陣比差多少。每個人 ORDER_FOLLOW 的機會照令出招，其餘出拿手的招。
"""
from __future__ import annotations

import io
import os
import random
import statistics
import sys
import tempfile
from collections import Counter
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tianxia import battle_instance as bi  # noqa: E402
from tianxia.content import load_content  # noqa: E402
from tianxia.models import BEATS, MOVES  # noqa: E402

ATTRS = ("剛", "實", "陽", "柔", "陰", "慢", "快", "虛")
CODES = {"強攻": "strong", "固守": "hold", "奇襲": "raid"}


def best(p, rng, last_enemy):
    return max(MOVES, key=lambda m: p.scores[m])


def counter(p, rng, last_enemy):
    """猜對面這回合照上回合最多的那招出，出剋它的招。"""
    if not last_enemy:
        return best(p, rng, last_enemy)
    likely = max(last_enemy, key=last_enemy.get)
    return next(m for m, v in BEATS.items() if v == likely)


def anything(p, rng, last_enemy):
    return rng.choice(MOVES)


STRATEGIES = {"拿手": best, "剋上回合": counter, "亂出": anything}


def run(definition, tuning, guan, huang, guan_play, huang_play, seed=0):
    rng = random.Random(seed)
    battle = bi.start_muster(definition, now=0)
    for side, count in (("guan", guan), ("huang", huang)):
        for i in range(count):
            power = rng.uniform(0, 150)
            scores = bi.move_scores(tuning, power, rng.choice(ATTRS), rng.choice(ATTRS))
            bi.join_faction(battle, f"{side}{i}", side, neili_cap=400, power=power, scores=scores)
    bi.close_muster(battle, definition, rng, now=0)
    pushes = []
    while battle.phase == "active":
        before = battle.trend
        for name, p in battle.participants.items():
            if p.eliminated:
                continue
            enemy = "huang" if p.faction == "guan" else "guan"
            play = guan_play if p.faction == "guan" else huang_play
            move = play(p, rng, battle.last_mix.get(enemy, {}))
            bi.submit_action(battle, name, f"{p.faction}_{CODES[move]}")
        bi.resolve_round(battle, definition, rng, now=0, tuning=tuning)
        pushes.append(battle.trend - before)
    return battle.trend, pushes, battle.round_number


def measure_rules(content) -> None:
    definition = content.battles["changshe_fire"].model_copy(update={"trend_start": 50})
    tuning = content.config.battle
    cases = [(1000, 250), (600, 400), (20, 20), (10, 2), (2, 10)]
    for guan, huang in cases:
        for gname, gplay in STRATEGIES.items():
            for hname, hplay in STRATEGIES.items():
                ends = [run(definition, tuning, guan, huang, gplay, hplay, seed) for seed in range(5)]
                trends = [t for t, _, _ in ends]
                rounds = [r for _, _, r in ends]
                print(f"官 {guan}（{gname}）對 黃 {huang}（{hname}）：收場戰局 {statistics.median(trends)}"
                      f"（{min(trends)}～{max(trends)}），回合中位 {statistics.median(rounds)}，"
                      f"第一場每回合推 {ends[0][1]}")


def measure_server_bots(content, samples: int = 2000) -> None:
    """伺服器假人（bot_policy._battle_score／pick）三招各出幾成：真實內容、起手的武學（新手的份量）與隨機的各種武學。
    只讀不改：用暫存資料庫（TIANXIA_DB 指到暫存檔，量完還原、關掉連線），不碰 saves/。"""
    from tianxia import database

    previous = os.environ.get(database.ENV_VAR)
    # 暫存資料夾量完就刪（連線先關掉，Windows 才刪得掉）；不留下一個又一個 tianxia_measure_xxxx
    with tempfile.TemporaryDirectory(prefix="tianxia_measure_", ignore_cleanup_errors=True) as tmp:
        os.environ[database.ENV_VAR] = str(Path(tmp) / "measure.db")
        try:
            _measure_server_bots(content, samples)
        finally:
            database.close_all()
            if previous is None:
                os.environ.pop(database.ENV_VAR, None)
            else:
                os.environ[database.ENV_VAR] = previous


def _measure_server_bots(content, samples: int) -> None:
    from tianxia import bot_policy
    from tianxia.engine import Game, Option
    from tianxia.sqlite_world import open_world
    from tianxia.state import BotProfile

    content.scenario.sim_players = []
    content.config.auto_open_first_season = True
    game = Game.new(content, "量測", rng=random.Random(0), world=open_world(Path(os.environ["TIANXIA_DB"])))
    game.now = 0.0
    definition = content.battles["huangjin_showdown"]
    game.world.start_battle(definition, now=0.0)
    name = game.state.player.name
    starter = game._battle_scores()
    game.world.mutate_battle(lambda b: bi.join_faction(b, name, "guan", game._battle_neili_cap(), game._battle_power(), scores=starter))
    options = [Option(id=f"battle:act:guan_{code}", label=m) for m, code in CODES.items()]
    profile = BotProfile(personality="普通", seed=1, faction="guan", season_number=1)
    print(f"\n── 伺服器假人（bot_strength {content.config.bot_strength}）──")
    print(f"新手起手的份量：{starter}（氣血上限 {game._battle_neili_cap():.0f}）")

    def share(label: str) -> None:
        rng = random.Random(7)
        picks = Counter(bot_policy.pick(game, options, profile, rng) for _ in range(samples))
        shown = "、".join(f"{m} {picks[f'battle:act:guan_{c}'] / samples:.0%}" for m, c in CODES.items())
        print(f"{label}：{shown}")

    for strength in (content.config.bot_strength, 1.0, 0.0):
        content.config.bot_strength = strength
        share(f"新手起手、強度 {strength}")
    content.config.bot_strength = 0.6
    # 隨機的各種武學（威力 0～150、武學與內功屬性各隨機）：每個假人固定自己的份量，各量 200 次再合起來
    rng = random.Random(11)
    total = Counter()
    per = 200
    for _ in range(60):
        power = rng.uniform(0, 150)
        scores = bi.move_scores(content.config.battle, power, rng.choice(ATTRS), rng.choice(ATTRS))
        game.world.mutate_battle(lambda b: b.participants[name].scores.update(scores))
        pick_rng = random.Random(rng.random())
        total.update(bot_policy.pick(game, options, profile, pick_rng) for _ in range(per))
    n = sum(total.values())
    print("隨機武學的假人（強度 0.6）：" + "、".join(f"{m} {total[f'battle:act:guan_{c}'] / n:.0%}" for m, c in CODES.items()))
    best_counts = Counter()
    rng = random.Random(11)
    for _ in range(6000):
        power = rng.uniform(0, 150)
        scores = bi.move_scores(content.config.battle, power, rng.choice(ATTRS), rng.choice(ATTRS))
        best_counts[max(MOVES, key=lambda m: scores[m])] += 1
    print("隨機武學的人最拿手的招：" + "、".join(f"{m} {best_counts[m] / 6000:.0%}" for m in MOVES))


def _generals_run(definition, tuning, chiefs, per_side, power, seed, follow, name_rate=0.0):
    """一場：兩邊各 per_side 人、人物照 chiefs 上陣（空的是對照）。回傳（收場戰局, 人物份量佔比 {陣營: 比例}, 敗走 [(名字, 回合)]）。"""
    rng = random.Random(seed)
    battle = bi.start_muster(definition, now=0)
    for side in ("guan", "huang"):
        for i in range(per_side):
            p = rng.uniform(*power)
            scores = bi.move_scores(tuning, p, rng.choice(ATTRS), rng.choice(ATTRS))
            bi.join_faction(battle, f"{side}{i}", side, neili_cap=600, power=p, scores=scores)
    battle.commanders = [c.model_copy() for c in chiefs]
    battle.record_id = seed + 1  # 將令的亂數照流水號：每一場不一樣
    bi.close_muster(battle, definition, rng, now=0, tuning=tuning)
    share = {}
    for side in ("guan", "huang"):
        mine = sum(c.score for c in battle.commanders if c.faction == side)
        players = sum(statistics.mean(q.scores.values()) for q in battle.participants.values() if q.faction == side)
        share[side] = mine / (mine + players) if mine + players else 0.0
    while battle.phase == "active":
        for name, q in battle.participants.items():
            if q.eliminated:
                continue
            foe = next((c for c in battle.commanders if c.faction != q.faction and c.fallen_round is None), None)
            if foe is not None and rng.random() < name_rate:  # 放手一搏點名對面的人物（成功率 40）
                bi.submit_action(battle, name, f"{q.faction}_reckless", text=f"直取{foe.name}", success_rate=40, stories=("", ""))
                continue
            order = battle.orders.get(q.faction)
            move = order if order and rng.random() < follow else max(MOVES, key=lambda m: q.scores[m])
            bi.submit_action(battle, name, f"{q.faction}_{CODES[move]}")
        bi.resolve_round(battle, definition, rng, now=0, tuning=tuning)
    falls = [(c.name, c.fallen_round) for c in battle.commanders if c.fallen_round is not None]
    return battle.trend, share, falls


def measure_generals(content, per_side: int, power: tuple[float, float], seeds: int, name_rate: float = 0.0) -> None:
    from tianxia import bot_policy, generals
    from tianxia.state import GameState, PlayerState
    from tianxia.world_state import fresh_season

    tuning = content.config.battle
    state = GameState(player=PlayerState(name="", location=content.scenario.start_location, stats={}, stamina=0),
                      world=fresh_season(content))
    print(f"\n── 龍頭上陣：每邊 {per_side} 人、威力 {power[0]:.0f}～{power[1]:.0f}、照令 {bot_policy.ORDER_FOLLOW:.0%}、每人每回合 {name_rate:.0%} 點名對面人物放手一搏 ──")
    for bid in ("changshe_fire", "wancheng_jia", "guangzong"):
        definition = content.battles.get(bid)
        if definition is None:
            continue
        definition = definition.model_copy(update={"trend_start": 50})
        chiefs = generals.pick(state, content, definition)
        rows = "、".join(f"{generals.RANK_NAMES[c.rank]}{c.name}（{c.faction} 份量 {c.score:.0f}・氣血 {c.neili_cap:.0f}）" for c in chiefs)
        print(f"{definition.name}：{rows or '沒有人上陣'}")
        base = [_generals_run(definition, tuning, [], per_side, power, seed, bot_policy.ORDER_FOLLOW, name_rate)[0] for seed in range(seeds)]
        led = [_generals_run(definition, tuning, chiefs, per_side, power, seed, bot_policy.ORDER_FOLLOW, name_rate) for seed in range(seeds)]
        shares = {side: statistics.mean(r[1][side] for r in led) for side in ("guan", "huang")}
        fell = Counter(name for r in led for name, _ in r[2])
        when = [rnd for r in led for _, rnd in r[2]]
        print(f"  收場戰局中位：沒有人物 {statistics.median(base)}、人物上陣 {statistics.median([r[0] for r in led])}"
              f"（往官軍是大）；人物份量佔自己那一邊：官軍 {shares['guan']:.0%}、黃巾 {shares['huang']:.0%}")
        print(f"  {seeds} 場裡敗走：{dict(fell) or '沒有'}" + (f"，回合中位 {statistics.median(when)}" if when else ""))


def main() -> None:
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--generals", action="store_true")
    ap.add_argument("--per-side", type=int, default=10)
    ap.add_argument("--power", type=float, nargs=2, default=(100.0, 300.0))
    ap.add_argument("--seeds", type=int, default=40)
    ap.add_argument("--name-rate", type=float, default=0.0)
    ap.add_argument("--ranks", type=float, nargs=2, default=None)
    args = ap.parse_args()
    content = load_content(ROOT / "content", profile="weekend")
    if args.generals:
        if args.ranks:
            content.config.battle.generals.ranks = tuple(args.ranks)
        measure_generals(content, args.per_side, tuple(args.power), args.seeds, args.name_rate)
        return
    content = load_content(ROOT / "content")
    measure_rules(content)
    measure_server_bots(content)


if __name__ == "__main__":
    main()
