"""素材四階（docs/superpowers/specs/2026-10-17-正式季整合-design.md 第四、五章；正式季整合第 2 批）。

測試內容保持三階、開關關著（10.1）：四階的測試用正式內容（real_content），或在測試裡自己補料。"""
from __future__ import annotations

from conftest import real_content

from tianxia import equipment, forge_secrets, four_tiers, materials, shopview, skillview


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
