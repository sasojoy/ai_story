"""perf_sum.py <perf.jsonl>：每個版本、每一種手勢，六次（兩個瀏覽器 × 三次）的平均幀距、p95、超過 33ms 的幀數、最大，與那一段的 Script／Layout／RecalcStyle／Task（ms）中位數。
同一個瀏覽器裡的三次不獨立：只當清單看。"""
import json
import statistics as stx
import sys

sys.stdout.reconfigure(encoding="utf-8")
rows = [json.loads(x) for x in open(sys.argv[1], encoding="utf-8-sig") if x.strip()]
by = {}
for r in rows:
    for run in r["runs"]:
        for g in ("pan", "pinch", "zoom", "fly"):
            by.setdefault((r["variant"], g), []).append(run[g])
for g in ("pan", "pinch", "zoom", "fly"):
    print(f"== {g}")
    for v in ("W1", "FIX", "NOMINI"):
        xs = by.get((v, g), [])
        if not xs:
            continue
        med = lambda k: round(stx.median(x[k] for x in xs), 1)  # noqa: E731
        cdp = {k: round(stx.median(x["cdp"][k] for x in xs), 1) for k in ("Script", "Layout", "RecalcStyle", "Task")}
        print(f"  {v:7s} n={len(xs)} avg med {med('avg')}  p95 {sorted(x['p95'] for x in xs)}  over33 {sorted(x['over33'] for x in xs)}  max med {med('max')}  cdp {cdp}")
for v in ("W1", "FIX", "NOMINI"):
    ts = [r["throttleCheck"]["ratio"] for r in rows if r["variant"] == v]
    print(v, "throttle", ts)
