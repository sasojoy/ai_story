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


def test_the_craft_page_has_a_way_into_the_manual_and_it_opens_as_a_book_over_everything(made):
    """武學譜（status.manual；企劃者 2026-10-10「武學譜能不能獨立一頁，做得更豪華一些」）：煉製頁背包上面只放一個入口，
    寫幾則、參透幾則；點了開全螢幕的一本書（S.book），左上返回。一條秘方一頁，口訣照標點斷成一欄一段，合中了蓋朱印寫名號；
    沒聽過的不列、不寫還差幾句。"""
    game, art = made
    main = server.main_view(game)
    main["status"]["manual"] = [{"clues": ["風過山崗<留痕>，雲自回", "山不動而風自回"], "solved": None},
                                {"clues": ["火入水中"], "solved": "沸雪掌"}]
    out = run(main, """return (async () => {
      H.S.tab = "craft"; H.render();
      const page = H.pageCraft();
      const open = { dataset: { act: "book-open" }, classList: { contains: () => false } };
      await T.docListeners.click[0]({ target: { closest: () => open } });
      const opened = T.els.app.innerHTML;
      const back = { dataset: { act: "book-close" }, classList: { contains: () => false } };
      await T.docListeners.click[0]({ target: { closest: () => back } });
      return { page, opened, closed: T.els.app.innerHTML, book: H.S.book };
    })();""", menxia=server.menxia_view(game))
    page = out["page"]
    assert 'data-act="book-open"' in page and "收錄口訣 2 則・已參透 1" in page and page.index("武學譜") < page.index("背包")
    assert "風過山崗" not in page  # 口訣只在書裡
    book = out["opened"]
    assert 'class="book-layer"' in book and 'data-act="book-close"' in book and "本季所聞口訣 2 則・已參透 1 則" in book
    assert "<span>風過山崗&lt;留痕&gt;，</span><span>雲自回</span>" in book and "<span>山不動而風自回</span>" in book
    assert "第一則" in book and "第二則" in book and book.count('class="seal"') == 1 and 'aria-label="沸雪掌"' in book
    assert "合出<b>【沸雪掌】</b>" in book and "尚待參悟" in book
    assert 'class="book-layer"' not in out["closed"] and out["book"] is False


def test_an_empty_manual_says_so_without_hinting_at_any_recipe(made):
    game, art = made
    main = server.main_view(game)
    assert main["status"]["manual"] == []  # 測試內容沒有秘方
    out = run(main, "H.S.book = true; return { page: H.pageCraft(), book: H.bookHtml() };", S={"tab": "craft"}, menxia=server.menxia_view(game))
    assert "卷中尚無一字" in out["page"] and "卷中尚無一字" in out["book"] and "leaf empty" in out["book"] and "seal" not in out["book"]


def test_changing_tab_closes_the_book(made):
    game, art = made
    out = run(server.main_view(game), "return (async () => { await H.goTab(\"practice\"); return H.S.book; })();",
              S={"tab": "craft", "book": True}, menxia=server.menxia_view(game))
    assert out is False
