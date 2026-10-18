"""素材四階（docs/superpowers/specs/2026-10-17-正式季整合-design.md 第四、五章；正式季整合第 2 批）。

測試內容保持三階、開關關著（10.1）：四階的測試用正式內容（real_content），或在測試裡自己補料。"""
from __future__ import annotations

import random
from unittest import mock

from conftest import real_content

from tianxia import economy, equipment, forge_secrets, four_tiers, howto, materials, renown, shopview, skillview


def test_real_content_has_four_tier4_materials_at_the_end():
    c = real_content()
    last = list(c.materials.values())[-4:]
    assert [m.id for m in last] == ["gang_4", "rou_4", "kuai_4", "man_4"]
    assert [m.name for m in last] == ["熔星髓", "天池露", "奔雷角", "歸墟壤"]
    assert [m.attribute for m in last] == ["剛", "柔", "快", "慢"]
    assert all(m.tier == 4 for m in last)


def test_tier_words_cover_four():
    assert materials.TIER_NAMES[4] == "神品"
    assert equipment.TIER_WORDS[4] == "四階"
    assert shopview.TIER_NAMES[4] == "四階"
    assert forge_secrets.TIER_WORDS[4] == "四"


def test_fixture_stays_three_tiers_and_switch_off(content):
    assert max(m.tier for m in content.materials.values()) == 3
    assert not four_tiers.on(content)
    assert four_tiers.on(real_content())


def test_bag_line_says_four_tiers(world):
    from tianxia.engine import Game

    c = real_content()
    game = Game.new(c, "四階", world=world)
    game.state.player.materials = {"gang_4": 1}
    text = skillview.bag_text(game.state, c)
    assert "凡品、靈品、天品、神品四階" in text


# ── Task 2：鐵匠鋪的素材買賣 ──────────────────────────────

DAY = 3


def _econ_game(bag=None, silver=1000, on=True):
    from tianxia.engine import Game
    from tianxia.sqlite_world import open_world

    c = real_content("weekend")
    c.config.four_tiers.enabled = on
    game = Game.new(c, "沈浪", rng=random.Random(0), world=open_world())
    game.client = None
    p = game.state.player
    p.location = "yingchuan"
    p.stats["silver"] = silver
    p.materials = dict(bag or {})
    return game


def test_tier3_sells_for_18_and_black_market_24():
    game = _econ_game(bag={"gang_3": 2, "gang_4": 1}, silver=0)
    s, c = game.state, game.content
    assert economy.sell(s, c, "gang_3", 1)[-1] == "銀兩 +18"
    with mock.patch.object(renown, "meets", return_value=True):
        assert economy.sell_price_for(s, c, 3) == 24
    assert economy.sell(s, c, "gang_4", 1) == [economy.SELL_TIER4]
    assert s.player.materials["gang_4"] == 1 and s.player.stats["silver"] == 18


def test_two_to_three_has_no_daily_cap():
    game = _econ_game(bag={"gang_2": 20})
    s, c = game.state, game.content
    assert economy.upgrade_left(s, c, 3, DAY) is None
    economy.upgrade(s, c, "剛", 3, DAY)
    assert economy.upgrade_problem(s, c, "剛", 3, DAY) is None
    economy.upgrade(s, c, "剛", 3, DAY)
    assert sum(n for mid, n in s.player.materials.items() if c.materials[mid].tier == 3) == 2


def test_three_to_four_needs_five_same_and_150():
    game = _econ_game(bag={"gang_3": 4}, silver=150)
    s, c = game.state, game.content
    assert ("剛", 4) in economy.upgradable(c)
    assert economy.upgrade_problem(s, c, "剛", 4, DAY) == economy.UPGRADE_SHORT.format(name="隕鐵膽", need=5, have=4)
    s.player.materials["gang_3"] = 5
    assert economy.upgrade_outcomes(c, "剛", 4) == [(c.materials["gang_4"], 1.0)]
    assert economy.upgrade_cost(s, c, 4) == 150
    economy.upgrade(s, c, "剛", 4, DAY)
    assert s.player.materials.get("gang_4") == 1 and "gang_3" not in s.player.materials
    assert s.player.stats["silver"] == 0 and s.player.tier4_upgrades == 1


