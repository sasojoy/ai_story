"""第一季正式版・丙一：第 3、4 階晉升的機制，與官軍、豪強的四則奇遇（計畫 2026-10-06-第一季正式版-丙一）。

用真實內容（content/）：每個測試拿自己的一份（conftest.real_content 的複本），開關在測試裡才打開。"""
from __future__ import annotations

import random

import pytest
from pydantic import ValidationError

from conftest import real_content
from tianxia import bot_policy, defection, enlist, figures, ranks, rules, timetable
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
    game.client = None  # 沒有任何地方會叫模型
    p = game.state.player
    p.faction, p.rank = faction, rank
    if at is not None:
        p.location = at
    return game


def _without_rank3(real):
    """拿掉真的官軍第 3 階與它兩段的事件（Task 3 之後才有，Task 1 時什麼都沒拿掉）：測試要自己寫一筆官軍第 3 階，
    不然同一階寫了兩筆、而且那兩則事件寫了 promote／followers 卻沒有晉升認它們，會多出跟測試無關的錯誤。"""
    real.promotions = [p for p in real.promotions if not (p.faction == "guan" and p.rank == 3)]
    for gone in ("promo_guan_3_palace", "promo_guan_3_hejin"):
        real.events.pop(gone, None)


# ── Task 1：資料模型與內容檢查 ─────────────────────────────


def test_defaults_so_old_saves_load():
    p = PlayerState(name="甲", location="x", stats={}, stamina=0)
    assert (p.qualified, p.rank_hinted) == (False, [])
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
    assert (p.qualified, p.rank_hinted) == (False, [])
    assert (p.summons.leg, p.summons.prev, p.summons.event) == (0, None, None)


def test_new_fields_survive_a_save_round_trip():
    p = PlayerState(name="甲", location="x", stats={}, stamina=0, qualified=True, rank_hinted=[3, 4],
                    summons=Summons(rank=3, location="x", leg=1, prev="promo_guan_3_memorial", event="promo_guan_3_palace"))
    again = PlayerState.model_validate_json(p.model_dump_json())
    assert (again.qualified, again.rank_hinted) == (True, [3, 4])
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
    _without_rank3(real)
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
    _without_rank3(real)
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
    _without_rank3(real)
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
    _without_rank3(real)
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


# ── Task 2：多段召見、提示、晉升到第 3 階與第 4 階資格 ─────────


def _test_rank3(on, rank4=False):
    """測試用的官軍第 3 階：盧植營兩個版本（盧植、董卓），第二段接著上一段。事件借用 T5 的兩則。
    rank4：再加一筆測試用的第 4 階（何進的大將軍府一段，事件借用 promo_guan_2）。真的官軍第 3、4 階（Task 3 以後有）先拿掉。"""
    _without_rank3(on)
    on.promotions = [p for p in on.promotions if not (p.faction == "guan" and p.rank == 4)]
    on.promotions.append(PromotionDef(faction="guan", rank=3, closing="（結尾）", legs=[
        PromotionLeg(casts=[
            PromotionCast(event="promo_guan_2", figure="luzhi", at="luzhi_camp", summons_text="盧植召你到{據點}。"),
            PromotionCast(event="promo_guan_2_handoff", figure="dongzhuo", at="luzhi_camp", summons_text="董卓召你到{據點}。"),
        ]),
        PromotionLeg(casts=[
            PromotionCast(event="promo_huang_2", at="luoyang_palace", after="promo_guan_2", summons_text="送到{據點}。"),
            PromotionCast(event="promo_huang_2_handoff", at="dajiangjun_fu", after="promo_guan_2_handoff",
                          summons_text="送到{據點}。"),
        ]),
    ]))
    if rank4:
        on.promotions.append(PromotionDef(faction="guan", rank=4, closing="（四階結尾）", legs=[
            PromotionLeg(casts=[PromotionCast(event="promo_guan_2", figure="hejin", summons_text="何進召你到{據點}。")]),
        ]))


def _ready(game, rank=2, contrib=900, opp=True):
    p = game.state.player
    p.rank, p.contrib = rank, contrib
    if opp:
        p.opp_done = [next(o.id for o in game.content.opportunities if o.faction == p.faction and o.rank == rank + 1)]


