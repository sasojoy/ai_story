"""計畫第八章裁決 18（PM 2026-10-20）：領地爭奪開著時，敵方的大本營與廣宗搶不下來、不推進度，所以不給攻、不畫 ⚔——
出陣那一格灰著寫「此地不在爭奪之列」（待 joy 潤），假人不往那裡出陣，軍令不把它列成攻城地點。截糧的運糧隊打那裡經過時照打
（截糧不動，裁決 11），只打運糧隊。"""
from __future__ import annotations

import pytest

from conquest_kit import conquest_game, go, join, plain_game
from tianxia import bot_policy, mapview, orders, sortie
from tianxia.state import BotProfile, Order

pytestmark = pytest.mark.slow  # 建 Game、載正式內容

# 輿圖重製第 1 批（新天下）：大本營只在外圈——官軍大將軍府、宛城，黃巾鉅鹿道壇、青州黃巾營（長社、黃巾別部營寨改成中原的中立地）
ENEMY_SPOTS = (("guan", "qingzhou_camp"), ("guan", "guangzong"), ("guan", "julu_altar"), ("huang", "dajiangjun_fu"), ("huang", "wan_city"))


def _train(game):
    return next((o for o in game.options() if o.id == "act:train"), None)


def _note(game, loc_id):
    return game._sortie_line(game.content.locations[loc_id])


@pytest.mark.parametrize(("side", "loc"), ENEMY_SPOTS)
def test_enemy_base_and_guangzong_give_no_attack(side, loc):
    game = go(join(conquest_game("season21"), side), loc)
    option = _train(game)
    assert option is not None and not option.enabled  # 修前「出陣・攻」按得下去
    assert option.label == f"{sortie.NAME}（{sortie.OUT_NOTE}）"
    assert game.sortie_mode() is None
    assert _note(game, loc) == sortie.OUT_LINE


@pytest.mark.parametrize(("side", "loc"), ENEMY_SPOTS)
def test_no_crossed_swords_and_no_map_sortie_there(side, loc):
    game = go(join(conquest_game("season21"), side), loc)
    assert loc not in mapview.armed_places(game.state, game.content)
    state = game.map_state()
    assert state["places"][loc]["sortie"] is None and state["places"][loc]["armed"] is False
    assert loc not in {g["id"] for g in state["suggest"]}


def test_crossed_swords_stay_on_blocks_you_can_take():
    game = join(conquest_game("season21"), "guan")
    armed = mapview.armed_places(game.state, game.content)
    assert {"deep_mountain", "hilltop_wilds", "runan_wilds", "zhuo_county", "changshe", "huangjin_camp"} <= armed
    assert not armed & {"qingzhou_camp", "julu_altar", "guangzong", "wan_city", "dajiangjun_fu"}


def test_bots_do_not_sortie_there():
    game = go(join(conquest_game("season21"), "guan"), "qingzhou_camp")
    profile = BotProfile(personality="普通", seed=1, faction="guan", season_number=1)
    assert bot_policy._train_value(game, profile, "qingzhou_camp") == 0
    assert not any(o.id == "act:train" and o.enabled for o in game.options())


def test_siege_places_never_list_them():
    game = conquest_game("season21")
    w, c = game.state.world, game.content
    for side, front in (("guan", "yingru"), ("guan", "jizhou"), ("guan", "nanyang"), ("huang", "yingru"), ("huang", "nanyang")):
        assert not set(orders.siege_places(c, side, front, w)) & {"qingzhou_camp", "guangzong", "julu_altar", "dajiangjun_fu",
                                                                 "wan_city"}


def test_intercept_convoy_at_an_enemy_base_is_still_fought():
    """黃巾的截糧在宛城（官軍的大本營；新天下南陽那條舊線的截糧地點）：運糧隊打那裡經過的那一週照打，只打運糧隊、只算截糧，不推進度。"""
    game = go(join(conquest_game("season21"), "huang"), "wan_city")
    s, c = game.state, game.content
    s.world.orders.append(Order(id="t:huang:intercept", template="intercept", faction="huang", week=orders.period_of(s, c),
                                location="wan_city", quota=4, text="（測試）"))
    convoy = c.orders.convoy_squads["guan"]
    option = _train(game)
    assert option is not None and option.enabled and "攻" in option.label
    assert game._sortie_foes(c.locations["wan_city"]) == [convoy]
    assert "wan_city" in mapview.armed_places(s, c)
    note = _note(game, "wan_city")
    assert note.startswith("對面的運糧隊正打這裡經過：") and "不在爭奪之列" in note and "推這一塊的進度" not in note


def test_own_base_still_holds():
    game = go(join(conquest_game("season21"), "guan"), "wan_city")
    option = _train(game)
    assert option is not None and option.enabled and "守" in option.label


def test_switch_off_enemy_base_is_unchanged():
    """關著：照舊攻得了、畫 ⚔（a73c111e 上量的）。"""
    game = go(join(plain_game("season21"), "guan"), "julu_altar")  # 新天下黃巾的大本營（v1 是黃巾別部營寨）
    option = _train(game)
    assert option is not None and option.enabled and option.label.startswith("出陣・攻（")
    assert "julu_altar" in mapview.armed_places(game.state, game.content)
