"""FB-503（7 天濃縮季第二輪，PM 2026-10-20）：FB-501 清單外還寫「週」的地方，7 天季照段寫（calendar.week_word／week_label）：
第 3、4 階行動「這週已經做滿 N 次」、補上第 4 階席次「到下週一為止」、管理者輪替席次的回話、管理者「這一季立刻蓋天命之季的章」
問句裡天命之爭的時刻。21 天季、週末、14 天一個字都不變。字待 joy 潤。"""
from __future__ import annotations

import pytest
import test_fb501_week7_words as fb501
import test_fb501_week7_words_web as fb501web
import webharness
from conftest import real_content

import server
from tianxia import calendar, seats, timetable

pytestmark = pytest.mark.slow  # 每一條都載真實內容、開一季

HOUR, DAY = 3600, 86400


# ── 第 3、4 階行動：做滿了 ──


def _rank_option(profile):
    game = fb501._game(profile)
    c, p = game.content, game.state.player
    p.faction, p.rank, p.location, p.stamina = "huang", 3, "runan", 100
    week = calendar.point(game.state.world.time, c, game.state.world).week
    weekly = next(a for a in c.orders.rank_actions if a.id == "incite").weekly
    p.rank_action_weeks = {f"{week}:incite": weekly}
    return next(o for o in game.options(odds=False) if o.id == "act:rank:incite")


@pytest.mark.parametrize("profile,word", [("week7", "這一段"), ("season21", "這週"), ("weekend", "這週")])
def test_the_rank_action_cap_names_the_segment_on_week7(profile, word):
    option = _rank_option(profile)
    assert not option.enabled and option.label == f"在一地煽動起事（{word}已經做滿 3 次）"


# ── 補上第 4 階席次：到什麼時候為止 ──


def _seat_line(profile, at):
    content = fb501._content(profile)
    state = fb501._state(content)
    state.world.time = at
    p = state.player
    p.faction, p.qualified = "guan", True
    return seats.report(state, content)


def test_a_filled_seat_lasts_until_the_next_segment_on_week7():
    assert _seat_line("week7", DAY + HOUR) == ["你補上了校尉的缺，到第 3 天 00:00 為止。"]  # 第 1 段
    assert _seat_line("week7", 3 * DAY + HOUR) == ["你補上了校尉的缺，到第 5 天 00:00 為止。"]  # 第 2 段
    assert _seat_line("week7", 5 * DAY + HOUR) == ["你補上了校尉的缺，到季末為止。"]  # 最後一段沒有下一段


@pytest.mark.parametrize("profile", ["season21", "weekend"])
def test_a_filled_seat_lasts_until_next_monday_elsewhere(profile):
    assert _seat_line(profile, DAY + HOUR) == ["你補上了校尉的缺，到下週一為止。"]


# ── 管理者：輪替第 4 階席次的回話 ──


def _rotate(profile, at):
    game = fb501._game(profile)
    game.sync(fb501.MON + at / game.content.config.time_scale)
    return game.admin_rotate_seats()[0]


def test_admin_rotation_reply_names_segments_on_week7():
    assert _rotate("week7", DAY + HOUR) == "（第 1 段沒有上一段的貢獻可排；空缺照常由有資格的人補上。）"


def test_admin_rotation_reply_in_the_second_segment():
    msg = _rotate("week7", 3 * DAY + HOUR)
    assert msg.startswith("已照第 1 段（第 1～2 天）的貢獻輪替第 4 階席次（下一段第一天 00:00 照常再排）——"), msg


def test_admin_rotation_reply_in_the_last_segment():
    msg = _rotate("week7", 5 * DAY + HOUR)
    assert msg.startswith("已照第 2 段（第 3～4 天）的貢獻輪替第 4 階席次（這是最後一段，季末之前不再排）——"), msg


@pytest.mark.parametrize("profile", ["season21", "weekend"])
def test_admin_rotation_reply_unchanged_elsewhere(profile):
    assert _rotate(profile, HOUR) == "（第 1 週沒有上一週的貢獻可排；空缺照常由有資格的人補上。）"


# ── 管理者：這一季立刻蓋天命之季的章 ──


def test_mandate_note_reads_the_week7_timetable():
    c7 = real_content("week7")
    assert timetable.mandate_note(c7, fb501._season(c7)) == "第 7 天 22:00"
    for profile in ("season21", "weekend", None):
        content = fb501._content(profile)
        assert timetable.mandate_note(content, fb501._season(content)) is None


@pytest.mark.parametrize("profile,when", [("week7", "第 7 天 22:00"), ("weekend", "第 12 週週一 20:00")])
def test_the_admin_mandate_ask_names_the_week7_time(profile, when, monkeypatch):
    game = fb501._game(profile)
    monkeypatch.setattr(server, "CONTENT", game.content)
    admin = server.admin_choices(game)
    assert admin["mandate_at"] == (when if profile == "week7" else None)
    payload = {"m": {**server.main_view(game), "admin": True}, "menxia": None, "stored": {}, "responses": {},
               "script": 'return H.adminAsk("seal_mandate", {when: "now"})[0];', "S": {"admin": admin}}
    asked = webharness.run(fb501web.DRIVER, payload)
    assert f"天命之爭排在{when}（" in asked
