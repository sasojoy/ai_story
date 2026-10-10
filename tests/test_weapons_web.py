"""兵器的網頁那一半（兵器設計 3.6）：修練頁的兵器塊——身上那把、裝備庫每把一行與「換上」鈕；字都跳脫；沒東西就不畫。
餵真的引擎給的 /api/main 與 /api/menxia 給 app.js（tests/test_prologue_web.py 的假瀏覽器）。沒有 node 就略過。"""
from __future__ import annotations

import random

import pytest
from test_prologue_web import run

import server
import webharness
from tianxia.engine import Game

pytestmark = pytest.mark.skipif(webharness.NODE is None, reason="沒有 node，前端畫面測試略過")


def _row(**over):
    return {"id": "兵:1", "name": "試刃", "kind": "劍", "attribute": "柔", "tier": 1, "quality": "下品",
            "edge": 80, "fits": True, "bonus": "+4.5%", **over}


@pytest.fixture
def views(hints_content, world):
    game = Game.new(hints_content, "沈浪", rng=random.Random(0), world=world)
    game.skip_tutorial()
    return server.main_view(game), server.menxia_view(game)


def test_the_practice_page_draws_the_worn_weapon_and_the_rack(views):
    m, x = views
    x["weapons"] = {"worn": _row(), "cap": 6, "rack": [_row(id="兵:2", name="<b>厚背刀</b>", kind="刀", fits=False, bonus=None)]}
    page = run(m, "return H.pagePractice();", menxia=x)
    assert 'class="weapons"' in page and "【試刃】" in page and "鋒利度 80" in page and "威力 +4.5%" in page
    assert page.count('data-act="wield"') == 1 and 'data-id="兵:2"' in page  # 身上那把不用換上
    assert "裝備庫 1/6" in page and "用不上" in page
    assert "<b>厚背刀</b>" not in page and "&lt;b&gt;厚背刀&lt;/b&gt;" in page  # 名字跳脫


def test_the_wield_button_sends_the_weapon_id(views):
    m, x = views
    x["weapons"] = {"worn": None, "cap": 6, "rack": [_row(id="兵:2")]}
    page = run(m, "return H.pagePractice();", menxia=x)
    assert "手上沒有兵器" in page and 'data-act="wield"' in page


def test_nothing_is_drawn_without_weapons(views):
    m, x = views
    assert "class=\"weapons\"" not in run(m, "return H.pagePractice();", menxia=x)  # 測試內容把兵器關著
    x["weapons"] = {"worn": None, "rack": [], "cap": 6}
    assert 'class="weapons"' not in run(m, "return H.pagePractice();", menxia=x)
    del x["weapons"]  # 舊的伺服器沒有這一欄
    assert 'class="weapons"' not in run(m, "return H.pagePractice();", menxia=x)


def test_a_long_rack_lists_eight_and_then_a_more_button(views):
    m, x = views
    rack = [_row(id=f"兵:{i + 2}", name=f"備刃{i}") for i in range(12)]
    x["weapons"] = {"worn": _row(), "cap": 100, "rack": rack}
    page = run(m, "return H.pagePractice();", menxia=x)
    assert page.count('data-act="wield"') == 8 and "備刃7" in page and "備刃8" not in page
    assert 'data-act="rack-all"' in page and "再列 4 件" in page and "裝備庫 12/100" in page
    everything = run(m, "return H.pagePractice();", menxia=x, S={"rackAll": True})  # 按了「再列」之後全部攤開
    assert everything.count('data-act="wield"') == 12 and "rack-all" not in everything and "再列" not in everything
    x["weapons"]["rack"] = rack[:8]  # 剛好八把：不必多按一次
    short = run(m, "return H.pagePractice();", menxia=x)
    assert short.count('data-act="wield"') == 8 and "再列" not in short


