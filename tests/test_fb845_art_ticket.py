"""FB-845：這一季用不到的列傳插畫票不賣，票綁買的那一季。
- 沒投靠一方的人（散人）：列傳配不了插畫，商城那一列灰掉寫原因、買也買不了；休季時已經得第一階的人：插畫白送，同樣灰掉寫原因
  （季中看不出會是第幾階，照舊賣）。已經買了一張的人說的是限購。
- 列傳的三種票（插畫、紀念印、親筆評曰）綁買的那一季：之後的季不再冒出用票的鈕，用票用的是這一季買的那一張。"""
from __future__ import annotations

import pytest
from conftest import next_season
from zhuan_fix_kit import close_season, make_game, option_ids, row, to_week

from tianxia import zhuan_end
from tianxia.characters import CharacterStore, name_key
from tianxia.wallet import Purchase, Wallet

pytestmark = pytest.mark.slow


def test_a_wanderer_cannot_buy_the_art_ticket_in_season_or_in_the_rest():
    game = make_game(side=None)
    to_week(game, 3)
    art = row(game, "zhuan_art")
    assert art is not None and art["can"] is False and art["why"] == zhuan_end.ART_NO_SIDE and art["max"] == 0
    wallet, owner = Wallet(game.world.db), name_key(game.state.player.name)
    before = wallet.balance(owner)
    assert game.mall_buy("zhuan_art", "w1") == [zhuan_end.ART_NO_SIDE]
    assert wallet.balance(owner) == before and not [b for b in wallet.purchases(owner) if b.item == "zhuan_art"]
    close_season(game)
    assert row(game, "zhuan_art")["why"] == zhuan_end.ART_NO_SIDE
    assert game.mall_buy("zhuan_art", "w2") == [zhuan_end.ART_NO_SIDE]
    assert row(game, "zhuan_seal")["can"] is True  # 紀念印、親筆評曰散人也用得上，照舊賣


def test_a_wanderer_who_joins_a_side_can_buy_it():
    game = make_game(side=None)
    to_week(game, 3)
    assert row(game, "zhuan_art")["can"] is False
    game.state.player.faction = "guan"
    assert row(game, "zhuan_art")["can"] is True and row(game, "zhuan_art")["why"] is None
    assert game.mall_buy("zhuan_art", "j1")[0].startswith("買下")


def test_the_first_tier_cannot_buy_the_art_ticket_once_the_season_is_over():
    game = make_game()
    game.state.player.contrib = 120  # 這一局官軍只有他：過了門檻就是第一階
    CharacterStore(game.world.db).save(game.state)
    to_week(game, 3)
    assert row(game, "zhuan_art")["can"] is True  # 季中看不出會是第幾階：照舊賣
    close_season(game)
    assert game.biography_entry()["tier"]["tier"] == 1
    art = row(game, "zhuan_art")
    assert art["can"] is False and art["why"] == zhuan_end.ART_FREE and art["max"] == 0
    wallet, owner = Wallet(game.world.db), name_key(game.state.player.name)
    assert game.mall_buy("zhuan_art", "t1") == [zhuan_end.ART_FREE]
    assert not [b for b in wallet.purchases(owner) if b.item == "zhuan_art"]


def test_a_lower_tier_keeps_buying_the_art_ticket_in_the_rest():
    game = make_game()
    to_week(game, 3)
    close_season(game)
    assert game.biography_entry()["tier"] is None
    assert row(game, "zhuan_art")["can"] is True
    assert game.mall_buy("zhuan_art", "l1")[0].startswith("買下")
    assert zhuan_end.PICK_ART in option_ids(game)


def test_the_limit_is_told_before_the_unfit_reason():
    """季中買了一張、休季才知道是第一階：再按說的是限購，不是「第一階白送」。"""
    game = make_game()
    game.state.player.contrib = 120
    CharacterStore(game.world.db).save(game.state)
    to_week(game, 3)
    assert game.mall_buy("zhuan_art", "b1")[0].startswith("買下")
    close_season(game)
    assert "這一季已經買了" in row(game, "zhuan_art")["why"]


