"""商城的設定與商品表（商城架構設計 4.2、4.3、4.10）：開關（正式與 week7 開、測試內容關）、封測發放（預設 0、week7 5000）、
商品表 content/mall.json 只能從允許的效果表挑，表外的、種類對不上的、外觀與通行證（這一版還沒有效果）載入時就擋。"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from conftest import real_content

from tianxia import mall
from tianxia.content import ContentError, load_content

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "content"


def _item(**over) -> dict:
    item = {"id": "pills_5", "name": "回體丹五顆", "note": "五顆回體丹。", "price": 100, "kind": "consumable", "effects": {"pills": 5}}
    item.update(over)
    return item


def _load(tmp_path, items: list[dict]):
    root = tmp_path / "content"
    shutil.copytree(FIXTURE, root)
    (root / "mall.json").write_text(json.dumps(items, ensure_ascii=False), encoding="utf-8")
    return load_content(root)


@pytest.mark.slow
def test_real_content_has_placeholder_items():
    c = real_content()
    assert c.config.mall.enabled is True and c.config.mall.beta_grant == 0
    assert c.config.mall.card_pill_bonus == 1
    kinds = sorted(item.kind for item in c.mall.values())
    assert "card" in kinds and kinds.count("consumable") >= 1
    assert all("待 joy" in item.draft for item in c.mall.values())  # PM 佔位，名字與價錢等 joy
    assert real_content("season21").config.mall.beta_grant == 0
    week7 = real_content("week7").config.mall
    assert week7.enabled is True and week7.beta_grant == 5000


@pytest.mark.smoke
def test_fixture_content_keeps_the_mall_off(content):
    assert content.config.mall.enabled is False and content.mall == {}
    raw = json.loads((FIXTURE / "config.json").read_text(encoding="utf-8"))
    assert raw["mall"] == {"enabled": False}  # 測試內容明寫關著


def test_a_good_item_loads(tmp_path):
    c = _load(tmp_path, [_item(), _item(id="card_30", name="月卡", kind="card", effects={"card_days": 30},
                                        limit={"account": 3}, on_sale={"seasons": [1, 2], "start": "2026-10-25", "end": "2026-11-01"})])
    assert c.mall["pills_5"].effects == {"pills": 5}
    assert c.mall["card_30"].limit.account == 3 and c.mall["card_30"].on_sale.seasons == [1, 2]


@pytest.mark.parametrize(("over", "word"), [
    ({"effects": {"silver": 100}}, "允許"),  # 表外的效果（銀兩不能用元寶買，設計反目標）
    ({"effects": {}}, "效果"),
    ({"kind": "card"}, "種類"),  # 回體丹是消耗品，不是月卡
    ({"kind": "look", "effects": {"pills": 1}}, "種類"),  # 外觀這一版不開：允許表裡沒有外觀的效果
    ({"effects": {"pills": 0}}, "數量"),
    ({"effects": {"pills": 5000}}, "數量"),
    ({"name": "回體丹ABC"}, "名字"),
    ({"on_sale": {"start": "2026/10/25"}}, "日期"),
    ({"on_sale": {"start": "2026-11-02", "end": "2026-11-01"}}, "日期"),
    ({"on_sale": {"seasons": [0]}}, "季"),
])
def test_bad_items_are_rejected(tmp_path, over, word):
    with pytest.raises(ContentError) as caught:
        _load(tmp_path, [_item(**over)])
    assert "pills_5" in str(caught.value) and word in str(caught.value)


def test_price_must_be_positive(tmp_path):
    with pytest.raises(ContentError):
        _load(tmp_path, [_item(price=0)])


def test_two_items_cannot_share_a_name(tmp_path):
    with pytest.raises(ContentError) as caught:
        _load(tmp_path, [_item(), _item(id="pills_5b")])
    assert "同名" in str(caught.value)


@pytest.mark.smoke
def test_date_day_matches_the_pill_day():
    """台灣 2026-10-25 這一天＝回體丹那一套的日數（從 1970-01-01 起算、照台灣日期）。"""
    from datetime import datetime, timedelta, timezone

    tw = timezone(timedelta(hours=8))
    noon = datetime(2026, 10, 25, 12, tzinfo=tw).timestamp()
    assert mall.date_day("2026-10-25") == int((noon + 8 * 3600) // 86400)
