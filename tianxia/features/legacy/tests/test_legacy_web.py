"""傳承頁、識海頁（web/app.js 的 legacyHtml、legacyPageHtml；樣子在 web/legacy.css）：企劃者 2026-11-04「要有真的傳承、識海的感覺」。

- 展開屬性裡一行入口（三項的值；識海封著東西時多一行名字），按了打開傳承頁。
- 傳承頁：三卷（墨水漲到值、到了的門蓋朱印）、每一項三片竹簡（開了的亮、沒開的寫還差多少）、按一片看那一道門的長句、入識海的入口。
- 識海頁：封著的意境與三道封印；全破了、身上沒有神品，「破封」才按得下；被人先取了名，改列候選；
  開季還沒挑的候選（封進識海、這一季不帶），有候選時進遊戲第一個畫面自己打開識海頁一次（企劃者 2026-11-05）。
切 app.js 裡傳承那一段（從「// 傳承（features/legacy」到名號那一塊的註解）放進 node 跑。"""
from __future__ import annotations

import re

import pytest

import webharness

pytestmark = pytest.mark.skipif(webharness.NODE is None, reason="沒有 node，前端畫面測試略過")

DRIVER = r"""
const a = src.indexOf("\n  // 傳承（features/legacy；main.legacy）");
const b = src.indexOf("\n  // 狀態列的名號那一塊");
if (a < 0 || b < a) throw new Error("app.js 裡找不到傳承那一段");
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const S = input.S;
eval(src.slice(a, b) + "\nglobalThis.__L = { legacyHtml, legacyPageHtml, legacyOfferOpen };");
if (input.what === "auto") { __L.legacyOfferOpen(); const first = S.legacy; S.legacy = null; __L.legacyOfferOpen(); finish([first, S.legacy]); }
else finish(input.what === "entry" ? __L.legacyHtml(S.main.legacy) : __L.legacyPageHtml());
"""


def _track(values):
    texts = {"zheng": ("書院", "俠義", "敬俠"), "xie": ("綠林", "狠辣", "喜狠"), "luck": ("頓悟", "奇遇", "長篇")}
    return {k: [{"at": at, "text": f"{texts[k][i]}長句", "short": texts[k][i], "open": values[k] >= at}
                for i, at in enumerate((5, 10, 20))] for k in texts}


def _legacy(values=None, sealed=True, need_ok=(True, False, False), held=False, names=(), offers=()):
    values = values or {"zheng": 12, "xie": 3, "luck": 7}
    keys = ("time", "level", "xinde")
    return {
        "values": values, "gains": {"zheng": 4, "xie": 0, "luck": 3}, "opened": [], "tracks": _track(values),
        "sealed": "寒江獨照" if sealed else None,
        "shihai": {
            "sealed": {"name": "寒江獨照", "attribute": "冰", "season": 2, "names": list(names)} if sealed else None,
            "need": [{"key": k, "text": f"條件{k}", "ok": ok, "now": f"現在{k}"} for k, ok in zip(keys, need_ok)],
            "held": held, "offers": [{"name": n, "attribute": "風", "season": 8} for n in offers],
        },
    }


def run(legacy, view=None, what="page", slip=None):
    S = {"main": {"legacy": legacy}, "legacy": view, "legacySlip": slip}
    return webharness.run(DRIVER, {"S": S, "what": what})


def text(html: str) -> str:
    return re.sub(r"<[^>]+>", "", html)


def test_the_entry_line_opens_the_page_and_names_the_sealed_one():
    html = run(_legacy(), what="entry")
    assert 'data-act="legacy-open"' in html
    assert "正氣 12" in text(html) and "邪氣 3" in text(html) and "機緣 7" in text(html)
    assert "識海封著：寒江獨照" in text(html)
    assert "識海封著" not in text(run(_legacy(sealed=False), what="entry"))


def test_the_legacy_page_has_three_scrolls_and_nine_slips():
    html = run(_legacy(), "main")
    assert html.count('class="lg-scroll"') == 3
    assert html.count('data-act="legacy-slip"') == 9
    assert html.count('class="lg-slip open"') == 3  # 正氣 5、10；機緣 5
    assert html.count('class="lg-seal-on"') == 3
    assert "差八" in text(html)  # 正氣 20 還差 8
    assert "上一季 +4" in text(html) and "上一季 —" in text(html)
    assert 'data-act="legacy-view" data-v="shihai"' in html
    assert "寒江獨照" in text(html) and "還有 2 道" in text(html)


def test_tapping_a_slip_shows_its_long_line():
    html = run(_legacy(), "main", slip="zheng:2")
    assert "敬俠長句" in text(html) and "還差 8" in text(html)
    assert 'data-k="zheng:2" aria-pressed="true"' in html


def test_the_unseal_button_waits_for_all_three_seals():
    html = run(_legacy(), "shihai")
    assert html.count('class="lg-seal"') == 2 and html.count('class="lg-seal broken"') == 1
    assert re.search(r'data-id="legacy:open" disabled', html)
    ready = run(_legacy(need_ok=(True, True, True)), "shihai")
    assert 'data-id="legacy:open" >' in ready
    held = run(_legacy(need_ok=(True, True, True), held=True), "shihai")
    assert 'data-id="legacy:open" disabled' in held and "先放掉那一份" in text(held)


def test_a_taken_name_lists_the_candidates_instead():
    html = run(_legacy(need_ok=(True, True, True), names=("寒江照影", "孤江獨照")), "shihai")
    assert 'data-id="legacy:name:0"' in html and 'data-id="legacy:name:1"' in html
    assert 'data-id="legacy:open"' not in html


def test_the_season_start_offers_and_opens_once():
    html = run(_legacy(sealed=False, offers=("斷雲", "孤鴻")), "shihai")
    assert "識海空空" in text(html) and "前世帶來的神品" in text(html)
    assert 'data-id="legacy:seal:0"' in html and 'data-id="legacy:seal:1"' in html and 'data-id="legacy:skip"' in html
    assert "第八季" in text(html)
    none = run(_legacy(sealed=False), "shihai")
    assert "legacy:seal" not in none and "每一季開季時" in text(none)
    assert run(_legacy(sealed=False, offers=("斷雲",)), what="auto") == ["shihai", None]  # 打開一次，關掉不再自己跳
    assert run(_legacy(sealed=False), what="auto") == [None, None]
