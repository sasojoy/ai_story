"""神品意境（特殊頓悟，Joy 2026-10-26；設計稿 https://claude.ai/artifact/EBUqqzK3dPMpjwYTdRzLs3）：四十個模板各自多強。只量、不改數字。

擂台（measure_tactics.ring_share，兩邊威力 150）十八位本命對三種玩家：
- 最強配法（/mnt/project-files/plan/最強配法-2026-10-22，破境修法甲之後本命贏 47.5% 的那一套）；
- 最強配法裡武學第三格（快）換成這個神品：那一格的一般功效照舊三重、真意換成模板的戰法（只比戰法）；
- 隨機破境滿配（measure_tactics.own_kit ascended，去掉重算的真意）帶不帶這個神品（多一招，不拿掉別的：一般玩家槽裡多半沒有真意）。
另量同一格換成合出來的神品（那一路的真意＋一般功效三重）當對照。

設計稿的過關線：本命對「最強配法＋神品」48～50%（本命底蘊另補，--might-add 試）、四十個之間最強最弱差不超過 3 個百分點、
隨機破境滿配帶神品贏面多 8～12 個百分點（本命少贏這麼多）。

用法：python scripts/measure_epiphany.py [--runs 300] [--kits 4] [--only god_kuai_gong,...] [--might-add 0.15] [--json out.json]
"""
from __future__ import annotations

import argparse
import io
import json
import multiprocessing as mp
import sys
from pathlib import Path

# stdout 由 measure_tactics 包成 UTF-8（包兩次，先包的那一份被回收時會關掉底下的 buffer）
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import measure_tactics as mt  # noqa: E402
from tianxia import insight_fx, moves, tactics, traits  # noqa: E402
from tianxia.content import load_content  # noqa: E402

C = load_content(ROOT / "content")
WUGONG_STANCE = {"出招": "攻勢", "應招": "守勢", "乘勢": "變勢", "起手": "起勢"}
NEIGONG_STANCE = {"心法": "攻勢", "起手": "起勢"}
ARMS = {r.name: r for r in C.forge_secrets.values() if r.tactic is not None and r.slot == "weapon"}
BEST = {"a": ["陽", "陽", "快"], "b": ["陽", "慢", "慢"], "ma": ["快", "出招", True], "mb": ["慢", "起手", True],
        "arm": "隕星刀", "pure": [True, True]}
GOD_CELL = (0, 2)  # 換掉哪一格：武學第三格
MIGHT_ADD = 0.0


def gods(content):
    return {g.id: g for g in content.traits.god}


def kit(spec, god=None):
    """最強配法那一套（同 search.py 的 kit）；god 給了就把 GOD_CELL 那一格換成這個神品（一般功效三重＋它的戰法），
    god 是 "merged" 時換成那一格屬性合出來的神品（那一路的真意＋第一個一般功效三重，跟其他格一樣，只是一定帶真意）。"""
    cfg = C.config.arts
    mult = traits.multiplier(C, "絕學")
    lo, pooled, tops, out = traits.Loadout(), {}, {}, []
    extra = []
    for i, cells in enumerate((spec["a"], spec["b"])):
        bonus = 1 + (cfg.pure_bonus if spec.get("pure", [True, True])[i] else 0.0)
        layer = {}
        for j, a in enumerate(cells):
            if god is not None and god != "merged" and (i, j) == GOD_CELL:
                # 只換戰法：那一格的一般功效照舊（玩家會把神品裝在合它的那一格），真意換成神品的戰法
                g1 = insight_fx.generals(C, a)[0]
                pooled.setdefault(g1.hook, []).append(mult * 3 * bonus)
                layer[g1.key] = layer.get(g1.key, 0) + 3
                extra.append(god.tactic)
                continue
            g1, g2 = insight_fx.generals(C, a)[:2]
            top = insight_fx.grand_of(C, a)
            picks = [g1]
            forced = god == "merged" and (i, j) == GOD_CELL
            if top is not None and (forced or tops.get(top.tactic.name, (top, 0))[1] < 2):
                tops[top.tactic.name] = (top, tops.get(top.tactic.name, (top, 0))[1] + 1)
            else:
                picks.append(g2)
            for t in picks:
                pooled.setdefault(t.hook, []).append(mult * 3 * bonus)
                layer[t.key] = layer.get(t.key, 0) + 3
        ultable = {k: v for k, v in layer.items() if traits.general(C, k).ultimate is not None}
        if ultable:
            best = traits.general(C, max(ultable, key=ultable.get))
            ult = best.ultimate.model_copy(update={"name": f"絕學{i + 1}"})
            out.append(tactics.bonded(ult, best.ultimate_bond) if i == 0 else ult)
    mt.settle(C, lo, pooled)
    lo.highs = [traits.high_tactic(C, top.tactic, k) for top, k in tops.values()]
    hs = []
    level = cfg.move_raw_levels + 1
    for kind, (attr, timing, rare) in (("武學", spec["ma"]), ("內功", spec["mb"])):
        stance = (WUGONG_STANCE if kind == "武學" else NEIGONG_STANCE)[timing]
        m = moves.build(C, kind, attr, stance, "透", rare, level=level)
        m = moves.ascend(C, moves.cell(C, attr, timing, rare), m)
        hs.append(tactics.Holder(who="你", key="player", skill=f"own:{kind}", tactic=m))
    hs += [tactics.Holder(who="你", key="player", skill=f"ult:{u.name}", tactic=u) for u in out]
    hs += [tactics.Holder(who="你", key="player", skill=f"trait:{t.name}", tactic=t) for t in traits.tactic_defs(C, lo)]
    hs += [tactics.Holder(who="你", key="player", skill=f"god:{t.name}", tactic=t) for t in extra]
    if spec.get("arm"):
        hs.append(mt.gear_holder(ARMS[spec["arm"]].tactic))
    return dedup(hs)


