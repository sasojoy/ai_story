"""合成（Joy 2026-10-21 之後煉製只剩意境＋意境 → 揣摩或複合意境）。
武學＋武學（blend）拿掉了；武學＋意境不再是合成（裝進槽：Game.slot_insight），爐裡放武學回 fusion.ART_IN_FURNACE。
那些測試一併刪除。這裡的 named／model_down／must_not_ask／other_player 給 test_secret_recipes、test_one_art 借用。"""
from unittest import mock

import pytest

from tianxia.state import InsightFx

from tianxia import insight_fx, arts as arts_mod
from tianxia import fusion, insights, library, naming, skillview, team
from tianxia.martial_arts import generate_from_name
from tianxia.state import new_game_state


def named(name, description="一句話說明。"):
    client = mock.Mock()
    client.chat_structured.return_value = naming.NameReply(name=name, description=description)
    return client


def model_down():
    client = mock.Mock()
    client.chat_structured.side_effect = RuntimeError("連不上")
    return client


class AskedTheModel(BaseException):
    """naming._ask 把模型呼叫丟出的所有 Exception 當成「這次沒拿到」吞掉（連 AssertionError 也是），所以「不該叫模型」的假 client
    要丟 _ask 接不住的東西：BaseException 不是 Exception，會一路穿到測試、測試才會真的失敗。"""


def must_not_ask():
    client = mock.Mock()
    client.chat_structured.side_effect = AskedTheModel("配方已經有了，不該再叫模型")
    return client


class Fixed:
    """rng.choices 永遠挑 pick 那一個。武學重構之後合成不擲品質了（blend 的 rng 不用）；留著給 test_secret_recipes 的打造那一段用。"""

    def __init__(self, pick):
        self.pick, self.weights = pick, None

    def choices(self, population, weights):
        self.weights = dict(zip(population, weights))
        return [self.pick]


@pytest.fixture
def ready(state):
    state.player.member.wugong_id = "basic_fist"
    state.player.insights = ["feng", "huo"]
    state.player.stats["xinde"] = 100
    return state


def other_player(content, insights=("feng",)):
    other = new_game_state(content, "乙")
    other.player.member.wugong_id = "basic_fist"
    other.player.insights = list(insights)
    other.player.stats["xinde"] = 100
    return other


# ── 合成的結果放哪（W5、W6）────────────────────────


def test_a_merge_and_other_ways_of_storing_an_art_get_no_switch_hint(ready, content, world):
    """意境合併沒有放進功法庫；學藝、事件教的武學收進功法庫也不是「煉製」的結果，不加這句。"""
    _, msgs = fusion.merge(ready, content, world, named("燎原"), "huo", "feng")
    assert all(library.SWITCH_HINT not in m and "比身上的" not in m for m in msgs)
    stored = library.store_art(ready, generate_from_name("甲乙丙", "武學", "甲乙丙", 0))
    assert stored == ["【甲乙丙】收進功法庫。"]


# ── 意境＋意境（設計 12.6；武學重構：同＋同是揣摩，不同是複合意境）────────────


def test_merge_fire_and_wind_makes_a_shared_yang_insight(ready, content, world):
    insight, msgs = fusion.merge(ready, content, world, named("燎原"), "huo", "feng")
    assert (insight.name, insight.attribute, insight.lean, insight.parents) == ("燎原", "陽", "無", ["feng", "huo"])
    assert ready.player.insights == ["feng", "huo", "燎原"]  # 兩個都留著
    assert ready.player.stats["xinde"] == 100 - content.config.merge_xinde
    assert world.lookup_insight_recipe(fusion.merge_key("feng", "huo")).name == "燎原"
    assert "第一次" in msgs[0] and "屬陽" in msgs[0]
    assert arts_mod.is_compound(content, insight)  # 複合意境：高階技能（測試內容沒有 high 表時照一般功效算）


def test_merge_shape_is_the_same_whichever_way_round(content, world):
    feng, huo = insights.resolve("feng", content, world), insights.resolve("huo", content, world)
    assert fusion.merge_shape(world, feng, huo) == fusion.merge_shape(world, huo, feng) == ("陽", "無")