def _retire(game, fid, status="retired"):
    w = game.state.world
    w.figures[fid] = figures.state_of(game.state, game.content, fid).model_copy(update={"status": status})


def _settle(game, event_id):
    """時刻表上的某件大事已經結算了（只要 timeline 裡有它）。"""
    game.state.world.timeline[event_id] = TimelineResult(key="成", time=game.state.world.time)


def test_hint_once_then_summons_after_the_opportunity(on):
    _test_rank3(on)
    game = _game(on, faction="guan", at="changshe")
    _ready(game, opp=False)
    assert ranks.check_summons(game.state, on) == [ranks.HINT]
    assert ranks.check_summons(game.state, on) == []  # 只說一次
    _ready(game)
    assert ranks.check_summons(game.state, on) == ["盧植召你到盧植營。"]
    s = game.state.player.summons
    assert (s.rank, s.leg, s.location, s.event, s.figure) == (3, 0, "luzhi_camp", "promo_guan_2", "luzhi")


def test_no_summons_below_the_bar(on):
    _test_rank3(on)
    game = _game(on, faction="guan")
    _ready(game, contrib=899)
    assert ranks.check_summons(game.state, on) == []


def test_jailed_luzhi_hands_the_first_leg_to_dongzhuo(on):
    _test_rank3(on)
    game = _game(on, faction="guan")
    _ready(game)
    ranks.check_summons(game.state, on)
    _retire(game, "luzhi", "jailed")
    w = game.state.world
    w.figures["dongzhuo"] = figures.state_of(game.state, on, "dongzhuo").model_copy(
        update={"front": "jizhou", "location": "luzhi_camp"})  # 第 8 週到任
    assert ranks.check_summons(game.state, on) == ["董卓召你到盧植營。"]  # 召見自動改由接手的人發
    assert game.state.player.summons.event == "promo_guan_2_handoff"


def test_no_summons_while_nobody_can_present(on):
    _test_rank3(on)
    game = _game(on, faction="guan")
    _ready(game)
    _retire(game, "luzhi", "jailed")  # 董卓還在孟津渡、不在盧植營
    assert ranks.check_summons(game.state, on) == [] and game.state.player.summons is None


def test_second_leg_follows_the_first(on):
    _test_rank3(on)
    game = _game(on, faction="guan", at="luzhi_camp")
    _ready(game)
    ranks.check_summons(game.state, on)
    assert ranks.next_leg(game.state, on, "promo_guan_2") == ["送到洛陽宮城。"]
    s = game.state.player.summons
    assert (s.leg, s.prev, s.location, s.event) == (1, "promo_guan_2", "luoyang_palace", "promo_huang_2")
    _retire(game, "luzhi", "jailed")  # 第二段不看盧植在不在
    assert ranks.check_summons(game.state, on) == [] and game.state.player.summons.location == "luoyang_palace"


def test_promote_to_three_names_the_member(on):
    game = _game(on, faction="guan")
    game.state.player.rank, game.state.player.summons = 2, Summons(rank=3, location="luoyang_palace")
    before = len(game.state.world.rumors)
    msgs = ranks.promote(game.state, on, 3)
    assert "你升為軍司馬。" in msgs and game.state.player.rank == 3 and game.state.player.summons is None
    note = game.state.world.rumors[before]
    assert (note.layer, note.faction, note.text) == ("faction", "guan", "甲升為軍司馬。")
    assert game.state.world.promoted_today == {}  # 第 3 階不進每日彙整


def test_rank_four_is_a_qualification(on):
    game = _game(on, faction="guan")
    game.state.player.rank = 3
    before = len(game.state.world.rumors)
    msgs = ranks.promote(game.state, on, 4)
    p = game.state.player
    assert (p.rank, p.qualified) == (3, True) and "你取得校尉的資格，候缺。" in msgs
    assert ranks.title(on, game.state) == "軍司馬（校尉候缺）"
    assert game.state.world.rumors[before].text == "甲取得校尉的資格，候缺。"
    p.contrib, p.opp_done = 99999, [o.id for o in on.opportunities]
    assert ranks.check_summons(game.state, on) == []  # 拿到資格之後不再發召見


