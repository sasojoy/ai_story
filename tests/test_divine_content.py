"""正式季第 10 批：每件神器的特色不重複、新神器第一批（正式季整合設計 5.7、5.9）。"""
from __future__ import annotations

import pytest

from conftest import real_content

from tianxia import tactics
from tianxia.content import ContentError, validate

NEW = 12


def _divines(c):
    return [r for r in c.forge_secrets.values() if r.divine]


def test_divine_tactics_are_all_different():
    c = real_content()
    kinds = [r.tactic.kind for r in _divines(c)]
    assert all(r.tactic is not None for r in _divines(c))
    assert len(kinds) == len(set(kinds))  # 用途可以重複、特色不能（5.9）
    assert c.forge_secrets["wd_dark_crystal"].tactic.kind == "shadow"  # 玄晶劍留著虛影
    assert c.forge_secrets["ad_skim_shadow"].tactic.kind != "shadow"  # 掠影衫改寫
    assert all(k in tactics.KINDS for k in kinds)


def test_the_new_batch_is_wave_two():
    c = real_content()
    first = [r for r in _divines(c) if r.wave == 1]
    new = [r for r in _divines(c) if r.wave == 2]
    assert len(first) == 9 and len(new) == NEW
    assert sum(r.slot == "weapon" for r in new) == 8 and sum(r.slot == "armor" for r in new) == 4
    assert {r.kind for r in new if r.slot == "weapon"} == {"劍", "刀", "槍", "棍", "弓弩", "拳腳"}  # 六種兵器都輪得到
    assert all(r.main.tier == 4 and r.aux.tier == 4 for r in new)


def test_same_kind_divines_use_different_pairs():
    c = real_content()
    pairs = [(r.slot, r.kind, r.main.attribute, r.aux.attribute) for r in _divines(c)]
    assert len(pairs) == len(set(pairs))  # 同一種兵器（防具算一種）兩件神器不能是同一對料（主輔照順序）


def test_validation_rejects_a_repeated_divine_tactic():
    c = real_content()
    c.forge_secrets["ad_skim_shadow"].tactic = c.forge_secrets["wd_dark_crystal"].tactic.model_copy(update={"name": "另一個名字"})
    with pytest.raises(ContentError, match="特色不重複"):
        validate(c)


def test_validation_rejects_the_same_pair_for_one_kind():
    c = real_content()
    sword = next(r for r in _divines(c) if r.kind == "劍" and r.wave == 2)
    sword.main, sword.aux = c.forge_secrets["wd_dark_crystal"].main, c.forge_secrets["wd_dark_crystal"].aux
    with pytest.raises(ContentError, match="認同一個組合"):
        validate(c)


def test_validation_wants_a_first_wave():
    c = real_content()
    for r in _divines(c):
        r.wave = 2
    with pytest.raises(ContentError, match="wave 1"):
        validate(c)
