"""意境合成改版（Config.craft；設計稿 https://claude.ai/artifact/G4m44hK3At7x2bmqoAbceu ，Joy 2026-11-10「好」）的規則：
主料定一般功效、輔料定型、火候帶真意、兩個小驚喜、合璧成神三條（齊了自動用掉兩份；Joy 2026-11-10「傾注好複雜」拿掉傾注）、熟、化入、開季蓋章。規則在 tianxia/fusion.py「意境合成改版」那一段。"""
import pytest

from conftest import real_content

from tianxia import fusion, insight_fx
from tianxia.state import InsightFx, new_game_state
from tianxia.world_state import stamp_season

pytestmark = pytest.mark.whole_content


@pytest.fixture
def rc():
    c = real_content()
    c.config.craft.enabled = True
    return c


@pytest.fixture
def me(rc):
    s = new_game_state(rc, "韓霜")
    s.world.craft_v2 = True
    s.player.stats["xinde"] = 500
    s.player.stamina = 500
    s.player.location = "luoyang" if "luoyang" in rc.locations else s.player.location
    return s


def give(s, piece, attribute_key, layers, quality="中品"):
    if piece not in s.player.insights:
        s.player.insights.append(piece)
    s.player.insight_fx[piece] = InsightFx(quality=quality, general={attribute_key: layers})


def no_luck(rc):
    rc.config.craft.near_chance = 0.0
    rc.config.craft.bonus_chance = 0.0


def test_the_switch_needs_both_the_setting_and_the_season_stamp(rc, me):
    assert fusion.v2_on(rc, me)
    me.world.craft_v2 = False
    assert not fusion.v2_on(rc, me)  # 正在跑的季沒蓋章：照舊
    me.world.craft_v2 = True
    rc.config.craft.enabled = False
    assert not fusion.v2_on(rc, me)  # 主機的開關關掉：一律照舊
    stamp_season(me.world, rc)
    assert me.world.craft_v2 is False
    rc.config.craft.enabled = True
    stamp_season(me.world, rc)
    assert me.world.craft_v2 is True


def test_the_left_slot_is_the_main_ingredient_and_fixes_the_general(rc, me, world):
    no_luck(rc)
    give(me, "huo", "剛", 1)
    give(me, "feng", "快", 1)
    a, _ = fusion.merge(me, rc, world, None, "huo", "feng", proposed=("焚風", ""))
    b, _ = fusion.merge(me, rc, world, None, "feng", "huo", proposed=("焚風", ""))
    assert a.attribute == b.attribute == "陽"
    assert list(me.player.insight_fx[a.id].general) == ["陽"]  # 主剛 → 乘勝
    assert list(me.player.insight_fx[b.id].general) == ["zhaoyang"]  # 主快 → 朝陽


def test_the_right_slot_is_the_aux_and_fixes_the_form(rc, me, world):
    """輔料定型（Joy 2026-11-10 決策卡）：右格那份最深的一般功效對到攻守變心；主輔對調換一型，同一配方換了輔料就換型。"""
    no_luck(rc)
    give(me, "huo", "剛", 3)
    give(me, "feng", "快", 3)
    first, msgs = fusion.merge(me, rc, world, None, "huo", "feng", proposed=("焚風", ""))
    key = fusion.merge_key("huo", "feng")
    fx = me.player.insight_fx[first.id]
    assert fx.grand == "he_yang_bian"  # 火候 3＋3＝6 帶真意；輔料是先手（快）→ 陽 × 變
    assert me.player.fusion_book[key].form == "變" and me.player.fusion_book[key].uses == 1
    give(me, "huo", "剛", 3)
    give(me, "feng", "快", 3)
    swapped, _ = fusion.merge(me, rc, world, None, "feng", "huo")
    assert me.player.insight_fx[swapped.id].grand == "he_yang_gong"  # 輔料換成破甲（剛）→ 攻
    give(me, "huo", "剛", 3)
    me.player.insight_fx["feng"] = InsightFx(quality="中品", general={"快": 1, "lueying": 3})
    deep, _ = fusion.merge(me, rc, world, None, "huo", "feng")
    assert me.player.insight_fx[deep.id].grand == "he_yang_shou"  # 輔料最深的是掠影 → 守


