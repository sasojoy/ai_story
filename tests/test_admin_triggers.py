"""管理者觸發鈕（企劃者 2026-10-07：「這些事件都要加到管理員按鈕觸發」；brief 2026-10-07-管理者觸發鈕 第 1～3 組）。

每一顆鈕都叫自然那條路用的同一個函式：測試照「雙胞胎」比——兩份一模一樣的世界，一份讓自然的路走（週一的掛鉤、時刻表、
同步時發的召見、行動之後聽到的線索），一份按鈕，比按完之後的世界與角色。拒絕的每一種都有一個測試。

用真實內容（content/）、週末設定的開關（季長 2.5 天）；人數上限 250（第 4 階兩席，跟 tests/test_seats.py 一樣）。
現實時間由測試給（game.now），time_scale 是 1；管理者是「管」。"""
from __future__ import annotations

import copy
import random

import pytest

from conftest import real_content
from tianxia import calendar, orders, seats
from tianxia.engine import PAUSED_REFUSAL, Game
from tianxia.sqlite_world import open_world

NOW = 1000.0


@pytest.fixture
def real():
    """真實內容，開關關著（beta 那一季）；季自己開、遊歷打完不接戰後事件；「管」是管理者。"""
    c = real_content()
    c.config.auto_open_first_season = True
    c.config.train_event_chance = 0.0
    c.config.admins = ["管"]
    return c


@pytest.fixture
def on(real):
    real.config.season_one, real.config.season_days, real.config.server_max_players = True, 2.5, 250
    return real


def _game(content, name="管", world=None):
    """一個角色，同步過一次（之後的同步才會推賽季）；不叫模型。"""
    game = Game.new(content, name, rng=random.Random(0), world=world)
    game.client = None
    game.sync(NOW)
    return game


def _twins(content, tmp_path):
    """兩份一模一樣的世界（各自一個資料庫）與各自的管理者。"""
    return _game(content), _game(content, world=open_world(tmp_path / "twin.db"))


def _week_real(game, week, after=5.0):
    """第 week 週週一 00:00 之後 after 秒的現實時間（從 NOW 起算；time_scale 1）。"""
    return NOW + calendar.week_start(week, game.content, game.state.world) / game.content.config.time_scale + after


def _into_week(game, week, after=5.0):
    game.sync(_week_real(game, week, after))


def _faction_notes(season, since=0):
    return [r.text for r in season.rumors[since:] if r.layer == "faction"]


# ── 第 1 組：立刻發本週軍令 ─────────────────────────────────


def _week_orders(game, week):
    return [o.model_dump() for o in game.world.get_season().orders if o.week == week]


def test_issue_orders_redraws_this_week_exactly_like_the_monday_hook(on, tmp_path):
    """雙胞胎都自然走進第 2 週（週一的掛鉤發令）。B 這一週做了一道（達成、效果套上去）、另一道有進度，然後按「立刻發本週軍令」：
    這一週的軍令跟 A 週一發的一模一樣（沒有進度、沒有達成），陣營軍情照週一那樣再發一輪；達成過的效果留著（戰況不退回）；
    不動 hooked_week，下週一照常發令。"""
    a, b = _twins(on, tmp_path)
    for game in (a, b):
        _into_week(game, 2)
    monday = calendar.week_start(2, on, a.state.world)
    issued_on_monday = [r.text for r in a.world.get_season().rumors if r.time >= monday - 1 and r.text.startswith(orders.ISSUED)]
    assert issued_on_monday and _week_orders(a, 2) == _week_orders(b, 2)

    season = b.world.get_season()
    week2 = [o for o in season.orders if o.week == 2]
    done = next(o for o in week2 if o.template in ("siege", "defend", "intercept", "escort"))
    vehicle = b.state
    vehicle.world = season
    done.progress = {"甲": done.quota}
    orders._complete(vehicle, on, done)  # noqa: SLF001  達成：效果套在戰況上
    other = next(o for o in week2 if o is not done)
    other.progress = {"乙": 1}
    b.world.save_season(season)
    trends = dict(b.world.get_season().trends)
    hooked = b.world.get_season().hooked_week
    b.state.world = b.world.get_season()
    before = len(b.state.world.rumors)

    [msg] = b.admin_issue_orders()
    after = b.world.get_season()
    assert _week_orders(b, 2) == _week_orders(a, 2)  # 照週一的挑法重挑：進度、達成都清掉
    assert [r.text for r in after.rumors[before:]] == issued_on_monday  # 軍情照週一那樣再發一輪
    assert after.trends == trends  # 達成過的效果留著
    assert after.hooked_week == hooked
    assert "換掉" in msg and f"{len(week2)} 道" in msg
    _into_week(b, 3)
    week3 = [o for o in b.world.get_season().orders if o.week == 3]
    assert week3 and b.world.get_season().hooked_week == 3  # 下週一照常發令


