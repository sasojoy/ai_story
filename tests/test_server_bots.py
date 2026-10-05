import random
from collections import Counter

from tianxia.models import Config
from tianxia import server_bots
from tianxia.server_bots import (
    DAY, GIVEN, SURNAMES, TZ_OFFSET, act_chance, active, attends_battle, is_online, make_name,
    pick_personality, reserved_names, schedule, strength,
)
from tianxia.state import BotProfile


def _bot(personality="普通", seed=7, faction="guan", season_number=1):
    return BotProfile(personality=personality, seed=seed, faction=faction, season_number=season_number)


def _at(minute_of_day: int, day: int = 20000) -> float:
    """台灣時間第 day 天的第 minute_of_day 分鐘，換成現實時間戳。"""
    return day * DAY + minute_of_day * 60 - TZ_OFFSET


def test_reserved_names_cover_famous_people_figures_in_the_content_and_admins(content):
    content.config.admins = ["掌門"]
    reserved = reserved_names(content)
    assert "曹操" in reserved and "張角" in reserved  # 三國名人
    assert all(ch.name in reserved for ch in content.characters.values())  # 遊戲裡的人物，跟著內容走
    assert "掌門" in reserved


def test_names_look_like_han_names_and_avoid_taken_ones():
    first = make_name(random.Random(1), set())
    assert 2 <= len(first) <= 3 and first[0] in SURNAMES and all(ch in GIVEN for ch in first[1:])
    assert make_name(random.Random(1), {first}) != first


class _Scripted(random.Random):
    """照劇本抽字：random() 永遠抽到單名，choice() 依序拿 picks 裡的字（先名、後姓）。"""

    def __init__(self, picks):
        super().__init__(0)
        self.picks = list(picks)

    def random(self):
        return 0.0

    def choice(self, seq):
        pick = self.picks.pop(0)
        assert pick in seq
        return pick


def test_names_never_match_a_famous_three_kingdoms_figure():
    """字庫組得出趙雲、周瑜、馬超這種名人；抽到了就重抽，假人不能頂著名人的名號。"""
    assert make_name(_Scripted(["雲", "趙", "雲", "陳"]), set()) == "陳雲"
    assert make_name(_Scripted(["瑜", "周", "超", "馬", "瑜", "林"]), set()) == "林瑜"
    assert {"趙雲", "周瑜", "馬超"} <= server_bots.FAMOUS_NAMES


def test_personalities_follow_the_twenty_fifty_thirty_split():
    rng = random.Random(0)
    counts = Counter(pick_personality(rng) for _ in range(10000))
    assert abs(counts["積極"] / 10000 - 0.2) < 0.03
    assert abs(counts["普通"] / 10000 - 0.5) < 0.03
    assert abs(counts["懶散"] / 10000 - 0.3) < 0.03


def test_the_same_bot_always_has_the_same_schedule_and_it_fits_its_temper():
    eager = _bot("積極", seed=11)
    assert schedule(eager) == schedule(_bot("積極", seed=11))
    total = sum(end - start for start, end in schedule(eager))
    assert 240 <= total <= 300
    for start, end in schedule(eager):
        assert 11 * 60 + 30 <= start < end <= 24 * 60


def test_each_temper_keeps_its_daily_total_and_its_windows_inside_waking_hours():
    ranges = {"積極": (240, 300), "普通": (120, 180), "懶散": (50, 70)}
    window_counts = Counter()
    for personality, (low, high) in ranges.items():
        for seed in range(200):
            spans = schedule(_bot(personality, seed=seed))
            assert low <= sum(end - start for start, end in spans) <= high
            for start, end in spans:
                assert 11 * 60 + 30 <= start < end <= 24 * 60
            window_counts[personality, len(spans)] += 1
    assert window_counts["普通", 1] > 0 and window_counts["普通", 2] > 0  # 一到兩段都有


def test_a_bot_is_online_only_inside_its_windows():
    eager = _bot("積極", seed=11)
    start, end = schedule(eager)[0]
    assert is_online(eager, _at(start))
    assert not is_online(eager, _at(4 * 60))  # 凌晨四點


def test_a_lazy_bot_skips_about_half_of_the_days():
    lazy = _bot("懶散", seed=5)
    start, _ = schedule(lazy)[0]
    online_days = sum(is_online(lazy, _at(start, day)) for day in range(20000, 20200))
    assert 70 <= online_days <= 130


def test_turning_up_for_a_battle_is_reproducible_and_follows_the_temper():
    eager = _bot("積極", seed=3)
    assert attends_battle(eager, 123.0) == attends_battle(eager, 123.0)
    shows = sum(attends_battle(eager, float(key)) for key in range(1000))
    assert 850 <= shows <= 950


def test_act_chance_and_strength():
    config = Config(bot_tick_seconds=20, bot_strength=0.9)
    assert act_chance(_bot("普通"), config) == 20 / 120
    assert strength(config, _bot("積極")) == 1.0
    assert strength(Config(bot_strength=0.1), _bot("懶散")) == 0.0
    assert strength(Config(bot_strength=0.6), _bot("普通")) == 0.6


def test_a_bot_is_active_only_when_woken_for_this_season():
    assert active(_bot(faction="guan", season_number=2), 2)
    assert not active(_bot(faction="guan", season_number=1), 2)
    assert not active(_bot(faction=None, season_number=2), 2)
