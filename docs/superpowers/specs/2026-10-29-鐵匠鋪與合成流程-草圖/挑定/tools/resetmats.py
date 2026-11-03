"""鐵衣客的背包換回拍圖那一份（熬過之後）；shop_clue 被寫成 null 的那一次也修回空字串（直接改那一列的 JSON）。"""
import json
import os
import sys

ROOT = r"C:\Ray\專案\天下大勢\.claude\worktrees\wf_b66bf522-e1d-1"
sys.path.insert(0, ROOT)
os.chdir(ROOT)
sys.stdout.reconfigure(encoding="utf-8")
from tianxia.characters import CharacterStore  # noqa: E402
from tianxia.state import GameState  # noqa: E402
from tianxia.sqlite_world import open_world  # noqa: E402

w = open_world()
with w.db.snapshot() as conn:
    row = conn.execute("SELECT key, data FROM characters WHERE name = ?", ("鐵衣客",)).fetchone()
data = json.loads(row["data"])
if data["player"].get("shop_clue") is None:
    data["player"]["shop_clue"] = ""
data["player"]["materials"] = {"gang_1": 6, "gang_2": 1, "rou_1": 4, "kuai_3": 1, "man_1": 2, "man_2": 1}
state = GameState.model_validate(data)
CharacterStore(w.db).save(state)
print("materials", CharacterStore(w.db).load("鐵衣客").player.materials)
