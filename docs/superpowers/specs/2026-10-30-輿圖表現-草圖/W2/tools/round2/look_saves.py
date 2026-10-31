"""W2 第二輪的局面（抄自 qa-w2）（照 W2 tools/look_saves.py；伺服器開著也行：每次拿鎖都從資料庫重讀）。
  look_saves.py open                           開季（籌備中 → 開季，此刻）
  look_saves.py place <名號> <地點> <陣營|->   擺人（體力補滿、不在路上）
  look_saves.py scene                          幾塊易手、兩塊正在翻（官軍站潁川郡看得到的那一帶），同 W1
  look_saves.py refresh                        拍圖前把局面擺回去（冷卻重新起算、進度補回）
  look_saves.py orders                         印這一季的軍令
  look_saves.py escort <起點> <終點>           官軍這一期多一道護糧
  look_saves.py clear-orders                   拿掉 w2: 開頭的軍令
  look_saves.py boost <名號> <等級> [屬性]      等級、屬性拉高
  look_saves.py tutorial <名號> <步>           改 tutorial_step（清 pending_event）
  look_saves.py show                           印控制、tug
TIANXIA_DB、TIANXIA_PROFILE 由外面設。"""
import io
import os
import sys
import time

ROOT = r"C:\Users\ray61\AppData\Local\Temp\claude\C--Ray--------\86ac9c59-a3d9-4fe5-9ee7-8a5bdac64444\scratchpad\w2b\srv"
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
        from tianxia import calendar as cal  # noqa: E402
        mine = [o for o in season.orders if o.faction == "guan"]
        week = max((o.week for o in mine), default=cal.point(season.time, content, season).cal_day)
        print("week", week)
        season.orders = [o for o in season.orders if not (o.faction == "guan" and o.template in ("escort", "intercept"))]
        season.orders.append(Order(id=f"w2:guan:escort:{week}", template="escort", faction="guan", week=week, location=start, start=start, end=end,
                                   quota=3, text="（W2 QA）護糧"))

    with world.action_lock():
        world.mutate_season(fn)
    print("escort", start, "->", end)
elif cmd == "clear-orders":
    world = open_world()

    def fn(season):
        season.orders = [o for o in season.orders if not o.id.startswith("w2:")]

    with world.action_lock():
        world.mutate_season(fn)
    print("cleared")
elif cmd == "boost":
    name, level = sys.argv[2], int(sys.argv[3])
    store = open_characters()
    world = open_world()
    with world.action_lock():
        st = store.load(name)
        m = st.player.member
        m.level = level
        if m.wugong_id:
            m.wugong_level = 10
        if m.neigong_id:
            m.neigong_level = 10
        for k in ("str", "agi", "con", "wis", "lore"):
            st.player.stats[k] = int(sys.argv[4]) if len(sys.argv) > 4 else 15
        st.player.stamina = float(content.config.stamina_max)
        store.save(st)
    print("boosted", name, level)
elif cmd == "show":
    world = open_world()
    s = world.get_season()
    print("time", s.time, "number", world.get_season_number())
    print("control", dict(s.territory.control) if s.territory else None)
    print("fights", {k: {sd: round(b.value) for sd, b in f.bars.items()} for k, f in s.conquest.fights.items()} if s.conquest else None)
