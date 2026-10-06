"""第一季正式版・丙一：第 3、4 階晉升的機制，與官軍、豪強的四則奇遇（計畫 2026-10-06-第一季正式版-丙一）。

用真實內容（content/）：每個測試拿自己的一份（conftest.real_content 的複本），開關在測試裡才打開。"""
from __future__ import annotations

import random

import pytest
from pydantic import ValidationError

from conftest import real_content
from tianxia import figures, ranks, rules, timetable
from tianxia.content import ContentError, validate
from tianxia.engine import Game
from tianxia.models import Config, Effect, EventMod, PatronLine, PromotionCast, PromotionDef, PromotionLeg
from tianxia.state import PlayerState, Summons, TimelineResult


@pytest.fixture
def real():
    c = real_content()
    c.config.auto_open_first_season = True
    c.config.train_event_chance = 0.0
    return c


@pytest.fixture
def on(real):
    real.config.season_one, real.config.season_days, real.config.server_max_players = True, 2.5, 2
    return real


def _game(content, name="甲", faction=None, at=None, rank=0):
    game = Game.new(content, name, rng=random.Random(0))
    p = game.state.player
    p.faction, p.rank = faction, rank
    if at is not None:
        p.location = at
    return game


# ── Task 1：資料模型與內容檢查 ─────────────────────────────


def test_defaults_so_old_saves_load():
    p = PlayerState(name="甲", location="x", stats={}, stamina=0)
    assert (p.qualified, p.hinted) == (False, [])
    s = Summons(rank=2, location="x")
    assert (s.leg, s.prev, s.event) == (0, None, None)
    assert (Config().rank3_contrib, Config().rank4_contrib) == (900, 1800)
    assert (Effect().summons_next, Effect().event_mods, Effect().patron) == (None, [], None)
    old = PromotionDef(faction="guan", rank=2, location="x", event_main="e", summons_text="t", closing="c")
    assert (old.legs, old.patron_lines) == ([], {})  # 第 2 階照舊寫法，不必認識新欄位


def test_old_save_json_without_the_new_fields_loads():
    """舊存檔的 JSON 沒有新欄位：照預設載入（characters.data 存的就是這種 JSON）。"""
    p = PlayerState.model_validate({"name": "甲", "location": "x", "stats": {}, "stamina": 0,
                                    "summons": {"rank": 2, "location": "x", "figure": "huangfusong", "since": 3.0}})
    assert (p.qualified, p.hinted) == (False, [])
    assert (p.summons.leg, p.summons.prev, p.summons.event) == (0, None, None)


def test_new_fields_survive_a_save_round_trip():
    p = PlayerState(name="甲", location="x", stats={}, stamina=0, qualified=True, hinted=[3, 4],
                    summons=Summons(rank=3, location="x", leg=1, prev="promo_guan_3_memorial", event="promo_guan_3_palace"))
    again = PlayerState.model_validate_json(p.model_dump_json())
    assert (again.qualified, again.hinted) == (True, [3, 4])
    assert (again.summons.leg, again.summons.prev, again.summons.event) == (1, "promo_guan_3_memorial", "promo_guan_3_palace")


def test_rank_is_between_two_and_four():
    for bad in (1, 5):
        with pytest.raises(ValidationError):
            PromotionDef(faction="guan", rank=bad, closing="x")
    for ok in (2, 3, 4):
        assert PromotionDef(faction="guan", rank=ok, closing="x").rank == ok


def test_effect_patron_is_one_of_three():
    assert Effect(patron="yuan").patron == "yuan"
    with pytest.raises(ValidationError):
        Effect(patron="liu")
    with pytest.raises(ValidationError):
        EventMod(event="luzhi_jailed", side="wei", amount=0.05)


def test_rank_three_needs_legs(real):
    real.promotions.append(PromotionDef(faction="guan", rank=3, closing="x"))
    with pytest.raises(ContentError, match="legs"):
        validate(real)


def test_rank_two_still_needs_its_own_fields(real):
    """第 2 階的 location、event_main、summons_text 改成預設空字串之後，由檢查擋住沒寫的。"""
    real.promotions = [p for p in real.promotions if not (p.faction == "guan" and p.rank == 2)]
    real.promotions.append(PromotionDef(faction="guan", rank=2, closing="x"))
    with pytest.raises(ContentError, match="第 2 階要寫 location、event_main、summons_text"):
        validate(real)


