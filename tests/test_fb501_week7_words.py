"""FB-501（7 天濃縮季 QA 第 7 件清單，PM 2026-10-20）：7 天季還寫「週」的地方換成段（或軍令的「今日／每天」）。
季曆有段的季（calendar.week7_on）才換字，換字一律走 calendar.week_word／week_label（網頁走 week_words 送的那一份）；
21 天季、週末、14 天一個字都不變（例外：暫停再繼續那一句照季寫季長，21 天季照舊）。字待 joy 潤。
FB-502（PM 2026-10-20）推翻「21 天季不動」的軍令那幾個字：21 天季的軍令也每天一道，照「今日／每天」寫，見
test_fb502_season21_order_words；這裡 21 天季只驗段以外的「週」照舊。"""
from __future__ import annotations

import random

import pytest
from conftest import real_content

from tianxia import calendar, duel, explore_modes, howto, orders, renown, rules, seats, timetable, world, yuedan
from tianxia.state import Order, YuedanEntry, new_game_state
from tianxia.world_state import fresh_season, stamp_season

pytestmark = pytest.mark.slow  # 每一條都載真實內容、開一季

HOUR, DAY = 3600, 86400
MON = 1792339200  # 2026-10-19 週一 00:00（台灣）
WED14 = 1792549800 + 3.5 * HOUR  # 2026-10-21 週三 14:00（台灣）
BOSS = "段鐵頭"  # 頭目次數用完那一句的名字（FB-672：explore_modes.boss_gone 多一個 name）
PROFILES = ("week7", "season21", "weekend", None)


def _content(profile):
    return real_content(profile) if profile else real_content()


def _season(content, now=MON):
    season = fresh_season(content)
    stamp_season(season, content, now=now)
    return season


def _state(content, now=MON):
    state = new_game_state(content, "甲")
    state.world = _season(content, now)
    return state


# ── 同一個函式：calendar.week_word／week_label／week_words ──


def test_week7_names_segments_with_their_days():
    c7 = real_content("week7")
    s7 = _season(c7)
    assert [calendar.segment_days(w, c7) for w in (1, 2, 3)] == [(1, 2), (3, 4), (5, 7)]
    assert [calendar.week_label(w, c7, s7) for w in (1, 2, 3)] == [
        "第 1 段（第 1～2 天）", "第 2 段（第 3～4 天）", "第 3 段（第 5～7 天）"]
    assert calendar.week_label(1, c7, s7, form="tight") == "第 1 段（第 1～2 天）"
    assert calendar.week_label(2, c7, s7, form="end") == "第 2 段末（第 4 天）"
    assert calendar.week_label(2, c7, s7, form="inner") == "第 2 段・第 3～4 天"
    assert [calendar.week_word(k, c7, s7) for k in ("this", "this_one", "each", "order_this", "order_that", "order_each")] == [
        "這一段", "這一段", "每段", "今日", "今天", "每天"]
    words = calendar.week_words(c7, s7)
    assert words["this"] == "這一段" and words["names"][2] == "第 3 段（第 5～7 天）" and words["ends"][0] == "第 1 段末（第 2 天）"


@pytest.mark.parametrize("profile", ["season21", "weekend", None])
def test_other_seasons_keep_their_week_words(profile):
    content = _content(profile)
    season = _season(content)
    assert [calendar.week_label(2, content, season, form=f) for f in ("", "tight", "end", "inner")] == [
        "第 2 週", "第2週", "第 2 週週末", "第 2 週"]
    assert [calendar.week_word(k, content, season) for k in ("this", "this_one", "each")] == ["本週", "這一週", "每週"]
    assert calendar.week_word("this", content, None) == "本週"  # 沒有季（上一季的江湖史）照原本的字
    if profile != "season21":  # 21 天季的軍令每天一道，軍令的字與 words 照「今日／每天」（FB-502，test_fb502_season21_order_words）
        assert calendar.week_words(content, season) is None
        assert [calendar.week_word(k, content, season) for k in ("order_this", "order_that", "order_each")] == ["本週", "這週", "每週一"]


