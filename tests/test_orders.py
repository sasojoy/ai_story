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
    # 官軍：沒有戰線 ≥ 60（不吃緊），但第 1 週守城在潁川汝南照發（FB-054，開局週：opening_fronts）；其餘兩格：一格留給進攻
    # （第 1 週是奇數週，偏好攻城：冀州 55 最吃緊）、一格給優先序 2 的南陽截糧（截糧排在護糧前面；FB-061 之前三格是守城、截糧、護糧）
    assert _kinds(game, "guan") == [("defend", "yingru"), ("intercept", "nanyang"), ("siege", "jizhou")]
    # 黃巾：南陽 35、潁川 40 都 ≤ 40，守城兩道（南陽比較吃緊排前面）；第三格留給攻城（只有南陽打得到官軍隊伍），
    # 原本的南陽截糧讓給它（FB-061 之前是守城兩道加南陽截糧）
    assert _kinds(game, "huang") == [("defend", "nanyang"), ("defend", "yingru"), ("siege", "nanyang")]
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
    # 官軍第 1 週（奇數週）輪到截糧、護糧排不進去（FB-061）：護糧看偶數週，南陽最吃緊的那一週（每條戰線兩週內都有大事）
    with mock.patch.object(orders, "_event_within", return_value=object()):
        _fronts(game, 40, 55, 50)
        escort = next(o for o in _week_orders(game, "guan", 2) if o.template == "escort")
    assert escort.front == "nanyang"
    assert (escort.start, escort.end, escort.location) == ("xinye", "wan_city", "xinye")
    assert escort.text == "一批軍糧要從新野送到宛城，各營派人沿途護送。"
    assert by_id[("haoqiang", "strike")].text == "家主吩咐：張曼成擋了咱們的路。"
    assert "{" not in "".join(o.text for o in game.state.world.orders)


def test_issue_with_no_commander_uses_fallback(on):
    """RF3：那條戰線己方沒有主將時，{主將} 寫泛稱；黃巾的號令跟著張角、張寶退場換人。"""
    game = _game(on)
    _fronts(game, 50, 50, 50)
    _at_week(game, 1)  # 第 1 週：南陽截糧、護糧之外還有一道守城（開局週，FB-054；第 5 週會被三條戰線的截糧護糧佔滿）
    with mock.patch("tianxia.figures.commander", return_value=None):
        orders.issue(game.state, on, 1, random.Random(0))
    stated = [o for o in game.state.world.orders if o.template in ("siege", "defend") and o.faction == "guan"]
    assert stated and all(o.text.startswith("營中傳令：") for o in stated)  # 兩種官軍軍令的文字都以 {主將} 開頭
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


# ── Task 3：記功與達成效果 ─────────────────────────────────


def test_siege_credit_by_win_at_front_only_against_the_enemy(on):
    game = _game(on, faction="guan")
    siege = _order(game, "siege", "guan", front="yingru")
    s, c = game.state, on
    assert orders.credit(s, c, "guan", "甲", kind="win", front="yingru", squad_faction="huang") == [
        "（軍令「攻城・潁川汝南」：你 1 次，陣營 1／4）",
    ]
    assert orders.credit(s, c, "guan", "甲", kind="win", front="nanyang", squad_faction="huang") == []  # 別的戰線
    assert orders.credit(s, c, "guan", "甲", kind="win", front="yingru", squad_faction=None) == []  # 流寇不是敵方陣營
    assert orders.credit(s, c, "guan", "甲", kind="duty", front="yingru") == []  # 守勢行動不算攻城
    assert orders.credit(s, c, None, "丙", kind="win", front="yingru", squad_faction="huang") == []  # 散人
    assert siege.progress == {"甲": 1}


def test_order_done_applies_effect_once_and_names_top_three(on):
    game = _game(on, faction="guan")
    _fronts(game, 50, 50, 50)
    siege = _order(game, "siege", "guan", front="yingru")
    s, c = game.state, on
    for name, times in (("甲", 1), ("乙", 2)):
        for _ in range(times):
            orders.credit(s, c, "guan", name, kind="win", front="yingru", squad_faction="huang")
    msgs = orders.credit(s, c, "guan", "丙", kind="win", front="yingru", squad_faction="huang", shown="某位少俠")
    assert siege.done and siege.applied == 8
    assert rules.trend_value(s, c, "yingru") == 42
    assert any("【軍令達成】潁川汝南的黃巾營壘被我軍連拔數處。出力最多：乙、甲、某位少俠。" in m for m in msgs)
    assert any("（潁川汝南 -8）" in m for m in msgs)
    news = [r for r in s.world.rumors if r.layer == "faction" and "軍令達成" in r.text]
    assert len(news) == 1 and news[0].faction == "guan"
    leak = [r for r in s.world.rumors if r.layer == "local" and "連破黃巾" in r.text]
    assert len(leak) == 1 and leak[0].region == "yingru" and leak[0].named is False and "乙" not in leak[0].text
    assert orders.credit(s, c, "guan", "甲", kind="win", front="yingru", squad_faction="huang") == []  # 達成了不再記
    assert rules.trend_value(s, c, "yingru") == 42


