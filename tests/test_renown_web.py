"""名聲的畫面（名聲設計十一之二：1B、2C、3B、4B、5B、6B）：餵真的引擎資料給 app.js（tests/test_prologue_web.py 的假瀏覽器）。"""
import copy
import random
import re

import pytest
from conftest import real_content
from test_prologue_web import DRIVER as BASE_DRIVER

import server
import webharness
from tianxia.engine import Game

pytestmark = pytest.mark.skipif(webharness.NODE is None, reason="沒有 node，前端畫面測試略過")

# test_prologue_web 的假瀏覽器，多交出本場戰功那一塊（4B）
DRIVER = BASE_DRIVER.replace('"bookHtml", "peerHtml"]', '"bookHtml", "peerHtml", "meritHtml"]')
assert DRIVER != BASE_DRIVER


def run(m, script, *, S=None):
    return webharness.run(DRIVER, {"m": m, "script": script, "S": S or {}, "menxia": None, "stored": {}, "responses": {}})


@pytest.fixture(scope="module")
def base():
    """正式內容、週末設定的一個新角色（名聲開著）：名望 27、善名 18、惡名 3。"""
    c = real_content("week7")
    c.config.auto_open_first_season = True
    g = Game.new(c, "甲", rng=random.Random(0))
    g.client = None
    g.state.player.stats.update({"fame": 27, "good": 18, "evil": 3})
    return server.main_view(g)


@pytest.fixture
def m(base):
    return copy.deepcopy(base)


def test_the_engine_data_is_there(m):
    r = m["status"]["renown"]
    assert r["short"] == ["名動一方", "一方豪俠"] and m["status"]["ranger"] is None


def test_collapsed_bar_has_a_titles_line(m):
    top = run(m, "return H.topHtml();")
    assert 'class="who-renown-line"' in top
    assert '<span class="rn-fame">名動一方</span>' in top and '<span class="rn-xia">一方豪俠</span>' in top


def test_expanded_bar_has_the_line_and_the_strip(m):
    top = run(m, "return H.topHtml();", S={"showMore": True})
    assert 'class="who-renown"' in top and "rn-strip" not in top  # 還沒點開
    assert "名望 27　善名" not in top  # minor 那一行拿掉了（名聲那一行取代）
    top = run(m, "return H.topHtml();", S={"showMore": True, "renownOpen": True})
    assert 'class="rn-strip"' in top and "再 23 到威震州郡" in top and "再 12 到州郡大俠" in top
    assert "名望從哪裡來" not in top or "事件的選擇" in top


def test_a_dot_shows_that_tier(m):
    top = run(m, "return H.topHtml();", S={"showMore": True, "renownOpen": True, "renownDot": "fame:4"})
    assert "天下聞名" in top and "擂台上排在你後面 5 名內的人挑得到你" in top


def test_tight_bar_moves_the_virtue_title_into_the_name_row(m):
    top = run(m, "return H.topHtml();", S={"renownTight": True})
    assert 'class="who-renown-line"' not in top and "一方豪俠" in top


def test_switch_off_draws_the_old_bar(m):
    m["status"]["renown"] = None
    top = run(m, "return H.topHtml();", S={"showMore": True})
    assert "who-renown" not in top and "名望 27　善名 18" in top


def test_peer_card_has_title_chips_and_a_generic_note(m):
    card = {"name": "乙", "affiliation": "散人", "level": 7, "record": "", "arts": [], "actions": [],
            "renown": {"titles": ["小有名氣", "江湖巨寇"], "path": "寇"}}
    html = run(m, "return H.peerHtml();", S={"peer": {"name": "乙", "card": card}})
    assert 'class="rn-chips"' in html and '<span class="rn-chip rn-fame">小有名氣</span>' in html
    assert '<span class="rn-chip rn-kou">江湖巨寇</span>' in html and "rn-peer-help" not in html
    html = run(m, "return H.peerHtml();", S={"peer": {"name": "乙", "card": card, "renownOpen": True}})
    assert "rn-peer-help" in html and "27" not in html


