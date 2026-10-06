"""悟意境（悟意境設計第零節）：量一季裡一個人「有所感」幾次、悟到幾個意境（基本的、自己的）、要請模型取名幾次。只量、不改數字。

整季機器人（bot.play_season，真實 content/），一個 seed 一季、一個機器人獨佔一個資料庫：量到的是「一個人一季」。
機器人挑做法有 bot.SENSE_RIGHT 的機會挑對、進了感悟狀態有 bot.SENSE_DRAW 的機會畫一筆（glyph.SAMPLES 裡隨便一筆），
真人看得懂場景、會自己畫，所以「選錯」會比這裡少、「自己的意境」會比這裡多一點。

模型一律不連。「模型呼叫」數的是決定點：insight_llm.name（悟到自己的意境要取名）與 naming.propose 裡合併到私有意境的
那幾次（有私有意境的合併每次都要取名），換成只記一筆、回「沒取到」的替身（跟真的連不上時一樣：走退路字表）。真人送圖：
看圖沒取到時同一次會再問一次文字（最多兩趟），畫布出現時另有一個暖機請求（不取名，不算在這裡）。
--old 把有所感的場景拿掉，量舊的做法（探索悟意境那一支直接悟到基本意境）當對照。

用法：.venv/Scripts/python.exe scripts/measure_insight.py --seeds 1 2 3 4 5 [--profile weekend] [--old]
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
TMP = Path(tempfile.mkdtemp(prefix="measure_insight_"))
os.environ["TIANXIA_DB"] = str(TMP / "unused.db")  # 別開到這份 clone 的 saves/tianxia.db

from tianxia import bot, database, insight_llm, insights, library, naming, sensing  # noqa: E402
from tianxia.content import load_content  # noqa: E402
from tianxia.ollama_client import OllamaClient  # noqa: E402
from tianxia.sqlite_world import open_world  # noqa: E402


def _cleanup() -> None:
    database.close_all()
    shutil.rmtree(TMP, ignore_errors=True)


atexit.register(_cleanup)


def measure(seed: int, profile: str | None, old: bool) -> Counter:
    content = load_content(ROOT / "content", profile=profile)
    if old:
        content.insight_scenes = {}
    world = open_world(TMP / f"seed{seed}{'old' if old else ''}.db")
    n: Counter = Counter()
    real_start, real_choose, real_finish, real_learn = sensing.start, sensing.choose, sensing.finish, insights.learn

    def start(state, content, scene, rng):
        n["有所感"] += 1
        return real_start(state, content, scene, rng)

    def choose(state, content, index, rng):
        out = real_choose(state, content, index, rng)
        text = "".join(out)
        n["選錯" if "心浮氣躁" in text else "沒擲中" if "差一點" in text else "擲中" if "凝住" in text else "其他"] += 1
        return out

    def finish(state, content, world, req, proposed=None, client=None):
        msgs, own, by_model = real_finish(state, content, world, req, proposed, client)
        if msgs != [sensing.STALE]:
            n["畫了" if req.raw is not None else "順其自然"] += 1
            n["自己的意境" if own is not None else "落回基本意境"] += 1
            if req.needs_name:  # 伺服器上每一張要取名的單都會在鎖外請模型（整季機器人在鎖內的額度早就用完，數不到真的呼叫）
                n["取名・感悟"] += 1
        return msgs, own, by_model

    def learn(state, content, world, insight_id):
        out = real_learn(state, content, world, insight_id)
        text = "".join(out)
        if "你悟得了" in text:
            n["悟到新的基本意境"] += 1
        elif "又悟到一次" in text:
            n["重複化成心得"] += 1
        return out

    def name(client, content, facts, image="", budget=None, person=None):
        return None, "", ""

    def propose(client, content, messages, budget=None, person=None):
        n["取名・合成"] += 1  # 首創配方與有私有意境的合併：都是真的會送給模型的
        return None, ""

    def refuse(*args, **kwargs):
        raise RuntimeError("量測不連模型")

    with mock.patch.object(sensing, "start", start), mock.patch.object(sensing, "choose", choose), \
            mock.patch.object(sensing, "finish", finish), mock.patch.object(insights, "learn", learn), \
            mock.patch.object(insight_llm, "name", name), mock.patch.object(naming, "propose", propose), \
            mock.patch.object(naming, "pick", lambda *a, **k: (None, "")), \
            mock.patch.object(OllamaClient, "chat_structured", refuse), mock.patch.object(OllamaClient, "chat_text", refuse), \
            mock.patch("requests.post", refuse), mock.patch("requests.get", refuse):
        game = bot.play_season(content, seed, world=world)
    p = game.state.player
    n["季末手上意境"] = len(p.insights)
    n["季末私有意境"] = sum(insights.is_own(i) for i in p.insights)
    n["私有意境（含熔掉的）"] = p.own_serial
    n["季末持有（武學＋意境）"] = library.held_count(game.state)
    n["季末上限"] = library.cap_of(game.state, content)
    return n


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seeds", type=int, nargs="+", default=[1, 2, 3, 4, 5])
    parser.add_argument("--profile", default=None)
    parser.add_argument("--old", action="store_true", help="拿掉有所感的場景，量舊的做法當對照")
    args = parser.parse_args()
    keys = ["有所感", "選錯", "沒擲中", "擲中", "畫了", "順其自然", "落回基本意境", "自己的意境", "悟到新的基本意境",
            "重複化成心得", "取名・感悟", "取名・合成", "私有意境（含熔掉的）", "季末手上意境", "季末私有意境",
            "季末持有（武學＋意境）", "季末上限"]
    rows = []
    print(f"設定：{args.profile or '預設'}{'（舊做法對照）' if args.old else ''}")
    for seed in args.seeds:
        n = measure(seed, args.profile, args.old)
        rows.append(n)
        print(f"seed {seed}：" + "、".join(f"{k} {n[k]}" for k in keys if n[k] or not args.old))
    print("中位數：" + "、".join(f"{k} {statistics.median(r[k] for r in rows)}" for k in keys))


if __name__ == "__main__":
    main()
