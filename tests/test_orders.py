"""第一季濃縮版 T6：陣營軍令、最小糧草、第 1 階守勢行動（計畫 2026-10-05-T6-軍令）。

規則與引擎的測試用真實內容（content/）：要驗的就是真實的插槽、戰線與大勢人物。每個測試自己載一份，
開關在測試裡才打開，不會漏到別的測試。開關開著的季是「蓋了章」的：auto_open_first_season 開出來的季
照當下的 Config 蓋章（world_state.stamp_season）。"""
from __future__ import annotations

import random
from pathlib import Path
from unittest import mock

import pytest

from tianxia import calendar, figures, orders, rules, team, timetable
from tianxia.content import load_content
from tianxia.encounter import EncounterResult
from tianxia.engine import Game
from tianxia.models import Config
from tianxia.state import Convoy, Order, PlayerState, WorldState

CONTENT_DIR = Path(__file__).parent.parent / "content"


@pytest.fixture
def real():
    """真實內容，開關關著（beta 那一季的樣子）。"""
    c = load_content(CONTENT_DIR)
    c.config.auto_open_first_season = True
    c.config.train_event_chance = 0.0
    c.config.train_stat_chance = 0.0
    return c


@pytest.fixture
def on(real):
    """同一份真實內容，照週末設定打開：開關、季長 2.5 天、人數上限 2（每道軍令 4 次）。"""
    real.config.season_one = True
    real.config.season_days = 2.5
    real.config.server_max_players = 2
    return real


def _game(content, name="甲", faction=None, at=None, world=None):
    game = Game.new(content, name, rng=random.Random(0), world=world)
    game.state.player.faction = faction
    if at is not None:
        game.state.player.location = at
    return game


def _win():
    """遊歷穩贏（team.fight 的結果寫死）。"""
    return mock.patch.object(
        team, "fight", return_value=EncounterResult(tier="大勝", margin=50, our_power=100, difficulty=15),
    )


def _order(game, template, faction, *, front=None, location=None, start=None, end=None, figure=None, quota=4):
    """直接放一道這一週的軍令（不經過 issue），測記功與效果用。"""
    week = orders.week_of(game.state, game.content)
    order = Order(
        id=f"{week}:{faction}:{template}:{front or figure or location}", template=template, faction=faction,
        week=week, front=front, location=location, start=start, end=end, figure=figure, quota=quota, text="（測試）",
    )
    game.state.world.orders.append(order)
    return order


# ── Task 1：資料模型與內容 ─────────────────────────────────


def test_new_fields_have_defaults_so_old_saves_load():
    cfg = Config()
    assert (cfg.orders_per_week, cfg.order_quota_min, cfg.convoy_ambush_chance, cfg.convoy_grain, cfg.duty_stamina) == (
        3, 4, 0.2, 4, 10,
    )
    assert WorldState().orders == []
    assert PlayerState(name="甲", location="x", stats={}, stamina=0).convoy is None
    assert WorldState.model_validate({"time": 5.0}).orders == []  # 舊的賽季存檔沒有這一欄


def test_real_orders_content(real):
    o = real.orders
    kinds = sorted((t.kind, t.side) for t in o.templates)
    assert kinds == sorted([
        ("defend", "guan"), ("defend", "huang"), ("intercept", "guan"), ("intercept", "huang"),
        ("escort", "guan"), ("escort", "huang"), ("siege", "guan"), ("siege", "huang"),
        ("strike", "guan"), ("strike", "huang"), ("strike", "haoqiang"),
    ])
    assert o.slots["yingru"]["guan"].intercept == "hilltop_wilds"
    assert o.slots["nanyang"]["huang"].escort == ("nanyang_wilds", "nanyang_huangjin_camp")
    assert {f: d.name for f, d in o.duties.items()} == {"guan": "巡哨", "huang": "傳道", "haoqiang": "保境安民"}
    assert real.squads["guan_grain_convoy"].faction == "guan" and real.squads["huang_grain_convoy"].faction == "huang"
    assert real.squads["huang_grain_convoy"].drops[0].material == "man_1"


# ── Task 2：發令 ─────────────────────────────────────────


def _fronts(game, yingru, nanyang, jizhou):
    for front, value in (("yingru", yingru), ("nanyang", nanyang), ("jizhou", jizhou)):
        game.state.world.trends[front] = value
    rules.recompute_trends(game.state.world, game.content)


