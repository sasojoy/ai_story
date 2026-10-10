"""兵器第二批：自己打造（docs/superpowers/specs/2026-10-09-兵器-design.md 4.2～4.4、4.7、4.7.1；
計畫 docs/superpowers/plans/2026-10-10-兵器-2-自己打造.md）。"""
from __future__ import annotations

import random

import pytest

from conftest import real_content
from tianxia import team, weapons
from tianxia.models import WEAPON_KINDS
from tianxia.state import Weapon


def _on(content):
    content.config.weapons.enabled = True
    return content


def _blade(kind="劍", attribute="柔", tier=1, quality="下品", edge=100, wid="兵:1", name="試刃"):
    return Weapon(id=wid, name=name, kind=kind, attribute=attribute, tier=tier, quality=quality, edge=edge)


def _game(content, world, name="試劍", art="sword"):
    from tianxia import rules
    from tianxia.engine import Game
    game = Game.new(content, name, rng=random.Random(0), world=world)
    game.client = None
    rules.learn_skill(game.state, content, art)
    return game


def _town(content, world, silver=200, name="試劍"):
    """在測試內容的城鎮（town：標籤城鎮、沒寫素材，當地鐵匠的屬性是剛），身上那門是流雲劍（柔・劍）。"""
    _on(content)
    game = _game(content, world, name=name)
    p = game.state.player
    p.location, p.stamina, p.stats["silver"] = "town", 100.0, silver
    p.member.wugong_id = "sword"
    game.sync(0.0)
    return game


def _ids(game):
    return {o.id: o for o in game.options(odds=False)}


def _art(game, content, world):
    return team.player_art(game.state, content, world, game.state.player.member.wugong_id)


# ── Task 1：拆解先問一次（FB-125）──

def test_rack_rows_carry_the_grade_and_a_dismantle_question(content, world):
    game = _town(content, world)
    p = game.state.player
    p.weapon = _blade()
    p.rack = [_blade(kind="刀", attribute="剛", tier=2, quality="中品", wid="兵:2", name="厚背刀")]
    data = weapons.rows(game.state, content, world, _art(game, content, world))
    assert data["rack"][0]["grade"] == "二階中品"
    assert data["rack"][0]["confirm"] == "把【厚背刀】（二階中品）拆成玄鋼骨×1？拆掉就沒了。"
    assert data["worn"]["grade"] == "一階下品" and data["worn"]["confirm"] == ""  # 身上那把不能拆，沒有問句


def test_smith_dismantle_buttons_ask_first_with_their_own_yes_word(content, world):
    game = _town(content, world)
    p = game.state.player
    p.weapon = _blade()
    p.rack = [_blade(kind="刀", attribute="剛", wid="兵:2", name="厚背刀")]
    game.choose("act:smith")
    opts = _ids(game)
    assert opts["smith:dismantle:兵:2"].confirm == "把【厚背刀】（一階下品）拆成精鐵砂×1？拆掉就沒了。"
    assert opts["smith:dismantle:兵:2"].confirm_yes == weapons.DISMANTLE_YES == "拆掉"
    assert all(o.confirm == "" for oid, o in opts.items() if not oid.startswith("smith:dismantle:"))
    game.choose("smith:dismantle:兵:2")  # 問一次是網頁的事：引擎收到照拆（機器人、腳本都這樣走）
    assert p.rack == [] and p.materials == {"gang_1": 1}


# ── Task 2：兵器配方的資料與資料庫第 4 版 ──

from tianxia.martial_arts import Insight, generate_from_name  # noqa: E402
from tianxia.sqlite_world import open_world  # noqa: E402
from tianxia.state import WeaponRecipe  # noqa: E402


@pytest.fixture
def store(tmp_path):
    return open_world(tmp_path / "w.db")


def _recipe(name="寒星劍", key="兵|劍|gang_1+kuai_1", creator="甲"):
    return WeaponRecipe(name=name, key=key, kind="劍", attribute="陽", tier=1, main="gang_1", aux="kuai_1",
                        creator=creator, creator_shown=creator)


def test_weapon_recipe_id_is_its_name_and_round_trips():
    r = _recipe()
    assert r.id == "寒星劍"
    assert WeaponRecipe.model_validate_json(r.model_dump_json()) == r


def test_the_first_weapon_recipe_claim_wins_and_later_ones_read_it(store):
    first = _recipe()
    assert store.claim_weapon_recipe(first.key, first) == (first, True)
    got, is_first = store.claim_weapon_recipe(first.key, _recipe(name="霜鳴劍", creator="乙"))
    assert is_first is False and got.name == "寒星劍" and got.creator == "甲"
    assert store.lookup_weapon_recipe(first.key) == first
    assert store.lookup_weapon_recipe("兵|劍|kuai_1+gang_1") is None  # 主輔對調是另一個配方
    assert store.is_skill_name_taken("霜鳴劍") is False  # 沒登記上的名字不佔名字空間


def test_weapon_recipe_names_share_the_namespace_with_arts_and_insights(store):
    store.claim_skill_name(generate_from_name("寒星劍", "武學", "寒星劍"))
    assert store.claim_weapon_recipe("兵|劍|gang_1+kuai_1", _recipe()) == (None, False)  # 武學用掉的名字
    other = _recipe(name="霜鳴劍", key="兵|劍|gang_1+gang_1")
    assert store.claim_weapon_recipe(other.key, other) == (other, True)
    assert store.is_skill_name_taken("霜鳴劍") is True
    assert store.claim_skill_name(generate_from_name("霜鳴劍", "武學", "霜鳴劍")) is False  # 反過來也擋
    got, first = store.claim_insight_recipe("feng+huo", Insight(id="霜鳴劍", name="霜鳴劍", attribute="陽"))
    assert (got, first) == (None, False)
    clash = _recipe(name="霜鳴劍", key="兵|刀|gang_1+gang_1")
    assert store.claim_weapon_recipe(clash.key, clash) == (None, False)  # 兩個配方不能同名


