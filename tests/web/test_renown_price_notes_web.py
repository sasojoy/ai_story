"""名聲複驗（2026-10-16）：價錢後面打折的原因在網頁上怎麼畫。
FB-296：鐵匠鋪店面「素材」頁的升階格子只寫「5 兩」，伺服器給了 cost_note（「（威震州郡・九折）」）網頁沒畫。
FB-297：375 寬折行斷在詞中間（「九／折」「八五／折」，宛城那顆三段的最後一行只剩「折））」）：每一段「稱號・N折」包成不折行的小段
（FB-132 的 .nb），字一個不改。真引擎的資料餵給 app.js 的假瀏覽器（tests/test_prologue_web.py、test_econ_web.py）。"""
from __future__ import annotations

import html
import random
import re
from pathlib import Path

import pytest
from conftest import no_week_unlock, real_content, renown_unscaled
from test_econ_web import _game as _econ_web_game
from test_econ_web import run as econ_run
from test_prologue_web import run as page_run

import server
import webharness
from tianxia.engine import Game

pytestmark = pytest.mark.skipif(webharness.NODE is None, reason="沒有 node，前端畫面測試略過")

ROOT = Path(__file__).parents[2]
HEAL = "醫館療傷（內傷 40・16 兩（自家地盤・九折，威震州郡・九折，一方豪俠・八五折））"


def _text(fragment: str) -> str:
    """拿掉標籤、還原跳脫：畫出來的字。"""
    return html.unescape(re.sub(r"<[^>]+>", "", fragment))


DEAL_DRIVER = r"""
const H = new Function(["esc", "DEAL_RE", "dealHtml"].map(konst).join("\n") + "\nreturn { dealHtml };")();
finish(H.dealHtml(input.text));
"""


def _deal(text: str) -> str:
    return webharness.run(DEAL_DRIVER, {"text": text})


@pytest.mark.parametrize("text, chunks", [
    (HEAL, ["（自家地盤・九折，", "威震州郡・九折，", "一方豪俠・八五折））"]),
    ("開爐・工錢 18 兩（威震州郡・九折）", ["（威震州郡・九折）"]),
    ("駑馬・100 兩（敵方地盤・貴兩成，名動一方・九四折）", ["（敵方地盤・貴兩成，", "名動一方・九四折）"]),
    ("內傷 40・20 兩", []),
])
def test_each_discount_reason_is_one_unbroken_chunk_and_no_word_changes(text, chunks):
    out = _deal(text)
    assert re.findall(r'<span class="nb">(.*?)</span>', out) == chunks
    assert _text(out) == text


def test_the_reasons_are_escaped_before_they_are_wrapped():
    out = _deal('<b>x</b>・九折&"')
    assert "<b>" not in out and _text(out) == '<b>x</b>・九折&"'


def econ_game(**kw):
    """test_econ_web 的店面角色，名聲門檻照原數（名望 50 是威震州郡・九折）：7 天季開季蓋的倍數 2.8 這裡不要。"""
    game = _econ_web_game(**kw)
    game.state.world.renown_scale = None
    return game


def _clinic_game():
    """正式內容、週末設定：潁川郡（醫館）、散人，名望 50（威震州郡・九折）、善名 30（州郡大俠・八五折）、內傷 40。"""
    c = renown_unscaled(no_week_unlock(real_content("week7")))
    c.config.auto_open_first_season = True
    game = Game.new(c, "沈浪", rng=random.Random(0))
    game.client = None
    p = game.state.player
    p.location, p.tutorial_step = "yingchuan", len(c.tutorial.steps)
    p.stats.update({"fame": 50, "good": 30, "silver": 100})
    p.member.injury = 40
    return game


def test_the_clinic_button_under_here_keeps_each_reason_whole():
    """「此地還能做」那一顆醫館療傷（閒著時在這裡）：每一段原因包成小段。"""
    game = _clinic_game()
    m = server.main_view(game)
    label = next(o["label"] for o in m["options"] if o["id"] == "act:heal")
    assert label.endswith("兩（威震州郡・九折，州郡大俠・八五折））")
    page = page_run(m, "return H.pageJianghu();")
    button = re.search(r'<button[^>]*data-id="act:heal"[^>]*>(.*?)</button>', page, re.S).group(1)
    assert '<span class="nb">（威震州郡・九折，</span><span class="nb">州郡大俠・八五折））</span>' in button
    assert _text(button).strip() == label


def test_a_choice_menu_label_keeps_each_reason_whole():
    """一組選項時（不是閒著的行動列）的鈕：同一個寫法。"""
    game = _clinic_game()
    m = server.main_view(game)
    m["options"] = [{"id": "act:heal", "label": HEAL, "enabled": True, "wait": "", "confirm": "", "confirm_yes": "", "tag": "", "note": ""}]
    page = page_run(m, "return H.pageJianghu();")
    assert '<span class="nb">（自家地盤・九折，</span><span class="nb">威震州郡・九折，</span><span class="nb">一方豪俠・八五折））</span>' in page


