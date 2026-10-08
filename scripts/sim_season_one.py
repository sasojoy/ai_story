"""第一季濃縮版的整季模擬與驗收（計畫 T11，2026-10-05-T11-整季模擬）：週末設定、暫存資料庫、假時鐘，
只有伺服器假人（BotRunner）加一個不做事的旁觀者（像一直開著網頁的人：每一輪同步一次、刷新一次選單，
共用賽季的時鐘與決戰的回合才會照現實時間往前走）。每個種子印出：

- 每週末三條戰況與割據；十二件大事的結果與有沒有人鎖定；三場決戰的結果；
- 每陣營每週達成幾道軍令；升第 2 階的人數；
- 結局、收季時間、有沒有卡住（時間用完還沒收季）；
- 驗收（總計畫 T11）：第 6 週以前沒有決定性勝利；三條戰線的週末中位數在 20～80。

執行：.venv/Scripts/python.exe scripts/sim_season_one.py --seeds 1 2 3 --factions 5 5 5 --hours 60
數字照實報，不為了驗收調參數（PM 2026-10-05）。輸出只有數字與陣營，不列名號。
"""
from __future__ import annotations

import argparse
import io
import os
import random
import statistics
import sys
import tempfile
from collections import Counter, defaultdict
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tianxia import calendar, database, rules, server_bots, team  # noqa: E402
from tianxia.bot_runner import BotRunner, TickReport  # noqa: E402
from tianxia.characters import open_characters  # noqa: E402
from tianxia.content import load_content, profile_line  # noqa: E402
from tianxia.engine import Game  # noqa: E402
from tianxia.models import Content  # noqa: E402
from tianxia.sqlite_world import open_world  # noqa: E402
from tianxia.world import settle_season_start  # noqa: E402

START = 1_791_198_000.0  # 2026-10-05 19:00 台灣時間（同 sim_server_bots）
FRONTS = ("yingru", "nanyang", "jizhou")
SIDES = ("guan", "huang", "haoqiang")
GEJU_LINES = (85, 100)  # 割據的兩條線：85 是決定性勝利的門檻（第 10 週起收季），100 是頂
WATCHER = "旁觀者"  # 不做事的真人角色：每一輪同步、刷新選單（跟開著網頁的人一樣推著共用時鐘與決戰回合）


class SimRunner(BotRunner):
    """照每陣營各自的人數補假人，而且不等補人間隔（模擬一開季人就到齊）。其他照假人程式。"""

    def __init__(self, *args, targets: dict[str, int], **kwargs):
        super().__init__(*args, **kwargs)
        self.targets = targets

    def _fill(self, now: float, report: TickReport) -> None:
        season = self.world.get_season_number()
        bots = self.characters.all(bots_only=True)
        counts = self.world.faction_counts()
        for state in bots:  # 已派去、還在路上沒投靠的假人也算（同 BotRunner._fill）
            bot = state.player.bot
            if bot is not None and server_bots.active(bot, season) and state.player.faction is None:
                counts[bot.faction] = counts.get(bot.faction, 0) + 1
        for faction in self.content.scenario.factions:
            if counts.get(faction.id, 0) < self.targets.get(faction.id, 0):
                bots = self._add_bot(faction.id, season, bots, now)
                report.added += 1


def decisive_ids(content: Content) -> set[str]:
    """決定性勝利的結局（有態勢門檻的那幾種）。"""
    return {e.id for e in content.scenario.endings if e.season_one and (e.stance_min or e.stance_max)}


def checks(result: dict, content: Content) -> dict:
    """驗收（總計畫 T11）：第 6 週以前沒有決定性勝利；三條戰線的週末中位數在 20～80。"""
    early = result["ending_id"] in decisive_ids(content) and result["end_week"] < 6
    medians = {
        f: statistics.median(week[f] for week in result["weekly"].values()) for f in FRONTS
    } if result["weekly"] else {f: None for f in FRONTS}
    in_range = all(m is not None and 20 <= m <= 80 for m in medians.values())
    return {"no_early_decisive": not early, "medians": medians, "medians_ok": in_range, "passed": not early and in_range}


