"""奪璽的網頁那一半（玉璽碎片設計 5.5、5.10、第十節）：江湖頁的奪璽卡、送出放手一搏、背景輪詢與分頁標題、修練頁的傳承那一列。
餵真的引擎給的 /api/main 給 app.js（tests/test_prologue_web.py 的假瀏覽器）。沒有 node 就略過。"""
from __future__ import annotations

import random

import pytest
from test_prologue_web import DRIVER as PROLOGUE_DRIVER

import server
import webharness
from tianxia.engine import Game

pytestmark = pytest.mark.skipif(webharness.NODE is None, reason="沒有 node，前端畫面測試略過")

# test_prologue_web 的假瀏覽器只把它列的名字交給 H（wholeApp([...]) 寫成 `{ a, b, … }`：名單上的名字 app.js 裡一定要有，
# 不然整支載不起來）。這裡多交奪璽要直接叫的三個；碎片卡 sealHtml 只經過 pageJianghu，不必列
NAMES_START = 'wholeApp(["S", '  # 名單的開頭（結尾那幾個名字別的計畫會加，開頭比較穩）
assert PROLOGUE_DRIVER.count(NAMES_START) == 1
DRIVER = PROLOGUE_DRIVER.replace(NAMES_START, 'wholeApp(["S", "sealDuelHtml", "pollBlocked", "sealTitle", ')


def run(m, script):
    """同 test_prologue_web.run（m 是 /api/main 回的那份）；script 裡可用 H、m、T（T.ctx.document 是假瀏覽器的 document）。"""
    return webharness.run(DRIVER, {"m": m, "script": script, "S": {}, "menxia": None, "stored": {}, "responses": {}})


def _card(**over):
    return {"id": "7:chishou", "shard": "螭首", "challenger": "<b>黃甲</b>", "holder": "懷璽", "phase": "active", "round": 2,
            "rounds": 5, "edge": "黃甲略佔上風", "lines": ["奪璽第 1 回合：黃甲強攻，懷璽以固守相迎——兩邊僵持不下。"], "sent": 1,
            "left": 75, "note": "最後氣勢越偏向挑戰者，碎片越可能易主；璽有靈，未必跟著贏家走。", "mine": False, "tell": "",
            "late": False, "turn": False, "gambles_left": 0, **over}


@pytest.fixture
def m(hints_content, world):
    game = Game.new(hints_content, "沈浪", rng=random.Random(0), world=world)
    game.skip_tutorial()
    return server.main_view(game)


def test_the_jianghu_page_draws_the_seal_card_escaped(m):
    m["status"]["seal_duel"] = _card()
    page = run(m, "return H.pageJianghu();")
    assert "奪璽" in page and "螭首" in page and "第 2／5 回合" in page and "已出招 1／2" in page and "1 分 15 秒" in page
    assert "<b>黃甲</b>" not in page and "&lt;b&gt;黃甲&lt;/b&gt;" in page
    assert "璽有靈" in page


def test_the_tell_is_drawn_only_when_the_server_sends_it(m):
    m["status"]["seal_duel"] = _card(mine=True, tell="他退了半步，門戶守得嚴嚴實實。", turn=True)
    page = run(m, "return H.pageJianghu();")
    assert "他退了半步" in page and "輪到你出招" in page
    m["status"]["seal_duel"] = _card(phase="muster", round=0, left=120)
    page = run(m, "return H.pageJianghu();")
    assert "2 分 0 秒後開打" in page and "已出招" not in page


def test_the_input_box_posts_to_seal_text(m):
    m["free_text"], m["free_op"] = "寫下你陣前的一手（20 字內）", "seal_text"
    page = run(m, "return H.pageJianghu();")
    assert 'data-op="seal_text"' in page


def test_a_watched_tab_keeps_polling_in_the_background_and_flags_your_turn(m):
    """5.5：seal_watch 為真時分頁在背景也照 10 秒輪詢；輪到你出招時分頁標題改成「【奪璽】輪到你出招」，之後改回原本的標題。"""
    m["status"]["seal_watch"] = True
    m["status"]["seal_duel"] = _card(mine=True, turn=True)
    out = run(m, "T.ctx.document.hidden = true; return [H.pollBlocked(), H.sealTitle()].join('|');")
    assert out == "false|【奪璽】輪到你出招"
    m["status"]["seal_watch"] = False
    m["status"]["seal_duel"] = None
    out = run(m, "T.ctx.document.hidden = true; return [H.pollBlocked(), H.sealTitle() === H.S.baseTitle].join('|');")
    assert out == "true|true"