def test_merge_carries_the_lean(ready, content, world):
    ready.player.insights += ["haoran", "xuesha"]
    good, _ = fusion.merge(ready, content, world, named("正氣長風"), "haoran", "feng")
    plain, _ = fusion.merge(ready, content, world, named("陰陽一氣"), "haoran", "xuesha")
    assert (good.lean, plain.lean) == ("正", "無")
    assert good.attribute in ("陽", "快")  # 陽與快不在對照表裡：配方種子挑一個


def test_a_slotted_compound_insight_gives_its_attribute_and_lean_to_the_art(ready, content, world):
    """意境就是技能：合出來的複合意境裝進武學，武學身上的功效與正邪照它（arts.apply）。"""
    ready.player.insights += ["haoran"]
    good, _ = fusion.merge(ready, content, world, named("正氣長風"), "haoran", "feng")
    assert arts_mod.slot_problem(ready, content, world, "basic_fist", good.id) is None
    arts_mod.slot(ready, content, world, "basic_fist", good.id)
    mine = team.player_art(ready, content, world, "basic_fist")
    fx = ready.player.insight_fx[good.id]  # 意境效果池：合出來的那一份照較好的品質擲一到兩個效果
    assert mine.traits == [k for k, n in fx.general.items() for _ in range(n)]
    assert mine.lean == "正" and mine.attribute == good.attribute  # 基礎拳腳兼容並蓄：屬性照槽裡強度最高那一格
    assert "正派" in skillview.art_card(mine, 1)


def test_the_same_piece_twice_is_refused(ready, content, world):
    """同一份放兩次不成：揣摩要同一種的兩份（意境效果池）。"""
    problem = fusion.merge_problem(ready, content, world, "feng", "feng")
    assert problem == fusion.SAME_PIECE.format(name="風") and problem.short == "要兩份"


def test_two_pieces_of_one_kind_deepen_into_one(ready, content, world):
    """同一種的兩份＝揣摩：同一個功效的層數相加（最多三重）、不取名、不登記、照樣收一次錢；第二份用掉；揉不出新東西就不准。"""
    p = ready.player
    p.insights += ["feng~2", "feng~3"]
    for piece in ("feng", "feng~2", "feng~3"):
        p.insight_fx[piece] = InsightFx(quality="中品", general={"快": 1})
    before = p.stamina
    insight, msgs = fusion.merge(ready, content, world, must_not_ask(), "feng", "feng~2")
    assert insight.id == "feng" and arts_mod.strength_of(ready, "feng") == 2
    assert msgs[0] == fusion.DEEPEN_LINE.format(name="風", mark="二重")
    assert p.stats["xinde"] == 100 - content.config.merge_xinde and p.stamina == before - content.config.merge_stamina
    assert p.insights == ["feng", "huo", "feng~3"] and "feng~2" not in p.insight_fx
    assert world.lookup_insight_recipe(fusion.merge_key("feng", "feng~2")) is None
    _, msgs = fusion.merge(ready, content, world, must_not_ask(), "feng", "feng~3")
    assert msgs[0] == fusion.DEEPEN_LINE.format(name="風", mark="三重") and p.insight_fx["feng"].general == {"快": 3}
    p.insights.append("feng~2")
    p.insight_fx["feng~2"] = InsightFx(quality="中品", general={"快": 1}, grand=None)
    content.config.arts.insight_grand = {}  # 揉不出大獎：三重再揉什麼都不變
    problem = fusion.merge_problem(ready, content, world, "feng", "feng~2")
    assert problem == fusion.DEEPEST.format(name="風", mark="三重") and problem.short == "已到極處"
    none, msgs = fusion.merge(ready, content, world, must_not_ask(), "feng", "feng~2")
    assert none is None and msgs == [problem] and p.stats["xinde"] == 100 - 2 * content.config.merge_xinde


def test_deepening_two_different_effects_keeps_both_and_takes_the_better_quality(ready, content, world):
    p = ready.player
    p.insights.append("feng~2")
    p.insight_fx["feng"] = InsightFx(quality="下品", general={"快": 2})
    p.insight_fx["feng~2"] = InsightFx(quality="上品", general={"lueying": 1})
    content.config.arts.insight_grand = {}
    _, msgs = fusion.merge(ready, content, world, must_not_ask(), "feng", "feng~2")
    assert p.insight_fx["feng"] == InsightFx(quality="上品", general={"快": 2, "lueying": 1})
    assert msgs[0] == fusion.MIXED_LINE.format(name="風")


