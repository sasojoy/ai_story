"""推力規則與貢獻帳（計畫 T3、第一季設計第七節）：陣營人數緩衝、每人每曆日上限、超過上限只記兩成、貢獻帳。

全部掛在第一季開關後面（install_season_one 打開、季也蓋了章）；開關關著時一個字都不變，見
test_push_off_switch_is_plain_change_trend。用 tests/fixtures/content 的 kou 線（開局 30），
陣營 guan 想壓低、huang 想推高、haoqiang 對這條線沒有目標。"""
import random

import pytest

from conftest import install_season_one, walk_to
from tianxia import calendar, push, rules
from tianxia.engine import Game
from tianxia.models import Choice, Effect, Event, FactionDef
from tianxia.state import new_game_state

DAY = 86400


@pytest.fixture
def s1(content):
    """第一季開關開著、季長 2.5 天（一個曆日約 2571 世界秒）、三個陣營、遊歷不接戰後事件。"""
    install_season_one(content)
    content.scenario.factions = [
        FactionDef(id="guan", name="官軍", join_at=["town"], goals={"kou": -1}),
        FactionDef(id="huang", name="黃巾", join_at=["lake"], goals={"kou": 1}),
        FactionDef(id="haoqiang", name="地方豪強"),
    ]
    content.config.train_event_chance = 0.0
    return content


def cal_day_seconds(content) -> float:
    return DAY / calendar.cal_scale(content)


def member(content, world, name: str, faction: str | None, *, at_cal_day: float = 1.0) -> Game:
    """一個在共用賽季裡的玩家（跟其他 member 共用同一份存檔）；at_cal_day＝世界時間放在第幾個曆日的哪裡（1.0＝第一天開頭）。"""
    game = Game.new(content, name, rng=random.Random(0), world=world)
    game.state.player.faction = faction
    game.state.world.time = (at_cal_day - 1) * cal_day_seconds(content) + 10
    return game


def trend(game: Game, trend_id: str = "kou") -> int:
    return game.state.world.trends[trend_id]


def mark_active(game: Game, faction: str, names: list[str], *, ago_days: float = 0.0) -> None:
    """把這些人記成「ago_days 個曆日以前推過大勢」的同陣營成員（不用真的讓他們各推一次）。"""
    ago = ago_days * cal_day_seconds(game.content)
    game.state.world.active_pushers.setdefault(faction, {}).update({n: game.state.world.time - ago for n in names})


# ── 純函式 ───────────────────────────────────────────────


@pytest.mark.parametrize("delta, n, expected", [(4, 4, 2.0), (4, 1, 4.0), (9, 9, 3.0), (-4, 4, -2.0), (3, 0, 3.0)])
def test_buffered_divides_by_the_root_of_the_headcount(delta, n, expected):
    assert push.buffered(delta, n) == pytest.approx(expected)


def test_active_count_counts_yourself_and_only_recent_members_of_your_faction(s1, world):
    game = member(s1, world, "沈浪", "huang")
    window = cal_day_seconds(s1)
    now = game.state.world.time
    assert push.active_count(game.state, "huang", now, window) == 1  # 沒人推過：只有自己，最少 1
    game.state.world.active_pushers["huang"] = {"甲": now - 10, "乙": now - window - 1, "沈浪": now - 20}
    game.state.world.active_pushers["guan"] = {"丙": now}
    assert push.active_count(game.state, "huang", now, window) == 2  # 甲、自己；乙過期、丙是別的陣營
    assert push.active_count(game.state, None, now, window) == 1  # 散人沒有陣營可數：1


def test_take_whole_keeps_the_fraction_for_next_time():
    assert push.take_whole(0.0, 0.7071) == (0, pytest.approx(0.7071))
    whole, rest = push.take_whole(0.7071, 0.7071)
    assert (whole, rest) == (1, pytest.approx(0.4142))
    assert push.take_whole(0.4, -0.7) == (0, pytest.approx(-0.3))  # 往零的方向取整，正負會互相抵銷
    assert push.take_whole(0.0, -2.0) == (-2, 0.0)
    assert push.take_whole(0.0, 1.9999999999) == (2, 0.0)  # 浮點誤差不能讓差一點變成少推一點


