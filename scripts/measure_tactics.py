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

第三批（--kits）另量：本命對玩家自組上品（兩門上品合成武學的功效換成的戰法，隨機 SELF_KITS 套）、神器特技、名將本命兵器（含人器合一）。
擂台同樣身手的兩個人對打（兩邊都照架勢出招），兩個方向都量；另量一般的仗多的贏面與決戰的份量。

合成深度（--depth third.json …，measure_depth.py --dump 寫的）另量：十八位本命對那一季合出的第三代滿配（兩門第三代練到絕學、
各自的功效與走向、絕招、以器配招的神器原品），--layers 試一門最多幾層。

用法：.venv/Scripts/python.exe scripts/measure_tactics.py [--runs 4000] [--bouts] [--kits] [--catch-up] [--depth JSON… --layers N…]
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
    parser.add_argument("--kits", action="store_true", help="只量第三批：本命對自組上品、神器特技、名將本命兵器")
    parser.add_argument("--catch-up", action="store_true", help="只量玩家武學追上本命：十八位本命對滿配絕學＋配招兵器")
    parser.add_argument("--depth", nargs="+", metavar="JSON",
                        help="合成深度：十八位本命對第三代滿配（measure_depth.py --dump 寫的第三代武學，一份一種季）")
    parser.add_argument("--layers", type=int, nargs="+", help="--depth 試幾種一門最多幾層（從第三代的功效清單前面截，只量）")
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
    if args.kits:
        kits(content, args.runs)
        return
    if args.catch_up:
        catch_up(content, args.runs)
        return
    if args.depth:
        for cap in args.layers or [content.config.fusion_depth.max_layers]:
            for path in args.depth:
                depth_vs(content, args.runs, path, cap)
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
ATTRS = ("快", "慢", "剛", "柔", "陽", "陰", "虛", "實")


def self_kit(content, seed, quality="上品", special_share=0.5):
    """一套自組：武學、內功各一門合成武學（品質 quality），各三格功效（第一格是自己的屬性），一半的機會帶一個特別功效。"""
    from tianxia import traits
    rng = random.Random(f"kit|{seed}")
    mult = traits.multiplier(content, quality)
    lo = traits.Loadout()
    for _art in range(2):
        own = rng.choice(ATTRS)
        cells = [own, rng.choice(ATTRS), rng.choice(ATTRS)]
        for a in cells:
            hook = traits.general(content, a).hook
            lo.layers[hook] = lo.layers.get(hook, 0.0) + mult
    if rng.random() < special_share:
        sp = rng.choice([t for t in content.traits.special if t.pool])
        lo.specials[sp.hook] = sp
    return [tactics.Holder(who="你", key="player", skill=f"trait:{t.name}", tactic=t) for t in traits.tactic_defs(content, lo)]


def full_kit(content, seed, special_share=0.5):
    """滿配（玩家武學追上本命）：武學、內功各一門自己合成的絕學（各三格功效，第一格是自己的屬性），兩門的功效戰法、各一招絕招
    （層數最多的那一格，traits.ultimate_trait 的挑法），一把以器配招的神器原品（兵器的特技＋綁在武學那一招上的 ultimate_bond）。"""
    from tianxia import traits
    rng = random.Random(f"full|{seed}")
    mult = traits.multiplier(content, "絕學")
    lo = traits.Loadout()
    ults = []
    for i in range(2):
        cells = [rng.choice(ATTRS) for _ in range(3)]
        for a in cells:
            hook = traits.general(content, a).hook
            lo.layers[hook] = lo.layers.get(hook, 0.0) + mult
        top = traits.general(content, max(dict.fromkeys(cells), key=cells.count))
        ult = top.ultimate.model_copy(update={"name": f"絕學{i + 1}"})
        ults.append(tactics.bonded(ult, top.ultimate_bond) if i == 0 else ult)
    if rng.random() < special_share:
        sp = rng.choice([t for t in content.traits.special if t.pool])
        lo.specials[sp.hook] = sp
    arm = rng.choice([r for r in content.forge_secrets.values() if r.tactic is not None and r.slot == "weapon"])
    out = [tactics.Holder(who="你", key="player", skill=f"ult:{u.name}", tactic=u) for u in ults]
    out += [tactics.Holder(who="你", key="player", skill=f"trait:{t.name}", tactic=t) for t in traits.tactic_defs(content, lo)]
    return out + [gear_holder(arm.tactic)]