def test_defend_halves_the_enemy_siege(on):
    """守城達成：敵方這週還沒攻下就戰況往己方 3；已經攻下就收回對方攻城的一半；守住之後對方才攻下只得一半。"""
    game = _game(on, faction="guan")
    s, c = game.state, on
    _fronts(game, 50, 50, 50)
    siege = _order(game, "siege", "huang", front="yingru", quota=1)
    orders.credit(s, c, "huang", "乙", kind="win", front="yingru", squad_faction="guan")
    assert rules.trend_value(s, c, "yingru") == 58
    defend = _order(game, "defend", "guan", front="yingru", quota=1)
    orders.credit(s, c, "guan", "甲", kind="duty", front="yingru")
    assert rules.trend_value(s, c, "yingru") == 54 and siege.applied == 4 and defend.applied == 4

    _fronts(game, 50, 50, 50)
    _order(game, "defend", "guan", front="nanyang", quota=1)
    orders.credit(s, c, "guan", "甲", kind="duty", front="nanyang")
    assert rules.trend_value(s, c, "nanyang") == 47
    late = _order(game, "siege", "huang", front="nanyang", quota=1)
    orders.credit(s, c, "huang", "乙", kind="win", front="nanyang", squad_faction="guan")
    assert late.applied == 4 and rules.trend_value(s, c, "nanyang") == 51


def test_intercept_counts_only_the_enemy_convoy_near_the_place(on):
    game = _game(on, faction="guan")
    s, c = game.state, on
    _order(game, "intercept", "guan", front="nanyang", location="nanyang_wilds")
    kw = dict(kind="win", front="nanyang", squad_faction="huang")
    assert orders.credit(s, c, "guan", "甲", location="nanyang_wilds", squad="huang_grain_convoy", **kw)
    assert orders.credit(s, c, "guan", "甲", location="xinye", squad="huang_grain_convoy", **kw)  # 相鄰的站
    assert not orders.credit(s, c, "guan", "甲", location="nanyang_wilds", squad="shanzei", **kw)  # 不是糧隊
    assert not orders.credit(s, c, "guan", "甲", location="changshe", squad="huang_grain_convoy", kind="win",
                             front="yingru", squad_faction="huang")  # 太遠
    assert orders.extra_enemies(s, c, "xinye", "guan") == ["huang_grain_convoy"]
    assert orders.extra_enemies(s, c, "changshe", "guan") == []
    assert orders.extra_enemies(s, c, "xinye", "huang") == []  # 黃巾沒有截糧軍令
    assert orders.extra_enemies(s, c, "xinye", None) == []


def test_intercept_and_escort_both_done_cancel_mods(on):
    """同一週、同一條戰線雙方都達成截糧、護糧：一般伏筆的修正互相抵銷。"""
    game = _game(on, faction="guan")
    s, c = game.state, on
    _at_week(game, 2)
    event = timetable.next_event_on(s, c, "nanyang")
    assert event.id == "zhangmancheng_wan"
    _order(game, "intercept", "guan", front="nanyang", location="nanyang_wilds", quota=1)
    orders.credit(s, c, "guan", "甲", kind="win", location="nanyang_wilds", front="nanyang",
                  squad="huang_grain_convoy", squad_faction="huang")
    assert s.world.event_mods[event.id] == pytest.approx(-0.05)  # 「成」對黃巾有利：官軍 +5% 是 −0.05
    escort = _order(game, "escort", "huang", front="nanyang", start="nanyang_wilds", end="nanyang_huangjin_camp", quota=1)
    orders.credit(s, c, "huang", "乙", kind="convoy", location="nanyang_huangjin_camp", front="nanyang", order=escort.id)
    assert s.world.event_mods[event.id] == pytest.approx(0.0)


def test_escort_counts_only_its_own_order(on):
    game = _game(on, faction="guan")
    s, c = game.state, on
    escort = _order(game, "escort", "guan", front="nanyang", start="xinye", end="wan_city")
    assert orders.credit(s, c, "guan", "甲", kind="convoy", location="wan_city", front="nanyang", order=escort.id)
    assert not orders.credit(s, c, "guan", "甲", kind="convoy", location="wan_city", front="nanyang", order="1:guan:escort:old")
    assert orders.escort_at(s, c, "guan", "xinye") is escort
    assert orders.escort_at(s, c, "guan", "wan_city") is None
    assert orders.ambusher(c, "guan") == "huang_grain_convoy" and orders.ambusher(c, "haoqiang") is None


def test_strike_figure_credit_and_extra_prestige(on):
    game = _game(on, faction="guan")
    s, c = game.state, on
    before = figures.state_of(s, c, "bocai").prestige
    _order(game, "strike", "guan", front="yingru", figure="bocai", quota=1)
    assert not orders.credit(s, c, "guan", "甲", kind="challenge", figure="zhangmancheng")
    orders.credit(s, c, "guan", "甲", kind="challenge", figure="bocai")
    assert figures.state_of(s, c, "bocai").prestige == before - 15


def test_strike_done_after_the_figure_retired(on):
    """RF3：目標在軍令期間已經退場：達成照樣發軍情，但不再扣他、不丟例外。"""
    game = _game(on, faction="guan")
    s, c = game.state, on
    order = _order(game, "strike", "guan", front="yingru", figure="bocai", quota=1)
    figures.state_of(s, c, "bocai")  # 種好
    s.world.figures["bocai"].status = "retired"
    s.world.figures["bocai"].prestige = 0
    msgs = orders.credit(s, c, "guan", "甲", kind="challenge", figure="bocai")
    assert order.done and any("軍令達成" in m for m in msgs)
    assert s.world.figures["bocai"].prestige == 0


