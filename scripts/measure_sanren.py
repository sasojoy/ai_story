"""散人對陣營：一季下來誰長得比較多（PM 2026-10-08 派工「加強散人玩法」：遊俠名號＋懸賞榜，目標是兩邊差不多）。只量、不改數字。

整季機器人（bot.play_season，真實 content/），每個種子跑兩次、各自一個資料庫：
- 散人：一路不投靠（選單上的投靠、會讓人入陣營的拜師都拿掉），照遊俠名號與懸賞榜長；
- 陣營：一看到投靠就投、照軍令與晉升長（投靠哪一個照選單上第一個出現的）。
兩邊都是「有目標的玩家」：一半的時候照手上的懸賞與軍令走、到了就做（_steer），另一半照整季機器人隨機玩；
城裡的懸賞榜兩邊都會去揭（bot.take_bounties）。模型一律不連（同 measure_forge）。

印每個種子、每一邊的季末：等級、本人威力、全隊威力（本人＋同伴＋部下）、銀兩、名望、同伴數、部下數，
散人另印俠名與名號的階、懸賞完成幾張；陣營另印階與貢獻。最後一行是兩邊的中位數。

用法：.venv/Scripts/python.exe scripts/measure_sanren.py --seeds 1 2 3 4 5 [--profile weekend] [--bare]
（--bare 是對照組：拿掉懸賞榜與名號的經驗加成，看這一版之前散人跟陣營差多少）
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

from tianxia import bot, bot_policy, bounties, database, encounter, naming, orders, ranger, ranks, team  # noqa: E402
from tianxia.content import load_content  # noqa: E402
from tianxia.ollama_client import OllamaClient  # noqa: E402
from tianxia.sqlite_world import open_world  # noqa: E402

STEER = 0.5  # 有目標的玩家：一半的時候照手上的懸賞、軍令走
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


def _steer(game, options, rng) -> str | None:
    """有目標的玩家（兩邊一樣）：一半的時候照手上的事走——懸賞（散人、陣營都能接）與這週的軍令（陣營）要去的地方、
    到了就做那件事（討伐、攻城、截糧：遊歷；打探：探索；守城：守勢行動），手上沒事要趕就在這裡遊歷；另一半照整季機器人隨機玩。"""
    if game.state.pending_event or rng.random() >= STEER:
        return None
    s, c = game.state, game.content
    ids = {o.id for o in options}
    here = s.player.location
    work = {b.kind for b in bounties.mine(s, c) if b.location == here}
    if "act:train" in ids and ("strike" in work or orders.win_counts(s, c, s.player.faction, here)):
        return "act:train"
    if "act:explore" in ids and "scout" in work:
        return "act:explore"
    if "act:duty" in ids and orders.duty_counts(s, c, s.player.faction, here):
        return "act:duty"
    places = bounties.targets(s, c) + orders.targets(s, c, s.player.faction)
    hop = bot_policy.next_hop(game, places) if places else None
    move = next((i for i in ids if i.startswith("move:") and i.partition(":")[2].partition(":")[0] == hop), None)
    if move is not None:
        return move
    return "act:train" if "act:train" in ids else None  # 手上沒事要趕：這裡有得打就打（兩邊一樣；陣營的人碰上自己人是操練）


def _power(game) -> tuple[float, float]:
    s, c, w = game.state, game.content, game.world
    members, _, boosts = team._fighters(s, c, w)
    arts = team.team_arts(s, c, w)
    powers = [encounter.member_power(m, arts, None, 1.0, b) for m, b in zip(members, boosts, strict=True)]
    return powers[0], sum(powers)


def measure(seed: int, profile: str | None, side: str, bare: bool = False) -> dict:
    content = load_content(ROOT / "content", profile=profile)
    if bare:  # 對照組：沒有懸賞榜、名號沒有經驗加成（這一版之前的散人）
        content.config.bounties.kinds = []
        content.config.ranger.exp_per_tier = 0.0
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
        steered = _steer(game, options, rng)
        return steered if steered is not None else original_pick(game, options, rng)

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
        row["懸賞"] = p.bounties_done
    else:
        row["階"] = ranks.rank_of(s)
        row["貢獻"] = p.contrib
    return row


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--seeds", type=int, nargs="+", default=[1, 2, 3])
    parser.add_argument("--profile", default="weekend")
    parser.add_argument("--bare", action="store_true", help="對照組：拿掉懸賞榜與名號的經驗加成")
    args = parser.parse_args()
    rows: dict[str, list[dict]] = {"散人": [], "陣營": []}
    for seed in args.seeds:
        for side in rows:
            row = measure(seed, args.profile, side, bare=args.bare)
            rows[side].append(row)
            extra = (f"俠名 {row['俠名']}（第 {row['名號']} 階）懸賞 {row['懸賞']}" if side == "散人"
                     else f"{row['faction']} 第 {row['階']} 階 貢獻 {row['貢獻']}")
            print(f"種子 {seed} {side}：" + "　".join(f"{k} {row[k]}" for k in COLUMNS) + f"　{extra}", flush=True)
    for side, side_rows in rows.items():
        print(f"{side}中位數：" + "　".join(f"{k} {statistics.median(r[k] for r in side_rows):g}" for k in COLUMNS))


if __name__ == "__main__":
    main()