def test_summons_next_must_name_its_own_event(real):
    event = real.events["promo_guan_2"]
    event.choices[0].effect.summons_next = "promo_huang_2"
    with pytest.raises(ContentError, match="summons_next"):
        validate(real)


def _two_leg(real, location="luoyang_palace", first_cast=None):
    """兩段的第 3 階：location 空著、地點寫在各段；各段的事件都算晉升奇遇（升階、給部下的那一段過得了檢查）。
    借用官軍第 2 階的兩則事件（同一個陣營，部下的陣營對得上）。真的官軍第 3 階（Task 3 以後有）先拿掉，
    連同它兩段事件（寫了 promote／followers，沒有晉升定義認它們就過不了檢查）一起。"""
    real.promotions = [p for p in real.promotions if not (p.faction == "guan" and p.rank == 3)]
    for gone in ("promo_guan_3_palace", "promo_guan_3_hejin"):  # Task 3 之後才有，Task 1 時 pop 不到
        real.events.pop(gone, None)
    first = first_cast or PromotionCast(event="promo_guan_2", figure="luzhi", at="luzhi_camp", summons_text="到{據點}。")
    promo = PromotionDef(faction="guan", rank=3, closing="（結尾）", legs=[
        PromotionLeg(casts=[first]),
        PromotionLeg(location=location, casts=[
            PromotionCast(event="promo_guan_2_handoff", after="promo_guan_2", summons_text="送到{據點}。"),
        ]),
    ])
    real.promotions.append(promo)
    return promo


def test_a_two_leg_promotion_is_valid(real):
    _two_leg(real)
    validate(real)  # 不丟錯


def test_the_events_of_the_legs_count_as_promotion_events(real):
    """各段的版本事件靠第 3 階自己認作晉升奇遇（升階、給部下才過得了檢查）：把第 2 階拿掉，那兩則事件就只剩 legs 認得它們。"""
    real.promotions = [p for p in real.promotions if not (p.faction == "guan" and p.rank == 2)]
    _two_leg(real)
    validate(real)  # 不丟錯
    real.promotions = [p for p in real.promotions if not (p.faction == "guan" and p.rank == 3)]
    with pytest.raises(ContentError, match="promote／followers 只能寫在晉升奇遇"):
        validate(real)  # 沒有任何晉升認它們了


def test_a_leg_location_may_be_the_nearest_base(real):
    _two_leg(real, location="nearest_base")
    validate(real)  # "nearest_base" 不是地點 id，不查


def test_a_leg_location_must_exist(real):
    real.promotions.append(PromotionDef(faction="guan", rank=3, closing="（結尾）", legs=[
        PromotionLeg(location="nowhere", casts=[PromotionCast(event="promo_guan_2", summons_text="到{據點}。")]),
    ]))
    with pytest.raises(ContentError, match="nowhere"):
        validate(real)


def test_a_leg_needs_at_least_one_cast(real):
    promo = _two_leg(real)
    promo.legs[1].casts = []
    with pytest.raises(ContentError, match="第 2 段沒有版本"):
        validate(real)


@pytest.mark.parametrize("change, word", [
    ({"event": "no_such_event"}, "no_such_event"),
    ({"figure": "no_such_figure"}, "no_such_figure"),
    ({"at": "no_such_place"}, "no_such_place"),
    ({"before_event": "no_such_big_event"}, "before_event no_such_big_event"),
])
def test_a_cast_names_things_that_exist(real, change, word):
    cast = PromotionCast(**{"event": "promo_guan_2", "figure": "luzhi", "at": "luzhi_camp",
                            "summons_text": "到{據點}。", **change})
    _two_leg(real, first_cast=cast)
    with pytest.raises(ContentError, match=word):
        validate(real)


def test_a_cast_before_a_timetable_event_is_valid(real):
    cast = PromotionCast(event="promo_guan_2", figure="luzhi", at="luzhi_camp", before_event="luzhi_jailed",
                         summons_text="到{據點}。")
    _two_leg(real, first_cast=cast)
    validate(real)


def test_a_cast_must_know_where_it_plays(real):
    """沒有人物、沒有 at、段也沒寫 location：不知道在哪裡演。"""
    real.promotions.append(PromotionDef(faction="guan", rank=3, closing="（結尾）", legs=[
        PromotionLeg(casts=[PromotionCast(event="promo_guan_2", summons_text="到{據點}。")]),
    ]))
    with pytest.raises(ContentError, match="不知道在哪裡演"):
        validate(real)