def test_weapon_recipes_are_per_season(store, content):
    content.config.auto_open_first_season = True
    store.seed_first_season(content)
    r = _recipe()
    store.claim_weapon_recipe(r.key, r)
    store.mutate_season(lambda season: setattr(season, "ended", True))
    assert store.next_season(content, now=1.0)
    assert store.lookup_weapon_recipe(r.key) is None
    with store.db.snapshot() as conn:  # 換季不刪資料：上一季的配方留著
        assert conn.execute("SELECT season FROM gear_recipes WHERE key = ?", (r.key,)).fetchone()["season"] == 1
    again = _recipe(creator="乙")
    assert store.claim_weapon_recipe(r.key, again) == (again, True)  # 新的一季：同一個配方別人首創、名字也能再用


# ── Task 3：打造的規則 ──

from tianxia import smithing  # noqa: E402


def _forger(content, world, silver=200, name="試劍"):
    """在城鎮、悟性 5（不加不扣）、背包：精鐵砂（剛一階）×3、玄鋼骨（剛二階）×2、驚羽（快一階）×2。"""
    game = _town(content, world, silver=silver, name=name)
    p = game.state.player
    p.stats["wis"] = 5
    p.materials = {"gang_1": 3, "gang_2": 2, "kuai_1": 2}
    return game


def test_recipe_key_keeps_main_and_aux_apart():
    assert weapons.recipe_key("劍", "gang_1", "kuai_1") == "兵|劍|gang_1+kuai_1"
    assert weapons.recipe_key("劍", "kuai_1", "gang_1") != weapons.recipe_key("劍", "gang_1", "kuai_1")
    assert weapons.recipe_parts("兵|劍|gang_1+kuai_1") == ("劍", "gang_1", "kuai_1")
    assert weapons.recipe_parts("兵|拳腳|gang_1+gang_1") == ("拳腳", "gang_1", "gang_1")
    assert weapons.recipe_parts("融|sword+feng") is None and weapons.recipe_parts(None) is None
    assert weapons.recipe_parts("鎧|gang_1+kuai_1") is None  # 前綴就是欄位：之後防具的配方鍵不是兵器的


def test_attribute_follows_merged_attribute_for_same_and_paired_attributes(content, world):
    """同屬性、四對（剛快、柔慢、快柔、剛慢）合出來的屬性跟主輔順序無關。"""
    assert smithing.attribute_of(world, content, "劍", "gang_1", "gang_1") == "剛"
    assert smithing.attribute_of(world, content, "劍", "gang_1", "kuai_1") == "陽"  # 剛＋快
    assert smithing.attribute_of(world, content, "劍", "kuai_1", "gang_1") == "陽"
    assert smithing.attribute_with(content, 3, "刀", "gang_2", "gang_1") == "剛"


def test_other_pairs_follow_the_recipe_seed_so_swapping_main_and_aux_can_differ():
    """剛＋柔、快＋慢不在四對裡、也不同屬性：照「天機|配方鍵」的雜湊從兩者挑一個。主輔對調是另一個配方鍵（4.4：主輔不交換），
    挑到的可能不一樣。測試內容只有剛與快，這裡用正式內容的柳絲綿（rou_1）；天機 0 時這一組剛好不一樣（照 sha256 算好的，
    配方鍵前綴是「兵|」，前綴或種子的寫法改了要重算）。"""
    rc = real_content()
    assert smithing.attribute_with(rc, 0, "劍", "gang_1", "rou_1") == "剛"
    assert smithing.attribute_with(rc, 0, "劍", "rou_1", "gang_1") == "柔"


def test_tier_and_price_follow_the_main_material(content):
    assert smithing.tier_of(content, "gang_2") == 2 and smithing.tier_of(content, "kuai_1") == 1
    assert [smithing.price(content, t) for t in (1, 2, 3)] == [20, 60, 150]


def test_forge_problem_reasons(content, world):
    game = _forger(content, world)
    s, p = game.state, game.state.player
    p.materials = {"gang_1": 1, "kuai_1": 1}
    assert smithing.forge_problem(s, content, "劍", "gang_1", "kuai_1") is None
    assert smithing.forge_problem(s, content, "斧", "gang_1", "kuai_1") == "沒有這種兵器"
    assert smithing.forge_problem(s, content, "劍", "gang_1", "nope") == "沒有這種素材"
    assert smithing.forge_problem(s, content, "劍", "gang_1", "gang_1") == "精鐵砂不夠（要 2 個）"  # 主輔同一種要兩個
    assert smithing.forge_problem(s, content, "劍", "gang_2", "gang_1") == "玄鋼骨不夠（要 1 個）"
    p.stats["silver"] = 5
    assert smithing.forge_problem(s, content, "劍", "gang_1", "kuai_1") == "還差 15 兩"
    p.stats["silver"] = 200
    p.weapon = _blade()
    p.rack = [_blade(wid=f"兵:{i + 2}") for i in range(content.config.weapons.rack_cap)]
    assert smithing.forge_problem(s, content, "劍", "gang_1", "kuai_1") == weapons.RACK_FULL
    p.rack = []
    p.location = "lake"
    assert smithing.forge_problem(s, content, "劍", "gang_1", "kuai_1") == weapons.NOT_HERE


def test_new_weapon_can_carry_its_recipe(content, world):
    game = _forger(content, world)
    w = weapons.new_weapon(game.state, name="寒星劍", kind="劍", attribute="陽", tier=1, quality="中品", recipe="兵|劍|gang_1+kuai_1")
    assert w.recipe == "兵|劍|gang_1+kuai_1" and w.id.startswith("兵:")
    assert weapons.new_weapon(game.state, name="厚背刀", kind="刀", attribute="剛", tier=1, quality="下品").recipe is None


