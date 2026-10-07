"""第一季正式版・丙二：黃巾的第 3、4 階奇遇（計畫 2026-10-06-第一季正式版-丙二）。

用真實內容（content/）：fixture real、on 在 tests/conftest.py（每個測試拿 real_content 的一份複本，開關在 on 裡才打開）。
週末設定（人數上限 2）：帶糧 2 份換算成 1。"""
from __future__ import annotations

import random

import pytest
from pydantic import ValidationError

from tianxia import foreshadow, materials, rules
from tianxia.content import ContentError, validate
from tianxia.engine import Game
from tianxia.models import Condition, Effect
from tianxia.state import PlayerState, TimelineResult


def _game(content, name="甲", faction="huang", at=None, rank=0):
    game = Game.new(content, name, rng=random.Random(0))
    game.client = None  # 沒有任何地方會叫模型
    p = game.state.player
    p.faction, p.rank = faction, rank
    if at is not None:
        p.location = at
    return game


def _grain(game, n):
    """給 n 份糧草：慢屬性素材從低階的開始算（materials.grain_of 怎麼算就怎麼給）。"""
    slow = sorted((m for m in game.content.materials.values() if m.attribute == "慢"), key=lambda m: m.tier)[0]
    game.state.player.materials = {slow.id: n}
    assert materials.grain_of(game.state, game.content) >= n


# ── Task 1：帶糧、捐糧、給片段、記殘片 ─────────────────────────


def test_defaults_so_old_saves_load():
    assert PlayerState(name="甲", location="x", stats={}, stamina=0).runic_pieces == 0
    assert (Condition().grain_min, Effect().donate_grain, Effect().fs_fragments, Effect().runic) == (0, {}, [], 0)


def test_grain_choice_needs_enough_grain(on):
    game = _game(on)
    cond = Condition(grain_min=2)  # 週末換算成 1
    assert not rules.check_condition(cond, game.state, on)
    _grain(game, 1)
    assert rules.check_condition(cond, game.state, on)
    assert not rules.check_condition(cond, game.state)  # 沒給 content 判不了：不成立


def test_a_grain_condition_hides_the_choice_until_the_grain_is_there(on):
    """真的走選項的可見判斷（events.visible_choices 帶著 content）：糧不夠就看不到那個選項。"""
    from tianxia.events import visible_choices
    from tianxia.models import Choice, Event

    event = Event(id="e", title="t", text="x", actions=[], choices=[
        Choice(text="「帶了糧。」", condition=Condition(grain_min=2)), Choice(text="「帶了人。」"),
    ])
    game = _game(on)
    assert [c.text for _, c in visible_choices(event, game.state, on)] == ["「帶了人。」"]
    _grain(game, 1)
    assert [c.text for _, c in visible_choices(event, game.state, on)] == ["「帶了糧。」", "「帶了人。」"]


def test_donate_grain_records_and_counts(on):
    game = _game(on, at="nanyang_huangjin_camp")
    _grain(game, 3)
    msgs = rules.apply_effect(Effect(donate_grain={"nanyang_huangjin_camp": 2}), game.state, on, game.world)
    p = game.state.player
    assert p.donations == {"nanyang_huangjin_camp:糧草": 1} and p.contrib == on.config.contrib_per_push
    assert materials.grain_of(game.state, on) == 2 and any(m.endswith("-1") for m in msgs)


def test_donate_grain_adds_up_and_goes_into_this_weeks_account(on):
    game = _game(on, at="nanyang_huangjin_camp")
    _grain(game, 5)
    for _ in range(2):
        rules.apply_effect(Effect(donate_grain={"nanyang_huangjin_camp": 2}), game.state, on, game.world)
    p = game.state.player
    assert p.donations == {"nanyang_huangjin_camp:糧草": 2}
    assert p.contrib == 2 * on.config.contrib_per_push and sum(p.contrib_weeks.values()) == p.contrib


def test_a_donation_without_the_grain_records_nothing(on):
    """糧不夠就什麼都不收、不記、不給貢獻（選項本來就用 grain_min 擋住，這裡是效果自己的底線）。"""
    game = _game(on, at="nanyang_huangjin_camp")
    msgs = rules.apply_effect(Effect(donate_grain={"nanyang_huangjin_camp": 2}), game.state, on, game.world)
    p = game.state.player
    assert msgs == [] and p.donations == {} and p.contrib == 0 and p.contrib_weeks == {}


