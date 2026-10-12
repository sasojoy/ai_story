"""打造第二批：神器原品與仿品、定名、神器譜、三階素材新來源、假人打造（docs/superpowers/specs/2026-10-12-打造隱藏配方-design.md
第五節、第十三節；計畫 docs/superpowers/plans/2026-10-12-打造-2-神器.md）。"""
from __future__ import annotations

import random
from collections import Counter

import pytest

from conftest import real_content
from test_forge_secrets import BLADE, CLEAVER, JACKET
from tianxia import armor, equipment, forge_secrets, fusion, rules, smithing, team, weapons
from tianxia.content import validate
from tianxia.models import ForgeSecret, ForgeSide
from tianxia.state import COPY_NAME, DIVINE_UNNAMED, Equipment, GearFind, Weapon

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


# ── Task 3：原品與仿品 ──

def test_the_first_divine_forge_is_the_unnamed_original_and_rolls_no_quality(divine_content, world, monkeypatch):
    rolled = []
    monkeypatch.setattr(fusion, "roll_quality", lambda odds, rng: rolled.append(rng) or "下品")
    cfg = divine_content.config.forge_secrets
    game = _forger(divine_content, world, name="甲")
    item, msgs = smithing.forge(game.state, divine_content, world, "劍", "gang_3", "gang_3", rng=random.Random(0))
    assert rolled == []  # 照甲（5.1）：一爐必出神器，不擲品質，不碰亂數
    assert (item.name, item.original, item.copy_of, item.secret, item.tier, item.quality) == (DIVINE_UNNAMED, True, None, "t_star", 3, "上品")
    assert equipment.grade(item) == "三階上品" + equipment.DIVINE_MARK and not equipment.named(divine_content, item)
    assert msgs[0].startswith(f"鐵匠把兩份隕鐵膽下爐，打出一把【{DIVINE_UNNAMED}】") and STAR.note in msgs[0] and cfg.divine_line in msgs[0]
    find = world.lookup_gear_find("鑄|t_star")
    assert (find.divine, find.owner, find.master_shown, find.divine_name, find.copies, find.name) == (True, "甲", "甲", None, 0, DIVINE_UNNAMED)
    rumors = [r.text for r in game.state.world.rumors]
    assert cfg.divine_rumor.format(who="甲") in rumors and not any("墜星劍" in r for r in rumors)  # 打出時的傳聞不帶名字（7.2）
    assert game.state.player.forge_manual.solved == ["t_star"]  # 鑄譜照樣記打中


def test_after_the_original_every_forge_is_a_copy_named_after_it(divine_content, world, monkeypatch):
    monkeypatch.setattr(fusion, "season_one", lambda *a, **k: True)  # 首創名望回饋只在第一季規則開著時有
    cfg = divine_content.config.forge_secrets
    first = _forger(divine_content, world, name="甲")
    smithing.forge(first.state, divine_content, world, "劍", "gang_3", "gang_3")
    mine, msgs = smithing.forge(first.state, divine_content, world, "劍", "gang_3", "gang_3")
    assert (mine.original, mine.copy_of, mine.name) == (False, "鑄|t_star", COPY_NAME.format(name=DIVINE_UNNAMED))  # 主人自己打的也是仿品（5.3）
    assert cfg.copy_mine_line in msgs[0]
    other = _forger(divine_content, world, name="乙")
    copy, msgs = smithing.forge(other.state, divine_content, world, "劍", "gang_3", "gang_3")
    assert (copy.original, copy.copy_of, copy.secret, copy.tier, copy.quality) == (False, "鑄|t_star", "t_star", 3, "上品")
    assert equipment.grade(copy) == "三階上品" + equipment.COPY_MARK and cfg.copy_line.format(who="甲") in msgs[0]
    assert world.lookup_gear_find("鑄|t_star").copies == 2
    entry = other.state.world.echoes["鑄|t_star"]
    assert entry.creator == "甲" and entry.followers == ["乙"] and entry.made == "打"  # 原品主人的回饋：主人自己打的不算


