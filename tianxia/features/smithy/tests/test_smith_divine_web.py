"""鐵匠鋪的「神器」頁（鐵匠鋪與合成流程 3.8，E 批網頁；企劃者 2026-10-29 三張對比圖選丙、「乙 守 5.10」）：
輪替季才有這一頁與架上那一行；上半「江湖已見」只列這一季已經有人打出原品的（加上只有自己看得到的「鑄譜上有・尚無人打出」），
下半收藏冊每一件一格，沒人打出過的畫「？」、不帶任何資料。這一季輪到、還沒人打出、自己也沒打中過的那一件，畫面上不出現它的名字。
資料是真的引擎給的（shopview.divine_view，test_shop2 的 _divine_ctx），畫面在 tests/test_shop_web.py 的假瀏覽器裡跑。"""
# 畫法在 web/smithy.js（全部拆包第 65 批從 app.js 切出來）；寫在這裡 test_for 改包檔時才挑得到
from __future__ import annotations

import pytest
from test_divine_rotation import SWORD, _forge_sword, _smith
from test_shop2 import _divine_ctx
from test_shop_web import _click, run

import server
import webharness

pytestmark = [pytest.mark.skipif(webharness.NODE is None, reason="沒有 node，前端畫面測試略過"), pytest.mark.whole_content]


def _shop_of(game):
    game.choose("act:smith")
    m = server.main_view(game)
    assert m["shop"] and m["shop"]["shop"] == "smith"
    return m


def _page(m, tab="divine", S=None, script="H.render(); return T.els.app.innerHTML;"):
    return run(m, script, S={"shopTab": tab, **(S or {})})


def _layer(html):
    """只看店面那一層（底下江湖頁的字不算）。"""
    return html[html.index('<div class="shop-layer'):]


def test_no_divine_page_or_shelf_line_outside_a_rotation_season(content, world):
    from test_shop import _smith as plain_smith

    m = server.main_view(plain_smith(content, world))
    assert m["shop"]["divine"] is None
    shelf = _page(m, "shelf")
    assert 'data-tab="divine"' not in shelf and "dv-link" not in shelf
    assert 'class="shop-tab on" data-act="shop-tab" data-tab="shelf"' in _page(m, "divine")  # 舊的分頁值：沒有這一頁就回架上


def test_a_fresh_rotation_season_draws_only_question_marks_and_no_lineup_name():
    """守 5.10：還沒人打出任何一件。江湖已見只寫一句，收藏冊 21 格全是「？」；這一季輪到的名單一個名字、一個 id 都不在畫面上。"""
    c, w = _divine_ctx()
    jia = _smith(c, w, "甲")
    m = _shop_of(jia)
    lineup = w.get_season().divine_lineup
    total = m["shop"]["divine"]["collected"]["total"]
    page, shelf = _layer(_page(m)), _layer(_page(m, "shelf"))
    assert "江湖已見" in page and "這一季江湖上還沒有人打出神器的原品。" in page
    assert page.count('<span class="dv-cell unknown">？</span>') == total == 21 and f"收藏 0／{total}" in page
    assert f'data-act="shop-tab" data-tab="divine">神器 收藏 0／{total} ›</button>' in shelf  # K 是 0：只寫收藏
    for html in (page, shelf):
        for rid in lineup:
            assert rid not in html and c.forge_secrets[rid].name not in html


def test_once_forged_the_seen_row_and_the_album_cell_appear():
    c, w = _divine_ctx()
    jia, yi = _smith(c, w, "甲"), _smith(c, w, "乙")
    _forge_sword(c, w, jia)
    name = c.forge_secrets[SWORD].name
    mine = _layer(_page(_shop_of(jia)))
    assert f"<b>【{name}】</b>" in mine and "原品在你手上・全服仿品 0 件" in mine and '<span class="dv-tag on">原品在手</span>' in mine
    assert f'<button class="dv-cell have dv-now" data-act="dv-cell" data-id="{SWORD}">{name}</button>' in mine  # 這一季打出的框粗、你有的亮
    theirs_m = _shop_of(yi)
    theirs = _layer(_page(theirs_m))
    assert "原品在甲手上・全服仿品 0 件" in theirs and '<span class="dv-tag">未有</span>' in theirs
    assert f'<button class="dv-cell dv-now" data-act="dv-cell" data-id="{SWORD}">{name}</button>' in theirs
    total = theirs_m["shop"]["divine"]["collected"]["total"]
    assert f">神器 江湖已見 1 件・收藏 0／{total} ›</button>" in _layer(_page(theirs_m, "shelf"))
    for rid in w.get_season().divine_lineup:  # 其餘八件照樣不露
        if rid != SWORD:
            assert c.forge_secrets[rid].name not in theirs


