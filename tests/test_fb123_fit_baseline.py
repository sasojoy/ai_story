"""FB-123（QA 32efa2c6，2026-10-09）：FB-107 收合的兩個殘留（web/app.js 的 fitOver、fitFirstScreen、renderTop）。

1. 量的基準跟著網址列跑：分頁列固定在畫面底下，手機捲動時網址列收起、跑出來，分頁列跟著上下移幾十 px。集結時倒數每一輪都整頁重畫、
   重量，拿當下的分頁列頂量的話，網址列每換一次狀態第一屏就多收或少收一步、畫面跟著跳。現在同一個寬度記住量到過最小的分頁列頂
   （網址列跑出來的時候；一開頁面、捲回頂端都是這樣）當基準，寬度變了（轉向、拉視窗）重記；打字時（輸入框有焦點，舊的 Android
   會因為鍵盤縮小視窗）不記。
2. 狀態列變高變矮不重量：點名號展開配點就照展開的高度收到底，收起名號之後那幾樣還收著，要等下一個動作；💡 冒出來或變兩行，
   行動列被推下去也不重收。現在 renderTop 重畫狀態列前後量一次 #top 的高度，變了就重量（fitTopMoved）；fitFirstScreen 自己收 💡、
   還原 💡 時也會重畫狀態列，那時不算（S.fitting），不會一直重量。

假頁面照 tests/test_fb107_first_screen.py 的驅動程式（從 app.js 切出 FB-107 那一段；scripts/test_for.py 靠 import 與 app.js 這個名字挑到這裡）。"""
from __future__ import annotations

import pytest
from test_fb107_first_screen import FIGHT, node, run

import webharness


# ── 1. 網址列收起、跑出來：基準不跟著跑 ─────────────────────────────


@node
def test_the_url_bar_hiding_does_not_unfold_a_step_on_the_next_redraw():
    """收了間距與對手的描述（756 − 16 = 740，行動列在 790）；捲下去網址列收起、分頁列移到 812，下一輪倒數重畫：照舊收這兩步，
    畫面不跳。網址列再跑出來也一樣。"""
    script = """
      H.fitFirstScreen(); const first = snap();
      els.setTabsTop(812); H.fitFirstScreen(); const hidden = snap();
      els.setTabsTop(756); H.fitFirstScreen(); const shown = snap();
      return { first, hidden, shown };"""
    out = run({**FIGHT, "bottom": 790}, script)
    assert out["first"]["fitted"] == ["space", "lines"]
    assert out["hidden"]["fitted"] == ["space", "lines"] and out["shown"]["fitted"] == ["space", "lines"]


@node
def test_a_first_measure_with_the_url_bar_hidden_tightens_once_when_it_shows_and_then_holds():
    """第一次量的時候網址列剛好收著（812）：放得下、不收；網址列跑出來（756）：收到放得下為止；之後再收起來：不攤回去（基準記最小的）。"""
    script = """
      els.setTabsTop(812); H.fitFirstScreen(); const hidden = snap();
      els.setTabsTop(756); H.fitFirstScreen(); const shown = snap();
      els.setTabsTop(812); H.fitFirstScreen(); const again = snap();
      return { hidden, shown, again };"""
    out = run({**FIGHT, "bottom": 790}, script)
    assert out["hidden"]["fitted"] == [] and out["shown"]["fitted"] == ["space", "lines"]
    assert out["again"]["fitted"] == ["space", "lines"]


@node
def test_a_width_change_takes_a_new_baseline():
    """橫著拿（寬 812、分頁列頂 330）量過，再轉回直的（寬 375、分頁列頂 756）：照新的寬度重記基準，不沿用橫的那個小的。"""
    script = """
      W.innerWidth = 812; els.setTabsTop(330); L.bottom = 300; H.fitFirstScreen(); const wide = snap();
      W.innerWidth = 375; els.setTabsTop(756); L.bottom = 790; H.fitOnResize(); const tall = snap();
      return { wide, tall, base: S.fitBase };"""
    out = run(FIGHT, script)
    assert out["wide"]["fitted"] == [] and out["tall"]["fitted"] == ["space", "lines"]
    assert out["base"] == {"width": 375, "top": 756}


