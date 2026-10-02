"""伺服器假人的整季模擬（伺服器假人設計第八節第 6 項）：正式內容、2 個「真人」機器人＋假人程式，
用假時鐘跑完一整季，印出有沒有開戰、兩邊參戰人數、各陣營人數、結局。

執行：.venv/Scripts/python.exe scripts/sim_server_bots.py --seasons 2 --time-scale 6 --tick 60
（time-scale 越大跑越快，但假人的作息是現實時間：太大會讓一季只涵蓋一兩個晚上）
"""
from __future__ import annotations

import argparse
import random
import sys
import tempfile
from collections import Counter
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tianxia import bot, server_bots  # noqa: E402
from tianxia.bot_runner import BotRunner  # noqa: E402
from tianxia.content import load_content  # noqa: E402
from tianxia.engine import Game  # noqa: E402
from tianxia.save import load_game, path_for, save_game  # noqa: E402
from tianxia.world_state import WorldStateStore  # noqa: E402

START = 1_791_198_000.0  # 2026-10-05 19:00 台灣時間
HUMANS = ("沈青衫", "柳如煙")
HUMAN_HOURS = range(20, 23)  # 「真人」每天晚上 8～11 點上線
MAX_REAL_DAYS = 60


def human_turn(game: Game, rng: random.Random) -> None:
    """「真人」機器人：能投靠就隨機挑一個陣營（確認畫面一定確定），其餘照 bot.pick 隨機玩。"""
    options = [o for o in game.options(odds=False) if o.enabled]
    ids = [o.id for o in options]
    if "faction:confirm" in ids:
        game.choose("faction:confirm")
        return
    joins = [i for i in ids if i.startswith("faction:")]
    if joins and game.state.player.faction is None:
        game.choose(rng.choice(joins))
        return
    choice = bot.pick(game, [o for o in options if not o.id.startswith("faction:")], rng)
    if choice:
        game.choose(choice)
    if rng.random() < 0.2:
        bot.spend_xinde(game, rng)


def run_season(content, workdir: Path, seed: int, tick: float) -> dict:
    now = [START]
    world = WorldStateStore(workdir / "world" / "state.json")
    saves = workdir / "saves"
    rng = random.Random(seed)
    sides: Counter = Counter()
    battle_started_day = None
    with mock.patch("time.time", lambda: now[0]):
        world.seed_first_season(content)
        world.open_season(now[0])
        humans = [Game.new(content, name, rng=random.Random(seed + i), world=world) for i, name in enumerate(HUMANS)]
        for game in humans:
            game.client = None
        runner = BotRunner(content, world, saves, random.Random(seed), clock=lambda: now[0])
        while not world.get_season().ended and now[0] - START < MAX_REAL_DAYS * 86400:
            runner.tick()
            hour = int((now[0] + server_bots.TZ_OFFSET) % 86400 // 3600)
            for game in humans:
                if hour in HUMAN_HOURS and rng.random() < 0.5:
                    with world.action_lock():
                        game.sync(now[0])
                        human_turn(game, rng)
                        save_game(game.state, path_for(saves, game.state.player.name))
            battle = world.get_battle()
            if battle is not None:
                if battle_started_day is None:
                    battle_started_day = world.get_season().time / 86400
                sides = Counter(p.faction for p in battle.participants.values())
            now[0] += tick
        season = world.get_season()
        bots = [load_game(p) for p in saves.glob("*.json")]
        bots = [s for s in bots if s.player.bot is not None]
    return {
        "ended": season.ended,
        "day": season.time / 86400,
        "ending": season.ending_title,
        "trends": dict(season.trends),
        "battle_day": battle_started_day,
        "battle_sides": dict(sides),
        "factions": world.faction_counts(),
        "humans": {g.state.player.name: g.state.player.faction for g in humans},
        "bots": len(bots),
        "tempers": dict(Counter(s.player.bot.personality for s in bots)),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seasons", type=int, default=2)
    parser.add_argument("--time-scale", type=float, default=6.0)
    parser.add_argument("--tick", type=float, default=60.0)
    args = parser.parse_args()
    for i in range(args.seasons):
        content = load_content(ROOT / "content")
        content.config.time_scale = args.time_scale
        content.config.bot_tick_seconds = args.tick
        with tempfile.TemporaryDirectory() as tmp:
            result = run_season(content, Path(tmp), seed=i, tick=args.tick)
        print(f"第 {i + 1} 季：{result}", flush=True)


if __name__ == "__main__":
    main()
