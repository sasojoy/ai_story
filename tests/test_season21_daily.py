"""正式季第 5 批：21 天的季（season21）每天一道軍令、每天一批懸賞、懸賞照等級長、推線的速度（正式季整合設計第七章、6.1）。
週末與 14 天的季一個字都不變。"""
from __future__ import annotations

import random

from conftest import real_content

from tianxia import calendar, orders, push, world
from tianxia.world_state import fresh_season, stamp_season

HOUR, DAY = 3600, 86400
MON = 1792339200  # 2026-10-19 週一 00:00（台灣）
WED = 1792549800  # 2026-10-21 週三 10:30（台灣）


def _vehicle(content, now=MON):
    season = fresh_season(content)
    stamp_season(season, content, now=now)
    world.settle_season_start(season, content, random.Random(0))
    return world._season_vehicle(content, season)


def _advance(vehicle, content, to):
    world.advance_world_state(vehicle.world, content, to - vehicle.world.time, random.Random(0))


def _live(vehicle, faction=None):
    return [o for o in vehicle.world.orders if not o.done and (faction is None or o.faction == faction)]


# ── Task 1：每天一道軍令 ──


def test_each_day_issues_one_order_per_faction():
    c = real_content("season21")
    v = _vehicle(c)
    factions = {o.faction for o in _live(v)}
    assert {"guan", "huang"} <= factions
    assert all(len(_live(v, f)) == c.config.season21_daily.orders_per_day for f in factions)
    assert {o.week for o in _live(v)} == {1}  # 21 天季的軍令照「期」記：季曆第幾天
    assert any(r.text.startswith(orders.ISSUED_DAY) for r in v.world.rumors if r.layer == "faction")
    _advance(v, c, DAY + 60)
    assert {o.week for o in _live(v)} == {2}  # 第 1 天沒達成的清掉


def test_daily_orders_take_turns():
    c = real_content("season21")
    v = _vehicle(c)
    kinds = []
    for day in range(3):
        _advance(v, c, day * DAY + 60)
        kinds += [o.template for o in _live(v, "guan")]
    assert len(set(kinds)) >= 2  # 守、進攻、補給輪流


def test_a_daily_order_applies_a_share_of_its_effect():
    c = real_content("season21")
    v = _vehicle(c)
    o = next(o for o in _live(v, "guan") if o.template in ("siege", "defend", "intercept", "escort"))
    nominal = orders.template_of(c, o).effect.trend
    orders._complete(v, c, o)
    assert o.applied == push.round_half_away(nominal * c.config.season21_daily.order_effect_share)


def test_the_order_card_says_midnight():
    c = real_content("season21")
    v = _vehicle(c)
    o = _live(v, "guan")[0]
    assert calendar.stamp_text(orders.deadline(v, c, o), c, v.world) == "第 1 週・週二 00:00"


def test_a_wednesday_opening_and_a_long_catch_up_issue_only_today():
    """Review Focus 1、2：週三開季只發第 3 天的；一次補算跨過好幾天只發今天的。"""
    c = real_content("season21")
    v = _vehicle(c, now=WED)
    assert {o.week for o in v.world.orders} == {3}
    _advance(v, c, 4 * DAY)  # 開季後四天：第 7 天（週日）
    assert {o.week for o in _live(v)} == {calendar.point(v.world.time, c, v.world).cal_day}
    assert not any(o.week in (4, 5, 6) for o in v.world.orders)


def test_weekend_orders_are_weekly():
    """Review Focus 5：週末的季照舊每週一發、一週最多 orders_per_week 道，寫「本週軍令：」。"""
    c = real_content("weekend")
    v = _vehicle(c)
    assert {o.week for o in v.world.orders} == {1}
    assert all(len(_live(v, f)) <= c.config.orders_per_week for f in ("guan", "huang"))
    assert any(r.text.startswith(orders.ISSUED) for r in v.world.rumors if r.layer == "faction")
    assert not any(r.text.startswith(orders.ISSUED_DAY) for r in v.world.rumors)