def test_a_zero_donation_pays_nothing_even_if_it_slips_past_loading(on):
    """載入時擋下份量 ≤ 0（見下面）；就算漏進來，換算出 0 份也不記捐獻、不給貢獻。"""
    game = _game(on, at="nanyang_huangjin_camp")
    _grain(game, 3)
    rules.apply_effect(Effect(donate_grain={"nanyang_huangjin_camp": 0}), game.state, on, game.world)
    p = game.state.player
    assert p.donations == {} and p.contrib == 0 and materials.grain_of(game.state, on) == 3


def test_donation_with_a_trend_still_pushes(on):
    """F1：效果裡有捐糧又有 trend 時，apply_effect 的 push 參數不能被同名的模組蓋掉（TypeError: 'module' object is not callable）。"""
    effect = Effect(donate_grain={"nanyang_huangjin_camp": 2}, trend={"nanyang": 1})
    for use_push in (False, True):
        game = _game(on, name=f"甲{use_push}", at="nanyang_huangjin_camp")
        _grain(game, 2)
        extra = (game.push_trend,) if use_push else ()  # 引擎走第五個參數 push；沒給就直接 change_trend
        msgs = rules.apply_effect(effect, game.state, on, game.world, *extra)
        assert game.state.player.donations == {"nanyang_huangjin_camp:糧草": 1} and msgs
        assert game.state.player.contrib >= on.config.contrib_per_push


def test_fragment_given_once(on):
    game = _game(on)
    first = rules.apply_effect(Effect(fs_fragments=["fs_zhangjiao_huang:0"]), game.state, on, game.world)
    assert first and first[0].startswith("你聽到一件事：")
    assert game.state.player.fragments.get("fs_zhangjiao_huang") == [0]
    assert rules.apply_effect(Effect(fs_fragments=["fs_zhangjiao_huang:0"]), game.state, on, game.world) == []


def test_fragment_not_for_the_other_side(on):
    game = _game(on, faction="guan")
    assert foreshadow.grant_fragment(game.state, on, "fs_zhangjiao_huang", 0) == []


def test_fragment_only_while_the_chain_can_still_be_done(on):
    """伏筆不在跑、鏈沒有、那件大事已經發生了：什麼都不給（跟聽片段的其他路一樣）。"""
    game = _game(on)
    assert foreshadow.grant_fragment(game.state, on, "no_such_chain", 0) == []
    chain = foreshadow.chain(on, "fs_zhangjiao_huang")
    game.state.world.timeline[chain.event] = TimelineResult(key="成", time=game.state.world.time)  # 結算過了就是發生了
    assert foreshadow.grant_fragment(game.state, on, "fs_zhangjiao_huang", 0) == []
    assert game.state.player.fragments == {}


def test_a_fragment_index_that_does_not_exist_gives_nothing(on):
    """載入時擋下（見下面）；漏進來也不能 IndexError 把整個動作弄壞。"""
    game = _game(on)
    assert foreshadow.grant_fragment(game.state, on, "fs_zhangjiao_huang", 99) == []
    assert foreshadow.grant_fragment(game.state, on, "fs_zhangjiao_huang", -1) == []
    assert game.state.player.fragments == {}


def test_a_malformed_fragment_reference_gives_nothing(on):
    """載入時擋下寫壞的參照（見下面）；漏進來的也只是什麼都不給，不能 ValueError 把整個動作弄壞。"""
    game = _game(on)
    effect = Effect(fs_fragments=["fs_zhangjiao_huang:x", "fs_zhangjiao_huang", "fs_zhangjiao_huang:-1", ":0"])
    assert rules.apply_effect(effect, game.state, on, game.world) == []
    assert game.state.player.fragments == {}


def test_the_given_fragment_does_not_start_a_rumor(on):
    game = _game(on)
    before = len(game.state.world.rumors)
    rules.apply_effect(Effect(fs_fragments=["fs_zhangjiao_huang:0"]), game.state, on, game.world)
    assert len(game.state.world.rumors) == before


def test_runic_pieces_add_up(on):
    game = _game(on)
    rules.apply_effect(Effect(runic=2), game.state, on, game.world)
    assert game.state.player.runic_pieces == 2
    rules.apply_effect(Effect(runic=1), game.state, on, game.world)
    assert game.state.player.runic_pieces == 3