def test_split_by_cap_and_contribution_round_half_up():
    assert push.split_by_cap(2.0, 9.0, 10.0) == (1.0, 1.0)
    assert push.split_by_cap(2.0, 10.0, 10.0) == (0.0, 2.0)
    assert push.split_by_cap(2.0, 0.0, 10.0) == (2.0, 0.0)
    assert push.contribution(4, 2.0, 2.0, 10, 0.2) == 40  # 全在上限內：不打折
    assert push.contribution(4, 2.0, 0.0, 10, 0.2) == 8  # 全超過：兩成
    assert push.contribution(1, 1.0, 0.25, 10, 0.0) == 3  # 2.5 → 3（四捨五入，不是銀行家捨入）
    assert push.contribution(1, 0.0, 0.0, 10, 0.2) == 0


def test_recent_days_and_drop_stale_do_not_touch_their_input():
    pushed = {"4:kou": 1.0, "5:kou": 2.0, "6:yingru": 3.0, "壞掉的鍵": 4.0}
    assert push.recent_days(pushed, 6) == {"5:kou": 2.0, "6:yingru": 3.0}
    assert len(pushed) == 4
    active = {"huang": {"甲": 100.0, "乙": 5.0}, "guan": {"丙": 1.0}}
    assert push.drop_stale(active, 120.0, 50.0) == {"huang": {"甲": 100.0}}  # 清空的陣營整列拿掉
    assert active == {"huang": {"甲": 100.0, "乙": 5.0}, "guan": {"丙": 1.0}}


# ── 人數緩衝 ─────────────────────────────────────────────


def test_buffer_by_active_members(s1, world):
    """同陣營 4 個活躍成員（含自己）：推 +4 只推 +2；貢獻照記 40（不打折）。"""
    game = member(s1, world, "沈浪", "huang")
    mark_active(game, "huang", ["甲", "乙", "丙"])
    msgs = game.push_trend("kou", 4, source="test")
    assert trend(game) == 32
    assert msgs == ["（寇亂 +2）"]
    assert game.state.player.contrib == 40


def test_inactive_members_do_not_count(s1, world):
    """一個曆日以前推過的人不算，也順手清掉；陣營外的人也不算。"""
    game = member(s1, world, "沈浪", "huang")
    mark_active(game, "huang", ["甲", "乙", "丙"], ago_days=1.5)
    mark_active(game, "guan", ["丁"])
    game.push_trend("kou", 4, source="test")
    assert trend(game) == 34
    assert game.state.player.contrib == 40
    assert set(game.state.world.active_pushers["huang"]) == {"沈浪"}  # 過期的清掉了，不讓它一直長
    assert set(game.state.world.active_pushers["guan"]) == {"丁"}


def test_a_stale_member_is_dropped_but_a_fresh_one_still_counts(s1, world):
    game = member(s1, world, "沈浪", "huang")
    mark_active(game, "huang", ["甲"], ago_days=0.5)
    mark_active(game, "huang", ["乙"], ago_days=2)
    game.push_trend("kou", 4, source="test")
    assert trend(game) == 32  # n＝2（甲、自己）：4 ÷ √2 ＝ 2.83，滿兩點才動
    assert game.state.world.trend_accum["kou"] == pytest.approx(4 / 2**0.5 - 2)


def test_pushes_by_different_players_buffer_each_other_through_the_shared_season(s1, world):
    """真的各推一次、存進共用賽季：後來的人讀到先推的人，人數緩衝跟著上去。"""
    first = member(s1, world, "甲", "huang")
    first.push_trend("kou", 4, source="test")
    first._save_season()
    assert trend(first) == 34  # 一個人：不打折
    second = member(s1, world, "乙", "huang")
    second.state.world.time = first.state.world.time + 60  # 一分鐘之後
    assert set(second.state.world.active_pushers["huang"]) == {"甲"}
    second.push_trend("kou", 4, source="test")
    assert trend(second) == 34 + 2  # 甲、乙兩人：4 ÷ √2 ＝ 2.83，進整數得 2
    assert second.state.player.contrib == 40


