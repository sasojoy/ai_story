"""改鐵衣客的爐火狀態（伺服器開著也行，下一次請求從資料庫重讀）：python setp.py open|ready|used|poor"""
from __future__ import annotations

import io
import os
import random
import sys
from pathlib import Path

ROOT = Path(r"C:\Ray\專案\天下大勢\.claude\worktrees\wf_b66bf522-e1d-1")
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from tianxia.characters import CharacterStore  # noqa: E402
from tianxia.content import env_profile, load_content  # noqa: E402
from tianxia.engine import Game  # noqa: E402
from tianxia.sqlite_world import open_world  # noqa: E402

mode = sys.argv[1]
c = load_content(ROOT / "content", profile=env_profile())
world = open_world()
store = CharacterStore(world.db)
state = store.load("鐵衣客")
game = Game(c, state, random.Random(1), world)
p = state.player
p.stats["silver"] = 2000
if mode == "open":
    p.furnace_ready, p.furnace_day = False, -1
elif mode == "ready":
    p.furnace_ready, p.furnace_day = True, game._pill_day()
elif mode == "used":
    p.furnace_ready, p.furnace_day = False, game._pill_day()
elif mode == "poor":
    p.furnace_ready, p.furnace_day = False, -1
    p.stats["silver"] = 10
with world.db.transaction():
    store.save(state)
print(mode, p.furnace_ready, p.furnace_day, p.stats["silver"])