def test_an_anonymous_member_is_named_on_promotion(on):
    """陣營軍情一律寫本名（傳聞分層第七節）：匿名的人升第 3 階、拿到第 4 階資格，軍情照寫名號。"""
    game = _game(on, faction="guan")
    p = game.state.player
    p.rank, p.anonymous = 2, True
    before = len(game.state.world.rumors)
    ranks.promote(game.state, on, 3)
    ranks.promote(game.state, on, 4)
    texts = [r.text for r in game.state.world.rumors[before:]]
    assert texts == ["甲升為軍司馬。", "甲取得校尉的資格，候缺。"]


def test_brush_off_stops_offering_a_rank_once_qualified(on):
    """被打發時「或在官軍再升一階」只給還升得上去的人：拿到第 4 階資格（候缺）的人沒有下一階可升。"""
    on.promotions = [p for p in on.promotions if not (p.faction == "guan" and p.rank == 4)]
    on.promotions.append(PromotionDef(faction="guan", rank=4, closing="（結尾）", legs=[
        PromotionLeg(casts=[PromotionCast(event="promo_guan_2", at="dajiangjun_fu", summons_text="到{據點}。")]),
    ]))  # 測試用的第 4 階（Task 3 才有真的）
    game = _game(on, faction="guan", rank=3)
    p = game.state.player
    p.stats["fame"] = rules.audience_bar(game.state, on, "luzhi") - 1
    assert "再升一階" in game._brush_off("luzhi")[0]  # noqa: SLF001
    p.qualified = True
    assert "再升一階" not in game._brush_off("luzhi")[0]  # noqa: SLF001


def test_summons_next_effect_moves_the_leg(on):
    _test_rank3(on)
    game = _game(on, faction="guan", at="luzhi_camp")
    _ready(game)
    ranks.check_summons(game.state, on)
    msgs = rules.apply_effect(Effect(summons_next="promo_guan_2"), game.state, on, game.world)
    assert msgs == ["送到洛陽宮城。"] and game.state.player.summons.leg == 1


# 以下是這個任務自己多寫的：開發預審的備註（N4、N6 以外）、機制的邊邊角角


def test_threshold_by_rank(on):
    assert [ranks.threshold(on, r) for r in (2, 3, 4)] == [300, 900, 1800]
    on.config.rank3_contrib = 5
    assert ranks.threshold(on, 3) == 5


def test_nothing_happens_with_the_switch_off(real):
    _test_rank3(real)
    game = _game(real, faction="guan", at="changshe")
    _ready(game)
    assert ranks.check_summons(game.state, real) == [] and game.state.player.summons is None
    assert ranks.promote(game.state, real, 3) == [] and game.state.player.rank == 2
    assert ranks.promote(game.state, real, 4) == [] and not game.state.player.qualified
    assert ranks.title(real, game.state) is None


def test_the_hint_is_said_once_per_rank_and_the_next_rank_gets_its_own(on):
    _test_rank3(on, rank4=True)
    game = _game(on, faction="guan")
    p = game.state.player
    _ready(game, opp=False)
    assert ranks.check_summons(game.state, on) == [ranks.HINT] and p.rank_hinted == [3]
    ranks.promote(game.state, on, 3)  # 之後升了第 3 階（演過奇遇）：第 4 階的進度到了、機緣還沒有
    p.contrib = 1800
    assert ranks.check_summons(game.state, on) == [ranks.HINT] and p.rank_hinted == [3, 4]
    assert ranks.check_summons(game.state, on) == []
    _ready(game, rank=3, contrib=1800)  # 補上第 4 階的機緣
    assert ranks.check_summons(game.state, on) == ["何進召你到大將軍府。"]
    assert p.summons.rank == 4 and p.summons.event == "promo_guan_2"


