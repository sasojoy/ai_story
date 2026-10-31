"""商城第三批：玩法說明多一段「商城」（元寶只能儲值取得、不能換銀兩；這一版封測發放；月卡怎麼算）。
玩法說明不看個人（howto.page），月卡寫成規則；點體力條看的那幾句照這個人此刻的上限寫（FB-480，test_mall.py）。
商城關著時玩法說明一個字都不提元寶。數字全讀 Config 與商品表。"""
from __future__ import annotations

import pytest

from tianxia import howto
from tianxia.models import MallItem
from tianxia.world_state import fresh_season


def _items(card: bool = True) -> dict[str, MallItem]:
    items = [MallItem(id="pills_5", name="回體丹五顆", price=100, kind="consumable", effects={"pills": 5})]
    if card:
        items.append(MallItem(id="card_30", name="月卡", price=600, kind="card", effects={"card_days": 30}))
    return {i.id: i for i in items}


@pytest.fixture
def on(content):
    m = content.config.mall
    m.enabled, m.beta_grant = True, 5000
    content.mall = _items()
    content.config.stamina_pills_per_day = 2
    content.config.newbie_pills_per_day = 5
    return content


def _section(content) -> str:
    """玩法說明裡「商城」那一段（標題到下一個標題之前）；沒有這一段是空字串。"""
    page = howto.page(content, fresh_season(content), recruitable=False)
    head = f"#### {howto.MALL_TITLE}"
    if head not in page:
        return ""
    return page.split(head, 1)[1].split("\n####", 1)[0]


@pytest.mark.smoke
def test_the_page_has_a_mall_section(on):
    text = _section(on)
    assert howto.MALL_COIN in text  # 元寶只能儲值取得、不能換銀兩
    assert "每個角色第一次進來先撥 5000 元寶" in text  # 封測發放（beta_grant）
    assert "回體丹多 1 顆（平常 2 → 3、新手期 5 → 6）" in text  # 月卡（card_pill_bonus、stamina_pills_per_day、newbie_pills_per_day）
    assert "還沒到期再買，從到期日往後接" in text


@pytest.mark.smoke
def test_no_grant_no_grant_line(on):
    on.config.mall.beta_grant = 0
    text = _section(on)
    assert howto.MALL_COIN in text and "先撥" not in text


def test_the_card_line_follows_the_numbers(on):
    on.config.mall.card_pill_bonus = 2
    on.config.newbie_pills_per_day = 0
    assert "回體丹多 2 顆（平常 2 → 4）" in _section(on)


def test_no_card_line_when_pills_are_unlimited_or_no_card_is_sold(on):
    on.config.stamina_pills_per_day = 0  # 不限就是不限：月卡不加
    assert "月卡" not in _section(on)
    on.config.stamina_pills_per_day = 2
    on.mall = _items(card=False)  # 架上沒有月卡
    assert "月卡" not in _section(on)


def test_mall_off_page_says_nothing_about_it(on):
    on.config.mall.enabled = False
    page = howto.page(on, fresh_season(on), recruitable=False)
    assert f"#### {howto.MALL_TITLE}" not in page and "元寶" not in page
