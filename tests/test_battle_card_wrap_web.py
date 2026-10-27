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