def test_a_copy_in_hand_says_so():
    c, w = _divine_ctx()
    jia, yi = _smith(c, w, "甲"), _smith(c, w, "乙")
    _forge_sword(c, w, jia)
    _forge_sword(c, w, yi)
    page = _layer(_page(_shop_of(yi)))
    assert "原品在甲手上・全服仿品 1 件" in page and '<span class="dv-tag on">仿品在手</span>' in page


def test_a_solved_only_row_shows_one_line_only_to_you():
    c, w = _divine_ctx()
    jia, yi = _smith(c, w, "甲"), _smith(c, w, "乙")
    other = next(rid for rid in w.get_season().divine_lineup if rid != SWORD)
    jia.state.player.divine_solved[other] = "某個組合"
    name = c.forge_secrets[other].name
    mine_m = _shop_of(jia)
    mine = _layer(_page(mine_m))
    assert f'<div class="dv-row solved"><b>【{name}】</b><small>鑄譜上有・尚無人打出</small></div>' in mine
    assert "這一季江湖上還沒有人打出神器的原品。" not in mine
    total = mine_m["shop"]["divine"]["collected"]["total"]
    assert f">神器 收藏 0／{total} ›</button>" in _layer(_page(mine_m, "shelf"))  # 鑄譜上的那一件不算「江湖已見」
    assert name not in _layer(_page(_shop_of(yi)))


def test_tapping_a_forged_cell_shows_its_line_from_the_book():
    """點收藏冊打出過的那一格：底下翻出神器譜那一行（/api/boards 的神器譜，照 ref「鑄|配方 id」認，用真的 divine_book_view）。"""
    c, w = _divine_ctx()
    jia, yi = _smith(c, w, "甲"), _smith(c, w, "乙")
    _forge_sword(c, w, jia)
    m = _shop_of(yi)
    book = yi.divine_book_view()
    row = next(r for r in book if r["ref"].endswith(SWORD))
    boards = {"boards": [{"id": "神器", "title": "神器譜", "note": "", "book": book}]}
    out = run(m, """return (async () => {
        H.render();
        """ + _click('{ act: "dv-cell", id: "%s" }' % SWORD) + """
        await new Promise((ok) => setTimeout(ok, 5));
        const shown = T.els.app.innerHTML;
        """ + _click('{ act: "dv-cell", id: "%s" }' % SWORD) + """
        return { shown, closed: T.els.app.innerHTML, calls: T.calls.map((c) => c[0]) };
      })();""", S={"shopTab": "divine"}, responses={"/api/boards": boards})
    assert out["calls"].count("/api/boards") == 1
    assert f'<p class="dv-line">第 {row["season"]} 季・{row["text"]}</p>' in out["shown"] and "dv-cell have dv-now on" not in out["shown"]
    assert f'data-id="{SWORD}">' in out["shown"] and 'class="dv-cell dv-now on"' in out["shown"]
    assert "dv-line" not in out["closed"]  # 再點一次收起


def test_a_tapped_cell_reads_the_book_again():
    """手上的榜單（S.boards）只在見聞→榜單、或手上沒有那一筆時才抓：之前看過榜單、之後別人又打了仿品，江湖已見那一列（輪詢的
    shop.divine）寫「全服仿品 3 件」、格子底下那一行還是舊的「仿品 0 把」。點一格就重抓一次神器譜（伺服器那一張不快取），照新的畫。"""
    c, w = _divine_ctx()
    jia, yi = _smith(c, w, "甲"), _smith(c, w, "乙")
    _forge_sword(c, w, jia)
    m = _shop_of(yi)
    book = yi.divine_book_view()
    row = next(r for r in book if r["ref"].endswith(SWORD))
    board = lambda rows: {"boards": [{"id": "神器", "title": "神器譜", "note": "", "book": rows}]}  # noqa: E731
    stale = board([{**row, "text": "舊的那一行"}])
    out = run(m, """return (async () => {
        H.render();
        """ + _click('{ act: "dv-cell", id: "%s" }' % SWORD) + """
        await new Promise((ok) => setTimeout(ok, 5));
        return { html: T.els.app.innerHTML, calls: T.calls.map((c) => c[0]) };
      })();""", S={"shopTab": "divine", "boards": stale}, responses={"/api/boards": board(book)})
    assert out["calls"].count("/api/boards") == 1
    assert f'<p class="dv-line">第 {row["season"]} 季・{row["text"]}</p>' in out["html"] and "舊的那一行" not in out["html"]


