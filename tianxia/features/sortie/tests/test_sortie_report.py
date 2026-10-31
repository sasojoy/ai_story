"""出陣回報（企劃者 2026-10-23 在草稿上選「寫數字」）：領地爭奪開著時，出陣那一下在「剛剛」卡片底下多一塊——那一塊的進度條、一句話、
小籤（今天自己推了多少、全軍今天推了多少、軍令進度）。引擎記今天每一邊、每個人推了多少（ConquestState.tally，換日同出陣次數）。"""
from __future__ import annotations

import json

import pytest
from conquest_kit import conquest_game, go, join, plain_game, win_sortie
from test_prologue_web import DRIVER as PROLOGUE_DRIVER

import webharness
from tianxia import conquest, orders, sortie
from tianxia.state import Order

pytestmark = pytest.mark.slow  # 建 Game、載正式內容


def _game(side="guan", loc="hilltop_wilds", name="沈浪", world=None):
    return go(join(conquest_game("season21", name=name, world=world), side), loc)


def _chips(front):
    return [c["text"] for c in front["chips"]]


def test_an_attack_reports_my_bar_before_and_after_and_todays_numbers():
    game = _game()
    w, c = game.state.world, game.content
    conquest.push(w, c, "hilltop_wilds", "guan", "某甲", 30, "attack")
    conquest.push(w, c, "hilltop_wilds", "huang", "某乙", 20, "attack")
    win_sortie(game)
    front = game.now_front()
    mine, theirs = front["rows"]
    moved = conquest.bar(w, "hilltop_wilds", "guan") - 30
    assert mine == {"side": "guan", "name": "官軍", "value": round(30 + moved), "before": 30, "mine": True}
    assert theirs["side"] == "huang" and theirs["value"] == theirs["before"] == 20
    assert front["title"] == "荒丘・進度" and front["count"] == "你今日出陣 1/5"
    left = 100 - mine["value"]
    assert front["text"] == f"荒丘還沒有人佔。官軍的進度 {mine['value']}／100，再推 {left} 就佔下。"
    word = sortie.amount_words(moved, game.content.config.sortie.chip_mine_steps)
    assert _chips(front) == [f"今天你替官軍{word}", f"全軍今天{sortie.amount_words(moved, game.content.config.sortie.chip_all_steps)}"]
    assert not any(ch.isdigit() for ch in "".join(_chips(front)))  # 小籤寫字不寫數字（企劃者 2026-10-26）


def test_the_whole_side_adds_up_and_a_new_day_starts_over():
    game = _game()
    other = _game(name="白飛", world=game.world)
    other.state.world = game.state.world
    win_sortie(other)
    first = conquest.today_moved(game.state.world, game._pill_day(), "guan", "白飛")
    win_sortie(game)
    w, day = game.state.world, game._pill_day()
    mine = conquest.today_moved(w, day, "guan", "沈浪")
    assert first > 0 and mine > 0
    assert conquest.today_moved(w, day, "guan") == pytest.approx(first + mine)
    assert _chips(game.now_front())[1] == f"全軍今天{sortie.amount_words(first + mine, game.content.config.sortie.chip_all_steps)}"
    assert conquest.today_moved(w, day + 1, "guan") == 0  # 別天的帳不算
    conquest.tally(w, game.content, day + 1, "guan", "沈浪", 3)
    assert w.conquest.tally.day == day + 1 and conquest.today_moved(w, day + 1, "guan") == 3  # 換了一天整本重記


def test_the_push_that_flips_gets_its_own_chip_and_the_payout_keeps_the_report():
    game = _game()
    w, c = game.state.world, game.content
    conquest.push(w, c, "hilltop_wilds", "guan", "某甲", 98, "attack")
    conquest.push(w, c, "hilltop_wilds", "huang", "某乙", 40, "attack")
    win_sortie(game)
    front = game.now_front()
    assert front["text"] == "荒丘被你這一下推滿，落入官軍之手。"
    assert front["chips"][0] == {"text": "易手・這一下是你推滿的", "kind": "flip"}
    assert [(r["side"], r["value"], r["before"]) for r in front["rows"]] == [("guan", 100, 98), ("huang", 0, 40)]
    game._deliver_conquest()  # 下一次同步：分紅那一則成了「剛剛」，底下照樣畫同一塊
    assert game.state.journal[0].title == "攻下荒丘"
    assert game.now_front() == front


