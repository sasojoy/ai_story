"""名聲草圖的資料：用正式內容（週末設定）建幾個示範角色，照真的引擎拿 /api/main（server.main_view）與玩家卡，存成 views.json。
不連模型（OllamaClient.from_config 回 None）、資料庫開在暫存資料夾。"""
from __future__ import annotations

import io
import json
import os
import random
import shutil
import sys
import tempfile
from pathlib import Path
from unittest import mock

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
ROOT = Path(__file__).resolve().parents[5]  # repo 的根（docs/superpowers/specs/<草圖>/產生器/）
HERE = Path(tempfile.gettempdir()) / "renown-sketch"  # 中間檔（views.json）放這裡，不進版控
HERE.mkdir(exist_ok=True)
TMP = Path(tempfile.mkdtemp(prefix="renown-sketch-"))
os.environ["TIANXIA_DB"] = str(TMP / "never.db")
sys.path.insert(0, str(ROOT))

from tianxia.ollama_client import OllamaClient  # noqa: E402

mock.patch.object(OllamaClient, "from_config", classmethod(lambda cls, *a, **k: None)).start()
mock.patch("requests.post", side_effect=RuntimeError("不連模型")).start()
mock.patch("requests.get", side_effect=RuntimeError("不連模型")).start()

import server  # noqa: E402
from tianxia import database, social  # noqa: E402
from tianxia.characters import CharacterStore  # noqa: E402
from tianxia.content import load_content  # noqa: E402
from tianxia.engine import Game  # noqa: E402
from tianxia.sqlite_world import open_world  # noqa: E402

content = load_content(ROOT / "content", profile="weekend")
world = open_world(TMP / "w.db")
if not world.get_season().storyline:
    world.seed_first_season(content)
NOW = 3 * 3600.0
world.open_season(content, now=0.0)


def make(name, faction, location, level, stats, sex=None, rank=0):
    g = Game.new(content, name, rng=random.Random(7), world=world, graduated=True, sex=sex)
    g.client = None
    g.set_hints_off(True)
    p = g.state.player
    p.faction = faction
    p.location = location
    p.member.level = level
    p.stat_points = 0
    for k, v in stats.items():
        p.stats[k] = v
    if rank:
        p.rank = rank
    for d in content.insights.values():  # 浩然、血煞先算悟過（不讓示範的那一下多出悟意境那兩行）
        if d.grant is not None:
            p.flags.add(f"悟得:{d.id}")
    g.sync(NOW)
    CharacterStore(world.db).save(g.state)
    return g


out = {}
hero = make("顧長風", "guan", "runan_market", 14, {"fame": 24, "good": 16, "evil": 3, "silver": 320, "wis": 9, "str": 8}, rank=2)
kou = make("韓七", None, "runan_market", 12, {"fame": 12, "good": 4, "evil": 22, "silver": 140})
print("hero rank", hero.state.player.rank, "affiliation", server.main_view(hero)["status"]["affiliation"])

# 六：跨段那一刻——米價一日三漲，盯著傭工量米（善名 +2、名望 +1）：名望 24 → 25 跨進名動一方
for seed in range(40):
    hero.rng = random.Random(seed)
    before = hero.state.player.stats.get("fame", 0)
    hero._present(content.events["rn_mkt_rice"])
    hero.choose("choice:0")
    if hero.state.player.stats.get("fame", 0) == before + 1:
        break
    hero.state.player.stats.update({"fame": 24, "good": 16})
print("fame after event", hero.state.player.stats.get("fame"), "good", hero.state.player.stats.get("good"))
out["cross"] = server.main_view(hero)

# 一～三：名望 27、善名 18、惡名 3
hero.state.player.stats.update({"fame": 27, "good": 18, "evil": 3})
for g, t in ((kou, NOW + 5), (hero, NOW + 10)):
    g.sync(t)
    CharacterStore(world.db).save(g.state)
out["hero"] = server.main_view(hero)
out["kou"] = server.main_view(kou)
out["card_kou"] = social.card(hero, kou)
out["card_hero"] = social.card(kou, hero)

# 五：韓七（江湖巨寇）碰上米價一日三漲
kou._present(content.events["rn_mkt_rice"])
out["event_kou"] = server.main_view(kou)

# 四：宛城之戰打到第三回合，本場戰功兩軍各三人
others = [("蘇硯", "guan", None), ("林驍", "guan", None), ("褚大石", "huang", None), ("葛三娘", "huang", "女"), ("馬奎", "huang", None)]
fighters = [hero] + [make(n, f, "wan_city", 12, {"fame": 10, "silver": 80}, sex=sx) for n, f, sx in others]
hero.state.player.location = "wan_city"
hero.state.pending_event = None
hero.sync(NOW + 20)
world.start_battle(content.battles["wancheng_jia"], now=hero.now)
for g in fighters:
    side = g.state.player.faction
    ids = [o.id for o in g.options()]
    join = f"battle:join:{side}"
    assert join in ids, (g.state.player.name, ids)
    g.choose(join)
world.mutate_battle(lambda x: setattr(x, "muster_deadline_real", -1.0))
hero.options()
plan = {"顧長風": [0, 0], "蘇硯": [0, 1], "林驍": [1, 1], "褚大石": [2, 0], "葛三娘": [1, 2], "馬奎": [2, 2]}
for r in range(2):
    for g in fighters:
        b = world.get_battle()
        if b.phase != "active" or g.state.player.name in b.round.pending_actions:
            continue
        acts = [o.id for o in g.options() if o.id.startswith("battle:act:")]
        if acts:
            g.choose(acts[plan[g.state.player.name][r] % len(acts)])
print("battle phase", world.get_battle().phase, "round", world.get_battle().round_number)
hero.sync(hero.now)
out["battle"] = server.main_view(hero)

print(json.dumps({k: (list(v.keys()) if isinstance(v, dict) else type(v).__name__) for k, v in out.items()}, ensure_ascii=False)[:2000])
(HERE / "views.json").write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
database.close_all()
shutil.rmtree(TMP, ignore_errors=True)
