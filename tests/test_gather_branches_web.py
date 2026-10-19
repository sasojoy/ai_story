"""找素材分支的畫面（第 32 項，計畫 2.1 甲）：探索卡上「找素材」是展開鈕，點開了在它底下攤一排分支，最後一顆「自己說…」叫出輸入框、
送 /api/do/gather_text。餵真的引擎資料給 app.js（tests/test_prologue_web.py 的假瀏覽器）。沒有 node 就略過。"""
from __future__ import annotations

import random

import pytest
from conftest import real_content
from test_prologue_web import DRIVER as BASE_DRIVER

import server
import webharness
from tianxia.engine import Game
from tianxia.sqlite_world import open_world

pytestmark = [pytest.mark.skipif(webharness.NODE is None, reason="沒有 node，前端畫面測試略過"), pytest.mark.slow]

DRIVER = BASE_DRIVER.replace('"bookHtml", "peerHtml"]', '"bookHtml", "peerHtml", "gatherSay", "gatherWheel"]')
assert DRIVER != BASE_DRIVER


def run(m, script, *, S=None, responses=None):
    return webharness.run(DRIVER, {"m": m, "script": script, "S": S or {}, "menxia": None, "stored": {}, "responses": responses or {}})


def _main(at="deep_mountain", stamina=250.0):
    c = real_content("weekend")
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
