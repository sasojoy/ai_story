"""託付的畫面（減法季批 6，FB-829）：此地的「勸降」按了就地換成二十字的輸入框、送 POST /api/do/persuade_text；
託付的信卡畫那一件（做什麼、到哪裡、期限）與「婉拒」，婉拒走引擎原有的 letter_decline。餵真的引擎資料給 app.js（假瀏覽器）。"""
from __future__ import annotations

import pytest
from stances_kit import LUZHI, real_game
from test_prologue_web import DRIVER as BASE_DRIVER

import server
import webharness
from tianxia import errands, letters

pytestmark = [pytest.mark.skipif(webharness.NODE is None, reason="沒有 node，前端畫面測試略過"), pytest.mark.slow]

DRIVER = BASE_DRIVER.replace('"bookHtml", "peerHtml"]', '"bookHtml", "peerHtml", "persuadeSay", "letterHtml", "choose"]')
assert DRIVER != BASE_DRIVER


def run(m, script, *, S=None, responses=None):
    return webharness.run(DRIVER, {"m": m, "script": script, "S": S or {}, "menxia": None, "stored": {}, "responses": responses or {}})


def _persuade_game(at_spot=True):
    g = real_game()
    g.state.player.affinities[LUZHI] = 50
    errands.give(g.state, g.content, LUZHI, "luzhi_persuade")
    e = g.state.player.errands[-1]
    if at_spot:
        g.state.player.location = e.target
    return g, e


def test_pressing_persuade_opens_a_box_instead_of_sending():
    g, e = _persuade_game()
    m = server.main_view(g)
    oid = f"errand:persuade:{e.id}"
    assert any(o["id"] == oid and o["enabled"] for o in m["options"])
    out = run(m, f"""return (async () => {{
      await H.choose({{ classList: {{ add() {{}} }} }}, "{oid}");
      return {{ calls: T.calls.filter((c) => c[0].startsWith("/api/")).map((c) => c[0]), persuading: H.S.persuading, bar: H.actionBar(H.S.main) }};
    }})();""")
    assert "/api/choose" not in out["calls"] and out["persuading"] == oid
    bar = out["bar"]
    assert 'id="persuade-form"' in bar and f'data-id="{e.id}"' in bar and 'maxlength="20"' in bar
    assert f'data-act="choose" data-id="{oid}"' not in bar  # 那一顆換成輸入框
    assert '<details class="fold here" open' in bar  # 收在「此地還能做」裡也攤開


def test_the_box_sends_the_line_to_persuade_text():
    g, e = _persuade_game()
    m = server.main_view(g)
    oid = f"errand:persuade:{e.id}"
    out = run(m, f"""return (async () => {{
      const form = {{ dataset: {{ id: "{e.id}" }}, querySelectorAll: () => [], querySelector: () => ({{ textContent: "" }}) }};
      await H.persuadeSay(form, "放下刀槍，回家種田吧");
      return {{ calls: T.calls.filter((c) => c[0].startsWith("/api/do/")), persuading: H.S.persuading }};
    }})();""", S={"persuading": oid}, responses={"/api/do/persuade_text": {"main": m, "message": "你：「放下刀槍，回家種田吧」（多半能成）"}})
    assert out["calls"] == [["/api/do/persuade_text", {"id": e.id, "text": "放下刀槍，回家種田吧"}]]
    assert out["persuading"] is False


def test_a_refused_line_keeps_the_box():
    g, e = _persuade_game()
    m = server.main_view(g)
    oid = f"errand:persuade:{e.id}"
    out = run(m, f"""return (async () => {{
      const form = {{ dataset: {{ id: "{e.id}" }}, querySelectorAll: () => [], querySelector: () => ({{ textContent: "" }}) }};
      await H.persuadeSay(form, "x");
      return H.S.persuading;
    }})();""", S={"persuading": oid}, responses={"/api/do/persuade_text": {"main": m, "message": errands.PERSUADE_ASK}})
    assert out == oid


def test_the_errand_letter_shows_the_task_and_a_decline():
    g, e = _persuade_game(at_spot=False)
    m = server.main_view(g)
    card = m["letter"]
    assert card["kind"] == "託付" and card["task"] is None and card["errand"]["status"] == "open"
    html = run(m, "return H.letterHtml(H.S.main.letter);", S={"letterOpen": card["id"]})
    assert f'data-act="letter-decline" data-id="{card["id"]}"' in html and "婉拒" in html
    assert card["errand"]["text"] in html and card["errand"]["deadline"] in html
    msgs = server.MAIN_ACTIONS["letter_decline"](g, {"id": card["id"]})
    assert msgs and msgs[0] != letters.NO_LETTER and e.status == "declined"