def test_the_new_effects_do_nothing_outside_season_one(real):
    """N9：第一季的規則沒開（beta 那一季）：捐糧不記捐獻與貢獻、片段不給、殘片不記。"""
    game = _game(real, at="nanyang_huangjin_camp")
    _grain(game, 3)
    effect = Effect(donate_grain={"nanyang_huangjin_camp": 2}, fs_fragments=["fs_zhangjiao_huang:0"], runic=2)
    assert rules.apply_effect(effect, game.state, real, game.world) == []
    p = game.state.player
    assert (p.donations, p.contrib, p.fragments, p.runic_pieces) == ({}, 0, {}, 0)
    assert materials.grain_of(game.state, real) == 3


def test_the_new_effects_come_in_together(on):
    game = _game(on, at="nanyang_huangjin_camp")
    _grain(game, 3)
    effect = Effect(text="全都來", donate_grain={"nanyang_huangjin_camp": 2}, fs_fragments=["fs_zhangjiao_huang:0"], runic=2)
    msgs = rules.apply_effect(effect, game.state, on, game.world)
    p = game.state.player
    assert msgs[0] == "全都來" and any(m.startswith("你聽到一件事：") for m in msgs)
    assert (p.donations, p.fragments, p.runic_pieces) == ({"nanyang_huangjin_camp:糧草": 1}, {"fs_zhangjiao_huang": [0]}, 2)


# ── 載入時的檢查（F3）────────────────────────────────────────


def test_runic_cannot_be_negative():
    with pytest.raises(ValidationError):
        Effect(runic=-1)
    assert Effect(runic=0).runic == 0


def test_grain_min_cannot_be_negative():
    with pytest.raises(ValidationError):
        Condition(grain_min=-1)


@pytest.mark.parametrize("amount", [0, -1])
def test_donate_grain_amounts_must_be_more_than_zero(on, amount):
    """份量 0 或負的：換算出 0 份，拿得到 0 份糧、還記一筆貢獻。載入時擋下。"""
    on.events["promo_huang_2"].choices[0].effect.donate_grain = {"nanyang_huangjin_camp": amount}
    with pytest.raises(ContentError, match="donate_grain 的份量要大於 0"):
        validate(on)


def test_donate_grain_must_name_a_location(on):
    on.events["promo_huang_2"].choices[0].effect.donate_grain = {"nowhere": 2}
    with pytest.raises(ContentError, match="nowhere"):
        validate(on)


@pytest.mark.parametrize("ref", [
    "fs_zhangjiao_huang:9",  # 片段沒有那麼多
    "fs_zhangjiao_huang:-1",  # 序號不能是負的
    "no_such_chain:0",  # 沒有這條鏈
    "fs_zhangjiao_huang",  # 沒寫序號
    "fs_zhangjiao_huang:x",  # 序號不是數字
])
def test_fs_fragments_must_name_a_fragment_that_exists(on, ref):
    on.events["promo_huang_2"].choices[0].effect.fs_fragments = [ref]
    with pytest.raises(ContentError, match="fs_fragments 的 .* 不存在"):
        validate(on)


def test_a_real_fragment_reference_passes(on):
    on.events["promo_huang_2"].choices[0].effect.fs_fragments = ["fs_zhangjiao_huang:0"]
    on.events["promo_huang_2"].choices[0].effect.donate_grain = {"nanyang_huangjin_camp": 2}
    validate(on)


@pytest.mark.parametrize("field, value", [
    ("donate_grain", {"nanyang_huangjin_camp": 2}), ("fs_fragments", ["fs_zhangjiao_huang:0"]), ("runic", 2),
])
def test_a_free_text_reward_cannot_carry_the_new_effects(on, field, value):
    """隨口應對的獎勵不能串劇情、也不能送糧、片段與殘片：跟 丙一 的晉升效果同一張禁用清單。"""
    event = next(e for e in on.events.values() if e.free_text is not None)
    setattr(event.free_text.effect, field, value)
    with pytest.raises(ContentError, match=f"隨口應對 effect：不能有.*{field}"):
        validate(on)
    setattr(event.free_text.effect, field, type(value)())
    setattr(event.free_text.fail_effect, field, value)
    with pytest.raises(ContentError, match=f"隨口應對 fail_effect：不能有.*{field}"):
        validate(on)
