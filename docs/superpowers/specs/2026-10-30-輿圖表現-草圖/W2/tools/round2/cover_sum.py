"""cover_sum.py <tag…>：cover.mjs 的結果，每一種寬一行——兩步內（含腳下）的小圖被蓋 ≥50% 幾次（照 QA：一處被兩樣蓋算兩次）、站位數、
≥95% 幾次、被誰蓋、被蓋 ≥50% 而沒掛箭頭牌的、畫面裡的名字與縮到 11px 的比例、兩步內在畫面裡的處數。"""
import io
import json
import os
import sys
from collections import defaultdict

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
OUT = r"C:\Users\ray61\AppData\Local\Temp\claude\C--Ray--------\86ac9c59-a3d9-4fe5-9ee7-8a5bdac64444\scratchpad\w2b\out"
summary = {}
for tag in sys.argv[1:]:
    with open(os.path.join(OUT, tag, "cover.json"), encoding="utf-8") as f:
        d = json.load(f)
    print("==", tag, "log", {k: len(v) for k, v in d.get("log", {}).items()})
    summary[tag] = {}
    for w in (375, 360, 320):
        rs = [r for r in d["rows"] if r["w"] == w]
        near = [(r["id"], o) for r in rs for o in r["out"] if o["hop"] is not None and o["hop"] <= 2]
        half = [x for x in near if x[1]["f"] >= 0.5]
        full = [x for x in near if x[1]["f"] >= 0.95]
        nopill = [x for x in half if not x[1].get("pill")]
        by = defaultdict(int)
        for _, o in half:
            by[o["by"]] += 1
        labs, tiny, leads = sum(r["labs"] for r in rs), sum(r["tiny"] for r in rs), sum(r["leads"] for r in rs)
        n2in, n2 = sum(r["near2In"] for r in rs), sum(r["near2"] for r in rs)
        summary[tag][w] = {"half": len(half), "stands": len({x[0] for x in half}), "full": len(full), "nopill": len(nopill), "by": dict(by),
                           "labs": labs, "tiny": tiny, "ratio": round(tiny / labs, 3) if labs else None, "leads": leads, "near2In": n2in, "near2": n2,
                           "pills": sum(len(r["pills"]) for r in rs)}
        s = summary[tag][w]
        print(f"  {w}: ≥50% {s['half']}（{s['stands']} 個站位）≥95% {s['full']} 沒掛牌 {s['nopill']} 被誰 {s['by']}｜名字 {labs} 縮字 {tiny}（{s['ratio']}）拉線 {leads}"
              f"｜兩步內在畫面裡 {n2in}/{n2}｜箭頭牌 {s['pills']}")
        print("     ", "; ".join(f"{sid}:{o['id']}({o['hop']})<{o['by']}:{o['f']}{'+牌' if o.get('pill') else ''}" for sid, o in half))
with open(os.path.join(OUT, "cover_summary.json"), "w", encoding="utf-8") as f:
    json.dump(summary, f, ensure_ascii=False, indent=1)
