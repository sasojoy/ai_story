"""俠的醫館折扣與寇的黑市（名聲設計 5.2）。"""
from conftest import real_content, renown_unscaled

from tianxia import economy, renown, skillview, team
from tianxia.state import new_game_state


def test_clinic_discount_for_heroes_from_the_second_tier():
    c = renown_unscaled(real_content("week7"))
    s = new_game_state(c, "甲")
    s.player.member.injury = 20
    s.player.stats["good"] = 15
    assert renown.clinic_factor(s, c) == 0.85
    assert team.heal_cost(c, s.player.member, s) == 9  # 10 兩 × 0.85 → 8.5 → 9
    s.player.stats["good"] = 14
    assert renown.clinic_factor(s, c) == 1.0
    assert team.heal_cost(c, s.player.member, s) == 10
    s.player.stats.update({"good": 15, "evil": 16})  # 走寇：不打折
    assert renown.clinic_factor(s, c) == 1.0


def test_the_heal_button_says_why():
    c = renown_unscaled(real_content("week7"))
    s = new_game_state(c, "甲")
    s.player.member.injury = 20
    s.player.stats.update({"good": 15, "silver": 100})
    assert "（一方豪俠・八五折）" in skillview.heal_note(s, c)
    c.config.renown.clinic = False
    assert "八五折" not in skillview.heal_note(s, c) and team.heal_cost(c, s.player.member, s) == 10


def test_both_reasons_share_one_bracket():
    """FB-294：名望的店家折扣與俠的醫館折扣都有時，原因寫在同一個括號、同一種寫法（設計 4.1 的「（名動一方・九四折）」），
    不再是「16 兩（威震州郡九折）（州郡大俠・八五折）」。"""
    c = renown_unscaled(real_content("week7"))
    s = new_game_state(c, "甲")
    s.player.member.injury = 40
    s.player.stats.update({"fame": 50, "good": 30, "silver": 100})
    note = skillview.heal_note(s, c)
    assert note == "內傷 40・16 兩（威震州郡・九折，州郡大俠・八五折）"


def test_black_market_for_rogues():
    c = renown_unscaled(real_content("week7"))
    s = new_game_state(c, "甲")
    assert economy.sell_price_for(s, c, 1) == economy.sell_price(c, 1) == 2
    s.player.stats["evil"] = 5
    assert (economy.sell_price_for(s, c, 1), economy.sell_price_for(s, c, 2), economy.sell_price_for(s, c, 3)) == (3, 8, 24)  # 素材四階：三階也收（正式季整合 6.6）
    c.config.renown.black_market = False
    assert economy.sell_price_for(s, c, 1) == 2


def test_the_store_says_black_market_and_the_smith_says_so_too():
    import random

    from tianxia import shopview
    from tianxia.engine import Game

    c = renown_unscaled(real_content("week7"))
    c.config.auto_open_first_season = True
    g = Game.new(c, "甲", rng=random.Random(0))
    g.client = None
    s = g.state
    s.player.location = "yingchuan"
    s.player.materials["gang_1"] = 2
    s.player.stats["evil"] = 5
    rows = shopview.trade_view(s, c, 0)
    row = next(r for r in rows["sell"] if r["id"] == "gang_1")
    assert (row["price"], row["dark"]) == (3, "（黑市價）") and "照黑市價收" in rows["sell_cap"]
    g.choose("act:smith")
    assert g.smith_sell("gang_1", 1)[-1] == "銀兩 +3"
    assert s.player.shop_line == "black_market"
    s.player.stats["evil"] = 0
    assert shopview.trade_view(s, c, 0)["sell"][0]["dark"] == ""


def test_the_virtue_perks_name_the_clinic_and_the_market():
    c = renown_unscaled(real_content("week7"))
    assert "醫館療傷八五折" in renown.virtue_perks(c, "俠", 2)
    assert "鐵匠鋪收購一階 3 兩、二階 8 兩、三階 24 兩" in renown.virtue_perks(c, "寇", 1)
    c.config.four_tiers.enabled = False  # 素材四階關著：照舊不收三階
    assert "鐵匠鋪收購一階 3 兩、二階 8 兩" in renown.virtue_perks(c, "寇", 1)
