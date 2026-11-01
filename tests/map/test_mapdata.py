"""輿圖升級的資料（設計第九節）：底圖的清單與疊層。正式內容、7 天季（week7）。"""
from __future__ import annotations

import json
import random

from conftest import classic_rules, real_content
from tianxia import atlas, calendar, mapdata, mapview, orders, territory
from tianxia.engine import Game
from tianxia.sqlite_world import open_world
import test_week7_season as fb501
from conftest import real_content
from tianxia import calendar, mapdata, timetable
import pytest
from tianxia.state import Order, TimelineResult
import datetime
from tianxia.world_state import fresh_season, stamp_season


def _game(faction="guan", at="yingchuan", classic=False, profile="week7"):
    c = real_content(profile)  # 地盤拔河的舊規則（領地爭奪 PM 2026-10-22 起正式內容打開；翻地的輿圖資料在 tests/test_world_map.py）
    c.config.auto_open_first_season = True
    if classic:
        classic_rules(c)
    game = Game.new(c, "沈浪", rng=random.Random(0), world=open_world())
    game.client = None
    p = game.state.player
    p.faction, p.location = faction, at
    return game


def test_the_base_lists_open_places_roads_and_regions():
    game = _game(profile=None)
    b = game.map_base()
    ids = [p["id"] for p in b["places"]]
    assert ids == mapview.open_places(game.state, game.content) and "jade_cave" not in ids
    assert all(p["glyph"] in mapview.GLYPHS.values() for p in b["places"])
    assert all({a, z} <= set(ids) for a, z in b["edges"])
    assert [r["id"] for r in b["regions"]] == [r.id for r in game.content.map.regions]
    assert b["key"] == mapdata.base_key(game.state, game.content) and b["svg"].startswith("<svg")


def test_the_state_suggests_where_to_sortie():
    st = _game().map_state()
    assert 1 <= len(st["suggest"]) <= mapdata.SUGGEST_MAX + 1  # 打得過的最多三處，再加一處必敗的
    for g in st["suggest"]:
        assert st["places"][g["id"]]["sortie"] == g["sortie"] and g["sortie"] in ("attack", "hold", "stir")
    loses = [g["lose"] for g in st["suggest"]]
    assert loses == sorted(loses)  # 必敗的排在最後（企劃者 10/15 對比 4 選乙）
    for lose in (False, True):
        scores = [g["score"] for g in st["suggest"] if g["lose"] is lose]
        assert scores == sorted(scores, reverse=True)
    assert all(g["lose"] == (g["sortie"] == "attack" and (st["places"][g["id"]]["odds"] or {}).get("word") == mapdata.LOSE_WORD)
               for g in st["suggest"])  # 只有攻才看勝算（守、攪局不打，FB-259）


@pytest.mark.smoke
def test_a_place_you_can_win_comes_before_one_with_a_big_order_you_would_lose():
    """軍令 +100 的必敗那一處，排在什麼都沒有、打得過的那一處後面。"""
    from tianxia import mapdata as md

    rows = [{"id": "a", "lose": True, "score": 100}, {"id": "b", "lose": False, "score": -3}]
    assert [g["id"] for g in md.rank_suggestions(rows)] == ["b", "a"]


def test_a_losing_place_still_shows_when_three_can_be_won():
    """「必敗的照樣列」：打得過的有三處時，必敗的分數最高那一處淡淡地排第四，不會整個不見。"""
    from tianxia import mapdata as md

    win = [{"id": f"w{i}", "lose": False, "score": -i} for i in range(5)]
    lose = [{"id": "l0", "lose": True, "score": 90}, {"id": "l1", "lose": True, "score": 50}]
    assert [g["id"] for g in md.rank_suggestions(win + lose)] == ["w0", "w1", "w2", "l0"]
    assert [g["id"] for g in md.rank_suggestions(win[:1] + lose)] == ["w0", "l0", "l1"]
    assert [g["id"] for g in md.rank_suggestions(lose)] == ["l0", "l1"]


def test_weeks_before_the_first_snapshot_are_empty():
    game = _game()
    w, c = game.state.world, game.content
    w.time = calendar.week_start(3, c, w) + 60
    territory.update(w, c)
    weeks = game.map_state()["weeks"]
    assert [x["control"] is None for x in weeks] == [True, True, False]


def test_the_state_says_where_you_are_heading():
    game = _game()
    game.travel("yingchuan_wilds", "walk")
    st = game.map_state()
    assert st["journey"]["to"] == "yingchuan_wilds" and st["journey"]["minutes"] >= 1
    assert isinstance(st["journey"]["x"], (int, float))


def test_the_fourteen_day_season_has_one_rope():
    st = _game(profile=None).map_state()
    assert len(st["ropes"]) == 1 and st["season_one"] is False


def test_the_state_is_small_and_counts_each_squad_once():
    game = _game()
    calls = []
    real = game.odds
    game.odds = lambda sid, at=None: calls.append(sid) or real(sid, at=at)  # 每一處照那一處的地利問（武學隨地理環境）
    game.content.config.terrain_arts.enabled = False  # 同一支隊伍只算一次：地利關著時（開著時同一路對手、同一種地利一次，見 test_terrain_arts）
    st = game.map_state()
    assert len(json.dumps(st, ensure_ascii=False).encode()) < 40_000
    assert calls and len(calls) == len(set(calls))


