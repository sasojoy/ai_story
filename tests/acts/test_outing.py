"""走一趟（tianxia/outing.py；企劃者 2026-10-29～30）：探索一次走一、三、五段，每一段是現行的一次探索；
要選的事停下、選完接著走；打輸、氣血見底回頭，沒走的段不扣體力；段數越多稀有的越容易來（倍數 1／1.2／1.5，畫面不寫）。
用正式內容（season21），整個檔標 slow。"""
from __future__ import annotations

import random
from contextlib import contextmanager
from unittest import mock

import pytest
from jianfa_kit import jianfa_game, ready

from tianxia import explore_modes, explore_one, outing, team
from tianxia.encounter import EncounterResult

pytestmark = pytest.mark.slow

MAT, EVT, ENC = explore_one.MATERIAL, explore_one.EVENT, explore_one.ENCOUNTER


@contextmanager
def _draws(*kinds: str, tier: str = "大勝"):
    """每一段抽到什麼照 kinds 的順序；遭遇照 tier 打。"""
    seq = iter(kinds)
    with mock.patch.object(explore_one, "draw", side_effect=lambda *a, **k: next(seq)), \
         mock.patch.object(team, "fight", return_value=EncounterResult(tier=tier, margin=50, our_power=200, difficulty=40)):
        yield


def _game(**flags):
    game = ready(jianfa_game(**flags), side="guan", loc="yingshui")
    game.state.player.stamina = 100.0
    return game


def _settle_event(game) -> None:
    option = next(o for o in game.options(odds=False) if o.id.startswith("choice:") and o.enabled)
    game.choose(option.id)


def test_three_segments_walk_three_explores():
    game = _game()
    p = game.state.player
    journal = len(game.state.journal)
    with _draws(MAT, MAT, MAT):
        assert game.outing_go(3) == []
    trip = p.outing
    assert (trip.total, trip.done, trip.end) == (3, 3, outing.DONE)
    assert [b.kind for b in trip.beats] == [MAT] * 3
    assert all(b.text and not b.stop for b in trip.beats)
    assert p.stamina == 100 - 3 * game.content.config.jianfa.explore_stamina  # 一段一次探索的體力
    assert len(game.state.journal) - journal == 3  # 每一段各寫一則江湖紀錄


def test_an_event_stops_the_walk_until_it_is_settled():
    game = _game()
    p = game.state.player
    with _draws(MAT, EVT, MAT):
        game.outing_go(3)
        trip = p.outing
        assert (trip.done, trip.end) == (2, "")
        assert trip.beats[-1].stop and game.state.pending_event is not None
        assert game.outing_view()["trip"]["can_go"] is False  # 事情還沒選
        _settle_event(game)
        assert game.outing_view()["trip"]["can_go"] is True
        game.outing_go()
    assert (trip.done, trip.end) == (3, outing.DONE)


def test_the_last_segment_stopping_closes_after_the_choice():
    game = _game()
    with _draws(EVT):
        game.outing_go(1)
    trip = game.state.player.outing
    assert (trip.done, trip.end) == (1, "")
    _settle_event(game)
    game.outing_go()
    assert trip.end == outing.DONE


def test_losing_a_fight_turns_back_and_saves_the_stamina():
    game = _game()
    p = game.state.player
    with _draws(ENC, MAT, MAT, tier="落敗"):
        game.outing_go(3)
    trip = p.outing
    assert (trip.done, trip.end) == (1, outing.LOST)
    assert trip.beats[0].kind == ENC and trip.beats[0].won is False
    assert p.stamina == 100 - game.content.config.jianfa.explore_stamina  # 只扣走了的那一段


def test_low_hp_turns_back():
    game = _game()
    with _draws(MAT, MAT, MAT), mock.patch.object(team, "member_neili", return_value=(10.0, 100.0)):
        game.outing_go(3)
    trip = game.state.player.outing
    assert (trip.done, trip.end) == (1, outing.HURT)


def test_refusals():
    game = _game()
    p = game.state.player
    assert game.outing_go(2) == ["（此刻無法這麼做。）"]  # 不是一、三、五段
    p.stamina = 10.0
    assert game.outing_go(5) == ["（體力不夠走這麼多段。）"]
    assert p.outing is None
    assert game.outing_go() == ["（此刻無法這麼做。）"]  # 沒有在路上的那一趟


def test_rare_boost_follows_the_trip_length():
    game = _game()
    s, c = game.state, game.content
    assert outing.rare_boost(s, c) == 1.0
    seen = []
    with _draws(MAT, MAT, MAT, MAT, MAT), mock.patch.object(
            explore_modes, "gather_finds", side_effect=lambda *a, boost=1.0, **k: seen.append(boost) or []):
        game.outing_go(5)
    assert seen == [1.5] * 5
    assert outing.rare_boost(s, c) == 1.0  # 走完了，不在路上
    assert c.config.jianfa.outing_rare == {"1": 1.0, "3": 1.2, "5": 1.5}


def test_gather_boost_raises_only_the_second_tier():
    game = _game()
    c = game.content
    loc = next(l for l in c.locations.values()
               if l.danger >= 2 and l.materials and not explore_modes.is_town(c, l))  # 城外、危險度二以上才擲二階
    chance = c.config.explore_modes.second_tier[loc.danger]

    class Fixed(random.Random):
        def random(self):
            return chance * 1.2  # 不加成擲不中，乘 1.5 擲得中

    plain = explore_modes.gather_finds(c, loc, Fixed(), sure=True)
    boosted = explore_modes.gather_finds(c, loc, Fixed(), sure=True, boost=1.5)
    assert len(boosted) == len(plain) + 1


def test_view_and_switch():
    game = _game()
    view = game.outing_view()
    assert [x["n"] for x in view["picker"]] == [1, 3, 5]
    assert view["note"] == outing.MORE_IS_RARER and "倍" not in view["note"]
    assert view["trip"] is None
    off = _game(outing=False)
    assert off.outing_view() is None
    assert off.outing_go(3) == ["（此刻無法這麼做。）"]