def test_a_deepened_insight_stays_slotted_and_counts_more_layers(ready, content, world):
    ready.player.insights.append("feng~2")
    arts_mod.slot(ready, content, world, "basic_fist", "feng~2")
    fusion.merge(ready, content, world, must_not_ask(), "feng", "feng~2")
    mine = team.player_art(ready, content, world, "basic_fist")
    assert arts_mod.slots_of(ready, content, mine) == ["feng~2", None] and mine.traits == ["快", "快"]
    assert "feng" not in ready.player.insights  # 裝在槽上的那一份留下，另一份用掉


def test_merging_again_gives_another_piece_until_the_cap(ready, content, world):
    """意境效果池：合過的再合一次是另一份（自己擲效果）；手上滿 insight_piece_cap 份就不准。"""
    first, _ = fusion.merge(ready, content, world, named("燎原"), "huo", "feng")
    second, msgs = fusion.merge(ready, content, world, named("燎原"), "huo", "feng")
    assert second.id == f"{first.id}~2" and second.name == first.name and second.id in ready.player.insight_fx
    while len(insight_fx.pieces(ready, first.id)) < content.config.arts.insight_piece_cap:
        ready.player.insights.append(insight_fx.new_piece_id(ready, first.id))
    problem = fusion.merge_problem(ready, content, world, "feng", "huo")
    assert "已經有" in problem and problem.short == "已經夠了"
    ready.player.stats["xinde"], ready.player.stamina = 0, 0
    assert problem == fusion.merge_problem(ready, content, world, "feng", "huo")  # 排在花費之前


@pytest.mark.parametrize(("change", "reason"), [
    (lambda s, c: s.player.insights.remove("feng"), "都要是你悟得的"),
    (lambda s, c: s.player.stats.update(xinde=0), "心得不足"),
    (lambda s, c: setattr(c.config, "holding_cap_base", 3), "滿了"),
])
def test_merge_explains_why_it_is_refused(ready, content, world, change, reason):
    change(ready, content)
    assert reason in fusion.merge_problem(ready, content, world, "feng", "huo")


def test_a_stale_reference_is_refused_instead_of_crashing(ready, content, world):
    ready.player.insights.append("ghost_insight")
    assert "找不到" in fusion.merge_problem(ready, content, world, "feng", "ghost_insight")


def test_a_second_player_merges_into_the_same_insight_without_the_model(ready, content, world):
    first, _ = fusion.merge(ready, content, world, named("燎原"), "huo", "feng")
    other = other_player(content, ("feng", "huo"))
    second, msgs = fusion.merge(other, content, world, must_not_ask(), "feng", "huo")
    assert (second.id, second.creator) == (first.id, "沈浪")
    assert other.player.insights == ["feng", "huo", "燎原"] and "首悟" in msgs[0]


def test_an_anonymous_first_merger_is_shown_by_name(ready, content, world):
    ready.player.anonymous = True
    first, _ = fusion.merge(ready, content, world, named("燎原"), "huo", "feng")
    assert (first.creator, first.creator_shown) == ("沈浪", "沈浪")
    _, msgs = fusion.merge(other_player(content, ("feng", "huo")), content, world, must_not_ask(), "feng", "huo")
    assert "這個意境由沈浪首悟" in msgs[0] and "某位少俠" not in msgs[0]


def test_merge_falls_back_to_the_word_table_when_the_model_is_down(ready, content, world):
    insight, _ = fusion.merge(ready, content, world, model_down(), "huo", "feng")
    assert insight.name == naming.fallback_name(content, fusion.merge_key("huo", "feng"), "意境", tianji=world.read().tianji)


def test_two_players_racing_for_a_new_merge_end_up_with_one_registered_insight(ready, content, world):
    first, _ = fusion.merge(ready, content, world, named("燎原"), "huo", "feng")
    other = other_player(content, ("feng", "huo"))
    with mock.patch.object(world, "lookup_insight_recipe", return_value=None):  # 乙看這一眼時，甲還沒登記
        second, msgs = fusion.merge(other, content, world, named("野火"), "feng", "huo")
    assert (second.id, second.name, second.attribute, second.creator) == (first.id, "燎原", first.attribute, "沈浪")
    assert world.get_insight("野火") is None  # 乙取的名字沒有登記
    assert other.player.insights == ["feng", "huo", "燎原"]
    assert "首悟" in msgs[0] and "第一次" not in msgs[0]
    assert other.player.stats["xinde"] == 95


