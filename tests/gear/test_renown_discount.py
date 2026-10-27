"""店家折扣（名聲設計 4.1）：名望那一半跟地盤福利疊乘，套療傷、打造工錢、升階工錢、買馬；價錢後面寫原因。"""
from conftest import real_content

from tianxia import economy, mounts, skillview, smithing, team, territory
from tianxia.state import new_game_state


def _s(c, fame):
    s = new_game_state(c, "甲")
    s.player.stats["fame"] = fame
    return s


def test_prices_take_the_fame_discount():
    c = real_content("week7")
    s = _s(c, 25)  # 名動一方：九四折；散人、地盤原價
    assert smithing.price(c, 2, "weapon", s) == int(c.config.weapons.forge_silver["2"] * 0.94 + 0.5)
    assert mounts.price(s, c) == int(c.config.mounts.shop_price * 0.94 + 0.5)
    tier = min(c.config.economy.upgrade_silver)
    assert economy.upgrade_cost(s, c, tier) == int(c.config.economy.upgrade_silver[tier] * 0.94 + 0.5)
    assert territory.price_note(s, c) == "（名動一方・九四折）"  # 設計 4.1 的寫法（FB-294：跟醫館那一半同一種）
    s.player.member.injury = 20
    assert team.heal_cost(c, s.player.member, s) == 10  # 20 點 ÷ 2 × 0.94 ＝ 9.4 → 10（無條件進位）
    s.player.member.injury = 40
    assert team.heal_cost(c, s.player.member, s) == 19  # 20 × 0.94 ＝ 18.8 → 19


def test_the_heal_button_names_the_discount():
    c = real_content("week7")
    s = _s(c, 25)
    s.player.member.injury = 40
    s.player.stats["silver"] = 100
    assert skillview.heal_note(s, c).endswith("（名動一方・九四折）")


def test_no_discount_no_note():
    c = real_content("week7")
    s = _s(c, 0)
    assert territory.price_note(s, c) == "" and territory.price_here(s, c) == 1.0
    c.config.renown.discount = False
    assert territory.price_here(_s(c, 90), c) == 1.0 and territory.price_note(_s(c, 90), c) == ""
