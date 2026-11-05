"""煉製與自創包的煙霧測試（開發規範手冊 4.1 第三級：一包一條，真實內容，走一次最常見的路）：正式內容 week7，煉製頁合一爐
（風＋火兩個意境，模型沒回就走退路字表）、自創一門武學（執器、擺式、立意、立名），再看一遍預覽路由
（/api/forge_line 經包的 routes 掛在殼上）與籌備中被擋。"""
import random

import pytest
from conftest import real_content

from tianxia import create
from tianxia.core.registry import FEATURES
from tianxia.engine import Game
from tianxia.sqlite_world import open_world


def _game(name="煉製客"):
    c = real_content("week7")
    c.config.auto_open_first_season = True
    game = Game.new(c, name, rng=random.Random(0), world=open_world())
    game.skip_tutorial()
    game.sync(1000.0)
    for _ in range(6):  # 開局三選一之類待選的事件：選掉
        first = next((o.id for o in game.options() if o.id.startswith("choice:") and o.enabled), None)
        if first is None:
            break
        game.choose(first)
    return game


@pytest.mark.smoke
def test_a_wanderer_merges_two_insights_and_creates_an_art():
    feature = next(f for f in FEATURES if f.name == "craft")
    game = _game()
    c = game.content
    assert feature.enabled(game) is True and feature.prefix is None
    assert feature.player_fields == ("creating", "created_count")
    p = game.state.player
    p.stats["xinde"] = 5000
    p.stamina = 100
    base = [i for i in c.insights][:2]
    p.insights = list(base)
    assert game.forge_line(base) and game.forge_preview(base) is not None
    out = game.forge(None, base)
    assert game.forged is True and game.forged_thing[0] == "ins" and out
    assert game.state.journal[0].title == "煉製"
    # 自創五步：執器、擺式、立意（付心得）、立名
    forms = create.forms_of(c, "武學")
    assert game.create_begin("武學", forms[0].key)
    game.create_pose(create.preset(c, "起手"))
    before = p.stats["xinde"]
    game.create_intent("風過林梢，影不留痕")
    assert p.creating is not None and p.creating.step == "name" and p.stats["xinde"] < before
    msgs = game.create_name("霜葉掌")
    assert game.forged is True and game.forged_thing == ("art", "霜葉掌") and "霜葉掌" in msgs[0]
    assert p.creating is None and p.created_count == 1
    assert game.create_view()["draft"] is None
