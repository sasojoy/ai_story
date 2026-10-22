"""FB-663（練功入口對比圖開發回報，PM 2026-10-21 給號）：點開探索（或移動）的卡，最後一顆被底部分頁列蓋住。沒有 node 就略過。

以前用 scrollIntoView({block: "nearest"}) 加 CSS 的 scroll-margin-bottom：卡本身還在視窗裡（只是落在分頁列底下）時瀏覽器認為「已經看得到」，
不捲，scroll-margin 不算數（量到：375×812 站潁川郡，探索卡底 797、分頁列頂 756，最後一顆〔練功〕下半截在分頁列底下，scrollY 一直 0）。
現在自己量卡底、分頁列頂、狀態列底再 scrollBy。node 排不了版：這裡用假的 document／window 餵幾組量到的位置，看捲了多少；
真正的幾何（375×812、375×667、320×568，城裡與野外）在瀏覽器裡量，數字寫在試玩回饋 FB-663 那一列。
"""
from __future__ import annotations

import re

import pytest

import webharness

pytestmark = pytest.mark.skipif(webharness.NODE is None, reason="沒有 node，前端畫面測試略過")

REVEAL = r"""
const code = [konst("REVEAL_GAP"), konst("REVEAL_TOP"), fn("revealShift"), fn("revealMoveCard")].join("\n");
const rect = (r) => ({ ...r, height: r.bottom - r.top });
// 假的 document／window：card 是 null 就是沒有展開的卡；scrollIntoView 照 Chrome 的做法——卡本身整個在視窗裡就不動（scroll-margin 不算數）
function reveal(c) {
  const calls = [];
  const innerHeight = c.innerHeight || 812;
  const win = { innerHeight, scrollBy: (o) => calls.push(o), matchMedia: () => ({ matches: !!c.calm }) };
  const card = c.card && {
    getBoundingClientRect: () => rect(c.card),
    scrollIntoView: () => {
      if (c.card.bottom > innerHeight) calls.push({ legacyScrollIntoView: c.card.bottom + 64 - innerHeight });
    },
  };
  const doc = {
    querySelector: (sel) => (sel === "#page .act-move, #page .act-explore" ? card : sel === ".tabs" && !c.noTabs ? { getBoundingClientRect: () => rect({ top: c.tabsTop, bottom: innerHeight }) } : null),
    getElementById: (id) => (id === "top" ? { hidden: false, getBoundingClientRect: () => rect({ top: 0, bottom: c.topBottom }) } : null),
  };
  new Function("document", "window", code + "\nrevealMoveCard();")(doc, win);
  return calls;
}
const cases = input.cases.map((c) => ({ name: c.name, calls: reveal(c) }));
finish(cases);
"""


def _reveal(*cases):
    out = webharness.run(REVEAL, {"cases": list(cases)})
    return {c["name"]: c["calls"] for c in out}


def _case(name, **kw):
    return {"name": name, "tabsTop": 756, "topBottom": 88, **kw}


def test_a_card_that_ends_under_the_tab_bar_is_scrolled_clear_of_it():
    """PM 量到的：卡底 797（視窗 812 裡）、分頁列頂 756。捲到卡底離分頁列頂至少 12 px。"""
    calls = _reveal(_case("city", card={"top": 575, "bottom": 797}))["city"]
    assert len(calls) == 1 and "legacyScrollIntoView" not in calls[0], calls
    assert calls[0]["top"] >= 797 - (756 - 12)  # 卡底落在 744 以上
    assert calls[0]["behavior"] == "smooth"


def test_a_card_in_the_wilds_that_is_thirteen_pixels_under_is_scrolled_too():
    calls = _reveal(_case("wild", card={"top": 520, "bottom": 769}))["wild"]  # 野外：卡矮一點，仍然被蓋住約 13 px
    assert len(calls) == 1 and calls[0]["top"] >= 769 - (756 - 12)


def test_a_card_already_clear_of_the_tab_bar_stays_put():
    assert _reveal(_case("clear", card={"top": 400, "bottom": 744}))["clear"] == []  # 剛好離 12 px：不動
    assert _reveal(_case("high", card={"top": 300, "bottom": 600}))["high"] == []  # 已經在上面：不往回捲


def test_the_safe_area_under_the_tab_bar_counts():
    """iPhone 底部安全區（--bottom）讓分頁列變高、頂往上移：量的是分頁列真正的頂，不是寫死的 64 px。"""
    plain = _reveal(_case("plain", card={"top": 575, "bottom": 797}))["plain"][0]["top"]
    safe = _reveal(_case("safe", card={"top": 575, "bottom": 797}, tabsTop=722))["safe"][0]["top"]  # 分頁列高了 34 px
    assert safe == plain + 34


def test_a_card_taller_than_the_visible_part_keeps_its_top_and_first_button_in_view():
    """卡比分頁列上方看得到的地方還高（320×568、攤開找素材分支）：捲到卡頂貼在狀態列底下就停，第一顆一定看得到。"""
    calls = _reveal(_case("tall", card={"top": 300, "bottom": 1000}))["tall"]
    assert len(calls) == 1
    new_top = 300 - calls[0]["top"]
    assert new_top >= 88 and new_top <= 88 + 12  # 卡頂在狀態列（底 88）底下，不被它蓋住
    # 已經貼在狀態列底下的：不再往上捲
    assert _reveal(_case("stuck", card={"top": 90, "bottom": 900}))["stuck"] == []


def test_nothing_to_scroll_without_a_card_or_a_tab_bar():
    out = _reveal(_case("closed", card=None), _case("notabs", card={"top": 575, "bottom": 797}, noTabs=True))
    assert out["closed"] == [] and out["notabs"] == []


def test_reduced_motion_scrolls_without_the_slide():
    calls = _reveal(_case("calm", card={"top": 575, "bottom": 797}, calm=True))["calm"]
    assert len(calls) == 1 and calls[0]["behavior"] == "auto"


def test_the_stylesheet_no_longer_leans_on_scroll_margin_for_the_card():
    """scroll-margin-bottom 在這個情形不算數（上面第一條）：留在樣式表裡只會讓人以為是它在管。"""
    css = (webharness.ROOT / "web" / "style.css").read_text(encoding="utf-8")
    rule = re.search(r"\.act-move, \.act-explore \{[^}]*\}", css)
    assert rule and "scroll-margin" not in rule.group(0)