# ── 意境提示（設計第六節）──
def test_the_base_lists_what_each_place_gives_with_the_strongest_first():
    b = _game().map_base()
    places = {p["id"]: p for p in b["places"]}
    assert places["changshe"]["insights"] == ["huo", "feng"] and places["changshe"]["strong"] == "huo"
    assert places["baima_temple"]["insights"] == ["shui", "shan"] and places["baima_temple"]["terrain"] == "寺院"
    assert places["wan_city"]["terrain"] == "城鎮"  # 馬市、醫館是設施，不算地形
    assert b["insight_kinds"]["shui"] == {"name": "水", "attribute": "柔"} and "haoran" not in b["insight_kinds"]
    assert b["insight_layer"] is True


def test_the_base_has_no_strongest_with_the_switch_off():
    game = _game()
    game.content.config.insight_strong.enabled = False
    b = game.map_base()
    assert b["insight_layer"] is False and all(p["strong"] is None for p in b["places"])
    assert {p["id"]: p for p in b["places"]}["changshe"]["insights"] == ["huo", "feng"]  # 「此地能悟」照樣有


def test_the_prologue_hut_lists_nothing_to_sense():  # Review Focus 4
    c = real_content("week7")
    assert mapdata.insight_pool(c.locations["mentor_hut"], c) == []
    assert mapdata.insight_pool(c.locations["changshe"], c) == ["huo", "feng"]


# ── 原 test_fb504_map_events_not_early.py（整檔搬進來） ──
# FB-504（7 天濃縮季第二輪，PM 2026-10-20）：輿圖「這一段大事」「天下怎麼變」把還沒發生的大事提早列出（第 1 天就列出長社火攻）。
# mapdata._titles 用 calendar.event_time：時刻表決戰只寫了星期與鐘點（day 是 0），被當成那一週（段）第一天就到了；季末也一樣。
# 修成照這一件真正的時刻（timetable.when_in：決戰照 WorldState.schedule，季末照排定的季末，其餘照季曆）判斷到了沒。21 天季同一個錯
# （決戰從那一週週一、季末從第 3 週週一就列出來），一起修。
# 週末（PM 2026-10-20 改修）同一個錯：FB-504 當時 PM 定週末一字不變所以沒動，週末的決戰那一週週一 00:00 就列出那一場，季末在最後一週週一就列出；
# 現在週末也照 timetable.when_in 判斷到了沒（決戰照排定的時刻、季末照排定的季末，其餘照季曆，跟 21 天季、7 天季同一個寫法）。
# 週末除了決戰與季末，其他大事列的時刻一個字都不變。

HOUR, DAY = 3600, 86400


def _titles(content, at):
    state = fb501._state(content)
    state.world.time = at
    now_week = calendar.point(at, content, state.world).week
    return mapdata._titles(state, content, now_week, now_week), state


@pytest.mark.slow
def test_week7_day_one_does_not_list_the_changshe_battle():
    """修前重現：00:00 開的 7 天季第 1 天 13:00，「這一段大事」已經列出長社火攻（第 2 天 20:00 才開集結）。"""
    c7 = real_content("week7")
    titles, state = _titles(c7, 13 * HOUR)
    assert "三十六方起義" in titles and "朝廷出兵" in titles
    assert "長社火攻" not in titles
    titles, _ = _titles(c7, DAY + 20 * HOUR - 60)  # 第 2 天 19:59：還沒
    assert "長社火攻" not in titles
    titles, _ = _titles(c7, DAY + 20 * HOUR)  # 第 2 天 20:00：照排定的時刻到了
    assert "長社火攻" in titles


@pytest.mark.slow
def test_week7_follows_the_schedule_the_admin_moved():
    """管理者把長社往後排到第 2 天 23:00：照排的時刻，20:00 還不列。"""
    c7 = real_content("week7")
    state = fb501._state(c7)
    state.world.schedule["changshe_fire"] = DAY + 23 * HOUR
    state.world.time = DAY + 21 * HOUR
    assert "長社火攻" not in mapdata._titles(state, c7, 1, 1)
    state.world.time = DAY + 23 * HOUR
    assert "長社火攻" in mapdata._titles(state, c7, 1, 1)


@pytest.mark.slow
def test_week7_last_segment_lists_the_finale_only_after_the_season_end():
    c7 = real_content("week7")
    titles, _ = _titles(c7, 4 * DAY + HOUR)  # 第 5 天 01:00：第 3 段
    assert "廣宗決戰" not in titles and "下曲陽・季末" not in titles


@pytest.mark.slow
def test_season21_lists_the_saturday_battle_only_on_saturday_night():
    """21 天季同一個錯：週一開的季第 1 週週四 13:00，修前已經列出長社火攻（週六 20:00）。"""
    c21 = real_content("season21")
    titles, _ = _titles(c21, 3 * DAY + 13 * HOUR)
    assert "波才大敗朱儁" in titles and "長社火攻" not in titles
    titles, _ = _titles(c21, 5 * DAY + 20 * HOUR)
    assert "長社火攻" in titles
    titles, _ = _titles(c21, 14 * DAY + 13 * HOUR)  # 第 3 週週一 13:00
    assert "盧植下獄" in titles and "廣宗決戰" not in titles and "下曲陽・季末" not in titles


def _week7_state():
    cw = real_content("week7")
    return cw, fb501._state(cw)


@pytest.mark.slow
def test_week7_by_week_start_does_not_list_the_changshe_battle_on_its_week_monday():
    """修前重現（當時寫成週末）：第 6 週週一 00:00 起「這一段大事」就列出長社火攻（週四 20:00 才開集結）。"""
    cw, state = _week7_state()
    changshe = next(e for e in cw.timetable if e.id == "changshe_fire")
    battle = timetable.when_in(state.world, cw, changshe)
    monday = calendar.week_start(changshe.week, cw, state.world)
    assert monday < battle
    # 改之前的寫法（calendar.event_time）：決戰的 day 是 0，那一週一開始就到了
    assert calendar.event_time(changshe, cw, state.world) <= monday + 1
    for at in (monday + 60, (monday + battle) / 2, battle - 60):
        state.world.time = at
        week = calendar.point(at, cw, state.world).week
        assert week == changshe.week
        assert "長社火攻" not in mapdata._titles(state, cw, week, week), at
    state.world.time = battle
    assert "長社火攻" in mapdata._titles(state, cw, changshe.week, changshe.week)


