"""第一季正式版・乙二：拼圖、推理與集體密謀（計畫 2026-10-06-第一季正式版-乙二）。

用真實內容（content/）；開關在測試裡才打開。週末設定（人數上限 2）：情誼 30→6、密謀人數 3→1。

content/opportunities.json 裡六筆第 4 階機緣、content/orders.json 的 petition 裡新寫的句子是初稿，待 joy 潤
（JSON 沒有註解、模型不收多的欄位，所以標記記在這裡與 models.py；跟乙一同一個做法）。機緣文件寫好的句子照原文，不在此列。"""
from __future__ import annotations

import random
from pathlib import Path
from unittest import mock

import pytest

from tianxia import bot, bot_policy, calendar, defection, figures, foreshadow, opportunities, rules, team
from tianxia.content import ContentError, load_content, validate
from tianxia.encounter import EncounterResult
from tianxia.engine import Game
from tianxia.state import BotProfile, FigureState, PlayerState, Plot, WorldState

CONTENT_DIR = Path(__file__).parent.parent / "content"


@pytest.fixture
def real():
    c = load_content(CONTENT_DIR)
    c.config.auto_open_first_season = True
    c.config.train_event_chance = 0.0
    return c


@pytest.fixture
def on(real):
    real.config.season_one, real.config.season_days, real.config.server_max_players = True, 2.5, 2
    return real


def _game(content, name="甲", faction=None, at=None, rank=3, world=None):
    game = Game.new(content, name, rng=random.Random(0), world=world)
    p = game.state.player
    p.faction, p.rank = faction, rank
    if at is not None:
        p.location = at
    return game


def _ids(game):
    return [o.id for o in game.options(odds=False)]


def _always(ok=True):
    return mock.patch.object(rules, "check_chance", return_value=1.0 if ok else 0.0)


def _opp(content, opp_id):
    return next(o for o in content.opportunities if o.id == opp_id)


# ── Task 1：資料模型、內容與載入 ─────────────────────────────────


def test_defaults_so_old_saves_load():
    p = PlayerState(name="甲", location="x", stats={}, stamina=0)
    assert (p.opp_pieces, p.patron, p.opp_settled) == ({}, None, [])
    assert WorldState().plots == []


def test_new_fields_survive_a_save_and_load():
    p = PlayerState(name="甲", location="x", stats={}, stamina=0, opp_pieces={"a": ["b", "c"]}, patron="cao", opp_settled=[1, 4])
    assert PlayerState.model_validate_json(p.model_dump_json()) == p
    w = WorldState(plots=[Plot(id=1, opp="guan_three_roads", faction="guan", leader="甲", shown="某位少俠", members=["甲"],
                               parts={"yingru": "甲"}, deadline=86400.0)])
    again = WorldState.model_validate_json(w.model_dump_json())
    assert again.plots == w.plots and again.plots[0].status == "open"


def test_real_rank_four_opportunities(real):
    four = {o.id: o.kind for o in real.opportunities if o.rank == 4}
    assert four == {
        "guan_three_plans": "puzzle", "guan_three_roads": "plot", "huang_mole": "deduce", "huang_jiazi": "plot",
        "hao_land_people_name": "puzzle", "hao_alliance": "plot",
    }
    assert set(real.orders.petition) == {"guan", "huang", "haoqiang"}


def test_real_petition_wording(real):
    p = real.orders.petition
    assert (p["guan"].label, p["huang"].label, p["haoqiang"].label) == ("請命", "請示渠帥", "聽家主吩咐")
    assert p["guan"].characters == p["huang"].characters == []  # 官軍、黃巾是此刻在場的大勢人物
    assert p["haoqiang"].characters == ["liubei", "guanyu", "zhangfei", "caocao", "yuanshao", "taoqian"]


def test_real_puzzle_content_matches_the_design(real):
    plans = _opp(real, "guan_three_plans").puzzle
    assert [(x.key, x.how, x.front, x.figure, x.affinity, x.topic) for x in plans.pieces] == [
        ("yingru", "ask", "yingru", "huangfusong", 30, "平亂"),
        ("jizhou", "ask", "jizhou", "luzhi", 30, "平亂"),
        ("nanyang", "ask", "nanyang", "sunjian", 30, "平亂"),
    ]
    assert plans.pieces[0].lines == plans.pieces[1].lines == plans.pieces[2].lines
    assert plans.pieces[0].lines["huangfusong"] == "皇甫嵩說：「賊依草，可火；賊依城，可困。」"
    assert (plans.present.at, plans.present.figure, plans.present.stand_in) == ("dajiangjun_fu", "hejin", "大將軍府的長史")
    land = _opp(real, "hao_land_people_name").puzzle
    assert [(x.key, x.how, x.at) for x in land.pieces] == [
        ("land", "silver", "haozu_fort"), ("people", "check", "zhuo_militia_hall"), ("name", "check", "cao_manor")]
    assert land.pieces[0].silver == 50 and land.pieces[1].check.stat == "wis" and land.pieces[1].check.difficulty == 7
    assert {k: (v.character, v.at) for k, v in land.present.patrons.items()} == {
        "yuan": ("yuanshao", "dajiangjun_fu"), "cao": ("caocao", "qiao_county"), "self": ("liubei", "loushang_village")}


def test_real_deduce_and_plot_content_match_the_design(real):
    mole = _opp(real, "huang_mole").deduce
    assert mole.tianji == "mole" and {s.id for s in mole.suspects} == {"clerk", "priest", "strongman"}
    assert [(h.figure, h.at) for h in mole.askers] == [("zhangliang", "guangzong"), ("zhangbao", "xiaquyang"), ("zhangjiao", "guangzong")]
    assert mole.wrong_affinity == -10 and mole.trend == {"jizhou": 1}
    roads = _opp(real, "guan_three_roads").plot
    assert (roads.how, [x.front for x in roads.parts], roads.headcount, roads.need_parts) == ("win", ["yingru", "nanyang", "jizhou"], 3, None)
    jiazi = _opp(real, "huang_jiazi").plot
    assert (jiazi.how, [x.at for x in jiazi.parts], jiazi.need_parts, jiazi.check.stat, jiazi.check.difficulty) == (
        "check", ["changshe", "wan_city", "luoyang_palace", "guangzong", "zhuo_county"], 3, "agi", 6)
    alliance = _opp(real, "hao_alliance").plot
    assert ([x.at for x in alliance.parts], alliance.check.stat, alliance.check.difficulty) == (
        ["zhuo_militia_hall", "cao_manor", "haozu_fort"], "wis", 6)


def test_the_mole_is_one_of_three_by_the_seasons_tianji():
    answers = [foreshadow.tianji_answer(t, "mole") for t in range(40)]
    assert set(answers) == {"clerk", "priest", "strongman"}  # 換季（天機 +1）會換人
    assert answers == [foreshadow.tianji_answer(t, "mole") for t in range(40)]


def test_clear_also_drops_pieces_and_patron():
    p = PlayerState(name="甲", location="x", stats={}, stamina=0, opp_pieces={"a": ["b"]}, patron="cao", opp_settled=[3])
    opportunities.clear(p)
    assert (p.opp_pieces, p.patron) == ({}, None)
    assert p.opp_settled == [3]  # 結算過的密謀不會因叛投再結算一次


def test_defection_clears_pieces_and_patron(on):
    game = _game(on, faction="haoqiang", at="huangjin_camp")
    p = game.state.player
    p.opp_pieces, p.patron = {"hao_land_people_name": ["land"]}, "yuan"
    defection.defect(game.state, on, next(f for f in on.scenario.factions if f.id == "huang"))
    assert (p.opp_pieces, p.patron) == ({}, None)