def test_every_pair_path_reaches_all_four_forms_by_swapping(rc):
    for path, (x, y) in fusion.PAIR_ORDER.items():
        table = fusion.FORM_BY_AUX[path]
        assert sorted(table.values()) == sorted(fusion.FORMS)
        ids = {"剛": "chenjin", "快": "lueying", "柔": "huilan", "慢": "shouzhuo"}
        assert set(table) == {x, ids[x], y, ids[y]}


def test_the_preview_shows_the_form_from_the_aux(rc, me, world):
    give(me, "huo", "剛", 3)
    give(me, "feng", "快", 3)
    look = fusion.v2_preview(me, rc, world, "huo", "feng")
    assert look["form"] == "變" and look["aux"] and look["grand"] == fusion.UNSEEN and "ask_intent" not in look


def test_without_the_three_conditions_a_true_meaning_stops_short_of_god(rc, me, world):
    no_luck(rc)
    give(me, "huo", "剛", 3)
    give(me, "feng", "快", 3)
    made, _ = fusion.merge(me, rc, world, None, "huo", "feng", proposed=("焚風", ""))
    fx = me.player.insight_fx[made.id]
    assert fx.grand is not None and max(fx.general.values()) == 1 and insight_fx.look(fx) != "神"  # 不在地方：平常合，一重帶真意
    assert "huo" in me.player.insights and "feng" in me.player.insights  # 平常合：兩份都留著


def test_low_heat_gives_no_true_meaning_and_near_heat_can_fill_itself(rc, me, world):
    no_luck(rc)
    give(me, "huo", "剛", 1)
    give(me, "feng", "快", 2)
    plain, _ = fusion.merge(me, rc, world, None, "huo", "feng", proposed=("焚風", ""))
    assert me.player.insight_fx[plain.id].grand is None  # 火候 3
    give(me, "huo", "剛", 3)
    give(me, "feng", "快", 2)
    near, _ = fusion.merge(me, rc, world, None, "huo", "feng")
    assert me.player.insight_fx[near.id].grand is None  # 火候 5，自足機會 0
    rc.config.craft.near_chance = 1.0
    filled, msgs = fusion.merge(me, rc, world, None, "huo", "feng")
    assert me.player.insight_fx[filled.id].grand is not None and any("自己湊足" in m for m in msgs)


def test_the_bonus_general_never_makes_god(rc, me, world):
    rc.config.craft.near_chance = 0.0
    rc.config.craft.bonus_chance = 1.0
    give(me, "huo", "剛", 1)
    give(me, "feng", "快", 1)
    made, msgs = fusion.merge(me, rc, world, None, "huo", "feng", proposed=("焚風", ""))
    assert len(me.player.insight_fx[made.id].general) == 2 and any("意外之喜" in m for m in msgs)
    give(me, "huo", "剛", 3)
    give(me, "feng", "快", 3)
    grand, _ = fusion.merge(me, rc, world, None, "huo", "feng")
    fx = me.player.insight_fx[grand.id]
    assert fx.grand is not None and len(fx.general) == 1 and insight_fx.look(fx) != "神"


def test_three_conditions_make_god_in_one_furnace_and_use_both(rc, me, world, monkeypatch):
    no_luck(rc)
    give(me, "huo", "剛", 3)
    give(me, "feng", "快", 3)
    me.player.location = "changshe"  # 陽最濃之地之一（此地最濃是剛或快，剛快兩路都悟得到）
    assert fusion.strongest_here(me, rc, "陽")
    monkeypatch.setattr(fusion, "secret_met", lambda *a: True)
    conds = fusion.god_conditions(me, rc, world, "huo", "feng", "陽")
    assert all(conds.values()) and list(conds) == ["layers", "place", "secret"]
    assert fusion.god_ready(me, rc, world, "huo", "feng")
    made, msgs = fusion.merge(me, rc, world, None, "huo", "feng", proposed=("焚風", ""))
    fx = me.player.insight_fx[made.id]
    assert fx.general == {"陽": 3} and fx.grand == "he_yang_bian" and insight_fx.look(fx) == "神"
    assert any("合璧成神" in m for m in msgs)
    assert "huo" not in me.player.insights and "feng" not in me.player.insights  # 成神那一爐兩份都用掉


