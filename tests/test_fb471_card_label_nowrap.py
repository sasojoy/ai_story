"""FB-471（第 36 項「武學隨地理環境」QA，2026-10-19）：「剛剛」戰鬥卡片的粗體標籤（「得失」等）沒有 nowrap，地利那一句讓
「結果」多一行時，375 寬「得」「失」被拆在兩行——卡片自己那幾段（.battle-card > p）的粗體標籤不折行。

CSS 沒辦法在 node 裡排版：讀 style.css 斷言那一條規則，另外驗卡片上的粗體標籤真的都是那幾段的直接子元素（選擇器對得上伺服器的
HTML 與 fightCard 的改寫）。"""
from __future__ import annotations

import re
from html.parser import HTMLParser

import pytest
import webharness

import server
from tianxia import battlelog
from tianxia.models import TerrainArts
from tianxia.state import BattleRecord, Fighter

pytestmark = pytest.mark.skipif(webharness.NODE is None, reason="沒有 node，前端畫面測試略過")

DRIVER = r"""
const H = new Function("S", [konst("ROUNDS_MARK"), konst("TALE_MARK"), konst("reportLink"), konst("TRAIT_LEAD"), konst("roundsMore"),
  fn("foldTraitItems"), fn("foldTraitText"), fn("roundsFold"), fn("withReportLink"), fn("trailMoves"), fn("fightCard"),
  "return { fightCard };"].join("\n"))({ roundsOpen: null });
finish(input.cards.map((c) => H.fightCard(c, 7)));
"""


def _css() -> str:
    return re.sub(r"/\*.*?\*/", "", (server.WEB / "style.css").read_text(encoding="utf-8"), flags=re.S)


def test_the_card_labels_do_not_wrap():
    rule = re.search(r"(?m)^\.battle-card > p > strong \{([^}]*)\}", _css())
    assert rule is not None and "white-space: nowrap" in rule.group(1)


class _Parents(HTMLParser):
    """每一個 <strong> 的祖先（由外而內的標籤名）與它的字。"""

    def __init__(self):
        super().__init__()
        self.stack: list[str] = []
        self.found: list[tuple[list[str], str]] = []

    def handle_starttag(self, tag, attrs):
        self.stack.append(tag)
        if tag == "strong":
            self.found.append((self.stack[:-1], ""))

    def handle_endtag(self, tag):
        while self.stack and self.stack.pop() != tag:
            pass

    def handle_data(self, data):
        if self.stack and self.stack[-1] == "strong":
            parents, text = self.found[-1]
            self.found[-1] = (parents, text + data)


def _record(note: str, narration: str = "") -> BattleRecord:
    return BattleRecord(
        id=7, time=0, location="淯水河畔", kind="train", opponent="河上水寇", ours=[Fighter(name="地利客", level=3)], tier="落敗",
        our_power=40, difficulty=60, rounds=["第1回合　甲。", "第2回合　乙。"], narration=narration, notes=[note], silver=-5,
    )


def test_every_label_on_the_card_is_a_direct_child_of_a_card_paragraph():
    """選擇器 .battle-card > p > strong 要真的套到「結果」「得失」：伺服器的 HTML 經過 fightCard（過程那一行改寫）之後，
    卡片上每一個粗體標籤都是卡片自己那幾段 <p> 的直接子元素。16 字的三句（375 寬必撞的那三句）配回合清單、配大場面的一段話都驗。"""
    lines = TerrainArts().lines
    records = [_record(lines[key]) for key in ("match:shui", "clash:shui", "match:feng")]
    records.append(_record(lines["match:shui"], narration="水寇刀勢沉猛，你左支右絀。"))
    cards = webharness.run(DRIVER, {"cards": [server.md(battlelog.card_text(r)) for r in records]})
    for card in cards:
        parser = _Parents()
        parser.feed(f'<div class="card battle-card">{card}</div>')
        labels = {text: parents for parents, text in parser.found}
        assert {"落敗", "過程", "結果", "得失"} <= set(labels)
        assert all(parents == ["div", "p"] for parents in labels.values()), labels
