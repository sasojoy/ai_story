"""一條線（奇事、章回主線）的事件剛選完（main.story_now，story 包的 feature_status）：江湖頁「剛剛」那一則一進來就整段攤開，不再收成一行；
玩家收起來就收著（S.nowShut）；最後一幕的結局卡等著時「剛剛」底下一顆「看結局」，跟結局卡同一段的那一行先不放，按了才跳卡、卡看過了全文放回來
（Joy 2026-11-13 杜若的奇事「選完後面只有顯示圖跟一行字」）。正式內容；沒有 node 的略過。"""
# 畫法在 web/main.js 的 nowBlock、nowToggle 與 web/story.js 的 storyNowTail、storyNowText、storyCard；寫在這裡 test_for 改這幾支時才挑得到
from __future__ import annotations

import pytest
from test_companions import _player, real  # noqa: F401  real 是 fixture
from test_prologue_web import DRIVER as PROLOGUE_DRIVER

import server
import webharness

pytestmark = pytest.mark.skipif(webharness.NODE is None, reason="沒有 node，前端畫面測試略過")
NAMES_START = 'wholeApp(["S", '
assert PROLOGUE_DRIVER.count(NAMES_START) == 1
DRIVER = PROLOGUE_DRIVER.replace(NAMES_START, 'wholeApp(["S", "nowBlock", "storyCard", ')

RESULT = "你從她几上拿起那卷竹簡，交給杜衡。"
ENDING = "杜衡走了以後，就沒有再回來。"
NOW = ('<div class="tx-now"><div class="tx-when">剛剛　第 6 天 09:46</div><div class="tx-head"><span class="tx-title">兩張矮几・把她的原稿交給杜衡</span></div>'
       f'<div class="tx-line">{RESULT}<br><br>杜衡接過去，解開青繩，就著燈讀。</div><div class="tx-line">{ENDING}<br><br>潁川的兵發了。</div></div>')
CARD = {"line": "duruo", "kind": "end", "sort": "奇事", "title": "代筆", "text": f"<p>{ENDING}</p>\n<p>潁川的兵發了。</p>", "src": None,
        "ending": "給哥哥", "failed": False}
CLICK = ("await T.docListeners.click[0]({ target: { closest: () => ({ dataset: { act: '%s' }, remove() {}, "
         "classList: { contains: () => false } }) } });")


# 跳顯框掛在 body 上：假的 document 補 appendChild，掛上去的那一個記在 T.els.pop（getElementById("story-pop") 找得到它）
POP = ("const d = T.ctx.document, byId = d.getElementById; d.body.appendChild = (el) => { T.els.pop = el; };"
       " d.getElementById = (id) => (id === 'story-pop' ? T.els.pop || null : byId(id));")


def run(m, script, *, S=None):
    return webharness.run(DRIVER, {"m": m, "script": POP + script, "S": S or {}, "menxia": None, "stored": {}, "responses": {}})


@pytest.fixture
def m(real, world):  # noqa: F811
    view = server.main_view(_player(real, world, "沈浪", "guan", "zhuo_county"))
    view.update(now=NOW, on_road=False, front=None, story_cards=[])
    return view


def test_a_line_event_just_chosen_opens_the_whole_result_until_the_player_folds_it(m):
    plain = run(m, "return H.nowBlock(H.S.main);")
    assert '<div class="now one">' in plain  # 一般的「剛剛」照舊收成一行
    m["story_now"] = True
    opened = run(m, "return H.nowBlock(H.S.main);")
    assert '<div class="now open">' in opened and RESULT in opened and ENDING in opened and "看結局" not in opened
    folded = run(m, "return H.nowBlock(H.S.main);", S={"nowShut": NOW})
    assert '<div class="now one">' in folded  # 玩家收起來了：重畫不再自己攤開


def test_the_last_scene_reads_the_result_first_then_the_ending_card_after_tapping(m):
    m.update(story_now=True, story_cards=[CARD])
    script = ("return (async () => { const before = H.nowBlock(H.S.main); H.storyCard(); const popped = !!T.els.pop;"
              + CLICK % "story-read"
              + " return { before, popped, read: H.S.storyRead === H.S.main.now, card: T.els.pop && T.els.pop.innerHTML, after: H.nowBlock(H.S.main) }; })();")
    out = run(m, script)
    before = out["before"]
    assert RESULT in before and ENDING not in before  # 結局那一段留給卡
    assert 'data-act="story-read"' in before and "看結局 ›" in before
    assert out["popped"] is False  # 卡先等著
    assert out["read"] is True and "此事已了・入傳" in out["card"]
    assert "看結局" not in out["after"] and ENDING in out["after"]  # 按了：卡跳出來，「剛剛」放回全文


def test_without_the_flag_the_ending_card_pops_right_away(m):
    m["story_cards"] = [CARD]
    out = run(m, "H.storyCard(); return { html: T.els.pop && T.els.pop.innerHTML, now: H.nowBlock(H.S.main) };")
    assert out["html"] and "此事已了・入傳" in out["html"]
    assert "看結局" not in out["now"]