# ── 4. 練功鈕「這一週他不再現身」──


def test_the_boss_line_names_the_next_segment_day():
    c7 = real_content("week7")
    state = _state(c7)
    # FB-672：這一句多帶頭目的名字（「這一段他不再現身」→「這一段頭目某某不再現身」）；哪一天再來、哪一種季寫哪個詞這一張沒動
    state.world.time = DAY + HOUR  # 第 2 天：第 1 段，下一段第 3 天
    assert explore_modes.boss_gone(state, c7, BOSS) == "這一段頭目段鐵頭不再現身，第 3 天 00:00 再來"
    state.world.time = 3 * DAY + HOUR  # 第 4 天：第 2 段，下一段第 5 天
    assert explore_modes.boss_gone(state, c7, BOSS) == "這一段頭目段鐵頭不再現身，第 5 天 00:00 再來"
    state.world.time = 5 * DAY  # 第 6 天：最後一段，季末之前不再重算
    assert explore_modes.boss_gone(state, c7, BOSS) == explore_modes.BOSS_GONE_SEASON.format(name=BOSS)


def test_the_boss_line_reads_the_live_option_on_week7():
    """引擎那一顆練功鈕（Game._practice_option 的頭目分支）走 boss_gone：用滿這一段的次數就寫段。"""
    c7 = real_content("week7")
    state = _state(c7, now=WED14)
    boss = next(iter(c7.duels))
    state.player.duel_tally[duel.week_key(state, c7, boss)] = c7.config.duel.per_boss_week
    assert duel.used_up(state, c7, boss)
    assert explore_modes.boss_gone(state, c7, BOSS).startswith("這一段頭目段鐵頭不再現身，第 3 天")


@pytest.mark.parametrize("profile,line", [("season21", explore_modes.BOSS_GONE_WEEK), ("weekend", explore_modes.BOSS_GONE_SEASON),
                                          (None, explore_modes.BOSS_GONE_SEASON)])
def test_other_seasons_keep_the_boss_line(profile, line):
    content = _content(profile)
    assert explore_modes.boss_gone(_state(content), content, BOSS) == line.format(name=BOSS)


# ── 5. 名聲：每週通緝、每週海捕文書 ──


def test_renown_perks_say_each_segment_on_week7():
    c7 = real_content("week7")
    s7 = _season(c7)
    fame = [p for t in range(1, 5) for p in renown.fame_perks(c7, t, s7)]
    kou = [p for t in range(1, 5) for p in renown.virtue_perks(c7, "寇", t, s7)]
    assert "敵方陣營每段通緝你" in fame and not any("每週" in p for p in fame)
    assert any(p.startswith("官府每段貼你的海捕文書") for p in kou) and not any("每週" in p for p in kou)
    howto_text = "".join(howto.renown_lines(c7, s7))
    assert "每段通緝你" in howto_text and "官府每段貼你" in howto_text


@pytest.mark.parametrize("profile", ["season21", "weekend", None])
def test_renown_perks_keep_each_week_elsewhere(profile):
    content = _content(profile)
    season = _season(content)
    for t in range(1, 5):
        assert renown.fame_perks(content, t, season) == renown.fame_perks(content, t)
        for way in renown.PATHS:
            assert renown.virtue_perks(content, way, t, season) == renown.virtue_perks(content, way, t)


# ── 3. 主線與玩法說明：軍令每天一道 ──


def test_howto_says_orders_come_every_day_on_week7():
    c7 = real_content("week7")
    state = _state(c7)
    quest = "".join(howto.war_help(state, c7)["quest"])
    assert "投靠陣營之後每天有軍令" in quest and "每週一" not in quest
    join = "".join(howto.join_lines(c7, state.world))
    assert "**軍令**：每天發令" in join and "今日的軍令卡在江湖頁行動列底下" in join
    assert "每週一" not in join and "本週" not in join


