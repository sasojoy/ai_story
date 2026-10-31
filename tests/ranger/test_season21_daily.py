"""正式季第 5 批：21 天的季（season21）每天一道軍令、每天一批懸賞、懸賞照等級長、推線的速度（正式季整合設計第七章、6.1）。
週末與 14 天的季一個字都不變。"""
from __future__ import annotations

import random

from conftest import no_plans, no_week_unlock, real_content

from tianxia import calendar, orders, push, world
from tianxia.world_state import fresh_season, stamp_season
import pytest
import test_week7_season as fb501web
from conftest import real_content
from tianxia import calendar, enlist, guide, howto, orders, world
from tianxia.state import Order, new_game_state

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


@pytest.mark.smoke
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


def _game(profile="season21", opened=MON):
    from tianxia.engine import Game
    from tianxia.sqlite_world import open_world

    c = no_plans(no_week_unlock(real_content(profile)))  # 開季第一天就進店：功能照週解鎖（減法季 6.6）關掉；傳聞寫死，行程關掉
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
    # 第 1 天原本掛求藝；求藝 Joy 2026-10-21 拿掉（「懸賞榜直接把武學拿掉」），單數天就沒有要交東西的那一張
    assert not [b for b in first if b.kind in ("art", "arms")]
    assert all(b.week == 1 for b in first)  # week 照舊是季曆週
    due = calendar.week_start(1, c, v.world) + 2 * DAY / calendar.cal_scale(c, v.world)
    assert all(b.expires == due for b in first)  # 期限：兩天後的 00:00（週三 00:00）
    assert calendar.stamp_text(due, c, v.world) == "第 1 週・週三 00:00"
    _advance(v, c, DAY + 60)
    second = _batch(v, 2)
    for side in ("guan", "huang"):
        kinds = sorted(b.kind for b in second if b.faction == side and b.kind in ("strike", "scout", "escort"))
        assert kinds == ["escort", "strike"]
    gives = [b for b in second if b.kind in ("art", "arms")]
    assert gives and {b.kind for b in gives} == {"arms"}  # 第 2 天求兵
    assert len({b.faction for b in gives}) == len(gives)  # 一個陣營一張


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
    # 求藝 2026-10-21 拿掉之後第 1 天少掛三張，第 2 天的亂數（種子帶流水號）跟著位移，掛出來的護送終點都沒寫素材：
    # 換一個寫了素材的終點，這一段照舊測「照終點的屬性給」（沒寫素材的那一種在下面另測）
    if not c.locations[escort.end].materials:
        escort.end = next(lid for lid, loc in c.locations.items() if loc.materials)
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
    xinde = round(team.level_cost(c.config, c.config.max_level) * 0.15) // c.config.maxed_exp_per_xinde
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
    assert bounties._silver(s, c, arms, base=base) == base + 10 * 5  # 第 1 天的求藝（照等級每級 5 兩）Joy 2026-10-21 拿掉


# ── Task 4：推大勢的速度 ──


def _back_to_middle(game):
    """一條戰線與一個往 50 拉的推力（往回拉一律全額，不碰盡頭阻力）。"""
    from tianxia import rules

    line = sorted(game._resisted_lines())[0]
    return line, (4 if rules.trend_value(game.state, game.content, line) <= 50 else -4)


def test_season21_sortie_drops_the_season_scale():
    """出陣、捐軍備乘 push_speed，不乘季長倍數（7.4；以前 21 天季乘約 0.12）。"""
    game = _game()
    c = game.content
    assert game.season_scale() < 1
    line, d = _back_to_middle(game)
    assert game._shaped(line, d, "sortie") == (d * c.config.season21_daily.push_speed, False)
    c.config.season21_daily.push_speed = 0.5
    assert game._shaped(line, d, "sortie")[0] == d * 0.5
    assert game._shaped(line, d, "donate")[0] == d * 0.5


def test_season21_events_follow_the_same_speed():
    """可重複的事件照同一個速度（再乘事件五折）；一次性的照全額。"""
    game = _game()
    c = game.content
    c.config.season21_daily.push_speed = 0.5
    line, d = _back_to_middle(game)
    share = c.config.explore_modes.event_trend_share if c.config.explore_modes.enabled else 1.0
    assert game._shaped(line, d, "event")[0] == d * share * 0.5
    assert game._shaped(line, d, "event_once")[0] == d


