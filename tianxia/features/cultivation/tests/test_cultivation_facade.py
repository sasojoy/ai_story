"""cultivation 這一包的測試，從 tests/core/test_engine.py 拆來（全部拆包第 61 批，只搬位置、不改斷言）。"""
import random
from unittest import mock
import pytest
from conftest import walk_to
from tianxia import library, skillview, team, traits
from tianxia.engine import Game
from tianxia.martial_arts import MartialArt
from engine_kit import _a_fused_art, _practice_step_game, _reload, _wear, ids  # noqa: F401

pytestmark = pytest.mark.whole_content


def test_the_menxia_pages_get_their_rows_from_the_game_facade(game):
    """修練與煉製兩頁的資料都從 Game 這個門面拿（伺服器不直接碰 skillview）。"""
    game.state.player.member.wugong_id = "basic_fist"
    game.state.player.arts = ["lake_kick"]
    game.state.player.insights = ["feng"]
    assert game.holdings() == {"count": 3, "cap": library.cap_of(game.state, game.content)}
    assert [r["id"] for r in game.art_rows()] == ["basic_fist", "lake_kick"]
    assert [r["id"] for r in game.insight_rows()] == ["feng"]
    assert game.naming_row() is None
    game.state.player.naming = "lake_kick"
    assert game.naming_row() == {"id": "lake_kick", "name": "湖邊腿法"}
    game.state.player.naming = "ghost"
    assert game.naming_row() is None  # 找不到那門武學：沒有東西可以取名


def test_loading_drops_a_naming_right_someone_else_holds_or_the_art_is_gone(content, world):
    game = Game.new(content, "舊檔", rng=random.Random(0), world=world)
    art = _a_fused_art(world)
    p = game.state.player
    assert world.claim_master(art.id, "別人")  # 第一個練成的是別人：換季、讀到舊檔都可能對不上
    p.arts, p.naming = [art.id], art.id
    assert _reload(game, content, world).naming is None
    other = _a_fused_art(world, "回風掌")
    assert world.claim_master(other.id, "舊檔")
    p.arts, p.naming = [], other.id  # 取名權是自己的，可是那門武學已經不在手上
    assert _reload(game, content, world).naming is None


def test_practice_writes_one_merged_journal_entry(game):
    _wear(game, wugong="fist")
    game.state.player.stats["xinde"] = 10
    msgs = game.practice("武學")
    assert msgs == ["【長拳】精進至第2成。", "心得 -1"]  # 第 1 成升第 2 成花 1 點心得
    assert game.state.player.member.wugong_level == 2
    entry = game.state.journal[0]
    assert entry.title == "修練" and entry.tag == msgs[0]
    game.practice("武學")
    assert game.state.player.member.wugong_level == 3
    assert game.state.player.stats["xinde"] == 7  # 再花 2 點
    assert game.state.journal[0].title == "修練"  # 併進同一則


def test_a_refused_practice_writes_no_journal_entry(game):
    """練不成（還沒學、心得不足）只回一句話，不留一則「修練」紀錄（武學與成長計畫 F12）。"""
    game.state.player.stats["xinde"] = 0
    before = list(game.state.journal)
    game.state.player.member.wugong_id = None
    game.practice("武學")  # 還沒學
    game.state.player.member.wugong_id, game.state.player.member.wugong_level = "fist", 4
    msgs = game.practice("武學")  # 心得不足
    assert "心得不足" in msgs[0]
    assert game.state.journal == before


def test_learning_shows_up_on_the_menu_and_costs_no_stamina(game):
    walk_to(game, "lake")
    game.state.player.stats["silver"] = 30
    stamina = game.state.player.stamina
    option = next(o for o in game.options() if o.id == "learn:lake_kick")
    assert option.enabled and "銀兩 10" in option.label
    game.choose("learn:lake_kick")
    assert "lake_kick" in library.owned_arts(game.state)
    assert game.state.player.stamina == stamina


def test_a_lesson_you_cannot_afford_is_listed_but_greyed_out(game):
    walk_to(game, "lake")
    game.state.player.stats["silver"] = 3
    option = next(o for o in game.options() if o.id == "learn:lake_kick")
    assert not option.enabled and "學費 10 兩" in option.label
    assert "（此刻無法這麼做。）" in game.choose("learn:lake_kick")