def test_new_season_resets_the_new_fields(on):
    """角色每季重來：三個新欄位跟著新角色回到空的（照乙一換季那一條的寫法）。"""
    on.config.admins = ["管"]
    admin = _game(on, "管")
    game = _game(on, "甲", faction="haoqiang")
    p = game.state.player
    p.opp_pieces, p.patron, p.opp_settled = {"hao_land_people_name": ["land"]}, "cao", [2]
    game.sync(100.0)
    admin.admin_end_season(now=200.0)
    admin.admin_next_season(now=300.0)
    game.sync(400.0)
    p = game.state.player
    assert p.season_number == 2
    assert (p.opp_pieces, p.patron, p.opp_settled) == ({}, None, [])


# ── 載入時的檢查 ─────────────────────────────────


@pytest.mark.parametrize("break_it, message", [
    (lambda c: setattr(_opp(c, "guan_three_plans").puzzle.pieces[0], "front", None), "yingru 是 ask，要寫 front、figure、topic"),
    (lambda c: setattr(_opp(c, "guan_three_plans").puzzle.pieces[0], "topic", ""), "yingru 是 ask，要寫 front、figure、topic"),
    (lambda c: setattr(_opp(c, "hao_land_people_name").puzzle.pieces[0], "at", None), "land 要寫 at"),
    (lambda c: setattr(_opp(c, "hao_land_people_name").puzzle.pieces[1], "check", None), "people 是 check，要寫 check"),
    (lambda c: setattr(_opp(c, "hao_land_people_name").puzzle.pieces[0], "at", "nowhere"), "地點 nowhere"),
    (lambda c: _opp(c, "guan_three_plans").puzzle.pieces[0].lines.update({"nobody": "他說。"}), "人物 nobody"),
    (lambda c: setattr(_opp(c, "guan_three_plans").puzzle.present, "at", "nowhere"), "地點 nowhere"),
    (lambda c: setattr(_opp(c, "hao_land_people_name").puzzle.present.patrons["cao"], "character", "nobody"), "人物 nobody"),
    (lambda c: setattr(_opp(c, "huang_mole").deduce, "tianji", "ghost"), "天機 ghost 不存在"),
    (lambda c: _opp(c, "huang_mole").deduce.suspects.pop(), "嫌疑人要跟天機 mole 的候選一樣"),
    (lambda c: _opp(c, "huang_mole").deduce.traits.pop(0), "嫌疑人有沒寫片段的特徵"),
    (lambda c: setattr(_opp(c, "huang_mole").deduce.traits[0], "region", "moon"), "特徵有不存在的大區"),
    (lambda c: setattr(_opp(c, "huang_mole").deduce.askers[0], "figure", "nobody"), "人物 nobody"),
    (lambda c: setattr(_opp(c, "huang_mole").deduce.askers[0], "at", "nowhere"), "地點 nowhere"),
    (lambda c: setattr(_opp(c, "huang_jiazi").plot, "check", None), "check 類要寫 check"),
    (lambda c: setattr(_opp(c, "guan_three_roads").plot.parts[0], "at", "changshe"), "每一處寫 front 或 at 其中一個"),
    (lambda c: setattr(_opp(c, "huang_jiazi").plot.parts[0], "at", None), "每一處寫 front 或 at 其中一個"),
    (lambda c: setattr(_opp(c, "huang_jiazi").plot, "need_parts", 6), "need_parts 超出處數"),
    (lambda c: setattr(_opp(c, "huang_jiazi").plot.parts[0], "at", "nowhere"), "地點 nowhere"),
    (lambda c: setattr(_opp(c, "huang_jiazi").plot, "done_text", "各地的牆上同时冒出甲子"), "文字只能用繁體中文"),
    (lambda c: setattr(_opp(c, "huang_mole").deduce, "right", "他沉着脸听完"), "文字只能用繁體中文"),
    (lambda c: c.orders.petition.update({"pirates": c.orders.petition["guan"]}), "沒有陣營 pirates"),
    (lambda c: c.orders.petition["haoqiang"].characters.append("nobody"), "人物 nobody"),
    # 計畫沒寫、這裡多擋的：寫壞了在載入當下就報，不要到玩的時候才發現
    (lambda c: setattr(_opp(c, "guan_three_plans").puzzle.pieces[0], "front", "nowhere"), "戰線 nowhere"),
    (lambda c: setattr(_opp(c, "guan_three_roads").plot.parts[0], "front", "nowhere"), "戰線 nowhere"),
    (lambda c: _opp(c, "huang_mole").deduce.trend.update({"nowhere": 1}), "大勢線 nowhere"),
    (lambda c: _opp(c, "huang_mole").deduce.trend.update({"huangjin": 1}), "trend 不能推衍生線"),
    (lambda c: _opp(c, "guan_three_plans").puzzle.pieces[0].lines.pop("*"), "的 lines 要有"),
    (lambda c: setattr(c.orders.petition["guan"], "label", "请命"), "petition.guan：文字只能用繁體中文"),
    (lambda c: setattr(_opp(c, "guan_three_plans").puzzle.pieces[1], "key", "yingru"), "東西 key 重複"),
    (lambda c: setattr(_opp(c, "guan_three_roads").plot.parts[1], "key", "yingru"), "各處的 key 重複"),
    (lambda c: _opp(c, "guan_three_plans").puzzle.pieces.clear(), "至少要有一樣東西"),
    (lambda c: _opp(c, "huang_mole").deduce.askers.clear(), "至少要有一位指認的人"),
    (lambda c: _opp(c, "guan_three_roads").plot.parts.clear(), "至少要有一處"),
    (lambda c: setattr(_opp(c, "guan_three_plans").puzzle.present, "figure", None), "官軍的交付要寫 figure"),
    (lambda c: setattr(_opp(c, "hao_land_people_name").puzzle.present, "patrons", {}), "要寫 at 或 patrons"),
    (lambda c: setattr(_opp(c, "hao_alliance").plot, "how", "win"), "win 類每一處都要寫 front"),
    (lambda c: setattr(_opp(c, "guan_three_roads").plot, "how", "check"), "check 類每一處都要寫 at"),
])
def test_validate_catches_broken_new_content(real, break_it, message):
    break_it(real)
    with pytest.raises(ContentError, match=message):
        validate(real)


def test_a_deduction_may_push_any_real_trend_line(real):
    """審查 m-3：推的是大勢線（戰線、割據），不只戰線；真實內容的 jizhou 照舊過。"""
    _opp(real, "huang_mole").deduce.trend = {"geju": 1}
    validate(real)


def test_an_opportunity_must_write_only_its_own_block(real):
    _opp(real, "huang_jiazi").puzzle = _opp(real, "guan_three_plans").puzzle  # plot 卻多寫了 puzzle
    with pytest.raises(ContentError, match="huang_jiazi：只能寫 plot 那一塊"):
        validate(real)


# ── Task 2：拼圖型（平亂三策、地人名）─────────────────────────────────


def _talk_to(game, character, affinity):
    p = game.state.player
    p.pending_companion, p.affinities = character, {character: affinity}


def _at_day(game, day, hour=12):
    w = game.state.world
    w.time = (day * 24 + hour) * calendar.HOUR / calendar.cal_scale(game.content, w)


def _option(game, option_id):
    return next((o for o in game.options(odds=False) if o.id == option_id), None)


def test_ask_a_general_for_his_plan(on):
    game = _game(on, faction="guan", at="changshe")
    _talk_to(game, "huangfusong", 5)
    assert "talk:opp:guan_three_plans:yingru" not in _ids(game)  # 30 換算成 6
    _talk_to(game, "huangfusong", 6)
    assert _option(game, "talk:opp:guan_three_plans:yingru").label == "平亂"
    msgs = game.choose("talk:opp:guan_three_plans:yingru")
    assert msgs == ["皇甫嵩說：「賊依草，可火；賊依城，可困。」"]
    assert game.state.player.opp_pieces == {"guan_three_plans": ["yingru"]}
    assert "talk:opp:guan_three_plans:yingru" not in _ids(game)  # 拿過就不再問