# ── Task 4：品質擲骰 ──

from tianxia import fusion  # noqa: E402

KEY_SWORD_YANG = "兵|劍|gang_1+kuai_1"


def test_plain_same_tier_odds_start_from_fifty_thirty_twenty_and_add_the_aux(content, world):
    game = _forger(content, world)
    odds = smithing.forge_odds(game.state, content, world, "劍", "gang_1", "kuai_1")
    assert odds.odds == {"下品": 46.0, "中品": 32.0, "上品": 22.0}  # 同階輔料 +4
    assert odds.reasons == ("輔料壓得住主料",)


def test_a_lower_tier_aux_drags_the_odds_down(content, world):
    game = _forger(content, world)
    odds = smithing.forge_odds(game.state, content, world, "劍", "gang_2", "kuai_1")
    assert odds.odds == {"下品": 58.0, "中品": 26.0, "上品": 16.0}  # 輔料低一階 −8
    assert odds.reasons == ("輔料壓不住主料",)


def test_practice_adds_up_to_a_cap(content, world):
    game = _forger(content, world)
    game.state.player.forge_counts = {KEY_SWORD_YANG: 3}
    odds = smithing.forge_odds(game.state, content, world, "劍", "gang_1", "kuai_1")
    assert odds.odds == {"下品": 40.0, "中品": 35.0, "上品": 25.0}  # 熟手 +6、輔料 +4
    assert odds.reasons == ("這個配方你打得順手", "輔料壓得住主料")
    game.state.player.forge_counts = {KEY_SWORD_YANG: 100}
    assert smithing.forge_odds(game.state, content, world, "劍", "gang_1", "kuai_1").odds == {"下品": 36.0, "中品": 37.0, "上品": 27.0}


def test_wisdom_pushes_the_top_grade_up(content, world):
    game = _forger(content, world)
    plain = smithing.forge_odds(game.state, content, world, "劍", "gang_1", "kuai_1")
    game.state.player.stats["wis"] = 12
    sharp = smithing.forge_odds(game.state, content, world, "劍", "gang_1", "kuai_1")
    assert sharp.odds["上品"] > plain.odds["上品"] and sharp.odds["下品"] < plain.odds["下品"]


def test_setting_is_off_in_the_fixture_and_on_in_real_content(content, world):
    game = _forger(content, world)
    game.state.player.seclusion_done = game.state.world.time
    assert smithing.setting_points(game.state, content, "剛") == []
    q = real_content().config.weapons.quality
    assert (q.terrain, q.battlefield, q.calm) == (10, 10, 8) and q.setting_good


def test_terrain_battlefield_and_calm(content, world, monkeypatch):
    game = _forger(content, world)
    q = content.config.weapons.quality
    q.terrain, q.battlefield, q.calm = 10, 10, 8
    monkeypatch.setattr(fusion, "terrain_here", lambda state, content, attribute: attribute == "剛")  # 當作此地探索悟得到剛的意境
    assert smithing.setting_points(game.state, content, "剛") == [("terrain", 10)]
    assert smithing.setting_points(game.state, content, "陽") == []
    monkeypatch.setattr(fusion, "battlefield_here", lambda state, content: True)
    assert smithing.setting_points(game.state, content, "陽") == []  # 戰場只算打出剛的
    game.state.player.seclusion_done = game.state.world.time
    assert smithing.setting_points(game.state, content, "剛") == [("terrain", 10), ("battlefield", 10)]  # 最多兩條
    assert smithing.setting_points(game.state, content, "陽") == [("calm", 8)]
    odds = smithing.forge_odds(game.state, content, world, "劍", "gang_1", "gang_1")
    assert odds.odds == {"下品": 26.0, "中品": 42.0, "上品": 32.0}  # 輔料 +4、地利 +10、戰場 +10
    q.setting_good = "爐火正旺。"
    assert smithing.setting_line(content, [("terrain", 10)]) == ["爐火正旺。"]
    assert smithing.setting_line(content, []) == []


def test_terrain_is_the_same_rule_as_fusion(content, world):
    """地利沿用合成那一套（附帶決定 b）：此地探索悟得到同屬性的意境才算，跟 fusion.setting_points 的地利同一個判斷。"""
    from tianxia import insights
    game = _forger(content, world)
    here = content.locations[game.state.player.location]
    gives = {content.insights[i].attribute for i in insights.explore_gives(here, content)}
    for attribute in ("剛", "柔", "快", "慢", "陽", "陰", "虛", "實"):
        assert fusion.terrain_here(game.state, content, attribute) == (attribute in gives)


def test_practice_counts_reset_with_a_new_season(content, world):
    from conftest import next_season
    game = _forger(content, world)
    game.state.player.forge_counts = {KEY_SWORD_YANG: 3}
    next_season(content, world, game)
    assert game.state.player.forge_counts == {}


def test_fuse_odds_are_unchanged_by_the_refactor(content, world):
    """合成的品質機率改走 odds_from_points 之後，數字一模一樣（同一個公式，只是 rule 與 base 改成參數）。"""
    from tianxia.martial_arts import Insight
    game = _forger(content, world)
    base = team.player_art(game.state, content, world, "sword")
    insight = Insight(id="風", name="風", attribute="快")
    odds = fusion.fuse_odds(game.state, content, "sword", base, insight)
    assert odds == fusion.odds_from_points(
        [*fusion._art_points(game.state, content, [("sword", base)]), ("insight", 0.0),
         ("attribute", fusion._attribute_points(content, base.attribute, "快"))],
        content.config.fuse_quality, content.config.fuse_quality_odds,
    )


# ── Task 5：開爐的取名、退路字表、首創名望回饋 ──

from tianxia import naming  # noqa: E402


