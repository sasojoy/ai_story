"""goto_sum.py <tag…>：把 goto.mjs 的 goto.json 印成一格一行（倍率、你／目標／終點在不在露出來那一塊、螢幕座標、被浮著的蓋到、ok）。"""
import io
import json
import os
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
OUT = r"C:\Users\ray61\AppData\Local\Temp\claude\C--Ray--------\86ac9c59-a3d9-4fe5-9ee7-8a5bdac64444\scratchpad\w2b\out"
for tag in sys.argv[1:]:
    with open(os.path.join(OUT, tag, "goto.json"), encoding="utf-8") as f:
        R = json.load(f)
    log = R.pop("log", {})
    print("==", tag, "log", {k: len(v) for k, v in log.items()})
    for name, r in R.items():
        if "error" in r:
            print(f"  {name}: {r['error']}")
            continue
        print(f"  {name}: z {r['z']} (Z0 {r['Z0']}, lvl {r['lvl']}) me {r['meOn']} {r['meScr']} sel {r['selOn']} {r['selScr']} end {r['endOn']} {r['endScr']}"
              f" room {r['roomTop']}..{r['bottom']} drawer {r['drawerPx']} cover {r.get('hudCover')} bad {len(r['bad'])} ok {r['ok']}")