def test_plan_comes_from_whoever_holds_the_front(on):
    game = _game(on, faction="guan", at="changshe")
    w = game.state.world
    hfs = figures.state_of(game.state, on, "huangfusong")
    w.figures["huangfusong"] = hfs.model_copy(update={"front": "jizhou", "location": "luzhi_camp"})  # 重挫轉冀州
    _talk_to(game, "huangfusong", 99)
    assert not any(i.startswith("talk:opp:guan_three_plans") for i in _ids(game))  # 他不再是潁川那一策的人
    _talk_to(game, "zhujun", 6)
    assert game.choose("talk:opp:guan_three_plans:yingru") == ["朱儁說：「賊眾烏合，先分其勢，再各個擊破。」"]


def test_present_three_plans_at_the_grand_generals_office(on):
    game = _game(on, faction="guan", at="dajiangjun_fu")
    game.state.player.opp_pieces = {"guan_three_plans": ["yingru", "jizhou"]}
    assert "opp:present:guan_three_plans" not in _ids(game)  # 還缺一策
    game.state.player.opp_pieces["guan_three_plans"].append("nanyang")
    option = _option(game, "opp:present:guan_three_plans")
    assert option.label == "把三策呈給何進"
    msgs = game.choose("opp:present:guan_three_plans")
    assert msgs[0].startswith("何進把三策翻來覆去看了幾遍") and msgs[-1] == "（機緣「平亂三策」完成。）"


def test_land_deed_costs_silver(on):
    game = _game(on, faction="haoqiang", at="haozu_fort")
    game.state.player.stats["silver"] = 30
    option = _option(game, "opp:piece:hao_land_people_name:land")
    assert not option.enabled  # 銀兩不夠
    game.state.player.stats["silver"] = 60
    msgs = game.choose("opp:piece:hao_land_people_name:land")
    assert msgs[0].startswith("塢堡主收了銀子") and game.state.player.stats["silver"] == 10
    assert game.state.player.opp_pieces == {"hao_land_people_name": ["land"]}


def test_register_needs_a_check(on):
    game = _game(on, faction="haoqiang", at="zhuo_militia_hall")
    _at_day(game, 3)
    with _always(False):
        assert game.choose("opp:piece:hao_land_people_name:people")[0].startswith("名冊太亂")
    _at_day(game, 4)  # 計畫的測試在同一天接著重試，可是失敗的那一處當天不能再試（改天再來）：換一天再按
    with _always(True):
        game.choose("opp:piece:hao_land_people_name:people")
    assert game.state.player.opp_pieces == {"hao_land_people_name": ["people"]}


def test_patron_receives_the_three(on):
    game = _game(on, faction="haoqiang", at="qiao_county")
    p = game.state.player
    p.opp_pieces, p.patron = {"hao_land_people_name": ["land", "people", "name"]}, "cao"
    option = _option(game, "opp:present:hao_land_people_name")
    assert option.label == "把地契、戶籍與鄉望交給曹操"
    p.location = "dajiangjun_fu"  # 袁紹那裡：靠山是曹，不收
    assert "opp:present:hao_land_people_name" not in _ids(game)


def test_any_patron_before_one_is_chosen(on):
    game = _game(on, faction="haoqiang", at="loushang_village")
    game.state.player.opp_pieces = {"hao_land_people_name": ["land", "people", "name"]}
    msgs = game.choose("opp:present:hao_land_people_name")
    assert msgs[0].startswith("劉備握著你的手") and msgs[-1] == "（機緣「地、人、名」完成。）"


# ── Task 2 補的：計畫沒寫、這裡多測的（試過一天一次、湊齊後收掉、長史代收、假人不碰、標題）──


def _profile(faction="guan"):
    return BotProfile(personality="普通", seed=1, faction=faction, season_number=1)


def test_only_the_holder_of_a_front_gives_its_plan(on):
    game = _game(on, faction="guan", at="changshe")
    _talk_to(game, "zhujun", 99)  # 朱儁在潁川，但潁川那一策問的是皇甫嵩（他還在那條戰線上）
    assert not any(i.startswith("talk:opp:guan_three_plans") for i in _ids(game))
    _talk_to(game, "huangfusong", 99)  # 冀州問盧植、南陽問孫堅：皇甫嵩只有潁川那一策
    assert [i for i in _ids(game) if i.startswith("talk:opp:guan_three_plans")] == ["talk:opp:guan_three_plans:yingru"]


def test_nobody_to_ask_when_the_front_has_no_commander(on):
    game = _game(on, faction="guan", at="changshe")
    for fid in ("huangfusong", "zhujun"):  # 潁川的官軍將領都下獄了
        game.state.world.figures[fid] = figures.state_of(game.state, on, fid).model_copy(update={"status": "jailed"})
    _talk_to(game, "zhujun", 99)
    assert not any(i.startswith("talk:opp:guan_three_plans:yingru") for i in _ids(game))


def test_taking_a_plan_is_free_and_leaves_the_talk_open(on):
    game = _game(on, faction="guan", at="changshe")
    _talk_to(game, "huangfusong", 6)
    p, rumors = game.state.player, len(game.state.world.rumors)
    before = p.stamina
    assert game.dialogue_request("talk:opp:guan_three_plans:yingru") is None  # 不叫模型（server.prepare_dialogue 靠它判斷）
    game.choose("talk:opp:guan_three_plans:yingru")
    assert p.stamina == before and p.pending_companion == "huangfusong"  # 不扣體力、對話還開著
    assert len(game.state.world.rumors) == rumors  # 拼圖不發任何傳聞
    assert game.choose("talk:opp:guan_three_plans:yingru") == ["（此刻無法這麼做。）"]  # 拿過了，選項不在了


def test_a_stand_in_receives_the_plans_when_he_jin_is_away(on):
    game = _game(on, faction="guan", at="dajiangjun_fu")
    game.state.world.figures["hejin"] = figures.state_of(game.state, on, "hejin").model_copy(update={"status": "jailed"})
    game.state.player.opp_pieces = {"guan_three_plans": ["yingru", "jizhou", "nanyang"]}
    assert _option(game, "opp:present:guan_three_plans").label == "把三策呈給大將軍府的長史"
    assert game.choose("opp:present:guan_three_plans")[0].startswith("大將軍府的長史把三策翻來覆去看了幾遍")


def test_the_plans_go_to_the_office_only(on):
    game = _game(on, faction="guan", at="changshe")
    game.state.player.opp_pieces = {"guan_three_plans": ["yingru", "jizhou", "nanyang"]}
    assert "opp:present:guan_three_plans" not in _ids(game)


def test_pieces_are_cleared_once_it_is_done(on):
    game = _game(on, faction="guan", at="dajiangjun_fu")
    p = game.state.player
    p.opp_pieces = {"guan_three_plans": ["yingru", "jizhou", "nanyang"]}
    game.choose("opp:present:guan_three_plans")
    assert p.opp_pieces == {} and p.opp_done == ["guan_three_plans"]
    assert "opp:present:guan_three_plans" not in _ids(game)  # 每種只完成一次


def test_pieces_are_offered_only_at_their_own_place(on):
    game = _game(on, faction="haoqiang", at="cao_manor")
    ids = _ids(game)
    assert "opp:piece:hao_land_people_name:name" in ids
    assert "opp:piece:hao_land_people_name:land" not in ids and "opp:piece:hao_land_people_name:people" not in ids


def test_a_held_piece_is_not_bought_twice(on):
    game = _game(on, faction="haoqiang", at="haozu_fort")
    p = game.state.player
    p.stats["silver"] = 100
    game.choose("opp:piece:hao_land_people_name:land")
    assert "opp:piece:hao_land_people_name:land" not in _ids(game) and p.stats["silver"] == 50
    stale = opportunities.act(game.state, on, game.world, "piece:hao_land_people_name:land", random.Random(0))
    assert stale == ["（此刻無法這麼做。）"] and p.stats["silver"] == 50  # 過時的按鍵不會再扣一次