@node
def test_typing_does_not_lower_the_baseline():
    """輸入框有焦點（隨口應對、放手一搏）：舊的 Android 鍵盤會把視窗縮小、分頁列頂跳上來幾百 px——這時量到的不記成基準，
    收起鍵盤之後不會整頁收到底。"""
    script = """
      H.fitFirstScreen(); const before = snap();
      globalThis.document.activeElement = { tagName: "INPUT" }; els.setTabsTop(430); H.fitFirstScreen();
      globalThis.document.activeElement = null; els.setTabsTop(756); H.fitFirstScreen(); const after = snap();
      return { before, after, base: S.fitBase };"""
    out = run({**FIGHT, "bottom": 790}, script)
    assert out["before"]["fitted"] == ["space", "lines"] and out["after"]["fitted"] == ["space", "lines"]
    assert out["base"]["top"] == 756


# ── 2. 狀態列變高變矮：重量 ─────────────────────────────


@node
def test_a_taller_status_bar_refits_and_a_shorter_one_unfolds_again():
    """點名號展開配點（狀態列高 120 → 300，行動列跟著往下 180）：當場重量、收到放得下；收起名號（回到 120）：當場重量、全部攤回來。
    高度沒變（重畫的只是數字）：不重量。"""
    script = """
      H.fitFirstScreen(); const plain = snap();
      els.top.offsetHeight = 300; L.bottom += 180; H.fitTopMoved(120); const open = snap();
      els.top.offsetHeight = 120; L.bottom -= 180; H.fitTopMoved(300); const shut = snap();
      S.fitted = ["mark"]; H.fitTopMoved(120); const same = S.fitted;
      return { plain, open, shut, same };"""
    out = run({**FIGHT, "bottom": 730}, script)
    assert out["plain"]["fitted"] == []
    assert out["open"]["fitted"][:2] == ["space", "lines"] and "rounds" in out["open"]["fitted"]
    assert out["shut"]["fitted"] == [] and out["shut"]["page"] == ["page"] and out["shut"]["rounds"] == ["rounds"]
    assert out["shut"]["lines"] == [["tx-line"]]
    assert out["same"] == ["mark"]


@node
def test_the_hint_showing_up_pushes_the_row_down_and_refits():
    """體力回到付得起合成時 💡 冒出來（狀態列多 40）：行動列被推下去，當場重量。"""
    script = """
      H.fitFirstScreen(); const before = snap();
      els.top.offsetHeight = 160; L.bottom += 40; H.fitTopMoved(120); const after = snap();
      return { before, after };"""
    out = run({**FIGHT, "bottom": 740}, script)
    assert out["before"]["fitted"] == [] and out["after"]["fitted"] == ["space", "lines"]


@node
def test_folding_the_hint_inside_a_fit_does_not_start_another_fit():
    """fitFirstScreen 收 💡（S.hintTight、重畫狀態列）時狀態列自己變矮，還原時又變高：那是收合本身，不再重量（不然會一直重量）。
    renderTop 照真的那樣先量、重畫、再交給 fitTopMoved。"""
    layout = {"bottom": 790, "actbar": True, "scene": True, "hint": True, "card": True, "lines": [False], "rounds": True}
    script = """
      H.fitFirstScreen(); const tight = snap();
      L.bottom = 700; H.fitFirstScreen(); const roomy = snap();
      return { tight, roomy, fitting: !!S.fitting };"""
    out = run(layout, script, realTop=True, topSaves=20)
    assert out["tight"]["fitted"] == ["space", "hint"] and out["tight"]["tops"] == 1
    assert out["roomy"]["fitted"] == [] and out["roomy"]["tops"] == 2 and out["fitting"] is False


RENDER_TOP = r"""
// renderTop 本身（FB-123）：重畫狀態列之前量 #top 的高度，重畫完交給 fitTopMoved
const code = fn("renderTop");
const top = { _html: "", offsetHeight: 120, hidden: false };
Object.defineProperty(top, "innerHTML", { get() { return this._html; }, set(v) { this._html = v; this.offsetHeight = v.length > 5 ? 300 : 120; } });
globalThis.document = { getElementById: (id) => (id === "top" ? top : null) };
const S = { prologueKey: "k" };
const seen = [];
const H = new Function("S", "prologueKey", "topHtml", "applyGlow", "render", "fitTopMoved", code + "\nreturn { renderTop };")(
  S, () => "k", () => input.html, () => {}, () => {}, (before) => seen.push([before, top.offsetHeight]));
H.renderTop();
finish(seen);
"""


@node
def test_render_top_hands_the_height_before_the_redraw_to_fit_top_moved():
    assert webharness.run(RENDER_TOP, {"html": "<div>展開的名號</div>"}) == [[120, 300]]
