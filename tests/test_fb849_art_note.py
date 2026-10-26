"""FB-849：列傳插畫票的說明照這一季的季曆寫上架時機：7 天季的「週」是段，畫面上沒有「第三週」，寫「第 5 天起買得到」（讀 MallWindow.from_week
和 calendar 的段，不另寫一份判斷）；其他季照舊「第三週起買得到」。說明（content/mall.json 的 note）用插槽 {上架}，載入時驗插槽。"""
from __future__ import annotations

import pytest
from zhuan_fix_kit import close_season, make_game, row, to_week

from jianfa_kit import jianfa_game
from tianxia import calendar, mall
from tianxia.models import MallItem, MallWindow

pytestmark = pytest.mark.slow


@pytest.mark.parametrize("profile, said, other", [("season21", "第三週起買得到", "第 5 天"), ("week7", "第 5 天起買得到", "第三週")])
def test_the_art_note_says_when_it_goes_on_sale_in_the_calendars_own_words(profile, said, other):
    game = make_game(profile)
    to_week(game, 3)
    note = row(game, "zhuan_art")["note"]
    assert said in note and other not in note and "{" not in note


def test_the_week7_note_names_the_day_the_item_really_goes_on_sale():
    game = make_game("week7")
    c, w = game.content, game.state.world
    first = calendar.segment_days(3, c)[0]
    assert first == 5
    start = calendar.week_start(3, c, w)
    w.time = start - 600
    game._save_season()
    assert row(game, "zhuan_art") is None  # 第 4 天 23:50：還沒上架
    w.time = start + 600
    game._save_season()
    assert f"第 {first} 天起買得到" in row(game, "zhuan_art")["note"]  # 第 5 天 00:10：上架了，說明寫的就是這一天


def test_the_rest_keeps_the_same_words_and_the_other_items_are_untouched():
    game = make_game("week7")
    to_week(game, 3)
    shelf = {r["id"]: r["note"] for r in game.mall_view()["items"]}
    for item_id, note in shelf.items():
        if item_id != "zhuan_art":
            assert note == game.content.mall[item_id].note  # 沒有插槽的說明一個字不變
    close_season(game)
    assert "第 5 天起買得到" in row(game, "zhuan_art")["note"]


def test_a_note_slot_has_to_be_known_and_needs_a_week_to_fill():
    content = jianfa_game().content
    bad = MallItem(id="x", name="測試貨", price=10, kind="consumable", effects={"zhuan_seal": 1}, note="買不到{別的}。")
    assert any("{別的}" in line for line in mall.item_problems(bad, content))
    no_week = MallItem(id="y", name="測試二", price=10, kind="consumable", effects={"zhuan_seal": 1}, note="{上架}起買得到。")
    assert any("{上架}" in line for line in mall.item_problems(no_week, content))
    ok = MallItem(id="z", name="測試三", price=10, kind="consumable", effects={"zhuan_seal": 1}, note="{上架}起買得到。",
                  on_sale=MallWindow(rule="zhuan_end", from_week=3))
    assert not any("{" in line for line in mall.item_problems(ok, content))


def test_the_real_content_note_uses_the_slot():
    content = jianfa_game().content
    assert "{上架}" in content.mall["zhuan_art"].note and "第三週" not in content.mall["zhuan_art"].note
    assert not any("zhuan_art" in line for item in content.mall.values() for line in mall.item_problems(item, content))
