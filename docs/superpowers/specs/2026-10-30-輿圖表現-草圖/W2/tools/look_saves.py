"""W2 實機的局面（照 W1 的 look_saves.py；伺服器開著也行：每次拿鎖都從資料庫重讀）。
  look_saves.py open                           開季（籌備中 → 開季，此刻）
  look_saves.py place <名號> <地點> <陣營|->   擺人（體力補滿、不在路上）
  look_saves.py scene                          幾塊易手、兩塊正在翻（官軍站潁川郡看得到的那一帶），同 W1
  look_saves.py refresh                        拍圖前把局面擺回去（冷卻重新起算、進度補回）
  look_saves.py orders                         印這一季的軍令
  look_saves.py escort <起點> <終點>           官軍這一期多一道護糧（照現有官軍那一道的期數；拍「去輿圖」帶終點的那一張）
  look_saves.py show                           印控制、tug
TIANXIA_DB、TIANXIA_PROFILE 由外面設。"""
import io
import os
import sys
import time

ROOT = r"C:\Ray\專案\天下大勢\.claude\worktrees\wf_b90e2f0a-6ca-1"
sys.path.insert(0, ROOT)
os.chdir(ROOT)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
from pathlib import Path  # noqa: E402

from tianxia import conquest  # noqa: E402
from tianxia.characters import open_characters  # noqa: E402
from tianxia.content import env_profile, load_content  # noqa: E402
from tianxia.sqlite_world import open_world  # noqa: E402
from tianxia.state import Order  # noqa: E402

content = load_content(Path(ROOT) / "content", profile=env_profile())
cmd = sys.argv[1]
if cmd == "open":
    world = open_world()
    world.seed_first_season(content)
    print("opened", world.open_season(content, now=time.time()))
elif cmd == "place":
    name, loc, faction = sys.argv[2], sys.argv[3], sys.argv[4]
    store = open_characters()
    world = open_world()
    with world.action_lock():
        st = store.load(name)
        st.player.location = loc
        st.player.journey = None
        if faction != "-":
            st.player.faction = faction
        st.player.stamina = float(content.config.stamina_max)
        store.save(st)
    print("placed", name, loc, faction)
elif cmd == "scene":
    world = open_world()

    def fn(season):
        conquest.flip(season, content, "hilltop_wilds", "huang", note=False)
        conquest.push(season, content, "runan_wilds", "guan", "映雪", 55, "attack")
        conquest.push(season, content, "yingchuan_wilds", "huang", "黃天客", 40, "attack")
        conquest.flip(season, content, "yingshui", "huang", note=False)

    with world.action_lock():
        world.mutate_season(fn)
    print("scene set")
elif cmd == "refresh":
    world = open_world()

    def fn(season):
        for loc in ("hilltop_wilds", "yingshui"):
            conquest.flip(season, content, loc, "huang", note=False)
        for loc, side, who, want in (("runan_wilds", "guan", "映雪", 55), ("yingchuan_wilds", "huang", "黃天客", 40)):
            have = conquest.bars(season, loc).get(side, 0.0)
            if want - have > 0.5:
                conquest.push(season, content, loc, side, who, want - have, "attack")

    with world.action_lock():
        world.mutate_season(fn)
    print("refreshed")
elif cmd == "orders":
    s = open_world().get_season()
    for o in s.orders:
        print(o.id, o.template, o.faction, o.week, o.location, o.start, o.end, o.done, o.text[:40])
elif cmd == "escort":
    start, end = sys.argv[2], sys.argv[3]
    world = open_world()

    def fn(season):
        mine = [o for o in season.orders if o.faction == "guan"]
        week = max((o.week for o in mine), default=1)
        season.orders = [o for o in season.orders if not (o.faction == "guan" and o.template in ("escort", "intercept"))]
        season.orders.append(Order(id=f"w2:guan:escort:{week}", template="escort", faction="guan", week=week, location=start, start=start, end=end,
                                   quota=3, text="（W2 實機）護糧"))

    with world.action_lock():
        world.mutate_season(fn)
    print("escort", start, "->", end)
elif cmd == "intercept":
    loc = sys.argv[2]
    world = open_world()

    def fn(season):
        mine = [o for o in season.orders if o.faction == "guan"]
        week = max((o.week for o in mine), default=1)
        season.orders = [o for o in season.orders if not (o.faction == "guan" and o.template in ("escort", "intercept"))]
        season.orders.append(Order(id=f"w2:guan:intercept:{week}", template="intercept", faction="guan", week=week, location=loc, quota=3, text="（W2 實機）截糧"))

    with world.action_lock():
        world.mutate_season(fn)
    print("intercept", loc)
elif cmd == "clear-orders":
    world = open_world()

    def fn(season):
        season.orders = [o for o in season.orders if not o.id.startswith("w2:")]

    with world.action_lock():
        world.mutate_season(fn)
    print("cleared")
elif cmd == "show":
    world = open_world()
    s = world.get_season()
    print("time", s.time, "number", world.get_season_number())
    print("control", dict(s.territory.control) if s.territory else None)
    print("fights", {k: {sd: round(b.value) for sd, b in f.bars.items()} for k, f in s.conquest.fights.items()} if s.conquest else None)