def test_armor_divine_recipes_make_originals_and_copies_too(divine_content, world):
    game = _forger(divine_content, world)
    key = "鎧|gang_3+gang_3"
    coat, _ = smithing.forge(game.state, divine_content, world, smithing.ARMOR_KIND, "gang_3", "gang_3", rng=smithing.own_rng(game.state, key))
    again, _ = smithing.forge(game.state, divine_content, world, smithing.ARMOR_KIND, "gang_3", "gang_3", rng=smithing.own_rng(game.state, key))
    assert (coat.slot, coat.original, coat.secret, coat.quality) == ("armor", True, "t_ward", "上品")
    assert (again.copy_of, again.name) == ("鑄|t_ward", COPY_NAME.format(name=DIVINE_UNNAMED))
    assert world.lookup_gear_find("鑄|t_ward").slot == "armor"


def test_originals_and_copies_take_their_own_base_and_skip_the_named_bonus(divine_content, world):
    c = divine_content
    w, a = c.config.weapons, c.config.armor
    assert (w.copy_base, w.original_base, a.copy_cut, a.original_cut) == (0.19, 0.22, 0.22, 0.25)  # 設計 4.3
    game = _forger(c, world)
    rules.learn_skill(game.state, c, "sword")
    game.state.player.member.wugong_id = "sword"
    art = team.player_art(game.state, c, world, "sword")
    plain = Weapon(id="兵:1", name="甲劍", kind="劍", attribute="剛", tier=3, quality="上品")  # 一般三階上品
    base = weapons.bonus(plain, art, c, world)
    original = plain.model_copy(update={"original": True, "secret": "t_star", "name": "墜星劍"})
    copy = plain.model_copy(update={"copy_of": "鑄|t_star", "secret": "t_star", "name": "仿・墜星劍"})
    assert weapons.bonus(original, art, c, world) == pytest.approx(base + 0.07)  # 22 對 15：上品合計 26 對 19
    assert weapons.bonus(copy, art, c, world) == pytest.approx(base + 0.04)  # 19 對 15：上品合計 23 對 19
    assert weapons.bonus(plain.model_copy(update={"secret": "t_blade"}), art, c, world) == pytest.approx(base + 0.02)  # 名器照舊
    gone = original.model_copy(update={"secret": "removed"})
    assert weapons.bonus(gone, art, c, world) == pytest.approx(base + 0.07)  # 神器不看內容：拿掉了那一條照樣算神器
    coat = Equipment(id="甲:2", slot="armor", name="甲衣", attribute="剛", tier=3, quality="上品")
    assert armor.cut(coat.model_copy(update={"original": True, "secret": "t_ward"}), None, c) == pytest.approx(armor.cut(coat, None, c) + 0.07)
    assert armor.cut(coat.model_copy(update={"copy_of": "鑄|t_ward", "secret": "t_ward"}), None, c) == pytest.approx(armor.cut(coat, None, c) + 0.04)


def test_the_go_button_says_a_solved_divine_recipe_always_makes_a_copy(divine_content, world):
    game = _forger(divine_content, world, name="甲")
    smithing.forge(game.state, divine_content, world, "劍", "gang_3", "gang_3")
    label = smithing.go_option(game.state, divine_content, world, "劍", "gang_3", "gang_3").label
    assert smithing.DIVINE_HEAD.format(name="墜星劍") in label and "工錢 150 兩" in label and "下品" not in label  # 6.4：必出神器，不寫機率
    fresh = _forger(divine_content, world, name="乙")
    label = smithing.go_option(fresh.state, divine_content, world, "劍", "gang_3", "gang_3").label
    assert "墜星劍" not in label and "神器" not in label and "下品" in label  # 自己的鑄譜上沒打中過：不露（別人打中了也不寫）


def test_old_gear_finds_read_as_named_pieces_and_divine_items_keep_names_without_a_row(divine_content, world):
    old = GearFind.model_validate_json('{"secret": "t_blade", "slot": "weapon", "attribute": "陽", "tier": 1, "title": "穿霞劍"}')
    assert (old.divine, old.owner, old.divine_name, old.copies, old.name) == (False, None, None, 0, "穿霞劍")  # 第一批的列照讀
    game = _forger(divine_content, world)
    p = game.state.player
    p.rack = [Weapon(id="兵:9", name="仿・舊神器", kind="劍", attribute="剛", tier=3, quality="上品", secret="t_star", copy_of="鑄|t_star")]
    game._drop_stale_references()
    assert p.rack[0].name == "仿・舊神器"  # 這一季那一列不在（別一季打的、資料不在）：留著存檔裡的名字
