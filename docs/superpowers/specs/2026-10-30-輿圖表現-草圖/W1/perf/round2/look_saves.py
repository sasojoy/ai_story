"""W1 QA 的局面（照 W1 後續 perf/look_saves.py；伺服器開著也行：每次拿鎖都從資料庫重讀）。
  look_saves.py open                           開季（籌備中 → 開季，此刻）
  look_saves.py place <名號> <地點> <陣營|->   擺人（體力補滿、不在路上）
  look_saves.py scene                          荒丘、潁水河畔被黃巾拿下（剛易手）；汝南荒野（中立）官軍推到 55、潁川郊野（官軍的）黃巾推到 40（正在翻）
  look_saves.py refresh                        冷卻重新起算、進度補回
  look_saves.py show                           印控制、tug
  look_saves.py journey <名號> <去哪>          擺成在路上（給「在路上不畫紅框」看）
TIANXIA_DB、TIANXIA_PROFILE 由外面設。"""
import io
import os
import sys
import time

ROOT = r"C:\Users\ray61\AppData\Local\Temp\claude\C--Ray--------\86ac9c59-a3d9-4fe5-9ee7-8a5bdac64444\scratchpad\w1c\src"
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
elif cmd == "boost":
    # 讓有些出陣不是必敗（橘框實的）：等級、屬性拉高
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
    print("boosted", name, level, {k: v for k, v in st.player.stats.items() if k in ("str", "agi", "con", "wis", "lore")})
elif cmd == "letter":
    # 戰書：替 side 對 loc 立刻下一張（同管理者的 admin_conquest_letter，不看門檻），集結還沒開打前輿圖是 w-letter
    from tianxia import conquest_day  # noqa: E402

    loc, side = sys.argv[2], sys.argv[3]
    world = open_world()
    out = []

    def fn(season):
        out.append(conquest_day.place_now(season, content, side, loc, time.time()))

    later = len(sys.argv) > 4 and sys.argv[4] == "later"

    def fn2(season):
        fn(season)
        if later:  # 集結延後十小時（世界時間）：還沒開集結＝輿圖的 letter（朱紅虛框）
            for s in season.conquest.schedule:
                if s.loc == loc and s.status in ("planned", "waiting"):
                    s.muster_at = season.time + 10 * 3600
                    s.at = season.time + 12 * 3600
                    s.status = "planned"

    with world.action_lock():
        world.mutate_season(fn2)
    print("letter", out, "later" if later else "")
elif cmd == "flipone":
    # 一塊地換主人（地上畫的會變：看輪詢重抓之後地有沒有跟著重寫）
    loc, side = sys.argv[2], sys.argv[3]
    world = open_world()
    with world.action_lock():
        world.mutate_season(lambda season: conquest.flip(season, content, loc, side, note=False))
    print("flipped", loc, side)
elif cmd in ("pause", "resume"):
    # 季曆停住／繼續（同管理者的 pause_clock／resume_clock）：修前修後同一個時刻拍
    import random  # noqa: E402

    from tianxia.world import resume_season_clock  # noqa: E402

    world = open_world()
    with world.action_lock():
        print(cmd, world.pause_clock(time.time()) if cmd == "pause" else resume_season_clock(world, content, time.time(), random.Random(0), "（繼續）"))
elif cmd == "show":
    world = open_world()
    s = world.get_season()
    print("time", s.time, "number", world.get_season_number())
    print("control", dict(s.territory.control) if s.territory else None)
    print("fights", {k: {sd: round(b.value) for sd, b in f.bars.items()} for k, f in s.conquest.fights.items()} if s.conquest else None)
