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

用法：.venv/Scripts/python.exe scripts/measure_tactics.py [--runs 4000] [--bouts] [--kits] [--catch-up [--strength 3]]
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
    parser.add_argument("--own", action="store_true", help="只量以意成招：十八位本命對自創滿配（兩門自創上品、各一招透的招）")
    parser.add_argument("--own-all", action="store_true", help="--own 另量空手、招熟、舊滿配")
    parser.add_argument("--move-scale", type=float, help="自創的招（content/create_forms.json 的 moves）會長的數全部乘這個數（只量）")
    parser.add_argument("--strength", type=int, default=3, help="--catch-up 滿配裡每個意境的強度（一重～三重）")
    parser.add_argument("--bout-strike", type=float, help="試別的 Config.tactics.bout_strike（只量）")
    parser.add_argument("--war-scale", type=float, help="試別的 Config.tactics.war_scale（只量）")
    parser.add_argument("--might-scale", type=float, help="本命底蘊（TacticDef.might）全部乘這個數（只量）")
    parser.add_argument("--grand-share", type=float, help="--catch-up 滿配每一格第二個效果是大獎的機會（預設 1.0）")
    parser.add_argument("--might-add", type=float, help="本命底蘊（TacticDef.might）每一門都加這個數（只量；一位人物兩門，合計加兩倍）")
    parser.add_argument("--tweak", nargs="+", default=[], metavar="技能.欄=數",
                        help="試別的本命戰法數字（只量）：zhangfei_wugong.rate=0.3、zhangliang_wugong.per_pct=0.05（params 裡的照鍵名）")
    args = parser.parse_args()
    content = load_content(ROOT / "content")
    if args.bout_strike is not None:
        content.config.tactics.bout_strike = args.bout_strike
    if args.war_scale is not None:
        content.config.tactics.war_scale = args.war_scale
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
    if args.grand_share is not None:
        global GRAND_SHARE
        GRAND_SHARE = args.grand_share
    if args.catch_up:
        catch_up(content, args.runs, args.strength)
        return
    if args.own:
        global OWN_ALL
        OWN_ALL = args.own_all
        if args.move_scale is not None:
            from tianxia import moves
            content.create_forms.moves = [m.model_copy(update=moves.scaled(m, args.move_scale)) for m in content.create_forms.moves]
        own(content, args.runs, args.strength)
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
OWN_ALL = False  # --own 時另量空手、招熟、舊滿配（--own-all）
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
    lo = traits.Loadout()
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
            lo.layers[hook] = lo.layers.get(hook, 0.0) + mult * strength
        if ults and cells:
            best = traits.general(content, max(dict.fromkeys(cells), key=cells.count))
            if best.ultimate is not None:
                ult = best.ultimate.model_copy(update={"name": f"絕學{i + 1}"})
                out.append(tactics.bonded(ult, best.ultimate_bond) if i == 0 else ult)
    hs = [tactics.Holder(who="你", key="player", skill=f"ult:{u.name}", tactic=u) for u in out]
    hs += [tactics.Holder(who="你", key="player", skill=f"trait:{t.name}", tactic=t) for t in traits.tactic_defs(content, lo)]
    hs += [tactics.Holder(who="你", key="player", skill=f"high:{t.name}", tactic=t) for t in lo.highs]
    return hs


def piece_kit(content, seed, quality, strength, grand_share=1.0, special_share=0.5, ults=False):
    """意境效果池之後（第二批）的一套：武學、內功各一門（品級 quality），每一格裝一份意境——那一路的一個一般功效 strength 重，
    再加第二個效果：grand_share 的機會是那一路的大獎（同一個大獎只算一次，撞了換成另一個一般功效 strength 重），其餘是另一個一般功效
    strength 重。一格裡的兩個效果最多三重（insight_fx.MAX_LAYERS）。special_share 的機會第一門一格換成秘方的特別功效。"""
    from tianxia import insight_fx, traits
    rng = random.Random(f"piece|{seed}")
    mult = traits.multiplier(content, quality)
    n = int(content.config.arts.slots.get(quality, 2))
    lo = traits.Loadout()
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
                lo.layers[t.hook] = lo.layers.get(t.hook, 0.0) + mult * strength
                layer_count[t.key] = layer_count.get(t.key, 0) + strength
        if ults and layer_count:
            ultable = {k: v for k, v in layer_count.items() if traits.general(content, k).ultimate is not None}
            if ultable:
                best = traits.general(content, max(ultable, key=ultable.get))
                ult = best.ultimate.model_copy(update={"name": f"絕學{i + 1}"})
                out.append(tactics.bonded(ult, best.ultimate_bond) if i == 0 else ult)
    hs = [tactics.Holder(who="你", key="player", skill=f"ult:{u.name}", tactic=u) for u in out]
    hs += [tactics.Holder(who="你", key="player", skill=f"trait:{t.name}", tactic=t) for t in traits.tactic_defs(content, lo)]
    hs += [tactics.Holder(who="你", key="player", skill=f"high:{t.name}", tactic=t) for t in lo.highs]
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
    ) if not OWN_ALL else (
        ("自創滿配＋配招兵器", [own_kit(content, k, strength) for k in range(SELF_KITS)]),
        ("自創滿配、空手", [own_kit(content, k, strength, gear=False) for k in range(SELF_KITS)]),
        ("自創滿配、招熟", [own_kit(content, k, strength, fire="熟") for k in range(SELF_KITS)]),
        ("破境滿配＋配招兵器", [own_kit(content, k, strength, ascended=True) for k in range(SELF_KITS)]),
    ):
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
