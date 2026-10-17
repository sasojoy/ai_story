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


def test_forging_empties_the_pot_and_writes_the_result_under_the_button_without_scrolling(made):
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
        responses={"/api/menxia/forge": {"menxia": after, "message": "<p>煉成了。</p>", "main": server.main_view(game), "made": True},
                   "/api/forge_line": {"line": "", "picks": None}})
    assert out["calls"].count("/api/menxia/forge") == 1 and out["body"]["art"] == "basic_fist" and out["body"]["insights"] == ["huo"]
    assert out["calls"][-1] == "/api/forge_line"  # 心得、體力變了：重問說明
    assert out["result"] == {"html": "<p>煉成了。</p>"} and out["sel"] == 0  # 合成了：兩格清空（Joy 2026-10-12）
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


def test_the_forge_book_sits_beside_the_arts_book_and_shows_the_mix_once_solved(made):
    """鑄譜（status.forge_manual；打造隱藏配方設計 6.3）：入口擺在武學譜旁邊，點了開同一本線裝書（S.book 記開哪一本）；打中過的蓋朱印、
    寫名字，另外寫出配方；只聽過口訣的不寫配方。"""
    game, art = made
    main = server.main_view(game)
    main["status"]["forge_manual"] = [
        {"clues": ["那劍客的劍軟如柳條，一閃比燕子還快。"], "solved": "柳影劍", "recipe": "劍：柳絲綿＋驚羽"},
        {"clues": ["刀要沉，精鐵砂是少不了的。"], "solved": None, "recipe": None},
    ]
    out = run(main, """return (async () => {
      H.S.tab = "craft"; H.render();
      const page = H.pageCraft();
      const open = { dataset: { act: "book-open", book: "forge" }, classList: { contains: () => false } };
      await T.docListeners.click[0]({ target: { closest: () => open } });
      return { page, opened: T.els.app.innerHTML, book: H.S.book };
    })();""", menxia=server.menxia_view(game))
    page = out["page"]
    assert page.count('data-act="book-open"') == 2 and 'data-book="forge"' in page and "收錄鑄訣 2 則・已參透 1" in page
    assert page.index("武學譜") < page.index("鑄譜") < page.index("背包")
    book = out["opened"]
    assert out["book"] == "forge" and 'aria-label="鑄譜"' in book and "本季所聞鑄訣 2 則・已參透 1 則" in book
    assert "打出<b>【柳影劍】</b>" in book and '<p class="leaf-recipe">劍：柳絲綿＋驚羽</p>' in book
    assert book.count('class="leaf-recipe"') == 1 and "尚待參悟" in book  # 沒打中的不寫配方
    assert "<span>那劍客的劍軟如柳條，</span><span>一閃比燕子還快。</span>" in book  # 口訣照標點斷成一欄一段（同武學譜）


def test_an_empty_forge_book_hints_at_smiths_and_tales_only(made):
    game, art = made
    main = server.main_view(game)
    assert main["status"]["forge_manual"] == []  # 測試內容沒有隱藏配方
    out = run(main, 'H.S.book = "forge"; return H.bookHtml();', S={"tab": "craft"}, menxia=server.menxia_view(game))
    assert "卷中尚無一字" in out and "失傳的鑄法" in out and "合成的門道" not in out and "seal" not in out


def test_the_next_season_question_says_the_forge_secrets_change():
    """打造隱藏配方設計 10.3：「開啟下一季」的問句提一句鑄法換一批、鑄譜與神器重來、神器譜留著。"""
    js = (server.ROOT / "web" / "app.js").read_text(encoding="utf-8")
    question = js.split("next_season: [", 1)[1].split('"確定開啟下一季"', 1)[0]
    assert "鐵匠鋪的隱藏鑄法換一批、鑄譜與神器重來（神器譜留著）" in question