def test_kind_problem_wants_this_kinds_word_and_no_other_kinds(content):
    assert weapons.kind_problem("劍", "寒星劍") is None
    assert weapons.kind_problem("槍", "裂雷矛") is None
    assert weapons.kind_problem("拳腳", "驚雷拳套") is None
    assert weapons.kind_problem("劍", "寒星") == weapons.KIND_MISSING
    assert weapons.kind_problem("劍", "寒星刀") == weapons.KIND_MISSING
    assert weapons.kind_problem("劍", "刀劍雙絕") == weapons.KIND_CLASH
    assert weapons.kind_problem("劍", "厚背劍") == weapons.SHOP_CLASH  # 鐵匠鋪架上的現成兵器名


def test_fallback_names_carry_the_weapon_word_and_are_stable(content):
    for kind in WEAPON_KINDS:
        for salt in range(naming.CLAIM_ATTEMPTS):
            name = weapons.fallback_name(content, weapons.recipe_key(kind, "gang_1", "kuai_1"), kind, salt=salt, tianji=1)
            assert name.endswith(weapons.NOUNS[kind]) and weapons.kind_problem(kind, name) is None
            assert naming.name_problem(name, content) is None
    assert weapons.fallback_name(content, "兵|劍|gang_1+kuai_1", "劍") == weapons.fallback_name(content, "兵|劍|gang_1+kuai_1", "劍")


def test_validate_checks_the_weapon_fallback_names(content):
    from tianxia.content import ContentError, validate
    content.craft_names.weapon = ["刀"]  # 「某刀劍」看起來是兩種兵器：載入當下就要報錯
    with pytest.raises(ContentError, match="craft_names.weapon 組出的兵器名"):
        validate(content)
    content.craft_names.weapon = []
    with pytest.raises(ContentError, match="craft_names.weapon 不能是空的"):
        validate(content)
    assert real_content().craft_names.weapon  # 正式內容載入時已經驗過每一個組合


def test_propose_drops_a_name_the_check_refuses(content):
    class Fake:
        timeout = 5

        def chat_structured(self, messages, model, **kwargs):
            return naming.NameReply(name="寒星刀", description="一句話。")

    assert naming.propose(Fake(), content, [], check=lambda n: weapons.kind_problem("劍", n)) == (None, "")
    assert naming.propose(Fake(), content, [], check=lambda n: None) == ("寒星刀", "一句話。")
    assert naming.recheck(content, ("寒星刀", "x"), check=lambda n: weapons.kind_problem("劍", n)) == (None, "")


def test_forge_request_opens_a_naming_order_only_for_a_new_recipe(content, world):
    game = _forger(content, world)
    req = smithing.forge_request(game.state, content, world, "劍", "gang_1", "kuai_1")
    assert req.kind == "weapon" and req.key == KEY_SWORD_YANG and req.choices == ()
    assert "精鐵砂" in req.messages[1]["content"] and "「劍」" in req.messages[1]["content"]
    assert req.check("寒星刀") == weapons.KIND_MISSING and req.check("寒星劍") is None
    game.state.player.stats["silver"] = 0
    assert smithing.forge_request(game.state, content, world, "劍", "gang_1", "kuai_1") is None  # 打不成的不開單


def test_first_forge_registers_the_recipe_with_the_fallback_name_and_charges(content, world):
    game = _forger(content, world)
    s = game.state
    weapon, msgs = smithing.forge(s, content, world, None, "劍", "gang_1", "kuai_1", rng=random.Random(0))
    assert weapon.name == weapons.fallback_name(content, KEY_SWORD_YANG, "劍", tianji=world.read().tianji)  # 沒有模型：退路字表
    assert (weapon.kind, weapon.attribute, weapon.tier, weapon.recipe) == ("劍", "陽", 1, KEY_SWORD_YANG)
    assert weapon.quality in ("下品", "中品", "上品")
    assert s.player.weapon is weapon  # 手上空著：直接拿在手上
    assert s.player.materials == {"gang_1": 2, "gang_2": 2, "kuai_1": 1} and s.player.stats["silver"] == 180
    assert s.player.forge_counts == {KEY_SWORD_YANG: 1}
    recipe = world.lookup_weapon_recipe(KEY_SWORD_YANG)
    assert recipe.name == weapon.name and recipe.creator == s.player.name and recipe.creator_shown == s.player.name
    assert any(smithing.FIRST_LINE in m for m in msgs)
    assert "銀兩 -20" in msgs and "精鐵砂 -1" in msgs and "驚羽 -1" in msgs


def test_a_proposed_name_is_rechecked_and_registered(content, world):
    game = _forger(content, world)
    weapon, _ = smithing.forge(game.state, content, world, None, "劍", "gang_1", "kuai_1",
                               proposed=("「寒星劍」", "劍身映著寒光。"), rng=random.Random(0))
    assert weapon.name == "寒星劍"
    assert world.lookup_weapon_recipe(KEY_SWORD_YANG).note == "劍身映著寒光。"


@pytest.mark.parametrize("proposed", ["寒星刀", "寒星", "厚背劍"])
def test_a_proposed_name_for_another_weapon_kind_falls_back_to_the_table(content, world, proposed):
    game = _forger(content, world)
    weapon, _ = smithing.forge(game.state, content, world, None, "劍", "gang_1", "kuai_1",
                               proposed=(proposed, "說明"), rng=random.Random(0))
    assert weapon.name == weapons.fallback_name(content, KEY_SWORD_YANG, "劍", tianji=world.read().tianji)
    assert weapon.name.endswith("劍") and world.lookup_weapon_recipe(KEY_SWORD_YANG).note == ""


