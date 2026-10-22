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

第三批（--kits）另量：本命對玩家自組上品（兩門上品、意境槽裝滿的技能換成的戰法，隨機 SELF_KITS 套）、神器特技、名將本命兵器（含人器合一）。
擂台同樣身手的兩個人對打（兩邊都照架勢出招），兩個方向都量；另量一般的仗多的贏面與決戰的份量。

武學重構（2026-10-20，tianxia/arts.py）之後的「滿配」（第三批：意境效果池之後）：兩門絕學各 4 格都裝滿、每一格一路不同的意境，
一個一般功效三重加一個大獎（--grand-share 試大獎的比例，沒有大獎的那一格換成第二個一般功效），一半帶秘方的特別功效，
各一招絕招、一把以器配招的神器原品。自組上品是 4 格各一重（新悟到的意境）。--strength 試滿配的一般功效重數（1～3）。

寶物與玉璽（--gear，企劃者 10/17 清單第 35 項「武學平衡要包含寶物，玉璽也是」；計畫 docs/superpowers/plans/2026-10-18-武學平衡含寶物玉璽.md）：
寶物八種效果、玉璽七片一樣一列，分直接（進打仗的數字：金角、螭首）、間接（改成長快慢）、不碰（跟打仗無關）三類（KIND）；
直接的量出在哪幾種仗、勝負各變幾個百分點（金角在一般的仗、螭首在連打與擂台），間接的印它改哪一條成長、改多少，不換算成威力。
數字一律照 Config 讀，調了數字重跑就是新表；只量不改。

用法：.venv/Scripts/python.exe scripts/measure_tactics.py [--runs 4000] [--bouts] [--kits] [--catch-up [--strength 3]]
      [--gear [--chain N]]