def _at_week(game, week, hours=0.0):
    game.state.world.time = calendar.week_start(week, game.content, game.state.world) + hours * 3600


def _kinds(game, faction):
    return sorted((o.template, o.figure if o.template == "strike" else o.front)
                  for o in game.state.world.orders if o.faction == faction)


def test_quota_scales_with_server_cap(on):
    siege = next(t for t in on.orders.templates if t.kind == "siege" and t.side == "guan")
    assert orders.quota(on, siege) == 4  # 2 人：ceil(1200 × 2 ÷ 3000)＝1，最少 4
    on.config.server_max_players = 3000
    assert orders.quota(on, siege) == 1200
    on.config.server_max_players = 30
    assert orders.quota(on, siege) == 12  # 整季模擬的 30 人


def test_issue_week_one_by_the_rules(on):
    """開季數字（潁川 40、南陽 35、冀州 55），第 1 週週一：南陽的下一件大事（第 3 週張曼成）剛好在兩週內。"""
    game = _game(on)
    _at_week(game, 1)
    assert orders.issue(game.state, on, 1, random.Random(0)) == []
    # 官軍：沒有戰線 ≥ 60（不守）；南陽截糧、護糧（優先 2）；攻城挑最吃緊的冀州（55）
    assert _kinds(game, "guan") == [("escort", "nanyang"), ("intercept", "nanyang"), ("siege", "jizhou")]
    # 黃巾：南陽 35、潁川 40 都 ≤ 40，守城兩道（南陽比較吃緊排前面），再加南陽截糧
    assert _kinds(game, "huang") == [("defend", "nanyang"), ("defend", "yingru"), ("intercept", "nanyang")]
    # 豪強：一道打擊，三條戰線都在亂局，挑聲威最低的張曼成（50）
    assert _kinds(game, "haoqiang") == [("strike", "zhangmancheng")]
    assert all(o.quota == 4 and o.week == 1 for o in game.state.world.orders)


def test_issue_defend_when_losing_or_enemy_sieged_last_week(on):
    game = _game(on)
    _fronts(game, 50, 50, 62)
    _at_week(game, 5)
    orders.issue(game.state, on, 5, random.Random(0))
    assert ("defend", "jizhou") in _kinds(game, "guan")  # 冀州 62 ≥ 60
    assert ("defend", "yingru") not in _kinds(game, "guan")
    game.state.world.orders.append(Order(
        id="5:huang:siege:yingru", template="siege", faction="huang", week=5, front="yingru", quota=4, text="", done=True,
    ))
    _at_week(game, 6)
    orders.issue(game.state, on, 6, random.Random(0))
    assert ("defend", "yingru") in _kinds(game, "guan")  # 黃巾上週在潁川達成攻城


def test_issue_fills_slots(on):
    game = _game(on)
    _at_week(game, 1)
    orders.issue(game.state, on, 1, random.Random(0))
    by_id = {(o.faction, o.template): o for o in game.state.world.orders}
    assert by_id[("guan", "intercept")].location == "nanyang_wilds"
    assert by_id[("guan", "intercept")].text == "探得黃巾的糧道經過南陽郊野，本週截斷它。"
    escort = by_id[("guan", "escort")]
    assert (escort.start, escort.end, escort.location) == ("xinye", "wan_city", "xinye")
    assert escort.text == "一批軍糧要從新野送到宛城，各營派人沿途護送。"
    assert by_id[("haoqiang", "strike")].text == "家主吩咐：張曼成擋了咱們的路。"
    assert "{" not in "".join(o.text for o in game.state.world.orders)


def test_issue_with_no_commander_uses_fallback(on):
    """RF3：那條戰線己方沒有主將時，{主將} 寫泛稱；黃巾的號令跟著張角、張寶退場換人。"""
    game = _game(on)
    _fronts(game, 50, 50, 50)
    _at_week(game, 1)  # 第 1 週：南陽截糧、護糧之外還有一道攻城（第 5 週會被三條戰線的截糧護糧佔滿）
    with mock.patch("tianxia.figures.commander", return_value=None):
        orders.issue(game.state, on, 1, random.Random(0))
    sieges = [o for o in game.state.world.orders if o.template == "siege" and o.faction == "guan"]
    assert sieges and all(o.text.startswith("營中傳令：") for o in sieges)
    template = next(t for t in on.orders.templates if t.kind == "siege" and t.side == "huang")
    order = Order(id="x", template="siege", faction="huang", week=5, front="yingru", quota=4, text="")
    assert orders.fill(game.state, on, order, template.text).startswith("大賢良師有令：")
    with mock.patch("tianxia.figures.is_out", side_effect=lambda state, fid: fid == "zhangjiao"):
        assert orders.fill(game.state, on, order, template.text).startswith("地公將軍有令：")
    with mock.patch("tianxia.figures.is_out", side_effect=lambda state, fid: fid in ("zhangjiao", "zhangbao")):
        assert orders.fill(game.state, on, order, template.text).startswith("人公將軍有令：")


