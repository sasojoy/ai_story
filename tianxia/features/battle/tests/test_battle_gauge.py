"""決戰的即時戰局條與看得懂的推進說法（Joy 2026-10-10 轉玩家反饋：「大決戰時……有辦法看即時戰局？那個推進多少我都不知道是啥意思」）。
引擎給資料（battle_instance.gauge、Game.battle_gauge／card_gauge／record_gauge），網頁畫條（web/app.js 的 gaugeHtml）；
句子裡不再寫「戰局推進 N」「戰局 a→b」，改成 shove 的三段說法，數字只畫在條上。"""
from __future__ import annotations

import random
import re

import pytest
from test_prologue_web import run

import server
import webharness
from tianxia import battle_instance as bi
from tianxia.engine import Game
from tianxia.models import MOVES, BattleAct, BattleDef, BattleFaction, BattleOption, BattleOutcome, BattleTuning

CODES = {"強攻": "strong", "固守": "hold", "奇襲": "raid"}
node = pytest.mark.skipif(webharness.NODE is None, reason="沒有 node，前端畫面測試略過")


@pytest.fixture
def three() -> BattleDef:
    options = [
        BattleOption(text=f"{side}{move}", tag=f"{side}_{CODES[move]}", faction=side, move=move)
        for side in ("guan", "huang") for move in MOVES
    ]
    return BattleDef(
        id="three", name="三招之戰",
        factions=[BattleFaction(id="guan", name="官軍"), BattleFaction(id="huang", name="黃巾")],
        acts=[BattleAct(id="a1", title="對陣", text="兩軍對陣。", goal="推動戰局", options=options)],
        rounds_per_act=9, decisive_margin=40,
        outcomes=[
            BattleOutcome(faction="guan", trend_min=65, title="官軍大勝", text="官軍獲勝。"),
            BattleOutcome(faction="huang", trend_max=35, title="黃巾得勢", text="黃巾獲勝。"),
            BattleOutcome(faction="guan", title="兩軍膠著", text="不分勝負。"),
        ],
    )


def _fought(definition, rounds):
    """甲（官軍）乙（黃巾）打幾回合：rounds 是 [(甲的招, 乙的招), ...]。"""
    battle = bi.start_muster(definition, now=0)
    for name, side in (("甲", "guan"), ("乙", "huang")):
        bi.join_faction(battle, name, side, neili_cap=1000, scores={m: 50.0 for m in MOVES})
    bi.close_muster(battle, definition, random.Random(0), now=0)
    for a, b in rounds:
        bi.submit_action(battle, "甲", f"guan_{CODES[a]}")
        bi.submit_action(battle, "乙", f"huang_{CODES[b]}")
        bi.resolve_round(battle, definition, random.Random(0), now=1, tuning=BattleTuning())
    return battle


# ── 說法 ──────────────────────────────────────────────


def test_the_shove_has_three_sizes_and_no_numbers():
    assert [bi.shove_size(n) for n in (1, 3, 4, 9, 10, 25)] == ["一點", "一點", "一截", "一截", "一大截", "一大截"]
    assert bi.shove("官軍", 5) == "替官軍把戰線推前了一截"
    assert bi.shove("黃巾", -1) == "讓黃巾的戰線退了一點"
    assert bi.round_line({"guan": "官軍", "huang": "黃巾"}, ("guan", "huang"), 50, 62, ["人多"]) == (
        "這一回合官軍佔了上風，把戰線往自己這邊推了一大截：人多。")
    assert bi.round_line({"guan": "官軍", "huang": "黃巾"}, ("guan", "huang"), 50, 50, []) == "這一回合兩軍相持不下，戰線沒有動。"


def test_no_round_message_carries_a_raw_trend_number(three):
    battle = _fought(three, [("奇襲", "固守"), ("強攻", "奇襲"), ("固守", "固守")])
    for record in battle.rounds:
        for line in record.messages:
            assert not re.search(r"戰局\s*[+-]?\d|戰局推進|戰局倒退|\d+→\d+", line), line


# ── 戰局條的資料 ──────────────────────────────────────────


def test_the_gauge_puts_the_viewer_on_the_left(three):
    battle = _fought(three, [("奇襲", "固守")])  # 官軍的奇襲剋固守：戰線往官軍那邊
    assert battle.trend > 50
    mine = bi.gauge(battle, three, "guan", timetable=False)
    theirs = bi.gauge(battle, three, "huang", timetable=False)
    assert (mine["left"]["name"], mine["left"]["mine"], mine["right"]["mine"]) == ("官軍", True, False)
    assert (theirs["left"]["name"], theirs["left"]["mine"]) == ("黃巾", True)
    assert mine["lean"] == battle.trend and theirs["lean"] == 100 - battle.trend
    assert mine["rounds"] == [{"n": 1, "from": 50, "to": battle.trend, "side": "left"}]
    assert theirs["rounds"] == [{"n": 1, "from": 50, "to": 100 - battle.trend, "side": "right"}]
    assert mine["caption"].startswith("官軍佔上風；再推") and "當場分出勝負" in mine["caption"]
    assert (mine["round"], mine["total"], mine["decisive"]) == (2, 9, 40)


