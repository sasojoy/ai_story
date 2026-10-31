"""地盤易手（docs/superpowers/specs/2026-10-14-出陣探索與地盤-design.md 第四節）。正式內容、週末設定（第一季規則開著）。
開季的戰線：潁川汝南 40、南陽 35、冀州 55、割據 10。"""
from __future__ import annotations

import random

import pytest

from conftest import classic_rules, real_content, third_party_gentry
from tianxia import bounties, orders, rules, territory, timetable
from tianxia.content import ContentError, validate
from tianxia.engine import Game
from tianxia.sqlite_world import open_world
from tianxia.state import TerritoryState

OPENING = {
    "guan_camp": "guan", "runan_wilds": "huang", "nanyang_wilds": "guan", "yu_river": "guan",
    "baima_ford": "guan", "xiaquyang": "guan", "juma_river": "huang", "yanshan_foot": "huang",
    "changshe": "guan", "luzhi_camp": "guan", "huangjin_camp": "huang", "julu_altar": "huang",
    "nanyang_huangjin_camp": "huang", "guangzong": "huang",
}


def _game(profile="week7"):
    c = third_party_gentry(real_content(profile))  # 這一檔測割據佔地：豪強是第三方的規則（豪強分屬兩軍見 test_gentry_allied.py）
    c.config.auto_open_first_season = True
    game = Game.new(c, "沈浪", rng=random.Random(0), world=open_world())
    game.client = None
    territory.update(game.state.world, c)  # 開季那一下：第一次算，不發天下大事
    return game


def _owner(game, loc_id):
    return territory.controller(game.state.world, game.content, loc_id)


@pytest.mark.smoke
def test_opening_a_prepared_season_starts_the_map_over(tmp_path):
    c = real_content("week7")
    store = open_world(tmp_path / "w.db")
    store.seed_first_season(c)
    season = store.get_season()
    season.territory = TerritoryState(control={"runan_wilds": "haoqiang"})
    store.save_season(season)
    assert store.open_season(c, now=0.0)
    assert store.get_season().territory is None


def test_the_territory_content_is_checked():
    c = real_content()
    c.scenario.territory.lines["yingru"].append("changshe")
    with pytest.raises(ContentError, match="大本營"):
        validate(c)