def run_season(
    content: Content, db_path: Path, seed: int, targets: dict[str, int], hours: float, tick: float = 60.0,
) -> dict:
    """跑一季（或跑到 hours 個現實小時用完），回傳整季的數字。content 已經照週末設定載好（開關打開）。"""
    content.config.season_one = True
    content.config.bot_tick_seconds = tick
    now = [START]
    rng = random.Random(seed)
    weekly: dict[int, dict[str, int]] = {}
    orders_done: dict[str, tuple[str, int]] = {}
    geju_first: dict[int, tuple[int, str]] = {}  # 割據第一次到 85、到 100 是第幾週、什麼時候（曆法的時間章）
    raided: Counter = Counter()  # 截殺（Config.raid）：被截殺的次數、輸的次數、失的銀兩與氣血，照名號（輸出不列名號）
    raid_losses: dict[str, list[int]] = defaultdict(lambda: [0, 0, 0])  # 名號 → [輸幾場, 失銀, 失氣血]
    raid_tiers: Counter = Counter()
    real_record, real_spoils = Game._raid_record, Game._raid_spoils

    def count_record(self, result, rival, rival_power, rival_game, spoils, *, attacker):
        if not attacker:
            raided[self.state.player.name] += 1
            raid_tiers["守方勝" if result.tier in team.WIN_TIERS else "平手" if spoils is None else "攻方勝"] += 1
        return real_record(self, result, rival, rival_power, rival_game, spoils, attacker=attacker)

    def count_spoils(self, loser):
        spoils = real_spoils(self, loser)
        row = raid_losses[loser.state.player.name]
        row[0], row[1], row[2] = row[0] + 1, row[1] + spoils.lost, row[2] + spoils.hp
        return spoils

    with mock.patch.dict(os.environ, {database.ENV_VAR: str(db_path)}), \
            mock.patch.object(Game, "_raid_record", count_record), mock.patch.object(Game, "_raid_spoils", count_spoils):
        world, characters = open_world(db_path), open_characters(db_path)
        world.seed_first_season(content)
        world.open_season(content, now[0])
        world.mutate_season(lambda season: settle_season_start(season, content, rng))  # 同管理者開季：結算第 1 週
        watcher = Game.new(content, WATCHER, rng=random.Random(seed + 7), world=world)
        watcher.client = None
        runner = SimRunner(
            content, world, characters, random.Random(seed + 1000), clock=lambda: now[0], targets=targets,
        )
        while now[0] - START <= hours * 3600:  # 含 hours 那一刻：季長剛好等於 hours 時，最後一輪才輪得到收季
            runner.tick()
            with world.action_lock():
                watcher.sync(now[0])
                watcher.options(odds=False)  # 刷新選單：決戰的集結截止、回合逾時照現實時間推進
                characters.save(watcher.state)
            season = world.get_season()
            if season.time > 0:
                week = calendar.point(season.time, content, season).week
                weekly[week] = {f: rules.trend_value(watcher.state, content, f) for f in (*FRONTS, "geju")}
                for line in GEJU_LINES:
                    if line not in geju_first and weekly[week]["geju"] >= line:
                        geju_first[line] = (week, calendar.stamp_text(season.time, content, season))
            for order in season.orders:
                if order.done:
                    orders_done[order.id] = (order.faction, order.week)
            if season.ended:
                break
            now[0] += tick
        season = world.get_season()
        everyone = characters.all()
        roster = sum(world.faction_counts().values())  # 這一季投靠名冊的人數（割據的漲速照它縮放）
    by_week: dict[str, Counter] = {side: Counter() for side in SIDES}
    for faction, week in orders_done.values():
        by_week.setdefault(faction, Counter())[week] += 1
    promoted = Counter(s.player.faction for s in everyone if s.player.bot is not None and s.player.rank >= 2)
    timeline = season.timeline
    result = {
        "weekly": weekly,
        "geju_first": {line: geju_first.get(line) for line in GEJU_LINES},  # {85: (週, 時間章) 或 None, 100: …}
        "roster": roster,
        "events": {eid: {"result": r.key, "locked": r.locked_by is not None} for eid, r in timeline.items()},
        "missing": [e.id for e in content.timetable if e.id not in timeline],
        "showdowns": {
            e.id: (timeline[e.id].key if e.id in timeline else ("開過、沒結算" if e.id in season.showdowns_opened else "沒開"))
            for e in content.timetable if e.kind == "showdown"
        },
        "orders": {side: dict(sorted(by_week.get(side, Counter()).items())) for side in SIDES},
        "promoted": {side: promoted.get(side, 0) for side in SIDES},
        "ending": season.ending_title if season.ended else "",
        "ending_id": season.ending_id if season.ended else "",
        "end_week": calendar.point(season.time, content, season).week,
        "end_stamp": calendar.stamp_text(season.time, content, season),
        "ended": season.ended,
        "stuck": not season.ended,
        "bots": {side: sum(1 for s in everyone if s.player.bot is not None and s.player.faction == side) for side in SIDES},
    }
    purse = {st.player.name: st.player.stats.get("silver", 0) for st in everyone}
    top = max(raided, key=lambda n: (raided[n], raid_losses[n][1]), default=None)
    worst = max(raid_losses, key=lambda n: raid_losses[n][1], default=None)
    result["raids"] = {
        "total": sum(raided.values()), "tiers": dict(raid_tiers), "victims": len(raided),
        "median": statistics.median(raided.values()) if raided else 0,
        "top": None if top is None else (raided[top], *raid_losses[top], purse.get(top, 0)),
        "worst": None if worst is None else (raided[worst], *raid_losses[worst], purse.get(worst, 0)),
    }
    result["checks"] = checks(result, content)
    return result