def test_a_second_smith_follows_the_registered_recipe_without_naming(content, world, monkeypatch):
    first = _forger(content, world, name="甲鐵匠")
    smithing.forge(first.state, content, world, None, "劍", "gang_1", "kuai_1", rng=random.Random(0))
    registered = world.lookup_weapon_recipe(KEY_SWORD_YANG)
    second = _forger(content, world, name="乙鐵匠")
    asked = []
    monkeypatch.setattr(naming, "propose", lambda *a, **k: asked.append(1) or ("不該用", ""))
    assert smithing.forge_request(second.state, content, world, "劍", "gang_1", "kuai_1") is None  # 查表就好，不開單
    weapon, msgs = smithing.forge(second.state, content, world, object(), "劍", "gang_1", "kuai_1", rng=random.Random(1))
    assert asked == [] and weapon.name == registered.name
    assert any("甲鐵匠首創" in m for m in msgs)
    weapon, msgs = smithing.forge(first.state, content, world, None, "劍", "gang_1", "kuai_1", rng=random.Random(2))
    assert any(smithing.MINE_LINE in m for m in msgs)


def test_a_refused_forge_registers_nothing_and_charges_nothing(content, world):
    game = _forger(content, world, silver=5)
    weapon, msgs = smithing.forge(game.state, content, world, None, "劍", "gang_1", "kuai_1", rng=random.Random(0))
    assert weapon is None and msgs == ["（還差 15 兩。）"]
    assert world.lookup_weapon_recipe(KEY_SWORD_YANG) is None
    assert game.state.player.materials == {"gang_1": 3, "gang_2": 2, "kuai_1": 2} and game.state.player.forge_counts == {}


def test_following_someone_elses_recipe_echoes_with_the_forge_verb(content, world, monkeypatch):
    monkeypatch.setattr(fusion, "season_one", lambda *a, **k: True)
    first = _forger(content, world, name="甲鐵匠")
    smithing.forge(first.state, content, world, None, "劍", "gang_1", "kuai_1", rng=random.Random(0))
    name = world.lookup_weapon_recipe(KEY_SWORD_YANG).name
    second = _forger(content, world, name="乙鐵匠")
    smithing.forge(second.state, content, world, None, "劍", "gang_1", "kuai_1", rng=random.Random(0))
    entry = second.state.world.echoes[name]
    assert entry.creator == "甲鐵匠" and entry.followers == ["乙鐵匠"] and entry.name == f"【{name}】" and entry.made == "打"


def test_echo_delivery_says_forged_for_weapons(content, world):
    from tianxia import journal
    from tianxia.state import Echo
    game = _forger(content, world)
    game.state.world.echoes["寒星劍"] = Echo(creator=game.state.player.name, name="【寒星劍】", followers=["乙"], made="打")
    game._deliver_echoes()
    entry = game.state.journal[0]
    assert entry.title == journal.ECHO and "江湖上又有 1 人照著你首創的【寒星劍】打了出來。" in entry.lines


# ── Task 6：接進鐵匠鋪 ──

import contextlib  # noqa: E402
from unittest import mock  # noqa: E402

GO_SWORD_YANG = "smith:forge-go:劍:gang_1:kuai_1"


def _smithy(content, world, **kw):
    game = _forger(content, world, **kw)
    game.choose("act:smith")
    return game


def _at_go(content, world, **kw):
    game = _smithy(content, world, **kw)
    for oid in (smithing.OPEN, f"{smithing.KIND}劍", f"{smithing.MAIN}gang_1", f"{smithing.AUX}kuai_1"):
        game.choose(oid)
    return game


def test_the_forge_door_is_on_the_smith_menu_and_greys_out_with_a_reason(content, world):
    game = _smithy(content, world)
    assert _ids(game)[smithing.OPEN].enabled
    game.state.player.materials = {"gang_1": 1}
    door = _ids(game)[smithing.OPEN]
    assert not door.enabled and smithing.NOT_ENOUGH in door.label
    game.state.player.materials, game.state.player.stats["silver"] = {"gang_1": 2}, 3
    assert "還差 17 兩" in _ids(game)[smithing.OPEN].label


def test_the_forge_door_sits_between_wield_and_dismantle(content, world):
    game = _forger(content, world)
    p = game.state.player
    p.weapon = _blade(kind="刀")
    p.rack = [_blade(wid="兵:7", name="軟鋼劍")]
    game.choose("act:smith")
    ids = list(_ids(game))
    assert ids.index("smith:wield:兵:7") < ids.index(smithing.OPEN) < ids.index("smith:dismantle:兵:7")  # FB-125：換上與拆解不相鄰


def test_the_wizard_walks_kind_main_aux_then_go(content, world):
    game = _smithy(content, world)
    game.choose(smithing.OPEN)
    ids = list(_ids(game))
    assert ids[0] == f"{smithing.KIND}劍"  # 配得上身上武學的種類排第一
    assert {f"{smithing.KIND}{k}" for k in WEAPON_KINDS} <= set(ids) and smithing.CANCEL in ids and "smith:back" not in ids
    game.choose(f"{smithing.KIND}劍")
    mains = [i for i in _ids(game) if i.startswith(smithing.MAIN)]
    assert mains[0] == f"{smithing.MAIN}gang_2"  # 高階的排前面
    game.choose(f"{smithing.MAIN}gang_1")
    aux = _ids(game)[f"{smithing.AUX}kuai_1"]
    assert "→ 屬陽" in aux.label
    game.choose(aux.id)
    go = _ids(game)[GO_SWORD_YANG]
    assert go.enabled and "工錢 20 兩" in go.label and "下品 46%" in go.label and go.wait == smithing.FORGE_WAIT
    game.choose(go.id)
    p = game.state.player
    assert p.weapon is not None and p.weapon.recipe == KEY_SWORD_YANG
    assert p.smith_draft is None and p.picking_smith and smithing.OPEN in _ids(game)  # 打完回到鐵匠鋪的選單
    forged = [e for e in game.state.journal if e.title == smithing.FORGE_TITLE]
    assert len(forged) == 1 and any(p.weapon.name in line for line in forged[0].lines)  # 一爐一則紀錄