def test_a_failed_check_piece_waits_for_the_next_day(on):
    game = _game(on, faction="haoqiang", at="zhuo_militia_hall")
    p = game.state.player
    _at_day(game, 3)
    before = p.stamina
    option = _option(game, "opp:piece:hao_land_people_name:people")
    assert option.enabled and option.label == "抄錄結社的鄉勇名冊（體力 10）"
    with _always(False):
        game.choose("opp:piece:hao_land_people_name:people")
    assert p.stamina == before - 10  # 失敗也花體力
    option = _option(game, "opp:piece:hao_land_people_name:people")
    assert not option.enabled and "今天已經試過" in option.label
    with _always(True):  # 當天直接按也不行：choose 先看選單，所以這裡直接叫 act，驗 act 自己的那道檢查（審查 m-1）
        assert game.choose("opp:piece:hao_land_people_name:people") == ["（此刻無法這麼做。）"]
        assert opportunities.act(game.state, on, game.world, "piece:hao_land_people_name:people", random.Random(0)) \
            == ["（此刻無法這麼做。）"]
    assert p.opp_pieces == {} and p.stamina == before - 10  # 沒有再花體力
    _at_day(game, 4)
    assert _option(game, "opp:piece:hao_land_people_name:people").enabled


def test_a_check_piece_needs_the_stamina(on):
    game = _game(on, faction="haoqiang", at="cao_manor")
    game.state.player.stamina = 9
    assert not _option(game, "opp:piece:hao_land_people_name:name").enabled


def test_nothing_with_the_switch_off(real):
    off = _game(real, faction="haoqiang", at="haozu_fort")  # 開關關著：一個選項都沒有
    assert not any(i.startswith("opp:") for i in _ids(off))
    asker = _game(real, faction="guan", at="changshe")
    _talk_to(asker, "huangfusong", 99)
    assert not any(i.startswith("talk:opp:") for i in _ids(asker))


def test_nothing_without_the_rank_or_the_faction(on):
    young = _game(on, faction="haoqiang", at="haozu_fort", rank=2)  # 第 4 階的要先是第 3 階
    assert "opp:piece:hao_land_people_name:land" not in _ids(young)
    other = _game(on, faction="guan", at="haozu_fort")  # 別的陣營看不到
    assert not any(i.startswith("opp:piece:") for i in _ids(other))


def test_a_piece_action_is_titled_with_the_opportunity(on):
    game = _game(on, faction="haoqiang", at="haozu_fort")
    game.state.player.stats["silver"] = 100
    game.choose("opp:piece:hao_land_people_name:land")
    assert game.state.journal[0].title == "機緣・地、人、名"  # 紀錄最新的放最前面
    game.state.player.opp_pieces = {"hao_land_people_name": ["land", "people", "name"]}
    game.state.player.location = "loushang_village"
    game.choose("opp:present:hao_land_people_name")
    assert game.state.journal[0].title == "機緣・地、人、名" and len(game.state.journal) >= 3


def test_bots_skip_the_puzzle_options(on):
    game = _game(on, faction="haoqiang", at="haozu_fort")
    game.state.player.stats["silver"] = 100
    piece = _option(game, "opp:piece:hao_land_people_name:land")
    assert bot.pick(game, [piece], random.Random(0)) is None
    assert bot_policy.score(game, piece, _profile("haoqiang")) is None
    game.state.player.opp_pieces = {"hao_land_people_name": ["land", "people", "name"]}
    game.state.player.location = "loushang_village"
    present = _option(game, "opp:present:hao_land_people_name")
    assert bot.pick(game, [present], random.Random(0)) is None
    assert bot_policy.score(game, present, _profile("haoqiang")) is None
    asker = _game(on, faction="guan", at="changshe")
    _talk_to(asker, "huangfusong", 6)
    ask = _option(asker, "talk:opp:guan_three_plans:yingru")
    assert bot.pick(asker, [ask], random.Random(0)) is None
    assert bot_policy.score(asker, ask, _profile("guan")) is None


def test_server_bots_never_take_a_puzzle_turn(on):
    game = _game(on, faction="guan", at="dajiangjun_fu")
    p = game.state.player
    chosen = []
    real_choose = game.choose
    with mock.patch.object(game, "choose", side_effect=lambda option_id, *a, **k: chosen.append(option_id) or real_choose(option_id, *a, **k)):
        for seed in range(40):
            p.stamina, p.location, p.pending_companion = 100, "dajiangjun_fu", None
            p.opp_pieces = {"guan_three_plans": ["yingru", "jizhou", "nanyang"]}
            bot_policy.take_turn(game, _profile(), random.Random(seed))
    assert chosen and not any(i.startswith(("opp:", "talk:opp:")) for i in chosen)


# ── Task 3：推理型（營中的內鬼）─────────────────────────────────


def _mole(on):
    return next(o for o in on.opportunities if o.id == "huang_mole")


def test_culprit_follows_the_seasons_tianji(on):
    o = _mole(on)
    picks = {opportunities.culprit(on, o, t) for t in range(30)}
    assert picks == {"clerk", "priest", "strongman"}  # 換季會換人
    assert opportunities.culprit(on, o, 5) == foreshadow.tianji_answer(5, "mole")


def test_trait_fragments_only_tell_the_culprits_traits(on):
    game = _game(on, faction="huang")
    rng = mock.Mock(random=mock.Mock(return_value=0.0), choice=lambda xs: xs[0])
    who = opportunities.culprit(on, _mole(on), 0)
    traits = next(s for s in _mole(on).deduce.suspects if s.id == who).traits
    heard = []
    for region in ("jizhou", "luoyang", "jizhou", "luoyang", "jizhou"):
        heard += opportunities.hear_clues(game.state, on, region, rng, world=None)
    texts = {t.text: t.key for t in _mole(on).deduce.traits}
    told = {texts[line.split("：", 1)[1]] for line in heard if line.split("：", 1)[1] in texts}
    assert told and told <= set(traits)


def test_accuse_right_and_wrong(on):
    game = _game(on, faction="huang", at="guangzong")
    who = opportunities.culprit(on, _mole(on), game.world.read().tianji)
    wrong = next(s.id for s in _mole(on).deduce.suspects if s.id != who)
    game.state.player.affinities = {"zhangliang": 20}
    msgs = game.choose(f"opp:accuse:huang_mole:{wrong}")
    assert "是清白的" in msgs[0] and game.state.player.affinities["zhangliang"] == 10
    assert not next(o for o in game.options(odds=False) if o.id == f"opp:accuse:huang_mole:{who}").enabled  # 當天不能再指
    w = game.state.world
    w.time += calendar.DAY / calendar.cal_scale(on, w)
    before = rules.trend_value(game.state, on, "jizhou")
    msgs = game.choose(f"opp:accuse:huang_mole:{who}")
    assert msgs[-1] == "（機緣「營中的內鬼」完成。）" and rules.trend_value(game.state, on, "jizhou") == before + 1


def test_accuse_needs_an_asker_present(on):
    game = _game(on, faction="huang", at="guangzong")
    w = game.state.world
    for fid in ("zhangliang", "zhangjiao"):
        w.figures[fid] = figures.state_of(game.state, on, fid).model_copy(update={"status": "retired"})
    assert not any(i.startswith("opp:accuse:") for i in _ids(game))  # 廣宗沒人問
    game.state.player.location = "xiaquyang"
    assert next(o for o in game.options(odds=False) if o.id.startswith("opp:accuse:")).label.startswith("向張寶指認")


# 計畫沒寫、這裡多測的