def test_issue_orders_refusals(on):
    player = _game(on, "甲")
    assert player.admin_issue_orders() == ["（只有管理者能發本週軍令。）"]
    admin = _game(on)
    before = admin.world.get_season().orders
    assert admin.world.pause_clock(NOW + 1)
    assert admin.admin_issue_orders() == [PAUSED_REFUSAL]
    assert admin.world.get_season().orders == before


def test_issue_orders_refused_with_the_switch_off(real):
    admin = _game(real)
    assert admin.admin_issue_orders() == ["（這一季沒有軍令。）"]


# ── 第 1 組：立刻輪替第 4 階席次 ─────────────────────────────


LEDGER = {"guan": {"乙": {1: 50}, "丙": {1: 40}, "甲": {1: 7}}}


def test_rotate_seats_matches_the_monday_rotation_and_leaves_monday_to_run(on, tmp_path):
    """A 的帳在週一之前就有上一週的貢獻：自然走進第 2 週時輪替（乙、丙上任、發一則名單）。B 週一時帳是空的（沒有輪替），
    帳補成跟 A 一樣之後按鈕：在任的人、發的那一則名單都跟 A 週一一樣；hooked_week 不動，第 3 週週一照常再排一次。"""
    a, b = _twins(on, tmp_path)
    a.world.mutate_season(lambda s: s.seat_ledger.update(copy.deepcopy(LEDGER)))
    monday_notes_from = len(a.world.get_season().rumors)
    for game in (a, b):
        _into_week(game, 2)
    sa = a.world.get_season()
    roster_a = [t for t in _faction_notes(sa, monday_notes_from) if t.startswith("本週在任的")]
    assert sa.seats["guan"] == ["乙", "丙"] and roster_a == ["本週在任的校尉：乙、丙。"]
    assert b.world.get_season().seats == {}

    b.world.mutate_season(lambda s: s.seat_ledger.update(copy.deepcopy(LEDGER)))
    b.state.world = b.world.get_season()
    before = len(b.state.world.rumors)
    [msg] = b.admin_rotate_seats()
    sb = b.world.get_season()
    assert sb.seats == sa.seats
    assert _faction_notes(sb, before) == roster_a
    assert sb.hooked_week == 2 and "下週一照常" in msg and "乙、丙" in msg
    _into_week(b, 3)
    assert _faction_notes(b.world.get_season()).count("本週在任的校尉：乙、丙。") == 2  # 第 3 週週一照常排


def test_rotate_seats_refusals(on):
    player = _game(on, "甲")
    assert player.admin_rotate_seats() == ["（只有管理者能輪替第 4 階席次。）"]
    admin = _game(on)
    admin.world.mutate_season(lambda s: s.seat_ledger.update(copy.deepcopy(LEDGER)))
    assert admin.admin_rotate_seats() == ["（第 1 週沒有上一週的貢獻可排；空缺照常由有資格的人補上。）"]
    _into_week(admin, 2)
    admin.world.mutate_season(lambda s: s.seats.clear())
    admin.state.world = admin.world.get_season()
    assert admin.world.pause_clock(_week_real(admin, 2, 10))  # 暫停中：跟自然的路一樣，不排、不補
    assert admin.admin_rotate_seats() == [PAUSED_REFUSAL]
    assert admin.world.get_season().seats == {}


def test_rotate_seats_refused_with_the_switch_off(real):
    admin = _game(real)
    assert admin.admin_rotate_seats() == ["（這一季沒有第 4 階席次。）"]
    assert seats.SEAT_RANK == 4


# ── 第 3 組：三場大戲 ─────────────────────────────────────


def _battle(game):
    battle = game.world.get_battle()
    return None if battle is None or battle.phase == "ended" else battle