"""
from __future__ import annotations

import argparse
import io
import random
import sys
from pathlib import Path
from typing import NamedTuple

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
    parser.add_argument("--kits", action="store_true", help="只量第三批：本命對自組上品、神器特技、名將本命兵器")
    parser.add_argument("--catch-up", action="store_true", help="只量玩家武學追上本命：十八位本命對滿配絕學＋配招兵器")
    parser.add_argument("--own", action="store_true", help="只量以意成招：十八位本命對自創滿配（兩門自創上品、各一招透的招）")
    parser.add_argument("--own-all", action="store_true", help="--own 另量空手、招熟、舊滿配")
    parser.add_argument("--pick", help="--own 只量哪幾列（列的名字，逗號隔開；分給好幾個行程平行跑）")
    parser.add_argument("--move-scale", type=float, help="自創的招（content/create_forms.json 的 moves）會長的數全部乘這個數（只量）")
    parser.add_argument("--strength", type=int, default=3, help="--catch-up 滿配裡每個意境的強度（一重～三重）")
    parser.add_argument("--bout-strike", type=float, help="試別的 Config.tactics.bout_strike（只量）")
    parser.add_argument("--war-scale", type=float, help="試別的 Config.tactics.war_scale（只量）")
    parser.add_argument("--might-scale", type=float, help="本命底蘊（TacticDef.might）全部乘這個數（只量）")
    parser.add_argument("--grand-share", type=float, help="--catch-up 滿配每一格第二個效果是大獎的機會（預設 1.0）")
    parser.add_argument("--stack-share", type=float, help="試別的 Config.arts.stack_share（同效果第二份起算幾成；0 配 --stack-ceiling 1 是改之前；只量）")
    parser.add_argument("--stack-ceiling", type=float, help="試別的 Config.arts.stack_ceiling（同效果疊上去最多上限的幾倍；只量）")
    parser.add_argument("--might-add", type=float, help="本命底蘊（TacticDef.might）每一門都加這個數（只量；一位人物兩門，合計加兩倍）")
    parser.add_argument("--tweak", nargs="+", default=[], metavar="技能.欄=數",
                        help="試別的本命戰法數字（只量）：zhangfei_wugong.rate=0.3、zhangliang_wugong.per_pct=0.05（params 裡的照鍵名）")
    parser.add_argument("--gear", action="store_true", help="只量寶物八種與玉璽七片：哪些進打仗、勝負變幾個百分點，哪些只改成長（第 35 項）")
    parser.add_argument("--chain", type=int, default=5, help="--gear 的螭首連打幾場不療傷（預設 5）")
    args = parser.parse_args()
    content = load_content(ROOT / "content")
    if args.bout_strike is not None:
        content.config.tactics.bout_strike = args.bout_strike
    if args.war_scale is not None:
        content.config.tactics.war_scale = args.war_scale
    if args.stack_share is not None:
        content.config.arts.stack_share = args.stack_share
    if args.stack_ceiling is not None:
        content.config.arts.stack_ceiling = args.stack_ceiling
    for item in args.tweak:
        path, value = item.split("=")
        sid, key = path.split(".")
        tactic = content.skills[sid].tactic
        if key in tactic.params:
            tactic.params[key] = float(value)
        else:
            setattr(tactic, key, float(value))
    if args.might_scale is not None:
        for sk in content.skills.values():
            if sk.tactic is not None:
                sk.tactic.might *= args.might_scale
    if args.might_add is not None:
        for sk in content.skills.values():
            if sk.tactic is not None:
                sk.tactic.might += args.might_add
    if args.bouts:
        bouts(content, args.runs)
        return
    if args.kits:
        kits(content, args.runs)
        return
    if args.gear:
        gear(content, args.runs, args.chain)
        return
    if args.grand_share is not None:
        global GRAND_SHARE
        GRAND_SHARE = args.grand_share
    if args.catch_up:
        catch_up(content, args.runs, args.strength)
        return
    if args.own:
        global OWN_ALL, PICK
        OWN_ALL = args.own_all
        PICK = None if not args.pick else set(args.pick.split(","))
        if args.move_scale is not None:
            from tianxia import moves
            content.create_forms.moves = [m.model_copy(update=moves.scaled(m, args.move_scale)) for m in content.create_forms.moves]
        own(content, args.runs, args.strength)
        return
    ctx = tactics.Ctx(foe="對手", our_agility=8, foe_agility=rounds.foe_agility(DIFFICULTY), team=["player", "a", "b"])
    print("贏面（大勝＋險勝），威力 ÷ 難度：" + "　".join(f"{r:g}" for r in RATIOS))
    plain = [win_rate(content, DIFFICULTY * r, [], args.runs, ctx) for r in RATIOS]
    print(f"{'沒有戰法':<10}" + "　".join(f"{w:5.1%}" for w in plain))
    figures = figures_with(content)
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
    """十八位有本命戰法的人物（tactics.figure_arts；歷史武將同行起始帶的學來的武學有小戰法、不是本命，FB-640）。"""
    return [ch.id for ch in content.characters.values()
            if any(content.skills[s].tactic is not None for s in tactics.figure_arts(content, ch))]


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
        f.bout = tactics.open_bout(kit_a, kit_b, "挑", "守", pvp=True)
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


# ── 第三批 ──────────────────────────────────────────

SELF_KITS = 12  # 隨機自組幾套
OWN_ALL = False  # --own 時另量空手、招熟、舊滿配（--own-all）
PICK = None  # --own 只量哪幾列（--pick，列的名字）
GRAND_SHARE = 1.0  # 滿配每一格的第二個效果是大獎的機會（--grand-share 改；意境效果池之後，第三批）
ATTRS = ("快", "慢", "剛", "柔", "陽", "陰", "虛", "實")


def slots_kit(content, seed, quality, strength, special_share=0.5, high_share=0.0, ults=False):
    """武學重構之後的一套：武學、內功各一門自己合成的武學（品級 quality），意境槽（Config.arts.slots）每一格裝一個意境、
    每個強度 strength（一般功效 strength 層，乘品級的倍數 traits.multiplier）；special_share 的機會第一門一格換成秘方的特別功效、
    high_share 的機會第二門一格換成不同意境合出來的高階技能；ults 時各一招絕招（層數最多的那個一般功效，第一招帶以器配招）。"""
    from tianxia import traits
    rng = random.Random(f"kit|{seed}")
    mult = traits.multiplier(content, quality)
    n = int(content.config.arts.slots.get(quality, 2))
    lo, pooled = traits.Loadout(), {}
    out = []
    for i in range(2):
        cells = [rng.choice(ATTRS) for _ in range(n)]
        if i == 0 and rng.random() < special_share:
            sp = rng.choice([t for t in content.traits.special if t.pool])
            lo.specials[sp.hook] = sp
            cells = cells[1:]
        elif i == 1 and rng.random() < high_share and content.traits.high:
            top = rng.choice(content.traits.high)
            if all(t.name != top.tactic.name for t in lo.highs):
                lo.highs.append(top.tactic)
            cells = cells[1:]
        for a in cells:
            hook = traits.general(content, a).hook
            pooled.setdefault(hook, []).append(mult * strength)
        if ults and cells:
            best = traits.general(content, max(dict.fromkeys(cells), key=cells.count))
            if best.ultimate is not None:
                ult = best.ultimate.model_copy(update={"name": f"絕學{i + 1}"})
                out.append(tactics.bonded(ult, best.ultimate_bond) if i == 0 else ult)
    settle(content, lo, pooled)
    hs = [tactics.Holder(who="你", key="player", skill=f"ult:{u.name}", tactic=u) for u in out]
    hs += [tactics.Holder(who="你", key="player", skill=f"trait:{t.name}", tactic=t) for t in traits.tactic_defs(content, lo)]
    hs += [tactics.Holder(who="你", key="player", skill=f"high:{t.name}", tactic=t) for t in lo.highs]
    return hs


def settle(content, lo, pooled):
    """身上兩門每一份的層數（已乘品級）照遊戲裡同一條算成 Loadout 的層數：同一個功效第二份起算一半、最多一倍半（traits.stack_value）。"""
    from tianxia import traits
    cfg = content.config.arts
    for t in content.traits.general:
        if pooled.get(t.hook):
            lo.layers[t.hook] = traits.stack_value([t.per_layer * c for c in pooled[t.hook]], t.cap, cfg.stack_share, cfg.stack_ceiling) / t.per_layer


def piece_kit(content, seed, quality, strength, grand_share=1.0, special_share=0.5, ults=False):
    """意境效果池之後（第二批）的一套：武學、內功各一門（品級 quality），每一格裝一份意境——那一路的一個一般功效 strength 重，
    再加第二個效果：grand_share 的機會是那一路的大獎（同一個大獎只算一次，撞了換成另一個一般功效 strength 重），其餘是另一個一般功效
    strength 重。一格裡的兩個效果最多三重（insight_fx.MAX_LAYERS）。special_share 的機會第一門一格換成秘方的特別功效。"""
    from tianxia import insight_fx, traits
    rng = random.Random(f"piece|{seed}")
    mult = traits.multiplier(content, quality)
    n = int(content.config.arts.slots.get(quality, 2))
    lo, pooled = traits.Loadout(), {}
    out = []
    for i in range(2):
        cells = rng.sample(ATTRS, n)
        if i == 0 and rng.random() < special_share:
            sp = rng.choice([t for t in content.traits.special if t.pool])
            lo.specials[sp.hook] = sp
            cells = cells[1:]
        layer_count: dict[str, float] = {}
        for a in cells:
            pool = insight_fx.generals(content, a)
            first = rng.choice(pool)
            picks = [first]
            top = insight_fx.grand_of(content, a)
            if rng.random() < grand_share and top is not None and all(t.name != top.tactic.name for t in lo.highs):
                lo.highs.append(top.tactic)
            else:
                picks += [t for t in pool if t.key != first.key][:1]
            for t in picks:
                pooled.setdefault(t.hook, []).append(mult * strength)
                layer_count[t.key] = layer_count.get(t.key, 0) + strength
        if ults and layer_count:
            ultable = {k: v for k, v in layer_count.items() if traits.general(content, k).ultimate is not None}
            if ultable:
                best = traits.general(content, max(ultable, key=ultable.get))
                ult = best.ultimate.model_copy(update={"name": f"絕學{i + 1}"})
                out.append(tactics.bonded(ult, best.ultimate_bond) if i == 0 else ult)
    settle(content, lo, pooled)
    hs = [tactics.Holder(who="你", key="player", skill=f"ult:{u.name}", tactic=u) for u in out]
    hs += [tactics.Holder(who="你", key="player", skill=f"trait:{t.name}", tactic=t) for t in traits.tactic_defs(content, lo)]
    hs += [tactics.Holder(who="你", key="player", skill=f"high:{t.name}", tactic=t) for t in lo.highs]
    return hs


def stack_kit(content, seed, attrs=("快", "陽"), strength=3, gear=True):
    """堆疊滿配（同效果第二份算半之後，Joy 2026-10-22）：破境的兩門自創，第一門三格全是 attrs[0]、第二門全是 attrs[1]，
    每一份那一路第一個一般功效 strength 重＋那一路的真意（同一個真意第二份發動率 ×1.5，第三份起不加，traits.high_tactic），
    各一招自己的招（升為絕招）＋後勁、一把配招兵器。attrs 兩個一樣就是最極端的堆法（兩門六格全是同一路）。"""
    from tianxia import insight_fx, moves, traits
    rng = random.Random(f"stack|{seed}")
    mult = traits.multiplier(content, "絕學")
    n = int(content.config.arts.slots.get("絕學", 3))
    lo, pooled, tops, out, own = traits.Loadout(), {}, {}, [], []
    level = content.config.arts.move_raw_levels + 1
    for i, a in enumerate(attrs):
        first = insight_fx.generals(content, a)[0]
        pooled.setdefault(first.hook, []).extend([mult * strength] * n)
        top = insight_fx.grand_of(content, a)
        if top is not None:
            tops[top.tactic.name] = (top, tops.get(top.tactic.name, (top, 0))[1] + n)
        if first.ultimate is not None:
            ult = first.ultimate.model_copy(update={"name": f"絕學{i + 1}"})
            out.append(tactics.bonded(ult, first.ultimate_bond) if i == 0 else ult)
        kind = ("武學", "內功")[i]
        stance = rng.choice(moves.STANCES)
        move = moves.build(content, kind, a, stance, "透", level=level)
        move = moves.ascend(content, moves.cell(content, a, moves.timing_of(kind, stance)), move)
        own.append(tactics.Holder(who="你", key="player", skill=f"own:{kind}", tactic=move))
    settle(content, lo, pooled)
    lo.highs = [traits.high_tactic(content, top.tactic, k) for top, k in tops.values()]
    hs = [tactics.Holder(who="你", key="player", skill=f"ult:{u.name}", tactic=u) for u in out]
    hs += [tactics.Holder(who="你", key="player", skill=f"trait:{t.name}", tactic=t) for t in traits.tactic_defs(content, lo)]
    hs += [tactics.Holder(who="你", key="player", skill=f"high:{t.name}", tactic=t) for t in lo.highs]
    hs += own
    if gear:
        arm = rng.choice([r for r in content.forge_secrets.values() if r.tactic is not None and r.slot == "weapon"])
        hs.append(gear_holder(arm.tactic))
    return hs


def self_kit(content, seed, quality="上品", special_share=0.5):
    """一套自組上品：四格各裝一個剛悟到的意境（●），一半的機會帶一個特別功效。"""
    return slots_kit(content, seed, quality, 1, special_share)


def full_kit(content, seed, strength=3, special_share=0.5):
    """滿配（玩家武學追上本命）：兩門絕學四格都裝滿、每格三重加大獎、一半帶特別功效、各一招絕招、一把以器配招的神器原品。"""
    rng = random.Random(f"full|{seed}")
    hs = piece_kit(content, seed, "絕學", strength, GRAND_SHARE, special_share, ults=True)
    arm = rng.choice([r for r in content.forge_secrets.values() if r.tactic is not None and r.slot == "weapon"])
    return hs + [gear_holder(arm.tactic)]


def catch_up(content, runs, strength=3):
    """玩家武學追上本命（Joy 2026-10-17 的分寸：本命對玩家最強的一套 50～52%）：十八位本命（有本命兵器的加上兵器與人器合一）
    逐一對滿配（full_kit，SELF_KITS 套）。"""
    share = ring_share(content, runs)
    arms = {a.character: a for a in content.gear.signature_arms}
    fulls = [full_kit(content, k, strength) for k in range(SELF_KITS)]
    selfs = [self_kit(content, k) for k in range(SELF_KITS)]
    print(f"擂台（兩邊威力 150，兩個方向各 {runs} 場）：本命對滿配絕學＋配招兵器（{SELF_KITS} 套，每格{'一二三'[strength - 1]}重＋大獎）")
    print(f"  滿配對自組上品：{sum(share(a, b) for a, b in zip(fulls, selfs)) / SELF_KITS:.1%}")
    rows = []
    for fid in figures_with(content):
        sig = holders(content, [("你", "player", fid)])
        arm = arms.get(fid)
        if arm is not None:
            sig = [h.model_copy(update={"tactic": tactics.bonded(h.tactic, arm.bond)}) if arm.bond and tactics.bond_fits(h, fid, arm.bond) else h for h in sig]
            sig = sig + [gear_holder(arm.tactic)]
        vs = [share(sig, k) for k in fulls]
        rows.append(sum(vs) / len(vs))
        tag = "＋本命兵器" if arm is not None else ""
        print(f"  {content.characters[fid].name:<4}{tag:<6}{rows[-1]:5.1%}（最低 {min(vs):.0%}、最高 {max(vs):.0%}）")
    print(f"  十八位平均 {sum(rows) / len(rows):.1%}，最低 {min(rows):.1%}、最高 {max(rows):.1%}")


def own_kit(content, seed, strength=3, gear=True, fire="透", ascended=False):
    """自創滿配（以意成招，破境之前）：武學、內功各一門自創上品，三格裝滿（每格那一路一個一般功效 strength 重＋大獎），
    各一招自己長出來的招（隨機路數與勢、火候 fire、練過前幾成）；gear 時另帶一把以器配招的神器原品。純、渾不算（另量）。"""
    from tianxia import moves
    rng = random.Random(f"own|{seed}")
    hs = piece_kit(content, seed, "絕學" if ascended else "上品", strength, GRAND_SHARE, 0.5, ults=ascended)
    level = content.config.arts.move_raw_levels + 1
    for kind in ("武學", "內功"):
        attribute, stance = rng.choice(ATTRS), rng.choice(moves.STANCES)
        move = moves.build(content, kind, attribute, stance, fire, level=level)
        if ascended:  # 破境：自己的招升為絕招（piece_kit 的 ults 就是接在後面的後勁）
            move = moves.ascend(content, moves.cell(content, attribute, moves.timing_of(kind, stance)), move)
        hs.append(tactics.Holder(who="你", key="player", skill=f"own:{kind}", tactic=move))
    if gear:
        arm = rng.choice([r for r in content.forge_secrets.values() if r.tactic is not None and r.slot == "weapon"])
        hs.append(gear_holder(arm.tactic))
    return hs


def own(content, runs, strength=3):
    """以意成招之後（破境之前）：十八位本命對自創滿配，看本命贏幾成（稿案：破境之前本命略佔上風，破境之後追到 50～52%）。"""
    share = ring_share(content, runs)
    arms = {a.character: a for a in content.gear.signature_arms}
    for label, kits in (
        ("自創滿配＋配招兵器", [own_kit(content, k, strength) for k in range(SELF_KITS)]),
        ("破境滿配＋配招兵器", [own_kit(content, k, strength, ascended=True) for k in range(SELF_KITS)]),
        ("破境堆疊（一門全快、一門全陽）", [stack_kit(content, k) for k in range(SELF_KITS)]),
        ("破境最極端（兩門六格全是快）", [stack_kit(content, k, ("快", "快")) for k in range(SELF_KITS)]),
    ) if not OWN_ALL else (
        ("自創滿配＋配招兵器", [own_kit(content, k, strength) for k in range(SELF_KITS)]),
        ("自創滿配、空手", [own_kit(content, k, strength, gear=False) for k in range(SELF_KITS)]),
        ("自創滿配、招熟", [own_kit(content, k, strength, fire="熟") for k in range(SELF_KITS)]),
        ("破境滿配＋配招兵器", [own_kit(content, k, strength, ascended=True) for k in range(SELF_KITS)]),
    ):
        if PICK is not None and label not in PICK:
            continue
        rows = []
        for fid in figures_with(content):
            sig = holders(content, [("你", "player", fid)])
            arm = arms.get(fid)
            if arm is not None:
                sig = [h.model_copy(update={"tactic": tactics.bonded(h.tactic, arm.bond)}) if arm.bond and tactics.bond_fits(h, fid, arm.bond) else h for h in sig]
                sig = sig + [gear_holder(arm.tactic)]
            vs = [share(sig, k) for k in kits]
            rows.append(sum(vs) / len(vs))
        print(f"本命對{label}：十八位平均 {sum(rows) / len(rows):.1%}，最低 {min(rows):.1%}、最高 {max(rows):.1%}")
    if OWN_ALL:
        fulls = [full_kit(content, k, strength) for k in range(SELF_KITS)]
        owns = [own_kit(content, k, strength) for k in range(SELF_KITS)]
        print(f"舊滿配（兩門絕學＋絕招）對自創滿配：{sum(share(a, b) for a, b in zip(fulls, owns)) / SELF_KITS:.1%}")


def gear_holder(tactic):
    return tactics.Holder(who="你", key="player", skill="gear", tactic=tactic)


def ring_share(content, runs, hp_a=1000, hp_b=1000):
    """擂台的贏面：share(甲的戰法, 乙的戰法)，兩邊威力 150（kits 與 catch_up 共用）。
    hp_a、hp_b 是甲、乙的池子（滿的開始，hp＝hp_cap；--gear 量螭首用），預設兩邊 1000、跟加這兩個參數之前一模一樣。"""
    from tianxia import arena, battle_instance
    from tianxia import duel as duel_rules
    from tianxia.models import MOVES
    from tianxia.state import ArenaFight, ArenaSide

    cfg, bt, t = content.config.duel, content.config.battle, content.config.tactics
    power = 150.0
    ctx = tactics.Ctx(foe="", our_agility=8, team=["player"])

    def ring_once(hs_a, hs_b, seed, hp_me, hp_foe):
        rng = random.Random(f"r|{seed}")
        trng = random.Random(f"rt|{seed}")
        sc = battle_instance.strength(bt, power)
        me = ArenaSide(name="甲", power=power, scores={m: sc for m in MOVES}, hp=hp_me, hp_cap=hp_me)
        foe = ArenaSide(name="乙", power=power, scores={m: sc for m in MOVES}, hp=hp_foe, hp_cap=hp_foe)
        f = ArenaFight(id=1, foe_key="乙", me=me, foe=foe)
        ka = tactics.side_for([h.model_copy(deep=True) for h in hs_a], ctx) if hs_a else None
        kb = tactics.side_for([h.model_copy(deep=True) for h in hs_b], ctx) if hs_b else None
        f.bout = tactics.open_bout(ka, kb, "甲", "乙", pvp=True)
        arena.roll_next(f, rng, content.config.arena, cfg)
        while True:
            move = duel_rules.answer_to(f) or rng.choice(MOVES)
            if f.bout is not None:
                locked = tactics.locks(f.bout).no_moves
                if move in locked:
                    shown = duel_rules.shown_move(f)
                    move = tactics.best_against([shown] if shown else list(MOVES), [m for m in MOVES if m not in locked])
            arena.exchange_full(f, move, content, rng, trng)
            f.round += 1
            tier = arena.verdict(f, cfg)
            if tier is not None:
                return 1 if tier in WIN else (-1 if tier == "落敗" else 0)
            arena.roll_next(f, rng, content.config.arena, cfg)

    def share(hs_a, hs_b):
        """甲對乙的贏面：兩個方向（甲挑乙、乙挑甲）各 runs 場，贏 ÷（贏＋輸），和局不算。"""
        won = lost = 0
        for i in range(runs):
            r = ring_once(hs_a, hs_b, f"ab|{i}", hp_a, hp_b)
            won += r > 0
            lost += r < 0
            r = ring_once(hs_b, hs_a, f"ba|{i}", hp_b, hp_a)
            won += r < 0
            lost += r > 0
        return won / max(1, won + lost)
    return share


def kits(content, runs):
    from tianxia.models import MOVES
    t = content.config.tactics
    power = 150.0
    share = ring_share(content, runs)
    figures = figures_with(content)
    names = {fid: content.characters[fid].name for fid in figures}
    selfs = [self_kit(content, k) for k in range(SELF_KITS)]
    plain = share([], [])
    print(f"擂台（兩邊威力 {power:g}，兩個方向各 {runs} 場；都沒有戰法時 {plain:.1%}）")
    print("自組上品（隨機 %d 套）對沒有戰法：" % SELF_KITS + "　".join(f"{share(k, []):.0%}" for k in selfs))
    print("本命對自組上品（每一位對 %d 套的平均，越接近 50%% 越平）：" % SELF_KITS)
    rows = []
    for fid in figures:
        sig = holders(content, [("你", "player", fid)])
        vs = [share(sig, k) for k in selfs]
        rows.append(sum(vs) / len(vs))
        print(f"  {names[fid]:<4}{rows[-1]:5.1%}（最低 {min(vs):.0%}、最高 {max(vs):.0%}）　對沒有戰法 {share(sig, []):.0%}")
    print(f"  十八位平均 {sum(rows) / len(rows):.1%}")
    jue = [self_kit(content, k, quality="絕學") for k in range(SELF_KITS)]
    print("自組絕學對自組上品：" + f"{sum(share(a, b) for a, b in zip(jue, selfs)) / SELF_KITS:.1%}")
    print("神器特技（原品／仿品）：自組上品加上它，對同一套自組上品")
    for r in content.forge_secrets.values():
        if r.tactic is None:
            continue
        orig = sum(share(k + [gear_holder(r.tactic)], k) for k in selfs) / SELF_KITS
        copy = sum(share(k + [gear_holder(tactics.copied(r.tactic, t.copy_rate))], k) for k in selfs) / SELF_KITS
        print(f"  〔{r.tactic.name}〕{orig:5.1%}　仿品 {copy:5.1%}")
    print("名將本命兵器：自組上品加上它，對同一套自組上品；人器合一＝本命加上本命兵器（含人器合一），對只有本命")
    for arm in content.gear.signature_arms:
        alone = sum(share(k + [gear_holder(arm.tactic)], k) for k in selfs) / SELF_KITS
        sig = holders(content, [("你", "player", arm.character)])
        bonded = [h.model_copy(update={"tactic": tactics.bonded(h.tactic, arm.bond)}) if tactics.bond_fits(h, arm.character, arm.bond) else h for h in sig]
        bond = share(bonded + [gear_holder(arm.tactic)], sig) if sig else float("nan")
        print(f"  {content.characters[arm.character].name}〔{arm.tactic.name}〕{alone:5.1%}　人器合一 {bond:5.1%}")
    # 一般的仗：贏面多幾個百分點（同第一批的算法）
    ectx = tactics.Ctx(foe="對手", our_agility=8, foe_agility=rounds.foe_agility(DIFFICULTY), team=["player"])
    base = [win_rate(content, DIFFICULTY * r, [], runs, ectx) for r in RATIOS]
    lift = []
    for k in selfs:
        rates = [win_rate(content, DIFFICULTY * r, k, runs, ectx) for r in RATIOS]
        lift.append(sum(a - b for a, b in zip(rates, base)) / len(RATIOS))
    print(f"一般的仗：自組上品贏面平均 {sum(lift) / len(lift):+.1%}（最低 {min(lift):+.1%}、最高 {max(lift):+.1%}）")
    # 決戰
    tot = []
    for k in selfs:
        kit = tactics.side_for(k, tactics.Ctx(foe="", our_agility=8, team=["player"]))
        rng = random.Random(1)
        total = n = 0.0
        for i in range(runs // 9 or 1):
            side = kit.model_copy(deep=True)
            for j in range(1, 10):
                w = tactics.war_round(side, rng.choice(MOVES), 1 if rng.random() < 0.3 else 0, j, 50.0, 1.0, t, random.Random(f"w|{i}|{j}"))
                total += w.force
                n += 1
                tactics.war_close(side, rng.random() < 0.5, t, random.Random(f"wc|{i}|{j}"))
        tot.append(total / n)
    print(f"決戰：自組上品份量平均 ×{sum(tot) / len(tot):.3f}（最低 ×{min(tot):.3f}、最高 ×{max(tot):.3f}）")


# ── 寶物與玉璽（--gear，第 35 項）──────────────────────────

DIRECT, INDIRECT, UNTOUCHED = "直接", "間接", "不碰"
# 效果鍵 → 類別（計畫 2.1【PM】）：寶物八種（Config.treasures.effects）＋玉璽七片（content/seal.json 的 effect，數字在 Config.seal.effects）
# ＋玉璽碎片改版的效果（content/seal.json 的 effects，數字在 Config.seal.revamp.effects：injury、keep_silver、chuangong 是新的，其餘沿用）。
# tests/test_measure_tactics_gear.py 驗它涵蓋每一個效果鍵：之後加了新寶物或新碎片效果，要先來這裡分類，平衡表才不會漏。
# --gear 量的是舊的七個效果（改版關著）；改版的效果與每片的戰力 ×Config.seal.revamp.power 這一張表還沒量（改版第 1 批不跑平衡）
KIND = {
    "cultivate": INDIRECT, "insight": INDIRECT, "win_xinde_pct": INDIRECT, "win_exp_pct": INDIRECT,
    "seclusion": INDIRECT, "audience": UNTOUCHED, "win_material": INDIRECT, "legend": INDIRECT,
    "hp_cap": DIRECT, "talk_turns": UNTOUCHED, "practice": INDIRECT, "dodge": DIRECT,
    "stamina_regen": UNTOUCHED, "fuse_points": INDIRECT, "mate_exp": INDIRECT,
    "injury": INDIRECT, "keep_silver": UNTOUCHED, "chuangong": INDIRECT,
}
NOTE = {  # 一句：改的是哪一條（量表的字，不是玩家看的，不必給 joy 潤）
    "cultivate": "衝絕學的機會（cultivation.seize 契機頓悟、force_odds 服丹衝關）",
    "insight": "探索悟意境（三選一開著：靜心感悟擲中，sensing.rate；關著：悟意境那一支的比重）",
    "win_xinde_pct": "打贏的心得（遊歷、出陣、野怪、挑戰本人、劇情戰）",
    "win_exp_pct": "打贏的經驗（整隊一起多；滿級之後換成心得）",
    "seclusion": "閉關出關的心得",
    "audience": "求見門檻（rules.audience_bar）",
    "win_material": "打贏而且掉了素材時多掉一個（遊歷、探索野怪）",
    "legend": "探索撿破境丹的機率",
    "hp_cap": "本人氣血上限（Member.cap_scale）；扣血、回血、挨打都照上限的比例",
    "talk_turns": "每位人物每個遊戲日多談幾輪",
    "practice": "練成的心得（熔煉照原價退）",
    "dodge": "落敗閃成僵持（team.dodge_chance，只在 team.fight 收尾擲）",
    "stamina_regen": "體力自然回復",
    "fuse_points": "自創的意分（create.seal_points：底子威力的倍數）",
    "mate_exp": "同伴拿到的經驗",
    "injury": "一場仗變成內傷的倍數（改版螭首；team.take_encounter_toll、頭目戰收場、買兇的殺手）：內傷少，療傷少花銀兩、上蓋掉得慢",
    "keep_silver": "落敗不失銀兩（改版金角；Game._lose_silver）",
    "chuangong": "傳功的心得（改版歸心；chuangong.price_of）",
}
TIERS = ("大勝", "險勝", "僵持", "落敗")
CHAIN_LEVEL = 20  # 【預設】螭首連打：20 級、根骨 5、身法 5
DODGE_AGI = (5, 15)  # 【預設】金角：身法 5、15 兩檔（身法自己的閃避 0、0.2）
# 金角只把落敗改成僵持。一般的仗僵持的下緣是 −50%、運氣 ±30%，威力到難度的八成就輸不了：RATIOS（0.9 起）一場落敗都沒有，
# 所以一般的仗量 0.5～0.8；挑戰大勢人物本人的僵持收窄（rise.draw_floor）輸得多，照 RATIOS 量
DODGE_RATIOS = (0.5, 0.6, 0.7, 0.8)
SEEN_BELOW = 1.0  # 【預設】直接那幾列的差在幾個百分點以內就是看不出來（「怎麼讀」那一段）


class GearRow(NamedTuple):
    source: str  # 寶物／玉璽
    name: str  # 寶物：帶這個效果的寶物（content/gear.json）；玉璽：片名（content/seal.json）
    key: str  # 效果鍵
    kind: str  # KIND（沒分類是「?」）
    value: float  # 照 Config 讀的數字
    field: str  # 數字來自哪個 Config 欄位
    text: str  # 遊戲裡那一句（treasures.effect_text／seal_effect_text）


def gear_rows(content):
    """寶物八種（照 Config.treasures.effects 的順序）與玉璽七片（照 content/seal.json 的順序）一樣一列；數字照 Config 讀，不寫死。"""
    from tianxia import treasures
    names: dict[str, list[str]] = {}
    for item in content.gear.treasures.values():
        names.setdefault(item.effect, []).append(item.name)
    rows = [GearRow("寶物", "、".join(names.get(key, [])) or "（沒有寶物帶它）", key, KIND.get(key, "?"),
                    *_source(content, key, f"Config.treasures.effects[{key}]", value), treasures.effect_text(content, key))
            for key, value in content.config.treasures.effects.items()]
    for shard in content.seal.values():
        key = shard.effect
        value = content.config.seal.effects.get(key, 1.0 if key in treasures.MULTIPLY else 0.0)
        rows.append(GearRow("玉璽", shard.name, key, KIND.get(key, "?"), *_source(content, key, f"Config.seal.effects[{key}]", value),
                            treasures.seal_effect_text(content, key)))
    return rows


def _source(content, key, field, value):
    """（數字, 它出自哪個欄位）：照遊戲裡真的用的那一個。探索悟意境（觀山石）在探索三選一開著時是 sensing.rate 加的
    Config.explore_modes.sense_treasure_points（effects 那個倍數只拿來比 > 1，同 treasures.effect_text 照開關寫的那一句；FB-455），
    其餘照 effects。"""
    if key == "insight" and content.config.explore_modes.enabled:
        return content.config.explore_modes.sense_treasure_points, "Config.explore_modes.sense_treasure_points"
    return value, field


def wearing(content, key=None, agi=team.BASE_STAT, wis=team.BASE_STAT):
    """一個只帶著 key 那一樣的角色（寶物放寶物欄；玉璽碎片放傳承那一格、上限倍數照 seal.copy_heirloom 設），給遊戲裡真的掛點讀
    （treasures.amount、team.dodge_chance、sensing.rate）；key 是 None 就是什麼都沒帶。"""
    from tianxia import seal, treasures
    from tianxia.state import Equipment, GameState, PlayerState
    p = PlayerState(name="量表", location=next(iter(content.locations)), stats={"agi": agi, "wis": wis}, stamina=0)
    if key in content.config.treasures.effects:
        item = next(t for t in content.gear.treasures.values() if t.effect == key)
        p.treasure = Equipment(slot="treasure", id="寶:1", name=item.name, template=item.id)
    elif key is not None:
        shard = next(s for s in content.seal.values() if s.effect == key)
        p.heirloom = Equipment(slot="treasure", id=seal.HEIRLOOM_PREFIX + shard.id, name=shard.name, template=shard.id, heirloom=True)
    state = GameState(player=p)
    p.member.cap_scale = treasures.amount(state, content, "hp_cap")  # 同 seal.copy_heirloom
    return state


def kit_full(content, seed):
    """滿配：照 --catch-up 的挑法（武學重構之後的 full_kit：兩門絕學每格三重、一半帶特別功效）。"""
    return full_kit(content, seed)


def dodge_table(content, runs, kit, ratio, chances, agi=8, draw_floor=None):
    """金角：一般的仗照 win_rate 的迴圈（單次判定＋回合，種子同 win_rate），收尾再接身法閃避（team.fight 最後那一下）。
    閃避用自己的亂數 d|i，不動判定與回合那兩顆：chances 裡每一個閃避機率看到的判定與回合一模一樣，差的只有閃避。
    回每一個機率的四種結果比例（TIERS）。agi 是本人的身法（回合裡誰先出手，tactics.Ctx.our_agility）。
    draw_floor 給了是挑戰大勢人物本人的僵持收窄（rise.draw_floor，team.fight 照它改 Mods；不帶他自己的戰法）。"""
    ctx = tactics.Ctx(foe="對手", our_agility=float(agi), foe_agility=rounds.foe_agility(DIFFICULTY), team=["player"])
    mods = encounter.Mods() if draw_floor is None else encounter.Mods(draw_floor=draw_floor)
    rng = random.Random(7)
    counts = [dict.fromkeys(TIERS, 0) for _ in chances]
    for i in range(runs):
        result = (encounter.resolve_encounter(DIFFICULTY * ratio, DIFFICULTY, rng) if draw_floor is None
                  else encounter.resolve_encounter(DIFFICULTY * ratio, DIFFICULTY, rng, mods=mods))
        if kit:
            result = team.clash_result(result, mods, kit, ctx, content, random.Random(f"m|{i}"))
        for count, chance in zip(counts, chances):
            tier = encounter.dodge(result, chance, random.Random(f"d|{i}")).tier
            count[tier] = count.get(tier, 0) + 1
    return [{tier: n / runs for tier, n in count.items()} for count in counts]


def toll_share(content, tier):
    """一場扣上限的幾成：日常氣血見底（2026-10-18 計畫 Task 2 的 team.toll_fraction，開著讀 Config.grave.loss）合進來之後照它，
    還沒合進來讀 Config.encounter_neili_loss——兩邊誰先合都量得對。"""
    fraction = getattr(team, "toll_fraction", None)
    return fraction(content, tier, False, 1.0) if fraction is not None else content.config.encounter_neili_loss.get(tier, 0.0)


def chain_table(content, runs, chain, scale, ratio=1.0, level=CHAIN_LEVEL, con=team.BASE_STAT, agi=team.BASE_STAT):
    """螭首：一般的仗連打 chain 場、中間不療傷也不回血。每一場照單次判定定勝負（威力＝難度 × ratio × 氣血係數 encounter.condition_of），
    打完照 team._apply_toll 扣血（take_encounter_toll 叫的同一個，比例照 toll_share、其中 injury_share 變內傷；不帶防具與化勁）。
    scale 是本人氣血上限的倍數（Member.cap_scale：1 是沒帶）。種子每一輪 c|i，不同 scale 看到的亂數一樣。
    回每一場的（贏面, 打完剩幾成氣血〔÷這個人的上限〕）。"""
    from tianxia.state import Member
    won = [0] * chain
    left = [0.0] * chain
    for i in range(runs):
        member = Member(level=level, cap_scale=scale)
        rng = random.Random(f"c|{i}")
        for k in range(chain):
            now, cap = team.member_neili(content, member, con)
            result = encounter.resolve_encounter(DIFFICULTY * ratio * encounter.condition_of(now, cap), DIFFICULTY, rng)
            won[k] += result.tier in WIN
            team._apply_toll(content, member, toll_share(content, result.tier), agi=agi, con=con)
            now, cap = team.member_neili(content, member, con)
            left[k] += now / cap
    return [(w / runs, x / runs) for w, x in zip(won, left)]


def _tiers(odds):
    return "/".join(f"{odds[t] * 100:4.1f}" for t in TIERS)


def gear(content, runs, chain):
    """第 35 項：寶物八種與玉璽七片哪些進打仗（直接：量勝負變幾個百分點）、哪些只改成長（間接：改哪一條、改多少）、哪些不碰。
    寶物或玉璽的開關關著也照樣量（量的是開了會怎樣）：只在這一份記憶體裡的內容把兩個開關打開，量完放回去。"""
    from tianxia import seal, treasures
    cfg = content.config
    print("寶物與玉璽：哪一樣進打仗（第 35 項；只量不改，數字照 Config 讀）")
    print(f"  寶物（Config.treasures.enabled）{'開著' if treasures.on(content) else '關著'}；"
          f"玉璽（Config.seal.enabled＋content/seal.json {len(content.seal)} 片）{'開著' if seal.on(content) else '關著'}；關著也照樣量")
    print(f"  玉璽碎片改版（Config.seal.revamp.enabled）{'開著' if cfg.seal.revamp.enabled else '關著'}：這一張量的是舊的七個效果，"
          "量的時候暫時關掉改版；改版的效果與戰力還沒量")
    was = cfg.treasures.enabled, cfg.seal.enabled, cfg.seal.revamp.enabled
    cfg.treasures.enabled = cfg.seal.enabled = True
    cfg.seal.revamp.enabled = False
    try:
        rows = gear_rows(content)
        print("\n── 一覽（直接＝進打仗的數字；間接＝改成長快慢；不碰＝跟打仗無關）──")
        for kind in (DIRECT, INDIRECT, UNTOUCHED, "?"):
            for r in (r for r in rows if r.kind == kind):
                tag = "沒分類：先到 KIND 分類" if kind == "?" else kind
                print(f"  [{tag}] {r.source}〔{r.name}〕{r.text}　← {r.field}＝{r.value:g}；{NOTE.get(r.key, '')}")
        keys = {r.key for r in rows}
        print("\n── 直接 ──")
        if "dodge" in keys:
            _gear_dodge(content, runs, rows)
        if "hp_cap" in keys:
            _gear_hp(content, runs, chain, rows)
        print("  兩片同時帶：一人最多一片（seal.shard_of），金角與螭首不會在同一個人身上；寶物八種沒有一樣進打仗，所以沒有合計那一列")
        print("\n── 間接（改成長快慢；不換算成威力：換算要看玩家怎麼玩，就是在跑模擬）──")
        for r in (r for r in rows if r.kind == INDIRECT):
            print(f"  {r.source}〔{r.name}〕{_indirect(content, r)}")
        print("\n── 不碰（不進打仗）──")
        for r in (r for r in rows if r.kind == UNTOUCHED):
            print(f"  {r.source}〔{r.name}〕{_untouched(content, r)}")
        print("\n── 怎麼讀 ──")
        print(f"  直接那幾列的差在 {SEEN_BELOW:g} 個百分點以內，就是看不出來（【預設】）。")
        print("  間接那幾列只說改哪一條成長、改多少；成長換成戰力要看玩家怎麼玩，不在這裡換算（企劃者 10/14：平衡等試玩回饋）。")
        print("  數字都照 Config 讀：調了 Config.treasures.effects 或 Config.seal.effects 重跑就是新表。")
    finally:
        cfg.treasures.enabled, cfg.seal.enabled, cfg.seal.revamp.enabled = was


def _named(rows, key):
    return next(r for r in rows if r.key == key)


def _gear_dodge(content, runs, rows):
    from tianxia import rise
    r = _named(rows, "dodge")
    fig = figures_with(content)[0]
    lineup = [("沒有戰法", []), ("滿配", kit_full(content, 0)),
              (f"本命（{content.characters[fig].name}）", holders(content, [("你", "player", fig)]))]
    floor = rise.draw_floor(content)
    fights = [("一般的仗", DODGE_RATIOS, None)]
    if floor is not None:
        fights.append((f"挑戰本人（僵持收窄 {floor:g}）", RATIOS, floor))
    print(f"金角〔{r.text}〕：只在一般的仗（遊歷、出陣、探索野怪、挑戰本人）收尾擲（team.fight → team.dodge_chance）；"
          "擂台、頭目戰、奪璽單挑、決戰、切磋、截殺都不擲，勝算（team.estimate）也不含")
    print(f"  各 {runs} 場；四個數是 大勝/險勝/僵持/落敗（%），左邊沒帶、右邊帶金角；最後是落敗少了幾個百分點（全部變成僵持，大勝險勝不動）")
    print("  一般的仗威力到難度的八成就輸不了（僵持的下緣 −50%、運氣 ±30%），所以量 0.5～0.8；挑戰本人的僵持收窄，量 0.9～1.3（不帶他自己的戰法）")
    for agi in DODGE_AGI:
        bare = team.dodge_chance(wearing(content, None, agi=agi), content)
        worn = team.dodge_chance(wearing(content, "dodge", agi=agi), content)
        print(f"  身法 {agi}：閃避 {bare:.0%} → 帶金角 {worn:.0%}")
        for fight, ratios, draw in fights:
            cuts = []
            for label, kit in lineup:
                for ratio in ratios:
                    a, b = dodge_table(content, runs, kit, ratio, [bare, worn], agi=agi, draw_floor=draw)
                    cuts.append((b["落敗"] - a["落敗"]) * 100)
                    print(f"    {fight} {label:<8}威力÷難度 {ratio:<5g}{_tiers(a)} → {_tiers(b)}　落敗 {cuts[-1]:+.1f}")
            print(f"    {fight}平均落敗 {sum(cuts) / len(cuts):+.1f} 個百分點（最多 {min(cuts):+.1f}）")


def _gear_hp(content, runs, chain, rows):
    from tianxia import treasures
    r = _named(rows, "hp_cap")
    scale = treasures.amount(wearing(content, "hp_cap"), content, "hp_cap")
    cap0 = team.neili_cap(content, CHAIN_LEVEL)
    cap1 = team.neili_cap(content, CHAIN_LEVEL, scale=scale)
    src = "team.toll_fraction" if hasattr(team, "toll_fraction") else "Config.encounter_neili_loss"
    print(f"螭首〔{r.text}〕：本人氣血上限 ×{scale:g}（Member.cap_scale）")
    print(f"  一般的仗連打 {chain} 場不療傷（{CHAIN_LEVEL} 級、根骨 5、身法 5，上限 {cap0:g} → {cap1:g}；每場扣上限的幾成照 {src}，"
          f"{content.config.injury_share:.0%} 變內傷），各 {runs} 輪；每場的贏面（大勝＋險勝）左邊沒帶、右邊帶螭首，最後是打完剩幾成氣血")
    for ratio in RATIOS:
        a = chain_table(content, runs, chain, 1.0, ratio)
        b = chain_table(content, runs, chain, scale, ratio)
        diff = max(abs(x[0] - y[0]) for x, y in zip(a, b)) * 100
        print(f"    威力÷難度 {ratio:<5g}" + "　".join(f"{x[0]:5.1%}→{y[0]:5.1%}" for x, y in zip(a, b))
              + f"　剩 {a[-1][1]:.0%}→{b[-1][1]:.0%}　最大差 {diff:.1f} 個百分點")
    base = 1000
    hp = round(base * scale)
    plain, worn = ring_share(content, runs), ring_share(content, runs, hp_a=hp)
    fulls = [kit_full(content, k) for k in range(SELF_KITS)]
    fig = figures_with(content)[0]
    sig = holders(content, [("你", "player", fig)])
    print(f"  擂台（兩邊威力 150，兩個方向各 {runs} 場；帶螭首的一方池子 {hp}、對手 {base}，左邊兩邊都 {base}）：")
    for label, pairs in (
        ("滿配（帶螭首）對滿配", [(fulls[k], fulls[(k + 1) % SELF_KITS]) for k in range(SELF_KITS)]),
        (f"本命（{content.characters[fig].name}，帶螭首）對滿配", [(sig, k) for k in fulls]),
    ):
        a = sum(plain(x, y) for x, y in pairs) / len(pairs)
        b = sum(worn(x, y) for x, y in pairs) / len(pairs)
        print(f"    {label}（{SELF_KITS} 套平均）：{a:.1%} → {b:.1%}（{(b - a) * 100:+.1f}）")
    print("  頭目戰：挨打（duel.harm_of）、放手一搏的代價都照自己的上限算，按比例，同擂台，不另量")
    print("  決戰、奪璽單挑：不吃（池子是加入決戰時的快照，team._cap_of 的 plain 不乘；隨行同伴 team.mate_pool 也是）")


def _indirect(content, r):
    """間接那一列：改哪一條成長、改多少（照遊戲裡真的掛點算，不換算成威力）。"""
    from tianxia import sensing, treasures
    cfg = content.config
    amt = treasures.amount(wearing(content, r.key), content, r.key)
    if r.key == "cultivate":
        base = cfg.legend_item_bonus  # 悟性 5
        hi = cfg.breakthrough.max_chance
        return (f"衝絕學的機會 ×{amt:g}：服丹衝關 {min(hi, base):g}% → {min(hi, base * amt):g}%，契機頓悟同一個倍數"
                f"（悟性 5；夾在 Config.breakthrough.max_chance {hi:g}%）")
    if r.key == "insight":
        if cfg.explore_modes.enabled:
            loc = next(iter(content.locations.values()))
            a = sensing.rate(wearing(content, None), content, loc)
            b = sensing.rate(wearing(content, "insight"), content, loc)
            return (f"探索三選一開著：靜心感悟擲中 {a}% → {b}%（悟性 5；+Config.explore_modes.sense_treasure_points，"
                    f"夾在 sense_rate_range 上限 {cfg.sense_rate_range[1]}%；Config.treasures.effects[insight]＝"
                    f"{cfg.treasures.effects.get('insight', 1.0):g} 只在三選一關著時用）")
        return f"探索悟意境那一支的比重 ×{amt:g}（跟悟性疊乘，_explore_weights）"
    if r.key in ("win_xinde_pct", "win_exp_pct"):
        what = "心得" if r.key == "win_xinde_pct" else "經驗"
        line = f"打贏一場的{what} ×{1 + amt:g}，同一份{what}少打 {1 - 1 / (1 + amt):.0%} 場"
        if r.key == "win_exp_pct":
            line += f"；滿級之後經驗每 {cfg.maxed_exp_per_xinde} 點換 1 心得（team.maxed_xinde），這一件就是多換心得"
        return line
    if r.key == "seclusion":
        return f"閉關出關的心得 ×{1 + amt:g}（照出關那一刻身上那件）"
    if r.key == "win_material":
        return f"打贏而且這一場掉了素材時，{amt:.0%} 多一個（從掉到的挑一種；只在遊歷、探索野怪）"
    if r.key == "legend":
        base = cfg.explore_legend_chance
        return f"探索撿破境丹 {base:.0%} → {min(1.0, base * amt):.0%}（只放大門檻，擲的還是同一顆）"
    if r.key == "practice":
        full = sum(team.practice_price(content, n) for n in range(1, team.MAX_LEVEL))
        cut = sum(team.practice_price(content, n, amt) for n in range(1, team.MAX_LEVEL))
        return f"練成 ×{amt:g}：練滿十成的心得 {full} → {cut}（每一成 round(原價×{amt:g})、最少 1；熔煉照原價退）"
    if r.key == "fuse_points":
        from tianxia import create
        mid = 50  # 自創的品級一律 Config.arts.create_grade（main d0ca2c25，Joy 2026-10-21「保底上品」），意分只推底子
        lo, hi = create.power_scale_of(content, mid), create.power_scale_of(content, mid + int(amt))
        return (f"自創的意分 +{amt:g}：品級一律{content.config.arts.create_grade}，意分 {mid} 的那一門"
                f"底子 {lo:.0%} → {hi:.0%}（create.power_scale_of）")
    if r.key == "mate_exp":
        return f"同伴拿到的經驗 ×{amt:g}（本人不變）"
    return f"{r.text}（{NOTE.get(r.key, '')}）"


def _untouched(content, r):
    """不碰那一列：一句。"""
    from tianxia import treasures
    cfg = content.config
    amt = treasures.amount(wearing(content, r.key), content, r.key)
    if r.key == "audience":
        return f"求見門檻 −{amt:g}（扣完遊俠名號再扣、最低 0）"
    if r.key == "talk_turns":
        return f"每位人物每個遊戲日 {cfg.talk_turns_per_day} 輪 → {cfg.talk_turns_per_day + round(amt)} 輪"
    if r.key == "stamina_regen":
        per_hour = 3600 / cfg.stamina_regen_seconds
        return (f"體力自然回復每小時 {per_hour:g} → {per_hour * amt:g} 點（不進打仗；一樣的時間多 {amt - 1:.0%} 行動，"
                "跟新手期疊乘、回體丹不吃）")
    return f"{r.text}（{NOTE.get(r.key, '')}）"


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