def test_a_figure_alone_tells_where_the_cast_plays(real):
    """只寫人物：他此刻在哪就在哪（盧植版的版本不必另寫 at）。"""
    cast = PromotionCast(event="promo_guan_2", figure="luzhi", summons_text="到{據點}。")
    _two_leg(real, first_cast=cast)
    validate(real)


def test_patron_lines_name_known_characters(real):
    promo = _two_leg(real)
    promo.patron_lines = {"yuan": PatronLine(text="（一句話）", affinity={"yuanshao": 5})}
    validate(real)
    promo.patron_lines = {"yuan": PatronLine(text="（一句話）", affinity={"no_such_person": 5})}
    with pytest.raises(ContentError, match="no_such_person"):
        validate(real)


@pytest.mark.parametrize("slot", ["effect", "fail_effect"])
def test_event_mods_name_a_timetable_event(real, slot):
    choice = real.events["promo_guan_2"].choices[0]
    setattr(choice, slot, Effect(event_mods=[EventMod(event="no_such_big_event", side="guan", amount=0.05)]))
    with pytest.raises(ContentError, match="event_mods 的 no_such_big_event"):
        validate(real)


def test_event_mods_on_a_rolled_event_are_valid(real):
    choice = real.events["promo_guan_2"].choices[0]
    choice.effect.event_mods = [EventMod(event="luzhi_jailed", side="huang", amount=0.05)]
    validate(real)


def test_event_mods_need_an_event_that_is_rolled(real):
    """固定、決戰、季末的大事沒有「成」對誰有利，event_mods 在那裡什麼都不做（timetable.add_mod）：寫了就是寫錯。"""
    fixed = next(e.id for e in real.timetable if e.roll_side is None)
    real.events["promo_guan_2"].choices[0].effect.event_mods = [EventMod(event=fixed, side="guan", amount=0.05)]
    with pytest.raises(ContentError, match=f"event_mods 的 {fixed}"):
        validate(real)


@pytest.mark.parametrize("slot", ["effect", "fail_effect"])
def test_summons_next_in_either_effect_must_name_its_own_event(real, slot):
    _two_leg(real)
    choice = real.events["promo_guan_2"].choices[0]
    setattr(choice, slot, Effect(summons_next="promo_guan_2"))
    validate(real)  # 第一段的事件、寫自己的 id：可以
    setattr(choice, slot, Effect(summons_next="promo_guan_2_handoff"))
    with pytest.raises(ContentError, match="summons_next 要寫這一則自己的 id"):
        validate(real)


def test_summons_next_is_only_for_a_leg_that_is_not_the_last(real):
    """最後一段演完就是晉升，沒有下一段可去；寫在晉升奇遇之外的事件上也沒人讀。"""
    _two_leg(real)
    real.events["promo_guan_2_handoff"].choices[0].effect.summons_next = "promo_guan_2_handoff"
    with pytest.raises(ContentError, match="summons_next 只能寫在晉升奇遇的最後一段以前"):
        validate(real)
    real.events["promo_guan_2_handoff"].choices[0].effect.summons_next = None
    stray = next(e for e in real.events.values() if e.id not in ("promo_guan_2", "promo_guan_2_handoff"))
    stray.choices[0].effect.summons_next = stray.id
    with pytest.raises(ContentError, match="summons_next 只能寫在晉升奇遇的最後一段以前"):
        validate(real)


def test_patron_is_only_for_promotion_events(real):
    real.events["promo_haoqiang_2"].choices[0].effect.patron = "yuan"
    validate(real)  # 晉升奇遇可以
    stray = next(e for e in real.events.values() if not e.id.startswith("promo_"))
    stray.choices[0].effect.patron = "cao"
    with pytest.raises(ContentError, match="patron 只能寫在晉升奇遇"):
        validate(real)


@pytest.mark.parametrize("field, value", [
    ("summons_next", "x"), ("patron", "yuan"), ("promote", 3), ("followers", ["follower_guan_spear"]),
    ("event_mods", [EventMod(event="luzhi_jailed", side="guan", amount=0.05)]),
])
def test_a_free_text_reward_cannot_carry_promotion_effects(real, field, value):
    """隨口應對的獎勵不能串劇情：新的三種（summons_next、event_mods、patron）與晉升的兩種（promote、followers）都擋。"""
    event = next(e for e in real.events.values() if e.free_text is not None)
    setattr(event.free_text.effect, field, value)
    with pytest.raises(ContentError, match=f"隨口應對 effect：不能有.*{field}"):
        validate(real)
