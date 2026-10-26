"""FB-502（PM 2026-10-20，推翻 FB-501 那一批「21 天季不動」）：21 天季的軍令其實也是每天一道，「本週軍令」「每週一發令」
「投靠陣營之後每週一有軍令」「本週截斷它」這些字在 21 天季也照「今日／每天」寫。換字照「這一季的軍令是不是每天發」
（calendar.orders_daily＝照現實天的季，同 orders.daily），不是照「有沒有段」（week7_on）。21 天季其他「週」的字（第 N 週、
本週大事、時刻表、第 4 階席次）不動；週末、14 天一個字都不變。字待 joy 潤。"""
from __future__ import annotations

import random

import pytest
import test_fb501_week7_words_web as fb501web
from conftest import real_content

from tianxia import calendar, enlist, guide, howto, orders, world
from tianxia.state import Order, new_game_state
from tianxia.world_state import fresh_season, stamp_season

pytestmark = pytest.mark.slow  # 每一條都載真實內容、開一季

MON = 1792339200  # 2026-10-19 週一 00:00（台灣）
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


@pytest.mark.parametrize("profile,daily", [("week7", True), ("season21", True), (None, False)])
def test_orders_daily_is_the_one_switch(profile, daily):
    content = _content(profile)
    state = _state(content)
    assert calendar.orders_daily(state.world, content) is daily
    assert orders.daily(state, content) is daily


def test_season21_order_words_say_today_but_weeks_stay():
    c21 = real_content("season21")
    s21 = _season(c21)
    assert [calendar.week_word(k, c21, s21) for k in ORDER_KEYS] == ["今日", "今天", "每天", "每天"]
    assert [calendar.week_word(k, c21, s21) for k in SEGMENT_KEYS] == ["本週", "這一週", "每週", "這週"]
    assert calendar.week_label(2, c21, s21) == "第 2 週"
    assert calendar.week_words(c21, s21) == {"order_this": "今日", "order_that": "今天", "order_each": "每天", "order_every": "每天"}


@pytest.mark.parametrize("profile", [None])
def test_weekend_and_fourteen_day_keep_every_week_word(profile):
    content = _content(profile)
    season = _season(content)
    assert calendar.week_words(content, season) is None
    assert [calendar.week_word(k, content, season) for k in ORDER_KEYS] == ["本週", "這週", "每週一", "每週"]
    assert [calendar.week_word(k, content, season) for k in SEGMENT_KEYS] == ["本週", "這一週", "每週", "這週"]


# ── 主線與玩法說明、軍令內容 ──


def test_season21_howto_says_orders_come_every_day():
    c21 = real_content("season21")
    state = _state(c21)
    quest = "".join(howto.war_help(state, c21)["quest"])
    assert "投靠陣營之後每天有軍令" in quest and "每週一" not in quest
    join = "".join(howto.join_lines(c21, state.world))
    assert "**軍令**：每天發令" in join and "今日的軍令卡在江湖頁行動列底下" in join and "每週一" not in join


def test_season21_order_text_slots_say_today():
    c21 = real_content("season21")
    s21 = _state(c21)
    raw = "{地點}，{本週}截斷它；{人物}{這週}連敗幾陣。"
    order = Order(id="o1", template="intercept", faction="guan", week=1, quota=10, text="")
    assert orders.fill(s21, c21, order, raw).endswith("，今日截斷它；今天連敗幾陣。")


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


@pytest.mark.parametrize("profile,head", [("season21", "已照 00:00 的做法重發第 1 天的軍令"), ("week7", "已照 00:00 的做法重發第 1 天的軍令")])
def test_admin_reissue_reply_follows_the_order_rhythm(profile, head):
    msg = _admin_game(profile).admin_issue_orders()[0]
    assert msg.startswith(head), msg


def test_admin_reissue_refusal_names_todays_orders():
    from tianxia.engine import Game

    game = _admin_game("season21")
    player = Game.new(game.content, "乙", rng=random.Random(1), world=game.world)
    player.sync(MON + 3600)
    assert player.admin_issue_orders() == ["（只有管理者能發今日軍令。）"]


# ── 網頁：/api/main 的 status.calendar.words 與畫出來的字 ──


def test_season21_status_sends_only_the_order_words():
    cal = _admin_game("season21").status_data()["calendar"]
    assert cal["words"] == {"order_this": "今日", "order_that": "今天", "order_each": "每天", "order_every": "每天"}


def test_season21_pages_say_todays_orders_and_keep_weeks(monkeypatch):
    out = fb501web._render(fb501web._game("season21"), monkeypatch)
    assert "📜 今日軍令（1）" in out["orders"]
    assert "每天、每週的事（軍令照 00:00、席次照週一的做法立刻再做一次；之後照常）" in out["sheet"] and "立刻發今日軍令" in out["sheet"]
    assert out["issue"].startswith("立刻發今日軍令：今天還沒達成的軍令照 00:00 的做法重挑") and "明天 00:00 照常發令" in out["issue"]
    # 其他「週」的字照舊（大事小標、季末結算卡、天下怎麼變、第 4 階席次）
    assert out["board"] == "本週江湖大事" and "<b>第 1 週・三十六方起義</b>" in out["result"]
    assert "<small>第 1 週週末</small>" in out["timeline"] and "<h4>本週大事</h4>" in out["overview"]
    assert "照上一週的貢獻" in out["rotate"] and "下週一照常再排" in out["rotate"]
