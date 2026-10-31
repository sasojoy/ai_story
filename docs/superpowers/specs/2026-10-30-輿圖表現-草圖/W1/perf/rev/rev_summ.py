import io, json, sys, statistics as st, itertools
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
rows = [json.loads(x) for x in open(sys.argv[1], encoding="utf-8") if x.strip()]
dpr, thr = int(sys.argv[2]), int(sys.argv[3])
vals = {}
for r in rows:
    if r["dpr"] != dpr or r["throttle"] != thr or r["variant"] not in ("V", "R"):
        continue
    for i, run in enumerate(r["runs"]):
        p = run["pinch"]
        vals.setdefault(r["variant"], []).append(dict(lab=r["label"], run=i, thr=r["throttleCheck"]["ratio"], env=(r["env"]["dpr"], r["env"]["touch"], r["env"]["coarse"], r["env"]["search"]),
                                                     p50=p["p50"], p95=p["p95"], mx=p["max"], o33=p["over33"], o50=p["over50"], avg=p["avg"], frames=p["frames"], zMax=p.get("zMax"), during=p["during"],
                                                     release=p.get("release"), task=p["cdp"]["Task"]))


def mwu(a, b):
    allv = a + b; n = len(a)
    ua = sum((x > y) + 0.5 * (x == y) for x in a for y in b)
    us = [sum((x > y) + 0.5 * (x == y) for x in [allv[i] for i in idx] for y in [allv[i] for i in range(len(allv)) if i not in idx]) for idx in itertools.combinations(range(len(allv)), n)]
    mid = n * len(b) / 2
    return ua, sum(abs(x - mid) >= abs(ua - mid) - 1e-9 for x in us) / len(us)


for v, xs in vals.items():
    print(v)
    for x in xs:
        print("  ", x)
    for k in ("p95", "o33", "o50", "avg", "task", "thr"):
        a = [x[k] for x in xs]
        print(f"   {k}: median {st.median(a):.2f} mean {sum(a)/len(a):.2f}")
if "V" in vals and "R" in vals:
    for k in ("p95", "o33", "o50", "avg", "task"):
        a, b = [x[k] for x in vals["V"]], [x[k] for x in vals["R"]]
        u, p = mwu(a, b)
        mv, mr = st.median(a), st.median(b)
        av, ar = sum(a) / len(a), sum(b) / len(b)
        print(f"{k}: V {sorted(a)} R {sorted(b)}  median R better {(mv-mr)/mv:+.0%}  mean R better {(av-ar)/av:+.0%}  U={u} p={p:.2f}")
