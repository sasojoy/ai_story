"""遊戲日跟著季長縮（企劃者 2026-10-08：「1 天是照現實的一天，但週末期間有縮時的話，就要等比例調整。」）。

一個遊戲日＝現實 24 小時 ×（這一季蓋章的季長 ÷ 14 天）：14 天的季照舊 24 小時，週末 2.5 天的季約 4.3 小時（換成季曆都是
6 個曆日）。以遊戲日為單位的上限——同一位人物一天談幾輪、路上收穫一天幾次、有所感選錯了當天不再悟、地方痕跡一人一天
一次——都在下一個遊戲日的開頭重算；寫給玩家看的「什麼時候再來」照季的那一種時間寫法（calendar.stamp_text）。"""
import math
import random
from unittest import mock

import pytest
from conftest import FixedRandom, install_season_one, walk_to

from tianxia import calendar, companion_agent, howto, rules, sensing
from tianxia.engine import Game
from tianxia.models import InsightScene, SenseMethod
from tianxia.state import WorldState

DAY = 86400
WEEKEND = 2.5
SHORT = DAY * WEEKEND / 14  # 週末那一季的一個遊戲日（世界秒）


def _season(content, days, one=False) -> WorldState:
    season = WorldState(storyline=content.scenario.storylines[0].id)
    season.length_days, season.season_one = days, one
    return season


def _game(content, days, one=False) -> Game:
    """季長 days 天（開季時蓋章）的一局；one 是第一季的規則開著（縮小的時刻表，install_season_one）。"""
    if one:
        install_season_one(content)
    content.config.season_days = days
    content.config.train_event_chance = 0.0
    game = Game.new(content, "沈浪", rng=random.Random(0))
    assert game.state.world.length_days == days and game.state.world.season_one == one
    return game


# ── 換日的長度與時刻（rules.day_seconds、game_day、day_ends、day_ends_text）──────────


def test_a_fourteen_day_season_keeps_the_real_day(content):
    assert rules.day_seconds(content, _season(content, 14)) == DAY


def test_a_weekend_season_scales_the_day_to_its_length(content):
    assert rules.day_seconds(content, _season(content, WEEKEND)) == pytest.approx(DAY * 2.5 / 14)
    assert rules.day_seconds(content, _season(content, 7)) == pytest.approx(DAY / 2)


@pytest.mark.parametrize("days", [14, WEEKEND])
def test_in_season_calendar_terms_a_game_day_is_six_calendar_days(content, days):
    season = _season(content, days)
    assert rules.day_seconds(content, season) * calendar.cal_scale(content, season) == pytest.approx(6 * DAY)


def test_the_day_length_follows_the_stamp_not_the_loaded_config(content):
    """跟季曆同一個章：設定中途換了，正在跑的這一季不動；沒有章的舊季照 14 天。"""
    season = _season(content, WEEKEND)
    content.config.season_days = 14
    assert rules.day_seconds(content, season) == pytest.approx(SHORT)
    content.config.season_days = WEEKEND
    assert rules.day_seconds(content, _season(content, 14)) == DAY
    assert rules.day_seconds(content, _season(content, None)) == DAY


def test_the_day_turns_exactly_at_the_moment_day_ends_names(content):
    season = _season(content, WEEKEND)
    for n in range(1, 60):
        end = rules.day_ends(content, season, (n - 0.5) * SHORT)
        assert end == pytest.approx(n * SHORT)
        assert rules.game_day(content, season, end) == n + 1
        assert rules.game_day(content, season, math.nextafter(end, -math.inf)) == n


def test_the_fourteen_day_season_turns_at_midnight_like_before(content):
    season = _season(content, 14)
    season.time = 3.5 * DAY
    assert rules.game_day(content, season) == rules.current_day(_state_at(content, season)) == 4
    assert rules.day_ends(content, season) == 4 * DAY


def _state_at(content, season):
    from tianxia.state import new_game_state

    state = new_game_state(content, "沈浪")
    state.world = season
    return state


def test_the_moment_is_written_on_the_season_calendar_when_the_switch_is_on(content):
    content.config.season_one = True
    season = _season(content, WEEKEND, one=True)
    season.time = 0.3 * SHORT
    end = rules.day_ends(content, season)
    assert rules.day_ends_text(content, season) == calendar.point_text(calendar.point(end, content, season))
    assert rules.day_ends_text(content, season) == "第 1 週・週日 00:00"  # 6 個曆日之後
    season.time = 1.2 * SHORT
    assert rules.day_ends_text(content, season) == "第 2 週・週六 00:00"


