"""鐵匠鋪長標籤在 375px 上的斷行（FB-132）：web/app.js 的 optLabelHtml 把 smith: 開頭的選項標籤照標點切成小段，
每段包一個不折行的 .nb（web/style.css），段與段之間才換行——「下品」「沒人」「壓得住」「屬實」不會被拆在兩行。
伺服器給的標籤文字一個字都沒改（待 joy 潤的字照舊）；這裡餵真的標籤格式（smithing.GO_LABEL 等）給 app.js 的假瀏覽器
（tests/test_prologue_web.py），檢查切出來的小段、跳脫、與 CSS 那一條。沒有 node 就略過。排版本身（折在哪一行）要瀏覽器才看得到，不在這裡。"""
from __future__ import annotations

import html
import random
import re
from pathlib import Path

import pytest
from test_prologue_web import run

import server
import webharness
from tianxia import smithing
from tianxia.engine import Game

pytestmark = pytest.mark.skipif(webharness.NODE is None, reason="沒有 node，前端畫面測試略過")

ROOT = Path(__file__).parent.parent

# FB-132 回報的那一爐（375×812 折四行）：主料＋輔料、還沒人打過、拳套・屬陰・三階、工錢與三個機率、一句原因
GO = smithing.GO_LABEL.format(
    what="鎮山鐵＋化水晶", head=smithing.NEW_RECIPE, kind="拳套", attribute="陰", tier="三階",
    note="工錢 150 兩；下品 46%、中品 32%、上品 22%（輔料壓得住主料）",
)
MAIN = "主料：掣電鱗（快・三階・剩 1・工錢 150 兩）"
AUX = f"輔料：精鐵砂（剛・一階・剩 2）→ 屬實{smithing.ATTR_MARK}"


@pytest.fixture
def menu(hints_content, world):
    """真引擎給的 /api/main，選單換成要畫的鐵匠鋪鈕。"""
    game = Game.new(hints_content, "沈浪", rng=random.Random(0), world=world)
    game.skip_tutorial()
    m = server.main_view(game)

    def draw(*options):
        opts = [{"id": oid, "label": label, "enabled": True, "wait": "", "confirm": "", "confirm_yes": ""} for oid, label in options]
        return run({**m, "options": opts}, "return H.pageJianghu();")

    return draw


def _chunks(page, oid):
    """某顆鈕裡切出來的小段（已還原跳脫），以及那顆鈕整句還原後的字。"""
    button = re.search(rf'<button[^>]*data-id="{re.escape(html.escape(oid))}"[^>]*>(.*?)</button>', page, re.S).group(1)
    button = re.sub(r'<span class="k[^"]*">.*?</span>', "", button)  # 左邊那一格編號
    return [html.unescape(c) for c in re.findall(r'<span class="nb">(.*?)</span>', button)], html.unescape(re.sub(r"<[^>]+>", "", button))


def test_the_forge_go_label_is_cut_into_unbroken_chunks_without_changing_a_word(menu):
    page = menu((smithing.GO + "拳套:gang_3:kuai_3", GO))
    chunks, text = _chunks(page, smithing.GO + "拳套:gang_3:kuai_3")
    assert "".join(chunks) == GO == text.strip()  # 字一個都沒多沒少，只是多包了幾層
    # FB-132 被拆開的詞，每個都完整躺在某一段裡
    for whole in ("下品 46%、", "中品 32%、", "上品 22%", "這個配方還沒人打過", "工錢 150 兩；", "（拳套・", "屬陰・", "化水晶 → "):
        assert whole in chunks, whole
    assert any("壓得住" in c for c in chunks) and all(len(c) <= 16 for c in chunks)
    assert not any(c.startswith(("、", "；", "・", "）", "→")) for c in chunks)  # 沒有以標點開頭的行頭


def test_main_and_aux_material_labels_keep_the_price_and_the_attribute_whole(menu):
    page = menu((smithing.MAIN + "kuai_3", MAIN), (smithing.AUX + "gang_1", AUX))
    chunks, _ = _chunks(page, smithing.MAIN + "kuai_3")
    assert chunks == ["主料：掣電鱗", "（快・", "三階・", "剩 1・", "工錢 150 兩）"]  # 「150｜兩」不分家
    chunks, _ = _chunks(page, smithing.AUX + "gang_1")
    assert chunks == ["輔料：精鐵砂", "（剛・", "一階・", "剩 2）→ ", "屬實・", "跟你的武學同屬性"]  # 「屬｜實」不分家


def test_every_smith_button_gets_the_chunks_and_other_buttons_do_not(menu):
    page = menu(("smith:repair", "修【試刃】（鋒利度 40・精鐵砂×1＋5 兩）・這把配不上你的武學，加成用不上"),
                ("smith:back", "離開鐵匠鋪"), ("act:explore", "探索（體力 6・也許有收穫）"))
    assert _chunks(page, "smith:repair")[0] == ["修【試刃】", "（鋒利度 40・", "精鐵砂×1＋", "5 兩）・", "這把配不上你的武學，", "加成用不上"]
    assert _chunks(page, "smith:back")[0] == ["離開鐵匠鋪"]
    assert _chunks(page, "act:explore")[0] == []  # 別的選單不動


def test_chunks_are_escaped_and_a_chunk_that_is_too_long_stays_breakable(menu):
    page = menu(("smith:forge-main:x", '主料：<b>驚雷</b>＋"x"&（剛・一階）'),
                ("smith:forge-aux:y", "輔料：" + "很長的名字" * 5 + "（剛・一階）"))
    assert "<b>" not in page and "&lt;b&gt;驚雷&lt;/b&gt;＋" in page and "&quot;x&quot;&amp;" in page
    chunks, text = _chunks(page, "smith:forge-main:x")
    assert "".join(chunks) == text.strip() == '主料：<b>驚雷</b>＋"x"&（剛・一階）'
    chunks, _ = _chunks(page, "smith:forge-aux:y")
    assert chunks == ["（剛・", "一階）"] and "輔料：" + "很長的名字" * 5 in page  # 超過 16 個字的那一段不包 .nb，免得衝出按鈕


def test_the_css_makes_each_chunk_an_unbreakable_inline_block():
    css = (ROOT / "web" / "style.css").read_text(encoding="utf-8")
    rule = re.search(r"(?m)^\.nb\s*\{([^}]*)\}", css)
    assert rule and "white-space: nowrap" in rule.group(1) and "display: inline-block" in rule.group(1)
    assert "FB-132" in css