def test_accusing_names_all_three_suspects(on):
    game = _game(on, faction="huang", at="guangzong")
    labels = {o.id: o.label for o in game.options(odds=False) if o.id.startswith("opp:accuse:")}
    assert labels == {
        "opp:accuse:huang_mole:clerk": "向張梁指認：管糧冊的帳房",
        "opp:accuse:huang_mole:priest": "向張梁指認：送藥的道士",
        "opp:accuse:huang_mole:strongman": "向張梁指認：新來的力士",
    }
    assert all("opp:accuse:" not in i for i in _ids(_game(on, faction="huang", at="changshe")))  # 別的地方沒有


def test_a_wrong_accusation_never_drops_affinity_below_zero(on):
    game = _game(on, faction="huang", at="guangzong")
    who = opportunities.culprit(on, _mole(on), game.world.read().tianji)
    wrong = next(s.id for s in _mole(on).deduce.suspects if s.id != who)
    game.state.player.affinities = {"zhangliang": 4}
    game.choose(f"opp:accuse:huang_mole:{wrong}")
    assert game.state.player.affinities["zhangliang"] == 0


def test_a_failed_accusation_waits_for_tomorrow_even_by_a_direct_press(on):
    game = _game(on, faction="huang", at="guangzong")
    who = opportunities.culprit(on, _mole(on), game.world.read().tianji)
    wrong = next(s.id for s in _mole(on).deduce.suspects if s.id != who)
    game.choose(f"opp:accuse:huang_mole:{wrong}")
    assert game.choose(f"opp:accuse:huang_mole:{who}") == ["（此刻無法這麼做。）"]  # 當天直接按也不行
    assert game.state.player.opp_done == []


def test_the_right_name_ends_the_accusing(on):
    game = _game(on, faction="huang", at="guangzong")
    who = opportunities.culprit(on, _mole(on), game.world.read().tianji)
    msgs = game.choose(f"opp:accuse:huang_mole:{who}")
    assert msgs[0].startswith("張梁沉著臉聽完") and msgs[-1] == "（機緣「營中的內鬼」完成。）"
    assert not any(i.startswith("opp:accuse:") for i in _ids(game))  # 每種只完成一次
    assert game.state.player.opp_done == ["huang_mole"]


def test_trait_fragments_are_known_not_tickets(on):
    """片段是知識不是門票（伏筆文件 2.2）：一則都沒聽到也能指認，猜對就算。"""
    game = _game(on, faction="huang", at="guangzong")
    who = opportunities.culprit(on, _mole(on), game.world.read().tianji)
    assert game.state.player.opp_clues == []
    assert game.choose(f"opp:accuse:huang_mole:{who}")[-1] == "（機緣「營中的內鬼」完成。）"


def test_each_trait_fragment_is_heard_once_and_only_in_its_region(on):
    game = _game(on, faction="huang")
    rng = mock.Mock(random=mock.Mock(return_value=0.0), choice=lambda xs: xs[-1])
    heard = [opportunities.hear_clues(game.state, on, "luoyang", rng) for _ in range(4)]
    assert len([h for h in heard if h]) == 1  # 洛陽只有一則特徵講到內鬼（寫工整或請人代寫、兩種只有一種是他的）
    assert all(k.startswith("huang_mole:") for k in game.state.player.opp_clues)
    assert opportunities.hear_clues(game.state, on, None, rng) == []  # 不在任何大區什麼都聽不到


def test_the_engine_hands_the_world_to_the_clues(on):
    game = _game(on, faction="huang", at="guangzong")
    before = game.state.player.stamina
    game.state.player.stamina -= 5  # 花了體力的行動之後才抽
    with mock.patch.object(opportunities, "hear_clues", return_value=[]) as hear:
        game._hear_after_stamina(before)
    assert hear.call_args.kwargs["world"] is game.world  # 內鬼是本季天機決定的，片段要讀同一個天機


def test_accusing_needs_rank_three_and_the_right_faction(on):
    young = _game(on, faction="huang", at="guangzong", rank=2)
    assert not any(i.startswith("opp:accuse:") for i in _ids(young))
    rng = mock.Mock(random=mock.Mock(return_value=0.0), choice=lambda xs: xs[0])
    assert opportunities.hear_clues(young.state, on, "luoyang", rng) == []  # 第 4 階的特徵片段也要先是第 3 階
    other = _game(on, faction="guan", at="guangzong")
    assert not any(i.startswith("opp:accuse:") for i in _ids(other))


def test_a_finished_deduction_tells_no_more_clues(on):
    game = _game(on, faction="huang")
    game.state.player.opp_done = ["huang_mole"]
    rng = mock.Mock(random=mock.Mock(return_value=0.0), choice=lambda xs: xs[0])
    assert not any(h.split("：", 1)[1] in {t.text for t in _mole(on).deduce.traits}
                   for r in ("jizhou", "luoyang") for h in opportunities.hear_clues(game.state, on, r, rng))


# ── Task 4：集體密謀（請命、響應、各處、結算）─────────────────────────────────


def _win():
    return mock.patch.object(team, "fight", return_value=EncounterResult(tier="大勝", margin=50, our_power=100, difficulty=15))


def _huang(on):
    return next(f for f in on.scenario.factions if f.id == "huang")


def test_petition_needs_rank_three_and_an_own_figure(on):
    game = _game(on, faction="guan", at="changshe", rank=2)
    assert "opp:plot:guan_three_roads" not in _ids(game)
    game.state.player.rank = 3
    option = _option(game, "opp:plot:guan_three_roads")
    assert option.label == "請命：接下密謀「三路並進」"
    game.state.player.location = "yingchuan"  # 沒有官軍人物
    assert "opp:plot:guan_three_roads" not in _ids(game)


def test_haoqiang_petition_at_a_patron_character(on):
    game = _game(on, faction="haoqiang", at="qiao_county")
    assert _option(game, "opp:plot:hao_alliance").label == "聽家主吩咐：接下密謀「聯保」"


def test_starting_a_plot_posts_faction_intel(on):
    game = _game(on, faction="guan", at="changshe")
    before = len(game.state.world.rumors)
    game.choose("opp:plot:guan_three_roads")
    plot = game.state.world.plots[-1]
    assert (plot.opp, plot.leader, plot.members, plot.status) == ("guan_three_roads", "甲", ["甲"], "open")
    note = game.state.world.rumors[before]
    assert (note.layer, note.faction) == ("faction", "guan")
    assert note.text == "甲 發起三路並進，還缺潁川汝南、南陽、冀州。"
    assert "opp:plot:guan_three_roads" not in _ids(game)  # 同時只能牽頭一場


def test_three_roads_done_by_wins_on_each_front(on):
    game = _game(on, faction="guan", at="changshe")
    game.choose("opp:plot:guan_three_roads")
    s = game.state
    assert opportunities.on_win(s, on, "yingru", "guan") == []  # 自己陣營的隊伍（操練）不算
    for front in ("yingru", "nanyang", "jizhou"):
        assert opportunities.on_win(s, on, front, "huang")
    assert s.world.plots[-1].status == "done"
    assert opportunities.settle(s, on)[-1] == "（機緣「三路並進」完成。）"  # 第 3 階的發起人：機緣完成


def test_a_train_win_reaches_the_plot(on):
    game = _game(on, faction="guan", at="changshe")
    game.choose("opp:plot:guan_three_roads")
    game.state.player.location = "yingchuan_wilds"
    with _win():
        msgs = game._squad_encounter("huang_grain_convoy")  # noqa: SLF001  黃巾的隊伍；只驗遊歷打贏有接到密謀
    assert "（密謀「三路並進」：潁川汝南這一路，成了。）" in msgs


