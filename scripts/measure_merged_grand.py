"""合璧真意（意境合成改版 批一；設計稿 https://claude.ai/artifact/G4m44hK3At7x2bmqoAbceu ，Joy 2026-11-10「好」）：
做 32 道草案、校到跟現在那一路的真意同級、量給 Joy 看。只量、不改遊戲。

- 32 道＝陽陰虛實四路 × 攻守變心四型 × 主料兩種（陽：主剛／主快；陰：主柔／主慢；虛：主快／主柔；實：主剛／主慢）。
  做法（kind、時機）借主料那一路、同一型的神品模板（traits.json 的 god），數字照下面校；同一路兩種主料借到同一種做法的，
  第二種照 BORROW 改借別的一道。
- 校準：擂台（measure_tactics.ring_share，兩邊威力 150）十八位本命對「最強配法多帶一道真意」（同 measure_epiphany 的
  kit(BEST, god)：最強配法那一格的一般功效照舊，多一招）。每一路的基準是那一路現在的真意（烈陽、寒煞、迷蹤、金身）
  用同一種方式多帶一招；32 道每一道照二分法調一個倍數 k（發動率小於 1 的調發動率，一直在的調 _pct 數字），
  讓本命贏面跟那一路的基準差不到 TOL。
- 再用 --verify 的場數重量一次，另量「隨機破境滿配多帶一道」（一般玩家）。

用法：python scripts/measure_merged_grand.py [--runs 1000] [--verify 1000] [--procs 4] [--out draft.json]
"""
from __future__ import annotations

import argparse
import json
import multiprocessing as mp
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import measure_epiphany as me  # noqa: E402
import measure_tactics as mt  # noqa: E402
from tianxia import insight_fx  # noqa: E402

C = me.C
PATHS = {"陽": ("剛", "快"), "陰": ("柔", "慢"), "虛": ("快", "柔"), "實": ("剛", "慢")}
FORMS = ("攻", "守", "變", "心")
ATTR_KEY = {"剛": "gang", "快": "kuai", "柔": "rou", "慢": "man", "陽": "yang", "陰": "yin", "虛": "xu", "實": "shi"}
TOL = 0.006
# 同一路兩種主料借到同一種做法時，第二種改借這一道（一路之內四型 × 兩種主料八道做法都不同）
BORROW = {("虛", "柔", "攻"): "god_yin_gong", ("虛", "柔", "守"): "god_yin_xin", ("虛", "柔", "心"): "god_man_xin",
          ("實", "慢", "守"): "god_xie_shou", ("實", "慢", "攻"): "god_zheng_gong",
          # 虛快心借到連贏無隙（streak）調不動（沒有連續的數字；wins 2→1 差 9 個百分點），改借猛虎（tiger）
          ("虛", "快", "心"): "god_gang_xin"}
# 只調倍數調不到的，先改這幾個數字當起點，再照常跑二分法（倍數從 1 起；2026-11-10 逐格試過）
FIXED = {"he_xu_bian_rou": {"turns": 2.0, "stun_pct": 0.25},   # 定身／失神兩回合、定身機會降一半
         "he_yin_xin_man": {"stacks": 4.0, "stack_pct": 0.12},  # 疊四層才連環，每層推力加大
         "he_shi_xin_man": {"stacks": 4.0, "stack_pct": 0.12}}


class Fake:
    """measure_epiphany.kit 只讀 .tactic。"""

    def __init__(self, tactic):
        self.tactic = tactic


def god(attr: str, form: str):
    return next(g for g in C.traits.god if g.id == f"god_{ATTR_KEY[attr]}_{ {'攻': 'gong', '守': 'shou', '變': 'bian', '心': 'xin'}[form] }")


def scaled(tactic, k: float, name: str):
    """照 k 調：發動率小於 1 的調發動率；一直在的（1.0）調 _pct 數字（mult 調超過 1 的那一段）；都沒有就調發動率。"""
    params = dict(tactic.params)
    rate = tactic.rate
    pcts = [p for p in params if p.endswith("_pct") and params[p] > 0 and p != "chance_pct"]
    if tactic.rate < 1.0 or (not pcts and "mult" not in params):
        rate = max(0.01, min(1.0, round(tactic.rate * k, 4)))
    else:
        for p in pcts:
            params[p] = round(params[p] * k, 4)
        if "mult" in params:
            params["mult"] = round(1 + (params["mult"] - 1) * k, 4)
    return tactic.model_copy(update={"name": name, "rate": rate, "params": params})


def drafts():
    out = []
    for path, mains in PATHS.items():
        for form in FORMS:
            for main in mains:
                g = god(main, form)
                if (path, main, form) in BORROW:
                    g = next(x for x in C.traits.god if x.id == BORROW[(path, main, form)])
                i = f"he_{ATTR_KEY[path]}_{ {'攻': 'gong', '守': 'shou', '變': 'bian', '心': 'xin'}[form] }_{ATTR_KEY[main]}"
                t = g.tactic
                if i in FIXED:
                    t = t.model_copy(update={"params": {**t.params, **FIXED[i]}})
                out.append({"id": f"he_{ATTR_KEY[path]}_{ {'攻': 'gong', '守': 'shou', '變': 'bian', '心': 'xin'}[form] }_{ATTR_KEY[main]}",
                            "path": path, "form": form, "main": main, "from": g.id, "tactic": t})
    return out


def baseline_tactic(path: str):
    top = insight_fx.grand_of(C, path)
    return top.tactic.model_copy(update={"name": f"基準{top.tactic.name}"})


