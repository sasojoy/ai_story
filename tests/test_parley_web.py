"""開口求人第二批的網頁那一半：商量打法（talk:plan）與帶路路上（parley:road）跟「自己說」共用同一個輸入框，
提示換成那一顆的說法，送出時 /api/say 帶著是哪一顆。餵真的引擎給的 /api/main（tests/test_prologue_web.py 的假瀏覽器）。沒有 node 就略過。"""
from __future__ import annotations

from unittest import mock

import pytest
from test_prologue_web import run

import server
import webharness
from tianxia import companion_agent, parley
from tianxia.engine import PLAN_OPTION, Game
from tianxia.state import ParleyBacking

pytestmark = pytest.mark.skipif(webharness.NODE is None, reason="沒有 node，前端畫面測試略過")


@pytest.fixture
def planning(monkeypatch):
    monkeypatch.setattr(server.CONTENT.config, "auto_open_first_season", True)
    monkeypatch.setattr(server.CONTENT.config.parley, "enabled", True)
    game = Game.new(server.CONTENT, "測試")
    p = game.state.player
    p.location, p.fortune = "luzhi_camp", True
    p.flags.add("結識:luzhi")
    turn = companion_agent.CompanionTurn(narrative="他點了點頭。", options=["閒聊幾句", "就此告辭"], option_tags=["尋常寒暄", "尋常寒暄"])
    with mock.patch.object(companion_agent, "generate_turn", return_value=turn):
        server.choose(game, "act:socialize")
    game.state.player.parley_backing = ParleyBacking(figure="luzhi", region=None, day=parley.game_day(game.content, game.state.world))
    view = server.main_view(game)
    assert any(o["id"] == PLAN_OPTION for o in view["options"])
    return view


def test_the_plan_button_opens_the_same_box_with_its_own_hint(planning):
    plain = run(planning, "return H.pageJianghu();")
    assert f'data-id="{PLAN_OPTION}"' in plain and 'id="say-form"' not in plain
    opened = run(planning, "return H.pageJianghu();", S={"saying": PLAN_OPTION})
    assert 'id="say-form"' in opened and "跟他說你想好的打法" in opened and f'data-id="{PLAN_OPTION}"' not in opened
    assert 'data-id="talk:say"' in opened  # 自己說那一顆照舊是一顆鈕


def test_sending_the_plan_tells_the_server_which_box(planning):
    out = run(planning, """return (async () => {
      const el = () => ({ disabled: false, textContent: "" });
      const btn = el();
      const form = { querySelectorAll: () => [el(), btn], querySelector: () => btn };
      await H.sayLine(form, "將軍從左翼包抄");
      return { calls: T.calls };
    })();""", S={"saying": PLAN_OPTION}, responses={"/api/say": {"main": planning}})
    assert any(url.startswith("/api/say") and PLAN_OPTION in str(body) and "將軍從左翼包抄" in str(body) for url, body in out["calls"])
