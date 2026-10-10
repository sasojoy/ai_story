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
