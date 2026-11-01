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


@pytest.mark.smoke
def test_the_real_pool_has_fifty_four_named_recipes_and_validates():
    rc = real_content()  # 載入時已經跑過 _validate_forge_secrets
    # 3.4：兵器 22、防具 9，神器 9；正式季第 10 批加新神器第一批 12 件（兵器 8、防具 4，wave 2）；第 4 批補三階一組（兵器 8、防具 3）
    assert len(rc.forge_secrets) == 54 and sum(r.divine for r in rc.forge_secrets.values()) == 21
    assert sum(r.divine and r.wave == 1 for r in rc.forge_secrets.values()) == 9
    groups = Counter(forge_secrets.group_of(r) for r in rc.forge_secrets.values())
    assert groups == {"weapon:1": 8, "weapon:2": 8, "weapon:3": 8, "weapon:divine": 14, "armor:1": 3, "armor:2": 3, "armor:3": 3,
                      "armor:divine": 7}
    assert rc.config.forge_secrets.per_season == {
        "weapon:1": 2, "weapon:2": 2, "weapon:3": 2, "weapon:divine": 2, "armor:1": 1, "armor:2": 1, "armor:3": 1, "armor:divine": 1}
    cfg = rc.config.forge_secrets
    assert (cfg.tale_chance, cfg.smith_chance, cfg.scrap_chance) == (0.5, 0.25, 0.04)  # 設計 6.2（PM 決定第 6 條照預設）
    names = {r.name for r in rc.forge_secrets.values()}
    assert {"柳影劍", "纏絲護手", "負山袍", "霧隱袍", "玄晶劍", "隕星刀", "寒淵拳套", "嶽峙鎧", "掠影衫"} <= names
    for r in rc.forge_secrets.values():
        if r.divine:
            assert r.main.tier == 4 and r.aux.tier == 4  # 神器配方兩樣都四階（正式季整合 5.5；以前是三階，5.1）
    for tianji in range(5):
        assert len(forge_secrets.active(rc, tianji)) == 12  # 一季 12 條（兵器 8、防具 4，3.2；第 4 批多三階兵器 2、防具 1）
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
    (lambda c: c.config.forge_secrets.per_season.__setitem__("weapon:divine", 1), "weapon:divine 只有 0 條，不夠挑 1 條"),
    (lambda c: setattr(c.forge_secrets["t_cleaver"], "divine", True), "神器配方的主料、輔料都要四階"),  # 正式季整合 5.5
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
    assert BLADE.note in msgs[0] and cfg.first_line in msgs[0] and msgs[0].startswith("打出一把名器【")  # FB-148：名器寫在名字前面
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


# ── Task 8：三種線索與鑄譜（引擎）──

def test_tales_and_scraps_also_roll_forge_clues_on_their_own_dice(forge_content, world):
    game = _smith(forge_content, world)
    event = forge_content.events["drunk"]
    rule = forge_content.config.forge_secrets
    forge_content.config.secrets.tale_events = ["drunk"]  # 武學那一擲照舊用這張清單；測試內容沒有武學秘方，那一擲不會有字
    assert game._tale_clue(event) == [] and game._scrap_find() == []  # 機率是 0：不擲
    rule.tale_chance, rule.scrap_chance = 1.0, 1.0
    before = game.rng.getstate()
    tale = game._tale_clue(event)
    scrap = game._scrap_find()
    assert game.rng.getstate() == before  # 自己的亂數，不動 Game.rng
    assert len(tale) == 1 and tale[0].startswith(rule.tale_frame.split("{clue}")[0])
    assert len(scrap) == 1 and scrap[0].startswith(rule.scrap_frame.split("{clue}")[0])
    book = game.state.player.forge_manual
    assert {i for idx in book.heard.values() for i in idx} == {forge_secrets.TALE, forge_secrets.SCRAP}
    assert game.state.player.manual.heard == {}  # 鑄器的口訣進鑄譜，不進武學譜
    rows = game.status_data()["forge_manual"]
    assert len(rows) == len(book.heard) and all(r["solved"] is None and r["recipe"] is None for r in rows)