def test_no_hint_for_a_rank_nobody_defined(on):
    """HINT 是「只缺一個機會」：那一階有晉升定義才說（這一版真內容還沒有第 4 階的話，沒有什麼好缺的）。"""
    _test_rank3(on)  # 只有第 3 階
    game = _game(on, faction="guan")
    _ready(game, rank=3, contrib=5000, opp=False)
    assert ranks.check_summons(game.state, on) == [] and game.state.player.rank_hinted == []


def test_the_same_cast_with_the_same_words_is_not_announced_twice(on):
    """N4（開發預審）：只換了版本事件、人與地點與那一句話都沒變（何進的索賄在盧植下獄之前、之後各一版）：手上的召見悄悄換成
    新的版本，不再把同一句話又寫進紀錄一次。"""
    _without_rank3(on)
    on.promotions.append(PromotionDef(faction="guan", rank=3, closing="（結尾）", legs=[
        PromotionLeg(casts=[
            PromotionCast(event="promo_guan_2", figure="hejin", before_event="luzhi_jailed", summons_text="何進召你到{據點}。"),
            PromotionCast(event="promo_guan_2_handoff", figure="hejin", summons_text="何進召你到{據點}。"),
        ]),
    ]))
    game = _game(on, faction="guan")
    _ready(game)
    assert ranks.check_summons(game.state, on) == ["何進召你到大將軍府。"]
    assert game.state.player.summons.event == "promo_guan_2"
    _settle(game, "luzhi_jailed")
    assert ranks.check_summons(game.state, on) == []  # 一句話都不重複
    assert game.state.player.summons.event == "promo_guan_2_handoff"  # 但演的版本已經換了
    assert ranks.summons_event(game.state, on) is None  # 人不在大將軍府
    game.state.player.location = "dajiangjun_fu"
    assert ranks.summons_event(game.state, on) == "promo_guan_2_handoff"


def test_the_summons_remembers_who_presents_now(on):
    """版本換了，召見記的出面的人也換（江湖紀錄與接手版都看它）。"""
    _test_rank3(on)
    game = _game(on, faction="guan")
    _ready(game)
    ranks.check_summons(game.state, on)
    assert game.state.player.summons.figure == "luzhi"
    _retire(game, "luzhi", "jailed")
    game.state.world.figures["dongzhuo"] = figures.state_of(game.state, on, "dongzhuo").model_copy(
        update={"front": "jizhou", "location": "luzhi_camp"})
    ranks.check_summons(game.state, on)
    assert game.state.player.summons.figure == "dongzhuo"


def test_a_qualified_member_is_not_summoned_again(on):
    """拿到第 4 階資格（候缺）之後 rank 還是 3、下一階的定義還在：不再發召見，也不再說 HINT。"""
    _test_rank3(on, rank4=True)
    game = _game(on, faction="guan", rank=3)
    p = game.state.player
    p.contrib, p.opp_done = 99999, [o.id for o in on.opportunities]
    p.qualified = True
    assert ranks.check_summons(game.state, on) == [] and p.summons is None
    p.qualified = False  # 對照：沒有資格的人這時就收到召見
    assert ranks.check_summons(game.state, on) == ["何進召你到大將軍府。"]


def test_a_new_version_with_other_words_is_announced(on):
    _without_rank3(on)
    on.promotions.append(PromotionDef(faction="guan", rank=3, closing="（結尾）", legs=[
        PromotionLeg(casts=[
            PromotionCast(event="promo_guan_2", figure="hejin", before_event="luzhi_jailed", summons_text="何進召你到{據點}。"),
            PromotionCast(event="promo_guan_2_handoff", figure="hejin", summons_text="何進改了主意，請你到{據點}。"),
        ]),
    ]))
    game = _game(on, faction="guan")
    _ready(game)
    ranks.check_summons(game.state, on)
    _settle(game, "luzhi_jailed")
    assert ranks.check_summons(game.state, on) == ["何進改了主意，請你到大將軍府。"]


