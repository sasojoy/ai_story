"""找素材分支的畫面（第 32 項，計畫 2.1 甲）：探索卡上「找素材」是展開鈕，點開了在它底下攤一排分支，最後一顆「自己說…」叫出輸入框、
送 /api/do/gather_text。餵真的引擎資料給 app.js（tests/test_prologue_web.py 的假瀏覽器）。沒有 node 就略過。"""
from __future__ import annotations

import random

import pytest
from conftest import real_content
from jianfa_kit import classic_explore
from test_prologue_web import DRIVER as BASE_DRIVER

import server
import webharness
from tianxia.engine import Game
from tianxia.sqlite_world import open_world
import re
from pathlib import Path

pytestmark = pytest.mark.skipif(webharness.NODE is None, reason="沒有 node，前端畫面測試略過")

DRIVER = BASE_DRIVER.replace('"bookHtml", "peerHtml"]', '"bookHtml", "peerHtml", "gatherSay", "gatherWheel"]')
assert DRIVER != BASE_DRIVER


def run(m, script, *, S=None, responses=None):
    return webharness.run(DRIVER, {"m": m, "script": script, "S": S or {}, "menxia": None, "stored": {}, "responses": responses or {}})


def _main(at="deep_mountain", stamina=250.0):
    c = classic_explore(real_content("week7"))  # 找素材分支是探索三選一的（減法季探索一顆開著時沒有）
    c.config.auto_open_first_season = True
    game = Game.new(c, "沈浪", rng=random.Random(0), world=open_world())
    game.client = None
    p = game.state.player
    p.location, p.stamina = at, stamina
    p.tutorial_step = len(c.tutorial.steps)
    return server.main_view(game)


def _bar(m, **S):
    return run(m, "return H.actionBar(H.S.main);", S={"wheelSel": "explore", **S})


def test_gather_is_a_wheel_and_folds_its_branches():
    m = _main()
    bar = _bar(m)
    assert 'data-act="gather-wheel"' in bar and 'aria-expanded="false"' in bar
    assert 'data-id="explore:gather:mine"' not in bar and 'data-act="choose" data-id="explore:gather"' not in bar
    assert "此地還能做" not in bar or "挖礦" not in bar  # 分支不掉進「此地還能做」
    assert all(f'data-id="explore:{x}"' in bar for x in ("seek", "sense", "practice"))


def test_opening_gather_lays_out_the_branches_and_the_say():
    bar = _bar(_main(), gatherOpen=True)
    assert 'class="gather-branches"' in bar and 'aria-expanded="true"' in bar
    for b in ("mine", "hunt", "deep", "say"):
        assert f'data-id="explore:gather:{b}"' in bar
    assert "<b>挖礦</b>" in bar and '<span class="nb">體力 6・</span>' in bar
    assert bar.index("gather-head") < bar.index("gather-branches") < bar.index('data-id="explore:seek"')  # 緊接在找素材底下


def test_saying_swaps_the_button_for_a_box():
    bar = _bar(_main(), gatherOpen=True, gatherSaying=True)
    assert 'id="gather-say-form"' in bar and 'maxlength="20"' in bar
    assert 'data-id="explore:gather:say"' not in bar and 'data-id="explore:gather:mine"' in bar


def test_a_tired_player_cannot_open_the_branches():
    bar = _bar(_main(stamina=3.0), gatherOpen=True)
    assert "gather-branches" not in bar  # 探索入口灰著：整張卡不畫


def test_one_branch_keeps_the_plain_gather_button():
    bar = _bar(_main("yingshui"), gatherOpen=True)
    assert 'data-act="choose" data-id="explore:gather"' in bar and "gather-wheel" not in bar


@pytest.mark.slow  # 單一條超過一秒（2026-10-31 測試自檢 T-01 量的；這個檔以前整個標 slow）
def test_the_box_sends_the_line_to_gather_text():
    m = _main()
    out = run(m, """return (async () => {
      const form = { querySelectorAll: () => [], querySelector: () => ({ textContent: "" }) };
      await H.gatherSay(form, "敲開山岩找鐵砂");
      return { calls: T.calls.filter((c) => c[0].startsWith("/api/do/")), saying: H.S.gatherSaying, open: H.S.gatherOpen };
    })();""", S={"wheelSel": "explore", "gatherOpen": True, "gatherSaying": True},
              responses={"/api/do/gather_text": {"main": m, "message": "你：「敲開山岩找鐵砂」（成算六成）"}})
    assert out["calls"] == [["/api/do/gather_text", {"text": "敲開山岩找鐵砂"}]]
    assert out["saying"] is False and out["open"] is True  # 分支展開照記著，輸入框收起


