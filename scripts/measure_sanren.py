"""散人對陣營：一季下來誰長得比較多（PM 2026-10-08 派工「加強散人玩法」：遊俠名號＋懸賞榜，目標是兩邊差不多）。只量、不改數字。

整季機器人（bot.play_season，真實 content/），每個種子跑兩次、各自一個資料庫：
- 散人：一路不投靠（選單上的投靠、會讓人入陣營的拜師都拿掉），照遊俠名號與懸賞榜長；
- 陣營：一看到投靠就投、照軍令與晉升長（投靠哪一個照選單上第一個出現的）。
其他照整季機器人隨機玩。模型一律不連（同 measure_forge）。

印每個種子、每一邊的季末：等級、本人威力、全隊威力（本人＋同伴＋部下）、銀兩、名望、同伴數、部下數，
散人另印俠名與名號的階、懸賞完成幾張；陣營另印階與貢獻。最後一行是兩邊的中位數。

用法：.venv/Scripts/python.exe scripts/measure_sanren.py --seeds 1 2 3 4 5 [--profile weekend]
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
TMP = Path(tempfile.mkdtemp(prefix="measure_sanren_"))
os.environ["TIANXIA_DB"] = str(TMP / "unused.db")  # 別開到 worktree 的 saves/tianxia.db

from tianxia import bot, database, encounter, naming, ranger, ranks, team  # noqa: E402
from tianxia.content import load_content  # noqa: E402
from tianxia.ollama_client import OllamaClient  # noqa: E402
from tianxia.sqlite_world import open_world  # noqa: E402

COLUMNS = ("等級", "本人威力", "全隊威力", "銀兩", "名望", "同伴", "部下")


def _cleanup() -> None:
    database.close_all()
    shutil.rmtree(TMP, ignore_errors=True)


atexit.register(_cleanup)


def _joins_faction(game, option_id: str) -> bool:
    """這個選項會讓人進陣營：投靠，或拜入陣營名下的門派。"""
    if option_id.startswith("faction:"):
        return True
    s, c = game.state, game.content
    if option_id.startswith("choice:") and option_id.partition(":")[2].isdigit() and s.pending_event:
        choice = c.events[s.pending_event].choices[int(option_id.partition(":")[2])]
        sect = choice.effect.join_sect
        return sect is not None and any(sect in f.sects for f in c.scenario.factions)
    return False


def _power(game) -> tuple[float, float]:
    s, c, w = game.state, game.content, game.world
    members, _, boosts = team._fighters(s, c, w)
    arts = team.team_arts(s, c, w)
    powers = [encounter.member_power(m, arts, None, 1.0, b) for m, b in zip(members, boosts, strict=True)]
    return powers[0], sum(powers)


def measure(seed: int, profile: str | None, side: str) -> dict:
    content = load_content(ROOT / "content", profile=profile)
    world = open_world(TMP / f"{side}{seed}.db")
    original_pick = bot.pick

    def pick(game, options, rng):
        if side == "散人":
            options = [o for o in options if not _joins_faction(game, o.id)]
        elif game.state.player.faction is None:
            ids = [o.id for o in options]
            if "faction:confirm" in ids:
                return "faction:confirm"
            join = next((i for i in ids if i.startswith("faction:") and i != "faction:cancel"), None)
            if join is not None:
                return join
        return original_pick(game, options, rng)

    def refuse(*args, **kwargs):
        raise RuntimeError("量測不連模型")

    with mock.patch.object(naming, "propose", lambda *a, **k: (None, "")), \
            mock.patch.object(naming, "pick", lambda *a, **k: (None, "")), \
            mock.patch.object(OllamaClient, "chat_structured", refuse), mock.patch.object(OllamaClient, "chat_text", refuse), \
            mock.patch("requests.post", refuse), mock.patch("requests.get", refuse), \
            mock.patch.object(bot, "pick", pick):
        game = bot.play_season(content, seed, world=world)
    s, c = game.state, game.content
    p = s.player
    mine, whole = _power(game)
    row = {
        "等級": p.member.level, "本人威力": round(mine), "全隊威力": round(whole), "銀兩": p.stats.get("silver", 0),
        "名望": p.stats.get("fame", 0), "同伴": len(p.team), "部下": len(p.followers),
        "faction": p.faction,
    }
    if p.faction is None:
        row["俠名"] = ranger.points(s)
        row["名號"] = ranger.tier(s, c)
        row["懸賞"] = getattr(p, "bounties_done", 0)
    else:
        row["階"] = ranks.rank_of(s)
        row["貢獻"] = p.contrib
    return row


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--seeds", type=int, nargs="+", default=[1, 2, 3])
    parser.add_argument("--profile", default="weekend")
    args = parser.parse_args()
    rows: dict[str, list[dict]] = {"散人": [], "陣營": []}
    for seed in args.seeds:
        for side in rows:
            row = measure(seed, args.profile, side)
            rows[side].append(row)
            extra = (f"俠名 {row['俠名']}（第 {row['名號']} 階）懸賞 {row['懸賞']}" if side == "散人"
                     else f"{row['faction']} 第 {row['階']} 階 貢獻 {row['貢獻']}")
            print(f"種子 {seed} {side}：" + "　".join(f"{k} {row[k]}" for k in COLUMNS) + f"　{extra}", flush=True)
    for side, side_rows in rows.items():
        print(f"{side}中位數：" + "　".join(f"{k} {statistics.median(r[k] for r in side_rows):g}" for k in COLUMNS))


if __name__ == "__main__":
    main()