@pytest.mark.slow
def test_week7_by_week_start_follows_the_schedule_the_admin_moved():
    """管理者把長社往後排：照排的時刻，預設的時刻到了也不列；排的時刻到了才列。"""
    cw, state = _week7_state()
    changshe = next(e for e in cw.timetable if e.id == "changshe_fire")
    default = timetable.when_in(state.world, cw, changshe)
    later = default + 7200  # 往後排兩個現實小時（仍在第 6 週裡）
    state.world.schedule["changshe_fire"] = later
    for at, listed in ((default, False), (later - 60, False), (later, True)):
        state.world.time = at
        week = calendar.point(at, cw, state.world).week
        assert week == changshe.week
        assert ("長社火攻" in mapdata._titles(state, cw, week, week)) is listed, at


@pytest.mark.slow
def test_week7_by_week_start_lists_the_finale_only_after_the_season_end():
    """修前重現（當時寫成週末）：最後一週週一 00:00 起就列出「下曲陽・季末」；現在要等到排定的季末。"""
    cw, state = _week7_state()
    finale = next(e for e in cw.timetable if e.kind == "finale")
    end = timetable.when_in(state.world, cw, finale)
    monday = calendar.week_start(finale.week, cw, state.world)
    assert monday < end
    assert calendar.event_time(finale, cw, state.world) <= monday + 1  # 改之前的寫法：那一週一開始就到了
    for at in (monday + 60, (monday + end) / 2, end - 60):
        state.world.time = at
        week = calendar.point(at, cw, state.world).week
        assert week == finale.week
        assert "下曲陽・季末" not in mapdata._titles(state, cw, week, week), at
    state.world.time = end
    assert "下曲陽・季末" in mapdata._titles(state, cw, finale.week, finale.week)
    # 管理者把季末往後排：排的時刻到了才列
    state.world.schedule["finale"] = end + 3600
    state.world.time = end + 60
    assert "下曲陽・季末" not in mapdata._titles(state, cw, finale.week, finale.week)
    state.world.time = end + 3600
    assert "下曲陽・季末" in mapdata._titles(state, cw, finale.week, finale.week)


@pytest.mark.slow
def test_week7_by_week_start_past_weeks_list_the_battle_once_it_has_happened():
    """「天下怎麼變」逐週列大事：以前的週列的是已經打過的決戰（過了排定的時刻），管理者往後排到還沒到的不列。"""
    cw, state = _week7_state()
    guangzong = next(e for e in cw.timetable if e.id == "guangzong")
    battle = timetable.when_in(state.world, cw, guangzong)
    monday = calendar.week_start(guangzong.week + 1, cw, state.world)
    assert battle < monday
    state.world.time = monday + 60
    assert "廣宗決戰" in mapdata._titles(state, cw, guangzong.week, guangzong.week + 1)
    state.world.schedule["guangzong"] = monday + 3600  # 管理者往後排到下一週
    assert "廣宗決戰" not in mapdata._titles(state, cw, guangzong.week, guangzong.week + 1)


@pytest.mark.slow
def test_week7_by_week_start_changes_only_the_showdowns_and_the_finale():
    """7 天季除了決戰與季末，每一刻列出來的大事跟改之前的寫法（以前的週全列、這一週照 calendar.event_time）一模一樣；
    決戰與季末照 timetable.when_in。整季從頭到尾每 20 分鐘看一次（現實 20 分鐘 ≈ 11 季曆小時，每一週都跨得到）。"""
    cw, state = _week7_state()
    special = {e.title for e in cw.timetable if e.kind in ("showdown", "finale")}
    assert special == {"長社火攻", "宛城之戰", "廣宗決戰", "下曲陽・季末"}
    end = calendar.nominal_end(cw, state.world)
    at = 0.0
    seen_special = 0
    while at <= end:
        state.world.time = at
        now_week = calendar.point(at, cw, state.world).week
        for week in range(1, now_week + 1):
            new = mapdata._titles(state, cw, week, now_week)
            old = [e.title for e in timetable.events(state.world, cw)
                   if e.week == week and (week < now_week or calendar.event_time(e, cw, state.world) <= at)]
            assert [t for t in new if t not in special] == [t for t in old if t not in special], (at, week)
            due = [e.title for e in timetable.events(state.world, cw)
                   if e.week == week and e.title in special and timetable.when_in(state.world, cw, e) <= at]
            assert [t for t in new if t in special] == due, (at, week)
            seen_special += len(due)
        at += 1200
    assert seen_special > 0


@pytest.mark.slow
def test_the_fourteen_day_season_has_no_timetable_in_the_map():
    """14 天的預設季沒有第一季規則，輿圖沒有這一段大事（跟以前一樣）。"""
    c14 = real_content()
    state = fb501._state(c14)
    state.world.time = 6 * DAY
    assert mapdata._titles(state, c14, 6, 6) == []


