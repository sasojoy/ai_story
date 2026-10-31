"""印季曆此刻是第幾天、軍令的 week，與幾個角色站在哪（TIANXIA_DB、TIANXIA_PROFILE 由外面設）。"""
import io
import os
import sys
import time

ROOT = r"C:\Users\ray61\AppData\Local\Temp\claude\C--Ray--------\86ac9c59-a3d9-4fe5-9ee7-8a5bdac64444\scratchpad\w2b\srv"
sys.path.insert(0, ROOT)
os.chdir(ROOT)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
from pathlib import Path  # noqa: E402

from tianxia import calendar as cal  # noqa: E402
from tianxia.characters import open_characters  # noqa: E402
from tianxia.content import env_profile, load_content  # noqa: E402
from tianxia.sqlite_world import open_world  # noqa: E402

content = load_content(Path(ROOT) / "content", profile=env_profile())
s = open_world().get_season()
p = cal.point(s.time, content, s)
print("season.time", round(s.time, 1), "cal_day", p.cal_day, "text", cal.point_text(p), "now", time.time())
for o in s.orders:
    print("order", o.id, o.faction, o.week, o.template, o.start, o.end)
store = open_characters()
for n in ("映雪", "聽雨"):
    st = store.load(n)
    print(n, st.player.location, st.player.faction, st.player.member.level)