def test_start_showdown_opens_exactly_as_the_timetable_would(on, tmp_path):
    """雙胞胎同一刻：A 讓時刻表自然開長社（排定的時間就是此刻，季的事把它記進等著開的、推進之後開集結——world 的同一串函式），
    B 按「立刻開這一場」。兩邊開出來的那一場（哪一筆、起點、集結截止……整份）、集結號角、開過的記號一模一樣。"""
    from tianxia import world as world_mod

    a, b = _twins(on, tmp_path)

    def due_now(season):
        season.schedule["changshe_fire"] = season.time
        world_mod._note_due_showdowns(world_mod._season_vehicle(on, season), on)  # noqa: SLF001  季的事那一步
    a.world.mutate_season(due_now)
    natural = world_mod.start_pending_battle(a.world, on, NOW)
    pressed = b.admin_start_showdown("changshe_fire", NOW)
    assert natural == pressed == ["🛡️ 【全服戰報】長社火攻的集結號角已經吹響！"]
    assert b.world.get_battle().model_dump() == a.world.get_battle().model_dump()
    assert b.world.get_season().showdowns_opened == a.world.get_season().showdowns_opened == {"changshe_fire": "changshe_fire"}


def test_an_early_start_counts_as_happened_so_the_date_passes_quietly(on):
    """第 1 週就開了長社、取消掉（時間軸上沒有結果，只剩開過的記號）：排定的日子過了也不再開集結。"""
    admin = _game(on)
    admin.admin_start_showdown("changshe_fire", NOW)
    first = admin.world.get_battle().record_id
    admin.admin_cancel_battle()
    season = admin.world.get_season()
    assert "changshe_fire" not in season.timeline and "changshe_fire" in season.showdowns_opened
    cal_hour = calendar.cal_hour_seconds(on, season)
    past = NOW + (season.schedule["changshe_fire"] + 3 * cal_hour - season.time)
    admin.sync(past)
    after = admin.world.get_season()
    assert after.time > season.schedule["changshe_fire"] and "changshe_fire" not in after.showdowns_waiting
    assert admin.world.get_battle() is None  # 沒有第二場
    assert [battle.record_id for _, battle in admin.world.ended_battles()] == [first]
    assert admin.admin_start_showdown("changshe_fire", past) == ["（長社火攻已經開打過了。）"]


def test_an_active_battle_blocks_the_buttons(on):
    admin = _game(on)
    admin.admin_start_showdown("changshe_fire", NOW)
    battle = admin.world.get_battle().model_dump()
    assert admin.admin_start_showdown("guangzong", NOW) == ["（已經有一場戰鬥在進行。）"]
    assert admin.world.get_battle().model_dump() == battle and "guangzong" not in admin.world.get_season().showdowns_opened
    notes = {event.id: why for event, why in admin.admin_showdowns()}
    assert notes["guangzong"] == "（已經有一場戰鬥在進行。）" and notes["changshe_fire"] == "（長社火攻已經開打過了。）"


@pytest.mark.parametrize(("week3", "battle_id"), [("成", "wancheng_jia"), ("不成", "wancheng_yi")])
def test_wancheng_takes_the_version_the_rule_picks(on, week3, battle_id):
    """宛城看第 3 週（張曼成攻殺南陽太守）的結果：還沒結算時按不下去、說要等它；結算之後開的是那一版。"""
    admin = _game(on)
    assert admin.admin_start_showdown("wancheng", NOW) == ["（宛城之戰要等張曼成攻殺南陽太守結算了才知道是哪一版。）"]
    assert admin.world.get_battle() is None
    admin.admin_resolve_event("zhangmancheng_wan", week3)
    admin.admin_start_showdown("wancheng", NOW)
    assert _battle(admin).battle_id == battle_id
    assert admin.world.get_season().showdowns_opened == {"wancheng": battle_id}


def test_start_showdown_refusals(on):
    player = _game(on, "甲")
    assert player.admin_start_showdown("changshe_fire", NOW) == ["（只有管理者能開這一場決戰。）"]
    admin = _game(on)
    assert admin.admin_start_showdown("luzhi_siege", NOW) == ["（時刻表上沒有這一場決戰。）"]
    assert admin.admin_start_showdown("nope", NOW) == ["（時刻表上沒有這一場決戰。）"]
    admin.admin_resolve_event("changshe_fire", "guan:大勝")
    assert admin.admin_start_showdown("changshe_fire", NOW) == ["（長社火攻已經結算了。）"]
    assert admin.world.pause_clock(NOW + 1)
    assert admin.admin_start_showdown("guangzong", NOW + 2) == [PAUSED_REFUSAL]
    assert admin.world.get_battle() is None


def test_start_showdown_refused_with_the_switch_off(real):
    admin = _game(real)
    assert admin.admin_start_showdown("changshe_fire", NOW) == ["（這一季沒有時刻表。）"]
    assert admin.admin_showdowns() == [] and admin.world.get_battle() is None