def test_missing_one_condition_is_an_ordinary_merge(rc, me, world, monkeypatch):
    no_luck(rc)
    give(me, "huo", "剛", 3)
    give(me, "feng", "快", 3)
    me.player.location = "changshe"
    monkeypatch.setattr(fusion, "secret_met", lambda *a: False)  # 秘訣沒對上
    made, _ = fusion.merge(me, rc, world, None, "huo", "feng", proposed=("焚風", ""))
    assert insight_fx.look(me.player.insight_fx[made.id]) != "神" and "huo" in me.player.insights


def test_the_season_secret_is_one_per_path_and_a_hint_needs_mastery(rc, me, world):
    for path in fusion.PAIR_ORDER:
        assert fusion.secret_of(world, path) in fusion.SECRETS
    key = fusion.merge_key("huo", "feng")
    assert fusion.secret_hint(me, rc, world, key, "陽") is None
    from tianxia.state import FusionNote

    me.player.fusion_book[key] = FusionNote(form="攻", uses=rc.config.craft.hint_at)
    assert fusion.secret_hint(me, rc, world, key, "陽") == fusion.SECRET_HINTS[fusion.secret_of(world, "陽")]


def test_no_god_in_discussion_or_switched_off_seasons(rc, me, world, monkeypatch):
    give(me, "huo", "剛", 3)
    give(me, "feng", "快", 3)
    me.player.location = "changshe"
    monkeypatch.setattr(fusion, "secret_met", lambda *a: True)
    assert fusion.god_ready(me, rc, world, "huo", "feng")
    partner = fusion.Partner(lent="feng", name="乙", price=(3, 3))
    assert not fusion.god_ready(me, rc, world, "huo", "feng", partner)
    me.world.craft_v2 = False
    assert not fusion.god_ready(me, rc, world, "huo", "feng")


def test_deepening_follows_heat_and_never_reaches_god_on_a_compound_path(rc, me, world):
    no_luck(rc)
    give(me, "huo", "剛", 1)
    give(me, "feng", "快", 1)
    made, _ = fusion.merge(me, rc, world, None, "huo", "feng", proposed=("焚風", ""))
    second, _ = fusion.merge(me, rc, world, None, "huo", "feng")
    me.player.insight_fx[made.id] = InsightFx(quality="上品", general={"陽": 3})
    me.player.insight_fx[second.id] = InsightFx(quality="中品", general={"陽": 2})
    kept, msgs = fusion.merge(me, rc, world, None, made.id, second.id)
    fx = me.player.insight_fx[kept.id]
    assert fx.grand is not None  # 火候 3＋2＋上品 1＝6：揣摩照火候帶真意，不擲
    assert insight_fx.look(fx) == "珍" and max(fx.general.values()) == 2  # 合成路：神品只從合璧成神來


def test_infusing_turns_weak_pieces_into_layers(rc, me, world):
    give(me, "feng", "快", 1)
    give(me, "feng~2", "快", 1)  # 凡：1 點
    give(me, "feng~3", "快", 2)  # 佳：2 點
    ok, lines = fusion.infuse(me, rc, world, "feng", ["feng~2", "feng~3"])
    assert ok and me.player.insight_fx["feng"].general == {"快": 2}
    assert "feng~2" not in me.player.insights and "feng~3" not in me.player.insights
    assert me.player.fusion_yun.get("feng", 0) == 0
    give(me, "feng~2", "快", 1)
    ok, lines = fusion.infuse(me, rc, world, "feng", ["feng~2"])
    assert ok and me.player.fusion_yun["feng"] == 1 and any("再 2 點" in m for m in lines)


