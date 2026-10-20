# 輿圖簡化對比圖的準備：暫存資料庫裡開一季（season21、領地爭奪開著）、一個官軍角色站在潁川郡、
# 荒丘給官軍、南陽郊野給黃巾（同中立地那一組對比圖的擺法）。只碰 scratchpad 裡的資料庫。
import io
import os
import sys
import time
from pathlib import Path

ROOT = Path(r"C:\Ray\專案\天下大勢\.claude\worktrees\serene-galileo-46e759")
HERE = Path(__file__).resolve().parent
os.environ["TIANXIA_DB"] = str(HERE / "tianxia.db")
os.environ["TIANXIA_PROFILE"] = "season21"
sys.path.insert(0, str(ROOT))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from tianxia import conquest  # noqa: E402
from tianxia.accounts import AccountStore  # noqa: E402
from tianxia.characters import open_characters  # noqa: E402
from tianxia.content import load_content  # noqa: E402
from tianxia.database import open_database  # noqa: E402
from tianxia.engine import Game  # noqa: E402
from tianxia.sqlite_world import open_world  # noqa: E402

NAME, LOGIN, PASSWORD = "映雪", "mapdisc", "mapdisc2026"

content = load_content(ROOT / "content", profile="season21")
content.config.conquest.enabled = True
content.config.ollama_url = "http://127.0.0.1:9"
store = open_world()
store.seed_first_season(content)
print("開季：", store.open_season(content, now=time.time()))
game = Game.new(content, NAME, world=store)
p = game.state.player
p.faction = "guan"
p.location = "yingchuan"
p.visited.add("yingchuan")
open_characters().save(game.state)
acc = AccountStore(open_database())
acc.register(LOGIN, PASSWORD)
acc.bind_character(LOGIN, NAME)
(HERE / "login.txt").write_text(f"{LOGIN}\n{PASSWORD}\n", encoding="utf-8")


def put(season):
    conquest.assign(season, content, {"hilltop_wilds": "guan", "nanyang_wilds": "huang"})


season = store.mutate_season(put)
print("conquest_on：", season.conquest_on, "；控制：", {k: v for k, v in season.territory.control.items() if k in ("hilltop_wilds", "nanyang_wilds", "yingchuan", "changshe")})
print("好了：", os.environ["TIANXIA_DB"])
