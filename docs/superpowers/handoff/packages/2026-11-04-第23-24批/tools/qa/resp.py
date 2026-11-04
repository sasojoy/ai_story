"""看存下來的回應：python resp.py <run 資料夾名> [re=<正規式>] <步數…>：印頂層鍵、message、latest、main.scene 的前幾百字。"""
import os
import io
import json
import re
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
OUT = Path(os.environ["QA_DIR"]).resolve() / "out"
run = OUT / sys.argv[1]
grep = None
args = sys.argv[2:]
if args and args[0].startswith("re="):
    grep = re.compile(args[0][3:])
    args = args[1:]


def strip(s):
    return re.sub(r"<[^>]+>", "", s or "")


for n in args:
    f = run / f"{int(n):04d}-A.bin"
    raw = f.read_bytes().decode("utf-8", "replace")
    try:
        d = json.loads(raw)
    except Exception:  # noqa: BLE001
        print(f"== {n} (not json) {strip(raw)[:600]}")
        continue
    if grep is not None:
        hits = sorted(set(grep.findall(raw)))
        print(f"== {n} hits {hits[:20]}")
        continue
    print(f"== {n} keys {sorted(d)[:40] if isinstance(d, dict) else type(d)}")
    if isinstance(d, dict):
        for k in ("message", "latest", "error"):
            if d.get(k):
                print(f"  [{k}] {strip(json.dumps(d[k], ensure_ascii=False))[:1500]}")
        m = d.get("main") if isinstance(d.get("main"), dict) else d
        for k in ("scene", "shop", "arena", "duel", "card"):
            if isinstance(m, dict) and m.get(k):
                print(f"  [main.{k}] {strip(json.dumps(m[k], ensure_ascii=False))[:1500]}")
