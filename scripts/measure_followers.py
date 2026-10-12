"""部下佔全隊威力的比例（PM 2026-10-12 派工「讓部下真的有用」）：季初、季中、季末，改動前後對照。只量、不改數字。

整季機器人（bot.play_season，真實 content/，預設週末設定：第一季規則開著），每個種子、每個陣營一個資料庫、一個機器人：
一開局就投靠、有召見就去應召、一半的時候這裡有得打就遊歷（同 measure_promotion 的「勤」），模型一律不連。
每一場部下上陣的仗（遊歷、野怪、劇情戰、挑戰本人）記一筆：部下的威力 ÷ 全隊威力（team.follower_share，照那一場的對手算）。
季分三段（季初、季中、季末各三分之一），印每段的平均比例（只算帶著部下的仗）與那一段帶著部下的仗數。
「前」是部下武學不長（levels_per_cheng 設成 999，成數停在模板的 3 成），「後」是現在的設定。
決戰的份量另算：季末帶著幾名部下、強攻與奇襲多幾成（Config.follower.battle_per × 人數）。

用法：.venv/Scripts/python.exe scripts/measure_followers.py --seeds 1 2 3 4 5 [--profile weekend]
"""
from __future__ import annotations

import argparse
import atexit
import io
import os
import shutil
import statistics
import sys
import tempfile
from pathlib import Path
from unittest import mock

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
TMP = Path(tempfile.mkdtemp(prefix="measure_followers_"))
os.environ["TIANXIA_DB"] = str(TMP / "unused.db")  # 別開到 worktree 的 saves/tianxia.db

from tianxia import battlelog, bot, bot_policy, calendar, database, naming, team  # noqa: E402
from tianxia.content import load_content  # noqa: E402
from tianxia.ollama_client import OllamaClient  # noqa: E402
from tianxia.sqlite_world import open_world  # noqa: E402
from tianxia.world_state import season_length_days  # noqa: E402

FACTIONS = ("guan", "huang", "haoqiang")
GRIND = 0.5  # 一半的時候這裡有得打就遊歷（measure_promotion 的「勤」）
THIRDS = ("季初", "季中", "季末")


def _cleanup() -> None:
    database.close_all()
    shutil.rmtree(TMP, ignore_errors=True)


atexit.register(_cleanup)


def _hop(game, options, places):
    hop = bot_policy.next_hop(game, places)
    return next((o.id for o in options if o.id.startswith("move:") and o.id.partition(":")[2].partition(":")[0] == hop), None)


def _hop(game, options, places):
    hop = bot_policy.next_hop(game, places)
    return next((o.id for o in options if o.id.startswith("move:") and o.id.partition(":")[2].partition(":")[0] == hop), None)


def measure(seed: int, profile: str | None, faction: str, grow: bool) -> dict:
    content = load_content(ROOT / "content", profile=profile)
    if not grow:
        content.config.follower.levels_per_cheng = 999
    world = open_world(TMP / f"{faction}{seed}{'g' if grow else 'f'}.db")
    original_pick, original_record = bot.pick, battlelog.new_record
    shares: list[tuple[float, float]] = []  # （季曆的第幾成, 部下佔全隊的比例）

    def record(state, c, w, squad, result, kind, event=""):
        if kind in battlelog.AID_KINDS and team.follower_rows(state, c):
            theirs, ours = team.follower_share(state, c, w, squad)
            if theirs + ours > 0:
                shares.append((state.world.time / (season_length_days(state.world, c) * calendar.DAY), theirs / (theirs + ours)))
        return original_record(state, c, w, squad, result, kind, event)

    def pick(game, options, rng):
        p = game.state.player
        ids = [o.id for o in options]
        if game.state.pending_event is None:
            if p.faction is None:
                if "faction:confirm" in ids:
                    return "faction:confirm"
                if f"faction:{faction}" in ids:
                    return f"faction:{faction}"
                options = [o for o in options if not o.id.startswith("faction:")]
                move = _hop(game, options, list(content.scenario.faction(faction).join_at))
                if move is not None:
                    return move
            elif p.summons is not None:
                if "act:summons" in ids:
                    return "act:summons"
                move = _hop(game, options, [p.summons.location]) if p.summons.location else None
                if move is not None:
                    return move
            elif "act:train" in ids and rng.random() < GRIND:
                return "act:train"
        return original_pick(game, options, rng)

    def refuse(*args, **kwargs):
        raise RuntimeError("量測不連模型")

    with mock.patch.object(naming, "propose", lambda *a, **k: (None, "")), \
            mock.patch.object(naming, "pick", lambda *a, **k: (None, "")), \
            mock.patch.object(OllamaClient, "chat_structured", refuse), mock.patch.object(OllamaClient, "chat_text", refuse), \
            mock.patch("requests.post", refuse), mock.patch("requests.get", refuse), \
            mock.patch.object(battlelog, "new_record", record), mock.patch.object(bot, "pick", pick):
        game = bot.play_season(content, seed, world=world)
    assert calendar.season_one_on(game.state.world, content), "這份量表量的是第一季規則開著的季"
    p = game.state.player
    thirds = {name: [s for t, s in shares if i / 3 <= t < (i + 1) / 3 or (i == 2 and t >= 1)] for i, name in enumerate(THIRDS)}
    return {
        "thirds": thirds, "部下": len(p.followers), "等級": p.member.level,
        "決戰": len(team.follower_rows(game.state, content)) * content.config.follower.battle_per,
    }


def _avg(values: list[float]) -> str:
    return f"{statistics.mean(values) * 100:4.1f}%（{len(values):3d} 場）" if values else "    —（  0 場）"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--seeds", type=int, nargs="+", default=[1, 2, 3])
    parser.add_argument("--profile", default="weekend")
    args = parser.parse_args()
    profile = None if args.profile in ("", "none", "default") else args.profile
    for grow, label in ((False, "前（部下不長）"), (True, "後（現在）")):
        pooled: dict[str, list[float]] = {name: [] for name in THIRDS}
        print(f"== {label} ==", flush=True)
        for faction in FACTIONS:
            for seed in args.seeds:
                row = measure(seed, profile, faction, grow)
                for name in THIRDS:
                    pooled[name] += row["thirds"][name]
                print(
                    f"{faction} 種子 {seed}：" + "　".join(f"{n} {_avg(row['thirds'][n])}" for n in THIRDS)
                    + f"　季末 {row['等級']} 級・部下 {row['部下']}・決戰強攻奇襲 +{row['決戰'] * 100:.0f}%",
                    flush=True,
                )
        print("合計：" + "　".join(f"{n} {_avg(pooled[n])}" for n in THIRDS), flush=True)


if __name__ == "__main__":
    main()