def test_three_to_four_two_per_season():
    game = _econ_game(bag={"kuai_3": 15})
    s, c = game.state, game.content
    assert economy.upgrade_left(s, c, 4, DAY) == 2
    economy.upgrade(s, c, "快", 4, DAY)
    assert economy.upgrade_left(s, c, 4, DAY) == 1
    economy.upgrade(s, c, "快", 4, DAY + 1)
    assert economy.upgrade_left(s, c, 4, DAY + 2) == 0
    before = (dict(s.player.materials), s.player.stats["silver"])
    assert economy.upgrade(s, c, "快", 4, DAY + 2) == [economy.UPGRADE_SEASON_FULL]
    assert (dict(s.player.materials), s.player.stats["silver"]) == before


def test_tier4_cannot_be_donated():
    game = _econ_game(bag={"man_4": 1})
    s, c = game.state, game.content
    assert economy.donate_points(c, "man_4") == 0
    assert economy.donate_problem(s, c, "man_4", DAY) == economy.DONATE_TIER4


def test_switch_off_restores_the_old_economy():
    game = _econ_game(bag={"gang_3": 6, "gang_2": 30}, on=False)
    s, c = game.state, game.content
    assert economy.sell(s, c, "gang_3", 1) == [economy.SELL_TIER3]
    assert ("剛", 4) not in economy.upgradable(c)
    assert economy.upgrade_left(s, c, 3, DAY) == 1
    economy.upgrade(s, c, "剛", 3, DAY)
    assert economy.upgrade_problem(s, c, "剛", 3, DAY) == economy.UPGRADE_DAY_FULL


def test_tier4_counts_as_reachable_through_the_upgrade():
    from tianxia.content import _material_sources

    c = real_content()
    assert {"gang_4", "rou_4", "kuai_4", "man_4"} <= _material_sources(c)


def test_captions_and_howto_say_tier3_sells():
    c = real_content("weekend")
    caps = shopview._trade_captions(c)
    assert "三階 18 兩" in caps["sell_cap"] and "四階不收，留著打神器" in caps["sell_cap"]
    text = "".join(howto.economy_lines(c))
    assert "三階 18 兩" in text and "四階不收，留著打神器" in text and "三階不收" not in text
    c.config.four_tiers.enabled = False
    assert "三階不收" in shopview._trade_captions(c)["sell_cap"]
    assert "三階不收" in "".join(howto.economy_lines(c))


# ── Task 3：四階不算糧草、不送人、不被搶；拆四階裝備回三階 ──────────────


def _pair():
    from tianxia.engine import Game
    from tianxia.sqlite_world import open_world

    c = real_content("weekend")
    world = open_world()
    a = Game.new(c, "甲", rng=random.Random(0), world=world)
    b = Game.new(c, "乙", rng=random.Random(1), world=world)
    for g in (a, b):
        g.client = None
        g.state.player.location = "yingchuan"
    return a, b


def test_tier4_is_not_grain():
    game = _econ_game(bag={"man_1": 2, "man_3": 1})
    s, c = game.state, game.content
    before = materials.grain_of(s, c)
    s.player.materials["man_4"] = 3
    assert materials.grain_of(s, c) == before
    assert all(mid != "man_4" for mid, _ in materials.grain_plan(s, c, before))


