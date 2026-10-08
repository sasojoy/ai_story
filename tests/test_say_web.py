"""對話「自己說」的網頁那一半：選單上那一顆按了才換成 20 字的輸入框（照隨口應對），送出走 /api/say，等的時候寫「對方沉吟中…」；
交談結束、選單上沒有那一顆了，輸入框跟著收起。餵真的引擎給的 /api/main（tests/test_prologue_web.py 的假瀏覽器）。沒有 node 就略過。"""
from __future__ import annotations

from unittest import mock

import pytest
from test_prologue_web import run

import server
import webharness
from tianxia import companion_agent
from tianxia.engine import Game

pytestmark = pytest.mark.skipif(webharness.NODE is None, reason="沒有 node，前端畫面測試略過")


@pytest.fixture
def talking(monkeypatch):
    monkeypatch.setattr(server.CONTENT.config, "auto_open_first_season", True)  # 正式內容預設要管理者開季
    game = Game.new(server.CONTENT, "測試")
    p = game.state.player
    p.location, p.fortune = "luzhi_camp", True
    p.flags.add("結識:luzhi")
    turn = companion_agent.CompanionTurn(narrative="他點了點頭。", options=["閒聊幾句", "就此告辭"], option_tags=["尋常寒暄", "尋常寒暄"])
    with mock.patch.object(companion_agent, "generate_turn", return_value=turn):
        server.choose(game, "act:socialize")
    assert game.state.player.pending_companion == "luzhi"
    return server.main_view(game)


def test_the_say_button_turns_into_a_box_only_when_pressed(talking):
    plain = run(talking, "return H.pageJianghu();")
    assert 'data-id="talk:say"' in plain and "自己說…" in plain and 'id="say-form"' not in plain
    opened = run(talking, "return H.pageJianghu();", S={"saying": True})
    assert 'id="say-form"' in opened and 'maxlength="20"' in opened and 'data-id="talk:say"' not in opened


def test_sending_a_line_posts_it_and_closes_the_box(talking):
    after = {**talking, "options": [o for o in talking["options"] if o["id"] != "talk:say"]}
    out = run(talking, """return (async () => {
      const el = () => ({ disabled: false, textContent: "" });
      const btn = el();
      const form = { querySelectorAll: () => [el(), btn], querySelector: () => btn };
      await H.sayLine(form, "久仰大名");
      return { calls: T.calls, saying: H.S.saying };
    })();""", S={"saying": True}, responses={"/api/say": {"main": after}})
    assert any(url.startswith("/api/say") and "久仰大名" in str(body) for url, body in out["calls"])
    assert not out["saying"]
