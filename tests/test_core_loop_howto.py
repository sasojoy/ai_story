"""玩法說明與新手引導的字（出陣探索與地盤設計第七節）。
這一份先放出陣、推力、地盤那幾塊（PM 2026-10-14：探索三選一與地盤福利另外平行做，合進來之後再補那兩段）。"""
from __future__ import annotations

from conftest import classic_rules, real_content
from tianxia import howto


def _page(content):
    from tianxia.world_state import fresh_season

    return howto.page(content, fresh_season(content), recruitable=False)


def test_the_howto_page_explains_the_new_loop():
    c = real_content("weekend")
    page = _page(c)
    assert "**出陣**" in page and "每天 5 次" in page and "**遊歷**" not in page
    assert "找素材" in page and "靜心感悟" in page and "照地點三選一：悟意境" not in page
    assert "- 靜心感悟時「有所感」" in page
    assert "#### 地盤" in page and "換了人" in page
    assert "便宜一成" in page and "貴兩成" in page and "底色" in page  # 地盤福利與輿圖上色（計畫 Task 5）


def test_the_territory_prices_follow_the_config():
    c = real_content("weekend")
    c.config.territory.own_price, c.config.territory.enemy_price = 0.85, 1.5
    line = " ".join(howto.territory_lines(c))
    assert "便宜15%" in line and "貴五成" in line


def test_the_howto_page_is_unchanged_with_the_switches_off():
    c = classic_rules(real_content("weekend"))
    page = _page(c)
    assert "**遊歷**" in page and "**出陣**" not in page and "#### 地盤" not in page
    assert "照地點三選一：悟意境" in page and "找素材" not in page and "- 探索落在悟意境時「有所感」" in page


def test_the_fronts_and_joining_explain_the_sortie():
    from tianxia.state import GameState, PlayerState
    from tianxia.world_state import fresh_season

    c = real_content("weekend")
    season = fresh_season(c)
    state = GameState(player=PlayerState(name="甲", location=c.scenario.start_location, stats={}, stamina=0), world=season)
    fronts = " ".join(howto.fronts_help(state, c))
    assert howto.SORTIE_PLACES in fronts and howto.SORTIE_RANGER in fronts and howto.SORTIE_GEJU in fronts
    assert howto.SORTIE_JOIN in " ".join(howto.join_lines(c, season))
    assert howto.SORTIE_PLACES in " ".join(howto.quest_help(c))
    old = classic_rules(real_content("weekend"))
    assert howto.SOME_PLACES in " ".join(howto.fronts_help(state, old))


def test_the_first_order_hint_points_at_the_sortie():
    c = real_content()
    recruiters = c.tutorial.enlist.recruiters
    assert "出陣" in recruiters["guan"].order_hint and "出陣" in recruiters["huang"].order_hint


def test_light_feet_names_the_sortie():
    c = real_content()
    [light] = [t for t in c.traits.special if t.hook == "train_stamina"]
    assert "出陣" in light.desc
