"""第一季正式版・丙一：第 3、4 階晉升的機制，與官軍、豪強的四則奇遇（計畫 2026-10-06-第一季正式版-丙一）。

用真實內容（content/）：每個測試拿自己的一份（conftest.real_content 的複本），開關在測試裡才打開。
釘住的內容：content/promotions.json、content/events/promotion.json（scripts/test_for.py 改到這兩個檔時靠檔名挑到這裡）。"""
from __future__ import annotations

import random

import pytest
from pydantic import ValidationError

from conftest import FixedRandom, real_content
from tianxia import atlas, bot_policy, defection, enlist, figures, ranks, rules, timetable
from tianxia.content import ContentError, validate
from tianxia.engine import Game
from tianxia.models import Check, Config, Effect, EventMod, PatronLine, PromotionCast, PromotionDef, PromotionLeg
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
    for gone in ("promo_guan_3_memorial", "promo_guan_3_gift", "promo_guan_3_palace", "promo_guan_3_hejin"):
        real.events.pop(gone, None)  # 第一段（寫 summons_next）與最後一段（寫 promote／followers）的四則：沒有晉升認它們就過不了檢查


def _without_rank4(real):
    """拿掉真的官軍第 4 階與它的三則事件（何進一前一後、營中授印；Task 3 之後才有，同 _without_rank3）。"""
    real.promotions = [p for p in real.promotions if not (p.faction == "guan" and p.rank == 4)]
    for gone in ("promo_guan_4", "promo_guan_4_late", "promo_guan_4_camp"):
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


def test_rank_four_needs_legs_too(real):
    _without_rank4(real)
    real.promotions.append(PromotionDef(faction="guan", rank=4, closing="x"))
    with pytest.raises(ContentError, match="第 4 階要寫 legs") as caught:
        validate(real)
    assert "只能寫在晉升奇遇" not in str(caught.value)  # 真的第 4 階的三則事件都拿掉了：不會多出跟這個測試無關的錯誤


