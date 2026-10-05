"""第一季正式版・乙一：機緣的框架、第 2 階行動與九種機緣（計畫 2026-10-06-第一季正式版-乙一）。

用真實內容（content/）；開關在測試裡才打開。週末設定（人數上限 2）：需求量照伏筆 2.8 換算（10 次→2、情誼 40→8）。

content/opportunities.json 與 content/orders.json 的 rank2 裡新寫的句子是初稿，待 joy 潤（JSON 沒有註解、模型不收多的欄位，
所以標記記在這裡與 models.py；跟叛投的 defect_text 同一個做法）。照機緣文件原文的句子不在此列。"""
from __future__ import annotations

import random
from pathlib import Path

import pytest

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