def test_the_place_moves_with_the_presenter(on):
    """版本只寫人物、沒寫 at：召見的地點是他此刻的所在，他換了地方、召見的地點跟著換。"""
    _without_rank3(on)
    on.promotions.append(PromotionDef(faction="guan", rank=3, closing="（結尾）", legs=[
        PromotionLeg(casts=[PromotionCast(event="promo_guan_2", figure="luzhi", summons_text="盧植召你到{據點}。")]),
    ]))
    game = _game(on, faction="guan")
    _ready(game)
    assert ranks.check_summons(game.state, on) == ["盧植召你到盧植營。"]
    w = game.state.world
    w.figures["luzhi"] = figures.state_of(game.state, on, "luzhi").model_copy(update={"location": "changshe"})
    assert ranks.check_summons(game.state, on) == ["盧植召你到長社。"]
    assert game.state.player.summons.location == "changshe" and ranks.summons_line(game.state, on) == "盧植召你到長社。"


def test_current_cast_picks_the_first_version_that_holds(on):
    _without_rank3(on)
    promo = PromotionDef(faction="guan", rank=3, closing="（結尾）", legs=[
        PromotionLeg(casts=[
            PromotionCast(event="promo_guan_2", figure="luzhi", at="luzhi_camp", before_event="luzhi_jailed",
                          summons_text="甲。"),
            PromotionCast(event="promo_guan_2_handoff", at="changshe", flags_none=["war_over"], summons_text="乙。"),
            PromotionCast(event="promo_huang_2", at="luoyang_palace", after="promo_guan_2", summons_text="丙。"),
            PromotionCast(event="promo_huang_2_handoff", at="dajiangjun_fu", summons_text="丁。"),
        ]),
    ])
    on.promotions.append(promo)
    game = _game(on, faction="guan")
    s = game.state

    def event_and_place():
        found = ranks.current_cast(s, on, promo, 0, None)
        return None if found is None else (found[0].event, found[1])

    assert event_and_place() == ("promo_guan_2", "luzhi_camp")  # 盧植在場、大事還沒結算
    _settle(game, "luzhi_jailed")  # 大事結算了：before_event 版本不成立
    assert event_and_place() == ("promo_guan_2_handoff", "changshe")
    s.world.flags.add("war_over")  # 旗標在：flags_none 版本不成立；after 版本要上一段演的是 promo_guan_2，這裡是 None
    assert event_and_place() == ("promo_huang_2_handoff", "dajiangjun_fu")
    assert ranks.current_cast(s, on, promo, 0, "promo_guan_2")[0].event == "promo_huang_2"  # 上一段演的是它才成立
    assert ranks.current_cast(s, on, promo, 1, None) is None  # 沒有第 2 段
    _retire(game, "luzhi", "jailed")  # 人物不在場：只有 figure 的版本不成立（上面 at 版本不看人物）
    assert event_and_place() == ("promo_huang_2_handoff", "dajiangjun_fu")


def test_a_cast_with_a_figure_needs_him_active_and_placed(on):
    _without_rank3(on)
    promo = PromotionDef(faction="guan", rank=3, closing="（結尾）", legs=[
        PromotionLeg(casts=[PromotionCast(event="promo_guan_2", figure="luzhi", at="luzhi_camp", summons_text="甲。")]),
    ])
    game = _game(on, faction="guan")
    assert ranks.current_cast(game.state, on, promo, 0, None) is not None
    w = game.state.world
    w.figures["luzhi"] = figures.state_of(game.state, on, "luzhi").model_copy(update={"location": "changshe"})
    assert ranks.current_cast(game.state, on, promo, 0, None) is None  # 在場、可是不在 at
    for status in ("jailed", "retired", "crippled"):
        _retire(game, "luzhi", status)
        w.figures["luzhi"] = w.figures["luzhi"].model_copy(update={"location": "luzhi_camp"})
        assert ranks.current_cast(game.state, on, promo, 0, None) is None  # 下獄、退場、重創


def test_a_leg_without_a_place_uses_its_own_location_or_the_nearest_base(on):
    _without_rank3(on)
    on.promotions = [p for p in on.promotions if not (p.faction == "haoqiang" and p.rank == 3)]
    promo = PromotionDef(faction="haoqiang", rank=3, closing="（結尾）", legs=[
        PromotionLeg(location="runan", casts=[PromotionCast(event="promo_haoqiang_2", summons_text="到{據點}。")]),
        PromotionLeg(location="nearest_base", casts=[PromotionCast(event="promo_haoqiang_2", summons_text="到{據點}。")]),
    ])
    game = _game(on, faction="haoqiang", at="loushang_village")
    assert ranks.current_cast(game.state, on, promo, 0, None)[1] == "runan"
    nearest = ranks.summons_place(game.state, on, PromotionDef(faction="haoqiang", rank=2, location="nearest_base",
                                                               closing="x"))
    assert ranks.current_cast(game.state, on, promo, 1, None)[1] == nearest