def test_learning_is_written_to_the_journal_and_the_lesson_leaves_the_menu(game):
    walk_to(game, "lake")
    game.state.player.stats["silver"] = 30
    game.choose("learn:lake_kick")
    entry = game.state.journal[0]
    assert entry.title == "學藝・湖邊腿法" and "銀兩 -10" in entry.changes
    assert "learn:lake_kick" not in ids(game)


def test_a_refused_melt_writes_no_journal_entry(game):
    game.state.player.member.wugong_id = "basic_fist"
    before = list(game.state.journal)
    assert "先改練" in game.melt_art("basic_fist")[0]  # 身上正在練的
    assert "沒有" in game.melt_art("lake_kick")[0]  # 功法庫裡沒有
    assert "沒有" in game.melt_insight("feng")[0]  # 沒有這個意境
    assert game.state.journal == before


def test_a_practice_that_cannot_be_afforded_does_not_finish_the_step(game):
    """練成花心得：心得不夠就沒練成，引導那一步不能算完成（也不發獎勵）。"""
    reward = _practice_step_game(game, {"武學": 1})
    game.state.player.stats["xinde"] = 0
    silver = game.state.player.stats["silver"]
    msgs = game.practice("武學")
    assert "心得不足" in msgs[0] and game.state.player.member.wugong_level == 1
    assert game.state.player.tutorial_step == 0 and game.state.player.guide_done == []
    assert game.state.player.stats["silver"] == silver
    game.state.player.stats["xinde"] = 1  # 湊到第 1 成升第 2 成的價錢，再練就算了
    game.practice("武學")
    assert game.state.player.tutorial_step == 1
    assert game.state.player.stats["silver"] == silver + reward


def test_art_detail_of_a_worn_art_uses_the_slots_level(game):
    """FB-006：功法卡。配在身上的那一門，熟練度看身上那一欄（內功、武學各一欄）。"""
    _wear(game, wugong="fist", neigong="breath")
    game.state.player.member.wugong_level = 5
    game.state.player.member.neigong_level = 7
    wugong = game.art_detail("fist")
    assert wugong.startswith("【長拳】") and "\n第5成 " in wugong
    assert "\n第7成 " in game.art_detail("breath")


def test_art_detail_of_a_library_art_uses_its_own_kept_level(game):
    """功法庫裡的那一門用換下來時存的熟練度（art_levels）；沒存過的從第一成算（見 team.switch_art）。"""
    stored = MartialArt(
        id="沉柳纏勁", name="沉柳纏勁", kind="武學", quality="上品", attribute="柔", affinity=["柔"],
        base_power=28.0, top_power=72.0, creator="沈浪", note="以柔勁纏住兵刃，借力卸力。",
    )
    assert game.world.claim_skill_name(stored)
    game.state.player.arts.append(stored.id)
    # 武學重構：屬性照相容屬性、功效照槽裡的意境（「水」裝進第一格）；卡照身上那一份（team.player_art）寫
    game.state.player.insights = ["shui"]
    game.state.player.art_slots[stored.id] = ["shui"]
    stored = team.player_art(game.state, game.content, game.world, stored.id)
    line = traits.card_line(game.content, stored)  # 功法卡多一行功效（計畫六 Task 4）
    assert game.art_detail(stored.id) == skillview.art_card(stored, 1, trait_line=line)
    game.state.player.art_levels[stored.id] = 4
    card = game.art_detail(stored.id)
    assert card == skillview.art_card(stored, 4, trait_line=line)
    assert "\n功效：〔化勁〕" in card and card.endswith("以柔勁纏住兵刃，借力卸力。")  # 在來源那一行之後、說明之前