# ── 合併要花體力（企劃者 2026-10-05；FB-067 降到 5）──────────


def test_merge_stamina_is_half_a_cultivation_by_default(content):
    assert (content.config.merge_stamina, content.config.cultivate_stamina) == (5, 10)


def test_a_merge_costs_stamina_as_well_as_xinde(ready, content, world):
    before = ready.player.stamina
    insight, msgs = fusion.merge(ready, content, world, named("燎原"), "huo", "feng")
    assert insight is not None
    assert ready.player.stamina == before - content.config.merge_stamina
    assert ready.player.stats["xinde"] == 100 - content.config.merge_xinde
    assert f"心得 -{content.config.merge_xinde}" in msgs and f"體力 -{content.config.merge_stamina}" in msgs


def test_a_merge_recipe_book_hit_costs_the_stamina_too(ready, content, world):
    fusion.merge(ready, content, world, named("燎原"), "huo", "feng")
    other = other_player(content, ("feng", "huo"))
    before = other.player.stamina
    second, msgs = fusion.merge(other, content, world, must_not_ask(), "feng", "huo")
    assert second is not None and other.player.stamina == before - content.config.merge_stamina
    assert f"體力 -{content.config.merge_stamina}" in msgs


def test_a_merge_without_enough_stamina_is_refused_and_changes_nothing(ready, content, world):
    ready.player.stamina = content.config.merge_stamina - 1
    assert fusion.merge_problem(ready, content, world, "feng", "huo") == f"體力不足：合併一次要 {content.config.merge_stamina}。"
    insight, msgs = fusion.merge(ready, content, world, named("燎原"), "feng", "huo")
    assert insight is None and msgs == [f"體力不足：合併一次要 {content.config.merge_stamina}。"]
    assert (ready.player.stamina, ready.player.stats["xinde"], ready.player.insights) == (
        content.config.merge_stamina - 1, 100, ["feng", "huo"],
    )
    assert world.lookup_insight_recipe(fusion.merge_key("feng", "huo")) is None  # 被拒絕的不登記配方
    assert fusion.merge_problem(ready, content, world, "feng", "feng") is not None  # 揣摩也要體力
    assert arts_mod.strength_of(ready, "feng") == 1


def test_a_merge_with_exactly_enough_stamina_goes_through_and_leaves_none(ready, content, world):
    ready.player.stamina = content.config.merge_stamina
    insight, _ = fusion.merge(ready, content, world, named("燎原"), "huo", "feng")
    assert insight is not None and ready.player.stamina == 0


def test_not_enough_xinde_is_still_reported_before_the_stamina(ready, content, world):
    ready.player.stamina, ready.player.stats["xinde"] = 0, 0
    assert "心得不足" in fusion.merge_problem(ready, content, world, "feng", "huo")


# ── 爐裡只合意境（Joy 2026-10-21）：武學＋意境改裝槽、武學＋武學拿掉 ────────────────────────────


def test_the_furnace_takes_only_insights_and_names_nothing_else(ready, content, world):
    assert fusion.forge_request(ready, content, world, "basic_fist", ["feng"]) is None  # 不開取名的單子
    assert fusion.forge_request(ready, content, world, "basic_fist", ["feng", "huo"]) is None  # 形狀不對
    assert fusion.forge_request(ready, content, world, None, ["feng"]) is None
    assert fusion.fuse_key("basic_fist", "feng") == "融|basic_fist+feng"  # 舊配方鍵還讀得到（上線前登記的）
    assert fusion.blend_key("basic_fist", "lake_kick").startswith(fusion.BLEND_PREFIX)  # 舊的武學合成配方也認得


