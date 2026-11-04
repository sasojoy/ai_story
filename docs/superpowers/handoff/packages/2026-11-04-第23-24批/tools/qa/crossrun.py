"""同一份 HEAD 在兩次跑的 A 側回應逐檔比：python crossrun.py <run1> <run2> [skip1]
skip1：run1 比 run2 多的那一步（之後 run1 的步數減一對齊）；不給就逐號對。"""
import os
import io
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
OUT = Path(os.environ["QA_DIR"]).resolve() / "out"
a, b = OUT / sys.argv[1], OUT / sys.argv[2]
skip = int(sys.argv[3]) if len(sys.argv) > 3 else None
fa = sorted(a.glob("*-A.bin"))
fb = {int(p.name[:4]): p for p in b.glob("*-A.bin")}
same, bad, missing = 0, [], []
for p in fa:
    n = int(p.name[:4])
    if skip is not None:
        if n == skip:
            continue
        if n > skip:
            n -= 1
    q = fb.get(n)
    if q is None:
        missing.append(p.name)
        continue
    if p.read_bytes() == q.read_bytes():
        same += 1
    else:
        bad.append((p.name, q.name))
print("run1", len(fa), "run2", len(fb), "same", same, "different", len(bad), bad[:10], "missing", missing[:10])