# ── 原 test_fb561_562_map_events_actual_time.py（整檔搬進來） ──
# FB-561／FB-562（develop 小單驗收 QA 回報，PM 2026-10-20）：輿圖「這一段大事」「天下怎麼變」列決戰與季末的時刻。
#
# FB-561：管理者「立刻開戰」提早開的時刻表決戰，修前要等到原本排定的時刻才列（開打了、收場了都不列）；現在這一場一開（WorldState.showdowns_opened）
# 或收場（timeline）就列，列在真的開了的那一週（段）。三種照週算的季（週末、21 天、7 天）都一樣。
# FB-562：決戰被「避開半夜」或管理者挪到另一週（段）時，修前照時刻表原本寫的那一週算；現在判斷到了沒、歸到哪一週都照實際排定的時刻
# （WorldState.schedule）。
# 不變：其他大事（非決戰、非季末）列的時刻與舊寫法逐刻一樣；14 天的季沒有這一段清單。

PROFILES = ("season21", "week7")


def _setup(profile):
    content = real_content(profile)
    return content, fb501._state(content)


def _event(content, event_id):
    return next(e for e in content.timetable if e.id == event_id)


def _in_week(content, state, week, cal_hours):
    """第 week 週（段）開始之後 cal_hours 個季曆小時的世界秒。"""
    return calendar.week_start(week, content, state.world) + cal_hours * HOUR / calendar.cal_scale(content, state.world)


def _week_of(content, state, at):
    return calendar.point(at, content, state.world).week


def _titles_fb561(content, state, at, week, now_week=None):
    state.world.time = at
    return mapdata._titles(state, content, week, now_week if now_week is not None else _week_of(content, state, at))


# ── FB-561：提早開的決戰，一開就列 ───────────────────────


@pytest.mark.slow
@pytest.mark.parametrize("profile", PROFILES)
def test_an_early_started_showdown_is_listed_from_the_moment_it_opens(profile):
    """修前重現：還沒到排定的時刻，開了集結也不列（只看 timetable.when_in）。"""
    content, state = _setup(profile)
    w = state.world
    changshe = _event(content, "changshe_fire")
    default = timetable.when_in(w, content, changshe)
    early = _in_week(content, state, changshe.week, 6)
    assert early + HOUR < default and _week_of(content, state, early) == changshe.week
    assert "長社火攻" not in _titles_fb561(content, state, early, changshe.week)  # 還沒開
    w.showdowns_opened["changshe_fire"] = "changshe_fire"  # 管理者「立刻開戰」：world._claim_showdown 記的就是這個
    for at in (early, early + 60, (early + default) / 2, default - 60):
        titles = _titles_fb561(content, state, at, changshe.week)
        assert "長社火攻" in titles, at
        assert "宛城之戰" not in titles and "廣宗決戰" not in titles  # 別場沒開，照排定的時刻
    state.world.time = default + HOUR  # 排定的時刻過了，照舊列
    assert "長社火攻" in mapdata._titles(state, content, changshe.week, changshe.week)


@pytest.mark.slow
@pytest.mark.parametrize("profile", PROFILES)
def test_a_showdown_opened_and_finished_early_stays_in_the_week_it_happened(profile):
    """時間軸上有了結果（收場了）：列在收場的那一週，之後的週也看得到；排定的那一週不再重複列。"""
    content, state = _setup(profile)
    w = state.world
    guangzong = _event(content, "guangzong")
    default = timetable.when_in(w, content, guangzong)
    week = guangzong.week - 2
    done = _in_week(content, state, week, 8)
    assert done < default and _week_of(content, state, done) == week
    w.showdowns_opened["guangzong"] = "guangzong"
    w.timeline["guangzong"] = TimelineResult(key="guan:大勝", time=done)
    assert "廣宗決戰" in _titles_fb561(content, state, done + 60, week)
    after = calendar.week_start(week + 1, content, w) + 60  # 下一週：「天下怎麼變」逐週列，過去的那一週還是有它
    assert "廣宗決戰" in _titles_fb561(content, state, after, week, week + 1)
    assert "廣宗決戰" not in _titles_fb561(content, state, after, guangzong.week, week + 1)


@pytest.mark.slow
@pytest.mark.parametrize("profile", PROFILES)
def test_a_showdown_that_was_not_started_waits_for_its_scheduled_time(profile):
    """沒有人開、也沒收場的決戰照舊等排定的時刻（FB-504 不變）。"""
    content, state = _setup(profile)
    changshe = _event(content, "changshe_fire")
    default = timetable.when_in(state.world, content, changshe)
    assert "長社火攻" not in _titles_fb561(content, state, default - 60, changshe.week)
    assert "長社火攻" in _titles_fb561(content, state, default, changshe.week)


NOW = 1000.0


@pytest.mark.slow
def test_the_admin_start_button_lists_the_battle_on_the_map_at_once(tmp_path):
    """整條路走一遍（7 天季）：管理者在排定時刻之前按「立刻開這一場」，輿圖當下就列，「天下怎麼變」那一週也有。"""
    content = real_content("week7")
    content.config.auto_open_first_season = True
    content.config.admins = ["管"]
    admin = Game.new(content, "管", rng=random.Random(0), world=open_world(tmp_path / "admin.db"))
    admin.client = None
    admin.sync(NOW)
    season = admin.world.get_season()
    scheduled = season.schedule["changshe_fire"]
    week = _week_of(content, admin.state, scheduled)
    monday = NOW + calendar.week_start(week, content, season) / content.config.time_scale
    admin.sync(monday + 5)
    assert admin.state.world.time < scheduled - HOUR
    assert "長社火攻" not in admin.map_state()["events"]
    admin.admin_start_showdown("changshe_fire", monday + 5)
    assert "changshe_fire" in admin.world.get_season().showdowns_opened
    state = admin.map_state()
    assert "長社火攻" in state["events"]
    assert any("長社火攻" in row["events"] for row in state["weeks"] if row["week"] == week)