# ── Task 4：遊歷記功、運糧隊、守勢行動 ───────────────────────


def _issue_now(game):
    orders.issue(game.state, game.content, orders.week_of(game.state, game.content), random.Random(0))


def test_win_at_front_counts_for_siege_but_a_drill_does_not(on):
    game = _game(on, faction="guan", at="changshe")
    _order(game, "siege", "guan", front="yingru")
    with _win():
        msgs = game.choose("act:train")
    assert any("軍令「攻城・潁川汝南」：你 1 次" in m for m in msgs)
    on.squads["louluo"].faction = "guan"  # 自己人：操練不算
    on.squads["shuikou"].faction = "guan"
    game.state.player.stamina = 150
    msgs = game.choose("act:train")
    assert not any("軍令" in m for m in msgs)


def test_intercept_convoy_squad_appears_and_counts(on):
    game = _game(on, faction="guan", at="nanyang_wilds")
    on.locations["nanyang_wilds"].enemies = []  # 只剩糧隊，看得出它是軍令帶來的
    assert "act:train" not in [o.id for o in game.options()]
    _order(game, "intercept", "guan", front="nanyang", location="nanyang_wilds")
    assert "act:train" in [o.id for o in game.options()]
    with _win():
        msgs = game.choose("act:train")
    assert any("黃巾糧隊" in m for m in msgs)
    assert any("軍令「截糧・南陽郊野」：你 1 次" in m for m in msgs)


def test_duty_pushes_the_front_and_counts_for_defend(on):
    game = _game(on, faction="huang", at="changshe")
    _fronts(game, 50, 50, 50)
    _order(game, "defend", "huang", front="yingru")
    option = next(o for o in game.options() if o.id == "act:duty")
    assert option.label == "傳道（體力 10）"
    msgs = game.choose("act:duty")
    assert msgs[0].startswith("你在長社的村口講了一段黃天的道理")
    assert any("（潁川汝南 +1）" in m for m in msgs)
    assert any("軍令「守城・潁川汝南」：你 1 次" in m for m in msgs)
    assert game.state.player.stamina == 140
    assert game.state.player.contrib == 10  # 推 1 點記 10 貢獻（T3）
    assert game.state.journal[0].title == "傳道・長社"
    assert game.state.journal[0].lines[0] == msgs[0]  # 那句敘事寫進「剛剛」與紀錄（FB-043：以前被當成結果標記藏起來）


def test_haoqiang_duty_pushes_geju_only_in_chaos(on):
    game = _game(on, faction="haoqiang", at="changshe")
    _fronts(game, 50, 50, 50)
    geju = rules.trend_value(game.state, on, "geju")
    game.choose("act:duty")
    assert rules.trend_value(game.state, on, "geju") == geju + 1
    _fronts(game, 80, 50, 50)
    game.state.player.stamina = 150
    game.choose("act:duty")
    assert rules.trend_value(game.state, on, "geju") == geju + 1  # 潁川不在亂局：什麼都不推


def test_duty_only_for_members_on_a_front(on):
    assert "act:duty" not in [o.id for o in _game(on, at="changshe").options()]  # 散人
    assert "act:duty" not in [o.id for o in _game(on, "乙", faction="guan", at="luoyang_palace").options()]  # 洛陽沒有戰線


def test_switch_off_no_duty_no_convoy_squad_same_draws(real):
    """開關關著：沒有守勢行動，遊歷的對手清單一樣（亂數抽法一樣），沒有任何軍令的字。"""
    game = _game(real, faction="guan", at="nanyang_wilds")
    assert "act:duty" not in [o.id for o in game.options()]
    assert game._train_squad_ids(real.locations["nanyang_wilds"]) == real.locations["nanyang_wilds"].enemies
    with _win():
        msgs = game.choose("act:train")
    assert not any("軍令" in m for m in msgs)


# ── Task 5：護糧的糧車 ─────────────────────────────────────


def _grain(game, **counts):
    game.state.player.materials.update(counts)


def test_convoy_needs_four_grain_and_says_why(on):
    """RF5：凡品 3 個（3 份）不夠，按鈕停用並寫明；一個天品（9 份）就夠，多的不找。"""
    game = _game(on, faction="guan", at="xinye")
    _order(game, "escort", "guan", front="nanyang", start="xinye", end="wan_city")
    _grain(game, man_1=3)
    option = next(o for o in game.options() if o.id == "act:convoy")
    assert not option.enabled
    assert option.label == "接下糧車（送到宛城・糧草不夠：要 4 份，你有 3 份；糧草是慢屬性的素材）"
    game.state.player.materials = {"man_3": 1}
    option = next(o for o in game.options() if o.id == "act:convoy")
    top = on.materials["man_3"].name
    assert option.enabled and option.label == f"接下糧車（送到宛城・交出糧草 4 份：{top} ×1）"  # 會用掉哪一個寫出來（審查 M6）
    game.choose("act:convoy")
    assert game.state.journal[0].lines == ["你把 4 份糧草裝上車，要送到宛城。路上當心截糧的。"]  # FB-043
    assert game.state.player.materials.get("man_3", 0) == 0
    assert game.state.player.convoy == Convoy(order=game.state.world.orders[-1].id, grain=4, from_loc="xinye", to_loc="wan_city")
    again = next(o for o in game.options() if o.id == "act:convoy")  # 一次押一車：按不下去，寫明手上那一車（T6 審查 I3）
    assert not again.enabled and again.label == "接下糧車（你還押著一車糧，要送到宛城）"