# ── 原 test_fb460_gather_say_hint.py（整檔搬進來） ──
# FB-460（第 32 項 QA，2026-10-20）：找素材「自己說」輸入框的提示字在 320 寬被切到「沿著獸徑」，也沒寫 20 字內。
# 這一格縮在分支那一排裡，比事件的隨口應對、對話的自己說窄。餵真的引擎資料給 app.js（test_gather_branches_web 的假瀏覽器）；
# CSS 在 node 裡排不了版，寬度照字數粗估（實機量的在回饋單裡）。沒有 node 就略過。

# QA 在 320 寬量到的：輸入框扣掉內距剩 152 像素，提示字 16px（一個全形字 16 像素）
NARROW_BOX = 152


def _placeholder(bar: str) -> str:
    found = re.search(r'id="gather-say-form"><input [^>]*placeholder="([^"]*)"', bar)
    assert found, "找不到找素材「自己說」的輸入框"
    return found.group(1)


def _width(text: str, em: float = 16.0) -> float:
    """粗估一行字的寬：全形字一個 em，半形（數字、英文）0.6 em——偏寬估，寧可多算。"""
    return sum(em if ord(ch) > 0xFF else em * 0.6 for ch in text)


def test_hint_says_twenty_characters_like_the_other_boxes():
    hint = _placeholder(_bar(_main(), gatherOpen=True, gatherSaying=True))
    assert hint.endswith("（20字內）")  # 同事件隨口應對「…（20字內）」、對話「想對他說的話（20字內）」


def test_hint_fits_the_box_at_320():
    hint = _placeholder(_bar(_main(), gatherOpen=True, gatherSaying=True))
    assert _width(hint) <= NARROW_BOX, (hint, _width(hint))  # 修前「怎麼找？例：沿著獸徑找落羽」208 像素


# ── 原 test_fb461_gather_odd_branches.py（整檔搬進來） ──
# FB-461（第 32 項 QA，2026-10-20）：有三條分支的地方（北邙山、嵩山深處、綠林山寨、燕山腳），分支兩欄排，「深入」旁邊空一格。
# 單數條時最後一條佔整列。餵真的引擎資料給 app.js（test_gather_branches_web 的假瀏覽器）；CSS 在 node 裡排不了版，讀 style.css 的
# 那一條規則。沒有 node 就略過。

CSS = (Path(__file__).resolve().parents[2] / "web" / "style.css").read_text(encoding="utf-8")


def _branch_classes(bar: str) -> dict[str, list[str]]:
    found = re.findall(r'<button class="btn gather-branch([^"]*)" data-act="choose" data-id="explore:gather:(\w+)"', bar)
    return {branch: extra.split() for extra, branch in found}


def test_odd_branches_last_one_takes_the_row():
    classes = _branch_classes(_bar(_main(), gatherOpen=True))  # 嵩山深處：挖礦、狩獵、深入
    assert set(classes) == {"mine", "hunt", "deep", "say"}
    assert "wide" in classes["deep"]
    assert "wide" not in classes["mine"] and "wide" not in classes["hunt"] and "wide" not in classes["say"]


def test_odd_branches_while_saying_too():
    classes = _branch_classes(_bar(_main(), gatherOpen=True, gatherSaying=True))  # 「自己說…」換成輸入框，深入照樣佔整列
    assert "say" not in classes and "wide" in classes["deep"]


def test_odd_branches_without_the_say_button():
    m = _main()
    m["options"] = [o for o in m["options"] if o["id"] != "explore:gather:say"]  # Config.gather_branches.say_enabled 關著
    classes = _branch_classes(_bar(m, gatherOpen=True))
    assert set(classes) == {"mine", "hunt", "deep"} and "wide" in classes["deep"]


def test_even_branches_stay_two_by_two():
    classes = _branch_classes(_bar(_main("songshan_foot"), gatherOpen=True))  # 嵩山腳兩條
    assert len([k for k in classes if k != "say"]) == 2
    assert not any("wide" in c for c in classes.values())


def test_the_wide_branch_spans_both_columns():
    rule = re.search(r"([^{}]*\.gather-branch\.wide[^{}]*)\{([^}]*)\}", CSS)
    assert rule, "style.css 沒有 .gather-branch.wide 的規則"
    assert re.search(r"grid-column:\s*1\s*/\s*-1", rule.group(2))