def test_a_rank_two_location_must_exist(real):
    """第 2 階的 location 還是照舊查（第 3、4 階的 location 空著、不查；第 2 階空著由上一個測試擋）。"""
    real.promotions = [p.model_copy(update={"location": "nowhere"}) if (p.faction == "guan" and p.rank == 2) else p
                       for p in real.promotions]
    with pytest.raises(ContentError, match="未知的地點 nowhere"):
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
    連同它兩段事件（寫了 promote／followers，沒有晉升定義認它們就過不了檢查）一起。
    借來的兩則事件原本寫 promote 2；放進第 3 階的各段，promote 要寫 3（載入時檢查），所以這裡改成 3。"""
    _without_rank3(real)
    for event_id in ("promo_guan_2", "promo_guan_2_handoff"):
        for choice in real.events[event_id].choices:
            for effect in (choice.effect, choice.fail_effect):
                if effect.promote is not None:
                    effect.promote = 3
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


def test_brush_off_offers_a_rank_up_only_where_the_rank_goes_up(on):
    """被打發時「或在官軍再升一階」只給真的會升階的人：升第 3 階是升階（求見門檻跟著降），第 4 階只是資格（候缺），
    rank 停在 3、門檻不降，所以第 2 階的人有這句，第 3 階的人（含已取得資格的）沒有。"""
    game = _game(on, faction="guan", rank=2)
    p = game.state.player
    p.stats["fame"] = rules.audience_bar(game.state, on, "luzhi") - 1
    assert "再升一階" in game._brush_off("luzhi")[0]  # noqa: SLF001
    p.rank = 3  # 升了第 3 階之後，下一階（第 4 階）只是資格
    p.stats["fame"] = rules.audience_bar(game.state, on, "luzhi") - 1
    assert "再升一階" not in game._brush_off("luzhi")[0]  # noqa: SLF001
    p.qualified = True
    assert "再升一階" not in game._brush_off("luzhi")[0]  # noqa: SLF001


def test_a_rank_three_member_is_not_promised_a_rank_up(on):
    """真的第 4 階（官軍：何進授印）有定義，rank_of + 1 找得到它；可是它不升階、求見門檻不降：被打發的話只寫還差多少，不許諾。
    取得資格之後門檻也一樣不降（audience_bar 不看資格）。"""
    assert any(x.faction == "guan" and x.rank == 4 for x in on.promotions)
    game = _game(on, faction="guan", rank=3)
    p = game.state.player
    bar = rules.audience_bar(game.state, on, "luzhi")
    p.stats["fame"] = bar - 1
    line = game._brush_off("luzhi")[0]  # noqa: SLF001
    assert "名望還差 1" in line and "再升" not in line
    p.qualified = True
    assert rules.audience_bar(game.state, on, "luzhi") == bar  # 資格不降門檻：上面不許諾，這裡也沒有騙人
    assert "再升" not in game._brush_off("luzhi")[0]  # noqa: SLF001


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


def test_a_figure_with_no_place_at_all_cannot_present(on):
    """版本寫了人物、沒寫 at，那位人物卻沒有所在（人物表裡沒有他：FigureState 的預設是在場、所在空字串）：不成立。
    不然召見的地點是 ""，寫召見那一句時查不到地點。"""
    promo = PromotionDef(faction="guan", rank=3, closing="（結尾）", legs=[
        PromotionLeg(casts=[PromotionCast(event="promo_guan_2", figure="ghost", summons_text="到{據點}。")]),
    ])
    game = _game(on, faction="guan")
    now = figures.state_of(game.state, on, "ghost")
    assert (now.status, now.location) == ("active", "")
    assert ranks.current_cast(game.state, on, promo, 0, None) is None


def test_no_summons_once_the_season_has_ended(on):
    _test_rank3(on)
    game = _game(on, faction="guan")
    _ready(game)
    game.state.world.ended = True
    assert ranks.check_summons(game.state, on) == [] and game.state.player.summons is None
    game.state.world.ended = False
    assert ranks.check_summons(game.state, on) == ["盧植召你到盧植營。"]


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


def test_the_defection_prompt_names_the_qualified_title(on):
    game = _game(on, faction="guan", at="changshe", rank=3)
    game.state.player.qualified = True
    target = on.scenario.faction("huang")
    text = defection.prompt(game.state, on, target, "（人數）")
    assert "身份歸零（你現在是軍司馬（校尉候缺））" in text


def test_the_defection_prompt_names_a_pending_two_leg_summons(on):
    """召見走到第二段還沒演完也算「還沒去的召見」：確認畫面寫它會作廢。"""
    game = _game(on, faction="guan", at="luzhi_camp")
    _summon_to(game, 3, "guan")
    game.choose("act:summons")
    game.choose("choice:0")
    assert game.state.player.summons.leg == 1
    text = defection.prompt(game.state, on, on.scenario.faction("huang"), "（人數）")
    assert "還沒去的召見作廢" in text
    game.state.player.summons = None
    assert "還沒去的召見作廢" not in defection.prompt(game.state, on, on.scenario.faction("huang"), "（人數）")


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


# ── Task 3：官軍、豪強的第 3、4 階奇遇（內容）─────────────────


def _summon_to(game, rank, faction):
    _ready(game, rank=rank - 1, contrib=10**6)
    return ranks.check_summons(game.state, game.content)


def test_guan_rank_three_two_legs(on):
    game = _game(on, faction="guan", at="luzhi_camp")
    assert _summon_to(game, 3, "guan") == ["盧植派人來找你：到盧植營見他。"]
    game.choose("act:summons")
    msgs = game.choose("choice:0")
    assert "把盧植的奏表送到洛陽宮城。" in msgs and game.state.player.summons.location == "luoyang_palace"
    game.state.player.location = "luoyang_palace"
    game.choose("act:summons")
    msgs = game.choose("choice:1")
    p = game.state.player
    assert "你升為軍司馬。" in msgs and p.rank == 3 and p.followers[-1] == "follower_guan_spear"


def test_bribe_after_the_jailing_changes_nothing(on):
    game = _game(on, faction="guan", at="dajiangjun_fu")
    w = game.state.world
    w.timeline["luzhi_jailed"] = TimelineResult(key="成", time=w.time)
    _summon_to(game, 4, "guan")
    assert game.state.player.summons.event == "promo_guan_4_late"
    game.choose("act:summons")
    game.choose("choice:1")
    assert w.event_mods.get("luzhi_jailed", 0.0) == 0.0 and game.state.player.qualified


def test_refusing_the_bribe_helps_luzhi(on):
    game = _game(on, faction="guan", at="dajiangjun_fu")
    _summon_to(game, 4, "guan")
    game.choose("act:summons")
    game.choose("choice:1")  # 拒絕
    event = next(e for e in on.timetable if e.id == "luzhi_jailed")
    expected = 0.05 if event.roll_side == "guan" else -0.05
    assert game.state.world.event_mods["luzhi_jailed"] == pytest.approx(expected)


def test_bribe_mods_are_capped(on):
    game = _game(on, faction="guan")
    for _ in range(10):
        rules.apply_effect(Effect(event_mods=[{"event": "luzhi_jailed", "side": "guan", "amount": 0.05}]),
                           game.state, on, game.world)
    assert abs(game.state.world.event_mods["luzhi_jailed"]) == pytest.approx(timetable.EVENT_MODS_CAP)


def test_hao_rank_three_sets_the_patron(on):
    game = _game(on, faction="haoqiang", at="runan")
    _summon_to(game, 3, "haoqiang")
    game.choose("act:summons")
    game.choose("choice:1")
    assert (game.state.player.patron, game.state.player.rank) == ("cao", 3)


def test_hao_rank_four_reacts_to_the_patron(on):
    game = _game(on, faction="haoqiang", at="loushang_village")
    game.state.player.patron = "self"
    _summon_to(game, 4, "haoqiang")
    game.choose("act:summons")
    msgs = game.choose("choice:0")
    assert "劉備笑了：「都是白手起家。」" in msgs and "你取得一方之主的資格，候缺。" in msgs


def test_camp_version_when_hejin_is_out(on):
    game = _game(on, faction="guan", at="changshe")
    _retire(game, "hejin", "crippled")
    assert _summon_to(game, 4, "guan") == ["皇甫嵩召你到長社營中授印。"]
    assert game.state.player.summons.location == "changshe"


# 以下是這個任務自己多寫的：內容的結構、每條路、兩句修過的話、m3


def test_the_real_promotions_are_defined(on):
    by = {(p.faction, p.rank): p for p in on.promotions}
    assert {"guan", "haoqiang"} <= {faction for faction, rank in by if rank == 3}
    assert {"guan", "haoqiang"} <= {faction for faction, rank in by if rank == 4}
    guan3, guan4, hao3, hao4 = by[("guan", 3)], by[("guan", 4)], by[("haoqiang", 3)], by[("haoqiang", 4)]
    assert [[c.event for c in leg.casts] for leg in guan3.legs] == [
        ["promo_guan_3_memorial", "promo_guan_3_gift"], ["promo_guan_3_palace", "promo_guan_3_hejin"]]
    assert [(c.figure, c.at, c.after) for c in guan3.legs[0].casts] == [
        ("luzhi", "luzhi_camp", None), ("dongzhuo", "luzhi_camp", None)]
    assert [(c.figure, c.at, c.after) for c in guan3.legs[1].casts] == [
        (None, "luoyang_palace", "promo_guan_3_memorial"), (None, "dajiangjun_fu", "promo_guan_3_gift")]
    assert guan3.closing == "又撥了一個鄉勇到你帳下：「軍司馬，往後聽你調遣。」"  # 原稿「營裡又撥…」：這一句在洛陽宮城或大將軍府演完，不在營裡（待 joy 潤）
    assert len(guan4.legs) == 1
    assert [(c.event, c.figure, c.at, c.before_event) for c in guan4.legs[0].casts] == [
        ("promo_guan_4", "hejin", "dajiangjun_fu", "luzhi_jailed"), ("promo_guan_4_late", "hejin", "dajiangjun_fu", None),
        ("promo_guan_4_camp", "huangfusong", None, None), ("promo_guan_4_camp", "zhujun", None, None)]
    assert [c.summons_text for c in guan4.legs[0].casts] == [
        "何進召你到{據點}。", "何進召你到{據點}。", "皇甫嵩召你到{據點}營中授印。", "朱儁召你到{據點}營中授印。"]
    assert guan4.closing == "又一個鄉勇撥到你帳下。校尉的缺一空出來，你就領兵。"
    assert [(leg.location, [c.event for c in leg.casts]) for leg in hao3.legs] == [("runan", ["promo_hao_3"])]
    assert [(leg.location, [c.event for c in leg.casts]) for leg in hao4.legs] == [("loushang_village", ["promo_hao_4"])]
    assert hao3.closing == "一個門客收拾了行囊，跟到你身邊：「往後替您跑腿。」"
    assert hao4.closing == "一個家養部曲扛著刀跟了上來：「一方之主，往後這條命是您的。」"
    assert {k: (v.text, v.affinity) for k, v in hao4.patron_lines.items()} == {
        "yuan": ("關羽冷冷道：「四世三公的門客？」", {"guanyu": -3}),
        "cao": ("劉備頓了一下：「曹孟德的人……也好。」", {}),
        "self": ("劉備笑了：「都是白手起家。」", {"liubei": 5}),
    }
    assert guan3.patron_lines == guan4.patron_lines == hao3.patron_lines == {}


def test_the_new_events_are_wired_to_their_legs(on):
    """第一段的事件選項寫 summons_next（自己的 id）、不晉升；最後一段每個選項（含檢定輸的那一邊）晉升到那一階、給那一階的部下。"""
    first_leg = {"promo_guan_3_memorial", "promo_guan_3_gift"}
    followers = {
        "promo_guan_3_palace": (3, ["follower_guan_spear"]), "promo_guan_3_hejin": (3, ["follower_guan_spear"]),
        "promo_guan_4": (4, ["follower_guan_crossbow"]), "promo_guan_4_late": (4, ["follower_guan_crossbow"]),
        "promo_guan_4_camp": (4, ["follower_guan_crossbow"]),
        "promo_hao_3": (3, ["follower_haoqiang_retainer"]), "promo_hao_4": (4, ["follower_haoqiang_buqu"]),
    }
    for event_id in first_leg:
        event = on.events[event_id]
        assert event.actions == [] and len(event.choices) == 1
        for choice in event.choices:
            assert choice.effect.summons_next == event_id and choice.effect.promote is None and not choice.effect.followers
    for event_id, (rank, given) in followers.items():
        event = on.events[event_id]
        assert event.actions == [] and len(event.choices) == 3
        for choice in event.choices:
            slots = [choice.effect, choice.fail_effect] if choice.check is not None else [choice.effect]
            for effect in slots:
                assert (effect.promote, effect.followers, effect.summons_next) == (rank, given, None)
    titles = {event_id: on.events[event_id].title for event_id in [*first_leg, *followers]}
    assert titles == {
        "promo_guan_3_memorial": "晉升・盧植營", "promo_guan_3_gift": "晉升・盧植營", "promo_guan_3_palace": "晉升・洛陽宮城",
        "promo_guan_3_hejin": "晉升・大將軍府", "promo_guan_4": "晉升・大將軍府", "promo_guan_4_late": "晉升・大將軍府",
        "promo_guan_4_camp": "晉升・營中授印", "promo_hao_3": "晉升・汝南酒樓", "promo_hao_4": "晉升・樓桑里",
    }


def test_bribe_mods_only_name_the_jailing_and_only_the_bribe_events_write_them(on):
    writers = {}
    for event in on.events.values():
        for choice in event.choices:
            for effect in (choice.effect, choice.fail_effect):
                for mod in effect.event_mods:
                    assert (mod.event, mod.amount) == ("luzhi_jailed", 0.05)
                    writers.setdefault(event.id, []).append(mod.side)
    assert writers == {"promo_guan_4": ["huang", "guan", "guan"], "promo_guan_4_camp": ["huang", "guan", "guan"]}
    assert [c.effect.event_mods for c in on.events["promo_guan_4_late"].choices] == [[], [], []]  # 結算之後不分前後兩版：這一則本來就不寫


def test_the_patron_is_only_written_by_the_two_families_scene(on):
    patrons = {
        event.id: [choice.effect.patron for choice in event.choices]
        for event in on.events.values() if any(choice.effect.patron for choice in event.choices)
    }
    assert patrons == {"promo_hao_3": ["yuan", "cao", "self"]}


@pytest.mark.parametrize("choice, silver, affinity, text", [
    (0, 0, {}, "奏表照常遞了上去，從此石沉大海。"),
    (1, 0, {}, None),
    (2, -20, {"luzhi": -10}, "黃門掂了掂錢袋，奏表遞上去了。盧植事後知道了這件事。"),
])
def test_every_palace_ending_makes_a_sima(on, choice, silver, affinity, text):
    game = _game(on, faction="guan", at="luoyang_palace")
    p = game.state.player
    p.stats["silver"] = 100
    p.affinities["luzhi"] = 50
    _summon_to(game, 3, "guan")
    p.summons.leg, p.summons.prev = 1, "promo_guan_3_memorial"
    ranks.check_summons(game.state, on)
    assert p.summons.event == "promo_guan_3_palace" and p.summons.location == "luoyang_palace"
    game.choose("act:summons")
    msgs = game.choose(f"choice:{choice}")
    assert "你升為軍司馬。" in msgs and p.rank == 3 and p.followers == ["follower_guan_spear"] and p.summons is None
    assert p.stats["silver"] == 100 + silver and p.affinities["luzhi"] == 50 + affinity.get("luzhi", 0)
    if text is not None:
        assert text in msgs
    assert any(r.text == "甲升為軍司馬。" and r.faction == "guan" for r in game.state.world.rumors)


def test_asking_the_grand_general_to_present_it_stays_at_the_palace(on):
    """NF3：奏表當場轉交——選項的反應不寫「轉身去了大將軍府」，人還在洛陽宮城（這個選項照舊往官軍推冀州一點）。"""
    game = _game(on, faction="guan", at="luoyang_palace")
    _summon_to(game, 3, "guan")
    p = game.state.player
    p.summons.leg, p.summons.prev = 1, "promo_guan_3_memorial"
    ranks.check_summons(game.state, on)
    jizhou = game.state.world.trends["jizhou"]
    game.choose("act:summons")
    msgs = game.choose("choice:1")
    text = on.events["promo_guan_3_palace"].choices[1].effect.text
    assert text == "你報出大將軍的名號，請他的人當場代呈。外戚樂得讓宦官難看，奏表很快遞了上去。"
    assert text in msgs and "轉身去了大將軍府" not in "".join(msgs)
    assert p.location == "luoyang_palace" and p.rank == 3
    assert game.state.world.trends["jizhou"] == jizhou - 1 and "冀州：官軍小有進展" in msgs  # 外戚得意：冀州往官軍推一點，不寫數字


@pytest.mark.parametrize("choice, affinity, silver", [(0, 5, 0), (1, -5, 0), (2, -15, 30)])
def test_the_dongzhuo_way_to_rank_three(on, choice, affinity, silver):
    """盧植不在（下獄）、董卓接手：盧植營的第一段演送禮，第二段是大將軍府，不看董卓在不在；三個選項都晉升。"""
    game = _game(on, faction="guan", at="luzhi_camp")
    p = game.state.player
    p.stats["silver"] = 100
    p.affinities["dongzhuo"] = 40
    _retire(game, "luzhi", "jailed")
    game.state.world.figures["dongzhuo"] = figures.state_of(game.state, on, "dongzhuo").model_copy(
        update={"front": "jizhou", "location": "luzhi_camp"})
    assert _summon_to(game, 3, "guan") == ["董卓派人來找你：到盧植營見他。"]
    game.choose("act:summons")
    assert "把董卓的厚禮送進大將軍府。" in game.choose("choice:0")
    _retire(game, "dongzhuo", "crippled")  # 第二段不看董卓在不在
    p.location = "dajiangjun_fu"
    assert ranks.summons_event(game.state, on) == "promo_guan_3_hejin"
    game.choose("act:summons")
    msgs = game.choose(f"choice:{choice}")
    assert "你升為軍司馬。" in msgs and (p.rank, p.location) == (3, "dajiangjun_fu")
    assert p.affinities["dongzhuo"] == 40 + affinity and p.stats["silver"] == 100 + silver


def test_advising_dongzhuo_not_to_send_it_keeps_the_player_at_the_office(on):
    """NF3：勸他別送發生在大將軍府、董卓不在場：反應不寫「抬回營中」，人還在大將軍府。"""
    game = _game(on, faction="guan", at="dajiangjun_fu")
    p = game.state.player
    _summon_to(game, 3, "guan")
    p.summons.leg, p.summons.prev = 1, "promo_guan_3_gift"
    ranks.check_summons(game.state, on)
    assert p.summons.event == "promo_guan_3_hejin"
    game.choose("act:summons")
    msgs = game.choose("choice:1")
    text = on.events["promo_guan_3_hejin"].choices[1].effect.text
    assert text == "你把箱子原樣退給門吏，託人捎話給董卓：這份禮送不得。事後董卓瞇起眼看了你半晌，把禮收了回去。"
    assert text in msgs and "抬回營中" not in "".join(msgs) and p.location == "dajiangjun_fu"


@pytest.mark.parametrize("choice, silver, mods, hejin", [(0, -50, 0.05, 0), (1, 0, -0.05, 0), (2, 0, -0.05, 5)])
def test_every_seal_ending_grants_the_qualification(on, choice, silver, mods, hejin):
    """第 4 階（何進版）：三個選項都取得資格（軍司馬不變）、給弩手；給錢往黃巾加一點、其他往官軍加一點；告訴大將軍的得何進情誼。"""
    game = _game(on, faction="guan", at="dajiangjun_fu")
    p = game.state.player
    p.stats["silver"] = 100
    p.affinities["hejin"] = 20
    _summon_to(game, 4, "guan")
    game.choose("act:summons")
    msgs = game.choose(f"choice:{choice}")
    assert "你取得校尉的資格，候缺。" in msgs and (p.rank, p.qualified) == (3, True)
    assert p.followers == ["follower_guan_crossbow"] and p.summons is None and p.stats["silver"] == 100 + silver
    assert p.affinities["hejin"] == 20 + hejin
    roll_side = next(e.roll_side for e in on.timetable if e.id == "luzhi_jailed")  # 擲「成」對誰有利
    sign = 1 if roll_side == "huang" else -1
    assert game.state.world.event_mods["luzhi_jailed"] == pytest.approx(sign * mods)
    assert ranks.title(on, game.state) == "校尉" and "你補上了校尉的缺，到下週一為止。" in msgs  # 席次空著：當下補上（正式版丁）
    assert any(r.text == "甲取得校尉的資格，候缺。" and r.faction == "guan" for r in game.state.world.rumors)
    assert ranks.check_summons(game.state, on) == []


def test_after_the_jailing_the_refusal_remembers_the_prisoner(on):
    game = _game(on, faction="guan", at="dajiangjun_fu")
    w = game.state.world
    w.timeline["luzhi_jailed"] = TimelineResult(key="成", time=w.time)
    p = game.state.player
    _summon_to(game, 4, "guan")
    game.choose("act:summons")
    msgs = game.choose("choice:1")
    assert "小黃門的笑僵在臉上。你想起廣宗城下那個寧可下獄也不肯低頭的人。" in msgs and p.qualified


def test_the_seal_event_changes_with_the_jailing_while_the_summons_stays_quiet(on):
    """N4：盧植下獄那一刻，手上的何進召見悄悄換成「之後」那一版，同一句話不重複寫。"""
    game = _game(on, faction="guan", at="changshe")
    p = game.state.player
    assert _summon_to(game, 4, "guan") == ["何進召你到大將軍府。"] and p.summons.event == "promo_guan_4"
    w = game.state.world
    w.timeline["luzhi_jailed"] = TimelineResult(key="成", time=w.time)
    assert ranks.check_summons(game.state, on) == [] and p.summons.event == "promo_guan_4_late"


def test_the_camp_version_pays_the_same_way(on):
    game = _game(on, faction="guan", at="changshe")
    p = game.state.player
    p.stats["silver"] = 100
    _retire(game, "hejin", "crippled")
    _summon_to(game, 4, "guan")
    assert p.summons.event == "promo_guan_4_camp" and p.summons.figure == "huangfusong"
    game.choose("act:summons")
    msgs = game.choose("choice:0")  # 給他
    assert "監軍把錢收進袖裡。" in msgs and (p.qualified, p.stats["silver"]) == (True, 50)
    roll_side = next(e.roll_side for e in on.timetable if e.id == "luzhi_jailed")
    assert game.state.world.event_mods["luzhi_jailed"] == pytest.approx(0.05 if roll_side == "huang" else -0.05)


def test_the_camp_version_passes_to_zhujun_when_huangfusong_is_out_too(on):
    game = _game(on, faction="guan", at="changshe")
    _retire(game, "hejin", "crippled")
    _retire(game, "huangfusong", "retired")
    assert _summon_to(game, 4, "guan") == ["朱儁召你到長社營中授印。"]
    assert game.state.player.summons.figure == "zhujun"


def test_nobody_to_present_rank_four_means_no_summons(on):
    """N6：何進、皇甫嵩、朱儁都不在場：先不發（不發一張找不到人的召見），之後有人回來才發。"""
    game = _game(on, faction="guan", at="changshe")
    for fid in ("hejin", "huangfusong", "zhujun"):
        _retire(game, fid, "retired")
    assert _summon_to(game, 4, "guan") == [] and game.state.player.summons is None
    game.state.world.figures["zhujun"] = figures.state_of(game.state, on, "zhujun").model_copy(update={"status": "active"})
    assert ranks.check_summons(game.state, on) == ["朱儁召你到長社營中授印。"]


@pytest.mark.parametrize("choice, patron, affinity, fame_gain", [
    (0, "yuan", {"yuanshao": 15, "caocao": -5}, 0),
    (1, "cao", {"caocao": 15, "yuanshao": -5}, 0),
    (2, "self", {"yuanshao": -3, "caocao": -3}, 2),
])
def test_every_hao_rank_three_choice_sets_a_patron(on, choice, patron, affinity, fame_gain):
    game = _game(on, faction="haoqiang", at="runan")
    p = game.state.player
    p.affinities.update({"yuanshao": 30, "caocao": 30})
    fame = p.stats.get("fame", 0)
    _summon_to(game, 3, "haoqiang")
    game.choose("act:summons")
    msgs = game.choose(f"choice:{choice}")
    assert (p.patron, p.rank, p.followers) == (patron, 3, ["follower_haoqiang_retainer"])
    assert {k: p.affinities[k] for k in ("yuanshao", "caocao")} == {k: 30 + v for k, v in affinity.items()}
    assert p.stats.get("fame", 0) == fame + fame_gain and "你升為地方豪強。" in msgs


@pytest.mark.parametrize("patron, line, shift", [
    ("yuan", "關羽冷冷道：「四世三公的門客？」", ("guanyu", -3)),
    ("cao", "劉備頓了一下：「曹孟德的人……也好。」", None),
    ("self", "劉備笑了：「都是白手起家。」", ("liubei", 5)),
    (None, None, None),
])
def test_hao_rank_four_line_for_every_patron(on, patron, line, shift):
    game = _game(on, faction="haoqiang", at="loushang_village")
    p = game.state.player
    p.patron = patron
    p.affinities.update({"guanyu": 30, "liubei": 30, "zhangfei": 30})
    _summon_to(game, 4, "haoqiang")
    game.choose("act:summons")
    msgs = game.choose("choice:0")  # 好，結盟
    said = [m for m in msgs if m.startswith(("關羽冷冷道", "劉備頓了一下", "劉備笑了"))]
    assert said == ([line] if line else [])
    base = {"liubei": 40, "guanyu": 35}  # 結盟本身 +10／+5（張飛 +5）
    if shift is not None:
        base[shift[0]] += shift[1]
    assert (p.affinities["liubei"], p.affinities["guanyu"]) == (base["liubei"], base["guanyu"])
    assert p.affinities["zhangfei"] == 35
    assert "你取得一方之主的資格，候缺。" in msgs and p.qualified and p.followers == ["follower_haoqiang_buqu"]


@pytest.mark.parametrize("win, text, zhang, guan", [
    (True, "你把張飛摔了個四腳朝天，他爬起來大笑：「好！這盟我結！」", 10, -3),
    (False, "張飛把你按在地上，大笑著把你拉起來：「有種！這盟我結！」", 5, -3),
])
def test_the_wrestling_oath_promotes_whether_you_win_or_lose(on, win, text, zhang, guan):
    """檢定輸了也晉升（儀式不是考試）：兩邊都取得資格、給部曲，只有情誼和那一句不同。"""
    game = _game(on, faction="haoqiang", at="loushang_village")
    p = game.state.player
    p.affinities.update({"zhangfei": 30, "guanyu": 30})
    _summon_to(game, 4, "haoqiang")
    game.rng = FixedRandom(0.0 if win else 0.99)
    game.choose("act:summons")
    msgs = game.choose("choice:2")
    assert text in msgs and "你取得一方之主的資格，候缺。" in msgs
    assert (p.affinities["zhangfei"], p.affinities["guanyu"]) == (30 + zhang, 30 + guan)
    assert p.qualified and p.followers == ["follower_haoqiang_buqu"] and p.summons is None


def test_the_wrestling_check_stays_in_the_danger_band(on):
    """B3：樓桑里的事件沒有地點與標籤，危險度 1，難度帶 3～6（tests/test_real_content.py 鎖著）：臂力 6。"""
    choice = on.events["promo_hao_4"].choices[2]
    assert (choice.check.stat, choice.check.difficulty) == ("str", 6)
    assert [c.check for c in on.events["promo_hao_4"].choices[:2]] == [None, None]


def test_a_whole_guan_career_from_rank_two_to_the_qualification(on):
    """從第 2 階走到資格：貢獻到了、機緣先沒有——只說一次 HINT；補上機緣才收到召見；兩段演完升第 3 階，然後同樣的路上第 4 階。"""
    game = _game(on, faction="guan", at="luzhi_camp")
    p = game.state.player
    p.rank, p.contrib = 2, 10**6
    assert ranks.check_summons(game.state, on) == [ranks.HINT]
    assert ranks.check_summons(game.state, on) == []
    _ready(game, rank=2, contrib=10**6)
    assert ranks.check_summons(game.state, on) == ["盧植派人來找你：到盧植營見他。"]
    game.choose("act:summons")
    game.choose("choice:0")
    p.location = "luoyang_palace"
    game.choose("act:summons")
    msgs = game.choose("choice:0")
    assert p.rank == 3 and ranks.HINT in msgs  # 第 4 階的進度到了、機緣還沒有：升階的那一下行動最後的檢查就說了
    assert p.rank_hinted == [3, 4] and ranks.check_summons(game.state, on) == []
    _ready(game, rank=3, contrib=10**6)  # 補上第 4 階的機緣
    assert ranks.check_summons(game.state, on) == ["何進召你到大將軍府。"]
    p.location = "dajiangjun_fu"
    game.choose("act:summons")
    game.choose("choice:2")
    assert (p.rank, p.qualified, p.summons, p.followers) == (
        3, True, None, ["follower_guan_spear", "follower_guan_crossbow"])
    assert ranks.title(on, game.state) == "校尉"  # 席次空著：取得資格的同一個動作補上（正式版丁）


@pytest.mark.parametrize("slot", ["effect", "fail_effect"])
def test_promote_and_followers_are_checked_in_the_fail_effect_too(real, slot):
    """m3（Task 1 review）：promote／followers 只能寫在晉升奇遇的選項上，成功與失敗兩邊都查（promo_hao_4 是第一則在 fail_effect 用到的）。"""
    stray = next(e for e in real.events.values() if not e.id.startswith("promo_") and e.choices)
    setattr(stray.choices[0], slot, Effect(promote=3))
    with pytest.raises(ContentError, match="promote／followers 只能寫在晉升奇遇"):
        validate(real)


def test_followers_in_the_fail_effect_must_belong_to_the_faction(real):
    real.events["promo_hao_4"].choices[2].fail_effect.followers = ["follower_guan_spear"]
    with pytest.raises(ContentError, match="給的部下要是 haoqiang 的"):
        validate(real)
    real.events["promo_hao_4"].choices[2].fail_effect.followers = ["follower_no_such"]
    with pytest.raises(ContentError, match="follower_no_such"):
        validate(real)


# ── 修正一輪（Task 2、3 審查）─────────────────────────────────


def test_the_swap_from_huangfusong_to_zhujun_is_announced(on):
    """T2 審查 m1：營中授印的兩個版本（皇甫嵩、朱儁）事件 id 一樣、地點也一樣（長社）。皇甫嵩退場、朱儁接手時，手上那張召見
    讀起來變了——要告訴玩家：召見那一句本身就寫著新的人（寫進江湖紀錄、主線與目標也換），召見記的出面的人也跟著換。"""
    game = _game(on, faction="guan", at="changshe")
    p = game.state.player
    _hear_only_the_promotion_hint(game)
    _retire(game, "hejin", "crippled")
    game.world.save_season(game.state.world)  # sync 讀的是全服狀態裡的那一份，人物的改動要先存進去
    _ready(game, rank=3, contrib=10**6)
    game.sync(game.now + 1)
    assert p.summons.event == "promo_guan_4_camp" and p.summons.figure == "huangfusong"
    assert "**召見**：皇甫嵩召你到長社營中授印。" in game.quest_text()
    _retire(game, "huangfusong", "retired")
    game.world.save_season(game.state.world)
    game.sync(game.now + 1)
    assert (p.summons.event, p.summons.figure, p.summons.location) == ("promo_guan_4_camp", "zhujun", "changshe")
    entry = game.state.journal[0]
    assert (entry.title, entry.lines) == ("召見", ["朱儁召你到長社營中授印。"])  # 玩家讀得到：換成朱儁了
    assert "**召見**：朱儁召你到長社營中授印。" in game.quest_text()
    game.sync(game.now + 1)
    assert game.state.journal[0] is entry or game.state.journal[0] == entry  # 不重複寫


def test_the_two_leg_walk_through_the_menu(on):
    """從發召見到升階，全程走 Game 的公開行動（sync、選單、choose）：第一段在盧植營，第二段在洛陽宮城；每一步召見記的段、事件、
    地點對得上，「應召」只在該去的地方出現，下一段的召見那一句在晉升之前出，存檔讀回來還在同一段、不重複說。"""
    from tianxia.characters import open_characters

    def usable(g):
        return [o.id for o in g.options(odds=False) if o.enabled]

    game = _game(on, faction="guan", at="luzhi_camp")
    p = game.state.player
    _hear_only_the_promotion_hint(game)
    _ready(game, rank=2, contrib=900)
    assert game.state.pending_event is None and p.summons is None
    game.sync(game.now + 1)  # 召見在同步的最後檢查發出來
    s = p.summons
    assert (s.rank, s.leg, s.prev, s.event, s.location, s.figure) == (
        3, 0, None, "promo_guan_3_memorial", "luzhi_camp", "luzhi")
    assert (game.state.journal[0].title, game.state.journal[0].lines) == ("召見", ["盧植派人來找你：到盧植營見他。"])
    assert "act:summons" in usable(game)

    game.choose("act:summons")
    assert game.state.pending_event == "promo_guan_3_memorial" and p.rank == 2
    msgs = game.choose("choice:0")
    assert msgs[:3] == ["▸ 「末將這就去。」", "你把竹簡貼身收好。", "把盧植的奏表送到洛陽宮城。"]
    assert game.state.pending_event is None and p.rank == 2
    assert (s.leg, s.prev, s.event, s.location, s.figure) == (
        1, "promo_guan_3_memorial", "promo_guan_3_palace", "luoyang_palace", None)
    assert "act:summons" not in usable(game)  # 人還在盧植營
    assert "**召見**：把盧植的奏表送到洛陽宮城。" in game.quest_text()

    open_characters().save(game.state)  # 存檔讀回來：同一段、不重複說
    again = Game(on, open_characters().load("甲"))
    again.client = None
    s = again.state.player.summons
    assert (s.leg, s.prev, s.event, s.location) == (1, "promo_guan_3_memorial", "promo_guan_3_palace", "luoyang_palace")
    before = len(again.state.journal)
    again.sync(again.now + 1)
    assert not [e for e in again.state.journal[: len(again.state.journal) - before] if e.title == "召見"]
    game, p = again, again.state.player

    p.location = "luoyang_palace"  # 路上的事不在這個測試裡
    assert "act:summons" in usable(game)
    game.choose("act:summons")
    assert game.state.pending_event == "promo_guan_3_palace"
    msgs = game.choose("choice:0")
    assert msgs[:2] == ["▸ 「照規矩交給黃門。」", "奏表照常遞了上去，從此石沉大海。"]
    closing = on.promotions[[(x.faction, x.rank) for x in on.promotions].index(("guan", 3))].closing
    order = [msgs.index(line) for line in ("你升為軍司馬。", closing, "獲得部下：持矛鄉勇")]
    assert order == sorted(order)
    assert (p.rank, p.summons, p.followers, game.state.pending_event) == (3, None, ["follower_guan_spear"], None)
    assert any(r.text == "甲升為軍司馬。" and r.faction == "guan" for r in game.state.world.rumors)
    assert ranks.check_summons(game.state, on) == [] and "act:summons" not in usable(game)


# ── 最終審查後的修正（I1 不許諾、m1 開著的那一幕、m3 載入檢查）─────────


def test_an_open_scene_is_not_swapped_under_the_player(on):
    """最終審查 m1：盧植的那一幕已經開著（事件待處理），這時盧植下獄、董卓接手：召見與主線與目標都不換——畫面上演的還是盧植
    交奏表。選了之後照演的那一則走到下一段；下一次檢查才照新的時局挑。"""
    game = _game(on, faction="guan", at="luzhi_camp")
    p = game.state.player
    _hear_only_the_promotion_hint(game)
    _ready(game, rank=2, contrib=900)
    game.sync(game.now + 1)
    assert p.summons.event == "promo_guan_3_memorial"
    game.choose("act:summons")
    assert game.state.pending_event == "promo_guan_3_memorial"

    _retire(game, "luzhi", "jailed")
    game.state.world.figures["dongzhuo"] = figures.state_of(game.state, on, "dongzhuo").model_copy(
        update={"front": "jizhou", "location": "luzhi_camp"})
    game.world.save_season(game.state.world)
    before = len(game.state.journal)
    game.sync(game.now + 1)
    assert not [e for e in game.state.journal[: len(game.state.journal) - before] if e.title == "召見"]
    assert (p.summons.event, p.summons.figure) == ("promo_guan_3_memorial", "luzhi")
    assert "**召見**：盧植派人來找你：到盧植營見他。" in game.quest_text()  # 主線與目標也還是盧植

    msgs = game.choose("choice:0")  # 演完這一幕：照演的那一則走到下一段
    assert "把盧植的奏表送到洛陽宮城。" in msgs
    assert (p.summons.leg, p.summons.prev, p.summons.event) == (1, "promo_guan_3_memorial", "promo_guan_3_palace")


def test_an_open_scene_counts_for_any_version_of_the_leg(on):
    """開著的那一幕是這一段任何一個版本的事件都算（盧植版、董卓版），不是下一段的事件，也不是沒有待處理的事件。"""
    game = _game(on, faction="guan", at="luzhi_camp")
    _ready(game, rank=2, contrib=900)
    ranks.check_summons(game.state, on)
    promo = ranks.promotion_for(on, "guan", 3)
    assert ranks._scene_open(game.state, promo) is False  # noqa: SLF001
    for event_id in ("promo_guan_3_memorial", "promo_guan_3_gift"):
        game.state.pending_event = event_id
        assert ranks._scene_open(game.state, promo) is True  # noqa: SLF001
    game.state.pending_event = "promo_guan_3_palace"  # 下一段的事件
    assert ranks._scene_open(game.state, promo) is False  # noqa: SLF001


def test_the_swap_is_announced_once_no_scene_is_open(on):
    """對照：沒有開著的那一幕時，盧植下獄、董卓接手照舊換、照舊說（見 test_jailed_luzhi_hands_the_first_leg_to_dongzhuo）。"""
    game = _game(on, faction="guan", at="luzhi_camp")
    p = game.state.player
    _hear_only_the_promotion_hint(game)
    _ready(game, rank=2, contrib=900)
    game.sync(game.now + 1)
    _retire(game, "luzhi", "jailed")
    game.state.world.figures["dongzhuo"] = figures.state_of(game.state, on, "dongzhuo").model_copy(
        update={"front": "jizhou", "location": "luzhi_camp"})
    game.world.save_season(game.state.world)
    game.sync(game.now + 1)
    assert p.summons.event == "promo_guan_3_gift"
    assert (game.state.journal[0].title, game.state.journal[0].lines) == ("召見", ["董卓派人來找你：到盧植營見他。"])


def test_a_leg_event_promotes_to_its_own_rank(real):
    """最終審查 m3(a)：第 4 階的奇遇選項 promote 寫成 3，每按一次「應召」就再升一次第 3 階、多一則軍情與一名部下：載入時擋下。"""
    real.events["promo_guan_4"].choices[0].effect.promote = 3
    with pytest.raises(ContentError, match="promo_guan_4：promote 要寫 4"):
        validate(real)


def test_a_failed_check_promotes_to_its_own_rank_too(real):
    real.events["promo_hao_4"].choices[2].fail_effect.promote = 3
    with pytest.raises(ContentError, match="promo_hao_4：promote 要寫 4"):
        validate(real)


@pytest.mark.parametrize("value", [0, 1, 5, 9])
def test_promote_stays_within_the_ranks_that_exist(real, value):
    """最終審查 m3(c)：promote 只能是 2～4（有頭銜的階）；大了會在 ranks.promote 查頭銜表時 IndexError。"""
    real.events["promo_guan_4"].choices[0].effect.promote = value
    with pytest.raises(ContentError, match="promote 要在 2～4 之間"):
        validate(real)


def test_a_first_leg_choice_must_move_the_summons_on_or_end_it(real):
    """最終審查 m3(b)：非最後一段的奇遇，選項沒寫 summons_next 也沒晉升，召見留在原地、「應召」（不花體力）又能重演同一幕，
    獎勵白拿（審查實測銀兩 50 → 140）：載入時擋下。"""
    real.events["promo_guan_3_memorial"].choices[0].effect = Effect(text="x", stats={"silver": 30})
    with pytest.raises(ContentError, match="promo_guan_3_memorial：.*summons_next（往下一段）或 promote"):
        validate(real)


def test_a_first_leg_check_must_move_on_in_both_outcomes(real):
    choice = real.events["promo_guan_3_memorial"].choices[0]
    choice.check = Check(stat="str", difficulty=4)  # 檢定輸的那一邊沒寫 summons_next：輸了就重演
    with pytest.raises(ContentError, match="promo_guan_3_memorial：.*summons_next（往下一段）或 promote"):
        validate(real)
    choice.fail_effect = Effect(summons_next="promo_guan_3_memorial")
    validate(real)  # 兩邊都往前走：不丟錯


def test_a_first_leg_choice_may_end_the_summons_instead(real):
    """選項直接晉升（結束召見）也算：召見不會留在原地。"""
    real.events["promo_guan_3_memorial"].choices[0].effect = Effect(
        text="x", promote=3, followers=["follower_guan_spear"])
    validate(real)


def test_a_last_leg_choice_must_promote(real):
    """對稱地，最後一段的選項沒晉升，召見也留在原地、可以重演。"""
    real.events["promo_guan_3_palace"].choices[0].effect = Effect(text="x")
    with pytest.raises(ContentError, match="promo_guan_3_palace：.*promote"):
        validate(real)


# ── 企劃者裁決 E2（2026-10-07）：召見的地點與路上的站都摸清 ─────────────
# 發召見、往下一段（next_leg）、換人（_refresh 換了地點）的當下，把從所在地到召見地點最短的那條路（所有已開放的地點，
# 同 summons_place）上沒去過的站記成摸清（PlayerState.surveyed）：看得見、還沒去過的站也記（人走開就看不見了）。
# 不另寫一句話（同送別時的留意地形）。


def _fresh(content, faction, join):
    """剛投靠的新角色站在陣營的投靠點（只去過起點與投靠點，跳過序章的人也一樣），體力是滿的。"""
    game = _game(content, faction=faction)
    p = game.state.player
    p.location = join
    p.visited.add(join)
    p.stamina = content.config.stamina_max
    return game


def _place(game, fid, location):
    """這位大勢人物此刻在場、在 location。"""
    w = game.state.world
    w.figures[fid] = figures.state_of(game.state, game.content, fid).model_copy(
        update={"status": "active", "location": location})


def _make_current(game, leg, cast, where=None, prev=None):
    """讓這一段的 cast 成為第一個成立的版本：排在它前面的版本都不成立（接的不是上一段演的 prev 就本來不成立；人不同就讓那位退場；
    同一個人就結算它的 before_event 或立它 flags_none 的旗標），它自己的人物在它演的地方（at，或 where：沒寫 at 的營中授印
    照人物此刻的所在）。"""
    for other in leg.casts:
        if other is cast:
            break
        if other.after is not None and other.after != prev:
            continue
        if other.figure is not None and other.figure != cast.figure:
            _retire(game, other.figure)
        elif other.before_event is not None:
            _settle(game, other.before_event)
        else:
            assert other.flags_none, f"不知道怎麼讓 {other.event} 不成立"
            rules.add_world_flags(game.state, other.flags_none)
    if cast.figure is not None and (cast.at or where):
        _place(game, cast.figure, cast.at or where)


def _issue(game, rank):
    """本季貢獻到了第 rank 階、做過那一階的機緣：check_summons 發召見。"""
    p = game.state.player
    p.rank = 0 if rank == 2 else rank - 1
    p.contrib = ranks.threshold(game.content, rank)
    p.opp_done = [o.id for o in game.content.opportunities if o.faction == p.faction and o.rank == rank]
    return ranks.check_summons(game.state, game.content)


def _can_get_there(game, where):
    """召見那一段的地點到得了：疾行安排得了前往（/api/travel 問的就是 travel_refusal）；就在這裡的話，奇遇此刻就演得了。"""
    p = game.state.player
    dest = p.summons.location
    if dest == p.location:  # 第 2 階的召見不記事件（主版或接手版照此刻出面的人）：演得了就好
        event = ranks.summons_event(game.state, game.content)
        assert event is not None and event == (p.summons.event or event), where
    else:
        assert game.travel_refusal(dest, "dash") is None, f"{where}：疾行到不了 {game.content.locations[dest].name}"


def _camp_places(content, fid):
    """營中授印（沒寫 at，人在哪就在哪演）可能演在哪裡：人物開季的所在，加上時刻表把這兩位調去的長社、盧植營、宛城。"""
    return sorted({content.figures[fid].location, "changshe", "luzhi_camp", "wan_city"})


def _summons_cases(content, faction):
    """這個陣營每一階、每一段、每一個版本（營中授印另外每一個可能的地點）的召見：(階, [(段, 版本, 地點)…])。
    第 2 階沒有段，是 (2, [])；第二段只配 after 寫的那個第一段版本。"""
    cases = []
    for promo in sorted((x for x in content.promotions if x.faction == faction), key=lambda x: x.rank):
        if not promo.legs:
            cases.append((promo.rank, []))
            continue
        firsts = [[(promo.legs[0], cast, where)] for cast in promo.legs[0].casts
                  for where in ([None] if cast.at or not cast.figure else _camp_places(content, cast.figure))]
        if len(promo.legs) == 1:
            cases += [(promo.rank, chain) for chain in firsts]
            continue
        for chain in firsts:
            for cast in promo.legs[1].casts:
                if cast.after is None or cast.after == chain[0][1].event:
                    cases.append((promo.rank, [*chain, (promo.legs[1], cast, None)]))
    return cases


@pytest.mark.parametrize("faction, join", [
    (f.id, join) for f in real_content().scenario.factions for join in f.join_at
])
def test_every_summons_place_can_be_reached_by_dash(on, faction, join):
    """promotions.json 的每一階、每一段、每一個版本：剛在投靠點投靠的新角色，召見一發出來（或往下一段）就安排得了疾行過去，
    或人就在那裡、奇遇演得了。第二段從第一段的地點出發（人是演完第一段才往下一段的）。"""
    cases = _summons_cases(on, faction)
    mine = [x for x in on.promotions if x.faction == faction]
    assert {rank for rank, _ in cases} == {x.rank for x in mine}  # 每一階、每一段的每一個版本都走到了
    assert {cast.event for _, chain in cases for _, cast, _ in chain} == {
        cast.event for x in mine for leg in x.legs for cast in leg.casts}
    for rank, chain in cases:
        game = _fresh(on, faction, join)
        p = game.state.player
        if not chain:  # 第 2 階
            assert _issue(game, rank), (faction, join, rank)
            _can_get_there(game, f"{faction} 第 2 階 從 {join}")
            continue
        leg, cast, where = chain[0]
        _make_current(game, leg, cast, where)
        assert _issue(game, rank), (faction, join, rank, cast.event)
        assert (p.summons.event, p.summons.figure) == (cast.event, cast.figure)
        _can_get_there(game, f"{faction} 第 {rank} 階 {cast.event}@{where or cast.at} 從 {join}")
        if len(chain) == 2:
            leg1, cast1, _ = chain[1]
            p.location = p.summons.location  # 到了第一段的地點、演完
            p.visited.add(p.location)
            _make_current(game, leg1, cast1, prev=cast.event)
            assert ranks.next_leg(game.state, on, cast.event)
            assert p.summons.event == cast1.event
            _can_get_there(game, f"{faction} 第 {rank} 階 {cast.event} → {cast1.event} 從 {join}")


def _route_stops(game, dest):
    return set(atlas.shortest_routes(game.state, game.content)[dest].path)


def test_issuing_a_summons_surveys_the_stops_on_the_way(on):
    """南陽黃巾營投靠的黃巾，第 3 階召見到下曲陽（張寶）：原本疾行安排不了（路上的站都沒摸清），發召見之後到得了，
    路上每一站不是去過就是摸清。"""
    game = _fresh(on, "huang", "nanyang_huangjin_camp")
    p = game.state.player
    assert game.travel_refusal("xiaquyang", "dash") == "無法安排前往這裡"
    stops = _route_stops(game, "xiaquyang")
    assert _issue(game, 3) == ["張寶召你到下曲陽。"]
    assert p.summons.location == "xiaquyang"
    assert stops <= p.visited | p.surveyed and "xiaquyang" in p.surveyed
    assert p.surveyed.isdisjoint(p.visited - stops) and p.surveyed == stops - p.visited  # 只記這一條路上的站
    assert game.travel_refusal("xiaquyang", "dash") is None


def test_the_next_leg_surveys_its_way(on):
    """黃巾第 3 階第一段在下曲陽演完，第二段要帶著符去南陽黃巾營：往下一段的當下就摸清那一條路。"""
    game = _fresh(on, "huang", "huangjin_camp")
    p = game.state.player
    _issue(game, 3)
    p.location = "xiaquyang"
    p.visited.add("xiaquyang")
    stops = _route_stops(game, "nanyang_huangjin_camp")
    assert not stops <= p.visited | p.surveyed  # 還沒摸清
    assert ranks.next_leg(game.state, on, "promo_huang_3_talisman") == ["帶著符去南陽黃巾營。"]
    assert stops <= p.visited | p.surveyed
    assert game.travel_refusal("nanyang_huangjin_camp", "dash") is None


def test_rank_two_is_surveyed_too(on):
    """第 2 階的召見也一樣（企劃者「發召見」說的是每一種召見）：宛城投靠的官軍召到長社、鉅鹿道壇投靠的黃巾召到黃巾別部營寨。"""
    for faction, join, dest in (("guan", "wan_city", "changshe"), ("huang", "julu_altar", "huangjin_camp")):
        game = _fresh(on, faction, join)
        assert game.travel_refusal(dest, "dash") == "無法安排前往這裡"
        assert _issue(game, 2)
        assert game.state.player.summons.location == dest
        assert game.travel_refusal(dest, "dash") is None


def test_a_presenter_who_moves_takes_the_survey_with_him(on):
    """營中授印跟著人走：皇甫嵩從長社調到宛城，召見改寫到宛城（話變了，照說），那一條路也摸清。"""
    game = _fresh(on, "guan", "changshe")
    p = game.state.player
    _retire(game, "hejin")
    assert _issue(game, 4) == ["皇甫嵩召你到長社營中授印。"]
    _place(game, "huangfusong", "dajiangjun_fu")  # 很遠的地方：從長社看不見、沒去過
    stops = _route_stops(game, "dajiangjun_fu")
    assert not stops <= p.visited | p.surveyed
    assert ranks.check_summons(game.state, on) == ["皇甫嵩召你到大將軍府營中授印。"]
    assert stops <= p.visited | p.surveyed
    assert game.travel_refusal("dajiangjun_fu", "dash") is None


def test_a_silent_swap_that_moves_the_place_still_surveys(on):
    """換了地點、話卻沒變（召見那一句不寫{據點}）時悄悄換、不再說一次，可是路照樣摸清：地點變了就摸清，跟說不說無關。"""
    camp = next(c for c in next(x for x in on.promotions if x.faction == "guan" and x.rank == 4).legs[0].casts
                if c.figure == "huangfusong")
    camp.summons_text = "皇甫嵩召你到營中授印。"
    game = _fresh(on, "guan", "changshe")
    p = game.state.player
    _retire(game, "hejin")
    assert _issue(game, 4) == ["皇甫嵩召你到營中授印。"]
    _place(game, "huangfusong", "dajiangjun_fu")
    assert ranks.check_summons(game.state, on) == []  # 話沒變：不說
    assert p.summons.location == "dajiangjun_fu"
    assert game.travel_refusal("dajiangjun_fu", "dash") is None


def test_stops_you_can_see_now_are_surveyed_too(on):
    """路上此刻看得見、還沒去過的站也要記：人走開之後就看不見了，路會斷在那裡。發召見之後走回起點（一路都是去過的站），
    召見的地點照樣疾行到得了。"""
    game = _fresh(on, "huang", "nanyang_huangjin_camp")
    p = game.state.player
    seen = atlas.visible_locations(game.state, on)
    stops = _route_stops(game, "xiaquyang")
    _issue(game, 3)
    assert (stops & seen) - p.visited and (stops & seen) - p.visited <= p.surveyed  # 看得見的站也記成摸清
    start = on.scenario.start_location
    back = atlas.shortest_routes(game.state, on)[start].path
    p.visited |= set(back)  # 一路走回起點
    p.location = start
    assert game.travel_refusal("xiaquyang", "dash") is None


def test_the_far_summons_places_are_marked_important(on):
    """樓桑里（豪強第 4 階）與下曲陽（黃巾第 3、4 階）在地圖上沒摸清時也畫出名字（Location.important）。"""
    assert on.locations["loushang_village"].important and on.locations["xiaquyang"].important
