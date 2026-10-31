"""修前修後每一張的像素差：差在哪個框裡（CSS px）、差了幾個像素。"""
import io
import os
import sys

from PIL import Image, ImageChops

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
SP = os.path.dirname(os.path.abspath(__file__))
A, B = os.path.join(SP, "out", "shots", "before"), os.path.join(SP, "out", "shots", "after")
for f in sorted(os.listdir(B)):
    if not f.endswith(".png"):
        continue
    a, b = Image.open(os.path.join(A, f)).convert("RGB"), Image.open(os.path.join(B, f)).convert("RGB")
    d = ImageChops.difference(a, b)
    box = d.getbbox()
    n = sum(1 for p in d.getdata() if max(p) > 24)
    print(f, a.size, "bbox(css)", [v // 2 for v in box] if box else None, "pixels>24", n)
