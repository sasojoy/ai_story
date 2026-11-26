"""修練包的煙霧測試（開發規範手冊 4.1 第三級：一包一條，真實內容，走一次最常見的路）：正式內容 week7，到潁水河畔拜師學一門
（learn:，修練包的 choose 掛鉤接走、標題先算）、練成一成、把一個意境裝進身上那一門的槽。"""
import random

import pytest
from conftest import real_content

from tianxia import team
from tianxia.core.registry import FEATURES
from tianxia.engine import Game
from tianxia.sqlite_world import open_world


@pytest.mark.smoke
def test_learn_practice_and_slot_an_insight():
    c = real_content("week7")
    c.config.auto_open_first_season = True
    game = Game.new(c, "修練客", rng=random.Random(0), world=open_world())
    game.skip_tutorial()
    game.sync(1000.0)
    for _ in range(6):  # 開局三選一之類待選的事件：選掉
        first = next((o.id for o in game.options() if o.id.startswith("choice:") and o.enabled), None)
        if first is None:
            break
        game.choose(first)
    feature = next(f for f in FEATURES if f.name == "cultivation")
    assert feature.enabled(game) is True
    p = game.state.player
    p.location, p.journey = "yu_river", None  # 村鎮與營地的下品 2026-11-12 起不教了：學一門還在教的上品
    p.visited.add("yu_river")
    p.stats["silver"] = 100
    p.stats["fame"] = 99

    lesson = next(o for o in game.options() if o.id.startswith("learn:"))
    assert lesson.enabled and lesson.id == "learn:yushui_changxi"
    game.choose(lesson.id)
    assert "yushui_changxi" in p.arts and p.stats["silver"] == 40
    assert game.state.journal[0].title == "學藝・淯水長息"
    assert not any(o.id == lesson.id for o in game.options())  # 學過的不在選單上

    art = p.member.wugong_id
    p.stats["xinde"] = 100
    before = p.member.wugong_level
    if team.xinde_practice_off(game.state, game.content):  # 打了才升的季（Joy 2026-11-13）：心得練不了，成數不動
        game.practice("武學")
        assert p.member.wugong_level == before
        game.state.world.fight_practice = False  # 下面照舊規則的季驗「練」這一下
    game.practice("武學")
    assert p.member.wugong_level == before + 1

    p.insights.append("feng")
    game.slot_insight(art, "feng")
    assert "feng" in p.art_slots[art]