def test_escort_takes_grain_and_records_donation(on):
    game = _game(on, "乙", faction="huang", at="nanyang_wilds")
    on.config.convoy_ambush_chance = 0.0
    escort = _order(game, "escort", "huang", front="nanyang", start="nanyang_wilds", end="nanyang_huangjin_camp")
    _grain(game, man_1=4)
    game.choose("act:convoy")
    assert game.state.player.donations == {}  # 抵達才算
    game.state.player.stamina = 150
    msgs = game.travel("nanyang_huangjin_camp", "dash")
    assert game.state.player.convoy is None
    assert game.state.player.donations == {"nanyang_huangjin_camp:糧草": 4}
    assert game.state.player.contrib == on.config.contrib_per_push
    assert escort.progress == {"乙": 1}
    assert any("軍令「護糧・南陽郊野→南陽黃巾營」：你 1 次" in m for m in msgs)


def test_convoy_ambushed_lost_does_not_count(on):
    game = _game(on, faction="guan", at="xinye")
    on.config.convoy_ambush_chance = 1.0
    escort = _order(game, "escort", "guan", front="nanyang", start="xinye", end="wan_city")
    _grain(game, man_1=4)
    game.choose("act:convoy")
    lose = EncounterResult(tier="落敗", margin=-50, our_power=1, difficulty=30)
    game.state.player.stamina = 150
    with mock.patch.object(team, "fight", return_value=lose):
        msgs = game.travel("wan_city", "dash")
    assert any("黃巾糧隊" in m for m in msgs) and any("糧車被劫" in m for m in msgs)
    assert game.state.player.convoy is None and game.state.player.donations == {} and escort.progress == {}


def test_convoy_ambushed_won_counts(on):
    game = _game(on, faction="guan", at="xinye")
    on.config.convoy_ambush_chance = 1.0
    escort = _order(game, "escort", "guan", front="nanyang", start="xinye", end="wan_city")
    _grain(game, man_1=4)
    game.choose("act:convoy")
    game.state.player.stamina = 150
    with _win():
        game.travel("wan_city", "dash")
    assert escort.progress == {"甲": 1} and game.state.player.donations == {"wan_city:糧草": 4}


def test_convoy_delivered_after_the_week_turned(on):
    """RF4：糧車還在路上就換週了：送到照記捐獻與貢獻，但只算它自己那一道（已經清掉就不算）。"""
    game = _game(on, faction="guan", at="xinye")
    on.config.convoy_ambush_chance = 0.0
    _at_week(game, 1)
    _order(game, "escort", "guan", front="nanyang", start="xinye", end="wan_city")
    _grain(game, man_1=4)
    game.choose("act:convoy")
    _at_week(game, 2)
    game.state.world.orders = []  # 週一清掉了沒達成的
    fresh = _order(game, "escort", "guan", front="nanyang", start="xinye", end="wan_city")
    game.state.player.stamina = 150
    game.travel("wan_city", "dash")
    assert game.state.player.donations == {"wan_city:糧草": 4}
    assert game.state.player.contrib == on.config.contrib_per_push
    assert fresh.progress == {}


def test_switch_off_no_convoy_option(real):
    game = _game(real, faction="guan", at="xinye")
    _grain(game, man_1=9)
    assert "act:convoy" not in [o.id for o in game.options()]


# ── Task 6：打擊大勢人物接上 T4 的挑戰 ──────────────────────────


def test_challenge_win_counts_for_strike(on):
    game = _game(on, faction="guan")
    game.state.player.location = figures.state_of(game.state, on, "bocai").location
    order = _order(game, "strike", "guan", front="yingru", figure="bocai")
    with _win():
        msgs = game.choose("act:challenge:bocai")
    assert any("軍令「打擊・波才」：你 1 次" in m for m in msgs)
    assert order.progress == {"甲": 1}


# ── Task 7：江湖頁的「本週軍令」卡 ───────────────────────────


def _issue_now(game):
    orders.issue(game.state, game.content, orders.week_of(game.state, game.content), random.Random(0))


def test_orders_view_shows_own_side_with_deadline(on):
    game = _game(on, faction="guan")
    _issue_now(game)
    view = game.orders_view()
    assert [v["title"] for v in view] == [orders.title(on, o) for o in orders.current(game.state, on, "guan")]
    first = view[0]
    assert (first["mine"], first["progress"], first["quota"], first["done"]) == (0, 0, 4, False)
    assert first["deadline"] == "第 2 週・週一 00:00"
    assert _game(on, "丙").orders_view() == []  # 散人


# ── Task 8：新手引導多兩步（只在第一季）────────────────────────