def test_the_second_leg_waits_when_no_version_holds_yet(on):
    """NN4：下一段此刻沒有成立的版本時召見留在這一段之後等著（地點空著）：沒有召見那一句、沒有「應召」，假人不往哪裡走；
    版本之後成立了，下一次檢查補上地點、說那一句。"""
    _test_rank3(on)
    game = _game(on, faction="guan", at="luoyang_palace")
    _ready(game)
    ranks.check_summons(game.state, on)
    assert ranks.next_leg(game.state, on, "別的事件") == []  # 沒有哪個版本的 after 是它
    s = game.state.player.summons
    assert (s.leg, s.prev, s.event, s.location) == (1, "別的事件", None, "")
    assert ranks.summons_line(game.state, on) is None and ranks.summons_event(game.state, on) is None
    assert "act:summons" not in [o.id for o in game.options(odds=False)]
    assert bot_policy._summons_hop(game) is None  # noqa: SLF001
    assert ranks.check_summons(game.state, on) == []  # 還是沒有
    s.prev = "promo_guan_2"
    assert ranks.check_summons(game.state, on) == ["送到洛陽宮城。"] and s.location == "luoyang_palace"
    assert "act:summons" in [o.id for o in game.options(odds=False)]


def test_summons_line_and_event_follow_the_leg_you_are_on(on):
    _test_rank3(on)
    game = _game(on, faction="guan", at="changshe")
    p = game.state.player
    assert ranks.summons_line(game.state, on) is None and ranks.summons_event(game.state, on) is None  # 沒有召見
    _ready(game)
    ranks.check_summons(game.state, on)
    assert ranks.summons_line(game.state, on) == "盧植召你到盧植營。"
    assert ranks.summons_event(game.state, on) is None  # 人在長社、召見在盧植營
    p.location = "luzhi_camp"
    assert ranks.summons_event(game.state, on) == "promo_guan_2"
    ranks.next_leg(game.state, on, "promo_guan_2")
    assert ranks.summons_line(game.state, on) == "送到洛陽宮城。" and ranks.summons_event(game.state, on) is None
    p.location = "luoyang_palace"
    assert ranks.summons_event(game.state, on) == "promo_huang_2"


def test_the_summons_option_shows_where_the_cast_plays(on):
    _test_rank3(on)
    game = _game(on, faction="guan", at="luzhi_camp")
    _ready(game)
    ranks.check_summons(game.state, on)
    assert "act:summons" in [o.id for o in game.options(odds=False)]
    game.state.player.location = "changshe"
    assert "act:summons" not in [o.id for o in game.options(odds=False)]


def test_a_title_for_every_rank_and_faction(on):
    game = _game(on, faction="guan", rank=3)
    assert ranks.title(on, game.state) == "軍司馬"
    game.state.player.qualified = True
    assert ranks.title(on, game.state) == "軍司馬（校尉候缺）"
    assert game.status_data()["affiliation"] == "官軍・軍司馬（校尉候缺）"
    other = _game(on, name="乙", faction="huang", rank=3)
    other.state.player.qualified = True
    assert ranks.title(on, other.state) == "小方渠帥（大方渠帥候缺）"
    third = _game(on, name="丙", faction="haoqiang", rank=3)
    third.state.player.qualified = True
    assert ranks.title(on, third.state) == "地方豪強（一方之主候缺）"
    plain = _game(on, name="丁", faction="guan", rank=2)
    assert ranks.title(on, plain.state) == "屯長"