def _game(profile="season21", opened=MON):
    from tianxia.engine import Game
    from tianxia.sqlite_world import open_world

    c = real_content(profile)
    c.config.admins = ["甲"]
    c.config.train_event_chance = 0.0
    w = open_world()
    w.seed_first_season(c)
    game = Game.new(c, "甲", rng=random.Random(0), world=w)
    game.client = None
    game.admin_open_season(opened)  # 同管理者開季：開季那一刻的掛鉤（軍令、懸賞）照跑
    game.state.player.faction = "guan"
    game.sync(opened)
    return game


def test_the_orders_card_reopens_each_day():
    """21 天季的軍令每天一道：軍令卡收起來照「第幾天」記（status.calendar.day），隔天的新軍令重新展開；週末照週記、沒有 day。"""
    import server
    from test_prologue_web import run, with_reveal

    game = _game()
    assert game.status_data()["calendar"]["day"] == 1
    m = with_reveal(server.main_view(game), ["all"])
    shut = run(m, "return H.pageJianghu();", S={"ordersShut": 1})
    assert 'class="fold orders" data-week="1" >' in shut  # 今天收起來的照舊收著
    game.sync(MON + DAY + 60)
    m = with_reveal(server.main_view(game), ["all"])
    reopened = run(m, "return H.pageJianghu();", S={"ordersShut": 1})
    assert 'class="fold orders" data-week="2" open>' in reopened  # 隔天的新軍令展開
    assert "day" not in _game("weekend").status_data()["calendar"]


# ── Task 2：每天一批懸賞 ──


def _batch(vehicle, day):
    return [b for b in vehicle.world.bounties if b.day == day]


def test_each_day_hangs_a_batch():
    c = real_content("season21")
    v = _vehicle(c)
    first = _batch(v, 1)
    for side in ("guan", "huang"):
        kinds = sorted(b.kind for b in first if b.faction == side and b.kind in ("strike", "scout", "escort"))
        assert kinds == ["scout", "strike"]
    gives = [b for b in first if b.kind in ("art", "arms")]
    assert gives and {b.kind for b in gives} == {"art"}  # 第 1 天求藝
    assert len({b.faction for b in gives}) == len(gives)  # 一個陣營一張
    assert all(b.week == 1 for b in first)  # week 照舊是季曆週
    due = calendar.week_start(1, c, v.world) + 2 * DAY / calendar.cal_scale(c, v.world)
    assert all(b.expires == due for b in first)  # 期限：兩天後的 00:00（週三 00:00）
    assert calendar.stamp_text(due, c, v.world) == "第 1 週・週三 00:00"
    _advance(v, c, DAY + 60)
    second = _batch(v, 2)
    for side in ("guan", "huang"):
        kinds = sorted(b.kind for b in second if b.faction == side and b.kind in ("strike", "scout", "escort"))
        assert kinds == ["escort", "strike"]
    assert {b.kind for b in second if b.kind in ("art", "arms")} == {"arms"}  # 第 2 天求兵


def test_a_wednesday_opening_and_a_long_catch_up_hang_only_today():
    """Review Focus 1、2：週三開季只掛第 3 天的；一次補算跨過好幾天只掛今天的。"""
    from tianxia import bounties

    c = real_content("season21")
    v = _vehicle(c, now=WED)
    assert {b.day for b in v.world.bounties} == {3}
    _advance(v, c, 4 * DAY)  # 補算逐小時走：每天的那一批在那天 00:00 掛、兩天後下榜，留著的只有昨天與今天的
    today = calendar.point(v.world.time, c, v.world).cal_day
    assert {b.day for b in v.world.bounties} == {today - 1, today}
    before = len(v.world.bounties)
    assert bounties.issue_day(v, c, today - 2, random.Random(0)) == [] and len(v.world.bounties) == before  # 過去的天不補掛
    v.world.bounty_day = 0
    assert bounties.issue_day(v, c, today - 2, random.Random(0)) == [] and len(v.world.bounties) == before


