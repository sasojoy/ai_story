"""把 measure_ground.py 修前修後的結果排成 README 用的字：每一塊的內框涵蓋率（由少到多）、各種框。"""
import io
import json
import os
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
SP = os.path.dirname(os.path.abspath(__file__))
a = json.load(open(os.path.join(SP, "ground_before.json"), encoding="utf-8"))
b = json.load(open(os.path.join(SP, "ground_after1.json"), encoding="utf-8"))
for state in ("open", "scene"):
    ra = {(r["id"], r["kind"]): r for r in a[state]["rows"]}
    rb = {(r["id"], r["kind"]): r for r in b[state]["rows"]}
    rims = sorted((r for r in a[state]["rows"] if r["kind"] in ("ld-rim", "w-cool")), key=lambda r: (r["cover"], r["name"]))
    print(state, "rims", len(rims), "under95 before", sum(r["cover"] < 0.95 for r in rims), "after", sum(rb[(r["id"], r["kind"])]["cover"] < 0.95 for r in rims),
          "min after", min(rb[(r["id"], r["kind"])]["cover"] for r in rims))
    print("、".join(f"{r['name']} {r['cover'] * 100:.1f}→{rb[(r['id'], r['kind'])]['cover'] * 100:.0f}" for r in rims))
    for r in a[state]["rows"]:
        if r["kind"] not in ("ld-rim", "w-cool"):
            print("  ", r["name"], r["kind"], f"{r['cover'] * 100:.1f} → {rb[(r['id'], r['kind'])]['cover'] * 100:.1f}", "區界上", f"{r['region'] * 100:.0f}%")
    print("len", a[state]["len"], "→", b[state]["len"], f"+{(b[state]['len'] / a[state]['len'] - 1) * 100:.1f}%", "elements", a[state]["elements"], "→", b[state]["elements"])
