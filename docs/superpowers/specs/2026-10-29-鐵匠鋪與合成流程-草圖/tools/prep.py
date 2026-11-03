"""實機拍圖的局面（鐵匠鋪網頁 A、C、E）：開一季 week7（TIANXIA_DB、TIANXIA_PROFILE 由呼叫的人設好），建兩個角色、兩個帳號。
鐵衣客（看的人）：人在潁川的鐵匠鋪門口、背包缺階的素材、手上一把上品淬過兩次、裝備庫十來件（上中下品、淬過的、仿品、原品）、
自創走到立意之後（付了心得）、兩個合得出真意的意境、鑄譜上打中過一件還沒人打出的神器。
鑄劍人：打出玄晶劍的原品（定名寒星），鐵衣客打了一把仿品。
用法：python prep.py <scratch 資料夾>（密碼寫進那個資料夾，不印出來）"""
from __future__ import annotations

import io
import itertools
import os
import random
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(r"C:\Ray\專案\天下大勢\.claude\worktrees\wf_dc7bba53-cfb-2")
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
OUT = Path(sys.argv[1])

from tianxia import create, forge_secrets, skillview, smithing  # noqa: E402
from tianxia.characters import CharacterStore  # noqa: E402
from tianxia.content import env_profile, load_content  # noqa: E402
from tianxia.engine import Game  # noqa: E402
from tianxia.sqlite_world import open_world  # noqa: E402
from tianxia.state import Weapon, Equipment  # noqa: E402

assert os.environ.get("TIANXIA_DB", "").startswith(str(OUT)), "TIANXIA_DB 要設在 scratch 裡"
c = load_content(ROOT / "content", profile=env_profile())
c.config.ollama_url = "http://127.0.0.1:9"
now = time.time()
world = open_world()
world.seed_first_season(c)
assert world.open_season(c, now)
lineup = list(world.get_season().divine_lineup or [])
print("lineup", len(lineup))
SWORD = "wd_dark_crystal"
assert SWORD in lineup, lineup


def forge(game, rid):
    recipe = c.forge_secrets[rid]
    main = next(m.id for m in c.materials.values() if m.tier == 4 and m.attribute == recipe.main.attribute)
    aux = next(m.id for m in c.materials.values() if m.tier == 4 and m.attribute == recipe.aux.attribute)
    p = game.state.player
    p.materials[main] = p.materials.get(main, 0) + 1
    p.materials[aux] = p.materials.get(aux, 0) + 1
    item, _ = smithing.forge(game.state, c, world, recipe.kind if recipe.slot == "weapon" else smithing.ARMOR_KIND, main, aux)
    assert item is not None, rid
    return item


def base(name):
    game = Game.new(c, name, rng=random.Random(7), world=world)
    game.client = None
    p = game.state.player
    p.location, p.faction, p.tutorial_step = "yingchuan", "guan", len(c.tutorial.steps)
    p.visited.add(p.location)
    p.member.level = 20
    p.stats["silver"] = 2000
    p.stats["xinde"] = 5000
    return game


yi = base("鑄劍人")
sword = forge(yi, SWORD)
assert sword.original
assert world.name_divine(forge_secrets.key_for(SWORD), "鑄劍人", "寒星") is None

jia = base("鐵衣客")
other = next(rid for rid in lineup if rid != SWORD and c.forge_secrets[rid].slot == "weapon")
mine = forge(jia, other)  # 鐵衣客自己打出一件原品
assert mine.original
assert world.name_divine(forge_secrets.key_for(other), "鐵衣客", "裂空") is None
copy = forge(jia, SWORD)  # 寒星的仿品
assert copy.copy_of is not None
solved = next(rid for rid in lineup if rid not in (SWORD, other))
p = jia.state.player
p.divine_solved[solved] = "某個組合"
# 手上與裝備庫：forge 出來的先都收進裝備庫，手上換一把上品淬過兩次的
forged = [item for item in [p.weapon, *p.rack] if item is not None]
p.rack = [item for item in forged if item.slot == "weapon"] + [item for item in p.rack if item.slot != "weapon"]
p.weapon = Weapon(id="兵:90", name="青鋒劍", kind="劍", attribute="柔", tier=2, quality="上品", tempers=2, edge=70)
p.armor = Equipment(id="甲:90", slot="armor", name="鎖子甲", attribute="剛", tier=1, quality="中品", edge=80)
p.rack += [
    Weapon(id="兵:91", name="斬馬刀", kind="刀", attribute="剛", tier=2, quality="上品", edge=55, tempers=3),
    Weapon(id="兵:92", name="蛇矛", kind="槍", attribute="快", tier=2, quality="中品", edge=100),
    Weapon(id="兵:93", name="哨棒", kind="棍", attribute="慢", tier=1, quality="下品", edge=30),
    Weapon(id="兵:94", name="柳葉刀", kind="刀", attribute="柔", tier=1, quality="下品", edge=88, tempers=1),
    Weapon(id="兵:95", name="鐵胎弓", kind="弓弩", attribute="快", tier=3, quality="中品", edge=64),
    Weapon(id="兵:96", name="鐵拳套", kind="拳腳", attribute="剛", tier=1, quality="下品", edge=100),
    Equipment(id="甲:91", slot="armor", name="藤甲", attribute="柔", tier=1, quality="上品", edge=60),
]
p.materials = {"gang_1": 6, "gang_2": 1, "rou_1": 4, "kuai_3": 1, "man_1": 2, "man_2": 1}
# 自創走到立意之後（付了心得）
assert jia.create_begin("武學", "拳腳")
jia.create_pose(create.preset(c, "起手"))
jia.create_intent("風過林梢，影不留痕", reading=create.IntentReading(score=60, attributes=["快"]))
assert p.creating is not None and p.creating.paid > 0
# 兩個合得出真意的意境
pair = None
for a, b in itertools.combinations(sorted(c.insights)[:40], 2):
    p.insights = [a, b]
    card = skillview.forge_preview(jia.state, c, world, [a, b])
    if card and card.get("kind") == "合併" and card.get("grand_pct") is not None:
        pair = (a, b, card["grand_pct"], card["fire"]["word"])
        break
print("insights", pair)
assert pair is not None
with world.db.transaction():
    CharacterStore(world.db).save(yi.state)
    CharacterStore(world.db).save(jia.state)
for account, name in (("smithjia", "鐵衣客"), ("smithyi", "鑄劍人")):
    out = subprocess.run([sys.executable, str(ROOT / "scripts" / "set_password.py"), account, "--character", name,
                          "--db", os.environ["TIANXIA_DB"], "--local-dir", str(OUT)], capture_output=True, text=True, encoding="utf-8",
                         env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    print(account, out.returncode, (out.stdout or "").splitlines()[-1:] if out.returncode == 0 else out.stderr[-500:])
print("ok", p.weapon.name, len(p.rack), "rack")