_SCROLL = """return (async () => {
    // 捲的那一層：底邊在分頁列頂上（320×700 實機量到 658）；翻出的那一行畫在整本收藏冊底下（739～769），畫上去了才找得到
    const line = { getBoundingClientRect: () => ({ top: %(top)s, bottom: %(bottom)s }) };
    const body = { scrollTop: 40, getBoundingClientRect: () => ({ top: 150, bottom: 658 }),
      querySelector: (s) => (s === ".dv-line" && T.els.app.innerHTML.includes('class="dv-line"') ? line : null) };
    T.qs[".shop-layer .shop-body"] = body;
    H.render();
    """ + _click('{ act: "dv-cell", id: "%(id)s" }') + """
    await new Promise((ok) => setTimeout(ok, 5));
    const opened = body.scrollTop;
    body.scrollTop = 40;
    """ + _click('{ act: "dv-cell", id: "%(id)s" }') + """
    return { opened, closed: body.scrollTop };
  })();"""


@pytest.mark.parametrize(("top", "bottom", "opened"), [(739, 769, 40 + 769 + 8 - 658), (600, 630, 40)])
def test_the_book_line_is_scrolled_above_the_tab_bar(top, bottom, opened):
    """點收藏冊一格翻出的那一行畫在整本收藏冊底下：小螢幕（320×700，375×667 照算的也一樣）或江湖已見的列多了，那一行落在捲的那一層的底邊
    （分頁列頂上）以下、看起來點了沒反應（審查 2026-11-01）。翻出來之後往下捲到那一行整個看得到（底下留 8px）；本來就看得到的不動，收起不捲。"""
    c, w = _divine_ctx()
    jia, yi = _smith(c, w, "甲"), _smith(c, w, "乙")
    _forge_sword(c, w, jia)
    m = _shop_of(yi)
    boards = {"boards": [{"id": "神器", "title": "神器譜", "note": "", "book": yi.divine_book_view()}]}
    out = run(m, _SCROLL % {"top": top, "bottom": bottom, "id": SWORD}, S={"shopTab": "divine"}, responses={"/api/boards": boards})
    assert out == {"opened": opened, "closed": 40}


def test_question_marks_carry_no_data():
    """收藏冊沒人打出過的格子：伺服器給的 id、name 都是 None；畫出來的「？」不可點、不帶任何 data（名單不能從屬性裡讀出來）。"""
    c, w = _divine_ctx()
    m = _shop_of(_smith(c, w, "甲"))
    page = _layer(_page(m))
    album = page[page.index('class="dv-album"'):]
    album = album[:album.index("</div>")]
    assert "data-" not in album and "<button" not in album


def test_no_album_cell_class_hits_a_site_wide_rule():
    """收藏冊的格子不能撞到全站沒加範圍的 class：江湖頁「剛剛」那張卡的 .now 帶 animation tx-now-rise（從透明浮上來）、邊框與底色，
    格子掛上它每次重畫（換頁、點格子、輪詢）都淡入一次。這一季打出的那一格用 dv-now（計畫 Global Constraints：新 class 加前綴）。"""
    import re

    c, w = _divine_ctx()
    jia = _smith(c, w, "甲")
    _forge_sword(c, w, jia)
    page = _layer(_page(_shop_of(jia)))
    album = page[page.index('class="dv-album"'):]
    classes = {k for cls in re.findall(r'class="(dv-cell[^"]*)"', album) for k in cls.split()}
    sheets = "\n".join(f.read_text(encoding="utf-8") for f in sorted(server.WEB.glob("*.css")))  # 頁面載的每一份樣式表
    bare = {k for k in classes if re.search(r"(?m)^\." + re.escape(k) + r"\s*[{,]", sheets)}  # 有一條就是這個 class 開頭、沒加範圍的
    assert "dv-now" in classes and "now" not in classes and not bare
    assert ".shop-layer .dv-cell.dv-now {" in (server.WEB / "smithy.css").read_text(encoding="utf-8")


