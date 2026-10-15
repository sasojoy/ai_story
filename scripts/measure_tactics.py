"""本命戰法（tianxia/tactics.py，Joy 2026-10-15「全部改回合制」）讓一般的仗的贏面動了多少：只量、不改數字。

一般的仗照舊先擲單次判定，再一回合一回合打；沒有戰法時結果一模一樣。這裡量的是帶著戰法時贏面（大勝＋險勝）多了幾個百分點：
- 每一位人物：本人身上練著他的本命武學與本命內功（兩個戰法），威力對上難度的比例 0.9、1.0、1.15、1.3（贏面在中段最敏感）；
- 三種陣容：張飛＋張角（單人兩個控制）、桃園（劉備、關羽、張飛三人六個戰法）、黃天三兄弟（張角、張寶、張梁）；
- 「本命對合成」：對上同一個對手（難度＝合成擲到絕學頂的威力 132），合成上品頂、合成絕學頂、本命（威力 × power_scale）沒有戰法、本命帶兩個戰法。
固定種子、每一格 RUNS 場；條件（身法、夜裡、坐騎、善名惡名、部下）照一般的散人：身法 8、白天、沒騎馬、善名惡名 0、沒有部下、對手不是黃巾。

用法：.venv/Scripts/python.exe scripts/measure_tactics.py [--runs 4000]
"""
from __future__ import annotations

import argparse
import io
import random
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tianxia import encounter, rounds, tactics, team  # noqa: E402
from tianxia.content import load_content  # noqa: E402

RATIOS = (0.9, 1.0, 1.15, 1.3)
DIFFICULTY = 100.0
WIN = ("大勝", "險勝")


def win_rate(content, power, holders, runs, ctx):
    rng = random.Random(7)
    wins = 0
    for i in range(runs):
        result = encounter.resolve_encounter(power, DIFFICULTY, rng)
        if holders:
            result = team.clash_result(result, encounter.Mods(), holders, ctx, content, random.Random(f"m|{i}"))
        wins += result.tier in WIN
    return wins / runs


def holders(content, rows):
    return tactics.holders_of(content, [(who, key, f"{fid}_wugong", f"{fid}_neigong") for who, key, fid in rows])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=4000)
    args = parser.parse_args()
    content = load_content(ROOT / "content")
    ctx = tactics.Ctx(foe="對手", our_agility=8, foe_agility=rounds.foe_agility(DIFFICULTY), team=["player", "a", "b"])
    print("贏面（大勝＋險勝），威力 ÷ 難度：" + "　".join(f"{r:g}" for r in RATIOS))
    plain = [win_rate(content, DIFFICULTY * r, [], args.runs, ctx) for r in RATIOS]
    print(f"{'沒有戰法':<10}" + "　".join(f"{w:5.1%}" for w in plain))
    figures = [ch.id for ch in content.characters.values() if ch.starting_wugong and content.skills[ch.starting_wugong].tactic]
    lifts = []
    for fid in figures:
        hs = holders(content, [("你", "player", fid)])
        rates = [win_rate(content, DIFFICULTY * r, hs, args.runs, ctx) for r in RATIOS]
        lift = [a - b for a, b in zip(rates, plain)]
        lifts.append(sum(lift) / len(lift))
        names = "＋".join(h.tactic.name for h in hs)
        print(f"{content.characters[fid].name:<4}{names:<12}" + "　".join(f"{d:+5.1%}" for d in lift))
    print(f"十八位平均多 {sum(lifts) / len(lifts):+.1%}")
    for label, rows in (
        ("張飛武＋張角內", None),
        ("桃園三人", [("你", "player", "liubei"), ("關羽", "a", "guanyu"), ("張飛", "b", "zhangfei")]),
        ("黃天三兄弟", [("你", "player", "zhangjiao"), ("張寶", "a", "zhangbao"), ("張梁", "b", "zhangliang")]),
    ):
        hs = (tactics.holders_of(content, [("你", "player", "zhangfei_wugong", "zhangjiao_neigong")]) if rows is None
              else holders(content, rows))
        rates = [win_rate(content, DIFFICULTY * r, hs, args.runs, ctx) for r in RATIOS]
        print(f"{label:<12}" + "　".join(f"{a - b:+5.1%}" for a, b in zip(rates, plain)))
    # 本命對合成：同一個對手（難度 = 合成擲到絕學頂的威力 132），本人只帶這一門（不帶內功，比的是武學本身）
    k = content.config.signature_arts.power_scale
    synth = {"合成上品頂": 72 * 1.1, "合成絕學頂": 120 * 1.1}
    sig = 120 * k
    d = synth["合成絕學頂"]
    print(f"同一個對手（難度 {d:g}）：" + "　".join(f"{name} {p:g}：{plain_rate(p, d, args.runs):.1%}" for name, p in synth.items())
          + f"　本命（{sig:g}，×{k:g}）沒有戰法：{plain_rate(sig, d, args.runs):.1%}")
    for fid in ("liubei", "guanyu", "zhangfei", "zhangjiao", "sunjian", "bocai"):
        hs = holders(content, [("你", "player", fid)])
        rng = random.Random(9)
        wins = 0
        for i in range(args.runs):
            r = encounter.resolve_encounter(sig, d, rng)
            wins += team.clash_result(r, encounter.Mods(), hs, ctx, content, random.Random(f"s|{i}")).tier in WIN
        print(f"  {content.characters[fid].name}本命帶兩個戰法：{wins / args.runs:.1%}")


def plain_rate(power, difficulty, runs):
    rng = random.Random(9)
    return sum(encounter.resolve_encounter(power, difficulty, rng).tier in WIN for _ in range(runs)) / runs

if __name__ == "__main__":
    main()