def catch_up(content, runs):
    """玩家武學追上本命（定案的分寸）：十八位本命（有本命兵器的加上兵器與人器合一）逐一對滿配（full_kit，SELF_KITS 套），
    本命的贏面要落在 52～60%、玩家不能反超。"""
    share = ring_share(content, runs)
    arms = {a.character: a for a in content.gear.signature_arms}
    fulls = [full_kit(content, k) for k in range(SELF_KITS)]
    selfs = [self_kit(content, k) for k in range(SELF_KITS)]
    print(f"擂台（兩邊威力 150，兩個方向各 {runs} 場）：本命對滿配絕學＋配招兵器（{SELF_KITS} 套）")
    print(f"  滿配對自組上品：{sum(share(a, b) for a, b in zip(fulls, selfs)) / SELF_KITS:.1%}")
    rows = []
    for fid in figures_with(content):
        sig = holders(content, [("你", "player", fid)])
        arm = arms.get(fid)
        if arm is not None:
            sig = [h.model_copy(update={"tactic": tactics.bonded(h.tactic, arm.bond)}) if h.figure == fid and arm.bond else h for h in sig]
            sig = sig + [gear_holder(arm.tactic)]
        vs = [share(sig, k) for k in fulls]
        rows.append(sum(vs) / len(vs))
        tag = "＋本命兵器" if arm is not None else ""
        print(f"  {content.characters[fid].name:<4}{tag:<6}{rows[-1]:5.1%}（最低 {min(vs):.0%}、最高 {max(vs):.0%}）")
    print(f"  十八位平均 {sum(rows) / len(rows):.1%}，最低 {min(rows):.1%}、最高 {max(rows):.1%}")


DEPTH_KITS = 24  # 從一種季的第三代裡配幾套


def depth_kit(content, arts, seed):
    """合成深度的第三代滿配：兩門第三代合成武學都練到絕學（功效照各自的清單、品質倍數照絕學、特別功效照各自的走向），
    各一招絕招（traits.ultimate_trait 的挑法），一把以器配招的神器原品綁在第一招上（同 full_kit）。"""
    from tianxia import traits
    from tianxia.martial_arts import with_quality
    rng = random.Random(f"depth|{seed}")
    mult = traits.multiplier(content, "絕學")
    lo = traits.Loadout()
    ults = []
    for i, art in enumerate(arts):
        art = with_quality(art, "絕學")
        mine = traits.traits_of(art)
        for attribute in dict.fromkeys(mine):
            hook = traits.general(content, attribute).hook
            lo.layers[hook] = lo.layers.get(hook, 0.0) + mine.count(attribute) * mult
        sp = traits.special(content, art.special)
        if sp is not None and sp.hook not in lo.specials:
            lo.specials[sp.hook] = sp
        top = traits.ultimate_trait(content, art)
        if top is not None:
            ult = top.ultimate.model_copy(update={"name": f"絕學{i + 1}"})
            ults.append(tactics.bonded(ult, top.ultimate_bond) if not ults else ult)
    arm = rng.choice([r for r in content.forge_secrets.values() if r.tactic is not None and r.slot == "weapon"])
    out = [tactics.Holder(who="你", key="player", skill=f"ult:{u.name}", tactic=u) for u in ults]
    out += [tactics.Holder(who="你", key="player", skill=f"trait:{t.name}", tactic=t) for t in traits.tactic_defs(content, lo)]
    return out + [gear_holder(arm.tactic)]


