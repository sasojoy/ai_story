"""伺服器假人的整季模擬（伺服器假人設計第八節第 6 項）：正式內容、2 個「真人」機器人＋假人程式，
用假時鐘跑完一整季，印出有沒有開戰、兩邊參戰人數、各陣營人數、結局。

執行：.venv/Scripts/python.exe scripts/sim_server_bots.py --seasons 2 --time-scale 6 --tick 60
（加 --pause-at 4 --pause-hours 3：開季後第 4 個現實鐘頭讓賽季時鐘停 3 個鐘頭；結果的 pause 一欄寫停的那一段季走了多少，應該是 0）
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
from tianxia.world import resume_season_clock  # noqa: E402

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


def _pause_step(world, content, now: float, pause: tuple[float, float], frozen: list[float], log: dict) -> None:
    """到了就暫停（一季只停一次）、停滿就繼續（跟管理者按「繼續」同一條路：world.resume_season_clock，繼續、補算、
    開集結三步一起做，原本的時間落在暫停裡的決戰這一刻開集結）；
    繼續之前（停著的這一段，「真人」照樣同步、假人程式照樣巡過）記下季的時間走了多少——應該是 0。"""
    start, end = START + pause[0] * 3600, START + (pause[0] + pause[1]) * 3600
    if not frozen and start <= now < end and world.pause_clock(now):
        frozen.append(world.get_season().time)
        log["at_day"] = frozen[0] / 86400
    elif frozen and now >= end and world.paused_at() is not None:
        log["season_moved"] = world.get_season().time - frozen[0]
        resume_season_clock(world, content, now, random.Random(0), "停了 {minutes} 分鐘")


def run_season(content, workdir: Path, seed: int, tick: float, pause: tuple[float, float] | None = None) -> dict:
    """pause＝（開季後第幾個現實鐘頭暫停, 停幾個鐘頭）：中途讓賽季時鐘停一段（公告停機），量停的那一段季有沒有動。"""
    now = [START]
    pause_log = None if pause is None else {"at_day": None, "season_moved": None, "bot_moves": 0}
    frozen: list[float] = []  # 暫停那一刻的季時間（停成了才有）
    db_path = workdir / "tianxia.db"
    world = open_world(db_path)
    characters = open_characters(db_path)
    rng = random.Random(seed)  # 模擬自己用的亂數；假人程式與「真人」另用不同的種子，三者互不牽動
    sides: Counter = Counter()
    battle_started_day = None
    battle_hour = None  # 第一場決戰開集結是開季後第幾個現實鐘頭（暫停之後決戰要照原本的現實時間開）
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
            if pause is not None:
                _pause_step(world, content, now[0], pause, frozen, pause_log)
            paused = world.paused_at() is not None
            report = runner.tick()
            if paused:
                pause_log["bot_moves"] += report.acted + report.added
            hour = int((now[0] + server_bots.TZ_OFFSET) % 86400 // 3600)
            for game in humans:
                if hour in HUMAN_HOURS and rng.random() < 0.5:
                    with world.action_lock():
                        game.sync(now[0])  # 暫停中照樣刷新畫面（同步），只是不行動
                        if not paused:
                            human_turn(game, rng)
                        characters.save(game.state)
            battle = world.get_battle()
            if battle is not None:
                if battle_started_day is None:
                    battle_started_day = world.get_season().time / 86400
                    battle_hour = (now[0] - START) / 3600
                sides = Counter(p.faction for p in battle.participants.values())
            now[0] += tick
        season = world.get_season()
        bots = characters.all(bots_only=True)
        late = sum(1 for s in characters.all() if (s.player.joined_at or 0.0) > 0)
    return {
        "ended": season.ended,
        "day": season.time / 86400,
        "ending": season.ending_title,
        "trends": dict(season.trends),
        "battle_day": battle_started_day,
        "battle_hour": battle_hour,
        "battle_sides": dict(sides),
        "factions": world.faction_counts(),
        "humans": {g.state.player.name: g.state.player.faction for g in humans},
        "bots": len(bots),
        "tempers": dict(Counter(s.player.bot.personality for s in bots)),
        "late_joiners": late,  # 季中才加入（joined_at > 0）的角色數：新手福利從他們自己加入那天起算
        "pause": pause_log,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seasons", type=int, default=2)
    parser.add_argument("--time-scale", type=float, default=6.0)
    parser.add_argument("--tick", type=float, default=60.0)
    parser.add_argument("--profile", default=os.environ.get(PROFILE_ENV) or None, help="設定覆寫檔，例如 weekend（預設讀 TIANXIA_PROFILE）")
    parser.add_argument("--pause-at", type=float, default=None, help="開季後第幾個現實鐘頭讓賽季時鐘暫停（公告停機）；不給就不停")
    parser.add_argument("--pause-hours", type=float, default=3.0, help="停幾個現實鐘頭（配 --pause-at）")
    args = parser.parse_args()
    print(profile_line(load_content(ROOT / "content", profile=args.profile), args.profile), flush=True)
    for i in range(args.seasons):
        content = load_content(ROOT / "content", profile=args.profile)
        content.config.time_scale = args.time_scale
        content.config.bot_tick_seconds = args.tick
        with tempfile.TemporaryDirectory() as tmp:
            try:
                pause = None if args.pause_at is None else (args.pause_at, args.pause_hours)
                result = run_season(content, Path(tmp), seed=i, tick=args.tick, pause=pause)
            finally:
                database.close_all()  # 不先關連線，Windows 刪不掉暫存資料夾（這一季出錯時也一樣）
        print(f"第 {i + 1} 季：{result}", flush=True)


if __name__ == "__main__":
    main()