def test_season21_cap_and_resistance_use_their_own_numbers():
    """每人每天上限與盡頭阻力讀 Season21Daily（不乘季長倍數）；軍令的推線照同一組阻力。"""
    from tianxia import orders, rules

    game = _game()
    c, s21 = game.content, game.content.config.season21_daily
    s21.push_daily_cap = 7
    assert game.daily_push_cap() == 7
    s21.push_mid_share, s21.push_far_share = 0.3, 0.1
    tuning = push.tuning_for(game.state.world, c)
    assert (tuning.mid_share, tuning.far_share) == (0.3, 0.1)
    assert tuning.full_within == c.config.push_resistance.full_within
    line = sorted(game._resisted_lines())[0]
    game.state.world.trends[line] = 90
    assert game._shaped(line, 10, "sortie") == (10 * s21.push_speed * 0.1, True)
    assert line in rules.front_ids(c)  # 第一季規則：會動的線就是三條戰線本身
    moved, _ = orders.front_push(game.state, c, line, 10)
    assert moved == 1  # 軍令湊滿推的量照同一組阻力：10 × 0.1


def test_the_away_summary_keeps_only_today_s_orders():
    """「你不在的時候」：21 天季的軍令每天一期，只留最新那一天發的（同週末只留最新那一週）。"""
    from tianxia import rumor_view

    game = _game()
    game.sync(MON + 2 * DAY + 60)
    c = game.content
    issued = [r for r in game.state.world.rumors if r.layer == "faction" and r.text.startswith(orders.ISSUED_DAY)]
    assert len({calendar.point(r.time, c, game.state.world).cal_day for r in issued}) == 3  # 三天各發過一次
    lines, _ = rumor_view.away_lines(game.state, c, None, game.stamp)
    shown = [line for line in lines if orders.ISSUED_DAY in line]
    assert shown and all("週三 00:00" in line for line in shown)  # 開季在週一 00:00：第 3 天是週三


# ── 原 test_fb502_season21_order_words.py（整檔搬進來） ──
# FB-502（PM 2026-10-20，推翻 FB-501 那一批「21 天季不動」）：21 天季的軍令其實也是每天一道，「本週軍令」「每週一發令」
# 「投靠陣營之後每週一有軍令」「本週截斷它」這些字在 21 天季也照「今日／每天」寫。換字照「這一季的軍令是不是每天發」
# （calendar.orders_daily＝照現實天的季，同 orders.daily），不是照「有沒有段」（week7_on）。21 天季其他「週」的字（第 N 週、
# 本週大事、時刻表、第 4 階席次）不動；週末、14 天一個字都不變。字待 joy 潤。

ORDER_KEYS = ("order_this", "order_that", "order_each", "order_every")


SEGMENT_KEYS = ("this", "this_one", "each", "this_short")


def _content(profile):
    return real_content(profile) if profile else real_content()


def _season(content):
    season = fresh_season(content)
    stamp_season(season, content, now=MON)
    return season


def _state(content, faction=None):
    state = new_game_state(content, "甲")
    state.world = _season(content)
    state.player.faction = faction
    state.player.tutorial_step = len(guide.steps(state, content))  # 序章走完（入伍段的框與「下一步」才輪得到引薦人）
    return state


# ── 同一個函式：照軍令是不是每天發 ──


@pytest.mark.slow
@pytest.mark.parametrize("profile,daily", [("week7", True), ("season21", True), (None, False)])
def test_orders_daily_is_the_one_switch(profile, daily):
    content = _content(profile)
    state = _state(content)
    assert calendar.orders_daily(state.world, content) is daily
    assert orders.daily(state, content) is daily


@pytest.mark.slow
def test_season21_order_words_say_today_but_weeks_stay():
    c21 = real_content("season21")
    s21 = _season(c21)
    assert [calendar.week_word(k, c21, s21) for k in ORDER_KEYS] == ["今日", "今天", "每天", "每天"]
    assert [calendar.week_word(k, c21, s21) for k in SEGMENT_KEYS] == ["本週", "這一週", "每週", "這週"]
    assert calendar.week_label(2, c21, s21) == "第 2 週"
    assert calendar.week_words(c21, s21) == {"order_this": "今日", "order_that": "今天", "order_each": "每天", "order_every": "每天"}


@pytest.mark.slow
@pytest.mark.parametrize("profile", [None])
def test_weekend_and_fourteen_day_keep_every_week_word(profile):
    content = _content(profile)
    season = _season(content)
    assert calendar.week_words(content, season) is None
    assert [calendar.week_word(k, content, season) for k in ORDER_KEYS] == ["本週", "這週", "每週一", "每週"]
    assert [calendar.week_word(k, content, season) for k in SEGMENT_KEYS] == ["本週", "這一週", "每週", "這週"]


# ── 主線與玩法說明、軍令內容 ──


@pytest.mark.slow
def test_season21_howto_says_orders_come_every_day():
    c21 = real_content("season21")
    state = _state(c21)
    quest = "".join(howto.war_help(state, c21)["quest"])
    assert "投靠陣營之後每天有軍令" in quest and "每週一" not in quest
    join = "".join(howto.join_lines(c21, state.world))
    assert "**軍令**：每天發令" in join and "今日的軍令卡在江湖頁行動列底下" in join and "每週一" not in join