def test_the_engine_slots_an_insight_instead_of_fusing(game):
    """裝意境走 Game.slot_insight：不花心得體力、不叫模型；江湖紀錄一則、不是「煉製」。爐裡放武學回 ART_IN_FURNACE。"""
    p = game.state.player
    p.member.wugong_id, p.insights, p.stats["xinde"] = "basic_fist", ["feng"], 100
    stamina = p.stamina
    assert game.forge("basic_fist", ["feng"]) == [fusion.ART_IN_FURNACE] and not game.forged
    assert p.art_slots.get("basic_fist") in (None, [None, None])
    with mock.patch.object(game.client, "chat_structured", side_effect=AskedTheModel("裝意境不叫模型")):
        msgs = game.slot_insight("basic_fist", "feng")
    assert msgs[0] == arts_mod.SLOTTED_LINE.format(insight="風", art="粗淺拳腳", i=1)
    assert p.art_slots["basic_fist"] == ["feng", None] and p.arts == [] and p.insights == ["feng"]
    assert (p.stats["xinde"], p.stamina) == (100, stamina) and game.forged and game.forged_thing is None
    assert game.forge_request("basic_fist", ["feng"]) is None
    again = game.slot_insight("basic_fist", "feng")
    assert again == [arts_mod.DUP_LINE.format(name="粗淺拳腳", insight="風")] and not game.forged


# ── Game.forge：江湖紀錄與價錢 ────────────────────────────────


def test_the_engine_forge_only_merges_two_insights(game):
    p = game.state.player
    p.member.wugong_id, p.member.neigong_id = "basic_fist", "basic_breath"
    p.insights, p.stats["xinde"] = ["feng", "huo"], 100
    with mock.patch.object(game.client, "chat_structured", side_effect=RuntimeError):
        assert game.forge("basic_fist", []) == [fusion.ART_IN_FURNACE]
        game.forge(None, ["feng", "huo"])
        msgs = game.forge(None, ["feng"])
    assert p.arts == [] and len(p.insights) == 3
    assert msgs == [fusion.TWO_INSIGHTS]


def test_the_engine_forge_is_titled_after_the_craft_tab_and_only_written_when_something_was_made(game):
    """FB-047：開爐的江湖紀錄標題是「煉製」（合併、揣摩都是）；被拒絕就只回一句話、不寫紀錄。"""
    p = game.state.player
    p.member.wugong_id, p.member.neigong_id = "basic_fist", "basic_breath"
    p.insights, p.stats["xinde"] = ["feng", "huo"], 100
    before = len(game.state.journal)
    game.forge("basic_fist", ["huo", "feng"])  # 爐裡放了武學：不合
    assert len(game.state.journal) == before
    with mock.patch.object(game.client, "chat_structured", side_effect=RuntimeError):
        game.forge(None, ["feng", "huo"])
        merged = game.state.journal[0]
        p.insights.append("feng~2")
        game.forge(None, ["feng", "feng~2"])
        deepened = game.state.journal[0]
    assert (merged.title, deepened.title) == ("煉製", "煉製")
    assert merged.tag.startswith("合併「") and deepened.tag == "合併「風」"
    assert game.forged_thing == ("ins", "feng")
    length = len(game.state.journal)
    game.forge(None, ["feng", "feng"])  # 同一份放兩次：被拒絕
    assert len(game.state.journal) == length


def test_the_engine_merge_journal_entry_shows_both_the_xinde_and_the_stamina(game):
    p = game.state.player
    p.insights, p.stats["xinde"] = ["feng", "huo"], 100
    before = p.stamina
    with mock.patch.object(game.client, "chat_structured", side_effect=RuntimeError):
        msgs = game.forge(None, ["feng", "huo"])
    entry = game.state.journal[0]
    assert entry.title == "煉製" and entry.tag.startswith("合併「")
    assert "心得 -5" in entry.changes and "體力 -5" in entry.changes  # FB-067：合併 5 點體力
    assert p.stamina == before - 5 and "體力 -5" in msgs


def test_the_engine_refused_merge_writes_no_journal_entry_and_spends_nothing(game):
    p = game.state.player
    p.insights, p.stats["xinde"], p.stamina = ["feng", "huo"], 100, 3
    length = len(game.state.journal)
    msgs = game.forge(None, ["feng", "huo"])
    assert any("體力不足" in m for m in msgs) and len(game.state.journal) == length
    assert (p.stamina, p.stats["xinde"], p.insights) == (3, 100, ["feng", "huo"])


