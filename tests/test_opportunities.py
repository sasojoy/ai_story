"""第一季正式版・乙一：機緣的框架、第 2 階行動與九種機緣（計畫 2026-10-06-第一季正式版-乙一）。

用真實內容（content/）；開關在測試裡才打開。週末設定（人數上限 2）：需求量照伏筆 2.8 換算（10 次→2、情誼 40→8）。

content/opportunities.json 與 content/orders.json 的 rank2 裡新寫的句子是初稿，待 joy 潤（JSON 沒有註解、模型不收多的欄位，
所以標記記在這裡與 models.py；跟叛投的 defect_text 同一個做法）。照機緣文件原文的句子不在此列。"""
from __future__ import annotations

import random
from pathlib import Path

import pytest

from tianxia import opportunities
from tianxia.content import ContentError, load_content, validate
from tianxia.engine import Game
from tianxia.models import OppDef
from tianxia.state import PlayerState

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


def _game(content, name="甲", faction=None, at=None, rank=0):
    game = Game.new(content, name, rng=random.Random(0))
    p = game.state.player
    p.faction, p.rank = faction, rank
    if at is not None:
        p.location = at
    return game


def _ids(game):
    return [o.id for o in game.options(odds=False)]


def test_defaults_so_old_saves_load():
    p = PlayerState(name="甲", location="x", stats={}, stamina=0)
    assert (p.opp_done, p.opp_counts, p.opp_items, p.opp_fronts, p.opp_clues, p.opp_tried, p.rank2_days) == (
        [], {}, {}, {}, [], {}, {})


def test_real_opportunities_valid(real):
    by_id = {o.id: o for o in real.opportunities}
    assert set(by_id) == {
        "guan_zhujun", "guan_courier", "guan_deserter", "huang_zhangliang", "huang_dawn", "huang_talisman",
        "hao_taoqian", "hao_aftermath", "hao_refugees",
    }
    assert all(o.rank == 3 for o in real.opportunities)
    assert set(real.orders.rank2) == {"guan", "huang"}
    assert real.orders.rank2["guan"].name == "招降黃巾散兵"


def test_kind_must_match_its_block(real):
    real.opportunities[0] = OppDef(id="bad", name="壞", faction="guan", rank=3, kind="bond")  # bond 卻沒寫 bond
    with pytest.raises(ContentError, match="bad"):
        validate(real)


def _opp(real, opp_id):
    return next(o for o in real.opportunities if o.id == opp_id)


def test_timing_must_name_its_place_and_front(real):
    courier = _opp(real, "guan_courier").timing
    courier.deliver_front = "nowhere"  # 不是戰線
    with pytest.raises(ContentError, match="deliver_front nowhere"):
        validate(real)
    courier.deliver_front = None  # 有 item 卻沒有要送去的戰線
    with pytest.raises(ContentError, match="item 與 deliver_front"):
        validate(real)
    courier.deliver_front, courier.at = "yingru", []  # 夜裡沒寫地點
    with pytest.raises(ContentError, match="夜裡要寫地點"):
        validate(real)


def test_accumulate_source_must_exist_for_the_faction(real):
    del real.orders.rank2["huang"]
    with pytest.raises(ContentError, match="huang_talisman：來源是第 2 階行動"):
        validate(real)


def test_opportunity_text_must_be_traditional(real):
    _opp(real, "guan_zhujun").bond.text = "朱儁说起自己寒门出身"
    with pytest.raises(ContentError, match="guan_zhujun：文字只能用繁體中文"):
        validate(real)
    real.orders.rank2["guan"].ok = "你放出话去"
    with pytest.raises(ContentError, match="rank2.guan：文字只能用繁體中文"):
        validate(real)


# ── Task 2：機緣的核心與情誼型 ─────────────────────────────────


def test_rank_three_open_to_any_member_rank_four_needs_rank_three(on):
    game = _game(on, faction="guan")
    assert {o.id for o in opportunities.open_ones(game.state, on)} == {"guan_zhujun", "guan_courier", "guan_deserter"}
    assert opportunities.open_ones(_game(on, "乙").state, on) == []  # 散人沒有