def test_the_moment_uses_the_stamp_format_when_the_switch_is_off(content):
    season = _season(content, 14)
    season.time = 1.3 * DAY
    assert rules.day_ends_text(content, season) == calendar.stamp_text(2 * DAY, content, season) == "第3天 00:00"
    short = _season(content, WEEKEND)  # 開關關著的短季（beta 規則）：一樣照比例換日，寫法照舊
    assert rules.day_ends_text(content, short) == calendar.day_clock_text(rules.day_ends(content, short)) == "第1天 04:17"


# ── 交友：同一位人物一個遊戲日最多談 talk_turns_per_day 輪 ──────────────

FAKE_TURN = companion_agent.CompanionTurn(
    narrative="他點了點頭。", options=["閒聊幾句", "就此告辭"], option_tags=["尋常寒暄", "尋常寒暄"],
)


def _talk_out(game) -> list[str]:
    """跟小鎮的韓鐵（開深度對話、門檻 0、福緣已領）談滿三輪，回最後一輪的訊息。"""
    ch = game.content.characters["mate"]
    ch.deep_interaction, ch.audience_fame = True, 0
    game.state.player.fortune = True
    game.state.player.stamina = 150
    with mock.patch.object(companion_agent, "_generate", return_value=FAKE_TURN):
        game.choose("act:socialize")
        game.choose("talk:0")
        game.choose("talk:0")
        msgs = game.choose("talk:0")
    assert game._talks_left("mate") == 0 and game.state.player.pending_companion is None
    return msgs


@pytest.mark.parametrize("one", [False, True])
def test_talk_turns_come_back_after_one_scaled_day_not_24_hours(content, one):
    game = _game(content, WEEKEND, one=one)
    _talk_out(game)
    w = game.state.world
    end = rules.day_ends(content, w)
    assert end - w.time <= SHORT < DAY
    w.time = math.nextafter(end, -math.inf)
    assert game._talks_left("mate") == 0
    w.time = end
    assert game._talks_left("mate") == content.config.talk_turns_per_day


