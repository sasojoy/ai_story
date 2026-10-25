"""素材與經濟（docs/superpowers/specs/2026-10-15-素材與經濟-design.md）第四、五節：鐵匠鋪的升階與收購（規則與選單、店面的資料）。
正式內容、週末設定（Config.economy 預設開）。潁川郡是城鎮、有鐵匠鋪、不在任何人的地盤上（地盤福利 ×1）。"""
from __future__ import annotations

import random
from unittest import mock

from conftest import no_week_unlock, real_content
from tianxia import economy, shopview
from tianxia import engine as engine_mod
from tianxia.engine import Game
from tianxia.equipment import NOT_NOW
from tianxia.sqlite_world import open_world

TW_MIDNIGHT = 16 * 3600  # UTC 16:00＝台灣 00:00（1970-01-02）


def _game(bag=None, silver=500, at="yingchuan", **econ):
    c = no_week_unlock(real_content("week7"))
    c.config.auto_open_first_season = True
    c.config.four_tiers.enabled = False  # 素材四階之前的規則（三階不收、二換三一天一個）；四階的規則在 test_four_tiers
    for key, value in econ.items():
        setattr(c.config.economy, key, value)
    game = Game.new(c, "沈浪", rng=random.Random(0), world=open_world())
    game.client = None
    p = game.state.player
    p.location, p.faction = at, "guan"
    p.tutorial_step = len(c.tutorial.steps)
    p.stats["silver"] = silver
    p.materials = dict(bag or {})
    game.now = TW_MIDNIGHT + 3600  # 台灣 01:00
    return game


def _ids(game):
    return {o.id: o for o in game.options()}


def _open(game):
    game.choose("act:smith")
    game.choose("smith:page:material")


def test_the_weapon_page_has_a_door_to_the_materials_page():
    game = _game(bag={"rou_1": 4})
    game.choose("act:smith")
    assert "smith:page:material" in _ids(game)
    game.choose("smith:page:material")
    ids = _ids(game)
    assert "smith:sell:rou_1" in ids and "smith:upgrade:柔:2" in ids and "smith:back" in ids
    assert "smith:page:weapon" in ids  # 回兵器頁
    assert not any(i.startswith("smith:buy:") for i in ids)


def test_selling_one_from_the_menu():
    game = _game(bag={"rou_1": 4, "rou_3": 1})
    _open(game)
    ids = _ids(game)
    assert ids["smith:sell:rou_1"].enabled and "2 兩" in ids["smith:sell:rou_1"].label and "手上 4" in ids["smith:sell:rou_1"].label
    assert "smith:sell:rou_3" not in ids  # 三階不收，不列
    with mock.patch.object(Game, "_smith_clue", side_effect=AssertionError("收購沒花錢，不擲鐵匠順口")):
        game.choose("smith:sell:rou_1")
    p = game.state.player
    assert p.materials["rou_1"] == 3 and p.stats["silver"] == 502
    assert game.state.journal[0].title == "鐵匠鋪" and "銀兩 +2" in game.state.journal[0].changes


def test_upgrading_from_the_menu_spends_three_and_five_silver():
    game = _game(bag={"rou_1": 3})
    _open(game)
    option = _ids(game)["smith:upgrade:柔:2"]
    assert option.enabled and "柳絲綿】×3" in option.label and "5 兩" in option.label
    assert "五成出流雲絮，其餘隨機" in option.label  # 升階隨機：鈕上寫得出機率
    rng_before = game.rng.getstate()
    game.choose("smith:upgrade:柔:2")
    p = game.state.player
    tier_two = {mid: n for mid, n in p.materials.items() if game.content.materials[mid].tier == 2}
    assert "rou_1" not in p.materials and sum(tier_two.values()) == 1 and p.stats["silver"] == 495
    assert game.rng.getstate() == rng_before  # 升階擲自己的亂數，不碰 Game.rng
    made = game.content.materials[next(iter(tier_two))].name
    assert any(f"【{made}】" in line for line in game.state.journal[0].lines)  # 結果句寫實際出了什麼


def test_the_menu_says_what_comes_out_when_it_is_certain():
    game = _game(bag={"rou_1": 3}, upgrade_same_share=1.0)
    _open(game)
    assert "（5 兩・出流雲絮）" in _ids(game)["smith:upgrade:柔:2"].label
    game.choose("smith:upgrade:柔:2")
    assert game.state.player.materials == {"rou_2": 1}