def test_two_tutorial_steps_after_joining_only_in_season_one(on):
    from tianxia import guide

    game = _game(on, at="changshe")
    off = load_content(CONTENT_DIR)  # 同一份存檔，開關關著的內容
    assert len(guide.steps(game.state, off)) == 6  # 開關關著：照舊 6 步
    steps = guide.steps(game.state, on)
    assert [s.id for s in steps][-2:] == ["t7_orders", "t8_order_done"]
    assert steps[-2].text.startswith("如今天下分成了三邊")  # 濃縮版內容表 3.4（S1 審過）
    game.state.player.tutorial_step = 6  # 前面六步做完了
    game.choose("faction:guan")
    msgs = game.choose("faction:confirm")
    assert game.state.player.tutorial_step == 7  # 投靠完成「看一眼本週軍令」那一步
    # 下一步的說明在對話框，不在「剛剛」（引導重做設計 8.1.3；畫面批次審查 I2）
    assert not any("軍令上寫什麼" in m or "引導完成" in m for m in msgs)
    assert "✔ 引導完成" in game.state.player.guide_done and game.guide_box()["text"].startswith("軍令上寫什麼，就照著做一次")
    assert not any("引導完成" in line for line in game.state.journal[0].lines)
    _order(game, "siege", "guan", front="yingru")
    with _win():
        game.choose("act:train")
    assert game.state.player.tutorial_step == 8 and not guide.tutorial_active(game.state, on)


def test_a_returning_player_who_finished_the_base_steps_keeps_going(on):
    """換季重來時，做完不分季的六步就算做完引導（FB-034 照舊不重來）；第一季多的兩步接著做。"""
    game = _game(on)
    game.state.player.tutorial_step = 6
    game._reset_player_for_new_season(2)
    assert game.state.player.tutorial_step == 6


# ── Task 9：假人照軍令出力、第一週走完一道軍令 ─────────────────────


def _bot_pick(game, faction):
    from tianxia import bot_policy
    from tianxia.state import BotProfile

    game.content.config.bot_strength = 1.0  # 永遠挑最高分
    profile = BotProfile(personality="普通", seed=1, faction=faction, season_number=1)
    options = [o for o in game.options(odds=False) if o.enabled and o.id != "act:rest"]
    return bot_policy.pick(game, options, profile, random.Random(0))


def test_bot_does_duty_for_a_defend_order(on):
    game = _game(on, faction="guan", at="changshe")
    _order(game, "defend", "guan", front="yingru")
    assert _bot_pick(game, "guan") == "act:duty"


def test_bot_heads_for_its_intercept_place_and_fights_there(on):
    game = _game(on, faction="guan", at="nanyang_road")
    _order(game, "intercept", "guan", front="nanyang", location="nanyang_wilds")
    assert _bot_pick(game, "guan") == "move:wan_city"  # 宛城是南陽郊野的相鄰站，截糧在那裡也算
    game.state.player.location = "wan_city"
    assert _bot_pick(game, "guan") == "act:train"  # 宛城本來沒有敵人，只有軍令帶來的糧隊


def test_bot_takes_a_cart_when_it_has_grain(on):
    game = _game(on, faction="guan", at="xinye")
    _order(game, "escort", "guan", front="nanyang", start="xinye", end="wan_city")
    game.state.player.materials["man_1"] = 4
    assert _bot_pick(game, "guan") == "act:convoy"


def test_bot_challenges_a_strike_target_at_even_odds(on):
    from tianxia import bot_policy

    game = _game(on, faction="guan")
    game.state.player.location = figures.state_of(game.state, on, "bocai").location
    with mock.patch.object(Game, "challenge_odds", return_value="五五波"):
        assert bot_policy.score(game, next(o for o in game.options(odds=False) if o.id == "act:challenge:bocai"),
                                None) is None  # 沒有軍令：五五波不打
        _order(game, "strike", "guan", front="yingru", figure="bocai")
        assert _bot_pick(game, "guan") == "act:challenge:bocai"


def test_new_player_can_join_and_finish_an_order_in_week_one(on):
    """版本目標第四節第 2 條（真實內容）：新角色第 1 週內投靠官軍、看到三道軍令、完成其中一道的個人部分。
    移動用疾行（只看規則，不看路程）。"""
    game = _game(on, at="yingchuan")
    game.state.player.tutorial_step = 6
    game.advance(200)  # 跨過開季後第一個曆時交界：第 1 週發令
    game.state.player.stamina = 150
    game.travel("changshe", "dash")
    game.choose("faction:guan")
    game.choose("faction:confirm")
    assert len(game.orders_view()) == 3
    target = next(o for o in orders.current(game.state, on, "guan") if o.template in ("intercept", "siege"))
    place = target.location if target.template == "intercept" else next(
        loc for loc in on.locations if rules.front_of(on, loc) == target.front and on.locations[loc].enemies
    )
    game.state.player.location = place  # 輿圖只能安排去看得見的地方；這裡只看軍令的規則，直接站過去
    for _ in range(40):
        if target.progress:
            break
        game.state.player.stamina = 150
        with _win():
            game.choose("act:train")
    assert target.progress.get("甲") == 1
    assert orders.week_of(game.state, on) == 1
    assert game.state.player.tutorial_step == 8