def test_issue_clears_last_weeks_unfinished_and_keeps_the_done(on):
    game = _game(on)
    _at_week(game, 1)
    orders.issue(game.state, on, 1, random.Random(0))
    first = game.state.world.orders
    first[0].done = True
    _at_week(game, 2)
    orders.issue(game.state, on, 2, random.Random(0))
    weeks = [(o.week, o.done) for o in game.state.world.orders]
    assert (1, True) in weeks and (1, False) not in weeks
    assert any(w == 2 for w, _ in weeks)


def test_catch_up_over_weeks_issues_only_this_week(on):
    """RF1：週初掛鉤晚了好幾週才跑（季的時鐘直接跳過去、中間的曆時沒有跑，例如管理者跳時間）：季的事一次補跑第 2～4 週的
    掛鉤，只發第 4 週的，第 2、3 週不補發、不洗版。（平常 advance 一個曆時一個曆時走，每週一各自發，見下一個測試。）"""
    game = _game(on)
    game.advance(200)  # 跨過第一個曆時交界（約 107 秒）：第 1 週的掛鉤與大事
    assert {o.week for o in game.state.world.orders} == {1}
    rumors = len(game.state.world.rumors)
    game.state.world.time = calendar.week_start(4, on, game.state.world) + 30  # 時鐘跳到第 4 週，掛鉤還停在第 1 週
    game.advance(200)
    assert {o.week for o in game.state.world.orders if not o.done} == {4}
    issued = [r for r in game.state.world.rumors[rumors:] if r.layer == "faction" and r.text.startswith("本週軍令")]
    assert len(issued) == sum(1 for o in game.state.world.orders if o.week == 4)


def test_each_monday_issues_that_weeks_orders(on):
    """平常一個曆時一個曆時往前走：每週一各發各的，上週沒達成的在下週一清掉。"""
    game = _game(on)
    game.advance(calendar.week_start(3, on, game.state.world) + 200)
    weeks = [o.week for o in game.state.world.orders]
    assert set(weeks) == {3} and weeks  # 第 1、2 週的都沒達成，清掉了
    issued = [r for r in game.state.world.rumors if r.layer == "faction" and r.text.startswith("本週軍令")]
    assert len(issued) > len(weeks)  # 第 1、2 週也各發過


def test_issue_writes_faction_news_not_messages(on, world):
    """RF2：發令發生在某個人同步時；那個人是黃巾，也看不到官軍的軍令（江湖紀錄、見聞都沒有）。"""
    huang = _game(on, "乙", faction="huang", world=world)
    msgs = huang.advance(200)
    guan_texts = [o.text for o in huang.state.world.orders if o.faction == "guan"]
    assert guan_texts
    assert not any(t in m for t in guan_texts for m in msgs)
    assert not any(t in e for t in guan_texts for e in (huang.journal_html(1, 50), huang.rumors_text()))
    guan = _game(on, "甲", faction="guan", world=world)
    guan.sync(guan.now)
    assert any(t in guan.rumors_text() for t in guan_texts)  # 官軍自己看得到陣營軍情


def test_switch_off_issues_nothing(real):
    game = _game(real, faction="guan")
    game.advance(6 * 3600)
    assert game.state.world.orders == []
    assert orders.issue(game.state, real, 1, random.Random(0)) == []
    assert orders.current(game.state, real, "guan") == []


def test_unstamped_season_issues_nothing(real):
    """開關打開時還在跑的 beta 那一季（沒蓋章）：照舊不發。"""
    game = _game(real, faction="guan")
    real.config.season_one = True
    game.advance(6 * 3600)
    assert game.state.world.orders == []