# ── FB-562：挪到另一週的決戰，照實際排定的時刻歸週 ───────


@pytest.mark.slow
@pytest.mark.parametrize("profile", PROFILES)
@pytest.mark.parametrize(("event_id", "step"), [("changshe_fire", 1), ("guangzong", -1), ("xiaquyang", -1)])
def test_a_showdown_moved_to_another_week_is_listed_in_the_week_it_is_really_scheduled(profile, event_id, step):
    """修前重現：往後挪到下一週的，排定的時刻到了卻列在原本那一週的那一列；往前挪到上一週的，早就到了卻要等原本那一週。"""
    content, state = _setup(profile)
    w = state.world
    event = _event(content, event_id)
    title = event.title
    moved_week = event.week + step
    moved = _in_week(content, state, moved_week, 12)
    w.schedule[timetable.schedule_key(event)] = moved
    assert _week_of(content, state, moved) == moved_week
    before = moved - 60
    assert title not in _titles_fb561(content, state, before, moved_week, _week_of(content, state, before))
    assert title not in _titles_fb561(content, state, before, event.week, _week_of(content, state, before))
    # 排定的時刻到了：列在排定的那一週，不列在時刻表原本寫的那一週
    assert title in _titles_fb561(content, state, moved, moved_week)
    assert title not in _titles_fb561(content, state, moved, event.week, moved_week)
    # 過了那一週，「天下怎麼變」逐週列：還是在排定的那一週的那一列
    later = calendar.week_start(moved_week + 1, content, w) + 60 if moved_week < content.config.season_weeks else moved + HOUR
    now_week = _week_of(content, state, later)
    assert title in _titles_fb561(content, state, later, moved_week, now_week)
    if event.week != moved_week:
        assert title not in _titles_fb561(content, state, later, event.week, now_week)


# ── 不變：其他大事、預設的排定、14 天的季 ─────────────────


@pytest.mark.slow
@pytest.mark.parametrize("profile", PROFILES)
def test_with_the_default_schedule_every_listing_is_the_same_as_the_week_the_timetable_says(profile):
    """預設的排定、沒人開過：每一刻、每一週列出的大事跟時刻表原本寫的那一週、照 timetable.when_in 到了沒一模一樣（其他大事是 calendar.event_time）。"""
    content, state = _setup(profile)
    w = state.world
    end = calendar.nominal_end(content, w)
    step = end / 700
    at = 0.0
    seen = 0
    while at <= end:
        w.time = at
        now_week = _week_of(content, state, at)
        for week in range(1, now_week + 1):
            new = mapdata._titles(state, content, week, now_week)
            old = [e.title for e in timetable.events(w, content) if e.week == week and timetable.when_in(w, content, e) <= at]
            assert new == old, (at, week)
            seen += len(new)
        at += step
    assert seen > 0


@pytest.mark.slow
def test_the_fourteen_day_season_still_has_no_timetable_in_the_map():
    content = real_content()
    state = fb501._state(content)
    state.world.showdowns_opened["changshe_fire"] = "changshe_fire"
    state.world.time = 6 * DAY
    assert mapdata._titles(state, content, 6, 6) == []


# ── 原 test_fb563_564_showdown_opened_moment_and_mandate_order.py（整檔搬進來） ──
# FB-563／FB-564（QA 複驗 FB-560～562 開的兩張，PM 2026-10-20 裁決）。
#
# FB-563：管理者提早開的時刻表決戰，輿圖要照「開的那一刻」判斷到了沒、歸在哪一週（WorldState.showdown_opened_at，照季分）：
# - 跨過週界：開在第 N 週最後幾分鐘、收場在第 N+1 週，列在第 N 週的那一列，不跟著收場（或此刻）換到下一週；
# - 管理者取消的決戰（WorldState.showdowns_cancelled）不列，取消之後排定的時刻過了也不列。
# FB-564：「避開半夜」挪時刻時，天命之爭一定排在那一季最後一場時刻表決戰（廣宗）的集結加打一幕之後（開季、換季蓋章、管理者
# 「這一季立刻蓋章」三條路）；挪不開半夜時寫進管理者那一行。21 天、7 天、週三開季的週末（預設排定）一個字都不變。
# 三種照週算的季（週末、21 天、7 天）都測。

TW = datetime.timezone(datetime.timedelta(hours=8))


MON = datetime.datetime(2026, 10, 19, 0, 0, tzinfo=TW).timestamp()  # 週一 00:00（台灣）


ADMIN = "管"


def _game_fb563(profile, tmp_path, start=MON):
    """開好一季的管理者 Game（網頁按鈕呼叫的同一批 admin_*）。"""
    content = real_content(profile)
    content.config.admins = [ADMIN]
    world = open_world(tmp_path / "world.db")
    admin = Game.new(content, ADMIN, rng=random.Random(1), world=world)
    admin.client = None
    admin.sync(start)
    admin.admin_open_season(start)
    return content, world, admin, start


def _real_at(content, admin, start, world_time):
    """世界秒 world_time 對應的現實秒（開季那一刻是 start，世界秒 0）。"""
    return start + world_time / content.config.time_scale


def _advance(content, world, admin, real):
    admin.sync(real)
    Game.for_world(content, world).world_tick(real)
    admin.sync(real)


def _settle_before(world, *event_ids):
    """前面的決戰當作打完了（時間軸上有結果、開過），一口氣推時間時不會一場一場開集結擋住後面那一場。"""
    def _apply(season):
        for event_id in event_ids:
            season.showdowns_opened[event_id] = event_id
            season.timeline[event_id] = TimelineResult(key="guan:大勢", time=0.0)
    world.mutate_season(_apply)