def test_a_new_guan_recruit_finishes_a_week_one_order_without_leaving_yingru(on):
    """FB-054：官軍第 1 週的軍令不能全在南陽、冀州（開局戰況潁川 40，官軍不吃緊，守城原本發不出來）。
    官軍的守城寫了開局週（opening_fronts），第 1 週在潁川汝南也發；新角色照引導在長社投靠、不離開潁川，
    巡哨一次就替這道記一次，跟黃巾在營寨傳道一次同一個難度。"""
    game = _game(on, at="yingchuan")
    game.state.player.tutorial_step = 6
    game.advance(200)  # 第 1 週發令
    game.state.player.stamina = 150
    game.travel("changshe", "dash")
    game.choose("faction:guan")
    game.choose("faction:confirm")
    assert orders.week_of(game.state, on) == 1
    defend = next(o for o in orders.current(game.state, on, "guan") if o.template == "defend")
    assert orders.title(on, defend) == "守城・潁川汝南"
    assert defend.id in [card["id"] for card in game.orders_view()]  # 軍令卡上看得到
    here = game.state.player.location
    assert rules.front_of(on, here) == defend.front  # 人在長社，已經站在那條戰線上，不必動
    msgs = game.choose("act:duty")
    assert game.state.player.location == here
    assert defend.progress.get("甲") == 1
    assert any("守城・潁川汝南" in m for m in msgs)
    assert game.state.player.tutorial_step == 8  # 引導的「做完一次軍令」也跟著過


@pytest.mark.parametrize("yingru", [40, 50])
@pytest.mark.parametrize("faction", ["guan", "huang"])
def test_both_sides_get_a_yingru_defend_in_week_one(on, faction, yingru):
    """FB-054 的對稱：兩邊第 1 週都有一道不必出遠門的守城・潁川汝南，不看戰況。40 是開局的數字（黃巾吃緊 60，剛好踩在邊界）；
    50 時黃巾的 losing_by 條件不成立，靠 opening_fronts 照發，不靠邊界。"""
    game = _game(on, faction=faction)
    _fronts(game, yingru, 35, 55)
    _at_week(game, 1)
    orders.issue(game.state, on, 1, random.Random(0))
    assert ("defend", "yingru") in _kinds(game, faction)


def test_the_opening_defend_is_only_for_week_one(on):
    """開局週只放寬第 1 週：之後官軍照舊要戰況吃緊（≥ 60）或敵方上週攻下才守城。"""
    game = _game(on)
    _fronts(game, 50, 35, 55)  # 黃巾在 50 也不吃緊（要 ≤ 40）：第 2 週兩邊都不守潁川汝南
    _at_week(game, 2)
    orders.issue(game.state, on, 2, random.Random(0))
    assert ("defend", "yingru") not in _kinds(game, "guan")
    assert ("defend", "yingru") not in _kinds(game, "huang")


def test_switch_off_no_week_one_defend_for_guan(real):
    """開關關著：官軍第 1 週也沒有軍令、沒有「巡哨」（開局週只在第一季規則開著時有效，關著跟 beta 一樣）。"""
    game = _game(real, faction="guan", at="changshe")
    game.advance(200)
    assert game.state.world.orders == []
    assert orders.current(game.state, real, "guan") == []
    assert "act:duty" not in [o.id for o in game.options()]


def test_opening_fronts_must_be_real_fronts(real):
    """內容檢查：開局週的戰線要是真的戰線，寫錯在載入當下報錯。"""
    from tianxia.content import ContentError, validate

    template = next(t for t in real.orders.templates if t.kind == "defend" and t.side == "guan")
    assert template.when.opening_fronts == ["yingru"]
    template.when.opening_fronts = ["nowhere"]
    with pytest.raises(ContentError, match="nowhere"):
        validate(real)


# ── 審查修正 ───────────────────────────────────────────────


def test_map_place_detail_hides_other_sides_orders(on):
    """T6 審查 C1：輿圖地點詳情的「龍頭人物最近的傳聞」不能露出別陣營的軍令與軍情（跟見聞頁、沿途打聽同一個規則）。"""
    game = _game(on, faction="huang")
    game.advance(200)  # 第 1 週發令
    others = [o.text for o in game.state.world.orders if o.faction != "huang"]
    assert others
    game.state.player.visited |= set(on.locations)  # 每個地點都算去過，詳情欄才會寫人物與傳聞
    for loc_id in on.locations:
        detail = game.place_detail(loc_id)
        assert not any(text in detail for text in others), loc_id


def test_no_siege_where_the_enemy_has_no_squad(on):
    """T6 審查 I2：潁川汝南沒有任何一支官軍隊伍，黃巾在那裡打不贏「敵方陣營的隊伍」，攻城永遠湊不滿：不發。
    假人也只往打得到敵方隊伍的地點走、只在那裡把遊歷算成攻城。"""
    assert orders.siege_places(on, "huang", "yingru") == []
    assert "nanyang_wilds" in orders.siege_places(on, "huang", "nanyang")
    assert "changshe" in orders.siege_places(on, "guan", "yingru")
    game = _game(on, faction="huang", at="changshe")
    _fronts(game, 55, 55, 55)
    _at_week(game, 1)
    _issue_now(game)
    assert ("siege", "yingru") not in _kinds(game, "huang") and len(_kinds(game, "huang")) == 3
    game.state.world.orders = []  # 只看攻城這一道
    _order(game, "siege", "huang", front="nanyang")
    assert not orders.win_counts(game.state, on, "huang", "xinye")  # 新野在南陽、但沒有官軍隊伍
    assert orders.win_counts(game.state, on, "huang", "nanyang_wilds")
    assert orders.targets(game.state, on, "huang") == orders.siege_places(on, "huang", "nanyang")


