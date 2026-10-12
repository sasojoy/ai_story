"""晉升與部下在第一季規則關著的季（beta）要多久（PM 2026-10-12 派工：企劃者問「部下現在是不是沒有作用」，晉升與部下拆出開關）。
只量、不改數字。

整季機器人（bot.play_season，真實 content/，預設設定：第一季規則關著），每個種子、每個陣營一個資料庫、一個機器人：
- 一開局就往那個陣營的投靠點走、投靠（同 measure_sanren 的陣營那一邊）；
- 手上有召見就往召見的地點走、到了就應召（伺服器假人照 bot_policy 也會這樣走）；
- 其餘的步數：「勤」一半的時候這裡有得打就遊歷（替陣營出力），另一半照整季機器人隨機玩；「隨」全照整季機器人隨機玩。
模型一律不連（同 measure_forge）。

印每個種子、每個陣營：第幾天投靠、第幾天貢獻到第 2 階的門檻（rank2_contrib）、第幾天升上第 2 階（拿到部下）、
季末的階、貢獻與部下數；天是這一季的天（世界秒 ÷ 一天），後面括號是一季的幾成。最後一行是各陣營的中位數（沒升上的不算）。

用法：.venv/Scripts/python.exe scripts/measure_promotion.py --seeds 1 2 3 4 5 [--style 勤|隨] [--profile none]
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
TMP = Path(tempfile.mkdtemp(prefix="measure_promotion_"))
os.environ["TIANXIA_DB"] = str(TMP / "unused.db")  # 別開到 worktree 的 saves/tianxia.db

from tianxia import bot, bot_policy, calendar, database, naming  # noqa: E402
from tianxia.content import load_content  # noqa: E402
from tianxia.ollama_client import OllamaClient  # noqa: E402
from tianxia.sqlite_world import open_world  # noqa: E402
from tianxia.world_state import season_length_days  # noqa: E402

FACTIONS = ("guan", "huang", "haoqiang")
GRIND = 0.5  # 「勤」：一半的時候這裡有得打就遊歷


def _cleanup() -> None:
    database.close_all()
    shutil.rmtree(TMP, ignore_errors=True)


atexit.register(_cleanup)


def _hop(game, options, places):
    hop = bot_policy.next_hop(game, places)
    return next((o.id for o in options if o.id.startswith("move:") and o.id.partition(":")[2].partition(":")[0] == hop), None)


def measure(seed: int, profile: str | None, faction: str, style: str) -> dict:
    content = load_content(ROOT / "content", profile=profile)
    world = open_world(TMP / f"{faction}{seed}.db")
    original_pick = bot.pick
    marks: dict[str, float] = {}

    def note(game) -> None:
        p, now = game.state.player, game.state.world.time
        if p.faction is not None:
            marks.setdefault("投靠", now)
        if p.contrib >= content.config.rank2_contrib:
            marks.setdefault("門檻", now)
        if p.rank >= 2:
            marks.setdefault("第 2 階", now)

    def pick(game, options, rng):
        note(game)
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
            elif style == "勤" and "act:train" in ids and rng.random() < GRIND:
                return "act:train"
        return original_pick(game, options, rng)

    def refuse(*args, **kwargs):
        raise RuntimeError("量測不連模型")

    with mock.patch.object(naming, "propose", lambda *a, **k: (None, "")), \
            mock.patch.object(naming, "pick", lambda *a, **k: (None, "")), \
            mock.patch.object(OllamaClient, "chat_structured", refuse), mock.patch.object(OllamaClient, "chat_text", refuse), \
            mock.patch("requests.post", refuse), mock.patch("requests.get", refuse), \
            mock.patch.object(bot, "pick", pick):
        game = bot.play_season(content, seed, world=world)
    note(game)
    w = game.state.world
    assert not calendar.season_one_on(w, content), "這份量表量的是第一季規則關著的季"
    p = game.state.player
    return {
        "marks": {k: v / calendar.DAY for k, v in marks.items()}, "季長": season_length_days(w, content),
        "階": p.rank, "貢獻": p.contrib, "部下": len(p.followers),
    }


def _day(row: dict, key: str) -> str:
    day = row["marks"].get(key)
    return "—" if day is None else f"{day:.1f}（{day / row['季長'] * 100:.0f}%）"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--seeds", type=int, nargs="+", default=[1, 2, 3])
    parser.add_argument("--style", default="勤", choices=("勤", "隨"))
    parser.add_argument("--profile", default="none")
    args = parser.parse_args()
    profile = None if args.profile in ("", "none", "default") else args.profile
    for faction in FACTIONS:
        rows = []
        for seed in args.seeds:
            row = measure(seed, profile, faction, args.style)
            rows.append(row)
            print(
                f"{faction} 種子 {seed}：投靠 {_day(row, '投靠')}　到門檻 {_day(row, '門檻')}　升第 2 階 {_day(row, '第 2 階')}"
                f"　季末 第 {row['階']} 階・貢獻 {row['貢獻']}・部下 {row['部下']}",
                flush=True,
            )
        done = [r["marks"]["第 2 階"] for r in rows if "第 2 階" in r["marks"]]
        reach = [r["marks"]["門檻"] for r in rows if "門檻" in r["marks"]]
        print(
            f"{faction} 中位數：到門檻 第 {statistics.median(reach):.1f} 天" if reach else f"{faction} 中位數：沒有人到門檻",
            f"　升第 2 階 第 {statistics.median(done):.1f} 天（{len(done)}/{len(rows)} 個種子升上）" if done else "　沒有人升上",
            f"　季長 {rows[0]['季長']:.0f} 天",
            sep="",
        )


if __name__ == "__main__":
    main()
