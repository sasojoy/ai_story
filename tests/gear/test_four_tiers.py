"""素材四階（docs/superpowers/specs/2026-10-17-正式季整合-design.md 第四、五章；正式季整合第 2 批）。

測試內容保持三階、開關關著（10.1）：四階的測試用正式內容（real_content），或在測試裡自己補料。"""
from __future__ import annotations

import random
from unittest import mock

import pytest

from conftest import no_week_unlock, real_content

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


@pytest.mark.smoke
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

    c = no_week_unlock(real_content("week7"))
    c.config.four_tiers.enabled = on
    c.config.auto_open_first_season = True  # 不然停在籌備中，鐵匠鋪進不去
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


def test_the_menu_counts_three_to_four_per_season():
    game = _econ_game(bag={"gang_3": 5})
    game.state.player.tutorial_step = len(game.content.tutorial.steps)
    game.choose("act:smith")
    game.choose("smith:page:material")
    label = next(o.label for o in game.options() if o.id == "smith:upgrade:剛:4")
    assert "這一季還能換 2 個" in label and "今天" not in label


def test_the_materials_page_counts_three_to_four_per_season():
    """FB-342：素材頁升階格的上限字由伺服器給（三換四是這一季、開關關著的二換三是今天），最上面那一句講清楚三換四一定同屬性。"""
    game = _econ_game(bag={"gang_3": 5, "gang_2": 10})
    rows = {(r["attribute"], r["tier"]): r for r in shopview.trade_view(game.state, game.content, DAY)["upgrade"]}
    assert rows[("剛", 4)]["left_text"] == "這一季還能 2 個" and rows[("剛", 3)]["left_text"] == ""
    hint = shopview.trade_view(game.state, game.content, DAY)["hint"]
    assert "三換四一定是同一個屬性" in hint
    off = _econ_game(bag={"gang_2": 10}, on=False)
    rows = {(r["attribute"], r["tier"]): r for r in shopview.trade_view(off.state, off.content, DAY)["upgrade"]}
    assert rows[("剛", 3)]["left_text"] == "今天還能 1 個"
    assert "三換四" not in shopview.trade_view(off.state, off.content, DAY)["hint"]


def test_the_depot_says_tier4_is_not_taken_when_only_tier4_is_left():
    """FB-343：背包只剩四階時，軍需帳那一格不說「背包裡沒有素材」，說四階不收。"""
    game = _econ_game(bag={"gang_4": 2})
    view = shopview.donate_view(game.state, game.content, DAY)
    assert view["cells"] == [] and view["empty"] == shopview.DONATE_TIER4_ONLY
    game.state.player.materials = {}
    assert shopview.donate_view(game.state, game.content, DAY)["empty"] == shopview.DONATE_EMPTY


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


def test_real_content_loads_with_the_tier4_rules_switched_off(tmp_path):
    """FB-340：主機在 content/config.json 關掉素材四階（或升階）時，正式內容照樣載得起來；四階料是內容收不回的，關著時只是拿不到
    （設計 10.1：九件神器實際上打不出來）。在載入之前就改設定。"""
    import json
    import shutil
    from pathlib import Path

    from tianxia.content import load_content

    root = tmp_path / "content"
    shutil.copytree(Path(__file__).resolve().parents[2] / "content", root)
    raw = json.loads((root / "config.json").read_text(encoding="utf-8"))
    for patch in ({"four_tiers": {"enabled": False}}, {"economy": {"upgrade": False}}):
        (root / "config.json").write_text(json.dumps({**raw, **patch}, ensure_ascii=False), encoding="utf-8")
        c = load_content(root)
        assert {"gang_4", "rou_4", "kuai_4", "man_4"} <= set(c.materials)


def test_tier4_counts_as_reachable_through_the_upgrade():
    from tianxia.content import _material_sources

    c = real_content()
    assert {"gang_4", "rou_4", "kuai_4", "man_4"} <= _material_sources(c)


def test_captions_and_howto_say_tier3_sells():
    c = no_week_unlock(real_content("week7"))
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

    c = no_week_unlock(real_content("week7"))
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


# ── Task 5：四階名器 ──────────────────────────────


def test_tier4_main_rolls_named_half_the_time():
    c = real_content()
    assert four_tiers.named_chance(c, "gang_4", "rou_1") == 0.5
    assert four_tiers.named_chance(c, "gang_4", "rou_4") == 0.8
    assert four_tiers.named_chance(c, "gang_3", "rou_4") == 0
    c.config.four_tiers.enabled = False
    assert four_tiers.named_chance(c, "gang_4", "rou_4") == 0


def _forge_game(bag):
    game = _econ_game(bag=bag, silver=5000)
    game.state.player.weapon = None
    return game