SIDE_NAMES = {"guan": "官軍", "huang": "黃巾", "haoqiang": "豪強"}
FRONT_NAMES = {"yingru": "潁川汝南", "nanyang": "南陽", "jizhou": "冀州", "geju": "割據"}


def summary(seed: int, r: dict) -> str:
    """一個種子的結果，印成給人看的幾行。"""
    head = f"種子 {seed}：" + (f"{r['ending']}（{r['end_stamp']} 收季）" if r["ended"] else f"沒收季（停在{r['end_stamp']}）")
    lines = [head + f"　卡住：{'是' if r['stuck'] else '否'}　假人：" + "、".join(
        f"{SIDE_NAMES[s]} {n}" for s, n in r["bots"].items())]
    lines.append("  每週末（潁川汝南/南陽/冀州/割據）：" + "　".join(
        f"{w}:{v['yingru']}/{v['nanyang']}/{v['jizhou']}/{v['geju']}" for w, v in sorted(r["weekly"].items())))
    lines.append(f"  割據首次到（投靠名冊 {r['roster']} 人）：" + "　".join(
        f"{line}＝" + (f"第 {hit[0]} 週（{hit[1]}）" if hit else "沒到") for line, hit in r["geju_first"].items()))
    lines.append("  大事：" + "　".join(
        f"{eid}={v['result']}{'（鎖定）' if v['locked'] else ''}" for eid, v in r["events"].items()))
    if r["missing"]:
        lines.append("  沒結算：" + "、".join(r["missing"]))
    lines.append("  決戰：" + "　".join(f"{eid}={key}" for eid, key in r["showdowns"].items()))
    lines.append("  軍令達成（週:道）：" + "　".join(
        f"{SIDE_NAMES[s]} " + (" ".join(f"{w}:{n}" for w, n in weeks.items()) or "0") for s, weeks in r["orders"].items()))
    lines.append("  升第 2 階：" + "、".join(f"{SIDE_NAMES[s]} {n}" for s, n in r["promoted"].items()))
    raids = r["raids"]
    def victim(row):
        return "沒有" if row is None else f"被截殺 {row[0]} 次、輸 {row[1]} 次、失銀 {row[2]} 兩、失氣血 {row[3]}（季末身上 {row[4]} 兩）"
    lines.append(f"  截殺：共 {raids['total']} 場（" + "、".join(f"{k} {v}" for k, v in sorted(raids["tiers"].items()))
                 + f"）；被截殺過的 {raids['victims']} 人，每人中位數 {raids['median']} 次")
    lines.append(f"    被截殺最多的人：{victim(raids['top'])}；失銀最多的人：{victim(raids['worst'])}")
    c = r["checks"]
    medians = "、".join(f"{FRONT_NAMES[f]} {m}" for f, m in c["medians"].items())
    lines.append(f"  驗收：第 6 週前沒有決定性勝利 {'✔' if c['no_early_decisive'] else '✘'}；"
                 f"戰線週末中位數 {medians} {'✔' if c['medians_ok'] else '✘'}；{'通過' if c['passed'] else '沒通過'}")
    return "\n".join(lines)


def main() -> None:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser()
    parser.add_argument("--seeds", type=int, nargs="+", default=[1, 2, 3])
    parser.add_argument("--factions", type=int, nargs=3, default=[5, 5, 5], metavar=("GUAN", "HUANG", "HAOQIANG"),
                        help="每陣營幾個假人（官軍、黃巾、豪強）")
    parser.add_argument("--hours", type=float, default=60.0, help="最多跑幾個現實小時（週末設定一季 60 小時）")
    parser.add_argument("--tick", type=float, default=60.0, help="假時鐘每一輪走幾秒")
    parser.add_argument("--profile", default="weekend")
    args = parser.parse_args()
    targets = dict(zip(SIDES, args.factions))
    print(profile_line(load_content(ROOT / "content", profile=args.profile), args.profile), flush=True)
    for seed in args.seeds:
        content = load_content(ROOT / "content", profile=args.profile)
        with tempfile.TemporaryDirectory() as tmp:
            try:
                result = run_season(content, Path(tmp) / "sim.db", seed, targets, args.hours, args.tick)
            finally:
                database.close_all()  # 不先關連線，Windows 刪不掉暫存資料夾
        print(summary(seed, result), flush=True)


if __name__ == "__main__":
    main()