def dedup(hs):
    seen, out = set(), []
    for h in hs:
        if h.tactic.name not in seen:
            seen.add(h.tactic.name)
            out.append(h)
    return out


def random_kit(seed, god=None):
    """隨機破境滿配（去掉重算的真意）；god 給了就多帶這個神品。"""
    hs = dedup(mt.own_kit(C, seed, ascended=True))
    if god is None:
        return hs
    # 一般玩家槽裡多半沒有真意（悟到帶真意的約 5%），神品裝進去就是多一招：不拿掉別的
    return hs + [tactics.Holder(who="你", key="player", skill=f"god:{god.tactic.name}", tactic=god.tactic)]


SIGS = None
SHARE = None


def sigs():
    arms = {a.character: a for a in C.gear.signature_arms}
    out = []
    for fid in mt.figures_with(C):
        sig = mt.holders(C, [("你", "player", fid)])
        arm = arms.get(fid)
        if arm is not None:
            sig = [h.model_copy(update={"tactic": tactics.bonded(h.tactic, arm.bond)}) if arm.bond and tactics.bond_fits(h, fid, arm.bond) else h for h in sig]
            sig = sig + [mt.gear_holder(arm.tactic)]
        if MIGHT_ADD:
            sig = [h.model_copy(update={"tactic": h.tactic.model_copy(update={"might": min(3.0, h.tactic.might + MIGHT_ADD)})})
                   if h.tactic.might else h for h in sig]
        out.append((fid, sig))
    return out


def job(args):
    """一格：(標籤, 模板 id 或 None/"merged", 哪一種套, runs, kits, might_add) → 本命贏面平均。"""
    label, gid, which, runs, kits, might_add = args
    global SIGS, SHARE, MIGHT_ADD
    if SIGS is None:
        MIGHT_ADD = might_add
        SIGS, SHARE = sigs(), mt.ring_share(C, runs)
    god = gods(C).get(gid) if gid not in (None, "merged") else gid
    if which == "best":
        packs = [kit(BEST, god)]
    else:
        packs = [random_kit(k, god if god != "merged" else None) for k in range(kits)]
    rows = [sum(SHARE(sig, p) for p in packs) / len(packs) for _, sig in SIGS]
    return label, gid, which, sum(rows) / len(rows), min(rows), max(rows)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=300)
    parser.add_argument("--kits", type=int, default=4, help="隨機破境滿配幾套")
    parser.add_argument("--only", help="只量哪幾個模板（id，逗號隔開）")
    parser.add_argument("--might-add", type=float, default=0.0, help="本命底蘊每一門加這個數（只量）")
    parser.add_argument("--no-random", action="store_true", help="不量隨機破境滿配")
    parser.add_argument("--json", help="結果另存成 JSON")
    parser.add_argument("--procs", type=int, default=4)
    a = parser.parse_args()
    ids = a.only.split(",") if a.only else list(gods(C))
    jobs = [("基準", None, "best", a.runs, a.kits, a.might_add), ("合出來的神品", "merged", "best", a.runs, a.kits, a.might_add)]
    jobs += [(gods(C)[g].name, g, "best", a.runs, a.kits, a.might_add) for g in ids]
    if not a.no_random:
        jobs += [("基準", None, "random", a.runs, a.kits, a.might_add)]
        jobs += [(gods(C)[g].name, g, "random", a.runs, a.kits, a.might_add) for g in ids]
    with mp.Pool(a.procs) as pool:
        res = pool.map(job, jobs, chunksize=1)
    by = {(gid, which): (avg, lo, hi) for _, gid, which, avg, lo, hi in res}
    base, merged = by[(None, "best")][0], by[("merged", "best")][0]
    rbase = by.get((None, "random"), (None,))[0]
    print(f"本命底蘊每門 +{a.might_add}；每格 {a.runs} 場；隨機破境滿配 {a.kits} 套")
    print(f"本命對最強配法 {base:.1%}；同一格換成合出來的神品 {merged:.1%}" + (f"；本命對隨機破境滿配 {rbase:.1%}" if rbase is not None else ""))
    print("模板｜本命對最強＋神品（比基準）｜比合出來的神品｜本命對隨機滿配＋神品（比不帶）")
    out = []
    for g in ids:
        avg = by[(g, "best")][0]
        r = by.get((g, "random"), (None,))[0]
        out.append({"id": g, "name": gods(C)[g].name, "best": avg, "random": r})
        tail = f"｜{r:.1%}（{(r - rbase) * 100:+.1f}）" if r is not None else ""
        print(f"{gods(C)[g].name}｜{avg:.1%}（{(avg - base) * 100:+.1f}）｜{(avg - merged) * 100:+.1f}{tail}")
    vals = [o["best"] for o in out]
    print(f"四十個：本命贏面 {min(vals):.1%}～{max(vals):.1%}（差 {(max(vals) - min(vals)) * 100:.1f} 個百分點）")
    if a.json:
        Path(a.json).write_text(json.dumps({"base": base, "merged": merged, "random_base": rbase, "might_add": a.might_add,
                                            "runs": a.runs, "rows": out}, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
