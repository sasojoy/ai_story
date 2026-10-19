"""失神把你挑的招換掉時，那一句話要寫出「挑的是什麼、變成了什麼」。

Joy 2026-10-19 在擂台上：「明明我選強攻，為什麼出來變固守，如果是對方武學影響，對話中也沒有描述清楚」。
實機那一場（司馬 對 青冥的分身，第 3 回合）回合開頭寫的是「你固守」，而他挑的是強攻；中間唯一能解釋的那一句
只寫「〔失神〕你心神一亂，一招打在自己身上」——招被換掉這件事一個字都沒提。
"""
from __future__ import annotations

import random

import pytest

from tianxia import tactics


def dazed(move: str, *, self_hit: float, seed: int) -> tuple[str | None, bool, list[str]]:
    """做一個身上帶著「失神」的 _Fight，照玩家挑的招走 _forced。"""
    tuning = tactics.TacticTuning(self_hit=self_hit)
    side = tactics.BoutSide(ctx=tactics.Ctx(foe="青冥"), status=tactics.Status(name="司馬"))
    side.status.states["失神"] = 1
    foe = tactics.BoutSide(ctx=tactics.Ctx(foe="司馬"), status=tactics.Status(name="青冥"))
    bout = tactics.Bout(a=side, b=foe, pvp=True)
    fight, _ = tactics._fights(bout, tuning, random.Random(seed), 1.0, 1.0)
    fight.lines = []
    picked, hit = tactics._forced(fight, move, False, None, random.Random(seed), tuning)
    return picked, hit, fight.lines


@pytest.mark.parametrize("seed", range(12))
def test_the_line_always_names_the_move_you_picked(seed):
    """不管有沒有打到自己，都要看得出你挑的那一招出不來了。"""
    picked, hit, lines = dazed("強攻", self_hit=1.0 if seed % 2 else 0.0, seed=seed)
    assert len(lines) == 1
    line = lines[0]
    assert "失神" in line
    if picked != "強攻":
        assert f"使不出強攻，亂出了{picked}" in line, line
    else:
        assert "強攻出得七零八落" in line, line


def test_hitting_yourself_no_longer_hides_the_swap():
    """舊的寫法打到自己時只寫「一招打在自己身上」，招被換掉完全沒提——就是 Joy 碰到的那一回合。"""
    seed = next(s for s in range(50) if dazed("強攻", self_hit=1.0, seed=s)[0] == "固守")
    picked, hit, lines = dazed("強攻", self_hit=1.0, seed=seed)
    assert (picked, hit) == ("固守", True)
    assert "使不出強攻，亂出了固守" in lines[0] and "打在自己身上" in lines[0]


def test_it_does_not_say_it_swapped_when_it_rolled_the_same_move():
    """亂出來剛好就是你挑的那一招時，不能寫「使不出強攻，亂出了強攻」。"""
    seed = next(s for s in range(50) if dazed("強攻", self_hit=0.0, seed=s)[0] == "強攻")
    _, _, lines = dazed("強攻", self_hit=0.0, seed=seed)
    assert "使不出強攻，亂出了強攻" not in lines[0]
    assert "強攻出得七零八落" in lines[0]


def test_the_dice_are_untouched():
    """只改字：擲骰的順序與次數不能動（招照舊是 rng.choice(MOVES)、打到自己照舊是下一個 rng.random()）。"""
    tuning = tactics.TacticTuning(self_hit=0.4)
    for seed in range(8):
        expect = random.Random(seed)
        move = expect.choice(tactics.MOVES)
        hit = expect.random() < tuning.self_hit
        picked, got, _ = dazed("強攻", self_hit=0.4, seed=seed)
        assert (picked, got) == (move, hit)