def test_join_and_check_parts(on):
    game = _game(on, faction="huang", at="guangzong")
    game.choose("opp:plot:huang_jiazi")
    plot_id = game.state.world.plots[-1].id
    other = _game(on, name="乙", faction="huang", at="wan_city", rank=1)
    other.state.world = game.state.world  # 同一季（測試裡直接共用同一份）
    assert _option(other, f"opp:join:{plot_id}").label.startswith("響應甲的密謀「甲子」")
    other.choose(f"opp:join:{plot_id}")
    with _always(True):
        msgs = other.choose(f"opp:part:{plot_id}")
    assert "在宛城的牆上用白土寫下兩個大字" in msgs[0]
    assert game.state.world.plots[-1].parts == {"wan_city": "乙"}


def test_one_person_cannot_do_every_part_when_two_are_needed(on):
    on.config.server_max_players = 500  # 0.6 那一檔：人數 3 換成 2，一個人最多做 2 處
    game = _game(on, faction="haoqiang", at="qiao_county")  # 曹操在譙縣：在這裡聽家主吩咐
    game.state.player.stamina = 100
    game.choose("opp:plot:hao_alliance")
    plot_id = game.state.world.plots[-1].id
    with _always(True):
        game.state.player.location = "cao_manor"
        game.choose(f"opp:part:{plot_id}")
        game.state.player.location = "haozu_fort"
        game.choose(f"opp:part:{plot_id}")
        game.state.player.location = "zhuo_militia_hall"
        option = _option(game, f"opp:part:{plot_id}")
    assert not option.enabled and "要等別人" in option.label  # 三處要 2 人，一人最多做 2 處


def test_offline_member_settles_once(on):
    leader = _game(on, faction="guan", at="changshe")
    leader.choose("opp:plot:guan_three_roads")
    plot = leader.state.world.plots[-1]
    helper = _game(on, name="乙", faction="guan", rank=1)
    helper.state.world = leader.state.world
    plot.members.append("乙")
    plot.status = "done"  # 在乙不在線的時候完成
    msgs = opportunities.settle(helper.state, on)
    assert msgs[0] == "三路並進成了，你那一路也記了一功。" and helper.state.player.contrib == on.config.plot_contrib
    assert opportunities.settle(helper.state, on) == []  # 只結算一次


def test_plot_expires(on):
    game = _game(on, faction="guan", at="changshe")
    game.choose("opp:plot:guan_three_roads")
    plot = game.state.world.plots[-1]
    w = game.state.world
    w.time = plot.deadline + 1
    assert opportunities.settle(game.state, on) == ["三路並進沒能在時限內湊齊，這一回作罷。"]
    assert plot.status == "failed"
    other = _game(on, name="乙", faction="guan", rank=1)
    other.state.world = w
    assert f"opp:join:{plot.id}" not in _ids(other)


# 計畫沒寫、這裡多測的

def _lead(content, opp="guan_three_roads", faction="guan", at="changshe", name="甲", anonymous=False):
    game = _game(content, name, faction=faction, at=at)
    game.state.player.anonymous = anonymous
    game.choose(f"opp:plot:{opp}")
    return game, game.state.world.plots[-1]


def _helper(content, leader, name="乙", faction="guan", rank=1, at=None):
    helper = _game(content, name, faction=faction, at=at, rank=rank)
    helper.state.world = leader.state.world  # 同一季（測試裡直接共用同一份）
    return helper


def test_a_defector_gets_nothing_from_the_plot_he_joined(on):
    """企劃者 2026-10-06 裁決：結算只付還在 plot.faction 的成員；叛投的人什麼都沒有，他的貢獻也不算進成功。"""
    on.config.server_max_players = 500  # 人數 3 換成 2：一個人最多做 2 處
    leader, plot = _lead(on)
    helper = _helper(on, leader, rank=3)
    helper.choose(f"opp:join:{plot.id}")
    assert opportunities.on_win(helper.state, on, "yingru", "huang") and plot.parts == {"yingru": "乙"}
    defection.defect(helper.state, on, _huang(on))
    assert plot.members == ["甲"] and plot.parts == {}  # 他做的那一路不再算
    for front in ("nanyang", "jizhou", "yingru"):
        opportunities.on_win(leader.state, on, front, "huang")
    assert plot.status == "open" and plot.parts == {"nanyang": "甲", "jizhou": "甲"}  # 甲做滿 2 處不能包辦，潁川要等別人
    assert opportunities.settle(helper.state, on) == []
    assert (helper.state.player.contrib, helper.state.player.opp_done) == (0, [])
    third = _helper(on, leader, name="丙", rank=1)
    third.choose(f"opp:join:{plot.id}")
    assert opportunities.on_win(third.state, on, "yingru", "huang")
    assert plot.status == "done"  # 換別人補上才算


def test_a_member_who_defects_after_it_is_done_is_still_not_paid(on):
    leader, plot = _lead(on)
    helper = _helper(on, leader, rank=3)
    helper.choose(f"opp:join:{plot.id}")
    plot.status = "done"  # 在乙不在線的時候完成，他還沒結算就叛投了
    defection.defect(helper.state, on, _huang(on))
    assert opportunities.settle(helper.state, on) == []
    p = helper.state.player
    assert (p.contrib, p.opp_done) == (0, []) and plot.id in p.opp_settled  # 記成結算過，不會之後又補一次
    assert opportunities.settle(helper.state, on) == []


def test_a_leader_who_defects_may_lead_in_the_new_faction(on):
    leader, plot = _lead(on)
    defection.defect(leader.state, on, _huang(on))
    assert leader.state.player.name not in plot.members
    leader.state.player.location, leader.state.player.rank = "guangzong", 3
    assert "opp:plot:huang_jiazi" in _ids(leader)  # 舊陣營那一場不再算他牽頭的


def test_the_news_and_the_join_label_name_an_anonymous_leader(on):
    """陣營軍情一律寫真名、不匿名（企劃者 2026-10-06：只有地方傳聞匿名）。"""
    game = _game(on, faction="guan", at="changshe")
    game.state.player.anonymous = True
    before = len(game.state.world.rumors)
    game.choose("opp:plot:guan_three_roads")
    note = game.state.world.rumors[before]
    assert note.named and note.text.startswith("甲 發起") and "某位少俠" not in note.text and note.layer == "faction"
    assert note.location is None and note.region is None  # 陣營軍情不帶地點（同叛投與軍令）
    helper = _helper(on, game)
    label = next(o for o in helper.options(odds=False) if o.id.startswith("opp:join:")).label
    assert label.startswith("響應甲的密謀") and "某位少俠" not in label


def test_another_faction_never_sees_the_plot(on):
    leader, plot = _lead(on)
    note = leader.state.world.rumors[-1]
    spy = _helper(on, leader, name="乙", faction="huang", rank=3, at="guangzong")
    assert not rules.can_hear(note, spy.state) and rules.can_hear(note, leader.state)
    assert not any(i.startswith(("opp:join:", "opp:part:")) for i in _ids(spy))
    assert opportunities.act(spy.state, on, spy.world, f"join:{plot.id}", random.Random(0)) == ["（此刻無法這麼做。）"]
    assert plot.members == ["甲"]


def test_joining_twice_or_late_is_refused(on):
    leader, plot = _lead(on)
    helper = _helper(on, leader)
    helper.choose(f"opp:join:{plot.id}")
    assert f"opp:join:{plot.id}" not in _ids(helper) and plot.members == ["甲", "乙"]  # 響應過就不再列
    assert opportunities.act(helper.state, on, helper.world, f"join:{plot.id}", random.Random(0)) == ["（此刻無法這麼做。）"]
    assert plot.members == ["甲", "乙"]
    late = _helper(on, leader, name="丙")
    leader.state.world.time = plot.deadline + 1
    assert opportunities.act(late.state, on, late.world, f"join:{plot.id}", random.Random(0)) == ["（此刻無法這麼做。）"]


