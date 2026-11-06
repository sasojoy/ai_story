"""招募同伴的煙霧測試（開發規範手冊 4.1 第三級）：五項屬性的季，在酒肆花銀兩招一位一般 NPC 同伴。"""
import random
import tempfile
from pathlib import Path

import pytest

from conftest import real_content
from tianxia import roster
from tianxia.core.registry import FEATURES
from tianxia.engine import Game
from tianxia.sqlite_world import open_world


def hire_game(on: bool = True, profile: str = "week7") -> Game:
    c = real_content(profile)
    c.config.attributes.v2.enabled = on
    c.config.auto_open_first_season = True
    world = open_world(Path(tempfile.mkdtemp(prefix="hire-")) / "tianxia.db")
    g = Game.new(c, "沈浪", rng=random.Random(0), world=world)
    g.client = None
    g.state.player.tutorial_step = len(c.tutorial.steps)
    g.state.player.location = next(ch.hire_at for ch in c.characters.values() if ch.hire_at)
    g.state.player.stats["silver"] = 1000
    return g


@pytest.mark.smoke
def test_hire_one_at_the_tavern():
    g = hire_game()
    c = g.content
    opts = [o for o in g.options() if o.id.startswith("hire:")]
    assert len(opts) == len(c.config.hire.types) and all(o.enabled for o in opts)
    cid = opts[0].id.partition(":")[2]
    g.choose(opts[0].id)
    assert roster.owned_by(g.world, cid) == "沈浪" and cid in g.state.player.team
    assert g.state.player.stats["silver"] == 1000 - c.config.hire.cost
    assert g.world.get_companion(cid).wugong_id == c.characters[cid].starting_wugong
    nxt = [o.id for o in g.options() if o.id.startswith("hire:")]
    assert f"hire:{cid}" not in nxt and len(nxt) == len(c.config.hire.types)  # 同一型的下一位補上來


def test_full_or_poor_greys_out():
    g = hire_game()
    g.state.player.stats["silver"] = 0
    assert all(not o.enabled for o in g.options() if o.id.startswith("hire:"))
    from tianxia.features.hire import actions

    cid = actions.free_here(g)[0]
    assert "銀兩不夠" in actions.act(g, cid)[0] and roster.owned_by(g.world, cid) is None
    g.state.player.stats["silver"] = 1000
    for other in [k for k, ch in g.content.characters.items() if ch.hire_type][: g.content.config.companions.max_owned]:
        g.world.try_recruit(other, "沈浪")
    assert all(not o.enabled for o in g.options() if o.id.startswith("hire:"))
    assert "招不了更多人" in actions.act(g, actions.free_here(g)[0])[0]


def test_quiet_in_the_old_season():
    g = hire_game(False)
    feature = next(f for f in FEATURES if f.name == "hire")
    assert feature.enabled(g) is False
    assert not any(o.id.startswith("hire:") for o in g.options())


def test_sitting_in_the_tavern_lists_the_hires_for_the_page():
    """介面重整：坐在酒肆裡時，畫面拿到此地能招的那幾位（按下去先出酒肆再招）；沒坐在酒肆裡不給。"""
    g = hire_game()
    assert "hires" not in g.feature_status()
    g.state.player.picking_tavern = True
    hires = g.feature_status()["hires"]
    assert len(hires) == len(g.content.config.hire.types)
    assert all(h["id"].startswith("hire:") and h["enabled"] for h in hires)