def test_rank_four_waits_for_rank_three(on):
    fourth = OppDef(id="guan_four", name="四階", faction="guan", rank=4, kind="bond", bond=on.opportunities[0].bond)
    on.opportunities.append(fourth)
    assert "guan_four" not in {o.id for o in opportunities.open_ones(_game(on, faction="guan", rank=2).state, on)}
    assert "guan_four" in {o.id for o in opportunities.open_ones(_game(on, faction="guan", rank=3).state, on)}


def test_bond_topic_appears_at_the_scaled_affinity(on):
    game = _game(on, faction="guan", at="changshe")
    p = game.state.player
    p.pending_companion, p.affinities = "zhujun", {"zhujun": 7}
    assert "talk:opp:guan_zhujun" not in _ids(game)  # 40 換算成 8，還差 1
    p.affinities["zhujun"] = 8
    option = next(o for o in game.options(odds=False) if o.id == "talk:opp:guan_zhujun")
    assert option.label == "出身"
    msgs = game.choose("talk:opp:guan_zhujun")
    assert msgs[0].startswith("朱儁說起自己寒門出身") and msgs[-1] == "（機緣「朱儁的出身」完成。）"
    assert p.opp_done == ["guan_zhujun"] and opportunities.done_for_rank(game.state, on, 3)
    assert "talk:opp:guan_zhujun" not in _ids(game)  # 每種只完成一次


def test_bond_threshold_is_the_baseline_amount_for_a_big_server(on):
    on.config.server_max_players = 1000  # 1000 人以上那一檔：不換算，情誼要 40
    game = _game(on, faction="guan", at="changshe")
    p = game.state.player
    p.pending_companion, p.affinities = "zhujun", {"zhujun": 39}
    assert "talk:opp:guan_zhujun" not in _ids(game)
    p.affinities["zhujun"] = 40
    assert "talk:opp:guan_zhujun" in _ids(game)


def test_bond_needs_own_faction(on):
    game = _game(on, faction="huang", at="changshe")
    game.state.player.pending_companion, game.state.player.affinities = "zhujun", {"zhujun": 99}
    assert "talk:opp:guan_zhujun" not in _ids(game)


def test_bond_topic_costs_no_stamina_and_no_model(on):
    game = _game(on, faction="guan", at="changshe")
    p = game.state.player
    p.pending_companion, p.affinities = "zhujun", {"zhujun": 8}
    assert game.dialogue_request("talk:opp:guan_zhujun") is None  # 不叫模型（server.prepare_dialogue 靠它判斷）
    before = p.stamina
    game.choose("talk:opp:guan_zhujun")
    assert p.opp_done == ["guan_zhujun"] and p.stamina == before and p.pending_companion == "zhujun"  # 不扣體力、對話還開著


def test_completion_publishes_nothing(on):
    game = _game(on, faction="huang", at="guangzong")
    game.state.player.pending_companion, game.state.player.affinities = "zhangliang", {"zhangliang": 8}
    before = len(game.state.world.rumors)
    game.choose("talk:opp:huang_zhangliang")
    assert len(game.state.world.rumors) == before  # 機緣不發任何傳聞


def test_clear_drops_all_progress():
    p = PlayerState(name="甲", location="x", stats={}, stamina=0, opp_done=["a"], opp_counts={"b": 1},
                    opp_items={"c": "信"}, opp_fronts={"c": "yingru"}, opp_clues=["d"], opp_tried={"e": 3})
    opportunities.clear(p)
    assert (p.opp_done, p.opp_counts, p.opp_items, p.opp_fronts, p.opp_clues, p.opp_tried) == ([], {}, {}, {}, [], {})


def test_switch_off_no_opportunities(real):
    game = _game(real, faction="guan")
    assert not opportunities.active(game.state, real) and opportunities.open_ones(game.state, real) == []


def test_switch_off_dialogue_menu_unchanged(real):
    game = _game(real, faction="guan", at="changshe")
    game.state.player.pending_companion, game.state.player.affinities = "zhujun", {"zhujun": 99}
    assert not any(i.startswith("talk:opp:") for i in _ids(game))


def test_defection_clears_opportunities(on):
    from tianxia import defection

    game = _game(on, faction="guan", at="huangjin_camp")
    game.state.player.opp_done = ["guan_zhujun"]
    defection.defect(game.state, on, next(f for f in on.scenario.factions if f.id == "huang"))
    assert game.state.player.opp_done == []