def test_the_other_shelf_rows_are_not_blocked():
    game = make_game(side=None)
    to_week(game, 3)
    others = [r for r in game.mall_view()["items"] if r["id"] != "zhuan_art"]
    assert others and all(r["can"] and r["why"] is None for r in others)


def test_a_ticket_belongs_to_the_season_it_was_bought_in():
    game = make_game()
    game.state.player.affinities.update({"luzhi": 55})
    CharacterStore(game.world.db).save(game.state)
    to_week(game, 3)
    assert game.mall_buy("zhuan_art", "a1")[0].startswith("買下")
    close_season(game)
    for item, ref in (("zhuan_seal", "s1"), ("zhuan_quote", "q1")):
        assert game.mall_buy(item, ref)[0].startswith("買下")
    assert {zhuan_end.PICK_ART, zhuan_end.SEAL, "zhuan:quote:luzhi"} <= option_ids(game)  # 這一季的票這一季用得上
    next_season(game.content, game.world, game)  # 第 2 季開了：第 1 季沒用掉的三張不再算
    game.state.player.affinities.update({"luzhi": 55})
    CharacterStore(game.world.db).save(game.state)
    close_season(game)
    assert game.state.player.season_number == 2 and game.state.world.ended
    assert not {zhuan_end.PICK_ART, zhuan_end.SEAL, "zhuan:quote:luzhi"} & option_ids(game)
    wallet, owner = Wallet(game.world.db), name_key(game.state.player.name)
    assert game.mall_buy("zhuan_seal", "s2")[0].startswith("買下")  # 第 2 季的限購另算
    assert zhuan_end.SEAL in option_ids(game)
    game.choose(zhuan_end.SEAL)
    used = [(b.item, b.season, b.data.get("season")) for b in wallet.purchases(owner) if b.data.get("used")]
    assert used == [("zhuan_seal", 2, 2)]  # 用掉的是第 2 季買的那一張，第 1 季的還躺著（沒作廢也用不到）
    assert sum(1 for b in wallet.purchases(owner) if b.item == "zhuan_seal" and not b.data.get("used")) == 1


def test_the_button_spends_the_ticket_of_this_season_not_an_older_one():
    """手上同時有舊季的票和這一季的票：用掉的是這一季買的那一張（舊的留著）。"""
    game = make_game()
    game.state.player.affinities.update({"luzhi": 55})
    CharacterStore(game.world.db).save(game.state)
    close_season(game)
    wallet, owner = Wallet(game.world.db), name_key(game.state.player.name)
    wallet.add_purchase(owner, "old-art", "zhuan_art", 300, time=game.now, day=0, season=0, data={"zhuan_art": 1})
    game.mall_buy("zhuan_art", "new-art")
    assert zhuan_end.PICK_ART in option_ids(game)
    game.choose(zhuan_end.PICK_ART)
    used = {b.ref.split(":")[-1]: b.data.get("used") is not None for b in wallet.purchases(owner) if b.item == "zhuan_art"}
    assert used == {"old-art": False, "new-art": True}


def test_only_this_seasons_tickets_are_counted_when_the_buttons_are_drawn():
    """純規則：zhuan_end.unused 帶了季就只數那一季買的。"""
    rows = [
        Purchase(id=3, owner="x", ref="r3", item="zhuan_seal", price=1, time=0, day=0, season=2, data={"zhuan_seal": 1}, refunded=None),
        Purchase(id=2, owner="x", ref="r2", item="zhuan_seal", price=1, time=0, day=0, season=1, data={"zhuan_seal": 1}, refunded=None),
    ]
    assert [b.id for b in zhuan_end.unused(rows, "zhuan_seal", 2)] == [3]
    assert [b.id for b in zhuan_end.unused(rows, "zhuan_seal", 1)] == [2]


def test_art_problem_is_a_pure_rule():
    game = make_game(side=None)
    s, c = game.state, game.content
    assert zhuan_end.art_problem(s, c, s.world) == zhuan_end.ART_NO_SIDE
    s.player.faction = "guan"
    assert zhuan_end.art_problem(s, c, s.world) is None
