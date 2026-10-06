"""決戰改版一 Task 6：三招與推力的數字量一場（戰鬥系統設計 3.4【預設】）。只量、不改數字、不擋上線。

假人直接在 battle_instance 上打（不經過 Game）：每個人的威力從「新手到高手」之間抽、武學與內功屬性隨機，
份量照 move_scores 算；出招照幾種策略。每種情況打到收場（最多 9 回合），印每回合的推力與收場的戰局。
最後另量伺服器假人（bot_policy）在真實內容、新手的起手武學下，三招各出幾成。

用法：.venv/Scripts/python.exe scripts/measure_battle.py
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
    os.environ[database.ENV_VAR] = str(Path(tempfile.mkdtemp(prefix="sd1_measure_")) / "measure.db")
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


def main() -> None:
    content = load_content(ROOT / "content")
    measure_rules(content)
    measure_server_bots(content)


if __name__ == "__main__":
    main()
