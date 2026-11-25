"""銀兩夠不夠花（PM 2026-11-25 派：只量不改數字、不提新出口）：season21 整季，一般玩家、勤快玩家，再加「見錢就花」兩個對照，
記每天身上的銀兩、每天進帳、每一樣花在哪裡（鐵匠鋪、馬市、酒肆、名師指點、看火候、破境丹、打點門路；捐軍備 11/12 起關著）。

做法：借 scripts/limit_bots.py 的整季世界（正式內容、伺服器假人照常補人、現實時鐘 1:1），再替被量的那一個角色在 Game.choose
外面包一層帳：每按一下前後的銀兩差，照選項的 id 歸類；不經過按鈕的進出（時間補算、季末折盤纏）算「其他」。
「見錢就花」：每一輪先進「打點」那一間店，把開著的名師指點、看火候、破境丹、打點門路都按一次再離開，鐵匠鋪一有錢就進
（真人想花錢時花得掉多少：出口本身一天一次、名師指點要等下一次衝絕學才用掉、看火候要等下一爐才用掉，都照規則）。

執行：python scripts/measure_silver.py --jobs 4 --out <資料夾>
"""
from __future__ import annotations

import argparse
import io
import json
import sys
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import limit_bots as lb  # noqa: E402
from tianxia.engine import Game  # noqa: E402

DAY = 86400.0
ME = "極限甲"
SPEND_IDS = ("act:mentor", "act:furnace", "act:buy_legend", "act:bribe:")
SPENDERS: set[str] = set()
LEDGER: dict = {}

lb.FOCUSES["normal"] = replace(lb.FOCUSES["control"], label="一般玩家（每天 3 小時）", hours=3.0)
lb.FOCUSES["diligent"] = replace(lb.FOCUSES["grinder"], label="勤快玩家（每天 16 小時）")
lb.FOCUSES["normal_spend"] = replace(lb.FOCUSES["control"], label="一般玩家＋見錢就花", hours=3.0, smith=True, smith_silver=0)
lb.FOCUSES["diligent_spend"] = replace(lb.FOCUSES["grinder"], label="勤快玩家＋見錢就花", smith=True, smith_silver=0)
SPENDERS.update({"一般玩家＋見錢就花", "勤快玩家＋見錢就花"})


def _ids(game: Game) -> set[str]:
    return {o.id for o in game.options(odds=False, tick=False) if o.enabled}


def spend_all(game: Game) -> None:
    """打點那一間店裡開著的都按一次（捐銀兩關著，不在裡面）。"""
    if game.state.pending_event or game.state.player.journey is not None:
        return
    if "act:dadian" not in _ids(game):
        return
    game.choose("act:dadian")
    for _ in range(12):
        pick = next((i for i in sorted(_ids(game)) if i.startswith(SPEND_IDS)), None)
        if pick is None:
            break
        game.choose(pick)
    if "dadian:back" in _ids(game):
        game.choose("dadian:back")


_real_turn = lb._turn


def _turn(game, profile, driver):
    if driver.focus.label in SPENDERS:
        spend_all(game)
    return _real_turn(game, profile, driver)


lb._turn = _turn

SINKS = (  # 選項 id 前綴 → 歸到哪一樣（最長的先比）
    ("act:mentor", "名師指點"), ("act:furnace", "看火候"), ("act:buy_legend", "破境丹"), ("act:bribe", "打點門路"),
    ("act:silver_donate", "捐銀兩"), ("act:smith", "鐵匠鋪"), ("smith", "鐵匠鋪"), ("act:market", "馬市"), ("market", "馬市"),
    ("horse", "馬市"), ("act:tavern", "酒肆"), ("tavern", "酒肆"), ("hire", "酒肆"), ("act:feast", "宴客"), ("feast", "宴客"),
    ("act:clinic", "醫館"), ("act:heal", "醫館"), ("bounty", "懸賞"), ("act:bounties", "懸賞"), ("act:explore", "探索"),
    ("explore", "探索"), ("act:train", "出陣"), ("sortie", "出陣"), ("act:checkin", "簽到"), ("checkin", "簽到"),
)


def sink_of(option_id: str) -> str:
    for prefix, name in SINKS:
        if option_id.startswith(prefix):
            return name
    head = option_id.split(":")[0]
    return {"ev": "事件", "event": "事件", "story": "事件", "choice": "事件", "duel": "單挑", "act": option_id.split(":")[1] if ":" in option_id else "act"}.get(head, head)


_real_choose = Game.choose
_depth = [0]


def choose(self, option_id, *a, **k):
    if self.state.player.name != ME or _depth[0]:
        return _real_choose(self, option_id, *a, **k)
    before = self.state.player.stats.get("silver", 0)
    _depth[0] += 1
    try:
        return _real_choose(self, option_id, *a, **k)
    finally:
        _depth[0] -= 1
        delta = self.state.player.stats.get("silver", 0) - before
        if delta:
            day = int(self.state.world.time // DAY) + 1
            book = LEDGER.setdefault(day, {"in": defaultdict(int), "out": defaultdict(int)})
            (book["in"] if delta > 0 else book["out"])[sink_of(str(option_id))] += abs(delta)


Game.choose = choose

_real_sync = Game.sync


def sync(self, *a, **k):
    """時間補算裡的進出（路上撞見的事、結算、季末折盤纏）：同一本帳，記成「時間補算」。"""
    if self.state.player.name != ME or _depth[0]:
        return _real_sync(self, *a, **k)
    before = self.state.player.stats.get("silver", 0)
    _depth[0] += 1
    try:
        return _real_sync(self, *a, **k)
    finally:
        _depth[0] -= 1
        delta = self.state.player.stats.get("silver", 0) - before
        if delta:
            day = int(self.state.world.time // DAY) + 1
            book = LEDGER.setdefault(day, {"in": defaultdict(int), "out": defaultdict(int)})
            (book["in"] if delta > 0 else book["out"])["時間補算"] += abs(delta)


Game.sync = sync


def _job(args):
    focus, seed, tick, out = args
    LEDGER.clear()
    try:
        result = lb.run_one("season21", focus, seed, tick, "loose", 20, 4)
    except Exception as exc:  # noqa: BLE001
        result = {"focus": focus, "seed": seed, "crash": repr(exc)}
    result["ledger"] = {d: {"in": dict(v["in"]), "out": dict(v["out"])} for d, v in sorted(LEDGER.items())}
    path = Path(out) / f"silver-{focus}-{seed}.json"
    path.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    return path.name, result.get("seconds"), result.get("crash")


def main() -> None:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser()
    parser.add_argument("--focus", nargs="+", default=["normal", "diligent", "normal_spend", "diligent_spend"])
    parser.add_argument("--seeds", type=int, nargs="+", default=[1])
    parser.add_argument("--tick", type=float, default=120.0)
    parser.add_argument("--jobs", type=int, default=4)
    parser.add_argument("--out", default=str(ROOT / ".local" / "silver"))
    args = parser.parse_args()
    Path(args.out).mkdir(parents=True, exist_ok=True)
    jobs = [(f, s, args.tick, args.out) for f in args.focus for s in args.seeds]
    with ProcessPoolExecutor(args.jobs) as pool:
        for row in pool.map(_job, jobs):
            print(*row, flush=True)


if __name__ == "__main__":
    main()