def test_each_forge_gets_its_own_entry_and_a_cancel_does_not_join_the_last_forge(content, world):
    """打開單子那一步另起一則（journal._mergeable_head 只看最新一則同不同標題）：連打兩爐是兩則；打開又不打了是第三則，
    不併進第二爐那一則。"""
    game = _at_go(content, world)
    game.choose(GO_SWORD_YANG)  # 第一爐
    for oid in (smithing.OPEN, f"{smithing.KIND}劍", f"{smithing.MAIN}gang_1", f"{smithing.AUX}kuai_1", GO_SWORD_YANG):
        game.choose(oid)  # 打完再按「打造兵器…」打第二爐
    forged = [e for e in game.state.journal if e.title == smithing.FORGE_TITLE]
    assert len(forged) == 2
    game.choose(smithing.OPEN)
    game.choose(smithing.CANCEL)
    forged = [e for e in game.state.journal if e.title == smithing.FORGE_TITLE]
    assert len(forged) == 3
    assert any(smithing.CANCELLED in line for line in forged[0].lines)  # 最新的一則是打開又不打了
    assert not any(smithing.CANCELLED in line for line in forged[1].lines)  # 第二爐那一則沒被併進去


def test_a_known_recipe_says_its_name_and_does_not_wait(content, world):
    game = _at_go(content, world)
    game.choose(GO_SWORD_YANG)
    name = world.lookup_weapon_recipe(KEY_SWORD_YANG).name
    for oid in (smithing.OPEN, f"{smithing.KIND}劍", f"{smithing.MAIN}gang_1", f"{smithing.AUX}kuai_1"):
        game.choose(oid)
    go = _ids(game)[GO_SWORD_YANG]
    assert f"【{name}】" in go.label and go.wait == ""


def test_undo_steps_back_and_cancel_returns_to_the_smith_menu(content, world):
    game = _smithy(content, world)
    for oid in (smithing.OPEN, f"{smithing.KIND}劍", f"{smithing.MAIN}gang_1"):
        game.choose(oid)
    game.choose(smithing.UNDO)
    assert game.state.player.smith_draft.main is None and any(i.startswith(smithing.MAIN) for i in _ids(game))
    game.choose(smithing.CANCEL)
    assert game.state.player.smith_draft is None and "smith:back" in _ids(game)
    assert game.state.player.materials == {"gang_1": 3, "gang_2": 2, "kuai_1": 2}  # 什麼都沒花


def test_a_second_press_of_the_same_forge_button_does_nothing(content, world):
    game = _at_go(content, world)
    game.choose(GO_SWORD_YANG)
    p = game.state.player
    before = (p.stats["silver"], dict(p.materials), len(p.rack) + (p.weapon is not None))
    assert game.choose(GO_SWORD_YANG) == ["（此刻無法這麼做。）"]
    assert (p.stats["silver"], p.materials, len(p.rack) + (p.weapon is not None)) == before


def test_aux_list_leaves_out_the_main_when_only_one_is_held(content, world):
    game = _smithy(content, world)
    p = game.state.player
    p.materials = {"gang_2": 1, "gang_1": 1}
    for oid in (smithing.OPEN, f"{smithing.KIND}劍", f"{smithing.MAIN}gang_2"):
        game.choose(oid)
    assert [i for i in _ids(game) if i.startswith(smithing.AUX)] == [f"{smithing.AUX}gang_1"]
    assert game.choose("smith:forge-go:劍:gang_2:gang_2") == ["（此刻無法這麼做。）"]  # 舊分頁的單子：不在選單上
    assert p.materials == {"gang_2": 1, "gang_1": 1} and p.stats["silver"] == 200


def test_leaving_the_smith_mid_way_starts_the_forge_over(content, world):
    game = _at_go(content, world)
    p = game.state.player
    p.location = "lake"
    game.sync(1.0)
    assert not p.picking_smith and p.smith_draft is None  # 人不在城鎮：鐵匠鋪收起來，單子一起清掉（存檔不留舊單子）
    p.location = "town"
    game.sync(2.0)
    game.choose("act:smith")
    assert p.smith_draft is None and smithing.OPEN in _ids(game)
    assert game.choose(GO_SWORD_YANG) == ["（此刻無法這麼做。）"]


def test_a_saved_draft_that_the_content_no_longer_supports_is_dropped_on_load(content, world):
    """存檔裡的單子指著內容已經沒有的素材（內容改版），或根本沒開著鐵匠鋪：存檔修補時清掉，選單不會因為查不到素材而丟錯。"""
    from tianxia.state import SmithDraft
    game = _smithy(content, world)
    p = game.state.player
    p.smith_draft = SmithDraft(kind="劍", main="gone_material")
    game._drop_stale_references()
    assert p.smith_draft is None and p.picking_smith and smithing.OPEN in _ids(game)
    p.smith_draft, p.picking_smith = SmithDraft(kind="劍"), False
    game._drop_stale_references()
    assert p.smith_draft is None


def test_choose_takes_a_name_prepared_outside_the_lock(content, world):
    game = _at_go(content, world)
    game.client = object()  # 有 client 才開單（伺服器上的 Game 一定有）
    req = game.smith_forge_request(GO_SWORD_YANG)
    assert req is not None and req.kind == "weapon" and req.key == KEY_SWORD_YANG
    assert game.smith_forge_request("smith:forge-go:劍:gang_1:gang_2") is None  # 不在選單上的單子不開
    game.client = None
    assert game.smith_forge_request(GO_SWORD_YANG) is None  # 沒有 client（假人鎖內的 Game）不開
    game.choose(GO_SWORD_YANG, proposed=("寒星劍", "劍身映著寒光。"))
    assert game.state.player.weapon.name == "寒星劍"


