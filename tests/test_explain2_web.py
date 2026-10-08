"""玩法說明二（explain-2）的網頁部分：點戰況圖卡、態勢、大事、主線看的說明。
照 tests/test_explain_web.py 的做法把整支 app.js 放進 node 的假瀏覽器，餵它真的引擎給的 /api/main；沒有 node 就略過。"""
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


def _season_one(**over):
    """週末設定（第一季濃縮版）的新角色、略過序章的樣子：伺服器給的 /api/main。"""
    content = real_content("weekend")
    content.config.auto_open_first_season = True
    game = Game.new(content, "沈浪", rng=random.Random(0))
    game.client = None
    m = server.main_view(game)
    m.update(over)
    return m


def _click(act):
    """在 node 裡送一次點擊：目標的 closest("[data-act]") 是一個 data-act＝act 的元素。"""
    return f'await T.docListeners.click[0]({{ target: {{ closest: () => ({{ dataset: {{ act: "{act}" }}, classList: {{ contains: () => false }} }}) }} }});'


# ── 一、戰況圖卡：點了在底下攤開說明 ─────────────────────────────


def test_tapping_the_front_cards_opens_their_explanation_below_them():
    m = _season_one()
    lines = m["status"]["war_help"]["fronts"]
    out = run(m, f"""return (async () => {{
      const closed = H.pageJianghu();
      {_click("fronts-help")}
      const opened = H.pageJianghu();
      const first = H.S.frontsOpen;
      {_click("fronts-help")}
      return {{ closed, opened, first, second: H.S.frontsOpen }};
    }})();""")
    assert out["first"] is True and out["second"] is False
    closed, opened = out["closed"], out["opened"]
    cards = re.search(r'<div class="fronts"[^>]*>', closed).group(0)
    assert 'data-act="fronts-help"' in cards and 'role="button"' in cards and 'aria-expanded="false"' in cards
    assert "war-help" not in closed  # 點開之前什麼都不多：第一屏照舊
    block = re.search(r'<div class="war-help fronts-help" id="fronts-help">(.*?)</div>', opened).group(1)
    assert re.findall(r"<p>(.*?)</p>", block) == lines  # 伺服器寫好的幾行，一行一段
    assert opened.index('id="fronts-help"') > opened.index('class="fronts"')  # 排在圖卡底下
    # 攤開只動到圖卡底下：圖卡以前的整頁一個字都沒變（「剛剛」、場景、行動列、軍令卡）
    assert opened[:opened.index('<div class="war"')] == closed[:closed.index('<div class="war"')]


def test_the_front_cards_are_not_a_button_without_the_server_explanation():
    """伺服器沒給說明（舊版）：照舊只是一排圖卡，不能點。"""
    m = _season_one()
    m["status"].pop("war_help")
    page = run(m, "return H.pageJianghu();", S={"frontsOpen": True})
    cards = re.search(r'<div class="fronts"[^>]*>', page).group(0)
    assert 'data-act' not in cards and 'role="group"' in cards and "war-help" not in page


def test_the_explanation_lines_are_escaped():
    m = _season_one()
    m["status"]["war_help"]["fronts"] = ["<b>粗</b>"]
    page = run(m, "return H.pageJianghu();", S={"frontsOpen": True})
    assert "&lt;b&gt;粗&lt;/b&gt;" in page and "<b>粗</b>" not in page


# ── 一、態勢、大事、主線：小標點開的面板最後接一小段說明 ─────────────────


@pytest.mark.parametrize("chip", ["stance", "board", "quest"])
def test_each_peek_panel_ends_with_its_explanation(chip):
    m = _season_one(bulletin=["<p><strong>三十六方起義</strong></p>"])
    week = m["status"]["calendar"]["week"]
    closed = run(m, "return H.peekBlock(H.S.main);")
    assert f'data-id="{chip}"' in closed and "war-help" not in closed  # 小標在、說明要點開才有
    panel = run(m, "return H.peekBlock(H.S.main);", S={"peekOpen": {"id": chip, "week": week}})
    block = re.search(rf'<div class="war-help {chip}-help">(.*?)</div>', panel).group(1)
    assert re.findall(r"<p>(.*?)</p>", block) == m["status"]["war_help"][chip]
    assert panel.rindex("war-help") > panel.index('class="peek-panel')  # 接在面板最後
