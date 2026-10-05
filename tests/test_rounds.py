"""回合演出（武學與成長設計 8.2、計畫三 Task 1）：勝負照 encounter 一次算好，rounds 只把結果拆成 3～5 回合的數字。"""
import random

import pytest

from tianxia import rounds

US = [rounds.Fighter(name="沈浪", art="旋風腿", attribute="快")]
THUG = rounds.Foe(name="山賊", attribute="剛", agility=6.0)


def test_split_adds_up_exactly():
    rng = random.Random(1)
    for total, parts in ((0, 3), (7, 4), (155, 5)):
        shares = rounds.split(total, parts, rng)
        assert len(shares) == parts and sum(shares) == total and min(shares) >= 0


@pytest.mark.parametrize(("tier", "low", "high", "left"), [
    ("大勝", 3, 3, 0), ("險勝", 4, 4, 0), ("僵持", 5, 5, 50), ("落敗", 3, 4, 80),
])
def test_the_rounds_add_up_to_the_result(tier, low, high, left):
    played = rounds.play(tier, US, THUG, our_agility=5.0, hp_lost=96, rng=random.Random(2))
    assert low <= len(played) <= high
    ours = sum(b.amount for r in played for b in r.beats if b.side == "ours")
    theirs = sum(b.amount for r in played for b in r.beats if b.side == "theirs")
    assert ours == 100 - left and theirs == 96


def test_the_quicker_side_strikes_first():
    slow = rounds.play("大勝", US, THUG, our_agility=5.0, hp_lost=10, rng=random.Random(0))
    quick = rounds.play("大勝", US, THUG, our_agility=7.0, hp_lost=10, rng=random.Random(0))
    assert slow[0].beats[0].side == "theirs" and quick[0].beats[0].side == "ours"


def test_foe_agility_grows_with_difficulty():
    assert rounds.foe_agility(0) == 5.0 and rounds.foe_agility(100) == 10.0


def test_a_fight_with_no_toll_gives_their_blows_no_amount():
    """劇情戰不扣氣血（G5）：hp_lost 是 None，對手的出手沒有數字（句子後面不接「你氣血 -N」也不接「被你閃開了」）；
    我方的氣勢照樣拆好。"""
    played = rounds.play("落敗", US, THUG, our_agility=5.0, hp_lost=None, rng=random.Random(3))
    assert all(b.amount is None for r in played for b in r.beats if b.side == "theirs")
    assert sum(b.amount for r in played for b in r.beats if b.side == "ours") == 20


def test_fighters_with_an_art_take_turns_and_a_bare_team_sends_the_player():
    """有武學的人輪流出手（本人在前）；沒學武學的同伴不出手。整隊都沒有武學就本人空手上。"""
    team = [
        rounds.Fighter(name="沈浪", art="旋風腿", attribute="快"),
        rounds.Fighter(name="韓鐵", art=None, attribute=None),
        rounds.Fighter(name="琴師", art="流雲劍", attribute="柔"),
    ]
    played = rounds.play("險勝", team, THUG, our_agility=9.0, hp_lost=0, rng=random.Random(0))
    actors = [b.actor for r in played for b in r.beats if b.side == "ours"]
    assert actors == ["沈浪", "琴師", "沈浪", "琴師"]
    bare = [rounds.Fighter(name="沈浪", art=None, attribute=None), rounds.Fighter(name="韓鐵", art=None, attribute=None)]
    played = rounds.play("大勝", bare, THUG, our_agility=9.0, hp_lost=0, rng=random.Random(0))
    assert {(b.actor, b.art) for r in played for b in r.beats if b.side == "ours"} == {("沈浪", None)}


def test_the_same_seed_plays_the_same_rounds():
    """同一個種子演出同一場（引擎用名號＋戰報流水號當種子，同一筆戰報每次都長一樣，G3）。"""
    first = rounds.play("落敗", US, THUG, our_agility=5.0, hp_lost=77, rng=random.Random("沈浪|3"))
    again = rounds.play("落敗", US, THUG, our_agility=5.0, hp_lost=77, rng=random.Random("沈浪|3"))
    assert first == again