def test_the_notice_names_the_last_day():
    """店面告示上短的那一行：每天一批的單在某天 00:00 到期，寫最後還有效的那一天（同週次寫最後還有效的那一週，FB-196）。待 joy 潤。"""
    from tianxia import bounties

    c = real_content("season21")
    v = _vehicle(c)
    b = next(b for b in _batch(v, 1) if b.kind == "strike")
    assert bounties.due_short(b, c, v.world) == f"到第 1 週週二・剩 {b.quota}"


def test_daily_prizes_hang_on_strike_and_on_the_second_bill():
    from tianxia import bounties

    c = real_content("season21")
    c.config.season21_daily.prize_treasure_chance = 1.0
    c.config.season21_daily.prize_horse_chance = 1.0
    v = _vehicle(c)
    for side in ("guan", "huang"):
        mine = [b for b in _batch(v, 1) if b.faction == side]
        assert {b.kind: b.prize for b in mine if b.kind in ("strike", "scout")} == {"strike": "treasure", "scout": "horse"}
    assert bounties.prize_rolls_day(0, 1, "guan", c) == (True, True)
    c.config.season21_daily.prize_treasure_chance = 0.0
    c.config.season21_daily.prize_horse_chance = 0.0
    assert bounties.prize_rolls_day(0, 1, "guan", c) == (False, False)


def test_weekend_bounties_are_weekly():
    """Review Focus 5：週末照舊每週一批、掛 auto_weeks 週，沒有 day。"""
    c = real_content("weekend")
    v = _vehicle(c)
    assert v.world.bounties and all(b.day == 0 and b.week == 1 for b in v.world.bounties)
    assert all(b.expires == calendar.week_start(1 + c.config.bounties.auto_weeks, c, v.world)
               for b in v.world.bounties if b.kind != "wanted")
    assert v.world.bounty_day == 0


# ── Task 3：懸賞獎勵照等級長、附一樣東西 ──


def _first(state, kind, faction=None):
    return next(b for b in state.world.bounties if b.kind == kind and (faction is None or b.faction == faction))


def _gained(before, after):
    return {k: v - before.get(k, 0) for k, v in after.items() if v != before.get(k, 0)}


def test_rewards_grow_with_the_level():
    from tianxia import bounties, team

    game = _game()
    s, c = game.state, game.content
    s.player.faction = None  # 散人：全額
    s.player.member.level = 20
    b = _first(s, "strike")
    exp = round(team.level_cost(c.config, 20) * 0.15)
    assert bounties.reward_text(s, c, b).startswith(f"賞銀 120・經驗 {exp}")  # 6.1 的例子：第 20 級一張討伐 120 兩
    silver = s.player.stats.get("silver", 0)
    msgs = bounties._complete(s, c, game.world, b)
    assert s.player.stats["silver"] - silver == 120 and f"經驗 +{exp}" in msgs
    s.player.faction = "guan"  # 陣營的人做自己陣營的：一半
    mine = _first(s, "strike", "guan")
    assert bounties.reward_text(s, c, mine).startswith(f"賞銀 60・經驗 {round(exp / 2)}")
    scout = _first(s, "scout", "guan")
    assert bounties._silver(s, c, scout) == round(20 * 3 / 2)
    assert bounties._exp(s, c, scout) == round(team.level_cost(c.config, 20) * 0.08 / 2)


