"""新手福利從自己加入那天起算（第一季設計第十四節；賽季計畫 Task 1）。"""
import json
import random

import pytest

from conftest import install_season_one
from tianxia import calendar, roster, rules
from tianxia.engine import Game
from tianxia.state import GameState, new_game_state

DAY = 86400


def _late_joiner(content, world, hours: float = 3.0) -> Game:
    """季開了 hours 個現實鐘頭都沒人補算之後才建的角色，建好之後第一次同步。"""
    first = Game.new(content, "先來", rng=random.Random(0), world=world)
    first.sync(1000.0)  # 記下時鐘
    late = Game.new(content, "遲來", rng=random.Random(1), world=world)
    late.sync(1000.0 + hours * 3600)
    return late


def test_the_join_time_is_stamped_at_the_first_sync_after_the_catch_up(content, world):
    """建角那一刻季已經三個鐘頭沒人補算：先不蓋，第一次同步補算完才蓋（不然福利白白被吃掉三個鐘頭）；蓋過就不再動。"""
    install_season_one(content)
    first = Game.new(content, "先來", rng=random.Random(0), world=world)
    first.sync(1000.0)
    late = Game.new(content, "遲來", rng=random.Random(1), world=world)
    assert late.state.player.joined_at is None
    late.sync(1000.0 + 3 * 3600)
    joined = late.state.player.joined_at
    assert joined == pytest.approx(3 * 3600 * content.config.time_scale) == pytest.approx(world.get_season().time)
    late.sync(1000.0 + 5 * 3600)
    assert late.state.player.joined_at == joined


def test_advance_also_stamps_the_join_before_moving_time(content, world):
    """沒同步過就直接快轉（測試與整季機器人）：推進之前先蓋，蓋的是推進前的季時間。"""
    install_season_one(content)
    game = Game.new(content, "快轉", rng=random.Random(0), world=world)
    game.advance(600)
    assert game.state.player.joined_at == 0.0


def test_newbie_regen_doubles_for_three_calendar_days_from_joining(content, world):
    """氣血回復加倍：從自己加入那一刻起的季曆 3 天（2.5 天的季，季曆 3 天是現實約 2 小時），之後恢復一倍。"""
    install_season_one(content)
    late = _late_joiner(content, world)
    p = late.state.player
    day = DAY / calendar.cal_scale(content, late.state.world)
    gained = []
    for after in (3 * day - 1, 3 * day + 1):
        late.state.world.time = p.joined_at + after
        assert roster.newbie(late.state, content) is (after < 3 * day)
        p.member.neili = 10.0
        late._advance_player_local(600)
        gained.append(p.member.neili - 10.0)
    assert gained[0] == pytest.approx(2 * gained[1])


def test_the_fortune_counts_calendar_days_from_joining(content, world):
    """新立門戶福緣：自己的第 2 個季曆日起交友必定先觸發，第 7 個季曆日結束還沒發生就直接送上門；發生過就都不算。"""
    install_season_one(content)
    late = _late_joiner(content, world)
    s, p = late.state, late.state.player
    day = DAY / calendar.cal_scale(content, s.world)
    s.world.time = p.joined_at + day - 1
    assert not roster.fortune_due(s, content)
    s.world.time = p.joined_at + day + 1
    assert roster.fortune_due(s, content) and not roster.fortune_overdue(s, content)
    s.world.time = p.joined_at + 7 * day + 1
    assert roster.fortune_overdue(s, content)
    p.fortune = True
    assert not roster.fortune_due(s, content) and not roster.fortune_overdue(s, content)


def test_a_new_season_stamps_the_join_again(content, world):
    """換季重來的角色是新加入這一季的人：第一次同步補算完新的一季才重新蓋。"""
    install_season_one(content)
    late = _late_joiner(content, world)
    assert late.state.player.joined_at > 0
    world.mutate_season(lambda s: setattr(s, "ended", True))
    assert world.next_season(content, 1000.0 + 4 * 3600)
    late.sync(1000.0 + 4 * 3600 + 600)
    p = late.state.player
    assert p.season_number == 2
    assert p.joined_at == pytest.approx(600 * content.config.time_scale)


def test_an_old_save_without_a_join_time_counts_from_the_season_start(content, world):
    """舊存檔沒有 joined_at：讀成 0.0，等於從季初算，跟以前一樣；之後同步也不會被當成剛加入而重蓋。"""
    install_season_one(content)
    data = json.loads(new_game_state(content, "老手").model_dump_json())
    del data["player"]["joined_at"]
    old = GameState.model_validate(data)
    assert old.player.joined_at == 0.0
    game = Game(content, old, rng=random.Random(0), world=world)
    game.sync(1000.0)
    game.sync(1000.0 + 3600)
    assert game.state.player.joined_at == 0.0


def test_with_the_switch_off_the_perks_still_follow_the_season_clock(content, world):
    """開關關著（beta 那一季）：加入時間照樣蓋，但新手福利照舊從季初起算、用世界的天數，一點都不變。"""
    content.config.newbie_days = 1
    late = _late_joiner(content, world, hours=36)  # 季的第 1.5 天才加入
    s = late.state
    assert not rules.season_one(content, s.world) and s.player.joined_at > 0
    assert not roster.newbie(s, content)  # 從季初算：已經過了 1 天
    assert roster.fortune_due(s, content)  # 季的第 2 天


def test_the_perks_count_with_the_length_the_season_was_stamped_with(content, world):
    """世界的天數看季曆，季曆照這一季開季時蓋的章（calendar.cal_scale(content, season)）算：開季之後設定的季長換了，
    這一季的新手福利照舊，不會跟著新設定走（週末設定開開關關、換季之間改季長都不能讓跑著的那一季亂掉）。"""
    install_season_one(content)
    late = _late_joiner(content, world)
    s = late.state
    s.world.time = s.player.joined_at + 100.0
    before = roster.since_join(s, content)
    assert before == pytest.approx(100.0 * calendar.cal_scale(content, s.world))
    content.config.season_days = 10.0  # 開季之後設定換了
    assert roster.since_join(s, content) == before
    assert roster.newbie(s, content) and not roster.fortune_due(s, content)