@pytest.fixture
def lock_events(monkeypatch):
    """記錄行動鎖「拿到、放掉」的順序（同 tests/test_server.py 的 lock_events）。"""
    from tianxia.sqlite_world import SqliteWorldStore
    events = []
    real = SqliteWorldStore.action_lock

    @contextlib.contextmanager
    def spy(self, timeout=None):
        with real(self, timeout):
            events.append("enter")
            yield
        events.append("exit")

    monkeypatch.setattr(SqliteWorldStore, "action_lock", spy)
    return events


@pytest.fixture
def server_ready(monkeypatch):
    """伺服器的兩支測試用（照 tests/test_server.py 的 season_already_open、fresh_server_memory、model_breaker_closed；那三個是
    test_server.py 自己的 autouse，這個檔沒有）。server.CONTENT 是正式內容，content/config.json 沒寫 auto_open_first_season
    （models.py 預設 False）：不打開的話 server.game_for 開出來的世界停在籌備中，smith_forge_request 的 _preparing() 讓 A 段回 None、
    B 段不叫模型，C 段的選單只剩 season:preparing，打造被拒。角色快取、登入狀態、排程那一份 Game、模型佇列、斷路器都是 server 的
    模組狀態，前後都清（不然 GAMES 裡留著上一個測試開在別的暫存資料庫上的 Game）。一定要在 server.game_for 之前生效：
    測試把它寫在參數裡（fixture 比測試本體先跑），不要在測試裡呼叫 _server_forger 之後才設。"""
    import server
    monkeypatch.setattr(server.CONTENT.config, "auto_open_first_season", True)
    monkeypatch.setattr(server, "_breaker_until", None, raising=False)

    def clear():
        for store in (server.LOGIN_FAILURES, server.SESSIONS, server.GAMES):
            store.clear()
        server.WORLD_GAME = None
        server.QUEUE = None  # 模型佇列：從關著開始（Config.llm_queue_slots 預設 0）

    clear()
    yield
    clear()


def _server_forger(name):
    """伺服器上這個角色唯一的那份 Game（照 tests/test_server.py::_forger）：站在起點的城鎮、單子挑好了拳套、存進資料庫（進鎖會重讀）。
    呼叫它的測試要帶 server_ready（季要開著、伺服器記憶體要清過）。"""
    import server
    from tianxia.characters import open_characters
    from tianxia.state import SmithDraft
    game = server.game_for(name)
    p = game.state.player
    p.materials, p.stats["silver"] = {"gang_1": 1, "kuai_1": 1}, 200
    p.picking_smith, p.smith_draft = True, SmithDraft(kind="拳腳", main="gang_1", aux="kuai_1")
    open_characters().save(game.state)
    return game


def _named(reply_name, events=None, game=None):
    from tianxia.ollama_client import OllamaClient

    def chat_structured(model, messages, response_model, **kwargs):
        if events is not None:
            events.append("generate")
            assert not game.world.db.writing()  # 鎖外：這個執行緒沒拿著寫入交易
        return naming.NameReply(name=reply_name, description="一句話。")

    return mock.patch.object(OllamaClient, "chat_structured", chat_structured)


GO_FIST = "smith:forge-go:拳腳:gang_1:kuai_1"


def test_a_new_weapon_recipe_is_named_outside_the_action_lock(server_ready, lock_events):
    import server
    from tianxia.characters import open_characters
    game = _server_forger("鍛刀人")
    lock_events.clear()
    with _named("驚雷拳套", lock_events, game):
        server.choose(game, GO_FIST)
    assert lock_events == ["enter", "exit", "generate", "enter", "exit"]  # 鎖內開單 → 鎖外取名 → 鎖內登記
    saved = open_characters().load("鍛刀人").player
    assert saved.weapon is not None and saved.weapon.name == "驚雷拳套"
    assert open_world().lookup_weapon_recipe(weapons.recipe_key("拳腳", "gang_1", "kuai_1")).name == "驚雷拳套"


def test_two_tabs_forging_the_same_order_charge_once(server_ready):
    import server
    from tianxia.characters import open_characters
    game = _server_forger("兩頁人")
    with _named("驚雷拳套"):
        first = server.prepare_smith_forge(game, GO_FIST)
        second = server.prepare_smith_forge(game, GO_FIST)  # 兩個分頁都走完 A、B
    server.act(game, lambda g: g.choose(GO_FIST, proposed=first))
    server.act(game, lambda g: g.choose(GO_FIST, proposed=second))
    saved = open_characters().load("兩頁人").player
    assert saved.stats["silver"] == 180 and saved.materials == {}
    assert len(saved.rack) + (saved.weapon is not None) == 1


# ── Task 7：淬煉 ──


def test_temper_uses_the_cheapest_material_at_or_above_the_weapon_tier(content, world):
    game = _smithy(content, world)
    p = game.state.player
    p.weapon = _blade(tier=2)  # 二階、柔，配身上的流雲劍（柔）
    p.materials = {"gang_1": 5, "gang_2": 1, "gang_3": 1}
    assert smithing.temper_material(game.state, content) == "gang_2"  # 一階不夠格；二階比三階便宜
    opt = _ids(game)[smithing.TEMPER]
    assert opt.enabled and "第 1/5 次" in opt.label and "玄鋼骨×1＋30 兩" in opt.label
    msgs = game.choose(smithing.TEMPER)
    assert p.weapon.tempers == 1 and p.materials == {"gang_1": 5, "gang_3": 1} and p.stats["silver"] == 170
    assert weapons.bonus(p.weapon, _art(game, content, world), content, world) == pytest.approx(0.10 + 0.01 + 0.05)
    assert any("淬" in m for m in msgs) and game.state.journal[0].title == smithing.TEMPER_TITLE


def test_a_tier_one_temper_costs_only_the_material(content, world):
    game = _smithy(content, world)
    p = game.state.player
    p.weapon, p.materials = _blade(), {"gang_1": 2}
    assert "精鐵砂×1）" in _ids(game)[smithing.TEMPER].label  # 一階不收錢，鈕上不寫兩
    game.choose(smithing.TEMPER)
    assert p.weapon.tempers == 1 and p.stats["silver"] == 200 and p.materials == {"gang_1": 1}