def test_a_dead_plot_takes_no_more_parts_or_wins(on):
    leader, plot = _lead(on)
    leader.state.world.time = plot.deadline + 1
    assert opportunities.on_win(leader.state, on, "yingru", "huang") == [] and plot.parts == {}
    jiazi, jplot = _lead(on, "huang_jiazi", "huang", "guangzong", name="丁")
    jiazi.state.world.time = jplot.deadline + 1
    jiazi.state.player.stamina = 100
    with _always(True):
        assert jiazi.choose(f"opp:part:{jplot.id}")[0] == "（此刻無法這麼做。）"
    assert jplot.parts == {}


def test_only_enemy_wins_on_the_right_front_count(on):
    leader, plot = _lead(on)
    assert opportunities.on_win(leader.state, on, None, "huang") == []  # 沒有戰線
    assert opportunities.on_win(leader.state, on, "yingru", None) == []  # 沒有陣營的對手（盜匪）
    assert opportunities.on_win(leader.state, on, "yingru", "huang") == ["（密謀「三路並進」：潁川汝南這一路，成了。）"]
    assert opportunities.on_win(leader.state, on, "yingru", "huang") == []  # 同一路不重複記
    assert plot.parts == {"yingru": "甲"}
    stranger = _game(on, "乙", faction="guan", rank=3)  # 沒響應過的人，打贏也不算
    stranger.state.world = leader.state.world
    assert opportunities.on_win(stranger.state, on, "nanyang", "huang") == []


def test_wins_do_not_count_for_a_check_plot(on):
    leader, plot = _lead(on, "huang_jiazi", "huang", "guangzong")
    assert opportunities.on_win(leader.state, on, "yingru", "guan") == [] and plot.parts == {}


def test_a_failed_part_check_blocks_that_part_for_the_day(on):
    on.config.plot_days = 5  # 要活過好幾個曆日，才看得出隔天又能試
    leader, plot = _lead(on, "huang_jiazi", "huang", "guangzong")
    helper = _helper(on, leader, faction="huang", at="wan_city")
    helper.choose(f"opp:join:{plot.id}")
    w = leader.state.world
    w.time = 3 * calendar.DAY / calendar.cal_scale(on, w)
    before = helper.state.player.stamina
    with _always(False):
        assert helper.choose(f"opp:part:{plot.id}")[0].startswith("巡兵的腳步聲近了，你在宛城只寫了一筆")
    assert helper.state.player.stamina == before - 10 and plot.parts == {}
    option = _option(helper, f"opp:part:{plot.id}")
    assert not option.enabled and "今天已經試過" in option.label
    with _always(True):
        assert helper.choose(f"opp:part:{plot.id}") == ["（此刻無法這麼做。）"]  # 當天直接按也不行
    w.time += calendar.DAY / calendar.cal_scale(on, w)
    assert _option(helper, f"opp:part:{plot.id}").enabled


def test_only_a_member_with_stamina_can_work_a_part(on):
    leader, plot = _lead(on, "huang_jiazi", "huang", "guangzong")
    outsider = _helper(on, leader, faction="huang", at="wan_city")  # 沒響應
    assert not any(i.startswith("opp:part:") for i in _ids(outsider))
    with _always(True):
        assert outsider.choose(f"opp:part:{plot.id}") == ["（此刻無法這麼做。）"]
    outsider.choose(f"opp:join:{plot.id}")
    outsider.state.player.stamina = 9
    assert not _option(outsider, f"opp:part:{plot.id}").enabled


def test_the_same_part_is_not_offered_once_someone_did_it(on):
    leader, plot = _lead(on, "huang_jiazi", "huang", "guangzong")
    leader.state.player.stamina = 100
    with _always(True):
        leader.choose(f"opp:part:{plot.id}")  # 廣宗
    assert plot.parts == {"guangzong": "甲"}
    assert not any(i.startswith("opp:part:") for i in _ids(leader))  # 廣宗那一處有人做了


def test_one_person_does_it_all_at_weekend_size(on):
    """週末設定（人數上限 2）：密謀人數 3 換成 1，一個人跑完全部；做完那一步就結算。"""
    game, plot = _lead(on, "huang_jiazi", "huang", "guangzong")
    p = game.state.player
    p.stamina = 100
    with _always(True):
        for place in ("guangzong", "wan_city", "luoyang_palace"):
            p.location = place
            msgs = game.choose(f"opp:part:{plot.id}")
    assert plot.status == "done"
    assert msgs[-1] == "（機緣「甲子」完成。）" and "各地的牆上同時冒出「甲子」兩個字" in "".join(msgs)  # choose 的最後結算
    assert p.opp_done == ["huang_jiazi"] and plot.id in p.opp_settled


def test_the_leader_can_lead_again_after_it_failed(on):
    game, plot = _lead(on)
    game.state.world.time = plot.deadline + 1
    assert "三路並進沒能在時限內湊齊，這一回作罷。" in game.choose("act:rest")  # 下一步行動收到作罷的那一句
    game.choose("act:stand")
    assert plot.status == "failed" and "opp:plot:guan_three_roads" in _ids(game)


def test_settlement_is_delivered_on_the_next_choose_and_sync(on):
    leader, plot = _lead(on)
    helper = _helper(on, leader, rank=1)
    helper.choose(f"opp:join:{plot.id}")
    plot.status = "done"
    msgs = helper.choose("act:rest")
    assert "三路並進成了，你那一路也記了一功。" in msgs and helper.state.player.contrib == on.config.plot_contrib
    helper.choose("act:stand")
    assert "三路並進成了，你那一路也記了一功。" not in helper.choose("act:rest")  # 只一次


def test_sync_settles_a_plot_that_ended_while_offline(on):
    leader, plot = _lead(on)

    def finish(season):
        season.plots[-1].members.append("乙")
        season.plots[-1].status = "done"

    leader.world.mutate_season(finish)  # 乙不在線的時候，別人把它做完了
    helper = _game(on, name="乙", faction="guan", rank=1)  # 之後才連線：從資料庫讀到收場的那一場
    msgs = helper.sync(10.0)
    assert "三路並進成了，你那一路也記了一功。" in msgs and helper.state.player.contrib == on.config.plot_contrib
    assert any(e.title == "密謀" for e in helper.state.journal)  # 寫進江湖紀錄
    assert "三路並進成了，你那一路也記了一功。" not in helper.sync(20.0)


def test_plot_actions_are_titled(on):
    game = _game(on, faction="huang", at="guangzong")
    game.choose("opp:plot:huang_jiazi")
    assert game.state.journal[0].title == "機緣・甲子"
    plot = game.state.world.plots[-1]
    helper = _helper(on, game, faction="huang", at="wan_city")
    helper.choose(f"opp:join:{plot.id}")
    assert helper.state.journal[0].title == "密謀・甲子"
    with _always(True):
        helper.choose(f"opp:part:{plot.id}")
    assert helper.state.journal[0].title == "密謀・甲子"


def test_bots_skip_every_plot_option(on):
    game = _game(on, faction="huang", at="guangzong")
    petition = _option(game, "opp:plot:huang_jiazi")
    accuse = next(o for o in game.options(odds=False) if o.id.startswith("opp:accuse:"))
    game.choose("opp:plot:huang_jiazi")
    plot = game.state.world.plots[-1]
    helper = _helper(on, game, faction="huang", at="wan_city")
    join = _option(helper, f"opp:join:{plot.id}")
    helper.choose(f"opp:join:{plot.id}")
    part = _option(helper, f"opp:part:{plot.id}")
    for owner, option in ((game, petition), (game, accuse), (helper, join), (helper, part)):
        assert option is not None
        assert bot.pick(owner, [option], random.Random(0)) is None
        assert bot_policy.score(owner, option, _profile("huang")) is None


def test_the_defection_prompt_says_the_plot_you_joined_is_lost(on):
    leader, plot = _lead(on)
    helper = _helper(on, leader, rank=1)
    counts = "目前官軍 1 人、黃巾軍 0 人、地方豪強 0 人"
    assert "密謀" not in defection.prompt(helper.state, on, _huang(on), counts)  # 沒響應過就不提
    helper.choose(f"opp:join:{plot.id}")
    assert "響應的密謀作廢" in defection.prompt(helper.state, on, _huang(on), counts)
    plot.status = "failed"  # 已經作罷的沒什麼好失去
    assert "密謀" not in defection.prompt(helper.state, on, _huang(on), counts)