def test_the_forge_go_button_keeps_the_reason_whole():
    """店面打造的開爐鈕（旁邊有「鑄譜」，比較窄；FB-297 第二行只剩「折）」）。"""
    game = econ_game(faction=None, bag={"gang_1": 3, "kuai_1": 3})
    game.state.player.stats["fame"] = 50
    game.choose("act:smith")
    m = server.main_view(game)
    line = game.smith_line("劍", "gang_1", "kuai_1")
    assert line["ready"] and line["go"].endswith("（威震州郡・九折）")
    script = ("H.S.shopTab = 'forge'; H.S.shopPot = { slot: 'weapon', kind: '劍', main: 'gang_1', aux: 'kuai_1' };"
              " H.S.shopLine = H.S.next; H.render(); return T.els.app.innerHTML;")
    page = econ_run(m, script, S={"next": line})
    go = re.search(r'<button class="btn primary shop-go"[^>]*>(.*?)</button>', page, re.S).group(1)
    assert '兩<span class="nb">（威震州郡・九折）</span>' in go and _text(go) == line["go"]


def test_the_forge_go_button_is_one_wrapping_item_and_the_book_keeps_its_place():
    """FB-297 複驗沒過的那一顆：.btn 是不換行的橫向 flex，字與每一段小段各是一個 flex 項目——宛城兩段原因時鈕撐出 375、字被擠成直排、
    「鑄譜」被推出畫面。整段字包在一個 span 裡（flex 項目只有一個，字照常換行）；那一列的格子讓鈕那一欄縮得下（minmax(0, 1fr)），
    「鑄譜」那一欄照自己的寬度。"""
    game = econ_game(at="wan_city", faction="guan", bag={"gang_1": 3, "kuai_1": 3})
    game.state.player.stats["fame"] = 50
    game.choose("act:smith")
    m = server.main_view(game)
    line = game.smith_line("劍", "gang_1", "kuai_1")
    assert line["ready"] and line["go"].count("・") >= 3  # 開爐・工錢 N 兩（自家地盤・九折，威震州郡・九折）
    script = ("H.S.shopTab = 'forge'; H.S.shopPot = { slot: 'weapon', kind: '劍', main: 'gang_1', aux: 'kuai_1' };"
              " H.S.shopLine = H.S.next; H.render(); return T.els.app.innerHTML;")
    page = econ_run(m, script, S={"next": line})
    inner = re.search(r'<button class="btn primary shop-go"[^>]*>(.*?)</button>', page, re.S).group(1)
    assert re.fullmatch(r"<span>(?:(?!</?span>).|<span class=\"nb\">[^<]*</span>)*</span>", inner, re.S), inner  # 只有一個子元素
    assert _text(inner) == line["go"]
    row = page[page.index('class="shop-gorow"'):]
    assert row.index("shop-go") < row.index('data-act="book-open" data-book="forge"')  # 「鑄譜」跟開爐鈕同一列
    css = (ROOT / "web" / "style.css").read_text(encoding="utf-8")
    gorow = re.search(r"(?m)^\.shop-gorow \{([^}]*)\}", css).group(1)
    assert "grid-template-columns: minmax(0, 1fr) auto" in gorow


def test_the_horse_for_sale_keeps_the_reason_whole():
    """馬市待售那一間的價錢與原因。"""
    game = econ_game(at="wan_city", faction=None)
    game.state.player.stats["fame"] = 50
    game.choose("act:market")
    m = server.main_view(game)
    sale = next(h for h in m["shop"]["stalls"] if h.get("role") == "sale")
    assert sale["sub"].endswith("兩（威震州郡・九折）")
    page = econ_run(m, "H.render(); return T.els.app.innerHTML;")
    assert '兩<span class="nb">（威震州郡・九折）</span>' in page


def test_the_upgrade_cell_names_the_discount():
    """FB-296：素材頁的升階格子在價錢後面寫原因（同療傷、打造那幾處），原因照樣是不折行的小段。"""
    game = econ_game(faction=None, bag={"rou_1": 7})
    game.state.player.stats["fame"] = 50  # 威震州郡：九折；散人，沒有地盤那一半
    game.choose("act:smith")
    m = server.main_view(game)
    row = next(r for r in m["shop"]["trade"]["upgrade"] if (r["attribute"], r["tier"]) == ("柔", 2))
    assert row["cost_note"] == "（威震州郡・九折）"
    page = econ_run(m, 'H.S.shopTab = "trade"; H.render(); return T.els.app.innerHTML;')
    cell = page[page.index('data-attr="柔" data-tier="2"'):]
    cell = cell[:cell.index("</button>")]
    # 價錢自己也是一個不折行的小段（FB-410），原因接在後面
    assert f'<span class="nb">{row["cost"]} 兩</span><span class="nb">（威震州郡・九折）</span>' in cell
    plain = econ_game(faction=None, bag={"rou_1": 7})  # 沒打折：照舊只寫價錢
    plain.choose("act:smith")
    page = econ_run(server.main_view(plain), 'H.S.shopTab = "trade"; H.render(); return T.els.app.innerHTML;')
    cell = page[page.index('data-attr="柔" data-tier="2"'):]
    assert "兩（" not in cell[:cell.index("</button>")]