def test_rank_three_for_the_other_factions_names_the_member(on):
    for faction, title in (("huang", "小方渠帥"), ("haoqiang", "地方豪強")):
        game = _game(on, faction=faction, rank=2)
        before = len(game.state.world.rumors)
        assert f"你升為{title}。" in ranks.promote(game.state, on, 3)
        note = game.state.world.rumors[before]
        assert (note.faction, note.text) == (faction, f"甲升為{title}。")


def test_rank_two_still_goes_into_the_daily_summary(on):
    """第 2 階照舊：不發當下的軍情，記進當天的彙整（flush_news 隔天發，寫本名）。"""
    game = _game(on, faction="guan")
    before = len(game.state.world.rumors)
    ranks.promote(game.state, on, 2)
    assert len(game.state.world.rumors) == before
    assert list(game.state.world.promoted_today.values()) == [["甲"]]


def test_the_patron_line_follows_the_patron(on):
    """豪強升第 4 階：看靠山多一句話與情誼（晉升奇遇 4.3）；靠山不在 patron_lines 裡（或沒有靠山）就沒有。"""
    on.promotions = [p for p in on.promotions if not (p.faction == "haoqiang" and p.rank == 4)]
    on.promotions.append(PromotionDef(faction="haoqiang", rank=4, closing="（結尾）", legs=[
        PromotionLeg(location="nearest_base", casts=[PromotionCast(event="promo_haoqiang_2", summons_text="到{據點}。")]),
    ], patron_lines={
        "yuan": PatronLine(text="關羽冷冷道：「四世三公的門客？」", affinity={"guanyu": -5}),
        "self": PatronLine(text="劉備笑了笑。"),
    }))
    shown = on.characters["guanyu"].name
    game = _game(on, faction="haoqiang", rank=3)
    game.state.player.patron = "yuan"
    game.state.player.affinities["guanyu"] = 20
    msgs = ranks.promote(game.state, on, 4)
    assert msgs[0] == "你取得一方之主的資格，候缺。" and msgs[1] == "（結尾）"
    assert msgs[2:] == ["關羽冷冷道：「四世三公的門客？」", f"{shown}情誼 -5"]
    assert game.state.player.qualified and game.state.player.affinities["guanyu"] == 15
    for patron, expect in (("self", ["劉備笑了笑。"]), ("cao", []), (None, [])):
        again = _game(on, name="乙", faction="haoqiang", rank=3)
        again.state.player.patron = patron
        assert ranks.promote(again.state, on, 4)[2:] == expect


def test_event_mods_count_only_before_the_big_event_settles(on):
    game = _game(on, faction="guan")
    w = game.state.world
    huang = Effect(event_mods=[EventMod(event="luzhi_jailed", side="huang", amount=0.05)])
    guan = Effect(event_mods=[EventMod(event="luzhi_jailed", side="guan", amount=0.05)])
    assert rules.apply_effect(huang, game.state, on, game.world) == []  # 暗中的：不寫字
    assert w.event_mods["luzhi_jailed"] == pytest.approx(0.05)  # luzhi_jailed 擲「成」對黃巾有利
    rules.apply_effect(guan, game.state, on, game.world)
    assert w.event_mods["luzhi_jailed"] == pytest.approx(0.0)
    for _ in range(10):
        rules.apply_effect(guan, game.state, on, game.world)
    assert w.event_mods["luzhi_jailed"] == pytest.approx(-timetable.EVENT_MODS_CAP)  # 全服合計夾在 ±0.20
    _settle(game, "luzhi_jailed")
    before = dict(w.event_mods)
    rules.apply_effect(huang, game.state, on, game.world)
    assert w.event_mods == before  # 結算之後不再影響它


def test_the_patron_effect_sets_the_patron(on):
    game = _game(on, faction="haoqiang")
    assert rules.apply_effect(Effect(patron="cao"), game.state, on, game.world) == []
    assert game.state.player.patron == "cao"


def test_a_promotion_leg_effect_runs_before_the_promotion(on):
    """summons_next 在 promote 前面：同一個效果裡兩樣都有時，下一段的召見那一句先出（事件裡的順序才對）。"""
    _test_rank3(on)
    game = _game(on, faction="guan", at="luzhi_camp")
    _ready(game)
    ranks.check_summons(game.state, on)
    msgs = rules.apply_effect(Effect(summons_next="promo_guan_2", promote=3), game.state, on, game.world)
    assert msgs[0] == "送到洛陽宮城。" and "你升為軍司馬。" in msgs[1:]