def test_named_tier4_gets_a_table_name_and_bonus():
    from tianxia import smithing

    game = _forge_game({"gang_4": 2})
    s, c, w = game.state, game.content, game.world
    c.config.four_tiers.named_both = 1.0
    with mock.patch.object(w, "claim_gear_find", side_effect=AssertionError("四階名器不登記首位發現")):
        item, msgs = smithing.forge(s, c, w, "劍", "gang_4", "gang_4", rng=random.Random(0))
    entry = c.tier4_named[item.named_entry]
    assert (entry.slot, entry.kind, entry.attribute, entry.name) == ("weapon", "劍", item.attribute, item.name)
    assert equipment.grade(item).startswith("四階") and equipment.grade(item).endswith("・名器")
    assert equipment.named(c, item) and equipment.is_named(item)
    assert "名器" in msgs[0]


def test_named_roll_does_not_shift_game_rng():
    from tianxia import smithing

    draws = []
    for chance in (0.0, 1.0):
        game = _forge_game({"gang_4": 2})
        game.content.config.four_tiers.named_both = chance
        rng = random.Random(7)
        smithing.forge(game.state, game.content, game.world, "劍", "gang_4", "gang_4", rng=rng)
        draws.append(rng.random())
    assert draws[0] == draws[1]


def test_divine_recipe_still_beats_named():
    from tianxia import forge_secrets as fs
    from tianxia import smithing

    game = _forge_game({"kuai_4": 1, "rou_4": 1})
    s, c, w = game.state, game.content, game.world
    c.config.four_tiers.named_both = 1.0
    recipe = c.forge_secrets["wd_dark_crystal"]
    with mock.patch.object(fs, "match", return_value=recipe):
        item, _ = smithing.forge(s, c, w, "劍", "kuai_4", "rou_4", rng=random.Random(0))
    assert item.original or item.copy_of is not None
    assert item.named_entry is None


def test_go_option_hints_named_for_tier4_main():
    from tianxia import smithing

    game = _forge_game({"gang_4": 1, "gang_3": 1})
    s, c, w = game.state, game.content, game.world
    four = smithing.go_option(s, c, w, "劍", "gang_4", "gang_3").label
    three = smithing.go_option(s, c, w, "劍", "gang_3", "gang_4").label
    assert smithing.NAMED_HINT in four and smithing.NAMED_HINT not in three
    assert "神器" not in smithing.NAMED_HINT and "%" not in smithing.NAMED_HINT


def test_the_shop_forge_line_hints_named_for_tier4_main():
    """FB-341：店面的開爐說明（/api/smith_line）跟一步一步選單的開爐鈕一樣，主料是四階時多那一句。"""
    from tianxia import smithing

    game = _forge_game({"gang_4": 1, "gang_3": 1})
    s, c, w = game.state, game.content, game.world
    assert shopview.smith_line(s, c, w, "劍", "gang_4", "gang_3")["named_hint"] == smithing.NAMED_HINT
    assert shopview.smith_line(s, c, w, "劍", "gang_3", "gang_4")["named_hint"] == ""


def test_old_gear_without_named_entry_loads():
    from tianxia.state import Equipment

    item = Equipment.model_validate({"id": "兵:1", "name": "舊刃", "kind": "劍", "attribute": "剛", "tier": 3, "quality": "下品"})
    assert item.named_entry is None and not equipment.is_named(item)


def test_tier4_named_table_passes_naming():
    from collections import Counter

    from tianxia.martial_arts import ATTRIBUTES
    from tianxia.models import WEAPON_KINDS

    c = real_content()
    assert len(c.tier4_named) == 112
    counts = Counter((e.slot, e.kind, e.attribute) for e in c.tier4_named.values())
    assert len(counts) == 56
    for slot, kind in [("weapon", k) for k in WEAPON_KINDS] + [("armor", None)]:
        for attribute in ATTRIBUTES:
            assert counts[(slot, kind, attribute)] == 2, (kind, attribute)


# ── Task 6：九件神器改用四階 ──────────────────────────────

DIVINE_ATTRS = {
    "wd_dark_crystal": ("快", "柔"), "wd_fallen_star": ("剛", "剛"), "wd_pierce_sun": ("剛", "快"), "wd_shake_mountain": ("慢", "剛"),
    "wd_chase_lightning": ("快", "快"), "wd_cold_abyss": ("柔", "慢"), "ad_mountain_stand": ("剛", "慢"), "ad_still_wave": ("柔", "柔"),
    "ad_skim_shadow": ("快", "柔"),
}


def test_divine_recipes_are_all_tier4():
    c = real_content()
    divine = {r.id: r for r in c.forge_secrets.values() if r.divine and r.wave == 1}  # 一開始的九件（新神器第一批是 wave 2，正式季第 10 批）
    assert set(divine) == set(DIVINE_ATTRS)
    for rid, (main, aux) in DIVINE_ATTRS.items():
        r = divine[rid]
        assert (r.main.attribute, r.main.tier, r.aux.attribute, r.aux.tier) == (main, 4, aux, 4), rid


