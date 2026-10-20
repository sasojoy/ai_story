"""第 9 批畫面：銀兩出口收成一間新店「打點」（企劃者挑乙：茶樓雅間的掮客，五樣記在一本攤開的帳簿上；設計 9.1）。
只在 21 天季；週末與 14 天的季沒有這間店。動作照舊送原本的選項 id。"""
from __future__ import annotations

import pytest
from test_silver_outlets import _game as _in_shop

import server
import webharness
from tianxia import silver


def _game(*args, **kwargs):
    """站在店外（test_silver_outlets._game 會先進店）。"""
    game = _in_shop(*args, **kwargs)
    if game.state.player.picking_dadian:
        game.choose("dadian:back")
    return game


def _ids(game):
    return {o.id: o for o in game.options()}


def _entries(view):
    return {e["name"]: e for page in view["pages"] for e in page["entries"]}


def test_the_outlets_fold_into_one_dadian_button():
    game = _game(at="wan_city")  # 宛城：官軍大本營、醫館、鐵匠鋪
    opts = _ids(game)
    assert opts["act:dadian"].label == "打點" and opts["act:dadian"].enabled
    assert not any(i in opts for i in ("act:silver_donate", "act:mentor", "act:furnace", "act:buy_legend"))
    stamina = game.state.player.stamina
    game.choose("act:dadian")
    inside = _ids(game)
    assert {"act:silver_donate", "act:mentor", "act:furnace", "act:buy_legend", "dadian:back"} <= set(inside)
    assert game.state.player.stamina == stamina


def test_the_shop_lists_all_five_and_strikes_what_is_elsewhere():
    game = _game(at="dajiangjun_fu")  # 大將軍府：官軍大本營，沒有醫館、鐵匠鋪（輿圖重製第 1 批：v1 是長社）
    game.choose("act:dadian")
    view = game.shop_view()
    assert view["shop"] == "dadian" and view["sign"] == "打點" and view["back"] == "dadian:back" and view["line"]
    assert [p["head"] for p in view["pages"]] == ["修為", "人情"]
    rows = _entries(view)
    assert {"名師指點", "看火候", "捐銀兩"} <= set(rows) and any(n.startswith("買") for n in rows)
    assert not rows["名師指點"]["ok"] and rows["名師指點"]["id"] is None and rows["名師指點"]["note"] == silver.WHERE["mentor"]
    assert rows["捐銀兩"]["ok"] and rows["捐銀兩"]["id"] == "act:silver_donate"


def test_a_ranger_is_told_to_join_before_donating():
    game = _game(at="wan_city", faction=None)
    game.choose("act:dadian")
    rows = _entries(game.shop_view())
    assert rows["捐銀兩"]["note"] == silver.WHERE["donate_ranger"]


def test_each_figure_here_gets_a_bribe_entry():
    game = _game(at="changshe")
    game.choose("act:dadian")
    view = game.shop_view()
    bribes = [e for e in view["pages"][1]["entries"] if e["name"].startswith("打點門路・")]
    assert bribes and all(e["id"].startswith("act:bribe:") and e["ok"] for e in bribes)
    assert {e["id"] for e in bribes} <= set(_ids(game))


def test_acting_in_the_shop_keeps_it_open_and_hangs_what_is_owed():
    game = _game(at="wan_city")
    game.choose("act:dadian")
    game.choose("act:mentor")
    view = game.shop_view()
    assert view["shop"] == "dadian" and view["hang"] == silver.HANG_HEAD + silver.HANG_MENTOR
    row = _entries(view)["名師指點"]
    assert not row["ok"] and row["note"] == silver.MENTOR_READY
    game.choose("dadian:back")
    assert game.shop_view() is None and not game.state.player.picking_dadian


def test_leaving_the_place_closes_the_shop():
    game = _game(at="wan_city")
    game.choose("act:dadian")
    game.state.player.location = "yingshui"  # 管理者挪人：這裡一樣都做不了
    game.sync(game.now)
    assert not game.state.player.picking_dadian


def test_weekend_has_no_dadian():
    game = _game("weekend", at="wan_city")
    assert "act:dadian" not in _ids(game)


# ── 網頁 ──

web = pytest.mark.skipif(webharness.NODE is None, reason="沒有 node，前端畫面測試略過")


def _shop_run(m, script):
    from test_shop2_web import DRIVER

    driver = DRIVER.replace('"shopHtml", ', '"shopHtml", "dadianHtml", ', 1)
    return webharness.run(driver, {"m": m, "script": script, "S": {}, "menxia": None, "stored": {}, "responses": {}})


