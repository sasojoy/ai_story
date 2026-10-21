"""領地爭奪：每天的鐘與攻城時段（tianxia/conquest_day.py；設計 4.3，裁決 6）。投票、主將定奪、合成時程表照翻地與爭搶拿掉了（PM 2026-10-20），
那幾條測試跟著拿掉；戰書挑時段（next_slot）在這裡，戰書本身在 test_conquest_letter.py。"""
from __future__ import annotations

import calendar as pycal
from datetime import datetime

import pytest

from conquest_kit import conquest_game, plain_game
from tianxia import conquest, conquest_day

pytestmark = pytest.mark.slow  # 建 Game、載正式內容


def _utc(y, mo, d, h, mi=0, s=0) -> float:
    return float(pycal.timegm(datetime(y, mo, d, h, mi, s).timetuple()))


def test_day_key_turns_at_22_taiwan():
    cfg = conquest_game("season21").content.config
    before, after = _utc(2026, 10, 20, 13, 59, 59), _utc(2026, 10, 20, 14, 0, 0)  # 台灣 21:59:59、22:00:00
    assert conquest_day.day_key(after, cfg) == conquest_day.day_key(before, cfg) + 1
    key = conquest_day.day_key(after, cfg)
    assert conquest_day.key_start(key, cfg) == after
    # 那一天的 12:00 是隔天中午（台灣 10/21 12:00＝UTC 04:00），21:00 也在同一天
    assert conquest_day.slot_real(key, 12 * 60, cfg) == _utc(2026, 10, 21, 4)
    assert conquest_day.slot_real(key, 21 * 60, cfg) == _utc(2026, 10, 21, 13)
    assert conquest_day.slot_text(20 * 60 + 30) == "20:30"


def test_next_slot_is_the_nearest_one_or_tomorrows_first():
    """戰書挑的時段（翻地與爭搶，輿圖簡化設計 4.4「時段挑最近的一個」）：今天還開得了集結的第一個，今天沒有了就下一天的第一個。"""
    game = conquest_game("season21")
    w, c = game.state.world, game.content
    morning = _utc(2026, 10, 20, 2)  # 台灣 10/20 10:00
    key = conquest_day.day_key(morning, c.config)
    assert conquest_day.next_slot(w, c, morning) == (key, 12 * 60)
    assert conquest_day.next_slot(w, c, _utc(2026, 10, 20, 11)) == (key, 19 * 60 + 30)  # 台灣 19:00：19:30 才來得及集結
    assert conquest_day.next_slot(w, c, _utc(2026, 10, 20, 12, 40)) == (key + 1, 12 * 60)  # 台灣 20:40：今天沒有了
    assert conquest_day.next_slot(w, c, _utc(2026, 10, 20, 15)) == (key + 1, 12 * 60)  # 台灣 23:00：已經換天，明天中午


def test_slots_skip_showdown_window():
    game = conquest_game("season21")
    w, c = game.state.world, game.content
    real_now = _utc(2026, 10, 20, 2)  # 台灣 10/20 10:00
    key = conquest_day.day_key(real_now, c.config) + 1  # 明天的時段：10/21 12:00～21:00
    event = next(e for e in c.timetable if e.kind == "showdown")
    w.schedule[event.id] = w.time + (conquest_day.slot_real(key, 20 * 60, c.config) - real_now)  # 決戰排在那一天 20:00
    got = conquest_day.slots(w, c, key, real_now)
    assert 19 * 60 in got and 21 * 60 in got
    assert not {19 * 60 + 30, 20 * 60, 20 * 60 + 30} & set(got)  # 19:30～20:45 拿掉（裁決 6）
    today = conquest_day.day_key(real_now, c.config)  # 今天（10/20 的 12:00～21:00）：10:00 看，12:00 之前的都還開得了集結
    assert conquest_day.slots(w, c, today, _utc(2026, 10, 20, 12))[0] == 20 * 60 + 30  # 台灣 20:00 看：20:30 以前的都來不及


def test_switch_off_today_is_empty():
    game = plain_game("season21")
    w, c = game.state.world, game.content
    assert not conquest.on(c, w)
    assert conquest_day.today(w, c, "huang", "attack") == [] and conquest_day.today(w, c, "guan", "defend") == []
