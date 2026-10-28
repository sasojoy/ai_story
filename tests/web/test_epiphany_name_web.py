"""神品意境「自己取一個名字…」（FB-901）：按了不送 /api/choose，就地換成六字的輸入框，送出時 /api/choose 帶 text。
以前這一顆按下去只回一句「（寫下你替它取的名字。）」寫進江湖紀錄，網頁上沒有輸入框、也沒人收那個 text，等於按不動。
餵真的引擎資料給 app.js（假瀏覽器）。"""
from __future__ import annotations

from unittest import mock

import pytest
from jianfa_kit import jianfa_game, ready
from test_prologue_web import DRIVER as BASE_DRIVER

import server
import webharness
from tianxia import epiphany, storyline, team
from tianxia.encounter import EncounterResult
from tianxia.rules import day_seconds

pytestmark = [pytest.mark.skipif(webharness.NODE is None, reason="沒有 node，前端畫面測試略過"), pytest.mark.slow]

DRIVER = BASE_DRIVER.replace('"bookHtml", "peerHtml"]', '"bookHtml", "peerHtml", "godName", "choose"]')
assert DRIVER != BASE_DRIVER

OWN = f"{epiphany.OPTION}:{epiphany.OWN}"


def run(m, script, *, S=None, responses=None):
    return webharness.run(DRIVER, {"m": m, "script": script, "S": S or {}, "menxia": None, "stored": {}, "responses": responses or {}})


def _naming_game():
    """走完一條特殊頓悟的線（拷問全選第一個、靜候一日、打贏心魔），停在「替這個境界取個名字」。"""
    game = ready(jianfa_game(), side="guan", loc="yingshui")
    game.content.config.epiphany.enabled = True
    with mock.patch.object(epiphany, "_trial", return_value=("wait", epiphany.TRIALS["wait"][0], -1)):
        game._epiphany_begin("剛", "潁水河畔")
    line = next(iter(game.state.player.storylines))
    for _ in range(epiphany.ASKED + 1):
        game.choose(f"{storyline.OPTION}:{line}:a0")
    game.state.world.time += day_seconds(game.content, game.state.world)
    game._story_tick()
    with mock.patch.object(team, "fight", return_value=EncounterResult(tier="大勝", margin=50, our_power=200, difficulty=40)):
        game.choose(f"{storyline.OPTION}:{line}")
    game._story_tick()
    assert game.state.player.god_naming is not None
    return game


def test_the_server_hands_the_typed_name_to_the_engine(monkeypatch):
    """/api/choose 收 text、原樣交給引擎（以前 server.choose 根本沒有這個參數，玩家打的字到不了引擎）。"""
    game = _naming_game()
    monkeypatch.setattr(server, "act", lambda g, action, **kw: action(g))
    assert server.choose(game, OWN) == [epiphany.NAME_OWN_ASK]  # 沒帶字：只叫出輸入框
    server.choose(game, OWN, text="寒江獨照")
    assert any(i.name == "寒江獨照" for i in game.state.player.own_insights.values())
    assert game.state.player.god_naming is None


def test_pressing_own_name_opens_a_box_instead_of_sending():
    m = server.main_view(_naming_game())
    assert any(o["id"] == OWN and o["enabled"] for o in m["options"])
    out = run(m, f"""return (async () => {{
      await H.choose({{ classList: {{ add() {{}} }} }}, "{OWN}");
      return {{ calls: T.calls.filter((c) => c[0].startsWith("/api/")).map((c) => c[0]), naming: H.S.godNaming, page: H.pageJianghu() }};
    }})();""")
    assert "/api/choose" not in out["calls"] and out["naming"] is True
    page = out["page"]
    assert 'id="own-name-form"' in page and 'maxlength="6"' in page
    assert f'data-act="choose" data-id="{OWN}"' not in page  # 那一顆換成輸入框


def test_the_box_sends_the_name_with_the_choose_call():
    m = server.main_view(_naming_game())
    # 取成了：那一顆不在選單上。story_cards 清掉——那是「此事已了」的跳顯框，假瀏覽器沒有 document.body.appendChild
    done = {**m, "options": [o for o in m["options"] if o["id"] != OWN], "story_cards": []}
    out = run(m, """return (async () => {
      const form = { querySelectorAll: () => [], querySelector: () => null, dataset: {} };
      await H.godName(form, "寒江獨照");
      return { calls: T.calls.filter((c) => c[0] === "/api/choose"), naming: H.S.godNaming };
    })();""", S={"godNaming": True}, responses={"/api/choose": {"main": done}})
    assert out["calls"] == [["/api/choose", {"id": OWN, "text": "寒江獨照"}]]
    assert out["naming"] is False  # 輸入框收起


def test_a_refused_name_keeps_the_box():
    """名字不合格、這一季全服撞名：伺服器回那一句、選項還在，輸入框留著（字也放回去，改一改再送）。"""
    m = {**server.main_view(_naming_game()), "story_cards": []}
    out = run(m, """return (async () => {
      const form = { querySelectorAll: () => [], querySelector: () => null, dataset: {} };
      await H.godName(form, "斷水流雲");
      return H.S.godNaming;
    })();""", S={"godNaming": True}, responses={"/api/choose": {"main": m, "message": epiphany.NAME_TAKEN}})
    assert out is True
