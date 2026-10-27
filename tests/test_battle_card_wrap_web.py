"""戰鬥卡片「展開過程」不跑版（2026-10-27 主機 pull develop 之後的回報）：輿圖四層那一排的「全區」鈕叫 .r-full，跟收著的第一回合
（main.js 的 fitFirstRound 包的 <span class="r-full">）撞名，展開之後第 1 回合被畫成一顆不換行的膠囊、衝出卡片右邊；
「得失」那一段的每一樣（「氣血 -11」）也被拆到兩行。這裡擋住：樣式表裡碰到 .r-full／.r-short 的規則一律限在自己那一塊底下、
戰鬥卡片過程的清單不設不換行，得失的每一樣整顆包起來。"""
from __future__ import annotations

import json
import re

import pytest

import server
import webharness
from html.parser import HTMLParser
from tianxia import battlelog
from tianxia.models import TerrainArts
from tianxia.state import BattleRecord, Fighter

CSS = (server.WEB / "style.css").read_text(encoding="utf-8")


def _rules(css: str):
    """（選擇器清單, 內容）：去掉註解、@media 的外殼照樣攤開（只看裡面的規則）。"""
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    for sel, body in re.findall(r"([^{}]+)\{([^{}]*)\}", css):
        yield [s.strip() for s in sel.split(",") if s.strip()], body


def test_round_classes_are_only_styled_inside_their_own_block():
    """.r-full、.r-short 兩個名字有兩個主人：戰鬥卡片的第一回合（.battle-card 底下）與輿圖上面那一排（.r-top 底下）。
    沒加範圍的規則會同時套到兩邊（2026-10-27：第 1 回合變成 40px 高、white-space: nowrap 的膠囊）。"""
    loose = [s for sels, _ in _rules(CSS) for s in sels
             if re.search(r"\.r-(full|short)\b", s) and not s.startswith((".battle-card", ".r-top"))]
    assert loose == []


def test_the_rounds_list_wraps():
    """過程的每一回合要換行：.battle-card 底下碰到 rounds 或 .r-full 的規則都不設 white-space: nowrap。"""
    bad = [s for sels, body in _rules(CSS) for s in sels
           if s.startswith(".battle-card") and re.search(r"rounds|\.r-full", s) and "nowrap" in body and ".rounds-more" not in s]
    assert bad == []


@pytest.mark.skipif(webharness.NODE is None, reason="沒有 node，前端畫面測試略過")
def test_each_gain_is_kept_whole():
    """「得失」那一段每一樣包成一顆 .nb（樣式表 white-space: nowrap），換行只落在兩樣之間；別的段落不動。"""
    js = webharness.app_source()
    start = js.index("  function keepGainsWhole(")
    fn = js[start:js.index("\n  }\n", start) + 4]
    card = ("<h3>⚔ 潁水河畔・對陣 河灘潑皮</h3>\n<p>第 1 週・週二 07:58　出門一趟・遭遇</p>\n"
            "<p><strong>結果</strong>　升到第 2 級　<strong>得失</strong>　經驗 +5（每人）　心得 +4　銀兩 +3　氣血 -11　內傷 +2　氣血 +9</p>\n")
    done = webharness.node(fn + "\nprocess.stdout.write(JSON.stringify(keepGainsWhole(" + json.dumps(card, ensure_ascii=False) + ")));")
    assert done.returncode == 0, done.stderr
    out = json.loads(done.stdout)
    for item in ("升到第 2 級", "經驗 +5（每人）", "心得 +4", "銀兩 +3", "氣血 -11", "內傷 +2", "氣血 +9"):
        assert f'<span class="nb">{item}</span>' in out
    assert "<p>第 1 週・週二 07:58　出門一趟・遭遇</p>" in out  # 沒有「得失」的段落不動
    assert re.search(r"(?m)^\.battle-card \.nb \{[^}]*white-space: nowrap", CSS)


# ── 原 test_fb471_card_label_nowrap.py（整檔搬進來） ──
# FB-471（第 36 項「武學隨地理環境」QA，2026-10-19）：「剛剛」戰鬥卡片的粗體標籤（「得失」等）沒有 nowrap，地利那一句讓
# 「結果」多一行時，375 寬「得」「失」被拆在兩行——卡片自己那幾段（.battle-card > p）的粗體標籤不折行。
#
# CSS 沒辦法在 node 裡排版：讀 style.css 斷言那一條規則，另外驗卡片上的粗體標籤真的都是那幾段的直接子元素（選擇器對得上伺服器的
# HTML 與 fightCard 的改寫）。

DRIVER = r"""
const H = new Function("S", [konst("ROUNDS_MARK"), konst("TALE_MARK"), konst("reportLink"), konst("TRAIT_LEAD"), konst("roundsMore"),
  fn("foldTraitItems"), fn("foldTraitText"), fn("roundsFold"), fn("withReportLink"), fn("trailMoves"), fn("keepGainsWhole"), fn("fightCard"),
  "return { fightCard };"].join("\n"))({ roundsOpen: null });
finish(input.cards.map((c) => H.fightCard(c, 7)));
"""


def _css() -> str:
    return re.sub(r"/\*.*?\*/", "", (server.WEB / "style.css").read_text(encoding="utf-8"), flags=re.S)


@pytest.mark.skipif(webharness.NODE is None, reason="沒有 node，前端畫面測試略過")
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


@pytest.mark.skipif(webharness.NODE is None, reason="沒有 node，前端畫面測試略過")
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
