"""稱號與官職普查（重做稱號與官職設計稿第一節；只讀、不改任何東西）。

先把資料庫用 SQLite 的備份 API 抄一份到暫存資料夾，只開那一份（正式站開著也能跑，不碰正式檔）。
算這一季每個角色此刻掙得到的頭銜（名帖那一串 mingtie.earned，含榜單）、官職的階、上一季論功的稱號，
印每一個頭銜有幾個人拿、佔這一季角色的幾成；真人、假人分開數（這支只在主機上跑，數字不給玩家看）。

用法：.venv/Scripts/python.exe scripts/title_census.py [--db saves/tianxia.db] [--profile season21]
"""
from __future__ import annotations

import argparse
import io
import os
import re
import sqlite3
import sys
import tempfile
from collections import Counter
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def _copy(src: Path) -> Path:
    tmp = Path(tempfile.mkdtemp(prefix="title_census_")) / "copy.db"
    with sqlite3.connect(f"file:{src}?mode=ro", uri=True) as a, sqlite3.connect(tmp) as b:
        a.backup(b)
    return tmp


def _family(title: str) -> str:
    """把「善人榜第三」「決戰首功二次」這種收成一類（善人榜前十、決戰首功），其餘照原字。"""
    t = re.sub(r"^第\d+季 ", "（往季）", title)
    t = re.sub(r"榜第[一二三四五六七八九十]$", "榜前十", t)
    t = re.sub(r"(首功|絕學)[一二三四五六七八九十\d]+(次|門)$", r"\1", t)
    t = re.sub(r"^.+(親傳|的本命兵器|的知交|的帖友|門下)$", r"某某\1", t)
    t = re.sub(r"^神器【.+】之主$", "神器之主", t)
    return t


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=os.environ.get("TIANXIA_DB", str(ROOT / "saves" / "tianxia.db")))
    ap.add_argument("--profile", default=None)
    args = ap.parse_args()
    copy = _copy(Path(args.db))
    os.environ["TIANXIA_DB"] = str(copy)

    from tianxia import leaderboard, ranks
    from tianxia.characters import open_characters
    from tianxia.content import load_content, serving_profile
    from tianxia.features.peers import mingtie
    from tianxia.sqlite_world import open_world

    content = load_content(ROOT / "content", args.profile or serving_profile())
    world, chars = open_world(copy), open_characters(copy)
    season, number = world.get_season(), world.get_season_number()
    board = leaderboard.compute_boards(content, world, chars)
    people = [s for s in chars.all() if s.player.season_number == number]
    kinds = {"真人": [s for s in people if not s.player.bot], "假人": [s for s in people if s.player.bot]}
    print(f"第 {number} 季，角色 {len(people)}（真人 {len(kinds['真人'])}、假人 {len(kinds['假人'])}），季時間第 {season.time / 86400:.1f} 天")
    for label, group in kinds.items():
        if not group:
            continue
        tally, raw, ranks_seen = Counter(), Counter(), Counter()
        for s in group:
            s.world = season
            got = mingtie.earned(s, content, world, board)
            raw.update(set(got))
            tally.update({_family(t) for t in got})
            ranks_seen[(s.player.faction or "散人", ranks.rank_of(s))] += 1
            if s.player.season_title:
                tally[f"論功：{s.player.season_title}"] += 1
        n = len(group)
        print(f"\n【{label}】{n} 人")
        print("  官職（陣營, 階）：" + "、".join(f"{f}{r}階 {c}" for (f, r), c in sorted(ranks_seen.items())))
        for t, c in tally.most_common():
            print(f"  {t}：{c} 人（{c / n:.0%}）")
        print("  沒有任何頭銜：", sum(1 for s in group if not mingtie.earned(s, content, world, board)), "人")
        if season.ended:  # 收季了：這一季論功的結果（下一季開局才掛到 season_title 上）
            tiers = Counter(season.final_tiers[s.player.name].title or "（沒有階）" for s in group if s.player.name in season.final_tiers)
            print("  這一季論功：" + "、".join(f"{t} {c} 人（{c / n:.0%}）" for t, c in tiers.most_common()))


if __name__ == "__main__":
    main()