def test_infusing_refuses_other_paths_true_meanings_and_slotted_pieces(rc, me, world):
    give(me, "feng", "快", 1)
    give(me, "huo", "剛", 1)
    assert fusion.infuse_problem(me, rc, world, "feng", ["huo"]) is not None  # 不同路只能熔
    give(me, "feng~2", "快", 1)
    me.player.insight_fx["feng~2"].grand = "liuguang"
    assert fusion.infuse_problem(me, rc, world, "feng", ["feng~2"]) is not None  # 帶真意化不得
    me.player.insight_fx["feng~2"].grand = None
    me.world.craft_v2 = False
    assert fusion.infuse_problem(me, rc, world, "feng", ["feng~2"]) is not None  # 改版沒開


def test_every_path_and_form_has_a_merged_true_meaning(rc):
    for path in fusion.PAIR_ORDER:
        for form in fusion.FORMS:
            gid = fusion.grand_for(rc, path, form)
            assert gid.startswith("he_") and insight_fx.grand(rc, gid).attribute == path
    assert fusion.grand_for(rc, "剛", "攻") == "bengshan"  # 基本四路照原本的真意


def _bot_game(rc, world):
    import random as _r

    from tianxia.engine import Game

    rc.config.auto_open_first_season = True  # 真實內容預設要管理者開季：籌備中什麼都按不下去
    game = Game.new(rc, "韓霜", rng=_r.Random(0), world=world)
    game.state.world.craft_v2 = True
    game.state.player.stamina = 500
    game.state.player.stats["xinde"] = 500
    return game


def test_the_bot_forges_a_ready_pair_and_holds_it_until_the_place_is_right(rc, world, monkeypatch):
    import random as _r

    from tianxia.features.craft import bots

    no_luck(rc)
    game = _bot_game(rc, world)
    give(game.state, "huo", "剛", 3)
    give(game.state, "feng", "快", 3)
    give(game.state, "shui", "柔", 1)
    monkeypatch.setattr(fusion, "secret_met", lambda *a: True)
    game.state.player.location = "luoyang"
    assert not fusion.strongest_here(game.state, rc, "陽")
    plan = bots.pick_forge(game, _r.Random(0), merge_share=1.0)
    assert plan is None or set(plan.insight_ids) != {"huo", "feng"}  # 地方不對：這一對留著
    game.state.player.location = "changshe"
    plan = bots.pick_forge(game, _r.Random(0), merge_share=1.0)
    assert plan is not None and set(plan.insight_ids) == {"huo", "feng"}
    from tianxia import bot_base
    from tianxia.bot_policy import apply_job

    slot = bot_base.NamingSlot(open=True)
    bots._forge(game, plan, slot)  # 首創的一爐：開單交給假人程式取名
    assert slot.job is not None
    assert any("合璧成神" in m for m in apply_job(game, slot.job, ("燼風", "火借風勢")))
    made = [i for i in game.state.player.insights if game.state.player.insight_fx[i].grand and insight_fx.look(game.state.player.insight_fx[i]) == "神"]
    assert made and "huo" not in game.state.player.insights


def test_the_bot_infuses_plain_pieces_into_the_deepest_one(rc, world):
    from tianxia.features.craft import bots

    game = _bot_game(rc, world)
    give(game.state, "feng", "快", 2)
    give(game.state, "feng~2", "快", 1)
    give(game.state, "feng~3", "快", 1)
    give(game.state, "feng~4", "快", 1)  # 三份凡品＝3 點：加一重
    bots.infuse_spare(game)
    assert game.state.player.insights == ["feng"] and game.state.player.insight_fx["feng"].general == {"快": 3}
    game.state.world.craft_v2 = False
    give(game.state, "feng~2", "快", 1)
    assert bots.infuse_spare(game) == [] and "feng~2" in game.state.player.insights