def test_a_cart_whose_order_is_gone_is_still_shown_and_delivered(on):
    """T6 審查 I3：押著的糧車那一道已經達成或換週清掉了，選單、軍令卡照樣看得到它要送去哪；新的護糧起點寫明
    為什麼接不了；假人照樣把它送到。"""
    game = _game(on, faction="guan", at="xinye")
    first = _order(game, "escort", "guan", front="nanyang", start="xinye", end="wan_city")
    game.state.player.materials["man_1"] = 8
    game.choose("act:convoy")
    first.done = True  # 別人湊滿了
    _order(game, "escort", "guan", front="yingru", start="xinye", end="changshe")  # 同一個起點又有一道
    option = next(o for o in game.options() if o.id == "act:convoy")
    assert not option.enabled and option.label == "接下糧車（你還押著一車糧，要送到宛城）"
    assert game.convoy_line() == "你押著一車糧（4 份），要送到宛城。"
    assert "wan_city" in orders.targets(game.state, on, "guan")
    assert _game(on, "乙", faction="guan").convoy_line() is None


def test_switch_off_joining_does_not_touch_the_tutorial(real):
    """T6 審查 M4：投靠那一刻推引導是第一季才有的（t7_orders 只看陣營）；beta 照舊等下一個行動才檢查。"""
    game = _game(real, at="changshe")
    steps = [s.id for s in real.tutorial.steps]
    game.state.player.tutorial_step = steps.index("t4_practice")
    game.state.player.member.wugong_id = "xingwu_qiang"  # 例如煉製來的武學：煉製不推引導
    game.choose("faction:guan")
    game.choose("faction:confirm")
    assert game.state.player.tutorial_step == steps.index("t4_practice")


def test_cart_button_names_the_materials_it_uses(on):
    """T6 審查 M6：按鈕寫明會用掉哪些素材（從低階的用起，多的不找），免得不知不覺交掉唯一的天品。"""
    from tianxia import materials

    game = _game(on, faction="guan", at="xinye")
    _order(game, "escort", "guan", front="nanyang", start="xinye", end="wan_city")
    low, top = on.materials["man_1"].name, on.materials["man_3"].name
    game.state.player.materials.update({"man_1": 3, "man_3": 1})
    assert materials.grain_plan(game.state, on, 4) == [("man_1", 3), ("man_3", 1)]
    label = next(o for o in game.options() if o.id == "act:convoy").label
    assert label == f"接下糧車（送到宛城・交出糧草 4 份：{low} ×3、{top} ×1）"
    game.choose("act:convoy")
    assert game.state.player.materials.get("man_1", 0) == 0 and game.state.player.materials.get("man_3", 0) == 0


# ── FB-061：每週留一格給進攻的軍令（攻城、打擊） ─────────────────────────────

OFFENSE = ("siege", "strike")


@pytest.fixture
def crowded(on):
    """三條戰線都在 50、而且每條兩週內都有大事：截糧、護糧到處發得出來，沒有留格的話三格全被優先序 1～2 佔滿。"""
    with mock.patch.object(orders, "_event_within", return_value=object()):
        game = _game(on)
        _fronts(game, 50, 50, 50)
        yield game


def _week_orders(game, faction, week):
    """這一週發令之後，這個陣營拿到的軍令（照發出的順序）。"""
    game.state.world.orders = []
    _at_week(game, week)
    orders.issue(game.state, game.content, week, random.Random(0))
    return [o for o in game.state.world.orders if o.faction == faction]


@pytest.mark.parametrize("faction", ["guan", "huang"])
@pytest.mark.parametrize("week", [3, 5, 7, 9])
def test_odd_weeks_reserve_one_slot_for_a_siege(crowded, faction, week):
    got = _week_orders(crowded, faction, week)
    kinds = [o.template for o in got]
    assert len(got) == 3 and kinds.count("siege") == 1 and "strike" not in kinds


@pytest.mark.parametrize("faction", ["guan", "huang"])
@pytest.mark.parametrize("week", [2, 4, 6, 8])
def test_even_weeks_reserve_one_slot_for_a_strike(crowded, faction, week):
    got = _week_orders(crowded, faction, week)
    kinds = [o.template for o in got]
    assert len(got) == 3 and kinds.count("strike") == 1 and "siege" not in kinds


def test_the_other_two_slots_keep_their_priority_order(crowded):
    """留一格之後，其餘兩格跟沒留一樣：就是把進攻那一道拿掉之後，優先序最前面的兩道。"""
    for week in (3, 4):
        for faction in ("guan", "huang"):
            with_offense = _week_orders(crowded, faction, week)
            rest = [(o.template, o.front, o.location, o.start) for o in with_offense if o.template not in OFFENSE]
            with mock.patch.object(orders, "strike_target", return_value=None), \
                    mock.patch.object(orders, "siege_places", return_value=[]):
                plain = [(o.template, o.front, o.location, o.start) for o in _week_orders(crowded, faction, week)]
            assert len(rest) == 2 and rest == plain[:2]