def test_fractional_pushes_accumulate(s1, world):
    """同陣營 2 人時，推 +1 三次→大勢共動 2（0.71 × 3 ＝ 2.12），訊息只在真的動的那兩次出現。"""
    game = member(s1, world, "沈浪", "huang")
    mark_active(game, "huang", ["甲"])
    results = [game.push_trend("kou", 1, source="test") for _ in range(3)]
    assert results == [[], ["（寇亂 +1）"], ["（寇亂 +1）"]]
    assert trend(game) == 32
    assert game.state.world.trend_accum["kou"] == pytest.approx(3 / 2**0.5 - 2)
    assert game.state.player.contrib == 30  # 貢獻不打折：三次各 10


def test_the_leftover_fraction_is_per_trend_and_shared_by_everyone(s1, world):
    """不足一點的推力記在全服、每條線一個；不同的人推同一條線會湊在一起。"""
    a = member(s1, world, "甲", "huang")
    mark_active(a, "huang", ["乙"])
    a.push_trend("kou", 1, source="test")
    a._save_season()
    b = member(s1, world, "乙", "huang")
    b.state.world.time = a.state.world.time + 5
    assert b.state.world.trend_accum == {"kou": pytest.approx(0.7071, abs=1e-3)}
    assert b.push_trend("kou", 1, source="test") == ["（寇亂 +1）"]  # 0.71 ＋ 0.71 ＞ 1：這一下動了


# ── 每曆日上限 ───────────────────────────────────────────


@pytest.mark.parametrize("steps", [[12], [1] * 12], ids=["one push of 12", "twelve pushes of 1"])
def test_daily_cap_then_twenty_percent(s1, world, steps):
    """上限 10：連推 12 點→大勢只動 10，貢獻 100 ＋ 2×10×0.2 ＝ 104。"""
    game = member(s1, world, "沈浪", "huang")
    for step in steps:
        game.push_trend("kou", step, source="test")
    assert trend(game) == 40
    assert game.state.player.contrib == 104
    assert game.state.player.contrib_weeks == {1: 104}
    assert game.state.player.pushed == {"1:kou": pytest.approx(10)}


def test_the_cap_is_counted_after_the_buffer(s1, world):
    """上限算的是緩衝後真的推出去多少：4 人活躍時每點只算 0.5，要推 20 點才頂到 10。"""
    game = member(s1, world, "沈浪", "huang")
    mark_active(game, "huang", ["甲", "乙", "丙"])
    game.push_trend("kou", 20, source="test")
    assert trend(game) == 40
    assert game.state.player.contrib == 200  # 剛好在上限內：沒有超過的部分
    game.push_trend("kou", 4, source="test")
    assert trend(game) == 40  # 今天這條線滿了
    assert game.state.player.contrib == 200 + 8  # 4 點 × 10 × 0.2


def test_a_push_that_straddles_the_cap_splits_the_contribution(s1, world):
    """只剩一點空間時推 4 點（4 人緩衝成 2）：一半推得動、一半超過。大勢動 1，貢獻 10×(2 ＋ 2×0.2) ＝ 24。"""
    game = member(s1, world, "沈浪", "huang")
    mark_active(game, "huang", ["甲", "乙", "丙"])
    game.state.player.pushed["1:kou"] = 9.0
    game.push_trend("kou", 4, source="test")
    assert trend(game) == 31
    assert game.state.player.contrib == 24


def test_the_cap_is_per_trend(s1, world):
    game = member(s1, world, "沈浪", "huang")
    game.push_trend("kou", 10, source="test")
    game.push_trend("yingru", 5, source="test")
    assert (trend(game), trend(game, "yingru")) == (40, 45)
    assert game.state.player.pushed == {"1:kou": pytest.approx(10), "1:yingru": pytest.approx(5)}