def test_divine_clues_name_tier4_materials():
    c = real_content()
    old = ("三階", "隕鐵膽", "化水晶", "掣電鱗", "鎮山鐵")
    new = ("熔星髓", "天池露", "奔雷角", "歸墟壤")
    for r in c.forge_secrets.values():
        if not r.divine:
            continue
        text = "".join(r.clues)
        assert not any(word in text for word in old), r.id
        assert "四階" in r.clues[2] and any(word in r.clues[1] for word in new), r.id


def test_divine_piece_says_tier4():
    c = real_content()
    piece = forge_secrets.piece_text(c, c.forge_secrets["wd_dark_crystal"], forge_secrets.MAIN)
    assert "快屬的四階料" in piece


def test_forging_a_divine_now_costs_300():
    from tianxia import smithing

    c = real_content()
    assert smithing.price(c, smithing.tier_of(c, "kuai_4")) == 300


def test_old_tier3_divine_keeps_its_bonus(world):
    from tianxia import team, weapons
    from tianxia.state import Equipment

    c = real_content()
    sword = team.resolve_art("liubei_wugong", c, world)
    old = Equipment(id="兵:3", name="仿・玄晶劍", kind="劍", attribute="虛", tier=3, quality="上品", copy_of="鑄|wd_dark_crystal",
                    secret="wd_dark_crystal")
    new = old.model_copy(update={"tier": 4})
    assert weapons.bonus(old, sword, c, world) == weapons.bonus(new, sword, c, world)  # 仿品照仿品的基本值，不看階
    assert equipment.grade(old) == "三階上品・仿品"


# ── Task 7：鐵匠的四條規矩 ──────────────────────────────


def _smith_game(bag):
    game = _econ_game(bag=bag)
    game.state.player.tutorial_step = len(game.content.tutorial.steps)
    return game


def _enter(game):
    game.choose("act:smith")
    rule = game.state.player.smith_rule
    game.choose("smith:back")
    return rule


def test_rule_line_only_with_tier4():
    game = _smith_game({"gang_3": 1})
    assert _enter(game) == ""
    game.state.player.materials["rou_4"] = 1
    game.choose("act:smith")
    assert game.state.player.smith_rule in game.content.shop_lines["smith"]["rules"]
    assert shopview.smith_view(game.state, game.content, game.world)["rule"] == game.state.player.smith_rule


def test_rules_rotate_without_repeating():
    game = _smith_game({"gang_4": 1})
    pool = game.content.shop_lines["smith"]["rules"]
    heard = [_enter(game) for _ in range(len(pool))]
    assert sorted(heard) == sorted(pool)
    assert _enter(game) == pool[0]


def test_clue_beats_rule():
    game = _smith_game({"gang_4": 1})
    game.choose("act:smith")
    game.state.player.shop_clue = "鐵匠順口說了一句"
    assert shopview.smith_view(game.state, game.content, game.world)["rule"] == ""


def test_rules_never_name_a_recipe():
    from tianxia.weapons import WEAPON_WORDS

    c = real_content()
    banned = {w for words in WEAPON_WORDS.values() for w in words} | set("陰陽剛柔快慢虛實")
    banned |= {m.name for m in c.materials.values()} | {r.name for r in c.forge_secrets.values()}
    for line in c.shop_lines["smith"]["rules"]:
        assert not any(word in line for word in banned), line


# ── Task 8：機器人 ──────────────────────────────


def test_pick_pair_keeps_a_lone_tier4():
    from tianxia import smithing

    game = _econ_game(bag={"gang_4": 1, "gang_3": 3})
    assert smithing._pick_pair(game.state, game.content, "剛", []) == ("gang_3", "gang_3")


def test_pick_pair_opens_tier4_with_two():
    from tianxia import smithing

    game = _econ_game(bag={"gang_4": 1, "rou_4": 1, "gang_3": 3})
    main, aux = smithing._pick_pair(game.state, game.content, "剛", [])
    assert (main, aux) == ("gang_4", "rou_4")
    mine = [_gear(tier=4).model_copy(update={"recipe": "兵|劍|gang_4+rou_4"})]  # 已經有一件自己打的四階：不再開四階的爐
    again = smithing._pick_pair(game.state, game.content, "剛", mine)
    assert again is None or game.content.materials[again[0]].tier < 4


def test_bot_trades_three_to_four():
    from tianxia import bot

    game = _econ_game(bag={"gang_3": 5}, silver=1000)
    assert bot.trade_want(game) == ("upgrade", "剛", 4)


def test_bot_sells_spare_tier3():
    from tianxia import bot

    game = _econ_game(bag={"gang_3": 8}, silver=0)
    assert bot.trade_want(game) == ("sell", "gang_3", 8 - bot.TRADE_KEEP[3])
