"""武學與成長計畫五 Task 8：量一季裡三種合成「第一次的組合數、合到舊的比例、模型呼叫數」（設計 12.5）。只量、不改數字。

整季機器人（bot.play_season，真實 content/），一個 seed 一季、一個機器人獨佔一個資料庫：量到的是「一個人一季」，
是全服的下限——多人時候選更多，合到舊的會更常發生；而且單人時合到舊的一定合到機器人自己已經有的那一門
（候選全是它自己合出來的：不收錢、也沒拿到東西），所以合到舊的的比例不能拿來當全服的比例。

模型一律不連。「模型呼叫」數的是決定點，不是 HTTP：把 naming.propose（首次出現的配方要取名）與 naming.pick
（合到舊的、候選兩個以上要挑一個）換成只記一筆、回 (None, "") 的替身（跟真的連不上時回的一樣：取名走退路字表、
挑走規則），所以數到的就是真的上線時會送給模型的次數。不用 Game 的 client 來數：Game._quick_client 在鎖內第一次
失敗之後（ModelBudget.gave_up）就回 None，而整季機器人從來不歸零，之後每一次都不會真的呼叫 chat_structured。
chat_text／chat_structured 與 requests 另外擋成一律丟錯，其他地方（裝飾句、對話）也不會連到真的 Ollama。

另外記體力（為了判斷 bot.FORGE_RESERVE 留 20 夠不夠）：整季步數、體力低於 10 的步數（探索與遊歷要 10，
見底就選不到）、合成被保留量擋下幾次、真的合成幾次。

用法：.venv/Scripts/python.exe scripts/measure_forge.py --seeds 1 2 3 4 5 [--profile weekend] [--reserve 0]
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
from collections import Counter
from pathlib import Path
from unittest import mock

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
TMP = Path(tempfile.mkdtemp(prefix="measure_forge_"))
os.environ["TIANXIA_DB"] = str(TMP / "unused.db")  # 別開到 worktree 的 saves/tianxia.db

from tianxia import bot, database, library, naming  # noqa: E402
from tianxia.content import load_content  # noqa: E402
from tianxia.engine import Game  # noqa: E402
from tianxia.ollama_client import OllamaClient  # noqa: E402
from tianxia.sqlite_world import open_world  # noqa: E402

KINDS = (("融", "武學＋意境"), ("兼", "武學＋武學"), ("合", "意境＋意境"))
STARVED_BELOW = 10  # 探索與遊歷各要 10 點體力（Config.action_cost）：低於這個就選不到


def _cleanup() -> None:
    """結束時清掉暫存的資料庫：先關掉所有連線（Windows 上開著的檔刪不掉），免得每跑一次留一個 measure_forge_* 資料夾。"""
    database.close_all()
    shutil.rmtree(TMP, ignore_errors=True)


atexit.register(_cleanup)


def _recipes(world, table: str, target: str) -> dict[str, tuple[int, int]]:
    """{配方鍵的第一個字: (第一次的組合數, 其中合到舊的)}。一門東西最早那一列是長出它的配方，之後指向它的都是合到舊的。"""
    with world.db.snapshot() as conn:
        rows = conn.execute(
            f"SELECT substr(r.key, 1, 1) AS kind, COUNT(*) AS keys, "
            f"SUM(r.rowid != (SELECT MIN(o.rowid) FROM {table} o WHERE o.season = r.season AND o.{target} = r.{target})) "
            f"AS landed FROM {table} r GROUP BY kind"
        ).fetchall()
    return {row["kind"]: (row["keys"], row["landed"] or 0) for row in rows}


def measure(seed: int, profile: str | None, reserve: int) -> tuple[dict[str, tuple[int, int]], Counter]:
    content = load_content(ROOT / "content", profile=profile)
    world = open_world(TMP / f"seed{seed}.db")
    calls: Counter = Counter()  # 取名、挑（模型呼叫的決定點）；forge*／made*（開爐）；held／steps／starved（體力）

    def propose(client, content, messages, budget=None, person=None):
        calls["取名"] += 1
        return None, ""

    def pick(client, messages, choices, budget=None):
        calls["挑"] += 1
        return None, ""

    def refuse(*args, **kwargs):
        raise RuntimeError("量測不連模型")

    original_round, original_forge = bot.forge_and_cultivate, Game.forge

    def counted_round(game, rng):
        p = game.state.player
        arts = library.owned_arts(game.state)
        could = bool(p.insights and arts) or len(arts) >= 2  # 結構上有東西可合（跟 bot.forge_and_cultivate 一樣的判斷）
        if could and p.stamina < bot.FORGE_RESERVE:
            calls["held"] += 1  # 有東西可合、但體力沒到保留量：這一輪的合成被擋下
        original_round(game, rng)

    def counted_forge(self, art_id, insight_ids, proposed=None, other_art=None):
        before = library.held_count(self.state)
        out = original_forge(self, art_id, insight_ids, proposed=proposed, other_art=other_art)
        kind = "兼" if other_art else "融" if art_id else "合"
        calls[f"forge{kind}"] += 1
        text = "".join(out or [])
        if library.held_count(self.state) > before:
            calls[f"made{kind}"] += 1  # 多了一門武學或一個意境：真的合成了一爐（被拒絕、合到你已經有的不算）
            if "竟是" in text:
                calls[f"regain{kind}"] += 1  # 合到舊的、而且是機器人自己早先合出來、後來熔掉的那一門：拿回來，照常收費
        elif "熄了" in text or "融不到一塊" in text:
            calls["burnt"] += 1  # 名字都被用掉、這一爐沒合成（取了名、也叫了模型，卻沒登記）
        elif "已經有了" in text or "已經悟得了" in text:
            calls[f"free{kind}"] += 1  # 合到舊的、而且那一門機器人還留著：什麼都不收（機器人先用 *_problem 擋掉已知的配方，所以這裡都是新配方）
        return out

    def observe(game):
        calls["steps"] += 1
        if game.state.player.stamina < STARVED_BELOW:
            calls["starved"] += 1

    with mock.patch.object(naming, "propose", propose), mock.patch.object(naming, "pick", pick), \
            mock.patch.object(OllamaClient, "chat_structured", refuse), mock.patch.object(OllamaClient, "chat_text", refuse), \
            mock.patch("requests.post", refuse), mock.patch("requests.get", refuse), \
            mock.patch.object(bot, "FORGE_RESERVE", reserve), mock.patch.object(bot, "forge_and_cultivate", counted_round), \
            mock.patch.object(Game, "forge", counted_forge):
        game = bot.play_season(content, seed, world=world, observe=observe)
    calls["final_stamina"] = round(game.state.player.stamina)
    return _recipes(world, "recipes", "skill_name") | _recipes(world, "insight_recipes", "insight_name"), calls


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seeds", type=int, nargs="+", default=[1, 2, 3, 4, 5])
    parser.add_argument("--profile", default=None)
    parser.add_argument("--reserve", type=int, default=bot.FORGE_RESERVE, help="bot.FORGE_RESERVE 要量哪個值（預設是 bot 現在的）")
    args = parser.parse_args()
    totals: dict[str, list[int]] = {"keys": [], "landed": [], "calls": [], "starved": []}
    print(f"設定：{args.profile or '預設'}，FORGE_RESERVE {args.reserve}")
    for seed in args.seeds:
        recipes, calls = measure(seed, args.profile, args.reserve)
        parts = []
        for prefix, label in KINDS:
            keys, landed = recipes.get(prefix, (0, 0))
            share = f"{landed / keys:.0%}" if keys else "—"
            parts.append(f"{label} {keys}（合到舊的 {landed}，{share}）")
        keys = sum(k for k, _ in recipes.values())
        landed = sum(n for _, n in recipes.values())
        model = calls["取名"] + calls["挑"]
        totals["keys"].append(keys)
        totals["landed"].append(landed)
        totals["calls"].append(model)
        totals["starved"].append(calls["starved"])
        print(f"seed {seed}：第一次的組合 {keys}；" + "；".join(parts) + f"；模型呼叫 {model}（取名 {calls['取名']}、挑 {calls['挑']}）")
        made = "、".join(f"{label} {calls['made' + prefix]}/{calls['forge' + prefix]}" for prefix, label in KINDS)
        print(f"        開爐（合成出東西／按了幾次）：{made}")
        landed_split = "、".join(
            f"{label} 免費 {calls['free' + prefix]}・拿回熔掉的 {calls['regain' + prefix]}" for prefix, label in KINDS
        )
        print(f"        合到舊的的去向（機器人只會合到自己合出來的）：{landed_split}")
        print(
            f"        名字都被用掉、沒合成的 {calls['burnt']} 爐；"
            f"體力：{calls['steps']} 步裡低於 {STARVED_BELOW} 的 {calls['starved']} 步；合成被保留量擋下 {calls['held']} 輪；"
            f"季末體力 {calls['final_stamina']}"
        )
    print(
        f"中位數：第一次的組合 {statistics.median(totals['keys'])}、合到舊的 {statistics.median(totals['landed'])}、"
        f"模型呼叫 {statistics.median(totals['calls'])}、體力見底的步數 {statistics.median(totals['starved'])}"
    )


if __name__ == "__main__":
    main()
