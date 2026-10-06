"""第一季正式版・乙二：拼圖、推理與集體密謀（計畫 2026-10-06-第一季正式版-乙二）。

用真實內容（content/）；開關在測試裡才打開。週末設定（人數上限 2）：情誼 30→6、密謀人數 3→1。

content/opportunities.json 裡六筆第 4 階機緣、content/orders.json 的 petition 裡新寫的句子是初稿，待 joy 潤
（JSON 沒有註解、模型不收多的欄位，所以標記記在這裡與 models.py；跟乙一同一個做法）。機緣文件寫好的句子照原文，不在此列。"""
from __future__ import annotations

import random
from pathlib import Path
from unittest import mock

import pytest

from tianxia import defection, foreshadow, opportunities, rules
from tianxia.content import ContentError, load_content, validate
from tianxia.engine import Game
from tianxia.state import PlayerState, Plot, WorldState

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
    (lambda c: _opp(c, "huang_mole").deduce.trend.update({"nowhere": 1}), "戰線 nowhere"),
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


def test_an_opportunity_must_write_only_its_own_block(real):
    _opp(real, "huang_jiazi").puzzle = _opp(real, "guan_three_plans").puzzle  # plot 卻多寫了 puzzle
    with pytest.raises(ContentError, match="huang_jiazi：只能寫 plot 那一塊"):
        validate(real)