def _listed(content, admin, title, week):
    return title in mapdata._titles(admin.state, content, week, calendar.point(admin.state.world.time, content, admin.state.world).week)


# ── FB-563：另記開的那一刻 ───────────────────────────────


@pytest.mark.slow
@pytest.mark.parametrize("profile", PROFILES)
def test_a_showdown_opened_just_before_a_week_ends_stays_in_that_week(profile, tmp_path):
    """修前重現：開在第 N 週最後 2 分鐘（世界秒）的決戰，過了週界列的週跟著此刻（開了還沒收場）或收場那一刻換成第 N+1 週，
    第 N 週那一列沒有了。現在記開的那一刻，一直列在第 N 週。"""
    content, world, admin, start = _game_fb563(profile, tmp_path)
    _settle_before(world, "changshe_fire", "wancheng")
    guangzong = _event(content, "guangzong")
    season = admin.state.world
    scheduled = season.schedule["guangzong"]
    sched_week = calendar.point(scheduled, content, season).week
    assert sched_week >= 2
    boundary = calendar.week_start(sched_week, content, season)
    opening = boundary - 120
    assert opening < scheduled
    _advance(content, world, admin, _real_at(content, admin, start, opening))
    admin.admin_start_showdown("guangzong", _real_at(content, admin, start, opening))
    assert "guangzong" in admin.world.get_season().showdowns_opened
    admin.sync(_real_at(content, admin, start, opening))
    title = guangzong.title
    assert _listed(content, admin, title, sched_week - 1)
    assert not _listed(content, admin, title, sched_week)
    # 過了週界（集結中），再過到打完／收場之後：始終列在開的那一週
    for later in (boundary + 5 * 60, boundary + HOUR, boundary + 6 * HOUR):
        _advance(content, world, admin, _real_at(content, admin, start, later))
        assert admin.state.world.time >= boundary
        assert _listed(content, admin, title, sched_week - 1), later
        assert not _listed(content, admin, title, sched_week), later
    state = admin.map_state()
    rows = {row["week"]: row["events"] for row in state["weeks"]}
    assert title in rows[sched_week - 1] and title not in rows[sched_week]
    opened_at = admin.state.world.showdown_opened_at["guangzong"]  # 記的就是開的那一刻
    assert abs(opened_at - opening) < 60 and calendar.point(opened_at, content, admin.state.world).week == sched_week - 1


@pytest.mark.slow
@pytest.mark.parametrize("profile", PROFILES)
def test_a_cancelled_showdown_is_not_listed_on_the_map(profile, tmp_path):
    """修前重現：開過的記號（showdowns_opened）留著，取消的決戰從取消那一刻起一直列在「本週大事」，沒有結果也列。
    現在取消的不列，排定的時刻過了也不列；取消之前（開打中）照舊列。"""
    content, world, admin, start = _game_fb563(profile, tmp_path)
    changshe = _event(content, "changshe_fire")
    season = admin.state.world
    scheduled = season.schedule["changshe_fire"]
    week = calendar.point(scheduled, content, season).week
    opening = max(calendar.week_start(week, content, season), 1800.0) + 1800
    assert opening < scheduled - HOUR / 2
    real = _real_at(content, admin, start, opening)
    _advance(content, world, admin, real)
    admin.admin_start_showdown("changshe_fire", real)
    admin.sync(real)
    title = changshe.title
    assert _listed(content, admin, title, week) and title in admin.map_state()["events"]
    admin.admin_cancel_battle()
    admin.sync(real + 600)
    assert "changshe_fire" in admin.world.get_season().showdowns_opened and "changshe_fire" not in admin.world.get_season().timeline
    for at in (opening + 600, scheduled - 60, scheduled + 60, scheduled + 3 * HOUR):
        _advance(content, world, admin, _real_at(content, admin, start, at))
        now_week = calendar.point(admin.state.world.time, content, admin.state.world).week
        for w in range(1, now_week + 1):
            assert not _listed(content, admin, title, w), (at, w)
        assert title not in admin.map_state()["events"], at
        assert all(title not in row["events"] for row in admin.map_state()["weeks"]), at


@pytest.mark.slow
def test_a_cancelled_showdown_the_admin_later_settles_is_listed_again():
    """取消之後管理者「定結果」了（時間軸上有結果）：那就是發生了，照有結果的寫法列（取排定的時刻與定結果那一刻較早的）。"""
    from tianxia.state import new_game_state

    content = real_content("week7")
    state = new_game_state(content, "甲")
    state.world = fresh_season(content)
    stamp_season(state.world, content, now=MON)
    w = state.world
    event = _event(content, "guangzong")
    done = calendar.week_start(event.week - 2, content, w) + 3000  # 週末一週 18000 世界秒
    week = calendar.point(done, content, w).week
    w.showdowns_opened["guangzong"] = "guangzong"
    w.showdown_opened_at["guangzong"] = done - 600
    w.showdowns_cancelled.append("guangzong")
    w.time = done - 60
    assert event.title not in mapdata._titles(state, content, week, week)
    w.timeline["guangzong"] = TimelineResult(key="guan:大勢", time=done)
    w.time = done + 60
    assert event.title in mapdata._titles(state, content, week, week)