def job(args):
    """(標籤, tactic, 哪一種套, runs, kits) → 本命贏面平均。"""
    label, tactic, which, runs, kits = args
    # 每個行程只建一次擂台表；場數換了要重建（不然重量那一輪其實還是校準的場數）
    if me.SIGS is None or getattr(me, "_RUNS", None) != runs:
        me.SIGS, me.SHARE, me._RUNS = me.sigs(), mt.ring_share(C, runs), runs
    fake = Fake(tactic)
    if which == "best":
        packs = [me.kit(me.BEST, fake)]
    else:
        packs = [me.random_kit(k, fake) for k in range(kits)]
    rows = [sum(me.SHARE(sig, p) for p in packs) / len(packs) for _, sig in me.SIGS]
    return label, sum(rows) / len(rows), min(rows), max(rows)


def run(pool, jobs):
    return {label: (avg, lo, hi) for label, avg, lo, hi in pool.map(job, jobs, chunksize=1)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=1000)  # 300 場跟 1000 場的擂台表差半個百分點以上，校跟量用同一個場數
    ap.add_argument("--verify", type=int, default=1000)
    ap.add_argument("--kits", type=int, default=4)
    ap.add_argument("--iters", type=int, default=7)
    ap.add_argument("--procs", type=int, default=4)
    ap.add_argument("--out", default="merged_grand_draft.json")
    a = ap.parse_args()
    ds = drafts()
    with mp.Pool(a.procs) as pool:
        base = run(pool, [(p, baseline_tactic(p), "best", a.runs, a.kits) for p in PATHS])
        print("基準（本命對最強配法多帶那一路現在的真意）：" + "、".join(f"{p} {base[p][0]:.1%}" for p in PATHS), flush=True)
        lo = {d["id"]: 0.1 for d in ds}  # 起點：FIXED 的從 1 起，其餘從 0.6 起
        hi = {d["id"]: 2.0 for d in ds}
        k = {d["id"]: (1.0 if d["id"] in FIXED else 0.6) for d in ds}
        for it in range(a.iters):
            res = run(pool, [(d["id"], scaled(d["tactic"], k[d["id"]], d["id"]), "best", a.runs, a.kits) for d in ds])
            for d in ds:
                i, diff = d["id"], res[d["id"]][0] - base[d["path"]][0]
                if abs(diff) <= TOL:
                    continue
                if diff > 0:  # 本命贏得比基準多：這一道太弱，k 往上
                    lo[i] = k[i]
                else:
                    hi[i] = k[i]
                k[i] = (lo[i] + hi[i]) / 2
            off = [abs(res[d["id"]][0] - base[d["path"]][0]) for d in ds]
            if it == a.iters - 1:
                print("沒校進去的：" + "、".join(f"{d['id']} {(res[d['id']][0] - base[d['path']][0]) * 100:+.1f}" for d in ds
                                               if abs(res[d["id"]][0] - base[d["path"]][0]) > TOL), flush=True)
            print(f"第 {it + 1} 輪：最大差 {max(off) * 100:.1f} 個百分點，差超過 {TOL * 100:.1f} 的 {sum(x > TOL for x in off)} 道", flush=True)
        # 校好之後用更多場重量：基準、32 道、隨機滿配
        vb = run(pool, [(p, baseline_tactic(p), "best", a.verify, a.kits) for p in PATHS])
        vr = run(pool, [(p, baseline_tactic(p), "random", a.verify, a.kits) for p in PATHS])
        final = {d["id"]: scaled(d["tactic"], k[d["id"]], d["id"]) for d in ds}
        fb = run(pool, [(i, t, "best", a.verify, a.kits) for i, t in final.items()])
        fr = run(pool, [(i, t, "random", a.verify, a.kits) for i, t in final.items()])
    rows = []
    for d in ds:
        i = d["id"]
        rows.append({"id": i, "path": d["path"], "form": d["form"], "main": d["main"], "from": d["from"], "k": round(k[i], 4),
                     "tactic": final[i].model_dump(exclude_defaults=True),
                     "best": fb[i][0], "best_min": fb[i][1], "best_max": fb[i][2], "random": fr[i][0],
                     "best_vs_base": fb[i][0] - vb[d["path"]][0], "random_vs_base": fr[i][0] - vr[d["path"]][0]})
    print(f"重量（每格 {a.verify} 場）：基準 最強配法 " + "、".join(f"{p} {vb[p][0]:.1%}" for p in PATHS)
          + "；隨機滿配 " + "、".join(f"{p} {vr[p][0]:.1%}" for p in PATHS))
    print("id｜路・型・主｜做法｜k｜本命對最強＋這道（比基準）｜本命對隨機＋這道（比基準）｜十八位最低～最高")
    for r in rows:
        print(f"{r['id']}｜{r['path']}{r['form']}・主{r['main']}｜{r['tactic']['kind']}｜{r['k']:.2f}｜{r['best']:.1%}（{r['best_vs_base'] * 100:+.1f}）"
              f"｜{r['random']:.1%}（{r['random_vs_base'] * 100:+.1f}）｜{r['best_min']:.0%}～{r['best_max']:.0%}")
    bv = [r["best_vs_base"] for r in rows]
    print(f"32 道比基準：{min(bv) * 100:+.1f}～{max(bv) * 100:+.1f} 個百分點")
    Path(a.out).write_text(json.dumps({"base_best": {p: vb[p][0] for p in PATHS}, "base_random": {p: vr[p][0] for p in PATHS},
                                       "runs": a.runs, "verify": a.verify, "rows": rows}, ensure_ascii=False, indent=1), encoding="utf-8")
    print("寫到", a.out)


if __name__ == "__main__":
    main()
