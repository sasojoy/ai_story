"""〈天下形勢〉的真實模型實測（領地爭奪第三批 A，計畫第五章 Task 17）：開一個暫存的世界、照真的規則跑一天（開季、一場攻城收場、22:00 結算
開單），拿那一張單的事實叫一次 xingshi.write，印出文章、花幾秒、有沒有退回固定段。只量不改，不進測試。

要先開 Ollama，模型用 content/config.json 的設定（跟遊戲一樣）。這台的 Ollama 同時在給線上伺服器用：只跑一次就好，不要迴圈跑。

    .venv/Scripts/python.exe scripts/try_xingshi.py
    .venv/Scripts/python.exe scripts/try_xingshi.py --model qwen2.5:14b   # 換一個模型試（預設照設定）

模型叫不動、答壞（過不了 xingshi.clean：太短太長、有阿拉伯數字或假名）時印「⚠ 退回固定段」與原因，文章換成固定段。
"""
from __future__ import annotations

import argparse
import calendar as pycal
import io
import os
import random
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("TIANXIA_DB", str(Path(tempfile.mkdtemp(prefix="try-xingshi-")) / "tianxia.db"))  # 不碰這份 clone 的 saves/

from tianxia import siege, territory, xingshi  # noqa: E402
from tianxia.content import load_content  # noqa: E402
from tianxia.engine import Game  # noqa: E402
from tianxia.ollama_client import OllamaClient  # noqa: E402
from tianxia.sqlite_world import open_world  # noqa: E402
from tianxia.state import SiegeSlot  # noqa: E402


class Watch:
    """把 client 包一層：記下 chat_structured 丟的例外與模型原樣回的文章（xingshi.write 吃掉例外、過不了 clean 回 None，從外面看不出來）。"""

    def __init__(self, client):
        self.client, self.failed, self.raw = client, None, None

    def chat_structured(self, *args, **kwargs):
        try:
            reply = self.client.chat_structured(*args, **kwargs)
        except Exception as e:  # noqa: BLE001  實測腳本：照原樣丟回去，只是先記下來
            self.failed = e
            raise
        self.raw = getattr(reply, "essay", None)
        return reply


def _tw(d: int, h: int, mi: int = 0) -> float:
    return float(pycal.timegm(datetime(2026, 10, d, h, mi).timetuple())) - 8 * 3600


def one_day() -> tuple[Game, xingshi.XingshiRequest]:
    """暫存的世界跑一天：21 天的季、領地爭奪與〈天下形勢〉打開；黃巾攻南陽官道大勝；22:01 結算開單。回（Game, A 段的單）。"""
    content = load_content(ROOT / "content", "season21")
    content.config.xingshi.enabled = True
    content.config.auto_open_first_season = True
    game = Game.new(content, "史官試筆", rng=random.Random(0), world=open_world())
    game.client = None
    p = game.state.player
    p.faction, p.tutorial_step, p.location = "huang", len(content.tutorial.steps), "nanyang_road"
    territory.update(game.state.world, content)
    game.now = _tw(20, 10)
    game._conquest_tick()  # 這一季第一次：只記下起點
    game.state.world = game.world.get_season()
    w = game.state.world
    slot = SiegeSlot(id="try-1", key=w.conquest.settled_key, loc="nanyang_road", minute=21 * 60, at=w.time + 1800, muster_at=w.time,
                     attackers=["huang"], by={"huang": "letter"}, reasons={"huang": "史官試筆"}, status="waiting")  # 戰書排的（翻地與爭搶）
    w.conquest.schedule.append(slot)
    game._save_season()
    siege.open_waiting(game.world, content, game.now)
    game.state.world = game.world.get_season()
    battle = game.world.get_sieges()[0]

    def close(b):
        b.phase, b.trend, b.end_time = "ended", 10, game.state.world.time

    game._apply_battle_outcome(game.world.mutate_siege(battle.record_id, close))
    game.state.world = game.world.get_season()
    game.now = _tw(20, 22, 1)
    game._conquest_tick()  # 22:01 換天：開一張〈天下形勢〉的單（翻地與爭搶之後換天不排攻城）
    game.state.world = game.world.get_season()
    request = game.xingshi_request()
    assert request is not None, "沒開成單（領地爭奪或〈天下形勢〉沒開？）"
    return game, request


def main() -> None:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")  # cp950 主控台印不了中文
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", help="換一個模型試（預設用 content/config.json 的 ollama_model）")
    args = parser.parse_args()

    game, request = one_day()
    cfg = game.content.config
    print(request.line)
    for fact in request.facts:
        print(f"  - {fact}")
    client = OllamaClient(
        base_url=cfg.ollama_url, model=args.model or cfg.ollama_model, timeout=cfg.xingshi.budget_seconds, think=cfg.ollama_think,
        keep_alive=cfg.ollama_keep_alive, repeat_penalty=cfg.ollama_repeat_penalty,
        presence_penalty=cfg.ollama_presence_penalty, frequency_penalty=cfg.ollama_frequency_penalty,
    )
    print(f"\n模型：{client.model}")
    watch = Watch(client)
    start = time.monotonic()
    essay = xingshi.write(watch, request)
    seconds = time.monotonic() - start
    if essay is not None:
        print(f"寫成了（{seconds:.1f} 秒、{len(essay.replace(chr(10), ''))} 字）：\n{essay}")
    else:
        why = repr(watch.failed) if watch.failed is not None else f"過不了 clean：{watch.raw!r}"
        print(f"⚠ 退回固定段（{seconds:.1f} 秒）：{why}")
        print(xingshi.rule_text(request.facts, game.content, "try"))
    game.settle_xingshi(request, essay)
    done = game.world.get_season().xingshi[-1]
    print(f"\n收下：第 {done.n} 篇、{'固定段' if done.by_rule else '模型寫的'}；天下大事：{xingshi.rumor_text(done.line)}")


if __name__ == "__main__":
    main()