def test_tier_three_once_a_day_until_taiwan_midnight():
    game = _game(bag={"man_2": 20}, upgrade_same_share=1.0)
    _open(game)
    assert "今天還能換 1 個" in _ids(game)["smith:upgrade:慢:3"].label
    assert game.smith_upgrade("慢", 3)
    assert game.state.player.materials == {"man_2": 10, "man_3": 1}
    option = _ids(game)["smith:upgrade:慢:3"]
    assert not option.enabled and economy.UPGRADE_DAY_FULL in option.label
    assert game.smith_upgrade("慢", 3) == [economy.UPGRADE_DAY_FULL] and game.state.player.materials["man_2"] == 10
    game.now = TW_MIDNIGHT + 24 * 3600  # 隔天台灣 00:00
    game.smith_upgrade("慢", 3)
    assert game.state.player.materials == {"man_3": 2}


def test_the_shop_actions_need_the_smith_open():
    game = _game(bag={"rou_1": 4, "man_2": 10})
    assert game.smith_sell("rou_1", 2) == [NOT_NOW] and game.smith_upgrade("慢", 3) == [NOT_NOW]
    assert game.state.player.materials == {"rou_1": 4, "man_2": 10} and game.state.player.stats["silver"] == 500
    game.choose("act:smith")
    assert game.smith_sell("rou_1", 2)
    assert game.state.player.materials["rou_1"] == 2 and game.state.player.stats["silver"] == 504


def test_switched_off_there_is_no_materials_page():
    game = _game(bag={"rou_1": 4}, sell=False, upgrade=False)
    game.choose("act:smith")
    assert "smith:page:material" not in _ids(game)
    assert game.smith_sell("rou_1", 1) == [NOT_NOW] and game.state.player.materials == {"rou_1": 4}
    assert game.shop_view().get("trade") is None


def test_only_selling_on_shows_no_upgrades():
    game = _game(bag={"rou_1": 4}, upgrade=False)
    _open(game)
    ids = _ids(game)
    assert "smith:sell:rou_1" in ids and not any(i.startswith("smith:upgrade:") for i in ids)


def test_the_shop_view_lists_what_can_be_sold_and_upgraded():
    game = _game(bag={"rou_1": 4, "rou_2": 1, "rou_3": 1})
    game.choose("act:smith")
    trade = game.shop_view()["trade"]
    sell = {row["id"]: row for row in trade["sell"]}
    assert set(sell) == {"rou_1", "rou_2"} and sell["rou_1"]["price"] == 2 and sell["rou_2"]["have"] == 1
    up = {(row["attribute"], row["tier"]): row for row in trade["upgrade"]}
    assert up[("柔", 2)]["problem"] is None and up[("柔", 2)]["need"] == 3 and up[("柔", 2)]["cost"] == 5
    assert up[("柔", 2)]["odds"] == "五成出流雲絮，其餘隨機" and up[("柔", 2)]["same_share"] == 0.5
    assert up[("柔", 3)]["problem"] is not None and up[("柔", 3)]["left"] == 1
    assert ("剛", 2) in up  # 四個屬性都列（沒料的灰掉、寫原因）


def test_the_hint_follows_the_switches():
    """FB-272：素材頁還沒做事時那一句照開關寫——升階關著（只剩收購）不提熬；開著時不說「只能熬出來」。"""
    def hint(**econ):
        game = _game(bag={"rou_1": 4}, **econ)
        game.choose("act:smith")
        return game.shop_view()["trade"]["hint"]

    assert hint(upgrade=False) == shopview.SELL_ONLY_HINT and "熬" not in shopview.SELL_ONLY_HINT
    assert hint() == shopview.UPGRADE_HINT.format(share="五成") and "得自己熬" in hint()
    assert hint(upgrade_same_share=1.0) == shopview.TRADE_HINT
    for text in (shopview.SELL_ONLY_HINT, shopview.UPGRADE_HINT, shopview.TRADE_HINT):
        assert "只能" not in text


def test_leaving_the_smith_resets_the_page():
    game = _game(bag={"rou_1": 4})
    _open(game)
    game.choose("smith:back")
    game.choose("act:smith")
    assert any(i.startswith("smith:buy:") for i in _ids(game))  # 進門照舊停在兵器頁
    assert engine_mod  # noqa: B018
