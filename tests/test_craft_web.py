"""煉製頁的網頁那一半（企劃者 2026-10-10「合成流程也很麻煩畫面跳來跳去……武學數量很多的時候，很難選，而且合過的意境不能合，
常常丟上去按合成才知道」）：合不了的灰掉、寫原因、點了只說為什麼；開爐之後頁面不捲、
結果寫在開爐底下、爐裡的東西留著。不替玩家列出合得出來的組合（企劃者同日退回：「這樣改不就變成玩家腦都不用動」）。
資料是真的引擎給的（skillview.forge_picks），畫面在 tests/test_prologue_web.py 的假瀏覽器裡跑。"""
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


def test_forging_keeps_the_pot_and_writes_the_result_under_the_button_without_scrolling(made):
    game, art = made
    after = server.menxia_view(game)
    out = run(server.main_view(game), """return (async () => {
      let scrolled = 0;
      T.ctx.window.scrollTo = () => { scrolled += 1; };
      const btn = { disabled: false, textContent: "開爐", classList: { add() {} } };
      const byId = T.ctx.document.getElementById;
      T.ctx.document.getElementById = (id) => (id === "forge" ? btn : byId(id));
      await H.forge();
      return { html: H.pageCraft(), calls: T.calls.map((c) => c[0]), body: (T.calls.find((c) => c[0] === "/api/menxia/forge") || [])[1], result: H.S.forgeResult, sel: H.S.forgeSel.length, scrolled };
    })();""", S={"tab": "craft", "forgeSel": [{"type": "art", "id": "basic_fist"}, {"type": "ins", "id": "huo"}]},
        menxia=server.menxia_view(game),
        responses={"/api/menxia/forge": {"menxia": after, "message": "<p>煉成了。</p>", "main": server.main_view(game)},
                   "/api/forge_line": {"line": "", "picks": None}})
    assert out["calls"].count("/api/menxia/forge") == 1 and out["body"]["art"] == "basic_fist" and out["body"]["insights"] == ["huo"]
    assert out["calls"][-1] == "/api/forge_line"  # 心得、體力變了：重問說明
    assert out["result"] == {"html": "<p>煉成了。</p>"} and out["sel"] == 2  # 爐裡的東西留著，換一格就能再合
    assert out["html"].index('id="forge"') < out["html"].index("煉成了。")  # 結果寫在開爐底下
    assert "現在合得出來的" not in out["html"] and "idea-forge" not in out["html"]  # 不替玩家列答案（企劃者 2026-10-10 退回）
    assert out["scrolled"] == 0  # 不跳到最上面


def test_the_forge_line_endpoint_gives_marks_only(made, monkeypatch):
    game, art = made
    monkeypatch.setattr(server, "look", lambda g, view: view(g))
    monkeypatch.setattr(server, "_game", lambda request: game)
    one = server.api_forge_line(None, {"insights": ["feng"]})
    assert one["picks"]["arts"]["basic_fist"]["short"] == "已經有了" and "ideas" not in one
    empty = server.api_forge_line(None, {})
    assert empty["picks"] is None and "ideas" not in empty


def test_the_manual_lists_only_the_clues_heard_and_what_was_solved(made):
    """武學譜（status.manual，PM 2026-10-10 派工）：煉製頁背包上面一個摺疊，一條秘方一格，聽過的口訣一句一行，合中了寫名號；
    沒聽過的不列、不寫還差幾句。開合記在 S.manualOpen（煉製頁常重畫）。"""
    game, art = made
    main = server.main_view(game)
    main["status"]["manual"] = [{"clues": ["風過山崗<留痕>", "山不動而風自回"], "solved": None},
                                {"clues": ["火入水中"], "solved": "沸雪掌"}]
    shut = run(main, "return H.pageCraft();", S={"tab": "craft"}, menxia=server.menxia_view(game))
    assert '<details class="fold manual">' in shut and "武學譜" in shut and "2 條・參透 1" in shut
    assert "「風過山崗&lt;留痕&gt;」" in shut and "「山不動而風自回」" in shut and "尚未參透" in shut
    assert "已參透：合出【沸雪掌】" in shut
    assert shut.index("武學譜") < shut.index("背包")
    opened = run(main, "return H.pageCraft();", S={"tab": "craft", "manualOpen": True}, menxia=server.menxia_view(game))
    assert '<details class="fold manual" open>' in opened


def test_an_empty_manual_says_so_without_hinting_at_any_recipe(made):
    game, art = made
    main = server.main_view(game)
    assert main["status"]["manual"] == []  # 測試內容沒有秘方
    html = run(main, "return H.pageCraft();", S={"tab": "craft"}, menxia=server.menxia_view(game))
    assert "還沒記下任何口訣" in html and "manual-row" not in html
