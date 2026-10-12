"""打造的隱藏配方、名器、線索與鑄譜（docs/superpowers/specs/2026-10-12-打造隱藏配方-design.md；
計畫 docs/superpowers/plans/2026-10-12-打造-1-隱藏配方與防具.md Task 6～9）。"""
from __future__ import annotations

import random
from collections import Counter

import pytest

from conftest import real_content
from tianxia import armor, equipment, forge_secrets, fusion, naming, rules, secret_recipes, smithing, team, weapons
from tianxia.content import ContentError, validate
from tianxia.models import ForgeSecret, ForgeSide
from tianxia.state import Equipment, GearFind, Manual, Weapon, WeaponRecipe, new_game_state

# 測試內容的素材只有精鐵砂（剛一）、玄鋼骨（剛二）、隕鐵膽（剛三）、驚羽（快一）
BLADE = ForgeSecret(
    id="t_blade", slot="weapon", kind="劍", main=ForgeSide(attribute="剛", tier=1), aux=ForgeSide(attribute="快", tier=1),
    name="穿霞劍", note="劍光像一道穿過晚霞的電。", clues=["說書一句。", "鐵匠一句。", "殘譜一句。"],
)
CLEAVER = ForgeSecret(
    id="t_cleaver", slot="weapon", kind="刀", main=ForgeSide(attribute="剛", tier=2), aux=ForgeSide(attribute="剛", min_tier=1),
    name="斷嶂刀", clues=["刀一句。", "刀二句。", "刀三句。"],
)
JACKET = ForgeSecret(
    id="t_jacket", slot="armor", main=ForgeSide(attribute="剛", tier=1), aux=ForgeSide(attribute="快", tier=1),
    name="赤霞鎧", note="甲片紅得像晚霞。", clues=["甲一句。", "甲二句。", "甲三句。"],
)


@pytest.fixture
def forge_content(content):
    # 深複本：test_a_bad_forge_pool_is_refused_at_load 會直接改 c.forge_secrets 裡的那一條（setattr），放模組層的原件進去
    # 就會漏到後面的測試（xdist 分到同一個 worker 時，BLADE 的 kind 被改成 None 之後 test_match 等都會紅）
    content.forge_secrets = {r.id: r.model_copy(deep=True) for r in (BLADE, CLEAVER, JACKET)}
    content.config.forge_secrets.per_season = {"weapon:1": 1, "weapon:2": 1, "armor:1": 1}
    content.config.weapons.enabled = content.config.armor.enabled = True
    return content


# ── Task 6：隱藏配方的內容、比對與命名過濾 ──

def test_each_season_picks_its_own_batch_per_group(forge_content):
    pool = {f"w{i}": BLADE.model_copy(update={"id": f"w{i}", "name": f"鋒{i}劍"}) for i in range(10)}
    forge_content.forge_secrets = {**pool, JACKET.id: JACKET}
    forge_content.config.forge_secrets.per_season = {"weapon:1": 2, "armor:1": 1}
    first = forge_secrets.active(forge_content, 0)
    assert [r.slot for r in first] == ["weapon", "weapon", "armor"] and first == forge_secrets.active(forge_content, 0)  # 全服同一批
    assert any(forge_secrets.active(forge_content, t) != first for t in range(1, 6))  # 換季換一批
    assert forge_secrets._rank(0, "w1") != secret_recipes._rank(0, "w1")  # 尾巴跟武學秘方分開，兩邊的排序互不牽動
    forge_content.config.armor.enabled = False
    assert all(r.slot == "weapon" for r in forge_secrets.active(forge_content, 0))  # 防具關著：不挑（也就不給摸不到的線索）
    forge_content.config.forge_secrets.per_season = {}
    assert forge_secrets.active(forge_content, 0) == []  # 預設全關（測試內容）


def test_match_reads_the_shape_kind_slot_and_main_aux_order(forge_content):
    m = lambda slot, kind, main, aux: forge_secrets.match(forge_content, 0, slot, kind, main, aux)  # noqa: E731
    assert m("weapon", "劍", "gang_1", "kuai_1") == BLADE  # forge_content 放的是深複本：比內容，不比是不是同一個物件
    assert m("weapon", "劍", "kuai_1", "gang_1") is None  # 主輔不交換
    assert m("weapon", "刀", "gang_1", "kuai_1") is None  # 種類對不上
    assert m("armor", "防具", "gang_1", "kuai_1") == JACKET  # 防具不看種類
    assert m("weapon", "刀", "gang_2", "gang_1") == CLEAVER and m("weapon", "刀", "gang_2", "gang_3") == CLEAVER  # 輔料不低於一階
    assert m("weapon", "刀", "gang_1", "gang_1") is None  # 主料寫死二階
    assert forge_secrets.key(BLADE) == "鑄|t_blade"
    forge_content.config.forge_secrets.per_season = {"armor:1": 1}
    assert m("weapon", "劍", "gang_1", "kuai_1") is None  # 這一季沒挑到的不算