@pytest.mark.slow
def test_season21_order_text_slots_say_today():
    c21 = real_content("season21")
    s21 = _state(c21)
    raw = "{地點}，{本週}截斷它；{人物}{這週}連敗幾陣。"
    order = Order(id="o1", template="intercept", faction="guan", week=1, quota=10, text="")
    assert orders.fill(s21, c21, order, raw).endswith("，今日截斷它；今天連敗幾陣。")


@pytest.mark.slow
def test_season21_issued_orders_read_today():
    """開季那一刻與之後每天 00:00 真的發出去的軍令：寫了 {本週}{這週} 的那幾種換成「今日」「今天」，沒有一道寫「本週」「這週」。"""
    c21 = real_content("season21")
    season = _season(c21)
    world.settle_season_start(season, c21, random.Random(0))
    vehicle = world._season_vehicle(c21, season)
    for day in range(2, 15):
        season.time = calendar.day_start(day, c21, season) + 1
        orders.issue_day(vehicle, c21, day, random.Random(day))
    texts = [o.text for o in season.orders]
    assert any("今日" in t or "今天" in t for t in texts), texts
    assert not any("本週" in t or "這週" in t or "{" in t for t in texts)


# ── 入伍段：引薦人說的話（content/tutorial.json 的 {本週}／{每週}）──


@pytest.mark.slow
@pytest.mark.parametrize("profile,each,this", [("season21", "每天", "今日"), ("week7", "每天", "今日")])
def test_recruiters_follow_the_order_rhythm(profile, each, this):
    content = _content(profile)
    for faction, brief in (("guan", f"上頭{each}發幾道軍令"), ("huang", f"上頭{each}傳幾道令下來")):
        state = _state(content, faction)
        state.player.enlist_step = 0
        box = enlist.box(state, content)
        assert brief in box["text"] and box["line"] == f"看看「{this}軍令」", (profile, faction)
        assert "{" not in box["text"]
        assert guide.next_hint(state, content) == f"（{enlist.recruiter(state, content).name}）看看「{this}軍令」"
        assert all("{" not in line for line in enlist.told(state, content))
    state = _state(content, "haoqiang")
    state.player.enlist_step = 1
    hint = enlist.box(state, content)["text"]
    assert "{" not in hint
    assert f"你跟的那一邊{each}發的軍令寫在卡上" in hint  # 豪強分屬兩軍的季：依附那一邊的軍令


# ── 管理者：重發軍令的回話 ──


def _admin_game(profile):
    from tianxia.engine import Game
    from tianxia.sqlite_world import open_world

    content = _content(profile)
    content.config.admins = ["甲"]
    content.config.train_event_chance = 0.0
    store = open_world()
    store.seed_first_season(content)
    game = Game.new(content, "甲", rng=random.Random(0), world=store)
    game.client = None
    game.admin_open_season(MON)
    game.sync(MON + 3600)
    return game


@pytest.mark.slow
@pytest.mark.parametrize("profile,head", [("season21", "已照 00:00 的做法重發第 1 天的軍令"), ("week7", "已照 00:00 的做法重發第 1 天的軍令")])
def test_admin_reissue_reply_follows_the_order_rhythm(profile, head):
    msg = _admin_game(profile).admin_issue_orders()[0]
    assert msg.startswith(head), msg


@pytest.mark.slow
def test_admin_reissue_refusal_names_todays_orders():
    from tianxia.engine import Game

    game = _admin_game("season21")
    player = Game.new(game.content, "乙", rng=random.Random(1), world=game.world)
    player.sync(MON + 3600)
    assert player.admin_issue_orders() == ["（只有管理者能發今日軍令。）"]


# ── 網頁：/api/main 的 status.calendar.words 與畫出來的字 ──


@pytest.mark.slow
def test_season21_status_sends_only_the_order_words():
    cal = _admin_game("season21").status_data()["calendar"]
    assert cal["words"] == {"order_this": "今日", "order_that": "今天", "order_each": "每天", "order_every": "每天"}


@pytest.mark.slow
def test_season21_pages_say_todays_orders_and_keep_weeks(monkeypatch):
    out = fb501web._render(fb501web._game_fb501("season21"), monkeypatch)
    assert "📜 今日軍令（1）" in out["orders"]
    assert "每天、每週的事（軍令照 00:00、席次照週一的做法立刻再做一次；之後照常）" in out["sheet"] and "立刻發今日軍令" in out["sheet"]
    assert out["issue"].startswith("立刻發今日軍令：今天還沒達成的軍令照 00:00 的做法重挑") and "明天 00:00 照常發令" in out["issue"]
    # 其他「週」的字照舊（大事小標、季末結算卡、天下怎麼變、第 4 階席次）
    assert out["board"] == "本週江湖大事" and "<b>第 1 週・三十六方起義</b>" in out["result"]
    assert "<small>第 1 週週末</small>" in out["timeline"] and "<h4>本週大事</h4>" in out["overview"]
    assert "照上一週的貢獻" in out["rotate"] and "下週一照常再排" in out["rotate"]