def test_every_rack_row_has_a_dismantle_button_and_the_worn_one_does_not(views):
    m, x = views
    x["weapons"] = {"worn": _row(), "cap": 100, "rack": [_row(id="兵:2", name="<i>厚背刀</i>"), _row(id="兵:3", name="備刃", fits=False, bonus=None)]}
    page = run(m, "return H.pagePractice();", menxia=x)
    assert page.count('data-act="dismantle"') == 2 and 'data-act="dismantle" data-id="兵:2"' in page and 'data-act="dismantle" data-id="兵:3"' in page
    assert page.count('data-act="wield"') == 2  # 換上照舊
    assert "<i>厚背刀</i>" not in page and "&lt;i&gt;厚背刀&lt;/i&gt;" in page
    x["weapons"]["rack"] = []
    assert 'data-act="dismantle"' not in run(m, "return H.pagePractice();", menxia=x)  # 身上那把不能拆


def _weapons_block(page):
    return page.split('class="weapons"')[1].split("</section>")[0]


def test_rack_rows_keep_both_buttons_together_and_show_the_grade(views):
    """FB-125：「換上」「拆解」包在同一個不折行的容器裡（不會折到下一把的名字上），每列寫階與品質，拆解帶著問句。"""
    m, x = views
    ask = "把【厚背刀】（二階中品）拆成玄鋼骨×1？拆掉就沒了。"
    x["weapons"] = {"worn": _row(grade="一階下品", confirm=""), "cap": 100,
                    "rack": [_row(id="兵:2", name="厚背刀", grade="二階中品", confirm=ask)]}
    block = _weapons_block(run(m, "return H.pagePractice();", menxia=x))
    assert block.count('class="wbtns"') == 1  # 只有裝備庫那一列有鈕
    assert "二階中品" in block and "一階下品" in block
    assert f'data-confirm="{ask}"' in block


_DISMANTLE_CLICK = """return (async () => {
  const click = (dataset) => T.docListeners.click[0]({ target: { closest: () => ({ dataset, classList: { contains: () => false, add() {}, remove() {} } }) } });
  T.qs['.ask [data-act="ask-no"]'] = { focus() {} };
  await click({ act: "dismantle", id: "兵:2", confirm: "把【厚背刀】（一階下品）拆成精鐵砂×1？拆掉就沒了。" });
  const asked = T.bodyHtml.join("");
  const before = T.calls.map((c) => c[0]);
  %(then)s
  return { asked, before, calls: T.calls.map((c) => [c[0], c[1]]) };
})();"""


def test_dismantle_asks_first_and_sends_only_on_yes(views):
    m, x = views
    x["weapons"] = {"worn": None, "cap": 100, "rack": [_row(id="兵:2", name="厚背刀", grade="一階下品", confirm="問")]}
    reply = {"/api/menxia/dismantle": {"menxia": x, "message": "", "main": m}}
    out = run(m, _DISMANTLE_CLICK % {"then": 'await click({ act: "ask-no" });'}, menxia=x, responses=reply)
    assert "拆成精鐵砂×1" in out["asked"] and "拆掉" in out["asked"]
    assert out["before"] == [] and out["calls"] == []  # 問了；取消之後什麼都沒送
    out = run(m, _DISMANTLE_CLICK % {"then": 'await click({ act: "ask-yes" });'}, menxia=x, responses=reply)
    assert [c[0] for c in out["calls"]] == ["/api/menxia/dismantle"] and out["calls"][0][1]["weapon"] == "兵:2"


_CHOOSE_CLICK = """return (async () => {
  const click = (act, id) => T.docListeners.click[0]({ target: { closest: () => ({ dataset: { act, id }, classList: { contains: () => false, add() {}, remove() {} } }) } });
  T.qs['.ask [data-act="ask-no"]'] = { focus() {} };
  await click("choose", "smith:dismantle:兵:2");
  return { asked: T.bodyHtml.join(""), calls: T.calls.map((c) => c[0]) };
})();"""


def test_a_smith_dismantle_option_asks_with_its_own_yes_word(views):
    m, _ = views
    m = {**m, "options": [{"id": "smith:dismantle:兵:2", "label": "拆解【厚背刀】→ 精鐵砂×1", "enabled": True, "wait": "",
                           "confirm": "把【厚背刀】（一階下品）拆成精鐵砂×1？拆掉就沒了。", "confirm_yes": "拆掉"}]}
    out = run(m, _CHOOSE_CLICK)
    assert "拆成精鐵砂×1" in out["asked"] and ">拆掉<" in out["asked"] and ">照打<" not in out["asked"]
    assert out["calls"] == []
