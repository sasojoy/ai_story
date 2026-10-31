"""W1 後續實機的局面（照 w1fix 的 look_saves.py；伺服器開著也行：每次拿鎖都從資料庫重讀）。
  look_saves.py open                           開季（籌備中 → 開季，此刻）
  look_saves.py place <名號> <地點> <陣營|->   擺人（體力補滿）
  look_saves.py scene                          幾塊易手、兩塊正在翻（官軍站潁川郡看得到的那一帶），同 W1 那一輪
  look_saves.py show                           印控制、tug
TIANXIA_DB、TIANXIA_PROFILE 由外面設。"""
import io
import os
import sys
import time

ROOT = r"C:\Users\ray61\AppData\Local\Temp\claude\C--Ray--------\86ac9c59-a3d9-4fe5-9ee7-8a5bdac64444\scratchpad\w1b\src"
sys.path.insert(0, ROOT)
os.chdir(ROOT)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
from pathlib import Path  # noqa: E402

from tianxia import conquest  # noqa: E402
from tianxia.characters import open_characters  # noqa: E402
from tianxia.content import env_profile, load_content  # noqa: E402
from tianxia.sqlite_world import open_world  # noqa: E402

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
        conquest.flip(season, content, "hilltop_wilds", "huang", note=False)  # 荒丘被黃巾拿下：剛易手、冷卻中
        conquest.push(season, content, "runan_wilds", "guan", "映雪", 55, "attack")  # 汝南荒野（中立）官軍推到 55：正在翻
        conquest.push(season, content, "yingchuan_wilds", "huang", "黃天客", 40, "attack")  # 潁川郊野（官軍的）黃巾推到 40
        conquest.flip(season, content, "yingshui", "huang", note=False)  # 潁水河畔被黃巾拿下：多幾段白邊

    with world.action_lock():
        world.mutate_season(fn)
    print("scene set")
elif cmd == "refresh":
    # 拍圖前把局面擺回去：兩塊剛易手的冷卻重新起算，兩塊正在翻的進度補回 55／40（季曆走了一段，冷卻可能過了）
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
elif cmd == "show":
    world = open_world()
    s = world.get_season()
    print("time", s.time, "number", world.get_season_number())
    print("control", dict(s.territory.control) if s.territory else None)
    print("fights", {k: {sd: round(b.value) for sd, b in f.bars.items()} for k, f in s.conquest.fights.items()} if s.conquest else None)
