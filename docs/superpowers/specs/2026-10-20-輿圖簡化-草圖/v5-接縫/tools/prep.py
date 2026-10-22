"""第 5 批對比圖的準備（只碰 scratchpad 的資料庫）：season21、領地爭奪開著；官軍「觀圖生」站潁川郡（潁川汝南）。三種時刻各擺一塊：
A 戰書下了、還沒開打：汝南荒野官軍進度 65（黃巾 15），官帥下了戰書（最近的攻城時段）；
B 攻城戰正在打：潁川郊野黃巾進度 62，立刻排一場（集結馬上開，伺服器下一次同步開集結）；
C 打完：荒丘官軍攻城戰打贏、剛易手（冷卻一小時）。密碼產生後寫進 login.txt，不印出來。用法：python prep.py <解出來的根目錄>"""
import io
import os
import secrets
import sys
import time
from pathlib import Path

ROOT = Path(sys.argv[1])
HERE = Path(__file__).resolve().parent
os.environ["TIANXIA_DB"] = str(HERE / "shot.db")
os.environ["TIANXIA_PROFILE"] = "season21"
for f in HERE.glob("shot.db*"):
    f.unlink()
sys.path.insert(0, str(ROOT))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from tianxia import conquest, conquest_day  # noqa: E402
from tianxia.accounts import AccountStore  # noqa: E402
from tianxia.characters import open_characters  # noqa: E402
from tianxia.content import load_content  # noqa: E402
from tianxia.database import open_database  # noqa: E402
from tianxia.engine import Game  # noqa: E402
from tianxia.sqlite_world import open_world  # noqa: E402
from tianxia.state import DayNote, SiegeSlot  # noqa: E402

NAME, LOGIN = "觀圖生", "map5shot"
password = secrets.token_urlsafe(12)
content = load_content(ROOT / "content", profile="season21")
content.config.conquest.enabled = True
content.config.ollama_url = "http://127.0.0.1:9"
store = open_world()
store.seed_first_season(content)
now = time.time()
print("開季：", store.open_season(content, now=now))
game = Game.new(content, NAME, world=store)
p = game.state.player
p.faction, p.location = "guan", "yingchuan"
p.tutorial_step = len(content.tutorial.steps)
p.stamina = float(content.config.stamina_max)
p.visited.add("yingchuan")
open_characters().save(game.state)
acc = AccountStore(open_database())
acc.register(LOGIN, password)
acc.bind_character(LOGIN, NAME)
(HERE / "login.txt").write_text(f"{LOGIN}\n{password}\n", encoding="utf-8")


def put(w):
    c = content
    # A：汝南荒野，官軍 65、黃巾 15，官帥下戰書
    conquest.push(w, c, "runan_wilds", "guan", "映雪", 40, "attack")
    conquest.push(w, c, "runan_wilds", "guan", "官帥", 25, "attack")
    conquest.push(w, c, "runan_wilds", "huang", "黃天客", 15, "attack")
    print("A 戰書：", conquest_day.place_letter(w, c, "guan", "runan_wilds", "官帥", now))
    # B：潁川郊野，黃巾 62，立刻排一場（集結馬上開）
    conquest.push(w, c, "yingchuan_wilds", "huang", "黃天客", 62, "attack")
    print("B 攻城：", conquest_day.place_now(w, c, "huang", "yingchuan_wilds", now))
    # C：荒丘，官軍攻城戰打贏、剛易手
    key = conquest_day.day_key(now, c.config)
    w.conquest.schedule.append(SiegeSlot(id=f"done-{key}", key=key, loc="hilltop_wilds", minute=12 * 60, at=w.time - 600,
                                         muster_at=w.time - 2400, attackers=["guan"], by={"guan": conquest_day.LETTER},
                                         reasons={"guan": "官帥"}, status="done", winner="guan"))
    conquest.flip(w, c, "hilltop_wilds", "guan", note=False)
    w.conquest.day_log.append(DayNote(key=key, side="guan", loc="hilltop_wilds", minute=12 * 60, by=conquest_day.LETTER, reason="官帥",
                                      result="taken", taken="guan", margin="大勝", keeper="guard", attackers=["guan"]))


season = store.mutate_season(put)
regions = {loc: content.locations[loc].region if hasattr(content.locations[loc], "region") else "?" for loc in ("runan_wilds", "yingchuan_wilds", "hilltop_wilds", "yingchuan")}
print("時程表：", [(s.loc, s.status, s.minute) for s in season.conquest.schedule])
print("控制：", {k: season.territory.control.get(k) for k in ("runan_wilds", "yingchuan_wilds", "hilltop_wilds")})
print("好了：", os.environ["TIANXIA_DB"])
