"""runs.py <perf.jsonl> <dpr> <throttle> <手勢>：每一次（六次）的 p95、超過 33ms、超過 50ms、最大，照版本列出來；另算 Mann-Whitney U（看是不是雜訊）。
注意（W1 審查 2026-10-31）：六次是兩個瀏覽器 × 三次，同一個瀏覽器裡的三次不獨立，這裡的 Mann-Whitney 是偽重複、p 不成立；只當每一次的清單看。"""
import io
import json
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
rows = [json.loads(x) for x in open(sys.argv[1], encoding="utf-8") if x.strip()]
dpr, thr, g = int(sys.argv[2]), int(sys.argv[3]), sys.argv[4]
vals = {}
for r in rows:
    if r["dpr"] != dpr or r["throttle"] != thr:
        continue
    for i, run in enumerate(r["runs"]):
        x = run[g]
        vals.setdefault(r["variant"], []).append((r["round"], i, x["p95"], x["over33"], x["over50"], x["max"], x.get("release"), x.get("settle")))
for v, xs in sorted(vals.items()):
    print(v)
    for t in xs:
        print("  ", t)


def mwu(a, b):
    """U 與小樣本的雙尾 p（精確，照排列）。"""
    import itertools
    allv = a + b
    n = len(a)
    ua =sum((x > y) + 0.5 * (x == y) for x in a for y in b)
    us = []
    for idx in itertools.combinations(range(len(allv)), n):
        sa = [allv[i] for i in idx]
        sb = [allv[i] for i in range(len(allv)) if i not in idx]
        us.append(sum((x > y) + 0.5 * (x == y) for x in sa for y in sb))
    mid = n * len(b) / 2
    p = sum(abs(x - mid) >= abs(ua - mid) - 1e-9 for x in us) / len(us)
    return ua, p


if "V" in vals and "R" in vals:
    for k, name in ((2, "p95"), (3, "over33"), (4, "over50"), (5, "max")):
        a, b = [t[k] for t in vals["V"]], [t[k] for t in vals["R"]]
        u, p = mwu(a, b)
        print(f"{name}: V {sorted(a)}  R {sorted(b)}  U(V>R)={u} p={p:.2f}")