def test_the_real_pool_has_twenty_two_named_recipes_and_validates():
    rc = real_content()  # 載入時已經跑過 _validate_forge_secrets
    assert len(rc.forge_secrets) == 22 and not any(r.divine for r in rc.forge_secrets.values())  # 神器那 9 條等第二批（3.4）
    groups = Counter(forge_secrets.group_of(r) for r in rc.forge_secrets.values())
    assert groups == {"weapon:1": 8, "weapon:2": 8, "armor:1": 3, "armor:2": 3}
    assert rc.config.forge_secrets.per_season == {"weapon:1": 2, "weapon:2": 2, "armor:1": 1, "armor:2": 1}
    cfg = rc.config.forge_secrets
    assert (cfg.tale_chance, cfg.smith_chance, cfg.scrap_chance) == (0.5, 0.25, 0.04)  # 設計 6.2（PM 決定第 6 條照預設）
    assert {"柳影劍", "纏絲護手", "負山袍", "霧隱袍"} <= {r.name for r in rc.forge_secrets.values()}
    for tianji in range(5):
        assert len(forge_secrets.active(rc, tianji)) == 6  # 第一批一季 6 條（兵器 4、防具 2，3.2）
    for r in rc.forge_secrets.values():
        assert naming.name_problem(r.name, rc) == naming.FORGE_CLASH  # 撞到自己：表示別人（模型、玩家）取不到這個名字


def test_forge_names_and_gear_names_are_kept_off_other_names(forge_content):
    assert naming.name_problem("穿霞劍", forge_content) == naming.FORGE_CLASH  # 模型替武學取名、玩家替絕學定名都取不到
    rc = real_content()
    for item in [*rc.gear.treasures.values(), *rc.gear.steeds.values()]:
        assert naming.name_problem(item.name, rc) == naming.GEAR_CLASH  # 寶物、名駒的名字也擋（防具打造計畫 PM 決定第 4 條留下的）


@pytest.mark.parametrize("change, message", [
    (lambda c: setattr(c.forge_secrets["t_blade"], "kind", None), "兵器要寫種類"),
    (lambda c: setattr(c.forge_secrets["t_jacket"], "kind", "劍"), "防具不寫種類"),
    (lambda c: setattr(c.forge_secrets["t_blade"].main, "tier", None), "主料要寫死階"),
    (lambda c: setattr(c.forge_secrets["t_cleaver"].aux, "tier", 2), "輔料寫 tier 或 min_tier 其中一個"),
    (lambda c: setattr(c.forge_secrets["t_blade"].aux, "attribute", "柔"), "剛柔、快慢合出來的屬性每季不同"),
    (lambda c: setattr(c.forge_secrets["t_blade"], "name", "寒星刀"), f"名字 寒星刀 過不了（{weapons.KIND_MISSING}）"),
    (lambda c: setattr(c.forge_secrets["t_jacket"], "name", "赤霞刀甲"), "名字 赤霞刀甲 過不了（名字像是兵器）"),
    (lambda c: setattr(c.forge_secrets["t_jacket"], "name", "穿霞劍"), "名字 穿霞劍 重複"),
    (lambda c: c.forge_secrets["t_blade"].clues.__setitem__(0, "一二三四五六七八九十一二三四五六七八九十多"), "第 1 句口訣要 1～20 字"),
    (lambda c: c.forge_secrets["t_blade"].clues.__setitem__(1, "照這個配方打。"), "口訣不寫「配方」「秘方」"),
    (lambda c: c.forge_secrets.__setitem__("t_dup", c.forge_secrets["t_blade"].model_copy(update={"id": "t_dup", "name": "穿雲劍"})),
     "跟隱藏配方 t_blade 認同一個組合"),
    (lambda c: c.config.forge_secrets.per_season.__setitem__("weapon:1", 3), "weapon:1 只有 1 條，不夠挑 3 條"),
    (lambda c: c.config.forge_secrets.per_season.__setitem__("weapon:divine", 1), "要等打造第二批"),
    (lambda c: c.config.forge_secrets.per_season.__setitem__("shield:1", 1), "per_season 只能有"),
])
def test_a_bad_forge_pool_is_refused_at_load(forge_content, change, message):
    validate(forge_content)  # 改之前是好的
    change(forge_content)
    with pytest.raises(ContentError, match=message):
        validate(forge_content)


# ── Task 7：名器、首位發現者、回饋與傳聞 ──