def test_each_smithy_knows_one_clue_and_tells_it_after_you_spend(forge_content, world):
    game = _smith(forge_content, world)
    rule = forge_content.config.forge_secrets
    rule.smith_chance = 1.0
    tianji = world.read().tianji
    recipe = forge_secrets.smith_clue(forge_content, tianji, "town")
    assert recipe is not None and forge_secrets.smith_clue(forge_content, tianji, "lake") is None  # 不是城鎮的地方沒有鐵匠
    assert forge_secrets.smith_clue(forge_content, tianji, "town") is recipe  # 同一家這一季一直是同一條
    said = rule.smith_frame.format(clue=recipe.clues[forge_secrets.SMITH])
    game.choose("act:smith")
    game.state.player.rack = [Weapon(id="兵:9", name="廢刃", kind="刀", attribute="剛", tier=1, quality="下品")]
    assert said not in game.choose("smith:dismantle:兵:9")  # 拆解拿到素材、沒花錢：不擲
    assert said in game.choose("smith:buy:劍")  # 花了銀兩：鐵匠順口說出這家知道的那一句
    assert forge_secrets.SMITH in game.state.player.forge_manual.heard[recipe.id]
    assert said not in game.choose("smith:buy:刀")  # 已經聽過那一句就不再說（免得洗版）
    before = game.rng.getstate()
    game._smith_clue()
    assert game.rng.getstate() == before


def test_the_smith_clue_rolls_again_after_each_spend_at_the_same_moment(forge_content, world, monkeypatch):
    """「要 PM 定的」第 3 條：鐵匠鋪的動作不花時間，種子多帶這一下之後的銀兩與素材數，同一刻連按每一下都各擲各的。"""
    game = _smith(forge_content, world)
    forge_content.config.forge_secrets.smith_chance = 0.25
    seeds = []
    monkeypatch.setattr(secret_recipes, "roll", lambda chance, seed: seeds.append(seed) or False)
    game.choose("act:smith")
    game.choose("smith:buy:劍")
    game.choose("smith:buy:刀")
    smith_seeds = [x for x in seeds if x.startswith("鐵匠|")]
    assert len(smith_seeds) == 2 and smith_seeds[0] != smith_seeds[1]


def test_the_forge_book_shows_heard_clues_and_solved_recipes_with_their_mix(forge_content, world):
    game = _smith(forge_content, world)
    tianji = world.read().tianji
    secret_recipes.note(forge_secrets.manual(game.state, tianji), JACKET, forge_secrets.SMITH)
    smithing.forge(game.state, forge_content, world, "劍", "gang_1", "kuai_1", rng=random.Random(0))
    rows = game.status_data()["forge_manual"]
    assert {"clues": [], "solved": "穿霞劍", "recipe": "劍：精鐵砂＋驚羽"} in rows  # 打中過：名字與配方（6.3）
    assert {"clues": ["甲二句。"], "solved": None, "recipe": None} in rows  # 只聽過鐵匠那一句：不寫配方
    assert len(rows) == 2  # 沒聽過也沒打過的（斷嶂刀）不露
    smithing.forge(game.state, forge_content, world, smithing.ARMOR_KIND, "gang_1", "kuai_1", rng=random.Random(0))
    assert {"clues": ["甲二句。"], "solved": "赤霞鎧", "recipe": "防具：精鐵砂＋驚羽"} in game.status_data()["forge_manual"]
    game.state.player.forge_manual = Manual(tianji=tianji + 1)  # 別一季的譜
    assert game.status_data()["forge_manual"] == []


def test_the_go_button_names_only_what_your_own_book_has_solved(forge_content, world):
    game = _smith(forge_content, world, name="甲")
    go = lambda g: smithing.go_option(g.state, forge_content, world, "劍", "gang_1", "kuai_1")  # noqa: E731
    assert "穿霞劍" not in go(game).label and "鑄譜" not in go(game).label  # 沒打中過：不露（6.4）
    other = _smith(forge_content, world, name="乙")
    smithing.forge(other.state, forge_content, world, "劍", "gang_1", "kuai_1", rng=random.Random(0))
    assert "穿霞劍" not in go(game).label  # 別人打中了也不露（不然點一遍就知道別人摸到了哪幾條）
    label = go(other).label
    assert label.startswith("開爐：精鐵砂＋驚羽" + smithing.SOLVED_HEAD.format(name="穿霞劍") + "（劍・屬陽・一階・")
    assert go(other).wait == ""


def test_named_gear_does_not_share_two_characters_with_a_divine_or_a_tactic():
    """FB-431：名器的名字（拿掉兵器字、防具字）不跟神器、本命兵器、戰法特技共用連著的兩個字；正式內容過得了。"""
    from tianxia import content as content_mod

    rc = real_content()
    problems: list[str] = []
    content_mod._validate_named_clash(rc, lambda ok, msg: problems.append(msg) if not ok else None)
    assert problems == []
    rid = next(r.id for r in rc.forge_secrets.values() if r.slot == "armor" and not r.divine)
    rc.forge_secrets[rid] = rc.forge_secrets[rid].model_copy(update={"name": "隕星鎧"})
    content_mod._validate_named_clash(rc, lambda ok, msg: problems.append(msg) if not ok else None)
    assert len(problems) == 1 and "隕星刀" in problems[0] and "隕星" in problems[0]
    assert content_mod._named_stem("寒淵拳套", "weapon", "拳腳") == "寒淵"  # 拳套不算撞字