def test_cap_resets_next_calendar_day(s1, world):
    game = member(s1, world, "沈浪", "huang")
    game.push_trend("kou", 12, source="test")
    assert trend(game) == 40
    game.state.world.time = cal_day_seconds(s1) + 10  # 第 2 個曆日
    game.push_trend("kou", 12, source="test")
    assert trend(game) == 50
    assert game.state.player.contrib == 208
    assert game.state.player.pushed == {"1:kou": pytest.approx(10), "2:kou": pytest.approx(10)}
    assert game.state.player.contrib_weeks == {1: 208}  # 兩個曆日都在第 1 週


def test_pushed_keeps_only_today_and_yesterday(s1, world):
    game = member(s1, world, "沈浪", "huang")
    for day in (1, 2, 3):
        game.state.world.time = (day - 1) * cal_day_seconds(s1) + 10
        game.push_trend("kou", 1, source="test")
    assert set(game.state.player.pushed) == {"2:kou", "3:kou"}


def test_contribution_lands_in_the_week_of_the_push(s1, world):
    """一週是 7 個曆日；跨週的推力各記各的週。"""
    game = member(s1, world, "沈浪", "huang", at_cal_day=7.0)
    game.push_trend("kou", 3, source="test")
    game.state.world.time = 7 * cal_day_seconds(s1) + 10  # 第 8 個曆日：第 2 週
    game.push_trend("kou", 2, source="test")
    assert game.state.player.contrib_weeks == {1: 30, 2: 20}
    assert game.state.player.contrib == 50


# ── 散人、逆著陣營目標 ────────────────────────────────────


def test_unaffiliated_push_moves_trend_but_records_no_contribution(s1, world):
    """散人也能推大勢、也受每曆日上限，但不記貢獻、不記活躍名單；人數當 1。"""
    game = member(s1, world, "沈浪", None)
    mark_active(game, "huang", ["甲", "乙", "丙"])  # 別人的陣營不會緩衝他
    game.push_trend("kou", 4, source="test")
    assert trend(game) == 34
    game.push_trend("kou", 12, source="test")
    assert trend(game) == 40  # 上限 10 照樣管他
    p = game.state.player
    assert (p.contrib, p.contrib_weeks) == (0, {})
    assert set(game.state.world.active_pushers) == {"huang"}
    assert "沈浪" not in game.state.world.active_pushers["huang"]


@pytest.mark.parametrize(
    "faction, trend_id, delta",
    [("guan", "kou", 3), ("huang", "kou", -3), ("haoqiang", "kou", 3), ("huang", "yingru", 3)],
    ids=["官軍推高黃巾", "黃巾壓低黃巾", "豪強對這條線沒有目標", "陣營對這條線沒有目標"],
)
def test_push_against_own_goal_records_no_contribution(s1, world, faction, trend_id, delta):
    """官軍在豪強的事件裡把黃巾推高：大勢照動，貢獻不記。對這條線沒有目標的陣營也不記。"""
    game = member(s1, world, "沈浪", faction)
    before = trend(game, trend_id)
    game.push_trend(trend_id, delta, source="test")
    assert trend(game, trend_id) == before + delta
    assert (game.state.player.contrib, game.state.player.contrib_weeks) == (0, {})
    assert game.state.world.active_pushers[faction] == {"沈浪": game.state.world.time}  # 推過大勢就算活躍


def test_pushing_towards_your_goal_down_the_trend_counts_too(s1, world):
    """官軍的目標是壓低：往下推才記貢獻。"""
    game = member(s1, world, "沈浪", "guan")
    game.push_trend("kou", -3, source="test")
    assert trend(game) == 27
    assert game.state.player.contrib == 30