def _smith(content, world, name="試鑄", silver=300):
    """站在測試內容的城鎮（town），悟性 5；背包：精鐵砂 ×6、玄鋼骨 ×2、驚羽 ×4。"""
    from tianxia.engine import Game
    game = Game.new(content, name, rng=random.Random(0), world=world)
    game.client = None
    p = game.state.player
    p.location, p.stamina, p.stats["silver"], p.stats["wis"] = "town", 100.0, silver, 5
    p.materials = {"gang_1": 6, "gang_2": 2, "kuai_1": 4}
    game.sync(0.0)
    return game


def test_hitting_a_hidden_recipe_makes_a_named_piece_and_the_first_finder_is_told(forge_content, world, monkeypatch):
    monkeypatch.setattr(fusion, "season_one", lambda *a, **k: True)  # 首創名望回饋只在第一季規則開著時有
    cfg = forge_content.config.forge_secrets
    game = _smith(forge_content, world, name="甲")
    item, msgs = smithing.forge(game.state, forge_content, world, "劍", "gang_1", "kuai_1", rng=random.Random(0))
    assert (item.name, item.secret, item.recipe) == ("穿霞劍", "t_blade", "兵|劍|gang_1+kuai_1")
    assert equipment.named(forge_content, item) and equipment.grade(item).endswith(equipment.NAMED_MARK)
    assert BLADE.note in msgs[0] and cfg.first_line in msgs[0] and equipment.NAMED_MARK in msgs[0]
    find = world.lookup_gear_find("鑄|t_blade")
    assert (find.creator, find.title, find.id) == ("甲", "穿霞劍", forge_secrets.key(BLADE))
    rumor = cfg.rumor.format(who="甲", name="穿霞劍")
    assert [r.text for r in game.state.world.rumors].count(rumor) == 1
    book = game.state.player.forge_manual
    assert book.solved == ["t_blade"] and book.made == {"t_blade": "兵|劍|gang_1+kuai_1"}
    again, msgs = smithing.forge(game.state, forge_content, world, "劍", "gang_1", "kuai_1", rng=random.Random(1))
    assert again.name == "穿霞劍" and cfg.mine_line in msgs[0] and cfg.first_line not in msgs[0]
    assert [r.text for r in game.state.world.rumors].count(rumor) == 1  # 傳聞只在第一次
    other = _smith(forge_content, world, name="乙")
    third, msgs = smithing.forge(other.state, forge_content, world, "劍", "gang_1", "kuai_1", rng=random.Random(2))
    assert third.name == "穿霞劍" and cfg.follow_line.format(who="甲") in msgs[0]
    entry = other.state.world.echoes["鑄|t_blade"]  # 照「鑄|配方 id」記，不會跟武學 id 或舊的兵器配方名字撞
    assert entry.creator == "甲" and entry.followers == ["乙"] and entry.name == "【穿霞劍】" and entry.made == "打"


def test_armor_hits_its_hidden_recipe_too(forge_content, world):
    game = _smith(forge_content, world)
    item, msgs = smithing.forge(game.state, forge_content, world, smithing.ARMOR_KIND, "gang_1", "kuai_1",
                                rng=smithing.own_rng(game.state, "鎧|gang_1+kuai_1"))
    assert (item.slot, item.name, item.secret, item.recipe) == ("armor", "赤霞鎧", "t_jacket", "鎧|gang_1+kuai_1")
    assert JACKET.note in msgs[0] and world.lookup_gear_find("鑄|t_jacket").slot == "armor"


def test_a_named_piece_adds_two_points_to_the_weapon_bonus_and_the_armor_cut(forge_content, world):
    c = forge_content
    assert c.config.weapons.named_bonus == 0.02 and c.config.armor.named_cut == 0.02  # 設計 4.2【預設】、PM 決定第 5 條
    game = _smith(c, world)
    rules.learn_skill(game.state, c, "sword")
    game.state.player.member.wugong_id = "sword"
    art = team.player_art(game.state, c, world, "sword")
    plain = Weapon(id="兵:1", name="甲劍", kind="劍", attribute="陽", tier=1, quality="下品")
    named = plain.model_copy(update={"secret": "t_blade", "name": "穿霞劍"})
    assert weapons.bonus(named, art, c, world) == pytest.approx(weapons.bonus(plain, art, c, world) + 0.02)
    gone = plain.model_copy(update={"secret": "removed"})
    assert weapons.bonus(gone, art, c, world) == pytest.approx(weapons.bonus(plain, art, c, world))  # 內容拿掉了那一條：照一般的算
    coat = Equipment(id="甲:2", slot="armor", name="甲衣", attribute="陽", tier=1, quality="下品")
    assert armor.cut(coat.model_copy(update={"secret": "t_jacket"}), None, c) == pytest.approx(armor.cut(coat, None, c) + 0.02)


