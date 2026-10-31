"""summarize.py <perf.jsonl> [輸出 json]：把 perf3.mjs 的結果照「條件 × 版本 × 手勢」整理成表（Markdown 印出來），
每一格是兩輪 × 三次＝六次的中位數（超過 33ms、50ms 的幀數是每一次的平均）；打開、記憶體是兩次（兩輪各開一次）的中位數。
最後照 PM 的規則判（主要：像素比 3、降速 6 倍的捏，p95 與超過 33ms 的幀數）。"""
import io
import json
import statistics as stx
import sys
from collections import defaultdict

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
rows = [json.loads(x) for x in open(sys.argv[1], encoding="utf-8") if x.strip()]
by = defaultdict(list)
for r in rows:
    by[(r["dpr"], r["throttle"], r["variant"])].append(r)


def med(xs):
    xs = [x for x in xs if x is not None]
    return round(stx.median(xs), 1) if xs else None


def mean(xs):
    xs = [x for x in xs if x is not None]
    return round(sum(xs) / len(xs), 1) if xs else None


def cell(launches):
    runs = [run for L in launches for run in L["runs"]]
    out = {"n": len(runs), "launches": len(launches)}
    for g in ("pan", "pinch", "zoom", "fly"):
        xs = [run[g] for run in runs]
        out[g] = {k: med([x.get(k) for x in xs]) for k in ("p50", "p95", "max", "avg")}
        out[g]["max"] = max(x["max"] for x in xs)
        out[g].update({k: mean([x.get(k) for x in xs]) for k in ("over33", "over50")})
        for k in ("release", "settle", "groundDone", "settleAfterFly", "flyMs"):
            if any(k in x for x in xs):
                out[g][k] = med([x.get(k) for x in xs])
        out[g]["writesDuring"] = sum(x.get("during", 0) for x in xs)
        out[g]["groundWrites"] = sum(x.get("groundWrites", 0) for x in xs)
        out[g]["cdp"] = {k: med([x["cdp"][k] for x in xs]) for k in ("Layout", "RecalcStyle", "Script", "Task")}
    out["open"] = med([L["open"]["open"] for L in launches])
    out["openFromFrame"] = med([L["open"]["fromFrame"] for L in launches])
    out["throttleRatio"] = [L["throttleCheck"]["ratio"] for L in launches]
    for when in ("memOpen", "memAfter"):
        m = [L[when] for L in launches]
        out[when] = {"heapMB": med([x["heapMB"] for x in m]), "domNodes": med([x["domNodes"] for x in m]), "all": med([x["all"] for x in m]),
                     "px": max(x["px"] for x in m), "cw": m[0]["cw"], "ch": m[0]["ch"],
                     "procMB": med([(x.get("proc") or {}).get("allMB") for x in m]), "rendererMB": med([(x.get("proc") or {}).get("rendererMB") for x in m]),
                     "gpuMB": med([(x.get("proc") or {}).get("gpuMB") for x in m])}
    return out


cells = {f"{d}|{t}|{v}": cell(L) for (d, t, v), L in sorted(by.items(), key=lambda kv: (-kv[0][0], -kv[0][1], kv[0][2]))}
if len(sys.argv) > 2:
    json.dump(cells, open(sys.argv[2], "w", encoding="utf-8"), ensure_ascii=False, indent=1)

NAME = {"V": "V 向量", "R": "R 點陣", "S1": "S1 預設（參考）"}
print("| 條件 | 版本 | 拖 p50／p95／最大・>33／>50 | 捏 p50／p95／最大・>33／>50 | 捏到 2.4 放手 p95・放手→穩 | 飛 p95／最大・>33・飛完→穩 | 拖、捏放手 | 打開→地畫好 | heap 開／後（MB） | DOM 節點 開／後 | canvas 像素 | 瀏覽器私有記憶體 開／後（MB） |")
print("|---|---|---|---|---|---|---|---|---|---|---|---|")
for key, c in cells.items():
    d, t, v = key.split("|")
    pan, pin, zm, fly = c["pan"], c["pinch"], c["zoom"], c["fly"]
    px = c["memAfter"]["px"]
    print(f"| 像素比 {d}・降速 {t}× | {NAME[v]} | {pan['p50']}／{pan['p95']}／{pan['max']}・{pan['over33']}／{pan['over50']} | "
          f"{pin['p50']}／{pin['p95']}／{pin['max']}・{pin['over33']}／{pin['over50']} | {zm['p95']}・{zm['settle']} | "
          f"{fly['p95']}／{fly['max']}・{fly['over33']}・{fly['settleAfterFly']} | {pan['release']}、{pin['release']} | {c['open']} | "
          f"{c['memOpen']['heapMB']}／{c['memAfter']['heapMB']} | {c['memOpen']['domNodes']}／{c['memAfter']['domNodes']} | "
          f"{('%.1f 萬（%s×%s）' % (px / 1e4, c['memAfter']['cw'], c['memAfter']['ch'])) if px else '—'} | {c['memOpen']['procMB']}／{c['memAfter']['procMB']} |")
print()
print("| 條件 | 版本 | 捏途中 Layout／RecalcStyle／Script／Task（ms） | 拖途中 同上 | 途中重寫或重烤地（六次合計） |")
print("|---|---|---|---|---|")
for key, c in cells.items():
    d, t, v = key.split("|")
    p, q = c["pinch"]["cdp"], c["pan"]["cdp"]
    print(f"| 像素比 {d}・降速 {t}× | {NAME[v]} | {p['Layout']}／{p['RecalcStyle']}／{p['Script']}／{p['Task']} | {q['Layout']}／{q['RecalcStyle']}／{q['Script']}／{q['Task']} | "
          f"拖 {c['pan']['writesDuring']}、捏 {c['pinch']['writesDuring']}、捏到 2.4 {c['zoom']['writesDuring']} |")


# PM 的規則：主要看像素比 3、降速 6 倍的捏（p95、超過 33ms 的幀數）
def better(a, b):
    """a 比 b 好幾成（正＝a 好）：(b − a) / b。"""
    return None if a is None or b is None or b == 0 else (b - a) / b


V, R = cells.get("3|6|V"), cells.get("3|6|R")
if V and R:
    p95, o33 = better(R["pinch"]["p95"], V["pinch"]["p95"]), better(R["pinch"]["over33"], V["pinch"]["over33"])
    print()
    print(f"主要指標（像素比 3、降速 6 倍的捏）：p95 V {V['pinch']['p95']}、R {R['pinch']['p95']}（R 好 {p95:+.0%}）；"
          f"超過 33ms V {V['pinch']['over33']}、R {R['pinch']['over33']}（R 好 {o33:+.0%}）" if o33 is not None else "")
    others = {"拖 p95": (V["pan"]["p95"], R["pan"]["p95"]), "捏放手": (V["pinch"]["release"], R["pinch"]["release"]),
              "捏到 2.4 放手→穩": (V["zoom"]["settle"], R["zoom"]["settle"]), "打開": (V["open"], R["open"]),
              "heap（後）": (V["memAfter"]["heapMB"], R["memAfter"]["heapMB"])}
    for k, (a, b) in others.items():
        print(f"  {k}: V {a}、R {b}（R 好 {better(b, a):+.0%}）")
