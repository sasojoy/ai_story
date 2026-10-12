"""打造第二批：神器原品與仿品、定名、神器譜、三階素材新來源、假人打造（docs/superpowers/specs/2026-10-12-打造隱藏配方-design.md
第五節、第十三節；計畫 docs/superpowers/plans/2026-10-12-打造-2-神器.md）。"""
from __future__ import annotations

import random
from collections import Counter

import pytest

from conftest import real_content
from test_forge_secrets import BLADE, CLEAVER, JACKET
from tianxia import forge_secrets, smithing
from tianxia.content import validate
from tianxia.models import ForgeSecret, ForgeSide

# 測試內容的三階素材只有隕鐵膽（剛三）：神器配方兩樣都是它（剛＋剛＝剛，不在剛柔、快慢那兩對裡）。
# 譜名不能是測試內容字表組得出的名字：content.validate 拿整張字表（字首 20 × 兵器中間字 16）過 name_problem，
# 「斷」是字首、「星」是中間字，「斷星劍」會被擋成 FORGE_CLASH，所以用字首沒有的「墜」
STAR = ForgeSecret(
    id="t_star", slot="weapon", kind="劍", main=ForgeSide(attribute="剛", tier=3), aux=ForgeSide(attribute="剛", tier=3),
    divine=True, name="墜星劍", note="劍身黑得像沒有星的夜。", clues=["星一句。", "星二句。", "星三句。"],
)
WARD = ForgeSecret(
    id="t_ward", slot="armor", main=ForgeSide(attribute="剛", tier=3), aux=ForgeSide(attribute="剛", tier=3),
    divine=True, name="鎮星甲", note="甲片沉得像一塊落下來的星鐵。", clues=["甲星一句。", "甲星二句。", "甲星三句。"],
)


@pytest.fixture
def divine_content(content):
    # 深複本（同 test_forge_secrets.forge_content 的理由：有測試會改內容裡的那一條）
    content.forge_secrets = {r.id: r.model_copy(deep=True) for r in (BLADE, CLEAVER, JACKET, STAR, WARD)}
    content.config.forge_secrets.per_season = {"weapon:1": 1, "weapon:2": 1, "armor:1": 1, "weapon:divine": 1, "armor:divine": 1}
    content.config.weapons.enabled = content.config.armor.enabled = True
    return content


def _forger(content, world, name="鑄神", silver=1000):
    """站在測試內容的城鎮（town），悟性 5；背包：隕鐵膽 ×6、精鐵砂 ×4、驚羽 ×2。"""
    from tianxia.engine import Game
    game = Game.new(content, name, rng=random.Random(0), world=world)
    game.client = None
    p = game.state.player
    p.location, p.stamina, p.stats["silver"], p.stats["wis"] = "town", 100.0, silver, 5
    p.materials = {"gang_3": 6, "gang_1": 4, "kuai_1": 2}
    game.sync(0.0)
    return game


# ── Task 2：神器配方的內容與挑選 ──

def test_divine_recipes_are_picked_per_season_in_their_own_group(divine_content):
    validate(divine_content)  # 神器組不再擋（第一批載入時擋成 0）
    picked = forge_secrets.active(divine_content, 0)
    assert Counter(forge_secrets.group_of(r) for r in picked) == {
        "weapon:1": 1, "weapon:2": 1, "armor:1": 1, "weapon:divine": 1, "armor:divine": 1}
    assert forge_secrets.match(divine_content, 0, "weapon", "劍", "gang_3", "gang_3") == STAR
    assert forge_secrets.match(divine_content, 0, "armor", smithing.ARMOR_KIND, "gang_3", "gang_3") == WARD
    divine_content.config.armor.enabled = False
    assert all(r.slot == "weapon" for r in forge_secrets.active(divine_content, 0))  # 防具關著：防具的神器配方也不挑


def test_adding_the_divine_groups_leaves_the_other_picks_alone():
    """上線那一季（10.1）：每一組各自照雜湊排、各挑各的，多了神器那兩組，原本那 6 條一條都不變。"""
    rc = real_content()
    with_divine = {t: [r.id for r in forge_secrets.active(rc, t) if not r.divine] for t in range(6)}
    rc.config.forge_secrets.per_season = {g: n for g, n in rc.config.forge_secrets.per_season.items() if not g.endswith("divine")}
    assert {t: [r.id for r in forge_secrets.active(rc, t)] for t in range(6)} == with_divine
