"""量：區的多邊形幾個點、幾個字；框描到區界那一段多幾個字；塊的框（看得到的外框）穿過圓幾單位（只描塊 vs 塊＋區界）。"""
import io
import math
import os
import random
import re
import sys

ROOT = sys.argv[1]
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tests"))
sys.path.insert(0, os.path.join(ROOT, "tests", "kit"))
os.chdir(ROOT)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from conftest import real_content  # noqa: E402
from tianxia.engine import Game  # noqa: E402
from tianxia.sqlite_world import open_world  # noqa: E402

c = real_content("season21")
c.config.auto_open_first_season = True
game = Game.new(c, "沈浪", rng=random.Random(0), world=open_world())
game.client = None
p = game.state.player
p.faction, p.location = "guan", "yingchuan"
base, st = game.map_base(), game.map_state()


def poly(d):
    n = [float(x) for x in re.findall(r"-?\d+(?:\.\d+)?", d)]
    return list(zip(n[0::2], n[1::2]))


def inside(x, y, pg):
    ins, j = False, len(pg) - 1
    for i in range(len(pg)):
        (xi, yi), (xj, yj) = pg[i], pg[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
            ins = not ins
        j = i
    return ins


regions = {r["id"]: r for r in base["world"]["regions"]}
for rid, r in regions.items():
    print("region", rid, len(poly(r["d"])), "pts", len(r["d"]), "chars")
cells = {x["id"]: x for x in base["world"]["cells"]}
pos = {b["id"]: b for b in base["places"]}
R = base["view"]["patch_radius"]
patches = {b["id"] for b in base["places"] if b["id"] not in cells or not inside(b["x"], b["y"], poly(regions[cells[b["id"]]["region"]]["d"]))}
blocks = [b["id"] for b in base["places"] if b["id"] not in patches and b["id"] in st["places"]]
print("patches", sorted(patches))
print("blocks", len(blocks))
added = [len(regions[cells[b]["region"]]["d"]) + 1 for b in blocks]  # " " + rd
print("chars added per ring: mean %.1f min %d max %d" % (sum(added) / len(added), min(added), max(added)))


def walk(pg, other, step=0.25):
    """pg 落在 other 裡面的那幾段，每 step 單位取一點 → [(x, y, 長)]"""
    out = []
    for i in range(len(pg)):
        a, b = pg[i], pg[(i + 1) % len(pg)]
        L = math.hypot(b[0] - a[0], b[1] - a[1])
        if not L:
            continue
        n = max(1, round(L / step))
        for s in range(n):
            t = (s + 0.5) / n
            x, y = a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t
            if inside(x, y, other):
                out.append((x, y, L / n))
    return out


tot_old = tot_new = 0.0
rows = []
for b in blocks:
    cell, reg = poly(cells[b]["d"]), poly(regions[cells[b]["region"]]["d"])
    edge = walk(cell, reg)
    border = walk(reg, cell)
    for q in sorted(patches):
        if q not in st["places"]:
            continue
        cx, cy = pos[q]["x"], pos[q]["y"]
        ino = sum(L for x, y, L in edge if (x - cx) ** 2 + (y - cy) ** 2 <= R * R)
        inn = sum(L for x, y, L in border if (x - cx) ** 2 + (y - cy) ** 2 <= R * R)
        if ino or inn:
            rows.append((b, q, ino, inn))
            tot_old += ino
            tot_new += inn
for b, q, o, n in sorted(rows, key=lambda r: -r[3]):
    print(f"{b:20s} x {q:16s} block-edge {o:6.0f}  region-border +{n:6.0f}")
print("total block-edge inside circles %.0f, region-border added %.0f" % (tot_old, tot_new))
