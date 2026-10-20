import sys
from pathlib import Path
HERE = Path(r"C:\Users\ray61\AppData\Local\Temp\claude\C--Ray----------claude-worktrees-serene-galileo-46e759\809cb46d-34d6-4713-96aa-0a3fd28bf9c7\scratchpad\mapdisc")
sys.path.insert(0, str(HERE))
from mock import frame
from mock3 import WASH_DEF, INK, PAPER, OUT, VB, base, compass, marks2, wash_soft
x0, y0, w, h = VB
svg = f"<defs>{WASH_DEF}</defs>{base}" + wash_soft() + marks2(INK, PAPER, colored_boxes=True) + compass(x0 + 48, y0 + 640, INK, PAPER)
(OUT / "定案-清甲加清乙的框.html").write_text(frame("定案", svg, "background:#E9E2CC"), encoding="utf-8")
print("ok")
