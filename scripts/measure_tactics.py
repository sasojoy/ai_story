"""本命戰法（tianxia/tactics.py，Joy 2026-10-15「全部改回合制」）讓一般的仗的贏面動了多少：只量、不改數字。

一般的仗照舊先擲單次判定，再一回合一回合打；沒有戰法時結果一模一樣。這裡量的是帶著戰法時贏面（大勝＋險勝）多了幾個百分點：
- 每一位人物：本人身上練著他的本命武學與本命內功（兩個戰法），威力對上難度的比例 0.9、1.0、1.15、1.3（贏面在中段最敏感）；
- 三種陣容：張飛＋張角（單人兩個控制）、桃園（劉備、關羽、張飛三人六個戰法）、黃天三兄弟（張角、張寶、張梁）；
- 「本命對合成」：對上同一個對手（難度＝合成擲到絕學頂的威力 132），合成上品頂、合成絕學頂、本命（威力 × power_scale）沒有戰法、本命帶兩個戰法。
固定種子、每一格 RUNS 場；條件（身法、夜裡、坐騎、善名惡名、部下）照一般的散人：身法 8、白天、沒騎馬、善名惡名 0、沒有部下、對手不是黃巾。

第二批（--bouts）另量：
- 挑戰大勢人物本人：他帶著自己的兩個戰法（對手方的戰法）時，你（沒有戰法）的贏面少了幾個百分點；
- 頭目戰：你帶著某位人物的兩個戰法、看架勢出招（同假人：架勢六成是真的），贏面（大勝＋險勝）多幾個百分點；難度挑在沒有戰法時約五成；
- 擂台：同樣身手的兩個人，挑的人帶戰法、守的分身沒有（以及兩邊都帶同一位人物的），挑的人贏面；
- 決戰：一個人一回合的份量平均乘多少（tactics.war_round，隨機出招、三成剋中），十八位各自。

用法：.venv/Scripts/python.exe scripts/measure_tactics.py [--runs 4000] [--bouts]
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
    parser.add_argument("--bouts", action="store_true", help="只量第二批：挑戰本人的對手戰法、頭目戰、擂台、決戰")
    parser.add_argument("--bout-strike", type=float, help="試別的 Config.tactics.bout_strike（只量）")
    parser.add_argument("--war-scale", type=float, help="試別的 Config.tactics.war_scale（只量）")
    args = parser.parse_args()
    content = load_content(ROOT / "content")
    if args.bout_strike is not None:
        content.config.tactics.bout_strike = args.bout_strike
    if args.war_scale is not None:
        content.config.tactics.war_scale = args.war_scale
    if args.bouts:
        bouts(content, args.runs)
        return
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

# ── 第二批 ──────────────────────────────────────────


def figures_with(content):
    return [ch.id for ch in content.characters.values() if ch.starting_wugong and content.skills[ch.starting_wugong].tactic]


def bouts(content, runs):
    from tianxia import arena, battle_instance
    from tianxia import duel as duel_rules
    from tianxia.models import MOVES
    from tianxia.state import ArenaFight, ArenaSide, DuelState

    figures = figures_with(content)
    names = {fid: content.characters[fid].name for fid in figures}
    t = content.config.tactics
    # 挑戰本人：他帶著自己的兩門
    ctx = tactics.Ctx(foe="對手", our_agility=8, foe_agility=rounds.foe_agility(DIFFICULTY), team=["player"])
    plain = [win_rate(content, DIFFICULTY * r, [], runs, ctx) for r in RATIOS]
    print(f"挑戰本人（他帶著自己的兩個戰法，你沒有），威力 ÷ 難度：" + "　".join(f"{r:g}" for r in RATIOS))
    print(f"{'他沒有戰法':<10}" + "　".join(f"{w:5.1%}" for w in plain))
    drops = []
    for fid in figures:
        foe = (holders(content, [(names[fid], tactics.FOE_KEY, fid)]),
               tactics.Ctx(foe=tactics.OUR_SIDE, our_agility=ctx.foe_agility, foe_agility=ctx.our_agility))
        rates = [foe_rate(content, DIFFICULTY * r, foe, runs, ctx) for r in RATIOS]
        d = [a - b for a, b in zip(rates, plain)]
        drops.append(sum(d) / len(d))
        print(f"{names[fid]:<6}" + "　".join(f"{x:+5.1%}" for x in d))
    print(f"十八位平均 {sum(drops) / len(drops):+.1%}")

    # 頭目戰
    boss = content.duels["julu_warden"] if "julu_warden" in content.duels else next(iter(content.duels.values()))
    foe_face = boss.foes[0]
    cfg, bt = content.config.duel, content.config.battle
    power = 150.0

    def duel_once(kit, difficulty, seed):
        rng = random.Random(f"d|{seed}")
        trng = random.Random(f"dt|{seed}")
        sc = battle_instance.strength(bt, power)
        d = DuelState(boss=boss.id, foe=0, edge=cfg.start, hp=1000, hp_cap=1000, hp_start=1000, power=power,
                      scores={m: sc for m in MOVES}, difficulty=difficulty)
        d.bout = tactics.open_bout(kit, None, "你", foe_face.name, b_agility=rounds.foe_agility(difficulty))
        duel_rules.roll_next(d, foe_face, cfg, rng)
        while True:
            move = duel_rules.answer_to(d) or rng.choice(MOVES)
            locked = tactics.locks(d.bout).no_moves
            if move in locked:  # 使不出來：挑看到的架勢底下最不吃虧的
                shown = duel_rules.shown_move(d)
                move = tactics.best_against([shown] if shown else list(MOVES), [m for m in MOVES if m not in locked])
            duel_rules.exchange_full(d, boss, move, cfg, bt, rng, t, trng)
            d.round += 1
            tier = duel_rules.verdict(d, boss, cfg)
            if tier is not None:
                return tier in WIN
            duel_rules.roll_next(d, foe_face, cfg, rng)

    def duel_rate(kit, difficulty):
        return sum(duel_once(kit.model_copy(deep=True) if kit else None, difficulty, i) for i in range(runs)) / runs

    target = None
    for diff in range(60, 400, 5):
        base = duel_rate(None, float(diff))
        if base <= 0.5:
            target = float(diff)
            break
    target = target or 200.0
    base = duel_rate(None, target)
    print(f"頭目戰（{boss.id}，你威力 {power:g}、他難度 {target:g}；沒有戰法 {base:.1%}）：帶著一位人物的兩個戰法，贏面")
    lifts = []
    for fid in figures:
        kit = tactics.side_for(holders(content, [("你", "player", fid)]), tactics.Ctx(foe="", our_agility=8, team=["player"]))
        r = duel_rate(kit, target)
        lifts.append(r - base)
        print(f"  {names[fid]:<4}{r:5.1%}（{r - base:+.1%}）")
    print(f"  十八位平均 {sum(lifts) / len(lifts):+.1%}")

    # 擂台：同樣身手
    def ring_once(kit_a, kit_b, seed):
        rng = random.Random(f"r|{seed}")
        trng = random.Random(f"rt|{seed}")
        sc = battle_instance.strength(bt, power)
        me = ArenaSide(name="挑", power=power, scores={m: sc for m in MOVES}, hp=1000, hp_cap=1000)
        foe = ArenaSide(name="守", power=power, scores={m: sc for m in MOVES}, hp=1000, hp_cap=1000)
        f = ArenaFight(id=1, foe_key="守", me=me, foe=foe)
        f.bout = tactics.open_bout(kit_a, kit_b, "挑", "守")
        arena.roll_next(f, rng, content.config.arena, cfg)
        while True:
            move = duel_rules.answer_to(f) or rng.choice(MOVES)
            locked = tactics.locks(f.bout).no_moves
            if move in locked:  # 使不出來：挑看到的架勢底下最不吃虧的
                shown = duel_rules.shown_move(f)
                move = tactics.best_against([shown] if shown else list(MOVES), [m for m in MOVES if m not in locked])
            arena.exchange_full(f, move, content, rng, trng)
            f.round += 1
            tier = arena.verdict(f, cfg)
            if tier is not None:
                return tier in WIN
            arena.roll_next(f, rng, content.config.arena, cfg)

    def ring_rate(ka, kb):
        return sum(ring_once(ka.model_copy(deep=True) if ka else None, kb.model_copy(deep=True) if kb else None, i)
                   for i in range(runs)) / runs

    base = ring_rate(None, None)
    print(f"擂台（兩邊威力 {power:g}；都沒有戰法時挑的人 {base:.1%}）：挑的人帶戰法／兩邊都帶同一位")
    for fid in figures:
        kit = tactics.side_for(holders(content, [("你", "player", fid)]), tactics.Ctx(foe="", our_agility=8, team=["player"]))
        a = ring_rate(kit, None)
        both = ring_rate(kit, kit)
        print(f"  {names[fid]:<4}{a:5.1%}（{a - base:+.1%}）　兩邊都帶 {both:5.1%}（{both - base:+.1%}）")

    # 決戰：份量平均乘多少
    print("決戰（一個人一回合的份量平均乘多少；隨機出招、三成剋中、戰局 50、氣血滿的）")
    for fid in figures:
        kit = tactics.side_for(holders(content, [("你", "player", fid)]),
                               tactics.Ctx(foe="", our_agility=8, team=["player"], followers=2, mount_tier=2))
        rng = random.Random(1)
        total = fired = 0.0
        n = 0
        for i in range(runs // 9 or 1):
            side = kit.model_copy(deep=True)
            for k in range(1, 10):
                move = rng.choice(MOVES)
                beat = 1 if rng.random() < 0.3 else 0
                w = tactics.war_round(side, move, beat, k, 50.0, 1.0, t, random.Random(f"w|{i}|{k}"))
                total += w.force
                fired += bool(w.lines)
                n += 1
                tactics.war_close(side, rng.random() < 0.5, t, random.Random(f"wc|{i}|{k}"))
        print(f"  {names[fid]:<4}×{total / n:.3f}（發動 {fired / n:.0%} 的回合）")


def foe_rate(content, power, foe, runs, ctx):
    rng = random.Random(7)
    wins = 0
    for i in range(runs):
        result = encounter.resolve_encounter(power, DIFFICULTY, rng)
        result = team.clash_result(result, encounter.Mods(), [], ctx, content, random.Random(f"m|{i}"), foe=foe)
        wins += result.tier in WIN
    return wins / runs


if __name__ == "__main__":
    main()