def test_each_bill_brings_one_thing():
    """討伐給對手屬性的二階（另擲三階）、打探給一顆回體丹、護送給終點屬性的二階；對手或終點沒屬性也給（Review Focus 4）。"""
    from tianxia import bounties, materials

    game = _game()
    s, c = game.state, game.content
    s.player.faction = None
    c.config.season21_daily.strike_tier3_chance = 1.0
    strike = _first(s, "strike")
    attr = c.squads[strike.squad].attribute
    before = dict(s.player.materials)
    msgs = bounties._complete(s, c, game.world, strike)
    got = _gained(before, s.player.materials)
    assert sorted(c.materials[m].tier for m in got) == [2, 3]
    assert all(c.materials[m].attribute == attr for m in got) or attr is None
    assert any(m.startswith(materials.GRANT_PREFIX) for m in msgs)
    pills = s.player.stamina_pills
    bounties._complete(s, c, game.world, _first(s, "scout"))
    assert s.player.stamina_pills == pills + 1
    c.squads[strike.squad].attribute = None  # 對手沒寫屬性：照同階隨便一個
    strike.done_by = []
    before = dict(s.player.materials)
    bounties._complete(s, c, game.world, strike)
    assert sorted(c.materials[m].tier for m in _gained(before, s.player.materials)) == [2, 3]
    game.sync(MON + DAY + 60)
    s = game.state
    s.player.faction = None
    escort = _first(s, "escort")
    before = dict(s.player.materials)
    bounties._complete(s, c, game.world, escort)
    got = _gained(before, s.player.materials)
    assert [c.materials[m].tier for m in got] == [2]
    assert c.materials[next(iter(got))].attribute in {c.materials[m].attribute for m in c.locations[escort.end].materials}
    c.locations[escort.end].materials = []  # 終點沒寫素材屬性
    escort.done_by = []
    before = dict(s.player.materials)
    bounties._complete(s, c, game.world, escort)
    assert [c.materials[m].tier for m in _gained(before, s.player.materials)] == [2]


def test_maxed_players_get_xinde():
    """Review Focus 3：滿級的人交懸賞，經驗照 5 換 1 換成心得，不寫「經驗 +N」。"""
    from tianxia import bounties, team

    game = _game()
    s, c = game.state, game.content
    s.player.faction = None
    s.player.member.level = c.config.max_level
    b = _first(s, "strike")
    xinde = round(team.level_cost(c.config, c.config.max_level) * 0.15) // c.config.season21_daily.maxed_exp_per_xinde
    assert xinde > 0
    text = bounties.reward_text(s, c, b)
    assert f"・心得 {xinde}" in text and "經驗" not in text
    have = s.player.stats.get("xinde", 0)
    msgs = bounties._complete(s, c, game.world, b)
    assert s.player.stats["xinde"] - have == xinde and f"心得 +{xinde}" in msgs
    assert not any(m.startswith("經驗") for m in msgs)


def test_arms_add_the_level_silver():
    from tianxia import bounties

    game = _game()
    game.sync(MON + DAY + 60)
    s, c = game.state, game.content
    s.player.member.level = 10
    arms = _first(s, "arms")
    base = c.config.bounties.arms_silver["中品"] * c.config.bounties.arms_tier["1"]
    assert bounties._silver(s, c, arms, base=base) == base + 10 * 5
    assert bounties._silver(s, c, _first(s, "art")) == 10 * 5  # 第 1 天的求藝還掛著：照等級每級 5 兩


def test_weekend_rewards_unchanged():
    """Review Focus 5：週末照舊固定的數字、不附東西。"""
    from tianxia import bounties

    game = _game("weekend")
    s, c = game.state, game.content
    s.player.faction = None
    s.player.member.level = 20
    b = _first(s, "strike")
    assert bounties._silver(s, c, b) == c.config.bounties.silver["strike"]
    assert bounties._exp(s, c, b) == c.config.bounties.exp["strike"]
    assert bounties.reward_text(s, c, b).startswith(f"賞銀 {c.config.bounties.silver['strike']}・經驗 {c.config.bounties.exp['strike']}")
    pills, before = s.player.stamina_pills, dict(s.player.materials)
    bounties._complete(s, c, game.world, _first(s, "scout"))
    assert s.player.stamina_pills == pills and s.player.materials == before