def test_defecting_clears_the_qualification_the_hint_and_the_leg(on):
    game = _game(on, faction="guan", rank=3)
    p = game.state.player
    p.qualified, p.rank_hinted = True, [3, 4]
    p.summons = Summons(rank=3, location="luoyang_palace", leg=1, prev="promo_guan_2", event="promo_huang_2")
    defection.clear_progress(p)
    assert (p.rank, p.qualified, p.rank_hinted, p.summons) == (0, False, [], None)


def test_the_defection_prompt_names_a_pending_summons_and_the_qualified_title(on):
    _test_rank3(on)
    game = _game(on, faction="guan", at="changshe", rank=3)
    game.state.player.qualified = True
    target = on.scenario.faction("huang")
    text = defection.prompt(game.state, on, target, "（人數）")
    assert "身份歸零（你現在是軍司馬（校尉候缺））" in text


def test_a_summons_during_the_enlistment_still_works(on):
    """入伍段進行中收到召見：「應召」照常出、引薦人的框在晉升奇遇待處理時寫「先把眼前的…了結」（pending），不被召見改掉。"""
    _test_rank3(on)
    game = _game(on, at="changshe")
    p = game.state.player
    p.tutorial_step = 99  # 序章與舊引導都走完了
    game.choose("faction:guan")
    game.choose("faction:confirm")
    assert enlist.active(game.state, on)
    p.location = "luzhi_camp"
    _ready(game)
    ranks.check_summons(game.state, on)
    assert "act:summons" in [o.id for o in game.options(odds=False)]
    game.choose("act:summons")
    event = on.events["promo_guan_2"]
    assert game.state.pending_event == event.id
    box = game.guide_box()
    assert box["pending"] is True and box["text"] == f"先把眼前的「{event.title}」了結"
    assert enlist.active(game.state, on)  # 入伍段沒被召見動到


def _tell_hints(game):
    return [line for entry in game.state.journal for line in entry.guide if "上頭點你的名了" in line]


def _hear_only_the_promotion_hint(game):
    """引導都走完了、別的「碰到才說」都當作說過了（同一時間只有一條狀態提示在框上，別的會先佔住）：剩 h_promotion 還沒說。"""
    p = game.state.player
    p.tutorial_step = 99
    p.hints_seen |= {h.id for h in game.content.hints.hints} - {"h_promotion"}


def test_a_multi_leg_summons_says_the_promotion_hint_once(on):
    """h_promotion 是整局只說一次（hints_seen）：一份多段召見走完兩段、中途換人，也不會每一段說一次。"""
    _test_rank3(on)
    game = _game(on, faction="guan", at="luzhi_camp")
    p = game.state.player
    _hear_only_the_promotion_hint(game)
    _ready(game)
    game.sync(game.now + 1)  # 同步的最後檢查發召見、排提示、上框
    assert p.summons is not None and "h_promotion" in p.hints_seen
    assert len(_tell_hints(game)) == 1
    game.guide_ack()
    ranks.next_leg(game.state, on, "promo_guan_2")
    for _ in range(3):
        game._check_hints()  # noqa: SLF001
    game.sync(game.now + 1)
    assert [n.id for n in p.hint_queue] == [] and len(_tell_hints(game)) == 1
    _retire(game, "luzhi", "jailed")  # 發召見之後又換了版本也一樣
    game._check_hints()  # noqa: SLF001
    assert len(_tell_hints(game)) == 1


def test_a_player_who_heard_the_hint_at_rank_two_does_not_hear_it_again(on):
    _test_rank3(on)
    game = _game(on, faction="guan", at="luzhi_camp")
    p = game.state.player
    _hear_only_the_promotion_hint(game)
    p.hints_seen.add("h_promotion")  # 在第 2 階的召見聽過了
    _ready(game)
    game.sync(game.now + 1)
    assert p.summons is not None and _tell_hints(game) == [] and p.hint_queue == []
