"""Build rev_perf.mjs from the developer's perf3.mjs: own origin/port, CDP port, runs per launch from argv, only PREP+PAN+PINCH
(pan kept so the pinch starts where the developer's did; zoom/fly/fit dropped)."""
import sys
from pathlib import Path

R = Path(r"C:\Users\ray61\AppData\Local\Temp\claude\C--Ray--------\86ac9c59-a3d9-4fe5-9ee7-8a5bdac64444\scratchpad\w1rev")
src = (R / "perf3_dev.mjs").read_text(encoding="utf-8").replace("\r\n", "\n")
subs = [
    ('const ORIGIN = "http://w1b.localhost:8166";', 'const ORIGIN = "http://w1rev.localhost:8167";'),
    ("launch({ port: 9466,", "launch({ port: 9477,"),
    ("const [, , outDir, pwFile, account, variant, dprS, thrS, rnd] = process.argv;",
     "const [, , outDir, pwFile, account, variant, dprS, thrS, rnd, nrunS] = process.argv;\nconst NRUN = Number(nrunS || 3);"),
    ("  for (let r = 0; r < 3; r++) {", "  for (let r = 0; r < NRUN; r++) {"),
    ("    run.zoom = await metricsDelta(() => page.eval(ZOOM));\n", ""),
    ("    run.zFit = await page.eval(FIT);\n", ""),
    ("    run.fly = await metricsDelta(() => page.eval(FLY));\n", ""),
]
for a, b in subs:
    n = src.count(a)
    if n != 1:
        print("MISS", n, a)
        sys.exit(1)
    src = src.replace(a, b)
(R / "rev_perf.mjs").write_text(src, encoding="utf-8")
print("ok")
