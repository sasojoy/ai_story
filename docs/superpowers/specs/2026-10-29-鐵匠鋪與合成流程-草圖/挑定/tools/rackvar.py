"""裝備庫一列「右邊二乘二」的幾種欄寬：寫鏡頭檔（python rackvar.py shots 輸出.json）、量完印摘要（python rackvar.py sum measure.json）"""
import json
import sys

sys.stdout.reconfigure(encoding="utf-8")
MEASURE = r"C:\Users\ray61\AppData\Local\Temp\claude\C--Ray----ai--\ade93b70-b3b7-42db-a8af-21f7a7cbdb16\scratchpad\picks\rackmeasure.js"
BTNS = ".shop-layer .rk-btns { grid-column: 3; grid-row: 1; grid-template-columns: repeat(2, minmax(0, 1fr)); }"
VARIANTS = {
    "p46": ".shop-layer .rk-row { grid-template-columns: auto minmax(0, 1fr) 46%; } " + BTNS,
    "p52": ".shop-layer .rk-row { grid-template-columns: auto minmax(0, 1fr) 52%; } " + BTNS,
    "p56": ".shop-layer .rk-row { grid-template-columns: auto minmax(0, 1fr) 56%; } " + BTNS,
    "em12": ".shop-layer .rk-row { grid-template-columns: auto minmax(0, 1fr) 12.4em; } " + BTNS,
    "em114": ".shop-layer .rk-row { grid-template-columns: auto minmax(0, 1fr) 11.4em; } " + BTNS
             + " @media (max-width: 359px) { .shop-layer .rk-row { grid-template-columns: auto minmax(0, 1fr); } .shop-layer .rk-btns { grid-column: 1 / -1; grid-row: auto; } }",
    "em11": ".shop-layer .rk-row { grid-template-columns: auto minmax(0, 1fr) 11em; } " + BTNS
            + " @media (max-width: 359px) { .shop-layer .rk-row { grid-template-columns: auto minmax(0, 1fr); } .shop-layer .rk-btns { grid-column: 1 / -1; grid-row: auto; } }",
    "jia": "",
}
SIZES = [(375, 812), (360, 780), (320, 700), (1280, 900)]

if sys.argv[1] == "shots":
    only = sys.argv[3].split(",") if len(sys.argv) > 3 else list(VARIANTS)
    shots = [{"name": f"{v}-{w}", "w": w, "h": h, "tab": "rack", "css": VARIANTS[v], "measureFile": MEASURE, "wait": 300}
             for v in only for w, h in SIZES]
    json.dump(shots, open(sys.argv[2], "w", encoding="utf-8"), ensure_ascii=False)
else:
    data = json.load(open(sys.argv[2], encoding="utf-8"))
    for name, m in data.items():
        rows = m["rows"]
        over = [(r["name"], b["text"], b["over"]) for r in rows for b in r["btns"] if b["over"] > 0.5]
        split = sum(b["split"] for r in rows for b in r["btns"]) + sum(r["lineSplit"] for r in rows)
        widths = sorted({b["w"] for r in rows for b in r["btns"]})
        print(f"{name:10} sw={m['sw']}/{m['iw']} btn={widths} nameW={min(r['nameW'] for r in rows)} "
              f"h={min(r['h'] for r in rows)}~{max(r['h'] for r in rows)} lines={max(r['lineLines'] for r in rows)} split={split} over={over}")