def test_talk_turns_in_a_fourteen_day_season_still_wait_a_whole_day(content):
    game = _game(content, 14)
    _talk_out(game)
    w = game.state.world
    start = w.time
    w.time = start + SHORT  # 週末的一天過去了，這一季還在同一天
    assert game._talks_left("mate") == 0
    w.time = DAY * (start // DAY + 1)  # 午夜換日
    assert game._talks_left("mate") == content.config.talk_turns_per_day


def test_the_talk_texts_name_the_moment_the_figure_opens_again(content):
    game = _game(content, WEEKEND, one=True)
    msgs = _talk_out(game)
    moment = rules.day_ends_text(content, game.state.world)
    assert moment.startswith("第 1 週・週")
    assert msgs[-1] == f"韓鐵起身送客，改日再敘：要到 {moment} 之後才能再來拜會。"
    with mock.patch("tianxia.engine.pick_event", return_value=None):
        assert game.choose("act:socialize") == [f"韓鐵事忙，要到 {moment} 之後才得空。"]
    assert all("今天" not in m and "明天" not in m and "今日" not in m for m in msgs)


def test_the_audience_button_greys_out_with_the_moment(content):
    game = _game(content, WEEKEND, one=True)
    ch = content.characters["mate"]
    ch.deep_interaction, ch.audience_fame, ch.brush_off = True, 0, ["閒雜人等退下。"]
    game.state.player.fortune = True  # 小鎮只有韓鐵開深度對話：選單上直接列「求見韓鐵」
    game.state.player.talks_today["mate"] = [rules.game_day(content, game.state.world), content.config.talk_turns_per_day]
    option = next(o for o in game.options() if o.id == "call:mate")
    moment = rules.day_ends_text(content, game.state.world)
    assert (option.label, option.enabled) == (f"求見韓鐵（已經談滿 3 輪，{moment} 之後再來）", False)


def test_the_audience_list_names_the_moment_and_drops_today(content):
    game = _game(content, WEEKEND, one=True)
    for cid in ("mate", "scholar"):
        content.characters[cid].deep_interaction = True
        content.characters[cid].audience_fame = 0
    game.state.player.fortune = True
    game.choose("act:call")
    moment = rules.day_ends_text(content, game.state.world)
    intro = game._audience_intro()
    assert f"到 {moment} 重新算起" in intro and "今天" not in intro and "明天" not in intro
    labels = {o.id: o.label for o in game.options()}
    assert labels["call:mate"].endswith("還能談 3/3 輪）") and "今天" not in labels["call:mate"]
    game.state.player.talks_today["mate"] = [rules.game_day(content, game.state.world), 3]
    labels = {o.id: o.label for o in game.options()}
    assert labels["call:mate"] == f"韓鐵（已經談滿 3 輪，{moment} 之後再來）"


def test_old_talk_records_keyed_by_the_old_day_number_read_as_an_earlier_day(content):
    """舊存檔的帳記的是 24 小時一天的號碼：週末那一季裡它只可能跟同一個遊戲日撞號（一開季那幾個小時）、或比現在的號碼小，
    所以頂多提早重算一次，不會擋人。"""
    game = _game(content, WEEKEND)
    w = game.state.world
    w.time = 30 * 3600  # 舊算法第 2 天、新算法第 8 天
    game.state.player.talks_today["mate"] = [int(w.time // DAY) + 1, 3]
    assert game._talks_left("mate") == 3


# ── 路上收穫：每個遊戲日各前 road_reward_daily_cap 次 ────────────────


def test_road_gains_come_back_after_one_scaled_day(content):
    game = _game(content, WEEKEND)
    content.config.road_reward_daily_cap = 1
    game._count_road_reward("task")
    w = game.state.world
    assert not game._road_reward_due("task")
    end = rules.day_ends(content, w)
    w.time = math.nextafter(end, -math.inf)
    assert not game._road_reward_due("task")
    w.time = end
    assert game._road_reward_due("task")


def test_road_gains_in_a_fourteen_day_season_still_wait_a_whole_day(content):
    game = _game(content, 14)
    content.config.road_reward_daily_cap = 1
    game._count_road_reward("task")
    w = game.state.world
    w.time += SHORT
    assert not game._road_reward_due("task")
    w.time = DAY
    assert game._road_reward_due("task")


def test_the_capped_road_texts_name_the_moment(content):
    game = _game(content, WEEKEND, one=True)
    content.config.road_reward_daily_cap = 1
    game.choose("move:lake")
    game.choose("road:think")
    moment = rules.day_ends_text(content, game.state.world)
    gather = next(o for o in game.options() if o.id == "road:gather")
    assert gather.label == f"路邊採集（收穫拿滿了，{moment} 之後才有）"
    game.rng = FixedRandom(0.1)
    assert game.choose("road:gather") == [f"你留心路邊，這陣子已經撿夠了，沒再去翻（{moment} 之後再說）。"]
    walk_to(game, "lake")
    game.choose("move:town")
    assert game.choose("road:think") == [f"你邊走邊想，這陣子想得夠多了，沒有新的心得（{moment} 之後才會再有）。"]


def test_a_road_sight_counts_toward_the_scaled_day_of_its_arrival(content):
    """下線補算跨過換日：第 2 個遊戲日結束前兩分鐘抵達的那一站，收穫算在抵達那一個遊戲日（不是補算的那一刻、也不是 24 小時的第 1 天）。"""
    game = _game(content, WEEKEND)
    content.config.road_sight_chance = 1.0
    p = game.state.player
    p.recent_sights = ["sight_wind", "sight_north_peddler"]  # 只剩烏鴉（心得 +1）
    end = rules.day_ends(content, game.state.world, 1.5 * SHORT)
    game.advance(end - 300 - game.state.world.time)
    game.choose("move:lake")  # 走三分鐘，換日前兩分鐘抵達
    game.advance(600)  # 換日之後才補算
    assert p.road_rewards_today == {"sight": [2, 1]}


def test_road_sight_gains_come_back_on_the_next_scaled_day(content):
    game = _game(content, WEEKEND)
    content.config.road_sight_chance = 1.0
    content.config.road_reward_daily_cap = 1
    p = game.state.player
    p.recent_sights = ["sight_wind", "sight_north_peddler"]
    walk_to(game, "lake")
    assert p.road_rewards_today == {"sight": [1, 1]}
    game.state.world.time = rules.day_ends(content, game.state.world)
    p.recent_sights = ["sight_wind", "sight_north_peddler"]
    xinde = p.stats["xinde"]
    walk_to(game, "town")
    assert p.stats["xinde"] == xinde + 1 and p.road_rewards_today == {"sight": [2, 1]}


# ── 有所感：選錯了做法，這一處到換日之前不再悟 ──────────────────

SCENE = InsightScene(
    id="lake_wind", title="湖風", text="風吹過湖面，停過腳的{痕跡}。", tags=["湖畔"], hints=["柔"],
    methods=[SenseMethod(attribute=a, text=t) for a, t in (("柔", "看水"), ("剛", "打水"), ("快", "追風"), ("慢", "靜坐"))],
)


def _lake(content, days, one=False) -> Game:
    game = _game(content, days, one=one)
    content.insight_scenes = {SCENE.id: SCENE}
    game.rng = FixedRandom(0.0)
    game.state.player.location = "lake"
    return game


def _miss(game) -> list[str]:
    """在湖邊有所感、選了錯的做法（湖邊只悟得到柔與快）。"""
    sensing.start(game.state, game.content, SCENE, random.Random(0))
    s = game.state.player.sensing
    index = [SCENE.methods[j].attribute for j in s.order].index("剛")
    return game.choose(f"sense:{index}")


@pytest.mark.parametrize("one", [False, True])
def test_a_wrong_method_blocks_insight_only_until_the_scaled_day_ends(content, one):
    game = _lake(content, WEEKEND, one=one)
    _miss(game)
    lake, w = content.locations["lake"], game.state.world
    assert sensing.missed_today(game.state, content, lake) and not game._explore_can("insight", lake)
    end = rules.day_ends(content, w)
    w.time = math.nextafter(end, -math.inf)
    assert sensing.missed_today(game.state, content, lake)
    w.time = end
    assert not sensing.missed_today(game.state, content, lake) and game._explore_can("insight", lake)


def test_a_wrong_method_in_a_fourteen_day_season_still_blocks_the_whole_day(content):
    game = _lake(content, 14)
    _miss(game)
    lake, w = content.locations["lake"], game.state.world
    w.time += SHORT
    assert sensing.missed_today(game.state, content, lake)
    w.time = DAY
    assert not sensing.missed_today(game.state, content, lake)


def test_the_insight_texts_name_the_moment_on_the_season_calendar(content):
    game = _lake(content, WEEKEND, one=True)
    sensing.start(game.state, content, SCENE, random.Random(0))
    moment = rules.day_ends_text(content, game.state.world)
    assert moment == calendar.point_text(calendar.point(rules.day_ends(content, game.state.world), content, game.state.world))
    card = sensing.scene_text(game.state, content)
    assert f"> 選錯了做法，這裡要到 {moment} 之後才悟得出。" in card and "今天" not in card
    game.state.player.sensing = None
    msgs = _miss(game)
    assert msgs[-1] == f"心浮氣躁，什麼也沒抓住。要到 {moment} 之後，這裡才悟得出東西。"
    note = game.action_notes(["act:explore"])["act:explore"]
    assert note.endswith(f"；這裡要到 {moment} 之後才悟得出") and "今天" not in note


def test_the_insight_texts_use_the_stamp_format_when_the_switch_is_off(content):
    game = _lake(content, 14)
    game.state.world.time = 5000.0
    sensing.start(game.state, content, SCENE, random.Random(0))
    assert "> 選錯了做法，這裡要到 第2天 00:00 之後才悟得出。" in sensing.scene_text(game.state, content)


def test_the_explore_note_only_mentions_the_block_while_it_lasts(content):
    game = _lake(content, WEEKEND, one=True)
    note = game.action_notes(["act:explore"])["act:explore"]
    assert "悟得出" not in note
    _miss(game)
    game.state.world.time = rules.day_ends(content, game.state.world)
    assert "悟得出" not in game.action_notes(["act:explore"])["act:explore"]


# ── 地方痕跡：同一個人對同一個痕跡，一個遊戲日只算一次 ──────────────


def test_a_mark_counts_again_after_one_scaled_day(content):
    game = _game(content, WEEKEND)
    s, w = game.state, game.state.world
    rules.add_marks({"town:棚屋": 2}, s, content)
    rules.add_marks({"town:棚屋": 2}, s, content)
    assert w.marks["town:棚屋"] == 2
    w.time = math.nextafter(rules.day_ends(content, w), -math.inf)
    rules.add_marks({"town:棚屋": 2}, s, content)
    assert w.marks["town:棚屋"] == 2
    w.time = rules.day_ends(content, w)
    rules.add_marks({"town:棚屋": 1}, s, content)
    assert w.marks["town:棚屋"] == 3


def test_a_mark_in_a_fourteen_day_season_still_counts_once_a_whole_day(content):
    game = _game(content, 14)
    s, w = game.state, game.state.world
    rules.add_marks({"town:棚屋": 2}, s, content)
    w.time += SHORT
    rules.add_marks({"town:棚屋": 2}, s, content)
    assert w.marks["town:棚屋"] == 2
    w.time = DAY
    rules.add_marks({"town:棚屋": 1}, s, content)
    assert w.marks["town:棚屋"] == 3


# ── 玩法說明 ─────────────────────────────────────────


def test_the_howto_page_writes_the_weekend_day_in_real_time(content):
    game = _game(content, WEEKEND, one=True)
    page = howto.page(content, game.state.world, recruitable=False)
    assert "同一位人物每 4 小時 17 分（現實時間）最多 3 輪" in page
    assert "選錯了，那裡要過一陣子才悟得出（選之前卡上就寫著要到什麼時候）" in page
    assert "每天最多" not in page and "今天在那裡" not in page


def test_the_howto_page_keeps_every_day_for_a_fourteen_day_season(content):
    game = _game(content, 14)
    assert "同一位人物每天最多 3 輪" in howto.page(content, game.state.world, recruitable=False)