def test_merit_rows_carry_titles_on_a_second_line(m):
    g = {"phase": "active", "left": {"name": "官軍"}, "right": {"name": "黃巾軍"},
         "merit": {"left": [{"name": "甲", "merit": 6, "mine": True, "renown": ["名動一方", "一方豪俠"]}],
                   "right": [{"name": "乙", "merit": 4, "mine": False, "renown": []}], "me": None}}
    html = run({**m, "g": g}, "return H.meritHtml(m.g, () => '');")
    assert '<span class="rn-two">甲<small>名動一方・一方豪俠</small></span>' in html and "<span>乙</span>" in html


def test_option_tag_and_note(m):
    m["options"] = [
        {"id": "choice:0", "label": "挺身而出", "enabled": True, "wait": "", "confirm": "", "confirm_yes": "", "tag": "俠", "note": "合你行俠的路數"},
        {"id": "choice:1", "label": "袖手旁觀", "enabled": True, "wait": "", "confirm": "", "confirm_yes": "", "tag": "", "note": ""},
    ]
    page = run(m, "return H.pageJianghu();")
    assert '<span class="k rn-tag rn-xia">俠</span>' in page and '<small class="opt-note">合你行俠的路數</small>' in page
    assert '<span class="k">2</span>' in page


def test_a_greyed_virtue_choice_keeps_its_reason_in_the_title_and_says_it_on_tap(m):
    """企劃者 2026-10-16 選 (c)：第一屏放不下時灰掉的俠寇鈕底下那一行原因收掉（FB-107 第 10 步），原因放在鈕的 title，點了說整句——
    所以那一顆不用 disabled（按不下去的鈕點了沒反應），改成 aria-disabled、點了只跳原因、不送選擇。"""
    why = "要江湖遊俠才做得來"
    m["options"] = [
        {"id": "choice:0", "label": "替鄉民付了錢", "enabled": False, "wait": "", "confirm": "", "confirm_yes": "", "tag": "俠", "note": why},
        {"id": "choice:1", "label": "乖乖交錢", "enabled": False, "wait": "", "confirm": "", "confirm_yes": "", "tag": "", "note": ""},
    ]
    page = run(m, "return H.pageJianghu();")
    greyed = page[page.index('data-id="choice:0"') - 120:page.index("替鄉民付了錢")]
    assert 'data-act="opt-why"' in greyed and f'data-why="{why}"' in greyed and f'title="{why}"' in greyed
    assert 'aria-disabled="true"' in greyed and " disabled" not in greyed.replace("aria-disabled", "")
    assert re.search(r'class="btn\s+off"', greyed)
    plain = page[page.index('data-id="choice:1"') - 80:page.index("乖乖交錢")]
    assert 'data-act="choose"' in plain and "disabled" in plain and "opt-why" not in plain  # 沒有原因的灰鈕照舊
    out = run(m, """return (async () => {
  await T.docListeners.click[0]({ target: { closest: () => ({ dataset: { act: "opt-why", why: %r, id: "choice:0" },
    classList: { contains: () => false, add() {}, remove() {} }, isConnected: false }) } });
  return { toast: T.els.toast.textContent, calls: T.calls.map((c) => c[0]) };
})();""" % why)
    assert out["toast"] == why and not any("/api/choose" in c for c in out["calls"])


def test_the_gold_tag_opens_the_renown_card(m):
    out = run(m, """return (async () => {
  const click = (act) => T.docListeners.click[0]({ target: { closest: () => ({ dataset: { act }, classList: { contains: () => false, add() {}, remove() {} } }) } });
  await click("renown-open");
  return { more: H.S.showMore, open: H.S.renownOpen };
})();""")
    assert out == {"more": True, "open": True}


def test_howto_entry_says_renown(m):
    """「玩法說明」入口在本週卡「為什麼」攤開的最後一行（減法季批 1）。"""
    why = {"wkOpen": {"key": m["week_card"]["label"] + m["week_card"]["when"], "id": "why"}}
    assert "名聲怎麼來" in run(m, "return H.weekCardHtml(H.S.main);", S=why)
    m["status"]["renown"] = None
    assert "名望怎麼來" in run(m, "return H.weekCardHtml(H.S.main);", S=why)
