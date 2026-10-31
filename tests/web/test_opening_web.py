"""開局第一分鐘的畫面（減法季整合設計 6.7，批 7 前半）：第一屏只有旁白與三顆選項（沒有本週卡、三方卡），選完人物的信一到就攤開、
排在三方卡前面，信收起來本週卡才出現、「你這一步」第一件就是送信。照 tests/test_prologue_web.py 的做法把整支網頁放進 node 的假瀏覽器；
沒有 node 就略過。"""
from __future__ import annotations

import random
import re

import pytest
from conftest import real_content
from test_prologue_web import run

import server
import webharness
from tianxia.engine import Game

pytestmark = pytest.mark.skipif(webharness.NODE is None, reason="沒有 node，前端畫面測試略過")


def _game():
    c = real_content()
    c.config.auto_open_first_season = True
    c.config.jianfa.enabled = True
    g = Game.new(c, "沈浪", rng=random.Random(0), prologue=True)
    g.client = None
    return g


def test_the_first_screen_is_the_narration_and_three_choices_only():
    m = server.main_view(_game())
    assert m.get("week_card") is None and m.get("sides_card") is None and m.get("letter") is None
    page = run(m, "return H.pageJianghu();")
    assert page.count('data-act="choose"') == 3 and "潁川城門口" in page
    for word in ("wk-card", "wk-strip", "sides-first", 'class="card letter', "新手福利"):
        assert word not in page


def test_after_the_choice_the_letter_opens_by_itself_above_the_sides_card_and_hides_the_week_card():
    g = _game()
    g.choose("choice:0")
    m = server.main_view(g)
    assert m["letter"]["open"] is True and m["week_card"] is not None
    page = run(m, "return H.pageJianghu();")
    letter = re.search(r'<section class="card letter open".*?</section>', page, re.S).group(0)
    assert "傅燮來信" in letter and "長社" in letter and "letter-peek" not in letter  # 攤開了：不是只露一行
    # 自檢 U-03（Joy 2026-10-31「都照建議」）：一到就攤開的這一封只露第一句與託的事，「看全文」點了才是整封、收起、婉拒
    first = m["letter"]["text"].split("。")[0] + "。"
    assert "letter-brief" in letter and f"<p>{first}</p>" in letter and m["letter"]["text"] not in letter
    assert 'data-act="letter-read"' not in letter and 'class="linkish letter-more" data-act="letter-open"' in letter
    full = run(m, "return H.pageJianghu();", S={"letterOpen": m["letter"]["id"]})
    assert m["letter"]["text"] in full and 'data-act="letter-read"' in full and "letter-brief" not in full
    assert page.index('class="card letter') < page.index("sides-first")  # 先聽人說話，再看三方
    assert "wk-card" not in page  # 信收起來本週卡才出現
    assert page.index('class="act-bar') < page.index("push-") if "push-" in page else True  # 問手機通知的那一張排在行動列底下（U-03）
    shut = run(m, "return H.pageJianghu();", S={"letterShut": m["letter"]["id"]})  # 玩家收攏過：照一行露著
    assert 'class="card letter"' in shut and "letter-peek" in shut


def test_once_the_letter_is_put_away_the_week_card_says_deliver_the_letter_first():
    g = _game()
    g.choose("choice:0")
    g.read_letter(opening_id(g))
    m = server.main_view(g)
    assert m.get("letter") is None
    page = run(m, "return H.pageJianghu();")
    card = re.search(r'<section data-wk="low" class="card wk-card".*?</section>', page, re.S).group(0)
    assert "護送" in card and "長社" in card and 'data-act="tab" data-tab="map"' in card
    assert page.index("sides-first") < page.index("wk-card")


def opening_id(game):
    return next(x.id for x in game.state.player.letters if x.kind == "託付")
