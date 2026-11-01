"""戰力（tianxia/might.py）：此刻的戰力乘上兩門槽裡意境的加成（Joy 2026-10-21：「合出來我根本看不懂這是不是好的」）。

10/31 測試自檢 T-08：把 might.now 的 `* (1 + bonus)` 改成 `* (1 - bonus)`，tests/arts、gear、seal 一千九百多條全過——
「意境讓戰力上升」沒有一條測試鎖住。這一檔鎖住它。"""
import pytest
from test_stack_rule import _art, _ins, _wear

from tianxia import arts as arts_mod, might, team


def _bonus(state, content, world, art_id):
    return arts_mod.effect_bonus(content, arts_mod.apply(state, content, world, team.player_art(state, content, world, art_id)))


def test_an_insight_with_an_effect_in_the_slot_raises_the_might(state, content, world):
    art = _wear(state, world, _art("裂石拳", "剛"), "上品", [])
    bare = might.now(state, content, world)
    assert bare > 0 and _bonus(state, content, world, art.id) == 0
    state.player.art_slots[art.id] = [_ins(state, 1, "剛")]
    bonus = _bonus(state, content, world, art.id)
    assert bonus > 0
    worn = might.now(state, content, world)
    assert worn > bare
    assert worn == pytest.approx(bare * (1 + bonus), abs=1)  # 本人那一份的威力不變，只多乘上意境的加成
