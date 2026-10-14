"""回饋單乙批（PM 2026-10-14 派工：世界、決戰、玉璽、規則、內容）：一張單一段，各自的重現與修正。"""
from __future__ import annotations

import random

from tianxia import atlas
from tianxia.engine import Game


def _ids(connections):
    return {c if isinstance(c, str) else c.to for c in connections}


# ── FB-184：官軍沒有操練點 → 潁川郡與長社之間新開「官軍大營」──
# 掛在潁川郊野上（同黃巾別部營寨掛在長社上）：潁川郡 → 潁川郊野 → 長社那條路的中間站，開局兩步走得到。
# 直接接長社，汝南荒野的小地圖上它跟黃巾別部營寨的方向字疊在一起（試過 37 個位置都疊）；也接潁川郡的話，
# 離潁川郡不超過 4.8 分鐘、離草廬 60 以上又不壓到初戰地圖的位置找不到（tests/test_real_map.py、test_real_content.py）


def test_fb184_the_government_army_drills_at_a_camp_between_yingchuan_and_changshe(real):
    c = real
    camp = c.locations["guan_camp"]
    assert _ids(camp.connections) == {"yingchuan_wilds"} and "guan_camp" in _ids(c.locations["yingchuan_wilds"].connections)
    assert {"yingchuan", "changshe"} <= _ids(c.locations["yingchuan_wilds"].connections)  # 潁川郡 → 潁川郊野 → 長社的中間站
    assert atlas.region_of(c, "guan_camp").id == "yingru" and "營寨" in camp.tags
    assert camp.enemies and all(c.squads[e].faction == "guan" for e in camp.enemies)  # 整支都是官軍：官軍的人在這裡只會操練
    assert camp.train_trend == {"yingru": 2}  # 同黃巾別部營寨的兩點、方向相反
    game = Game.new(c, "營中客", rng=random.Random(0))
    game.client = None
    p = game.state.player
    p.faction, p.location = "guan", "guan_camp"
    option = next(o for o in game.options() if o.id == "act:train")
    assert option.label.startswith("操練") and "零風險" in option.label
    guan = game.train_trend_push("guan_camp")
    silver = p.stats["silver"]
    msgs = game.choose("act:train")
    assert any("操軍擺陣" in m for m in msgs) and game.state.battles == [] and p.stats["silver"] == silver
    p.faction = "huang"
    huang = game.train_trend_push("guan_camp")
    assert guan and set(guan) == set(huang)
    assert all(guan[k] < 0 < huang[k] for k in guan)  # 官軍往官軍那一邊推、黃巾在這裡打贏往黃巾那一邊推