def test_a_push_that_does_nothing_earns_nothing(s1, world):
    """還沒浮現的隱藏線壓低是無效的（跟 change_trend 一樣），不能因此刷貢獻。"""
    s1.scenario.factions[0].goals["bao"] = -1
    game = member(s1, world, "沈浪", "guan")
    assert game.push_trend("bao", -5, source="test") == []
    assert game.push_trend("kou", 0, source="test") == []
    assert (game.state.player.contrib, game.state.player.pushed) == (0, {})
    assert game.state.world.active_pushers == {}


def test_a_hidden_trend_surfaces_with_the_first_whole_point(s1, world):
    s1.scenario.factions[1].goals["bao"] = 1
    game = member(s1, world, "沈浪", "huang")
    msgs = game.push_trend("bao", 3, source="test")
    assert "bao" in game.state.world.revealed
    assert game.state.world.trends["bao"] == 3
    assert any("浮上檯面" in m for m in msgs) and msgs[-1] == "（寶藏 +3）"


# ── 遊歷、操練、事件都走這一條 ────────────────────────────


def test_training_win_goes_through_push(s1, world):
    """遊歷打贏之後：大勢動了、貢獻增加、活躍名單有他。"""
    game = member(s1, world, "沈浪", "huang")
    rules.learn_skill(game.state, s1, "fist")  # 壓倒性的威力，穩贏
    walk_to(game, "lake")
    game.choose("act:train")  # 湖邊的對手是水寇小隊（不屬於任何陣營），train_trend kou:-1，黃巾往自己的目標推 +1
    assert game.state.battles[0].tier in ("大勝", "險勝")
    assert trend(game) == 31
    assert game.state.battles[0].notes == ["（寇亂 +1）"]
    p = game.state.player
    assert p.contrib == 10 and sum(p.contrib_weeks.values()) == 10
    assert list(game.state.world.active_pushers["huang"]) == ["沈浪"]


def test_a_drill_goes_through_push(s1, world):
    s1.squads["thug"].faction = "huang"
    game = member(s1, world, "沈浪", "huang")
    walk_to(game, "lake")
    msgs = game.choose("act:train")
    assert any("操軍擺陣" in m for m in msgs) and "（寇亂 +1）" in msgs
    assert game.state.player.contrib == 10
    assert "沈浪" in game.state.world.active_pushers["huang"]


def test_a_wild_fight_pushes_nothing_so_it_records_nothing(s1, world):
    """探索撞上的野怪打贏不推大勢（_squad_encounter 的 wild）：沒有推動，就沒有貢獻。"""
    game = member(s1, world, "沈浪", "huang")
    rules.learn_skill(game.state, s1, "fist")
    walk_to(game, "lake")
    game._squad_encounter("thug", wild=True)
    assert trend(game) == 30
    assert game.state.player.contrib == 0 and game.state.world.active_pushers == {}


def test_an_event_choice_goes_through_push(s1, world):
    """玩家選的事件效果（Effect.trend）也走推力規則。"""
    s1.events["push_test"] = Event(
        id="push_test", title="市集鬧事", text="兩邊都在拉人。", actions=[],
        choices=[Choice(text="幫黃巾", effect=Effect(trend={"kou": 3})), Choice(text="幫官軍", effect=Effect(trend={"kou": -3}))],
    )
    game = member(s1, world, "沈浪", "huang")
    game.state.pending_event = "push_test"
    msgs = game.choose("choice:0")
    assert "（寇亂 +3）" in msgs
    assert trend(game) == 33
    assert game.state.player.contrib == 30
    game.state.pending_event = "push_test"
    game.choose("choice:1")  # 逆著自己陣營的目標：大勢照動，貢獻不記
    assert trend(game) == 30
    assert game.state.player.contrib == 30


def test_apply_effect_hands_trend_pushes_to_the_callback(s1, world):
    calls = []

    def fake_push(trend_id, delta, *, source):
        calls.append((trend_id, delta, source))
        return ["（推過了）"]

    state = new_game_state(s1, "沈浪")
    msgs = rules.apply_effect(Effect(trend={"kou": 3}), state, s1, world, push=fake_push)
    assert calls == [("kou", 3, "event")]
    assert msgs == ["（推過了）"]
    assert state.world.trends["kou"] == 30  # 交給回呼之後 apply_effect 自己不動大勢