def test_named_names_follow_the_content_on_load(forge_content, world):
    game = _smith(forge_content, world)
    p = game.state.player
    p.weapon = Weapon(id="兵:1", name="舊名", kind="劍", attribute="陽", tier=1, quality="下品", secret="t_blade")
    p.rack = [Equipment(id="甲:2", slot="armor", name="舊甲", attribute="陽", tier=1, quality="下品", secret="gone")]
    game._drop_stale_references()
    assert p.weapon.name == "穿霞劍"  # joy 改名不動存檔：讀檔時照內容重寫（同寶物 refresh_names）
    assert p.rack[0].name == "舊甲"  # 內容拿掉了：留著舊名字當備份


def test_secrets_win_over_old_names_and_general_combos_stay_plain(forge_content, world):
    old = WeaponRecipe(name="寒星劍", key="兵|劍|gang_1+kuai_1", kind="劍", attribute="陽", tier=1, main="gang_1", aux="kuai_1",
                       creator="甲", creator_shown="甲")
    world.claim_weapon_recipe(old.key, old)
    game = _smith(forge_content, world)
    item, _ = smithing.forge(game.state, forge_content, world, "劍", "gang_1", "kuai_1", rng=random.Random(0))
    assert item.name == "穿霞劍"  # 上線前登記過、剛好是這一季的隱藏配方：隱藏配方優先（10.1）
    plain, msgs = smithing.forge(game.state, forge_content, world, "槍", "gang_1", "kuai_1", rng=random.Random(0))
    assert plain.secret is None and plain.name == weapons.table_name(forge_content, "槍", "gang_1", "kuai_1")
    assert not equipment.grade(plain).endswith(equipment.NAMED_MARK) and not any("失傳" in m for m in msgs)
    with world.db.snapshot() as conn:
        keys = sorted(row["key"] for row in conn.execute("SELECT key FROM gear_recipes"))
    assert keys == ["兵|劍|gang_1+kuai_1", "鑄|t_blade"]  # 一般組合什麼都不記（7.2）：只有上線前那一列與名器那一列


def test_hidden_recipes_do_not_change_the_odds_or_the_dice(forge_content, world, monkeypatch):
    game = _smith(forge_content, world)
    before = smithing.forge_odds(game.state, forge_content, world, "劍", "gang_1", "kuai_1")
    saved, forge_content.forge_secrets = forge_content.forge_secrets, {}
    assert smithing.forge_odds(game.state, forge_content, world, "劍", "gang_1", "kuai_1") == before  # 機率只看組成（6.4）
    forge_content.forge_secrets = saved
    seen, real = [], fusion.roll_quality
    monkeypatch.setattr(fusion, "roll_quality", lambda odds, rng: seen.append(rng) or real(odds, rng))
    rng = random.Random(5)
    smithing.forge(game.state, forge_content, world, "劍", "gang_1", "kuai_1", rng=rng)
    assert seen == [rng]  # 名器照樣只擲一次品質、用呼叫端給的那一份（兵器是 Game.rng：序列不位移）


def test_gear_finds_are_one_per_season_and_take_no_name(tmp_path, content):
    from tianxia.sqlite_world import open_world
    store = open_world(tmp_path / "w.db")
    content.config.auto_open_first_season = True
    store.seed_first_season(content)
    find = GearFind(secret="t_blade", slot="weapon", kind="劍", attribute="陽", tier=1, title="穿霞劍", creator="甲", creator_shown="甲")
    assert store.claim_gear_find("鑄|t_blade", find) == (find, True)
    late = find.model_copy(update={"creator": "乙", "creator_shown": "乙"})
    assert store.claim_gear_find("鑄|t_blade", late) == (find, False)  # 誰先寫進去誰是首位發現者
    assert store.lookup_gear_find("鑄|t_blade") == find and store.lookup_gear_find("鑄|t_other") is None
    assert not store.is_skill_name_taken("穿霞劍")  # 名字欄寫鍵本身，不佔名字空間（7.1）
    with pytest.raises(ValueError):
        store.claim_gear_find("兵|劍|gang_1+kuai_1", find)
    store.mutate_season(lambda season: setattr(season, "ended", True))
    assert store.next_season(content, now=1.0)
    assert store.lookup_gear_find("鑄|t_blade") is None  # 換季：新的一季沒有首位發現者（照季分，舊的列不刪）


def test_old_saves_read_with_empty_forge_fields(content):
    old = '{"id": "兵:1", "name": "寒星劍", "kind": "劍", "attribute": "陽", "tier": 1, "quality": "中品"}'
    assert Equipment.model_validate_json(old).secret is None
    assert Manual.model_validate_json('{"tianji": 2, "heard": {}, "solved": []}').made == {}
    assert new_game_state(content, "甲").player.forge_manual == Manual()