def test_gift_refuses_tier4():
    from tianxia import social

    a, b = _pair()
    a.state.player.materials = {"gang_4": 2, "gang_1": 3}
    buttons = social._gift_buttons(a, b)
    choices = next(btn for btn in buttons if btn.arg == "material").choices
    assert [ch["id"] for ch in choices] == ["gang_1"]
    msgs = social._gift(a, b, {"arg": "material", "choice": "gang_4", "amount": 1})
    assert msgs == [social.GIFT_TIER4]
    assert a.state.player.materials["gang_4"] == 2 and "gang_4" not in b.state.player.materials


def test_ambush_never_takes_tier4():
    a, b = _pair()
    b.state.player.materials = {"kuai_4": 3}
    spoils = a._ambush_spoils(b)
    assert spoils.goods == () or all(mid != "kuai_4" for mid, _ in spoils.goods)
    assert b.state.player.materials["kuai_4"] == 3 and "kuai_4" not in a.state.player.materials


def test_dismantle_tier4_gear_gives_tier3():
    from tianxia.state import Equipment

    c = real_content()
    four = Equipment(id="兵:7", name="試刃", kind="劍", attribute="剛", tier=4, quality="下品")
    three = Equipment(id="兵:8", name="舊刃", kind="劍", attribute="剛", tier=3, quality="下品")
    assert equipment.dismantle_material(c, four).id == "gang_3"
    assert equipment.dismantle_material(c, three).id == "gang_3"


# ── Task 4：四階裝備的數字 ──────────────────────────────


def _gear(slot="weapon", tier=4, attribute="剛", kind="劍", gid="兵:9"):
    from tianxia.state import Equipment

    return Equipment(slot=slot, id=gid, name="試器", kind=kind if slot == "weapon" else "", attribute=attribute, tier=tier, quality="下品")


def test_tier4_weapon_bonus_is_17(world):
    from tianxia import team, weapons

    c = real_content()
    sword = team.resolve_art("liubei_wugong", c, world)
    other = next(a for a in ("剛", "柔", "快", "慢") if a != sword.attribute and not weapons.clashes(_gear(attribute=a), sword))
    four, three = (weapons.bonus(_gear(tier=t, attribute=other), sword, c, world) for t in (4, 3))
    assert round(four, 4) == round(three + 0.02, 4) and c.config.weapons.tier_bonus["4"] == 0.17


def test_tier4_armor_cut_is_20():
    from tianxia import armor

    c = real_content()
    four = armor.cut(_gear(slot="armor", tier=4, gid="甲:9"), None, c)
    three = armor.cut(_gear(slot="armor", tier=3, gid="甲:9"), None, c)
    assert round(four - three, 4) == 0.02 and c.config.armor.tier_cut["4"] == 0.20


def test_tier4_forge_costs_300():
    from tianxia import smithing

    c = real_content()
    assert smithing.price(c, 4) == 300 and smithing.price(c, 4, "armor") == 300


def test_tier4_temper_takes_tier3_first():
    from tianxia import smithing

    game = _econ_game(bag={"gang_3": 1, "gang_4": 1})
    s, c = game.state, game.content
    s.player.weapon = _gear(tier=4)
    assert smithing.temper_floor(s.player.weapon) == 3
    mid = smithing.temper_material(s, c)
    assert mid == "gang_3" and smithing.temper_price(c, c.materials[mid]) == 80
    s.player.materials = {"gang_4": 1}
    mid = smithing.temper_material(s, c)
    assert mid == "gang_4" and smithing.temper_price(c, c.materials[mid]) == 150
    s.player.weapon, s.player.materials = _gear(tier=3), {"gang_2": 1}
    assert smithing.temper_material(s, c) is None
    assert smithing.temper_problem(s, c) == "沒有三階以上的素材"


def test_aux_three_tiers_apart():
    from tianxia.models import SmithQuality

    aux = SmithQuality().aux_tier
    assert aux["3"] == 16 and aux["-3"] == -24


def test_arms_bounty_tier4_is_x6():
    from tianxia import bounties

    c = real_content()
    w = _gear(tier=4)
    assert bounties._arms_base(c, w) == c.config.bounties.arms_silver["下品"] * 6
