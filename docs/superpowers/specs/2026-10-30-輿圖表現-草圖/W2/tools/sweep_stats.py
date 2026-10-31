"""Stats for the W2 label sweep: how many labels shrink / spiral, visible ones only, per width and level."""
import io, json, os, re, sys
from collections import Counter

ROOT = sys.argv[1]
os.environ.setdefault("TIANXIA_DB", os.path.join(os.path.dirname(__file__), "stats.db"))
sys.path.insert(0, ROOT)
for d in ("tests", "tests/web", "tests/kit"):
    sys.path.insert(0, os.path.join(ROOT, d))
os.chdir(ROOT)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
import conftest  # noqa
for _d in sorted(p for p in (os.path.join(ROOT, "tests", x) for x in os.listdir(os.path.join(ROOT, "tests"))) if os.path.isdir(p)):
    if _d not in sys.path:
        sys.path.insert(0, _d)
import test_map_web as T  # noqa

game = T._w2()
base = game.map_base()
states = T._sweep_states(game) + T._sweep_states(game, scene=True)  # 修正輪（W2 審查 2026-10-31）：開季那一刻＋本週、正在翻、激戰
out = T.run(game, T.SWEEP_JS.replace("FRAMES", json.dumps(sorted(T.FRAMES.items()))).replace("STATES", json.dumps(states, ensure_ascii=False)), timeout=600)
pos = {p["id"]: p for p in base["places"]}
stats = Counter()
examples = {}
for case in out:
    c, vw, bottom = case["c"], case["vw"], case["room"]["bottom"]
    labs = T._labs(case["html"])
    anchor = {pid: (c["x"] + pos[pid]["x"] * c["z"], c["y"] + pos[pid]["y"] * c["z"]) for pid in pos}
    inside = lambda pid: 0 <= anchor[pid][0] <= vw and 0 <= anchor[pid][1] <= bottom
    leads = re.findall(r'<i class="mv-lead" style="left:([-\d.]+)px;top:([-\d.]+)px', case["html"])
    vis_leads = sum(1 for x, y in leads if 0 <= float(x) <= vw and 0 <= float(y) <= bottom)
    tiny_vis = sum(1 for lab in labs if "tiny" in lab[4] and inside(lab[0]))
    k = (vw, case["level"], "scene" if case["i"] >= len(states) // 2 else "open")
    stats[k + ("labels",)] += sum(1 for lab in labs if inside(lab[0]))
    stats[k + ("all",)] += len(labs)
    stats[k + ("tiny_all",)] += sum(1 for lab in labs if "tiny" in lab[4])
    stats[k + ("tiny_vis",)] += tiny_vis
    stats[k + ("lead_vis",)] += vis_leads
    stats[k + ("lead_all",)] += len(leads)
    if vis_leads:
        examples.setdefault(k, []).append((case["here"], vis_leads, [lab[0] for lab in labs if "tiny" in lab[4] and inside(lab[0])]))
for k in sorted({k[:3] for k in stats}):
    print(k, {n: stats[k + (n,)] for n in ("labels", "all", "tiny_vis", "tiny_all", "lead_vis", "lead_all")})
print("TOTAL", {n: sum(v for kk, v in stats.items() if kk[3] == n) for n in ("labels", "all", "tiny_vis", "tiny_all", "lead_vis", "lead_all")})
for k, v in sorted(examples.items()):
    print(k, v[:8])