# ── 收藏冊的樣子：企劃者 2026-11-03 從三張對比圖挑「乙 圓印」（原本做的是寫名字的方格）──


def test_the_album_is_round_seals_five_a_row():
    """一排五枚圓印；圓的大小寫 em（電腦寬跟著店面字級放大），字級不低於店面的下限（0.8em＝手機 12px）；
    有的亮、這一季打出的框粗、點著的外圈一道、沒人打出過的「？」虛線淡（照舊那幾個 class）。"""
    import re

    css = (server.WEB / "smithy.css").read_text(encoding="utf-8")
    album = re.search(r"\.shop-layer \.dv-album \{([^}]*)\}", css)
    assert album and "grid-template-columns: repeat(5, minmax(0, 1fr))" in album.group(1) and "justify-items: center" in album.group(1)
    cell = re.search(r"\.shop-layer \.dv-cell \{([^}]*)\}", css)
    assert cell and "border-radius: 50%" in cell.group(1) and "aspect-ratio: 1" in cell.group(1)
    size = re.search(r"width: min\(([0-9.]+)em, 100%\)", cell.group(1))
    font = re.search(r"font: ([0-9.]+)em/", cell.group(1))
    assert size and font and float(font.group(1)) >= 0.8  # 店面字級最低 12px（FB-305）


def test_a_long_name_folds_into_two_lines_in_its_seal():
    """圓裡一行放三個字：四個字以上的名字折成兩行（前一行多一個字），不縮字；三個字以內照舊一行、不多任何標記。
    名字照伺服器那一格給的（定名或譜名），網頁只決定在哪裡折。"""
    c, w = _divine_ctx()
    m = _shop_of(_smith(c, w, "甲"))
    cells = m["shop"]["divine"]["collected"]["cells"]
    names = ["寒星", "玄晶劍", "斷水流雲", "斷水流雲客", "千峰暮雪孤鴻"]
    for cell, name in zip(cells, names):
        cell.update({"id": f"wd_{len(name)}", "name": name, "forged": True})
    page = _layer(_page(m))
    want = {"寒星": "寒星", "玄晶劍": "玄晶劍", "斷水流雲": "斷水<br>流雲", "斷水流雲客": "斷水流<br>雲客", "千峰暮雪孤鴻": "千峰暮<br>雪孤鴻"}
    for name, html in want.items():
        assert f'data-id="wd_{len(name)}">{html}</button>' in page


def test_a_six_character_divine_name_folds_in_the_real_album():
    """真的引擎：原品定名六個字（玩家取名最多六個字，naming.NAME_MAX_CHARS），收藏冊那一枚折成三字兩行。"""
    from tianxia import forge_secrets

    c, w = _divine_ctx()
    jia = _smith(c, w, "甲")
    _forge_sword(c, w, jia)
    assert w.name_divine(forge_secrets.key_for(SWORD), "甲", "千峰暮雪孤鴻") is None
    page = _layer(_page(_shop_of(jia)))
    assert f'data-act="dv-cell" data-id="{SWORD}">千峰暮<br>雪孤鴻</button>' in page


def test_the_divine_tab_comes_last_and_has_no_weapon_armor_switch():
    c, w = _divine_ctx()
    m = _shop_of(_smith(c, w, "甲"))
    page = _layer(_page(m))
    import re

    tabs = re.findall(r'data-act="shop-tab" data-tab="(\w+)">([^<]+)</button>', page[page.index('<nav class="shop-tabs">'):])
    assert tabs[-1] == ("divine", "神器") and [k for k, _ in tabs[:3]] == ["shelf", "forge", "rack"]  # 排最後（素材開著時在它前面）
    assert len(m["shop"]["pages"]) > 1 and 'class="shop-pages"' not in page  # 神器不分兵器、防具：那一排切換不畫
