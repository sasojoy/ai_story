"""兵器量表（docs/superpowers/specs/2026-10-09-兵器-design.md 第七節，第一批的部分）：整季機器人跑幾個種子，
比開兵器與關兵器：季末等級、遊歷勝率、修了幾次、季末手上一二三階素材。只量不改。

勝率與場數：state.battles 只留最近 20 場，所以在 observe 裡逐步累計新出現的戰報（記看過的流水號）；只算遊歷與探索野怪
（kind train／wild），大勝與險勝算贏。修幾次：同一把兵器的鋒利度比上一步高就是修了一次（鋒利度只有鐵匠修得上去；換一把、
買新的不算，因為兵器 id 變了）。平均鋒利度是身上有兵器的每一步取平均。

用法：.venv/Scripts/python.exe scripts/measure_weapons.py --seeds 1 2 3 [--profile weekend]
"""
from __future__ import annotations

import argparse
import atexit
import io
import os
import shutil
import sys
import tempfile
from pathlib import Path
from unittest import mock

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
TMP = Path(tempfile.mkdtemp(prefix="measure_weapons_"))
os.environ["TIANXIA_DB"] = str(TMP / "unused.db")  # 別開到 worktree 的 saves/tianxia.db

from tianxia import bot, database, naming  # noqa: E402
from tianxia.content import load_content, profile_line  # noqa: E402
from tianxia.ollama_client import OllamaClient  # noqa: E402
from tianxia.sqlite_world import open_world  # noqa: E402


def _cleanup() -> None:
    """結束時關掉所有資料庫連線再刪暫存資料夾（Windows 上開著的檔刪不掉）。"""
    database.close_all()
    shutil.rmtree(TMP, ignore_errors=True)


atexit.register(_cleanup)


def run(seed: int, profile: str | None, weapons_on: bool) -> dict:
    content = load_content(ROOT / "content", profile=profile)
    content.config.weapons.enabled = weapons_on
    seen: set[int] = set()
    count = {"fights": 0, "wins": 0, "repairs": 0}
    edges: list[int] = []
    last: dict = {"id": None, "edge": None}

    def observe(game) -> None:
        for b in game.state.battles:
            if b.id in seen:
                continue
            seen.add(b.id)
            if b.kind in ("train", "wild"):
                count["fights"] += 1
                count["wins"] += b.tier in ("大勝", "險勝")
        w = game.state.player.weapon
        if w is None:
            last["id"], last["edge"] = None, None
            return
        edges.append(w.edge)
        if last["id"] == w.id and last["edge"] is not None and w.edge > last["edge"]:
            count["repairs"] += 1
        last["id"], last["edge"] = w.id, w.edge


    def refuse(*args, **kwargs):
        raise RuntimeError("量測不連模型")

    # 同 measure_sanren：模型一個都不連（取名走退路字表），每次跑的結果才一樣
    with mock.patch.object(naming, "propose", lambda *a, **k: (None, "")),             mock.patch.object(naming, "pick", lambda *a, **k: (None, "")),             mock.patch.object(OllamaClient, "chat_structured", refuse), mock.patch.object(OllamaClient, "chat_text", refuse),             mock.patch("requests.post", refuse), mock.patch("requests.get", refuse):
        game = bot.play_season(content, seed, world=open_world(TMP / f"s{seed}-{int(weapons_on)}.db"), observe=observe)
    p = game.state.player
    tiers = {1: 0, 2: 0, 3: 0}
    for mid, n in p.materials.items():
        tiers[content.materials[mid].tier] += n
    return {
        "level": p.member.level, "win": count["wins"] / count["fights"] if count["fights"] else 0.0,
        "fights": count["fights"], "repairs": count["repairs"],
        "edge_avg": sum(edges) / len(edges) if edges else None,
        "weapon": p.weapon.name if p.weapon else "—", "mats": tiers, "silver": p.stats.get("silver", 0),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seeds", type=int, nargs="+", default=[1, 2, 3])
    parser.add_argument("--profile", default=None)
    args = parser.parse_args()
    print(profile_line(load_content(ROOT / "content", profile=args.profile), args.profile), flush=True)
    for seed in args.seeds:
        for on in (False, True):
            r = run(seed, args.profile, on)
            edge = "—" if r["edge_avg"] is None else round(r["edge_avg"])
            print(f"種子 {seed} 兵器{'開' if on else '關'}：等級 {r['level']}、遊歷勝率 {r['win']:.0%}（{r['fights']} 場）、"
                  f"修 {r['repairs']} 次、平均鋒利度 {edge}、"
                  f"季末兵器 {r['weapon']}、素材 {r['mats']}、銀兩 {r['silver']}", flush=True)


if __name__ == "__main__":
    main()