def test_outsiders_see_the_first_army_on_the_left(three):
    battle = _fought(three, [])
    g = bi.gauge(battle, three, None, timetable=False)
    assert g["left"]["name"] == "官軍" and not g["left"]["mine"] and not g["right"]["mine"]
    assert g["caption"] == "兩軍不分上下，戰線在正中間" and g["rounds"] == []


def test_zones_follow_the_outcomes_or_the_timetable_rule(three):
    battle = _fought(three, [])
    plain = bi.gauge(battle, three, "huang", timetable=False)
    assert plain["zones"] == [  # 從黃巾那邊看：官軍大勝（戰局 65 以上）落在右邊那一頭
        {"from": 0, "to": 35, "side": "right", "label": "官軍大勝"},
        {"from": 65, "to": 100, "side": "left", "label": "黃巾得勢"},
    ]
    timed = bi.gauge(battle, three, "guan", timetable=True)
    assert timed["zones"] == [
        {"from": 65, "to": 100, "side": "left", "label": "官軍大勝"},
        {"from": 0, "to": 35, "side": "right", "label": "黃巾大勝"},
    ]


def test_muster_and_end_captions(three):
    battle = bi.start_muster(three, now=0, trend_start=58)
    assert bi.gauge(battle, three, "guan", timetable=False)["caption"] == "集結中：開戰時戰線偏向官軍一截"
    battle = _fought(three, [("奇襲", "固守")] * 9)
    g = bi.gauge(battle, three, "guan", timetable=False)
    assert battle.phase == "ended" and g["caption"] == battle.outcome_title and len(g["rounds"]) == battle.round_number


def test_old_swings_without_a_fixed_part_still_read():
    assert bi.RoundSwing.model_validate({"round": 1, "delta": 3}).fixed == 0


# ── 引擎與伺服器 ─────────────────────────────────────────


@pytest.fixture
def showdown(on):
    """宛城之戰：官軍的甲、黃巾的乙都在宛城，開打。"""
    games = []
    for name, side in (("甲", "guan"), ("乙", "huang")):
        g = Game.new(on, name, rng=random.Random(0))
        g.client = None
        g.set_hints_off(True)
        g.state.player.faction, g.state.player.location = side, "wan_city"
        games.append(g)
    a, b = games
    a.world.start_battle(on.battles["wancheng_jia"], now=a.now)
    a.choose("battle:join:guan")
    b.choose("battle:join:huang")
    return on, a, b


def test_both_sides_see_the_gauge_from_their_own_end(showdown):
    _, a, b = showdown
    ga, gb = server.main_view(a)["battle_gauge"], server.main_view(b)["battle_gauge"]
    assert ga["phase"] == "muster" and ga["left"]["name"] == "官軍" and gb["left"]["name"] == "黃巾軍"
    assert ga["lean"] + gb["lean"] == 100


def test_the_closing_report_keeps_the_final_gauge(showdown):
    on, a, b = showdown
    a.world.mutate_battle(lambda x: setattr(x, "muster_deadline_real", -1.0))
    a.options()
    for _ in range(20):
        battle = a.world.get_battle()
        if battle.phase == "ended":
            break
        for g, tag in ((a, "battle:act:guan_raid"), (b, "battle:act:huang_hold")):
            if g.state.player.name not in g.world.get_battle().round.pending_actions and g.world.get_battle().phase == "active":
                g.choose(tag)
    a.sync(a.now)  # 收場的決戰在下一次同步補進自己的戰報（_deliver_battle_results）
    assert a.world.get_battle().phase == "ended"
    view = server.main_view(a)
    assert view["battle_gauge"] is None  # 打完了，場景裡沒有戰場
    card = view["card_gauge"]
    assert card is not None and card["phase"] == "ended" and card["left"]["name"] == "官軍" and card["rounds"]
    assert server.reports_view(a, None)["gauge"] == card


# ── 網頁 ──────────────────────────────────────────────


@node
def test_the_page_draws_the_gauge_under_the_battle_name(showdown):
    _, a, _ = showdown
    a.world.mutate_battle(lambda x: setattr(x, "muster_deadline_real", -1.0))
    a.options()
    a.choose("battle:act:guan_raid")
    m = server.main_view(a)
    page = run(m, "return H.pageJianghu();")
    scene = re.search(r'<section class="card scene">(.*?)</section>', page, re.S).group(1)
    assert scene.startswith("<p><strong>宛城之戰</strong></p><div class=\"gauge\"")
    g = m["battle_gauge"]
    assert f'class="g-flag" style="left:{100 - g["lean"]}%"' in scene
    assert scene.count('<li class="g-r') == g["total"] and "官軍（我方）" in scene
    assert scene.count('class="g-tick"') == 2 and 'class="g-zone' in scene


@node
def test_no_gauge_without_a_battle(on):
    g = Game.new(on, "丙", rng=random.Random(0))
    g.client = None
    m = server.main_view(g)
    assert m["battle_gauge"] is None
    assert 'class="gauge"' not in run(m, "return H.pageJianghu();")