@pytest.mark.parametrize("profile", ["weekend"])
def test_howto_orders_lines_unchanged_elsewhere(profile):
    """週末本來就是每週一。21 天季的軍令也是每天一道，FB-502 起照「每天」寫（test_fb502_season21_order_words）。"""
    content = _content(profile)
    state = _state(content)
    assert "投靠陣營之後每週一有軍令" in "".join(howto.war_help(state, content)["quest"])
    join = "".join(howto.join_lines(content, state.world))
    assert "**軍令**：每週一發令" in join and "本週的軍令卡在江湖頁行動列底下" in join
    assert howto.quest_help(content, rules.haoqiang_allied(content, state.world), state.world) == howto.quest_help(
        content, rules.haoqiang_allied(content, state.world))


# ── 11. 軍令的字（content/orders.json 的 {本週}{這週}）──


def _order(world_state):
    return Order(id="o1", template="intercept", faction="guan", week=1, quota=10, text="")


def test_order_text_slots_follow_the_season():
    """21 天季（軍令也每天一道）見 test_fb502_season21_order_words（FB-502）。"""
    c7, cw = real_content("week7"), real_content("weekend")
    s7, sw = _state(c7), _state(cw)
    raw = "{地點}，{本週}截斷它；{人物}{這週}連敗幾陣。"
    assert orders.fill(s7, c7, _order(s7), raw).endswith("，今日截斷它；今天連敗幾陣。")
    assert orders.fill(sw, cw, _order(sw), raw).endswith("，本週截斷它；這週連敗幾陣。")


def test_issued_orders_read_today_on_week7_only():
    c7, cw = real_content("week7"), real_content("weekend")
    for content, want, never in ((c7, "今日", "本週"), (cw, "本週", "今日截斷")):
        season = _season(content)
        world.settle_season_start(season, content, random.Random(0))
        texts = [o.text for o in season.orders]
        assert texts and not any("{" in t for t in texts)
        assert not any(never in t for t in texts)
        intercept = [t for t in texts if "截斷它" in t]
        assert all(f"{want}截斷它" in t for t in intercept)


# ── 12. 月旦評、第 4 階席次 ──


def _publish_yuedan(content, week):
    state = _state(content)
    state.world.yuedan = [YuedanEntry(week=week, name="乙", board="名人", line="名動四方，一時無兩", at=0.0)]
    yuedan.publish(state, content)
    return state.world.rumors[-1].text


def test_yuedan_head_names_the_segment_on_week7():
    assert _publish_yuedan(real_content("week7"), 2).startswith("許劭月旦評（第 2 段・第 3～4 天）：")
    assert _publish_yuedan(real_content("season21"), 2).startswith("許劭月旦評（第 2 週）：")


def test_seat_rotation_rumor_says_this_segment_on_week7():
    for profile, head in (("week7", "這一段在任的"), ("season21", "本週在任的"), ("weekend", "本週在任的")):
        content = _content(profile)
        state = _state(content)
        state.world.seat_ledger = {"guan": {"乙": {1: 5}}}
        seats.rotate(state, content, 2)
        assert any(r.text.startswith(head) for r in state.world.rumors), profile


# ── 9、10. 管理者：時刻表、開季、暫停再繼續 ──


def test_default_dates_follow_the_week7_timetable():
    assert timetable.default_dates_note(real_content("week7")) == "預設在第 2、4、7 天 20:00、季末第 7 天過完"
    for profile in ("weekend", None):
        assert timetable.default_dates_note(_content(profile)) is None