def test_the_merge_melt_merge_loop_is_still_allowed_but_every_round_costs_stamina(game):
    """要拿心得就給他拿：合併（-5 心得、-5 體力）→ 熔掉那個意境（+10 心得）→ 再合同一組，沒有被擋；每一圈都付體力。"""
    p = game.state.player
    p.insights, p.stats["xinde"] = ["feng", "huo"], 100
    cfg = game.content.config
    stamina, xinde = p.stamina, p.stats["xinde"]
    with mock.patch.object(game.client, "chat_structured", side_effect=RuntimeError):
        for round_ in range(1, 4):
            game.forge(None, ["feng", "huo"])
            (merged,) = [i for i in p.insights if i not in ("feng", "huo")]
            game.melt_insight(merged)
            assert p.insights == ["feng", "huo"]
            assert p.stamina == stamina - cfg.merge_stamina * round_
            assert p.stats["xinde"] == xinde + (cfg.melt_insight_xinde - cfg.merge_xinde) * round_


# ── 首次取名在行動鎖外（最終審查 Critical 1）：A 鎖內備料 → B 鎖外取名 → C 鎖內重驗、登記、收費 ──────────


def test_forge_request_hands_out_a_naming_slip_only_when_the_model_is_needed(ready, content, world):
    """A 段只讀：會被拒絕、配方已經登記過、放的不是兩個意境、同一個意境揣摩，都不必叫模型（回 None）。"""
    before = ready.model_dump_json()
    merge = fusion.forge_request(ready, content, world, None, ["huo", "feng"])
    assert (merge.kind, merge.key, merge.name_kind) == ("merge", fusion.merge_key("huo", "feng"), "意境")
    assert merge.choices == ()
    assert ready.model_dump_json() == before  # 什麼都沒動
    assert fusion.forge_request(ready, content, world, None, ["feng", "feng"]) is None  # 揣摩不取名
    assert fusion.forge_request(ready, content, world, None, ["feng", "shui"]) is None  # 會被拒絕（沒悟到水）
    assert fusion.forge_request(ready, content, world, "basic_fist", ["feng", "huo"]) is None  # 形狀不對
    other = other_player(content, ("feng", "huo"))
    fusion.merge(other, content, world, named("燎原"), "huo", "feng")
    assert fusion.forge_request(ready, content, world, None, ["feng", "huo"]) is None  # 別人登記過了：查表就好


def test_the_naming_slip_is_exactly_the_prompt_the_merge_sends(ready, content, world):
    """A 段開的單子、B 段送出去的、C 段（沒給 proposed 時）自己送的是同一份提示。"""
    request = fusion.forge_request(ready, content, world, None, ["feng", "huo"])
    client = named("燎原")
    fusion.merge(ready, content, world, client, "feng", "huo")
    assert request.messages == client.chat_structured.call_args.args[0]


def test_a_proposed_name_is_used_without_asking_the_model(ready, content, world):
    insight, msgs = fusion.merge(ready, content, world, must_not_ask(), "huo", "feng", proposed=("燎原", "野火燒原。"))
    assert (insight.name, insight.note) == ("燎原", "野火燒原。") and "第一次" in msgs[0]


def _brew_two_recipes_that_got_the_same_model_name(content, world, order):
    """同一個玩家、兩個不同的配方（火＋風、火＋水），模型碰巧給了同一個名字；照 order 的順序登記。"""
    state = new_game_state(content, "沈浪")
    state.player.insights, state.player.stats["xinde"] = ["feng", "huo", "shui"], 100
    for other in order:
        fusion.merge(state, content, world, must_not_ask(), "huo", other, proposed=("燎原", "一句話。"))
    return {other: world.lookup_insight_recipe(fusion.merge_key("huo", other)).name for other in order}


def test_two_recipes_given_the_same_model_name_get_a_fallback_that_does_not_depend_on_who_came_first(content, tmp_path):
    """Infra 第 3 點：兩個不同的配方同時拿到同一個模型名字。先登記的拿到它；後到的換成退路字表的名字——
    種子是它自己的配方鍵＋這一季的天機、鹽從 0 起，所以換個順序再跑一次，後到的那一個拿到的退路名字一樣是它自己的那一個。"""
    from tianxia.sqlite_world import open_world

    names = {}
    for order in (("feng", "shui"), ("shui", "feng")):
        world = open_world(tmp_path / f"{order[0]}.db")
        world.mutate(lambda shared: setattr(shared, "tianji", 3))
        names[order] = _brew_two_recipes_that_got_the_same_model_name(content, world, order)
    fallback = {o: naming.fallback_name(content, fusion.merge_key("huo", o), "意境", tianji=3) for o in ("feng", "shui")}
    assert names[("feng", "shui")] == {"feng": "燎原", "shui": fallback["shui"]}
    assert names[("shui", "feng")] == {"shui": "燎原", "feng": fallback["feng"]}
    assert fallback["feng"] != naming.fallback_name(content, fusion.merge_key("huo", "feng"), "意境")  # 天機有算進去