# 審查（review-t1-2）併進來的

def test_plot_ids_reveal_nothing_across_factions(on):
    """I-1：選項 id 會送到前端，密謀編號不能是全服連號（空缺會洩漏別的陣營發起過幾場、大約什麼時候）。"""
    _, a = _lead(on, name="甲")
    _, h1 = _lead(on, "huang_jiazi", "huang", "guangzong", name="乙")
    _, h2 = _lead(on, "huang_jiazi", "huang", "guangzong", name="丙")
    _, b = _lead(on, name="丁")
    ids = [a.id, h1.id, h2.id, b.id]
    assert len(set(ids)) == 4
    assert not set(ids) & {1, 2, 3, 4} and sorted(ids) != list(range(min(ids), min(ids) + 4))  # 不是連號
    # 每一個編號只由自己這一場（陣營、機緣、發起人、發起時刻）決定：別的陣營發起過幾場，都改不了它
    assert b.id == opportunities.plot_id("guan", "guan_three_roads", "丁", 0.0)
    assert a.id == opportunities.plot_id("guan", "guan_three_roads", "甲", 0.0)
    assert h1.id == opportunities.plot_id("huang", "huang_jiazi", "乙", 0.0)


def test_a_colliding_plot_id_is_bumped(on):
    with mock.patch.object(opportunities, "plot_id", return_value=12345):
        _, a = _lead(on, name="甲")
        _, b = _lead(on, name="丁")
    assert a.id == 12345 and b.id != 12345  # 一季之內編號不重複


def test_the_join_option_carries_the_opaque_id(on):
    leader, plot = _lead(on)
    helper = _helper(on, leader)
    join = next(o for o in helper.options(odds=False) if o.id.startswith("opp:join:"))
    assert join.id == f"opp:join:{plot.id}" and plot.id > 4  # 不是從 1 起的連號


def test_two_anonymous_leaders_get_distinct_named_buttons_and_news(on):
    """I-2：陣營軍情與響應的選項一律寫真名、不帶地點；兩個匿名的發起人不會變成一模一樣的兩顆按鈕。"""
    a, _ = _lead(on, name="甲", anonymous=True)
    b, _ = _lead(on, name="丁", anonymous=True)
    helper = _game(on, "乙", faction="guan", rank=1)  # 之後才連線：從資料庫讀到兩場
    labels = [o.label for o in helper.options(odds=False) if o.id.startswith("opp:join:")]
    assert len(labels) == 2 and len(set(labels)) == 2 and not any("某位少俠" in text for text in labels)
    news = [r for r in helper.state.world.rumors if r.layer == "faction"]
    assert {r.text.split(" ")[0] for r in news} == {"甲", "丁"} and all(r.location is None and r.named for r in news)


def test_a_wrong_faction_member_never_fills_the_old_plot(on):
    """裁決補強：就算名單沒清乾淨，換了陣營的人打贏也不會記進舊陣營的密謀（_my_plots 看陣營）。"""
    leader, plot = _lead(on)
    helper = _helper(on, leader, rank=3)
    helper.choose(f"opp:join:{plot.id}")
    helper.state.player.faction = "huang"  # 換了陣營卻沒走 leave_plots
    assert opportunities.on_win(helper.state, on, "yingru", "guan") == [] and plot.parts == {}


def test_leading_is_counted_per_faction(on):
    leader, plot = _lead(on)
    p = leader.state.player
    p.faction, p.location = "huang", "guangzong"  # 還在舊密謀的名單上，但已經是黃巾
    assert "opp:plot:huang_jiazi" in _ids(leader)


def test_plot_steps_hide_when_the_rules_are_off(on):
    """季中開關被關掉（這一季的章是關）：選單上沒有響應、做一處，act 也不給，打贏不記。"""
    leader, plot = _lead(on)
    helper = _helper(on, leader)
    helper.state.world.season_one = False  # 同一份賽季，leader 也看得到
    assert not any(i.startswith("opp:") for i in _ids(helper))
    for what in ("join", "part"):
        assert opportunities.act(helper.state, on, helper.world, f"{what}:{plot.id}", random.Random(0)) == ["（此刻無法這麼做。）"]
    assert opportunities.on_win(leader.state, on, "yingru", "huang") == [] and plot.parts == {} and plot.members == ["甲"]


# 休季之後不再結算（結局與跨季計畫的預檢：收季那一刻的貢獻榜與結算畫面已經存好，之後不能再有東西記進這一季）

def _done_plot_with_two_offline_members(on):
    """甲牽頭、乙（第 1 階）與丙（第 3 階）響應，在他們都不在線的時候被人做完；回傳資料庫裡的那一場。"""
    leader, plot = _lead(on)

    def finish(season):
        season.plots[-1].members += ["乙", "丙"]
        season.plots[-1].status = "done"

    leader.world.mutate_season(finish)
    return leader


def _late_pair(on):
    return _game(on, name="乙", faction="guan", rank=1), _game(on, name="丙", faction="guan", rank=3)


def test_a_participant_who_syncs_only_after_the_season_ended_gets_nothing(on):
    on.config.admins = ["管"]
    admin = _game(on, "管")
    leader = _done_plot_with_two_offline_members(on)
    admin.admin_end_season(now=200.0)
    low, high = _late_pair(on)
    assert low.state.world.ended
    for member in (low, high):
        msgs = member.sync(300.0)
        p = member.state.player
        assert "三路並進成了，你那一路也記了一功。" not in msgs and "三路的捷報同時送進營中，你的名字跟著報了上去。" not in msgs
        assert (p.contrib, p.contrib_weeks, p.opp_done, p.opp_settled) == (0, {}, [], [])
        assert opportunities.settle(member.state, on) == []  # 直接叫也一樣
        assert not any(e.title == "密謀" for e in member.state.journal)
    assert leader.world.get_season().plots[-1].status == "done"  # 收季之後不改那一場（讀資料庫裡的那一份）


def test_the_same_plot_synced_before_the_season_ends_is_paid_as_today(on):
    on.config.admins = ["管"]
    admin = _game(on, "管")
    _done_plot_with_two_offline_members(on)
    low, high = _late_pair(on)
    assert "三路並進成了，你那一路也記了一功。" in low.sync(10.0)
    assert "三路的捷報同時送進營中，你的名字跟著報了上去。" in high.sync(10.0)
    assert low.state.player.contrib == on.config.plot_contrib and low.state.player.opp_done == []
    assert high.state.player.opp_done == ["guan_three_roads"] and len(high.state.player.opp_settled) == 1
    admin.admin_end_season(now=200.0)  # 收季之後再同步，不會再算一次
    assert "三路並進成了，你那一路也記了一功。" not in low.sync(300.0)
    assert low.state.player.contrib == on.config.plot_contrib


def test_nothing_about_plots_works_once_the_season_ended(on):
    leader, plot = _lead(on, "huang_jiazi", "huang", "guangzong")
    helper = _helper(on, leader, faction="huang", at="wan_city")
    leader.state.world.ended = True  # 收季（同一份賽季，測試裡直接共用）
    assert not any(i.startswith("opp:") for i in _ids(helper))
    for what in ("join", "part"):
        assert opportunities.act(helper.state, on, helper.world, f"{what}:{plot.id}", random.Random(0)) == ["（此刻無法這麼做。）"]
    assert opportunities.act(leader.state, on, leader.world, "plot:huang_jiazi", random.Random(0)) == ["（此刻無法這麼做。）"]
    assert opportunities.on_win(leader.state, on, "yingru", "guan") == []
    assert opportunities.settle(leader.state, on) == []
