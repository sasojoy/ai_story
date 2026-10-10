"""煉製頁的網頁那一半（企劃者 2026-10-10「合成流程也很麻煩畫面跳來跳去……武學數量很多的時候，很難選，而且合過的意境不能合，
常常丟上去按合成才知道」）：合不了的灰掉、寫原因、點了只說為什麼；「現在合得出來的」一列一組、點「開爐」就合；開爐之後頁面不捲、
結果寫在按的地方旁邊。資料是真的引擎給的（skillview.forge_picks／forge_ideas），畫面在 tests/test_prologue_web.py 的假瀏覽器裡跑。"""
from __future__ import annotations

from unittest import mock

import pytest
from test_prologue_web import run

import server
import webharness
from tianxia import fusion, naming

pytestmark = pytest.mark.skipif(webharness.NODE is None, reason="沒有 node，前端畫面測試略過")


def named(name):
    client = mock.Mock()
    client.chat_structured.return_value = naming.NameReply(name=name, description="一句話說明。")
    return client


@pytest.fixture
def made(game):
    """手上有基礎拳腳、風、火，已經合過【旋風腿】（基礎拳腳＋風）。"""
    p = game.state.player
    p.member.wugong_id = "basic_fist"
    p.insights = ["feng", "huo"]
    p.stats["xinde"] = 100
    art, _ = fusion.fuse(game.state, game.content, game.world, named("旋風腿"), "basic_fist", "feng")
    return game, art


def test_with_an_insight_in_the_pot_the_arts_that_cannot_take_it_are_greyed_with_a_reason(made):
    game, art = made
    picks = game.forge_picks(None, ["feng"])
    S = {"tab": "craft", "forgeSel": [{"type": "ins", "id": "feng"}], "forgePicks": picks}
    out = run(server.main_view(game), """
      const html = H.pageCraft();
      H.pick("art", "basic_fist");
      return { html, sel: H.S.forgeSel.length, toast: T.els.toast.textContent };
    """, S=S, menxia=server.menxia_view(game))
    assert '<i class="why">已經有了</i>' in out["html"] and '<i class="why">來歷裡融過</i>' in out["html"]
    assert out["html"].count('class="chip r1 no"') + out["html"].count('class="chip r2 no"') >= 2
    assert out["sel"] == 1 and "你已經有了" in out["toast"]  # 點了不放進去，說整句


def test_only_what_fits_can_be_shown(made):
    game, art = made
    S = {"tab": "craft", "forgeSel": [{"type": "ins", "id": "feng"}], "forgePicks": game.forge_picks(None, ["feng"]),
         "craftView": {"attr": "", "quality": "", "sort": "", "okOnly": True, "all": False}}
    html = run(server.main_view(game), "return H.pageCraft();", S=S, menxia=server.menxia_view(game))
    assert "只看合得了的" in html and 'data-id="basic_fist"' not in html and f'data-id="{art.id}"' not in html


def test_the_ideas_list_and_one_tap_forges_without_scrolling(made):
    game, art = made
    ideas = game.forge_ideas()
    after = server.menxia_view(game)
    out = run(server.main_view(game), """return (async () => {
      const html = H.pageCraft();
      let scrolled = 0;
      T.ctx.window.scrollTo = () => { scrolled += 1; };
      const btn = { dataset: { act: "idea-forge" }, disabled: false, textContent: "開爐", classList: { add() {} } };
      H.ideaToPot(H.S.forgeIdeas.items[0]);
      await H.forge(btn);
      return { html, calls: T.calls.map((c) => c[0]), body: T.calls[0][1], result: H.S.forgeResult, sel: H.S.forgeSel.length, scrolled };
    })();""", S={"tab": "craft", "forgeIdeas": ideas}, menxia=server.menxia_view(game),
        responses={"/api/menxia/forge": {"menxia": after, "message": "<p>煉成了。</p>", "main": server.main_view(game)},
                   "/api/forge_line": {"line": "", "picks": None, "ideas": ideas}})
    assert "現在合得出來的" in out["html"] and "沒人合過" in out["html"] and 'data-act="idea-forge"' in out["html"]
    first = ideas["items"][0]
    assert out["calls"][0] == "/api/menxia/forge" and out["body"] == {"art": first["art"], "other_art": first["other_art"], "insights": first["insights"]}
    assert out["calls"][-1] == "/api/forge_line"  # 爐空了：重問「現在合得出來的」
    assert out["result"] == {"at": "ideas", "html": "<p>煉成了。</p>"} and out["sel"] == 0
    assert out["scrolled"] == 0  # 不跳到最上面


def test_the_forge_line_endpoint_gives_marks_and_ideas(made, monkeypatch):
    game, art = made
    monkeypatch.setattr(server, "look", lambda g, view: view(g))
    monkeypatch.setattr(server, "_game", lambda request: game)
    one = server.api_forge_line(None, {"insights": ["feng"]})
    assert one["picks"]["arts"]["basic_fist"]["short"] == "已經有了" and "ideas" not in one
    empty = server.api_forge_line(None, {})
    assert empty["picks"] is None and empty["ideas"] == game.forge_ideas() and empty["ideas"]["total"] > 0