def test_temper_stops_at_five_and_refuses_without_a_fitting_material_or_silver(content, world):
    game = _smithy(content, world)
    p = game.state.player
    p.weapon, p.materials = _blade(), {"gang_1": 3}
    p.weapon.tempers = 5
    opt = _ids(game)[smithing.TEMPER]
    assert not opt.enabled and smithing.FULL in opt.label
    assert smithing.temper(game.state, content) == [f"（{smithing.FULL}。）"] and p.materials == {"gang_1": 3}
    p.weapon = _blade(tier=3)
    assert smithing.temper_problem(game.state, content) == "沒有三階以上的素材"
    p.weapon, p.materials, p.stats["silver"] = _blade(tier=2), {"gang_2": 1}, 10
    assert smithing.temper_problem(game.state, content) == "還差 20 兩"
    p.weapon = None
    assert smithing.TEMPER not in _ids(game)  # 空手沒有淬煉鈕
    p.weapon, p.location = _blade(), "lake"
    assert smithing.temper_problem(game.state, content) == weapons.NOT_HERE


# ── Task 8：畫面 ──


def test_rows_carry_tempers_and_the_recipe_text(content, world):
    game = _forger(content, world)
    smithing.forge(game.state, content, world, None, "劍", "gang_1", "kuai_1", rng=random.Random(0))
    p = game.state.player
    p.weapon.tempers = 2
    art = _art(game, content, world)
    row = weapons.rows(game.state, content, world, art)["worn"]
    assert row["tempers"] == 2 and row["temper_max"] == 5 and row["recipe"] == "精鐵砂＋驚羽"
    assert "淬煉 2 次" in weapons.card_line(game.state, content, world, art)
    p.weapon = _blade()
    row = weapons.rows(game.state, content, world, art)["worn"]
    assert row["recipe"] is None and row["tempers"] == 0
    assert "淬煉" not in weapons.card_line(game.state, content, world, art)
    assert weapons.recipe_text(content, "兵|劍|gang_1+gang_1") == "精鐵砂＋精鐵砂"
    assert weapons.recipe_text(content, None) is None


# ── Task 9：整季機器人會打造與淬煉、假人不打造 ──


def test_forge_plan_reaches_for_the_highest_tier_and_stops_once_it_has_one(content, world):
    game = _forger(content, world)
    s, p = game.state, game.state.player
    art = _art(game, content, world)
    assert smithing.forge_plan(s, content, world, art) == ("劍", "gang_2", "gang_2")  # 最高階、夠兩個就主輔同一種
    p.materials = {"gang_2": 1, "gang_1": 2, "kuai_1": 3}
    assert smithing.forge_plan(s, content, world, art) == ("劍", "gang_2", "kuai_1")  # 輔料挑低一階數量最多的
    p.rack = [_blade(tier=2, wid="兵:3", name="寒星劍")]
    p.rack[0].recipe = weapons.recipe_key("劍", "gang_2", "gang_2")
    assert smithing.forge_plan(s, content, world, art) is None  # 已經有一把同階、自己打的、配得上的
    p.rack = []
    p.stats["silver"] = 10
    assert smithing.forge_plan(s, content, world, art) is None  # 打不起


def test_better_in_rack_compares_the_bonus(content, world):
    game = _forger(content, world)
    p = game.state.player
    art = _art(game, content, world)
    p.weapon = _blade(attribute="剛")  # 剛剋柔：+5% −5% ＝ 0
    p.rack = [_blade(attribute="柔", wid="兵:2", name="軟劍")]  # 同屬性：+10%
    assert smithing.better_in_rack(game.state, content, world, art).id == "兵:2"
    p.weapon, p.rack = p.rack[0], [p.weapon]
    assert smithing.better_in_rack(game.state, content, world, art) is None


def test_visit_smith_forges_then_tempers_and_leaves(content, world):
    from tianxia import bot
    game = _forger(content, world, silver=30)  # 買不起架上的劍（40），打得起一爐一階（20）
    p = game.state.player
    p.materials = {"gang_1": 6}
    bot.visit_smith(game)
    assert p.weapon is not None and p.weapon.recipe == weapons.recipe_key("劍", "gang_1", "gang_1")
    assert p.weapon.tempers == 4 and p.materials == {} and p.stats["silver"] == 10  # 打一把用兩個，剩四個全拿去淬（一階不收錢）
    assert not p.picking_smith and p.smith_draft is None


def test_visit_smith_never_leaves_a_draft_open(content, world, monkeypatch):
    from tianxia import bot
    game = _forger(content, world)
    monkeypatch.setattr(smithing, "wizard_steps", lambda kind, main, aux: [smithing.OPEN, f"{smithing.KIND}{kind}"])  # 走到一半就停
    bot.visit_smith(game)
    assert not game.state.player.picking_smith and game.state.player.smith_draft is None


def test_server_bots_never_open_the_forge_or_temper(content, world):
    from tianxia import bot_policy
    from tianxia.state import BotProfile
    game = _smithy(content, world)
    game.state.player.weapon = _blade()
    profile = BotProfile(personality="普通", seed=1, faction="guan", season_number=1)
    scored = {o.id: bot_policy.score(game, o, profile) for o in game.options(odds=False)}
    assert scored[smithing.OPEN] is None and scored[smithing.TEMPER] is None
    game.choose(smithing.OPEN)
    scored = {o.id: bot_policy.score(game, o, profile) for o in game.options(odds=False)}
    assert scored[smithing.CANCEL] == 0.0  # 萬一停在單子上，只會按「不打了」
    assert all(v is None for k, v in scored.items() if k != smithing.CANCEL)