@pytest.mark.slow
@pytest.mark.parametrize("profile", PROFILES)
def test_the_opened_moment_is_recorded_when_the_muster_opens(profile, tmp_path):
    """自然開的（時間到了）也記：記的是開的那一刻（不早於排定的時刻），輿圖照排定的時刻到了沒（跟以前一樣）。"""
    content, world, admin, start = _game_fb563(profile, tmp_path)
    season = admin.state.world
    scheduled = season.schedule["changshe_fire"]
    week = calendar.point(scheduled, content, season).week
    _advance(content, world, admin, _real_at(content, admin, start, scheduled - 60))
    assert "changshe_fire" not in admin.state.world.showdown_opened_at
    assert not _listed(content, admin, "長社火攻", week)
    _advance(content, world, admin, _real_at(content, admin, start, scheduled + 30))
    stored = admin.world.get_season()
    assert "changshe_fire" in stored.showdowns_opened
    assert scheduled - 1 <= stored.showdown_opened_at["changshe_fire"] <= scheduled + 60
    assert _listed(content, admin, "長社火攻", week)
    assert timetable.happened_at(stored, content, _event(content, "changshe_fire")) == scheduled


# ── FB-564：天命之爭一定排在最後一場時刻表決戰之後 ──────────


def _span_world(content):
    return timetable.showdown_span(content, _event(content, "guangzong")) * content.config.time_scale


def _stamp_now(content, now, season_time=0.0):
    """管理者「這一季立刻蓋章」那條路（Game.admin_seal_mandate("now")）：照開季那一刻排好、再蓋天命之季的章、再避開半夜。
    season_time 是蓋章那一刻季的時間，now 是那一刻的現實秒。"""
    start = now - season_time / content.config.time_scale
    season = fresh_season(content)
    stamp_season(season, content, now=start)
    timetable.avoid_quiet_hours(season, content, start)
    season.time = season_time
    season.mandate = True
    season.schedule["tianming"] = timetable.default_time(timetable.find(content, "tianming"), content, season)
    timetable.avoid_quiet_hours(season, content, now)
    return season


def _stamp_at_season_change(content, now):
    """換季蓋章那條路（SqliteWorldStore.next_season）：新的一季一開始就蓋天命之季的章，再避開半夜。"""
    season = fresh_season(content, now=now)
    season.mandate = True
    season.schedule["tianming"] = timetable.default_time(timetable.find(content, "tianming"), content, season)
    timetable.avoid_quiet_hours(season, content, now)
    return season


def _mandate_notes(content, season, now):
    """管理者那一行裡關於天命之爭的話（別的決戰挪不開的不算）。"""
    return [n for n in timetable.quiet_notes(season, content, now) if "天命之爭" in n]


def _ordered(content, season):
    span = _span_world(content)
    schedule = season.schedule
    return schedule["guangzong"] + span <= schedule["tianming"] and schedule["tianming"] < schedule["finale"]


@pytest.mark.slow
def test_the_week7_mandate_stamp_after_a_monday_midnight_open_lands_after_guangzong(tmp_path):
    """QA 重現（FB-564，當時在週末；現在照 7 天季）：週一 00:00 開季，管理者「這一季立刻蓋章」，修前天命之爭被挪到第 10 週・週四 06:00，
    廣宗決戰被挪到第 12 週・週二 10:00（約晚 9 個現實小時）。現在天命之爭排在廣宗決戰收尾之後。"""
    content, world, admin, start = _game_fb563("week7", tmp_path)
    admin.admin_seal_mandate("now")
    season = admin.world.get_season()
    assert season.mandate
    assert _ordered(content, season), {k: calendar.stamp_text(v, content, season) for k, v in season.schedule.items()}
    assert _mandate_notes(content, season, start) == []  # 排得下，不碰半夜，管理者那一行沒有挪不開的話


@pytest.mark.slow
@pytest.mark.parametrize("hour", [0, 1, 23, 12])
def test_the_season_change_route_through_the_store_keeps_the_order(hour, tmp_path):
    """換季蓋章那條路整條走一遍（管理者收季、開下一季，天命之季的章在 SqliteWorldStore.next_season 蓋）：換季那一刻不論落在
    當地幾點，天命之爭都在廣宗收尾之後、季末之前。"""
    content, world, admin, start = _game_fb563("week7", tmp_path)
    admin.admin_seal_mandate("next")
    admin.admin_end_season(start + 100)
    admin.admin_next_season(start + 3 * DAY + hour * HOUR)
    season = world.get_season()
    assert season.mandate and "tianming" in season.schedule
    assert _ordered(content, season), {k: calendar.stamp_text(v, content, season) for k, v in season.schedule.items()}


