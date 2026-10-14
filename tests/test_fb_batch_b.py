"""回饋單乙批（PM 2026-10-14 派工：世界、決戰、玉璽、規則、內容）：一張單一段，各自的重現與修正。"""
from __future__ import annotations

import random

from tianxia import atlas
from tianxia.engine import Game


def _ids(connections):
    return {c if isinstance(c, str) else c.to for c in connections}


# ── FB-184：官軍沒有操練點 → 潁川郡與長社之間新開「官軍大營」──
# 路接潁川郡與潁川郊野（郊野再一步就是長社）：直接接長社的話，汝南荒野的小地圖上它跟黃巾別部營寨的方向字疊在一起（試過 37 個位置都疊）


def test_fb184_the_government_army_drills_at_a_camp_between_yingchuan_and_changshe(real):
    c = real
    camp = c.locations["guan_camp"]
    assert _ids(camp.connections) == {"yingchuan", "yingchuan_wilds"}
    assert all("guan_camp" in _ids(c.locations[n].connections) for n in ("yingchuan", "yingchuan_wilds"))
    assert "changshe" in _ids(c.locations["yingchuan_wilds"].connections)  # 往長社：大營 → 潁川郊野 → 長社
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