def test_art_detail_of_an_art_that_is_not_yours_is_not_found(game):
    other = MartialArt(
        id="鐵柳纏勁", name="鐵柳纏勁", kind="武學", quality="中品", attribute="剛",
        base_power=16.0, top_power=44.0, creator="別人",
    )
    assert game.world.claim_skill_name(other)
    assert game.art_detail("鐵柳纏勁") == "（找不到這門功法。）"  # 世界裡有，但不是你的
    assert game.art_detail("ghost") == "（找不到這門功法。）"
    game.state.player.arts.append("ghost")  # 庫裡記著、內容與世界裡都沒有
    assert game.art_detail("ghost") == "（找不到這門功法。）"


def _registered_art(game, name="凌風拳", parents=()):
    """一門登記在全服、放進功法庫的合成武學（煉製不再合武學，直接登記）。回傳它的 id。"""
    art = MartialArt(
        id=name, name=name, kind="武學", quality="中品", attribute="剛", base_power=16.0, top_power=44.0,
        creator=game.state.player.name, origin="fused", parents=list(parents),
    )
    assert game.world.claim_skill_name(art)
    game.state.player.arts.append(art.id)
    return art.id


def test_art_detail_of_a_blended_art_names_both_parents(game):
    made = _registered_art(game, parents=["basic_breath", "basic_fist"])
    assert "由【粗淺吐納】與【粗淺拳腳】衍生" in game.art_detail(made)  # 來源照 id 排序（basic_breath 在 basic_fist 前）
    assert "衍生" not in game.art_detail("basic_fist")


def test_allocation_stops_at_the_cap_and_without_points(game):
    p = game.state.player
    p.stat_points = 1
    p.stats["wis"] = 15
    assert "到頂" in game.allocate_stat("wis")[0]
    assert p.stat_points == 1  # 到頂的那一點沒扣
    p.stat_points = 0
    assert "沒有可以分配" in game.allocate_stat("str")[0]
    assert "沒有這項" in game.allocate_stat("silver")[0]
    assert p.stats["str"] == 5 and p.stats["silver"] == 50


def test_a_refused_allocation_writes_no_journal_entry(game):
    """被拒絕（沒有點、到頂、沒這項）只回一句話，不留紀錄（武學與成長計畫 F12）。"""
    p = game.state.player
    before = list(game.state.journal)
    game.allocate_stat("str")  # 沒有點
    p.stat_points, p.stats["wis"] = 1, 15
    game.allocate_stat("wis")  # 到頂
    game.allocate_stat("silver")  # 沒這項
    assert game.state.journal == before


def test_allocating_writes_one_merged_journal_entry(game):
    """連按幾次（玩家、假人都一樣）併成一則「配點」，數值變化加總。"""
    game.state.player.stat_points = 3
    game.allocate_stat("str")
    game.allocate_stat("str")
    game.allocate_stat("agi")
    heads = [e for e in game.state.journal if e.title == "配點"]
    assert len(heads) == 1 and game.state.journal[0] is heads[0]
    assert heads[0].changes == ["臂力 +2", "身法 +1"]


def test_the_last_point_does_not_say_there_are_zero_left(game):
    game.state.player.stat_points = 2
    assert game.allocate_stat("str") == ["臂力 +1（還有 1 點可以分配）"]
    assert game.allocate_stat("agi") == ["身法 +1"]  # 最後一點：不寫「還有 0 點」


def test_a_mastery_request_asks_for_a_new_name(game):
    """練成絕學、輪到自己定名：開一張請模型另取新名字的單（伺服器假人用；真人自己填）。沒有等著定名的是 None。"""
    p = game.state.player
    assert game.mastery_request() is None
    p.naming = _registered_art(game)
    request = game.mastery_request()
    assert request.kind == "master" and request.key == f"定名|{p.naming}" and request.name_kind == "武學"
    assert "凌風拳" in request.messages[-1]["content"] and "不一樣" in request.messages[-1]["content"]


def test_a_mastery_request_is_only_a_read_and_waits_for_the_season(game):
    """開單只讀（A 段在鎖內、很快）；賽季籌備中不開。"""
    p = game.state.player
    p.naming = _registered_art(game)
    before = game.state.model_dump()
    assert game.mastery_request() is not None
    assert game.state.model_dump() == before
    with mock.patch.object(game.world, "season_phase", return_value="preparing"):
        assert game.mastery_request() is None