@pytest.mark.parametrize("faction", ["guan", "huang"])
def test_a_missing_strike_target_falls_back_to_a_siege(crowded, faction):
    """偶數週偏好打擊；沒有打擊的對象就改發攻城。"""
    with mock.patch.object(orders, "strike_target", return_value=None):
        kinds = [o.template for o in _week_orders(crowded, faction, 4)]
    assert len(kinds) == 3 and kinds.count("siege") == 1 and "strike" not in kinds


@pytest.mark.parametrize("faction", ["guan", "huang"])
def test_a_missing_siege_target_falls_back_to_a_strike(crowded, faction):
    """奇數週偏好攻城；沒有打得到敵方隊伍的戰線就改發打擊。"""
    with mock.patch.object(orders, "siege_places", return_value=[]):
        kinds = [o.template for o in _week_orders(crowded, faction, 3)]
    assert len(kinds) == 3 and kinds.count("strike") == 1 and "siege" not in kinds


@pytest.mark.parametrize("week", [3, 4])
@pytest.mark.parametrize("faction", ["guan", "huang"])
def test_with_no_offense_at_all_the_slot_goes_back_to_priority(crowded, faction, week):
    """兩種進攻都沒有對象：那一格照原本的優先序給下一道，三格還是滿的。"""
    with mock.patch.object(orders, "strike_target", return_value=None), \
            mock.patch.object(orders, "siege_places", return_value=[]):
        got = _week_orders(crowded, faction, week)
    assert len(got) == 3 and not any(o.template in OFFENSE for o in got)
    assert {o.template for o in got} <= {"defend", "intercept", "escort"}


@pytest.fixture
def pressed(on):
    """兩邊都有一道守城（官軍冀州 60、黃巾南陽 40 吃緊），而且每條戰線兩週內都有大事：守城之外只剩一格優先序 2，
    截糧、護糧都發得出來（留一格給進攻之後，這就是 FB-061 審查找到的情形）。"""
    with mock.patch.object(orders, "_event_within", return_value=object()):
        game = _game(on)
        _fronts(game, 45, 40, 60)
        yield game


@pytest.mark.parametrize("faction", ["guan", "huang"])
@pytest.mark.parametrize("week, supply", [(3, "intercept"), (5, "intercept"), (4, "escort"), (6, "escort")])
def test_the_supply_slot_alternates_between_intercept_and_escort(pressed, faction, week, supply):
    """守城、進攻之外只剩一格優先序 2 時，截糧與護糧輪流：奇數週截糧、偶數週護糧（不然同優先序的平手永遠是截糧贏，護糧一道都發不出）。"""
    got = _week_orders(pressed, faction, week)
    kinds = [o.template for o in got]
    assert kinds.count("defend") >= 1 and sum(k in OFFENSE for k in kinds) == 1
    supplies = [k for k in kinds if k in ("intercept", "escort")]
    assert supplies == [supply]


def test_the_supply_alternation_only_breaks_ties_within_one_priority(pressed):
    """輪流只動優先序 2 裡面的次序：守城（優先序 1）照舊排在前面，進攻那一道照舊排在後面。"""
    for week in (3, 4):
        kinds = [o.template for o in _week_orders(pressed, "guan", week)]
        assert kinds[0] == "defend" and kinds[-1] in OFFENSE


def test_week_one_composition_with_the_offense(on):
    """第 1 週（奇數，偏好攻城）：開局的守城・潁川汝南照發。官軍 ＝ 守城・潁川汝南、一道截糧、攻城・冀州（冀州 55 最吃緊的攻城戰線）；
    黃巾 ＝ 兩道守城（南陽 65、潁川汝南 60 都吃緊）、攻城・南陽（潁川汝南沒有官軍隊伍，攻不了）。"""
    game = _game(on)
    guan = _week_orders(game, "guan", 1)
    assert [(o.template, o.front) for o in guan] == [("defend", "yingru"), ("intercept", "nanyang"), ("siege", "jizhou")]
    huang = _week_orders(game, "huang", 1)
    assert [(o.template, o.front) for o in huang] == [("defend", "nanyang"), ("defend", "yingru"), ("siege", "nanyang")]
    assert sum(o.template in ("intercept", "escort") for o in guan) == 1


def test_haoqiang_keeps_its_single_strike_every_week(on):
    """豪強只有一種模板（打擊），每週最多一道：留格不能讓它多發、少發或重複發，奇偶週都一樣。"""
    game = _game(on)
    for week in range(1, 9):
        got = _week_orders(game, "haoqiang", week)
        assert [o.template for o in got] == ["strike"], week
        assert got[0].figure == orders.strike_target(game.state, on, next(
            t for t in on.orders.templates if t.side == "haoqiang"))


def test_a_one_slot_week_keeps_plain_priority(crowded):
    """每週只有一格時沒有「其中一格」可留：照優先序，不讓進攻的軍令把守城、截糧、護糧全擠掉。"""
    crowded.content.config.orders_per_week = 1
    for week in (3, 4):
        kinds = [o.template for o in _week_orders(crowded, "guan", week)]
        assert len(kinds) == 1 and kinds[0] not in OFFENSE


def test_switch_off_no_orders_in_any_week(real):
    """開關關著：軍令只在第一季存在，每一週發令都什麼都不做（包括偏好的進攻軍令）。"""
    game = _game(real, faction="guan")
    for week in range(1, 5):
        _at_week(game, week)
        assert orders.issue(game.state, real, week, random.Random(0)) == []
        assert game.state.world.orders == []
