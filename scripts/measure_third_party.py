"""決戰改版五 Task 3：豪強第三方的收穫量一次（戰鬥系統設計第六節【預設】）。只量、不改數字、不擋上線。

兩軍各 N 人（威力從新手到高手之間抽、屬性隨機、七成出拿手招三成亂出），豪強 K 人，血多就搶地盤、剩不到一半就保存實力。
印每種人數下這一場推了割據幾點（20 場的中位數，括號是最少～最多）。

純戰鬥結算：不開世界、不碰資料庫、不叫模型。

用法：.venv/Scripts/python.exe scripts/measure_third_party.py
"""
from __future__ import annotations

import io
import random
import statistics
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tianxia import battle_instance as bi  # noqa: E402
from tianxia.content import load_content  # noqa: E402
from tianxia.models import MOVES  # noqa: E402

ATTRS = ("剛", "實", "陽", "柔", "陰", "慢", "快", "虛")
CODES = {"強攻": "strong", "固守": "hold", "奇襲": "raid"}


def run(definition, tuning, guan, huang, warlords, seed):
    """打完一整場，回傳這一場推了割據幾點（battle.third_push）。"""
    rng = random.Random(seed)
    battle = bi.start_muster(definition, now=0)
    third = definition.third.faction
    for side, count in (("guan", guan), ("huang", huang), (third, warlords)):
        for i in range(count):
            power = rng.uniform(0, 150)
            scores = bi.move_scores(tuning, power, rng.choice(ATTRS), rng.choice(ATTRS))
            bi.join_faction(battle, f"{side}{i}", side, neili_cap=400, power=power, scores=scores)
    bi.close_muster(battle, definition, rng, now=0)
    while battle.phase == "active":
        for name, p in battle.participants.items():
            if p.eliminated:
                continue
            if p.faction == third:
                bi.submit_action(battle, name, bi.THIRD_GRAB if p.neili > p.neili_cap / 2 else bi.THIRD_KEEP)
                continue
            best = max(MOVES, key=lambda m: p.scores[m])
            move = best if rng.random() < 0.7 else rng.choice(MOVES)
            bi.submit_action(battle, name, f"{p.faction}_{CODES[move]}")
        bi.resolve_round(battle, definition, rng, now=0, tuning=tuning)
    return battle.third_push


def main() -> None:
    content = load_content(ROOT / "content")
    definition = content.battles["changshe_fire"].model_copy(update={"trend_start": 50})
    tuning = content.config.battle
    for guan, huang in ((20, 20), (40, 10), (200, 200)):
        for warlords in (1, 3, 10, 30, 100):
            pushes = [run(definition, tuning, guan, huang, warlords, seed) for seed in range(20)]
            print(f"官 {guan} 對 黃 {huang}，豪強 {warlords}：割據推 {statistics.median(pushes)}（{min(pushes)}～{max(pushes)}）")


if __name__ == "__main__":
    main()