def test_holding_reports_the_rival_bar_pulled_back():
    game = _game()
    w, c = game.state.world, game.content
    conquest.set_control(w, c, "hilltop_wilds", "guan")
    conquest.push(w, c, "hilltop_wilds", "huang", "某乙", 40, "attack")
    game.choose("act:train")
    front = game.now_front()
    (row,) = front["rows"]
    assert row["side"] == "huang" and row["before"] == 40 and row["value"] < 40 and not row["mine"]
    assert front["text"] == f"荒丘官軍守著。黃巾軍的進度被拉到 {row['value']}／100，推到 100 才奪得走。"


def test_cannot_push_says_why_and_the_order_chip_counts_the_side():
    game = _game()
    w, c = game.state.world, game.content
    line = conquest.line_of(w, c, "nanyang_road")
    period = orders.period_of(game.state, c)
    w.orders.append(Order(id="o1", template="siege", faction="guan", week=period, front=line, quota=12, text="攻", progress={"某甲": 6}))
    w.orders.append(Order(id="o2", template="siege", faction="huang", week=period, front=line, quota=12, text="攻", progress={"某乙": 9}))
    conquest.push(w, c, "hilltop_wilds", "guan", "某甲", 100, "attack")  # 官軍剛拿下：冷卻
    conquest.push(w, c, "nanyang_road", "guan", "某甲", 10, "attack")
    go(game, "nanyang_road")
    win_sortie(game)
    assert _chips(game.now_front())[-1] == "軍令「攻城」過半"  # 6～7／12
    go(game, "hilltop_wilds")
    w.time += 1
    game.choose("act:train")
    front = game.now_front()
    assert front["text"].startswith("荒丘此刻推不動進度：剛易手")
    assert front["rows"] == []


def test_without_conquest_there_is_no_report_and_other_entries_drop_it():
    game = go(join(plain_game(), "guan"), "nanyang_wilds")
    win_sortie(game)
    assert game.state.journal[0].front is None and game.now_front() is None
    game = _game()
    win_sortie(game)
    assert game.now_front() is not None
    game.notice("別的事")
    assert game.now_front() is None


# ── 網頁 ──

NAMES_START = 'wholeApp(["S", '
assert PROLOGUE_DRIVER.count(NAMES_START) == 1
DRIVER = PROLOGUE_DRIVER.replace(NAMES_START, 'wholeApp(["S", "frontReportHtml", ')
needs_node = pytest.mark.skipif(webharness.NODE is None, reason="沒有 node，前端畫面測試略過")
FRONT = {
    "loc": "hilltop_wilds", "title": "荒丘・進度", "count": "你今日出陣 2/5", "holder": "guan", "side": "guan",
    "rows": [{"side": "guan", "name": "官軍", "value": 100, "before": 96, "mine": True},
             {"side": "huang", "name": "黃巾軍", "value": 0, "before": 22, "mine": False}],
    "text": "荒丘被你這一下推滿，落入官軍之手。",
    "chips": [{"text": "易手・這一下是你推滿的", "kind": "flip"}, {"text": "今天你替官軍推了一點", "kind": ""}],
}


@needs_node
def test_the_report_draws_bars_text_and_chips():
    script = f"const f = {json.dumps(FRONT, ensure_ascii=False)}; return [H.frontReportHtml(f), H.frontReportHtml(null)];"
    report, empty = webharness.run(DRIVER, {"m": {}, "script": script, "S": {}, "menxia": None, "stored": {}, "responses": {}})
    assert empty == ""
    assert "荒丘・進度" in report and "你今日出陣 2/5" in report and "落入官軍之手" in report
    assert 'class="sf-row side-guan mine"' in report and 'class="sf-gain" style="left:96%;width:4%"' in report
    assert 'class="sf-lost" style="left:0%;width:22%"' in report  # 黃巾那一條被清掉：虛的那一截
    assert 'class="sf-chip flip side-guan"' in report and "今天你替官軍推了一點" in report


def test_chip_words_follow_the_steps():
    """小籤寫字（企劃者 2026-10-26「出陣寫字」）：推的量照 chip_*_steps 分三級、沒推「還沒推動」；軍令照完成幾成分級。"""
    steps = (5.0, 15.0)
    assert [sortie.amount_words(x, steps) for x in (0, 0.3, 4.9, 5, 14.9, 15, 80)] == [
        "還沒推動", "推了一點", "推了一點", "推了不少", "推了不少", "推了一大截", "推了一大截"]
    assert [sortie.order_words(n, 10) for n in (0, 1, 4, 5, 7, 8, 9, 10)] == [
        "還沒起頭", "剛起頭", "剛起頭", "過半", "過半", "快成了", "快成了", "快成了"]