# ── 開關關著：一個字都不變 ────────────────────────────────


def test_push_off_switch_is_plain_change_trend(s1, world):
    """開關關著（beta 那一季）：遊歷打贏、事件效果推大勢的結果與訊息跟改之前一樣，沒有緩衝、沒有上限、沒有貢獻。"""
    s1.config.season_one = False
    s1.events["push_test"] = Event(
        id="push_test", title="市集鬧事", text="兩邊都在拉人。", actions=[],
        choices=[Choice(text="幫黃巾", effect=Effect(trend={"kou": 3}))],
    )
    game = member(s1, world, "沈浪", "huang")
    assert not calendar.season_one_on(game.state.world, s1)
    mark_active(game, "huang", ["甲", "乙", "丙"])  # 開關開著的話會打緩衝
    rules.learn_skill(game.state, s1, "fist")
    walk_to(game, "lake")
    game.choose("act:train")
    assert trend(game) == 31
    assert game.state.battles[0].notes == ["（寇亂 +1）"]
    game.state.pending_event = "push_test"
    msgs = game.choose("choice:0")
    assert "（寇亂 +3）" in msgs and trend(game) == 34
    assert game.push_trend("kou", 50, source="test") == ["（寇亂 +50）"]  # 沒有每日上限
    assert trend(game) == 84
    p = game.state.player
    assert (p.contrib, p.contrib_weeks, p.pushed) == (0, {}, {})
    assert game.state.world.trend_accum == {}
    assert set(game.state.world.active_pushers["huang"]) == {"甲", "乙", "丙"}  # 他自己沒被記進去


def test_old_saves_load_without_the_new_fields(s1, world):
    """舊存檔（角色存檔、賽季存檔）沒有這幾個欄位，照樣讀得進來，預設是空的。"""
    state = new_game_state(s1, "沈浪")
    data = state.model_dump(mode="json")
    for key in ("contrib", "contrib_weeks", "pushed"):
        del data["player"][key]
    p = type(state).model_validate(data).player
    assert (p.contrib, p.contrib_weeks, p.pushed) == (0, {}, {})
    season = state.world.model_dump(mode="json")
    for key in ("trend_accum", "active_pushers"):
        del season[key]
    loaded = type(state.world).model_validate(season)
    assert (loaded.trend_accum, loaded.active_pushers) == ({}, {})


def test_the_new_fields_survive_a_save_and_reload(s1, world):
    """整數的鍵（contrib_weeks）存成 JSON 再讀回來還是整數；賽季整份寫進資料庫再讀回來，累積的小數與活躍名單都在。"""
    state = new_game_state(s1, "沈浪")
    state.player.contrib, state.player.contrib_weeks, state.player.pushed = 40, {3: 40}, {"7:kou": 2.5}
    reloaded = type(state).model_validate_json(state.model_dump_json())
    assert (reloaded.player.contrib, reloaded.player.contrib_weeks, reloaded.player.pushed) == (40, {3: 40}, {"7:kou": 2.5})
    season = state.world
    season.trend_accum, season.active_pushers = {"kou": 0.25}, {"huang": {"沈浪": 123.5}}
    world.save_season(season)
    stored = world.get_season()
    assert (stored.trend_accum, stored.active_pushers) == ({"kou": 0.25}, {"huang": {"沈浪": 123.5}})


def test_add_contribution_records_the_total_and_the_week():
    """貢獻帳只有一份寫法（T4 交接備註第 2 條）：推大勢、挑戰打贏、伏筆、護糧都經過它。"""
    from tianxia.state import PlayerState

    p = PlayerState(name="甲", location="x", stats={}, stamina=0)
    push.add_contribution(p, 3, 10)
    push.add_contribution(p, 3, 5)
    push.add_contribution(p, 4, 0)  # 0 不留下空的一週
    assert p.contrib == 15 and p.contrib_weeks == {3: 15}