def test_the_engine_says_what_it_forged_and_the_page_finds_it_in_the_lists(made):
    """開爐成了，煉製頁在結果底下畫合出來的那一樣（Joy 2026-10-17）：Game.forged_thing 是 ("art"／"ins", id)，
    id 在 menxia_view 的 owned_arts／insights 裡找得到；被拒絕是 None。"""
    game, art = made
    game.forge("basic_fist", ["huo"], proposed=("烈焰拳", "一句話說明。"))
    kind, art_id = game.forged_thing
    assert kind == "art" and any(r["id"] == art_id for r in server.menxia_view(game)["owned_arts"])
    game.forge(None, ["feng", "huo"], proposed=("風火意", "一句話說明。"))
    kind, ins_id = game.forged_thing
    assert kind == "ins" and any(r["id"] == ins_id for r in server.menxia_view(game)["insights"])
    game.forge("basic_fist", ["feng"], proposed=("旋風腿", ""))  # 已經有了：被拒絕
    assert game.forged is False and game.forged_thing is None


def test_a_new_art_shows_its_card_under_the_result_with_power_and_how_it_compares(made):
    game, art = made
    game.forge("basic_fist", ["huo"], proposed=("烈焰拳", "一句話說明。"))
    menxia = server.menxia_view(game)
    row = next(r for r in menxia["owned_arts"] if r["id"] == game.forged_thing[1])
    row["judge"]["traits"] = [{"name": "剛猛", "layers": 2, "tier": 3}]  # 檔次由平衡那邊接上：帶了就寫
    row["judge"]["worn_diff"] = -3.5
    html = run(server.main_view(game), "return H.pageCraft();", menxia=menxia,
               S={"tab": "craft", "forgeSel": [], "forgeResult": {"html": "<p>煉成了。</p>"}, "forgeMade": {"type": "art", "id": row["id"]}})
    card = html.split('class="made-card"', 1)[1]
    assert html.index('id="forge"') < html.index('class="made-card"') < html.index("煉成了。")  # 卡在結果那段話前面
    assert "【烈焰拳】" in card and f"威力<b>{row['judge']['power']:g}</b>" in card and "比身上那門弱 −3.5" in card
    assert "<em>精</em>剛猛<small>2 層</small>" in card and "整張功法卡" in card
    assert ('data-act="switch"' in card) is (not row["worn"])


def test_a_merged_insight_shows_its_card_too(made):
    game, art = made
    game.forge(None, ["feng", "huo"], proposed=("風火意", "一句話說明。"))
    html = run(server.main_view(game), "return H.pageCraft();", menxia=server.menxia_view(game),
               S={"tab": "craft", "forgeSel": [], "forgeResult": {"html": "<p>合成了。</p>"}, "forgeMade": {"type": "ins", "id": game.forged_thing[1]}})
    assert 'class="made-card"' in html and "「風火意」" in html.split('class="made-card"', 1)[1]


def test_the_pot_bar_holds_both_slots_and_the_forge_button_and_flashes_what_was_just_put_in(made):
    """爐子兩格與開爐鈕一直看得到（Joy 2026-10-17）：固定列寫兩格放了什麼（點了拿出來）、開爐鈕；剛放進去的那一格閃一下；
    說明那一行有 ⚠ 時固定列底下也寫一行。"""
    game, art = made
    out = run(server.main_view(game), """
      H.S.forgeSel = [{ type: "ins", id: "huo" }];
      H.pick("art", "basic_fist");
      return { html: H.pageCraft(), drawn: T.els.page.innerHTML };
    """, S={"tab": "craft", "forgeSel": [], "forgeLine": "<p>合成 …</p><p>⚠ 心得不夠。</p>"}, menxia=server.menxia_view(game),
        responses={"/api/forge_line": {"line": "", "picks": None}})
    bar = out["html"].split('class="kiln-bar"', 1)[1].split('class="label"', 1)[0]
    assert bar.count('data-act="unslot"') == 2 and 'id="forge"' in bar and "<b>粗淺拳腳</b>" in bar and "<b>火</b>" in bar
    assert "⚠ 心得不夠。" in bar
    assert 'kiln-slot full r1 flash" data-act="unslot" data-i="0"' in out["drawn"]  # 武學放左邊那一格，放進去那一下閃