@web
def test_the_ledger_draws_two_pages_and_strikes_what_is_elsewhere():
    game = _game(at="dajiangjun_fu")
    game.choose("act:dadian")
    m = server.main_view(game)
    html = _shop_run(m, "H.render(); return T.els.app.innerHTML;")
    assert 'class="shop-layer shop-dadian"' in html and 'class="ledger"' in html
    assert html.count('class="ledger-page"') == 2 and "修為" in html and "人情" in html
    assert 'data-act="choose" data-id="act:silver_donate"' in html  # 這裡做得了的送原本的選項 id
    assert 'class="entry off"' in html and silver.WHERE["mentor"] in html  # 這裡做不了的劃掉、批去哪做
    assert 'data-act="choose" data-id="dadian:back"' in html


@web
def test_the_ledger_writes_what_is_owed_underneath():
    game = _game(at="wan_city")
    game.choose("act:dadian")
    game.choose("act:mentor")
    m = server.main_view(game)
    html = _shop_run(m, "H.render(); return T.els.app.innerHTML;")
    assert '<p class="ledger-hang">' in html and silver.HANG_MENTOR in html


@web
def test_the_ledger_text_breaks_only_between_phrases():
    """FB-411：375 寬一頁 176px，說明斷在詞中間（「最／多打點到 40」「今天還能／捐 1000 兩」「下 35／／中 40」）：帳上的字照「，・；／：」
    與「（」切成不折行的小段（同 FB-132 的 .nb），「情誼 0 → 5」這種不在箭頭那裡切開。"""
    import re

    game = _game(at="wan_city", money=2000)
    game.choose("act:dadian")
    html = _shop_run(server.main_view(game), "H.render(); return T.els.app.innerHTML;")
    assert re.search(r'<span class="nb">\w+的門房：</span><span class="nb">情誼 \d+ → \d+，</span><span class="nb">最多打點到 \d+</span>', html)
    assert re.search(r'<span class="nb">這一下捐 \d+ 兩・</span><span class="nb">今天還能捐 \d+ 兩</span>', html)
    assert re.search(r'<span class="nb">下 \d+／</span><span class="nb">中 \d+／</span><span class="nb">上 \d+</span>', html)


@web
def test_the_broker_line_breaks_only_between_phrases():
    """FB-433：店上面掮客那一句在 360、320 寬斷在「您／挑」「寫／著」中間：照 FB-297 切成不折行的小段，切在「，。：；！？」後面，
    緊跟著的收引號併進前一段（「」」不落單）；字一個不改。"""
    game = _game(at="wan_city")
    game.choose("act:dadian")
    m = server.main_view(game)
    m["shop"]["line"] = "掮客撥了兩下算盤：「要辦什麼事，帳上都寫著，您挑。」"
    html = _shop_run(m, "H.render(); return T.els.app.innerHTML;")
    assert ('<p class="shop-line"><span class="nb">掮客撥了兩下算盤：</span><span class="nb">「要辦什麼事，</span>'
            '<span class="nb">帳上都寫著，</span><span class="nb">您挑。」</span></p>') in html


def test_the_ledger_stacks_its_pages_below_360():
    """FB-411：比 360 窄時兩頁放不下，改成上下兩頁（第二頁的左邊線換成上邊線）；360 以上照舊並排。"""
    from pathlib import Path

    css = (Path(__file__).resolve().parent.parent / "web" / "style.css").read_text(encoding="utf-8")
    narrow = css.split("@media (max-width: 359px)")[1].split("\n}\n")[0]
    assert ".shop-layer.shop-dadian .ledger { grid-template-columns: 1fr; }" in narrow
    assert ".shop-layer.shop-dadian .ledger-page + .ledger-page {" in narrow and "border-top" in narrow


def test_the_ledger_css_keeps_text_at_twelve_px_and_has_a_desktop_column():
    import re
    from pathlib import Path

    css = (Path(__file__).resolve().parent.parent / "web" / "style.css").read_text(encoding="utf-8")
    sizes = [float(x) for x in re.findall(r"\.shop-dadian[^{]*\{[^}]*?font(?:-size)?:[^;}]*?(\d+(?:\.\d+)?)px", css)]
    assert sizes and min(sizes) >= 12
    assert ".shop-layer.shop-dadian" in css.split("@media (min-width: 641px)")[1]  # 電腦上底色只畫中間那一欄（FB-225）