def test_default_dates_follow_the_season21_timetable():
    """修前重現：21 天季這一句 None，網頁退回週末的「預設在第 6、9、11 週中、第 12 週末」（21 天季只有 3 週；PM 2026-10-20）。
    寫的要跟開季真正排進 schedule 的時刻對得上。"""
    c21 = real_content("season21")
    assert timetable.default_dates_note(c21) == "預設在第 1、2、3 週週六 20:00、季末第 3 週週日過完"
    season = _season(c21)
    for e in (e for e in c21.timetable if e.kind == "showdown"):
        p = calendar.point(timetable.when_in(season, c21, e), c21, season)
        assert (p.week, calendar.WEEKDAYS[p.weekday], p.hour) == (e.week, "六", 20), e.id
    finale = next(e for e in c21.timetable if e.kind == "finale")
    assert timetable.when_in(season, c21, finale) == calendar.calendar_end(c21, season)  # 最後一週週日過完
    assert calendar.point(calendar.calendar_end(c21, season) - 60, c21, season).week == finale.week


def test_resume_line_names_the_season_length():
    c7, c21 = real_content("week7"), real_content("season21")
    assert world.resume_skip_text(_season(c7), c7, 3600) == "7 天的季：季曆對回現實的日子，暫停期間的大事在這一刻一起發生，季末照原本的日期"
    assert world.resume_skip_text(_season(c21), c21, 3600) == world.RESUME_SKIP_REAL
    assert world.RESUME_SKIP_REAL == "21 天的季：季曆對回現實的星期，暫停期間的大事在這一刻一起發生，季末照原本的日期"


# ── 網頁的那一份：status.calendar.words、管理者那一份 ──


def _game(profile, opened=MON):
    from tianxia.engine import Game
    from tianxia.sqlite_world import open_world

    content = _content(profile)
    content.config.admins = ["甲"]
    content.config.train_event_chance = 0.0
    store = open_world()
    store.seed_first_season(content)
    game = Game.new(content, "甲", rng=random.Random(0), world=store)
    game.client = None
    game.admin_open_season(opened)
    game.state.player.faction = "guan"
    game.sync(opened)
    return game


@pytest.mark.parametrize("profile", ["week7", "season21", "weekend"])
def test_status_sends_the_words_only_on_week7(profile):
    cal = _game(profile).status_data()["calendar"]
    if profile == "week7":
        assert cal["words"]["names"][0] == "第 1 段（第 1～2 天）" and cal["words"]["order_this"] == "今日"
    elif profile == "season21":  # 只有軍令的字（FB-502）：沒有段的名字，網頁的「週」照原本的字
        assert "names" not in cal["words"] and "this" not in cal["words"] and cal["words"]["order_this"] == "今日"
    else:
        assert "words" not in cal


ADMIN = {  # 管理者時刻表第一列與最後一列的開頭、暫停那一句、開季問句括號裡那一句
    "week7": ("第 1 段（第 1～2 天）　三十六方起義", "第 3 段（第 5～7 天）　", {"days": "7", "unit": "日子"},
              "預設在第 2、4、7 天 20:00、季末第 7 天過完"),
    "season21": ("第1週　三十六方起義", "第3週　", {"days": "21", "unit": "星期"},
                 "預設在第 1、2、3 週週六 20:00、季末第 3 週週日過完"),
    "weekend": ("第1週　三十六方起義", "第12週　", None, None),
}


@pytest.mark.parametrize("profile", list(ADMIN))
def test_admin_view_labels_and_lines(profile, monkeypatch):
    """一個資料庫一季：照季各開一個測試（同一個測試開兩季會讀到同一份季）。"""
    import server

    first, last, realign, dates = ADMIN[profile]
    game = _game(profile, opened=WED14 if profile == "week7" else MON)
    monkeypatch.setattr(server, "CONTENT", game.content)  # 伺服器整理管理者資料讀的是 server.CONTENT
    rows = server.timetable_choices(game)["timetable"]
    assert rows[0]["label"] == first and rows[-1]["label"].startswith(last)
    view = server.admin_choices(game)
    assert view["realign"] == realign and view["default_dates"] == dates