def depth_vs(content, runs, path, cap):
    """合成深度（Joy 2026-10-15「本命還是強一點點」）：十八位本命（同 catch_up，含本命兵器與人器合一）逐一對第三代滿配。
    滿配從那一季全服登記的第三代裡配（武學一門＋內功一門，湊不出來就任兩門），DEPTH_KITS 套；另寫十八位對哪一套的平均最低
    （玩家最強的那一套）。功效清單照 cap 從前面截（fuse_traits 擠掉的是最舊的）。"""
    import json
    from tianxia.martial_arts import MartialArt
    arts = [MartialArt.model_validate(a) for a in json.loads(Path(path).read_text(encoding="utf-8"))]
    arts = [a.model_copy(update={"traits": list(a.traits)[:cap]}) for a in arts]
    if len(arts) < 2:
        print(f"{path}：第三代不到兩門，配不出滿配")
        return
    share = ring_share(content, runs)
    rng = random.Random("depth-pairs")
    wu = [a for a in arts if a.kind != "內功"] or arts
    nei = [a for a in arts if a.kind == "內功"] or arts
    pairs = []
    for _ in range(DEPTH_KITS):
        a = rng.choice(wu)
        b = rng.choice([x for x in nei if x.id != a.id] or [x for x in arts if x.id != a.id])
        pairs.append((a, b))
    kits = [depth_kit(content, p, k) for k, p in enumerate(pairs)]
    arms = {a.character: a for a in content.gear.signature_arms}
    layers = sorted(len(a.traits) for a in arts)
    print(f"{Path(path).name}：一門最多 {cap} 層；第三代 {len(arts)} 門（層數中位 {layers[len(layers) // 2]}）；"
          f"擂台兩邊威力 150、兩個方向各 {runs} 場；本命對 {DEPTH_KITS} 套第三代滿配")
    rows, grid = [], []
    for fid in figures_with(content):
        sig = holders(content, [("你", "player", fid)])
        arm = arms.get(fid)
        if arm is not None:
            sig = [h.model_copy(update={"tactic": tactics.bonded(h.tactic, arm.bond)}) if h.figure == fid and arm.bond else h for h in sig]
            sig = sig + [gear_holder(arm.tactic)]
        vs = [share(sig, k) for k in kits]
        grid.append(vs)
        rows.append(sum(vs) / len(vs))
        print(f"  {content.characters[fid].name:<4}{rows[-1]:5.1%}（最低 {min(vs):.0%}、最高 {max(vs):.0%}）")
    per_kit = [sum(col) / len(col) for col in zip(*grid)]
    strong = min(range(len(kits)), key=per_kit.__getitem__)
    a, b = pairs[strong]
    print(f"  十八位平均 {sum(rows) / len(rows):.1%}（最低 {min(rows):.1%}、最高 {max(rows):.1%}）")
    print(f"  最強的一套（{''.join(a.traits)}＋{''.join(b.traits)}）：十八位對它平均 {per_kit[strong]:.1%}、"
          f"最低 {min(col[strong] for col in grid):.1%}；最弱的一套 {max(per_kit):.1%}")


def gear_holder(tactic):
    return tactics.Holder(who="你", key="player", skill="gear", tactic=tactic)


def ring_share(content, runs):
    """擂台的贏面：share(甲的戰法, 乙的戰法)，兩邊威力 150（kits 與 catch_up 共用）。"""
    from tianxia import arena, battle_instance
    from tianxia import duel as duel_rules
    from tianxia.models import MOVES
    from tianxia.state import ArenaFight, ArenaSide

    cfg, bt, t = content.config.duel, content.config.battle, content.config.tactics
    power = 150.0
    ctx = tactics.Ctx(foe="", our_agility=8, team=["player"])

    def ring_once(hs_a, hs_b, seed):
        rng = random.Random(f"r|{seed}")
        trng = random.Random(f"rt|{seed}")
        sc = battle_instance.strength(bt, power)
        me = ArenaSide(name="甲", power=power, scores={m: sc for m in MOVES}, hp=1000, hp_cap=1000)
        foe = ArenaSide(name="乙", power=power, scores={m: sc for m in MOVES}, hp=1000, hp_cap=1000)
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
            r = ring_once(hs_a, hs_b, f"ab|{i}")
            won += r > 0
            lost += r < 0
            r = ring_once(hs_b, hs_a, f"ba|{i}")
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
        bonded = [h.model_copy(update={"tactic": tactics.bonded(h.tactic, arm.bond)}) if h.figure == arm.character else h for h in sig]
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