@pytest.mark.slow
@pytest.mark.parametrize("route", ["now", "season-change"])
@pytest.mark.parametrize("profile", PROFILES)
def test_whatever_hour_the_season_opens_the_mandate_battle_comes_after_guangzong(profile, route):
    """每 15 分鐘的開季時刻掃七天（672 個），兩條蓋章的路：天命之爭都在廣宗決戰的集結加打一幕之後、季末之前。"""
    content = real_content(profile)
    bad = []
    for day in range(7):
        for minute in range(0, 24 * 60, 15):
            now = MON + day * DAY + minute * 60
            season = _stamp_now(content, now) if route == "now" else _stamp_at_season_change(content, now)
            if not _ordered(content, season):
                bad.append((day, minute // 60, minute % 60))
    assert bad == []


@pytest.mark.slow
@pytest.mark.parametrize("profile", PROFILES)
def test_a_mid_season_stamp_never_puts_the_mandate_battle_before_guangzong(profile):
    """管理者在季中某一刻蓋章（廣宗還沒打）：開季的各種時刻 × 蓋章在第一場決戰之前、廣宗之前一週。"""
    content = real_content(profile)
    guangzong = _event(content, "guangzong")
    bad = []
    for day in range(7):
        for minute in range(0, 24 * 60, 60):
            start = MON + day * DAY + minute * 60
            probe = fresh_season(content)
            stamp_season(probe, content, now=start)
            at = calendar.week_start(max(1, guangzong.week - 1), content, probe) + HOUR
            season = _stamp_now(content, start + at / content.config.time_scale, season_time=at)
            if not _ordered(content, season):
                bad.append((day, minute // 60))
    assert bad == []


@pytest.mark.slow
@pytest.mark.parametrize("profile", PROFILES)
def test_a_guangzong_the_admin_scheduled_late_pushes_the_mandate_battle_behind_it(profile):
    """修前重現：管理者先把廣宗排得比天命之爭預設時刻只早 10 分鐘（集結加打一幕要 39 分鐘，疊在一起）或更晚，再蓋章：
    天命之爭預設沒碰半夜，所以不動，排在廣宗前面或跟它疊在一起。現在一定排在廣宗收尾之後（白天，管理者那一行沒有話）。"""
    content = real_content(profile)
    scale = content.config.time_scale
    now = MON  # 21 天、7 天季的日曆貼著現實的天（預設 20:00、22:00），不碰半夜；週末下面換成正午
    if profile == "week7":
        probe = fresh_season(content)
        stamp_season(probe, content, now=MON)
        default = timetable.default_time(timetable.find(content, "tianming"), content, probe)
        now = 20_000 * DAY + 12 * HOUR - default / scale - content.config.pill_day_utc_offset_hours * HOUR  # 天命之爭預設落在當地正午
    season = fresh_season(content)
    stamp_season(season, content, now=now)
    default = timetable.default_time(timetable.find(content, "tianming"), content, season)
    season.schedule["guangzong"] = default - 10 * 60 * scale
    season.mandate = True
    season.schedule["tianming"] = default
    timetable.avoid_quiet_hours(season, content, now)
    assert season.schedule["guangzong"] == default - 10 * 60 * scale  # 廣宗不動
    assert _ordered(content, season)
    assert season.schedule["tianming"] - default <= 2 * calendar.cal_hour_seconds(content, season) + _span_world(content)  # 只往後挪一點
    assert _mandate_notes(content, season, now) == []


# ── 不變：預設的排定 ─────────────────────────────────────


@pytest.mark.slow
@pytest.mark.parametrize("profile", PROFILES)
def test_the_default_schedules_do_not_move(profile):
    """沒碰半夜的預設排定（週三 14:00 開季的週末、21 天、7 天）：蓋章之後天命之爭還在預設時刻，其餘決戰與季末一個字不動。"""
    content = real_content(profile)
    wed = datetime.datetime(2026, 10, 21, 14, 0, tzinfo=TW).timestamp()
    plain = fresh_season(content)
    stamp_season(plain, content, now=wed)
    timetable.avoid_quiet_hours(plain, content, wed)
    for route in (_stamp_now(content, wed), _stamp_at_season_change(content, wed)):
        for key, value in plain.schedule.items():
            assert route.schedule[key] == value, key
        assert route.schedule["tianming"] == timetable.default_time(timetable.find(content, "tianming"), content, route)


# ── FB-258（2026-10-31 從 tests/map/test_map_qa_fb.py 併進來）────────
# 輿圖升級 QA 的回饋（docs/superpowers/feedback/試玩回饋.md 的 FB-258～264，PM 2026-10-15 定的修法）：疊層的資料那一半。
# 網頁那一半在 tests/test_map_web.py。正式內容、週末設定。


def _game_fb258(faction="guan", at="yingchuan"):
    c = real_content("week7")  # 地盤拔河的舊規則（領地爭奪 PM 2026-10-22 起正式內容打開）
    c.config.auto_open_first_season = True
    game = Game.new(c, "沈浪", rng=random.Random(0), world=open_world())
    game.client = None
    p = game.state.player
    p.faction, p.location = faction, at
    return game


def _order(game, faction, template, **kw):
    order = Order(id=f"1:{faction}:{template}:x", template=template, faction=faction, week=orders.week_of(game.state, game.content),
                  quota=99, text="", **kw)
    game.state.world.orders = [o for o in game.state.world.orders if not (o.faction == faction and o.template == template)] + [order]
    return order


def _intercept(game, faction, location):
    return _order(game, faction, "intercept", front=territory.line_of(game.content, location), location=location)


def _why(st, loc_id):
    return [text for text, _ in next((g["why"] for g in st["suggest"] if g["id"] == loc_id), [])]


# ── FB-258：截糧只在指定的那一處（FB-248），守不記截糧，自家地盤上的截糧對手是運糧隊 ──


def test_fb258_the_intercept_badge_is_only_on_the_intercept_place():
    game = _game_fb258("huang", "huangjin_camp")
    _intercept(game, "huang", "changshe")
    st = game.map_state()
    marked = {k for k, p in st["places"].items() if p["order"] and "截糧" in p["order"]}
    assert marked == orders.intercept_spots(game.content, "changshe") == {"changshe"}


def test_fb258_a_hold_never_gives_intercept_as_the_reason():
    game = _game_fb258("guan", "changshe")
    _intercept(game, "guan", "runan_wilds")
    st = game.map_state()
    for g in st["suggest"]:
        if g["sortie"] != "attack":
            assert not any("截糧" in t for t in _why(st, g["id"])), g
    runan = st["places"]["runan_wilds"]
    assert runan["sortie"] == "attack" and "軍令・截糧" in _why(st, "runan_wilds")


def test_fb264_a_season_first_reckoned_later_has_no_start():
    """中途上線（第一次算在第 3 週）：沒有開季那一刻的樣子，不假裝有。"""
    game = _game_fb258()
    w, c = game.state.world, game.content
    w.time = calendar.week_start(3, c, w) + 60
    territory.update(w, c)
    assert 0 not in w.territory.weeks and game.map_state()["start"] is None
