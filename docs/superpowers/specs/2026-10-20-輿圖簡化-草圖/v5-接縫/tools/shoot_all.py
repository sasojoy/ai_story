"""三種時刻 × 甲乙丙 × 天下圖／區圖，各拍一張（node shot5.js）。用法：python shoot_all.py [只拍的前綴，例 B]"""
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
NODE = r"C:\Users\ray61\AppData\Local\hermes\node\node.exe"
BASE = "http://map5b.localhost:7962"
PLACE = {"A": "runan_wilds", "B": "yingchuan_wilds", "C": "hilltop_wilds"}
only = sys.argv[1] if len(sys.argv) > 1 else ""
for st, loc in PLACE.items():
    for v in "甲乙丙":
        key = st + v
        if only and not key.startswith(only):
            continue
        for layer, pick in (("world", "-"), ("region", loc)):
            out = HERE / "shots" / f"{key}-{layer}.png"
            r = subprocess.run([NODE, str(HERE / "shot5.js"), "9362", BASE, str(out), "淺色", key, layer, pick],
                               capture_output=True, text=True, encoding="utf-8", errors="replace")
            print(key, layer, r.returncode, (r.stdout + r.stderr).strip()[-200:])