def test_the_three_steps_run_without_a_server(game):
    """假人也叫 AI 取名：bot_runner 不經過 HTTP 也要走同樣的三段。這裡只拿 Game 與它的全服儲存：
    A 在行動鎖裡（Game.forge_request）→ B 在鎖外（naming.generate）→ C 再進行動鎖（Game.forge(..., proposed=)）。"""
    p = game.state.player
    p.insights, p.stats["xinde"] = ["feng", "huo", "shui"], 100
    world = game.world
    with world.action_lock():
        request = game.forge_request(None, ["feng", "huo"])
    assert request is not None and request.kind == "merge"
    model = mock.Mock(timeout=120)

    def reply(messages, response_model, **kwargs):
        assert not world.db.writing()  # B 段沒拿著寫入交易
        return naming.NameReply(name="燎原", description="野火燒原。")

    model.chat_structured.side_effect = reply
    proposed = naming.generate(model, game.content, request, budget=game.content.config.naming_budget_seconds)
    assert proposed == ("燎原", "野火燒原。")
    with world.action_lock():
        msgs = game.forge(None, ["feng", "huo"], proposed=proposed)
    assert "燎原" in p.insights and p.stats["xinde"] == 95 and "第一次" in msgs[0]
    assert world.lookup_insight_recipe(fusion.merge_key("feng", "huo")).note == "野火燒原。"
    assert game.forge_request(None, ["feng", "huo"]) is None  # 配方登記了：不必再問
    assert game.forge_request(None, ["feng", "shui"]) is not None  # 另一組還沒人合過


def test_forge_request_on_the_game_needs_a_model_client(game):
    p = game.state.player
    p.insights, p.stats["xinde"] = ["feng", "huo"], 100
    assert game.forge_request(None, ["feng", "huo"]) is not None
    assert game.forge_request(None, ["feng", "shui"]) is None  # 沒悟到：會被拒絕
    game.client = None  # 沒有 client（伺服器假人鎖內的 Game 就是這樣）：預設不開單；假人程式在鎖外自己叫模型，給 named_outside=True 才開
    assert game.forge_request(None, ["feng", "huo"]) is None
    assert game.forge_request(None, ["feng", "huo"], named_outside=True) is not None


def test_the_naming_budget_fits_under_the_tunnels_cut(content):
    """trycloudflare 約 100 秒就切斷一個請求；取名的預算 60 秒，留下 A、C 兩段等行動鎖的餘裕。"""
    assert content.config.naming_budget_seconds == 60


# ── 狀態列的「可以開爐」提示（can_forge）────────────────────────


def test_can_forge_looks_only_at_the_shape_of_what_you_hold(ready, content, world):
    assert fusion.can_forge(ready, content)  # 有意境、付得起
    ready.player.insights = []
    assert not fusion.can_forge(ready, content)  # 沒有意境：合不了
    ready.player.arts = ["lake_kick"]
    assert not fusion.can_forge(ready, content)  # 兩門武學也合不了（武學合成拿掉了）
    ready.player.insights = ["feng"]
    ready.player.stats["xinde"] = 0
    assert not fusion.can_forge(ready, content)


def test_slot_refusals_carry_a_short_word(ready, content, world):
    """裝槽的拒絕也帶 short（skillview.forge_picks 照它標，不再一律「合不了」）。"""
    from tianxia import arts
    ready.player.art_slots["basic_fist"] = ["feng", None]
    assert arts.slot_problem(ready, content, world, "basic_fist", "feng").short == "已裝上"
    ready.player.art_slots["basic_fist"] = ["feng", "huo"]
    ready.player.insights.append("shui")
    assert arts.slot_problem(ready, content, world, "basic_fist", "shui").short == "槽滿了"
