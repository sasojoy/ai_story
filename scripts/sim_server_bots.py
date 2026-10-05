"""伺服器假人的整季模擬（伺服器假人設計第八節第 6 項）：正式內容、2 個「真人」機器人＋假人程式，
用假時鐘跑完一整季，印出有沒有開戰、兩邊參戰人數、各陣營人數、結局。

執行：.venv/Scripts/python.exe scripts/sim_server_bots.py --seasons 2 --time-scale 6 --tick 60
（time-scale 越大跑越快，但假人的作息是現實時間：太大會讓一季只涵蓋一兩個晚上；
遠離出生地的陣營，懶散的假人可能整季都走不到投靠點，各陣營人數因此補不滿）
"""
from __future__ import annotations

import argparse
import os
import random
import sys
import tempfile
from collections import Counter
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tianxia import bot, database, server_bots  # noqa: E402
from tianxia.bot_runner import BotRunner  # noqa: E402
from tianxia.characters import open_characters  # noqa: E402
from tianxia.content import PROFILE_ENV, load_content, profile_line  # noqa: E402
from tianxia.engine import Game  # noqa: E402
from tianxia.sqlite_world import open_world  # noqa: E402

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
        bot.allocate_points(game, rng)  # 升級的屬性點（武學與成長設計 6.2）；假人在 bot_policy.look_after 裡配
        bot.spend_xinde(game, rng)


def run_season(content, workdir: Path, seed: int, tick: float) -> dict:
    now = [START]
    db_path = workdir / "tianxia.db"
    world = open_world(db_path)
    characters = open_characters(db_path)
    rng = random.Random(seed)  # 模擬自己用的亂數；假人程式與「真人」另用不同的種子，三者互不牽動
    sides: Counter = Counter()
    battle_started_day = None
    # 季末結算榜單時沒指定資料庫就開預設的那個；用環境變數指到這次的暫存檔，不碰真資料。
    # 引擎已經不讀電腦時鐘（假人程式用 clock，「真人」sync 時傳 now），不用再 mock time.time。
    with mock.patch.dict(os.environ, {database.ENV_VAR: str(db_path)}):
        world.seed_first_season(content)
        world.open_season(content, now[0])
        humans = [Game.new(content, name, rng=random.Random(seed + 2000 + i), world=world) for i, name in enumerate(HUMANS)]
        for game in humans:
            game.client = None
        runner = BotRunner(content, world, characters, random.Random(seed + 1000), clock=lambda: now[0])
        while not world.get_season().ended and now[0] - START < MAX_REAL_DAYS * 86400:
            runner.tick()
            hour = int((now[0] + server_bots.TZ_OFFSET) % 86400 // 3600)
            for game in humans:
                if hour in HUMAN_HOURS and rng.random() < 0.5:
                    with world.action_lock():
                        game.sync(now[0])
                        human_turn(game, rng)
                        characters.save(game.state)
            battle = world.get_battle()
            if battle is not None:
                if battle_started_day is None:
                    battle_started_day = world.get_season().time / 86400
                sides = Counter(p.faction for p in battle.participants.values())
            now[0] += tick
        season = world.get_season()
        bots = characters.all(bots_only=True)
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
    parser.add_argument("--profile", default=os.environ.get(PROFILE_ENV) or None, help="設定覆寫檔，例如 weekend（預設讀 TIANXIA_PROFILE）")
    args = parser.parse_args()
    print(profile_line(load_content(ROOT / "content", profile=args.profile), args.profile), flush=True)
    for i in range(args.seasons):
        content = load_content(ROOT / "content", profile=args.profile)
        content.config.time_scale = args.time_scale
        content.config.bot_tick_seconds = args.tick
        with tempfile.TemporaryDirectory() as tmp:
            try:
                result = run_season(content, Path(tmp), seed=i, tick=args.tick)
            finally:
                database.close_all()  # 不先關連線，Windows 刪不掉暫存資料夾（這一季出錯時也一樣）
        print(f"第 {i + 1} 季：{result}", flush=True)


if __name__ == "__main__":
    main()
