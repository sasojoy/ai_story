"""第一季正式版・丙二：黃巾的第 3、4 階奇遇（計畫 2026-10-06-第一季正式版-丙二）。

用真實內容（content/）：fixture real、on 在 tests/conftest.py（每個測試拿 real_content 的一份複本，開關在 on 裡才打開）。
週末設定（人數上限 2）：帶糧 2 份換算成 1。
釘住的內容：content/promotions.json、content/events/promotion.json（scripts/test_for.py 改到這兩個檔時靠檔名挑到這裡）。"""
from __future__ import annotations

import random

import pytest
from pydantic import ValidationError

from conftest import real_content
from tianxia import calendar, figures, foreshadow, materials, ranks, rules
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
    """貢獻記在捐的那一週的帳上（季曆第幾週）：隔了幾週再捐一次，兩週各記各的。"""
    game = _game(on, at="nanyang_huangjin_camp")
    _grain(game, 5)
    w = game.state.world
    weeks = []
    for week in (2, 5):  # 第 2 週與第 5 週（週末設定一週五個小時）各捐一次
        w.time = calendar.week_start(week, on, w) + 60
        weeks.append(calendar.point(w.time, on, w).week)
        rules.apply_effect(Effect(donate_grain={"nanyang_huangjin_camp": 2}), game.state, on, game.world)
    p = game.state.player
    assert weeks[0] != weeks[1]
    assert p.donations == {"nanyang_huangjin_camp:糧草": 2}
    assert p.contrib == 2 * on.config.contrib_per_push
    assert p.contrib_weeks == {weeks[0]: on.config.contrib_per_push, weeks[1]: on.config.contrib_per_push}


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
        per_push = on.config.contrib_per_push
        # 沒給 push：捐糧記一次貢獻，trend 直接改戰況、不記；給了 push（Game.push_trend）：trend 走個人推動，另記自己的貢獻——
        # 兩次都記在一起才大於一次，所以這一支真的用到了傳進來的 push，不是只靠捐糧那一份
        contrib = game.state.player.contrib
        assert (contrib > per_push) if use_push else (contrib == per_push)


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


# ── Task 2：黃巾的第 3、4 階（內容）─────────────────────────────


def _ready(game, rank, contrib=10**6):
    p = game.state.player
    p.rank, p.contrib = rank, contrib
    p.opp_done = [next(o.id for o in game.content.opportunities if o.faction == "huang" and o.rank == rank + 1)]


def _retire(game, fid, status="retired"):
    w = game.state.world
    w.figures[fid] = figures.state_of(game.state, game.content, fid).model_copy(update={"status": status})


def _lines(game):
    """眼前事件的選項標籤（只算按得下去的）。"""
    return [o.label for o in game.options(odds=False) if o.enabled and o.id.startswith("choice:")]


def test_talisman_then_zhangmancheng(on):
    game = _game(on, at="xiaquyang")
    _ready(game, 2)
    assert ranks.check_summons(game.state, on) == ["張寶召你到下曲陽。"]
    game.choose("act:summons")
    assert "帶著符去南陽黃巾營。" in game.choose("choice:0")
    game.state.player.location = "nanyang_huangjin_camp"
    game.choose("act:summons")
    msgs = game.choose("choice:0")
    assert "你升為小方渠帥。" in msgs and game.state.player.affinities.get("zhangmancheng") == 10


def test_receiver_changes_after_week_seven(on):
    game = _game(on, at="xiaquyang")
    _ready(game, 2)
    ranks.check_summons(game.state, on)
    game.choose("act:summons")
    game.choose("choice:0")
    _retire(game, "zhangmancheng")  # 第 7 週秦頡斬張曼成（趙弘本來就在南陽黃巾營、在場：不必另外改他）
    # 地點與召見那一句都沒變，悄悄換成趙弘那一版（丙一 _refresh：同一句話不再寫進紀錄一次）；到了才知道是趙弘
    assert ranks.check_summons(game.state, on) == []
    assert game.state.player.summons.event == "promo_huang_3_zh"
    game.state.player.location = "nanyang_huangjin_camp"
    assert ranks.summons_event(game.state, on) == "promo_huang_3_zh"  # 到了演的是趙弘那一版
    game.choose("act:summons")
    assert game.state.pending_event == "promo_huang_3_zh"


def test_grain_offer_feeds_the_hoard(on):
    game = _game(on, at="nanyang_huangjin_camp")
    _retire(game, "zhangmancheng")
    _ready(game, 2)
    p = game.state.player
    p.summons = None
    ranks.check_summons(game.state, on)  # 第一段：張寶
    ranks.next_leg(game.state, on, "promo_huang_3_talisman")
    game.choose("act:summons")
    assert _lines(game) == ["「帶了人。」", "「只帶了這道符。」"]  # 沒有糧：「帶了糧。」看不到
    _grain(game, 2)
    offer = next(o for o in game.options(odds=False) if o.label == "「帶了糧。」")
    game.choose(offer.id)
    assert p.donations.get("nanyang_huangjin_camp:糧草") == 1 and p.rank == 3


def test_no_speaker_in_nanyang_sends_you_to_guangzong(on):
    game = _game(on, at="xiaquyang")
    _ready(game, 2)
    ranks.check_summons(game.state, on)
    game.choose("act:summons")
    game.choose("choice:0")
    _retire(game, "zhangmancheng")
    _retire(game, "zhaohong")  # 宛城之戰趙弘戰死
    assert ranks.check_summons(game.state, on) == ["南陽那邊沒有人接應了，改去廣宗支援張梁。"]
    assert game.state.player.summons.location == "guangzong"


def test_zhangjiao_gives_two_runic_pieces(on):
    game = _game(on, at="guangzong")
    _ready(game, 3)
    assert ranks.check_summons(game.state, on) == ["張角召你到廣宗。"]
    game.choose("act:summons")
    msgs = game.choose("choice:2")  # 您該多歇著
    p = game.state.player
    assert p.runic_pieces == 2 and p.qualified and "你取得大方渠帥的資格，候缺。" in msgs
    assert any(m.startswith("你聽到一件事：") for m in msgs)


def test_revealed_runes_give_no_pieces(on):
    game = _game(on, at="guangzong")
    game.state.world.flags.add("runic_revealed")
    _ready(game, 3)
    ranks.check_summons(game.state, on)
    assert game.state.player.summons.event == "promo_huang_4_revealed"
    game.choose("act:summons")
    game.choose("choice:1")
    assert game.state.player.runic_pieces == 0 and game.state.player.qualified


def test_heir_hands_the_order_without_shards(on):
    game = _game(on, at="xiaquyang")
    _retire(game, "zhangjiao")  # 第 10 週病逝
    _ready(game, 3)
    assert ranks.check_summons(game.state, on) == ["張寶召你到下曲陽。"]
    game.choose("act:summons")
    game.choose("choice:0")
    assert game.state.player.runic_pieces == 0 and game.state.player.qualified


# 以下是這個任務自己多寫的：內容的結構、每個選項、兩句修過的話、各種換人的路


def test_the_real_huang_promotions_are_defined(on):
    by = {(p.faction, p.rank): p for p in on.promotions}
    rank3, rank4 = by[("huang", 3)], by[("huang", 4)]
    assert [[c.event for c in leg.casts] for leg in rank3.legs] == [
        ["promo_huang_3_talisman", "promo_huang_3_talisman_zl"],
        ["promo_huang_3_zmc", "promo_huang_3_zh", "promo_huang_3_zl"]]
    assert [(c.figure, c.at, c.after, c.before_event, c.flags_none) for leg in rank3.legs for c in leg.casts] == [
        ("zhangbao", "xiaquyang", None, None, []), ("zhangliang", "guangzong", None, None, []),
        ("zhangmancheng", "nanyang_huangjin_camp", None, None, []), ("zhaohong", "nanyang_huangjin_camp", None, None, []),
        ("zhangliang", "guangzong", None, None, [])]
    assert [c.summons_text for leg in rank3.legs for c in leg.casts] == [
        "張寶召你到{據點}。", "張梁召你到{據點}。", "帶著符去{據點}。", "帶著符去{據點}。",
        "南陽那邊沒有人接應了，改去{據點}支援張梁。"]
    assert [(c.event, c.figure, c.at, c.flags_none) for c in rank4.legs[0].casts] == [
        ("promo_huang_4", "zhangjiao", "guangzong", ["runic_revealed"]),
        ("promo_huang_4_revealed", "zhangjiao", "guangzong", []),
        ("promo_huang_4_heir", "zhangbao", "xiaquyang", []), ("promo_huang_4_heir", "zhangliang", "guangzong", [])]
    assert len(rank4.legs) == 1 and rank3.closing.endswith("「小方渠帥，往後聽你的。」")


def test_the_eight_new_events_are_wired_to_their_legs(on):
    """第 3 階第一段的兩則寫 summons_next（自己的 id）、不晉升；最後一段與第 4 階的每個選項晉升到那一階、給那一階的部下。
    計畫寫「加七則」，表裡其實是八則。"""
    first = {"promo_huang_3_talisman", "promo_huang_3_talisman_zl"}
    rank3 = {"promo_huang_3_zmc", "promo_huang_3_zh", "promo_huang_3_zl"}
    rank4 = {"promo_huang_4", "promo_huang_4_revealed", "promo_huang_4_heir"}
    for event_id in first:
        choices = on.events[event_id].choices
        assert len(choices) == 1 and choices[0].effect.summons_next == event_id and choices[0].effect.promote is None
    for event_id, rank, given in [(e, 3, ["follower_huang_believer"]) for e in sorted(rank3)] + [
            (e, 4, ["follower_huang_strongman"]) for e in sorted(rank4)]:
        event = on.events[event_id]
        assert event.actions == [] and len(event.choices) == (2 if event_id == "promo_huang_4_heir" else 3)
        for choice in event.choices:
            assert (choice.effect.promote, choice.effect.followers, choice.effect.summons_next) == (rank, given, None)
    # 帶糧是基準量 2（週末換算成 1；人多的伺服器要得更多），捐去那個人所在的據點
    for event_id, place in (("promo_huang_3_zh", "nanyang_huangjin_camp"), ("promo_huang_3_zl", "guangzong")):
        grain = on.events[event_id].choices[0]
        assert grain.condition.grain_min == 2 and grain.effect.donate_grain == {place: 2}
        assert all(c.condition == Condition() and not c.effect.donate_grain for c in on.events[event_id].choices[1:])
    assert [c.effect.runic for e in ("promo_huang_4", "promo_huang_4_revealed", "promo_huang_4_heir")
            for c in on.events[e].choices] == [2, 2, 2, 0, 0, 0, 0, 0]
    assert [bool(c.effect.fs_fragments) for c in on.events["promo_huang_4"].choices] == [False, False, True]
    assert [bool(c.effect.fs_fragments) for c in on.events["promo_huang_4_revealed"].choices] == [False, False, True]
    assert {e.title for e in (on.events[i] for i in [*first, *rank3, *rank4])} == {
        "晉升・下曲陽", "晉升・廣宗", "晉升・南陽黃巾營", "晉升・廣宗靜室", "晉升・黃天密令"}


def test_the_labels_and_the_spec_scenes_are_as_written(on):
    """選項文字與出自晉升奇遇文件的場景一字不差；新寫、待 joy 潤的句子不在這裡釘（見 joy 清單）。"""
    labels = {
        "promo_huang_3_talisman": ["「是。」"], "promo_huang_3_talisman_zl": ["「是。」"],
        "promo_huang_3_zmc": ["「信。」", "「我信大賢良師。」", "「我信的是手上的刀。」"],
        "promo_huang_3_zh": ["「帶了糧。」", "「帶了人。」", "「只帶了這道符。」"],
        "promo_huang_3_zl": ["「帶了糧。」", "「帶了人。」", "「只帶了這道符。」"],
        "promo_huang_4": ["「大賢良師，錦囊裡是什麼？」", "「弟子不問。」", "「大賢良師，您該多歇著。」"],
        "promo_huang_4_revealed": ["「大賢良師，錦囊裡是什麼？」", "「弟子不問。」", "「大賢良師，您該多歇著。」"],
        "promo_huang_4_heir": ["「弟子領命。」", "「黃天不會倒。」"],
    }
    for event_id, expected in labels.items():
        assert [c.text for c in on.events[event_id].choices] == expected
    assert on.events["promo_huang_3_talisman"].text == (
        "張寶咬破手指，在黃紙上畫了一道符，塞進你懷裡：「南陽要人。帶著這道符去，他們就知道你是自己人。」")
    assert on.events["promo_huang_3_zmc"].text == "神上使接過符，對著日光看了很久：「你信黃天嗎？」"
    assert on.events["promo_huang_3_zmc"].choices[2].effect.text == "一旁的趙弘看了你一眼。"
    assert on.events["promo_huang_4"].text.startswith("廣宗城裡最深的一間靜室。張角瘦得只剩一副骨架，眼睛卻亮得嚇人。他把一卷黃帛交給你：")
    assert on.events["promo_huang_4"].text.endswith("像是自言自語：「南華老仙給我的，不只是一部書……」")
    # 另外四句出自晉升奇遇文件（3.2、3.3）：揭開之後的張角那句、趙弘開口那句、張角點頭、交令的人手上那卷黃帛
    assert "「天下都知道了。那就讓他們來搶。」" in on.events["promo_huang_4_revealed"].text
    assert on.events["promo_huang_3_zh"].text.endswith("「符？我不看符，我看你帶了什麼來。」")
    assert [on.events[e].choices[1].effect.text for e in ("promo_huang_4", "promo_huang_4_revealed")] == ["張角點了點頭。"] * 2
    assert "「這是大賢良師留下的黃天密令，見令如見他。」" in on.events["promo_huang_4_heir"].text


def test_inner_quotes_are_stored_as_corner_brackets(on):
    """F4：計畫的表格拿 「」 當儲存格的框，裡面的引號寫成 『』；存進內容的是 「」（跟丙一一樣，晉升奇遇裡一個 『』 都沒有）。"""
    for event in on.events.values():
        if event.id.startswith("promo_"):
            texts = [event.text] + [t for c in event.choices for e in (c.effect, c.fail_effect) for t in (e.text,)]
            assert not any("『" in t or "』" in t for t in texts), event.id
    zh = on.events["promo_huang_3_zh"].choices
    assert zh[1].effect.text == "趙弘點點頭：「人也好，城頭缺人。」" and zh[2].effect.text == "「那就先去城頭站一夜。」"


@pytest.mark.parametrize("choice, affinity", [(0, {"zhangmancheng": 10}), (1, {"zhangmancheng": 3}),
                                              (2, {"zhangmancheng": -3, "zhaohong": 5})])
def test_every_zhangmancheng_ending_makes_a_small_leader(on, choice, affinity):
    game = _game(on, at="nanyang_huangjin_camp")
    p = game.state.player
    p.affinities.update({"zhangmancheng": 20, "zhaohong": 20})
    _ready(game, 2)
    ranks.check_summons(game.state, on)
    ranks.next_leg(game.state, on, "promo_huang_3_talisman")
    assert p.summons.event == "promo_huang_3_zmc"
    game.choose("act:summons")
    msgs = game.choose(f"choice:{choice}")
    assert "你升為小方渠帥。" in msgs and (p.rank, p.followers, p.summons) == (3, ["follower_huang_believer"], None)
    assert ranks.promotion_for(on, "huang", 3).closing in msgs  # 玩家看到的訊息裡真的有結尾那一句，不只是資料裡寫了
    assert {k: p.affinities[k] for k in ("zhangmancheng", "zhaohong")} == {
        "zhangmancheng": 20 + affinity.get("zhangmancheng", 0), "zhaohong": 20 + affinity.get("zhaohong", 0)}
    assert any(r.text == "甲升為小方渠帥。" and r.faction == "huang" for r in game.state.world.rumors)


@pytest.mark.parametrize("choice, affinity, grain", [(0, 10, 1), (1, 5, 0), (2, 0, 0)])
def test_every_zhaohong_ending(on, choice, affinity, grain):
    game = _game(on, at="nanyang_huangjin_camp")
    p = game.state.player
    p.affinities["zhaohong"] = 20
    _retire(game, "zhangmancheng")
    _ready(game, 2)
    ranks.check_summons(game.state, on)
    ranks.next_leg(game.state, on, "promo_huang_3_talisman")
    assert p.summons.event == "promo_huang_3_zh"
    _grain(game, 2)
    game.choose("act:summons")
    assert _lines(game) == ["「帶了糧。」", "「帶了人。」", "「只帶了這道符。」"]
    contrib = p.contrib
    game.choose(f"choice:{choice}")
    assert (p.rank, p.followers, p.affinities["zhaohong"]) == (3, ["follower_huang_believer"], 20 + affinity)
    assert p.donations.get("nanyang_huangjin_camp:糧草", 0) == grain
    assert p.contrib - contrib == (on.config.contrib_per_push if grain else 0)
    assert materials.grain_of(game.state, on) == (1 if grain else 2)


@pytest.mark.parametrize("choice, affinity, grain", [(0, 10, 1), (1, 5, 0), (2, 0, 0)])
def test_every_zhangliang_ending_at_guangzong(on, choice, affinity, grain):
    """南陽沒有人接應：召見改去廣宗，張梁收符；帶了糧就捐進廣宗。"""
    game = _game(on, at="guangzong")
    p = game.state.player
    p.affinities["zhangliang"] = 20
    _ready(game, 2)
    ranks.check_summons(game.state, on)
    ranks.next_leg(game.state, on, "promo_huang_3_talisman")
    _retire(game, "zhangmancheng")
    _retire(game, "zhaohong")
    assert ranks.check_summons(game.state, on) == ["南陽那邊沒有人接應了，改去廣宗支援張梁。"]
    assert (p.summons.event, p.summons.location) == ("promo_huang_3_zl", "guangzong")
    _grain(game, 2)
    game.choose("act:summons")
    game.choose(f"choice:{choice}")
    assert (p.rank, p.followers, p.affinities["zhangliang"]) == (3, ["follower_huang_believer"], 20 + affinity)
    assert p.donations.get("guangzong:糧草", 0) == grain


def test_the_talisman_can_come_from_zhangliang_when_zhangbao_is_out(on):
    game = _game(on, at="guangzong")
    _retire(game, "zhangbao")
    _ready(game, 2)
    assert ranks.check_summons(game.state, on) == ["張梁召你到廣宗。"]
    assert game.state.player.summons.event == "promo_huang_3_talisman_zl"
    game.choose("act:summons")
    msgs = game.choose("choice:0")
    assert "帶著符去南陽黃巾營。" in msgs and game.state.player.summons.leg == 1


def test_nobody_to_hand_over_the_talisman_means_no_summons(on):
    """N1：張寶與張梁都不在：先不發（不發一張找不到人的召見）；之後有人回來才發。"""
    game = _game(on, at="xiaquyang")
    _retire(game, "zhangbao")
    _retire(game, "zhangliang")
    _ready(game, 2)
    assert ranks.check_summons(game.state, on) == [] and game.state.player.summons is None
    game.state.world.figures["zhangbao"] = game.state.world.figures["zhangbao"].model_copy(update={"status": "active"})
    assert ranks.check_summons(game.state, on) == ["張寶召你到下曲陽。"]


@pytest.mark.parametrize("choice, affinity, fragment", [(0, 3, False), (1, 10, False), (2, 5, True)])
@pytest.mark.parametrize("revealed", [False, True])
def test_every_zhangjiao_ending(on, choice, affinity, fragment, revealed):
    """三個選項都取得資格（小方渠帥不變）、給太平力士；密令算 2 片殘片，殘片已經有人揭開（runic_revealed）就不算；
    只有「您該多歇著」給伏筆片段，不管揭開沒有。"""
    game = _game(on, at="guangzong")
    p = game.state.player
    p.affinities["zhangjiao"] = 20
    if revealed:
        game.state.world.flags.add("runic_revealed")
    _ready(game, 3)
    ranks.check_summons(game.state, on)
    assert p.summons.event == ("promo_huang_4_revealed" if revealed else "promo_huang_4")
    game.choose("act:summons")
    msgs = game.choose(f"choice:{choice}")
    assert "你取得大方渠帥的資格，候缺。" in msgs and (p.rank, p.qualified) == (3, True)
    assert ranks.promotion_for(on, "huang", 4).closing in msgs  # 玩家看到的訊息裡真的有結尾那一句
    assert p.followers == ["follower_huang_strongman"] and p.summons is None
    assert p.affinities["zhangjiao"] == 20 + affinity
    assert p.runic_pieces == (0 if revealed else 2)
    assert any(m.startswith("你聽到一件事：") for m in msgs) is fragment
    assert (p.fragments.get("fs_zhangjiao_huang") == [0]) is fragment
    assert ranks.title(on, game.state) == "大方渠帥" and "你補上了大方渠帥的缺，到下週一為止。" in msgs  # 席次空著：當下補上（正式版丁）
    assert any(r.text == "甲取得大方渠帥的資格，候缺。" and r.faction == "huang" for r in game.state.world.rumors)


def test_a_fragment_already_heard_is_not_heard_twice_in_the_secret_order(on):
    """Focus 4：先聽過了片段 0，再選「您該多歇著」就不再給（也不再寫「你聽到一件事」）。"""
    game = _game(on, at="guangzong")
    p = game.state.player
    p.fragments = {"fs_zhangjiao_huang": [0]}
    _ready(game, 3)
    ranks.check_summons(game.state, on)
    game.choose("act:summons")
    msgs = game.choose("choice:2")
    assert not any(m.startswith("你聽到一件事：") for m in msgs) and p.runic_pieces == 2


def test_the_runic_flag_is_read_when_the_summons_is_made_and_again_when_it_is_played(on):
    """召見發出後旗標才立起來：下一次檢查就換成揭開之後的那一版（說的話不變，所以悄悄換），演的是揭開之後的版本、不給殘片。"""
    game = _game(on, at="guangzong")
    _ready(game, 3)
    ranks.check_summons(game.state, on)
    assert game.state.player.summons.event == "promo_huang_4"
    game.state.world.flags.add("runic_revealed")
    assert ranks.check_summons(game.state, on) == []
    assert game.state.player.summons.event == "promo_huang_4_revealed"
    game.choose("act:summons")
    game.choose("choice:1")
    assert game.state.player.runic_pieces == 0


@pytest.mark.parametrize("choice", [0, 1])
def test_every_heir_ending(on, choice):
    game = _game(on, at="xiaquyang")
    p = game.state.player
    _retire(game, "zhangjiao")
    _ready(game, 3)
    ranks.check_summons(game.state, on)
    game.choose("act:summons")
    msgs = game.choose(f"choice:{choice}")
    assert "你取得大方渠帥的資格，候缺。" in msgs and p.qualified and p.followers == ["follower_huang_strongman"]
    assert p.runic_pieces == 0 and p.fragments == {}


def test_the_heir_is_zhangliang_when_zhangbao_is_out_and_the_swap_is_told(on):
    game = _game(on, at="guangzong")
    _retire(game, "zhangjiao")
    _ready(game, 3)
    assert ranks.check_summons(game.state, on) == ["張寶召你到下曲陽。"]
    _retire(game, "zhangbao")
    assert ranks.check_summons(game.state, on) == ["張梁召你到廣宗。"]  # 同一則事件、換了出面的人：話變了，照樣說
    assert (game.state.player.summons.event, game.state.player.summons.figure) == ("promo_huang_4_heir", "zhangliang")


def test_zhangjiao_dying_while_you_hold_the_summons_hands_it_to_an_heir(on):
    game = _game(on, at="guangzong")
    _ready(game, 3)
    assert ranks.check_summons(game.state, on) == ["張角召你到廣宗。"]
    _retire(game, "zhangjiao")
    assert ranks.check_summons(game.state, on) == ["張寶召你到下曲陽。"]
    assert game.state.player.summons.event == "promo_huang_4_heir"


def test_the_two_fixed_sentences(on):
    """F5：計畫兩處跟遊戲對不上的句子，各給最小的修正（待 joy 潤）。
    一、第 4 階結尾稱「大方渠帥」，可是玩家只是候缺，還是小方渠帥；
    二、揭開之後的張角已經說「天下都知道了」，第一個選項的回答卻還說「等黃天立了，你自會知道」。"""
    assert ranks.promotion_for(on, "huang", 4).closing == "一個太平力士被帶到你身後：「渠帥，往後聽你的。」"
    plain, revealed = on.events["promo_huang_4"], on.events["promo_huang_4_revealed"]
    assert plain.choices[0].effect.text == "他淡淡一笑：「等黃天立了，你自會知道。」"  # 還沒揭開：原文
    assert revealed.choices[0].effect.text == "他淡淡一笑：「如今天下都知道了，何必問我。」"
    assert "等黃天立了" not in revealed.choices[0].effect.text
    # 其他兩個選項兩版相同
    assert [c.effect.text for c in plain.choices[1:]] == [c.effect.text for c in revealed.choices[1:]]


def test_a_huang_player_walks_all_the_way_up(on):
    """一個黃巾角色從第 2 階走到第 4 階的資格：貢獻到了、機緣先沒有——說一次 HINT；補上機緣才收到召見；兩段演完升第 3 階，
    第 4 階同樣，每一步都走 Game 的公開行動。"""
    game = _game(on, at="xiaquyang")
    p = game.state.player
    p.rank, p.contrib = 2, 10**6
    assert ranks.check_summons(game.state, on) == [ranks.HINT]
    _ready(game, 2)
    assert ranks.check_summons(game.state, on) == ["張寶召你到下曲陽。"]
    game.choose("act:summons")
    game.choose("choice:0")
    p.location = "nanyang_huangjin_camp"
    game.choose("act:summons")
    msgs = game.choose("choice:1")
    assert "你升為小方渠帥。" in msgs and ranks.HINT in msgs  # 第 4 階的進度到了、機緣還沒有
    assert p.rank_hinted == [3, 4]
    _ready(game, 3)
    assert ranks.check_summons(game.state, on) == ["張角召你到廣宗。"]
    p.location = "guangzong"
    game.choose("act:summons")
    game.choose("choice:1")
    assert (p.rank, p.qualified, p.followers) == (
        3, True, ["follower_huang_believer", "follower_huang_strongman"])
    assert game.status_data()["affiliation"] == "黃巾軍・大方渠帥"  # 席次空著：取得資格的同一個動作補上（正式版丁）
    notes = [r.text for r in game.state.world.rumors if r.layer == "faction" and r.faction == "huang"]
    assert "甲升為小方渠帥。" in notes and "甲取得大方渠帥的資格，候缺。" in notes


# ── 審查後的修正（丙二 Task 1、2 的 Minor）─────────────────────────────


def test_a_new_season_resets_the_runic_pieces_and_the_fragments(on):
    """審查 Minor 1：換季是新角色，符文殘片與聽過的片段都重來（_reset_player_for_new_season 蓋一個新的 PlayerState）。"""
    on.config.admins = ["管"]
    admin = _game(on, "管")
    player = _game(on, "甲")
    p = player.state.player
    p.runic_pieces, p.fragments = 2, {"fs_zhangjiao_huang": [0]}
    player.sync(100.0)
    admin.admin_end_season(now=200.0)
    admin.admin_next_season(now=300.0)
    player.sync(400.0)
    p = player.state.player
    assert (p.faction, p.runic_pieces, p.fragments) == (None, 0, {})


def test_defecting_keeps_the_runic_pieces_for_now(on):
    """審查 Minor 1：叛投清掉貢獻、捐獻、階與部下，可是符文殘片（跟聽過的片段一樣是知道的事）留著。這是現在的做法，
    計畫沒寫、待企劃者確認（見 defection.clear_progress 的說明）；改了就改這個測試。"""
    from tianxia import defection

    game = _game(on, at="nanyang_huangjin_camp")
    p = game.state.player
    p.runic_pieces, p.fragments = 2, {"fs_zhangjiao_huang": [0]}
    p.contrib, p.donations, p.rank, p.followers = 900, {"nanyang_huangjin_camp:糧草": 1}, 3, ["follower_huang_believer"]
    defection.clear_progress(p)
    assert (p.contrib, p.donations, p.rank, p.followers) == (0, {}, 0, [])
    assert p.runic_pieces == 2 and p.fragments == {"fs_zhangjiao_huang": [0]}


def test_the_fragment_grant_checks_foreshadowing_itself(on, monkeypatch):
    """審查 Minor 4：grant_fragment 自己先看伏筆有沒有在跑，不全靠 capable 裡的那一道（以後 capable 改了寫法，beta 季也不會給）。
    把 capable 換成永遠成立的假的，伏筆沒在跑（第一季的開關關著）時仍然什麼都不給；開著時給。"""
    monkeypatch.setattr(foreshadow, "capable", lambda *args, **kwargs: True)
    open_game = _game(on, name="乙")  # 先開季（這一季蓋著第一季的章）；開著時給
    assert foreshadow.grant_fragment(open_game.state, on, "fs_zhangjiao_huang", 0) != []
    beta = real_content()  # 開關關著的那一份（on 是同一份真實內容打開開關之後的樣子）
    game = _game(beta)
    assert not foreshadow.active(game.state, beta)
    assert foreshadow.grant_fragment(game.state, beta, "fs_zhangjiao_huang", 0) == []
    assert game.state.player.fragments == {}


# 捐糧與符文殘片自己不看陣營（審查 Task 1 Minor 8）：由所在的事件擋，載入時檢查


def _rank2_event(on):
    return on.events["promo_huang_2"]


@pytest.mark.parametrize("field, value", [("donate_grain", {"nanyang_huangjin_camp": 2}), ("runic", 2)])
def test_donations_and_runic_pieces_need_an_event_only_one_side_can_reach(on, field, value):
    """沒投靠的人、別的陣營的人領得到貢獻與殘片就是漏洞：只准寫在晉升奇遇（召見只發給自己陣營的人），或條件寫了 factions
    的事件；兩邊都不是的，載入時擋下。"""
    event = next(e for e in on.events.values() if not e.id.startswith("promo_") and e.free_text is None)
    setattr(event.choices[0].effect, field, value)
    with pytest.raises(ContentError, match=f"{event.id}：donate_grain／runic 只能寫在晉升奇遇"):
        validate(on)


@pytest.mark.parametrize("field, value", [("donate_grain", {"nanyang_huangjin_camp": 2}), ("runic", 2)])
def test_a_factions_condition_gates_the_event_or_the_choice(on, field, value):
    event = next(e for e in on.events.values() if not e.id.startswith("promo_") and e.free_text is None)
    setattr(event.choices[0].effect, field, value)
    event.condition = event.condition.model_copy(update={"factions": ["huang"]})
    validate(on)  # 事件整個只給黃巾：過得了
    event.condition = event.condition.model_copy(update={"factions": []})
    with pytest.raises(ContentError, match="donate_grain／runic 只能寫在晉升奇遇"):
        validate(on)
    event.choices[0].condition = event.choices[0].condition.model_copy(update={"factions": ["huang"]})
    validate(on)  # 只有這個選項給黃巾：也過得了


def test_a_promotion_event_may_donate_and_give_runic_pieces(on):
    """晉升奇遇本來就只有自己陣營的人演得到（召見只發給自己陣營）：不必另外寫 factions。真的內容就是這樣。"""
    _rank2_event(on).choices[0].effect.donate_grain = {"nanyang_huangjin_camp": 2}
    _rank2_event(on).choices[0].effect.runic = 2
    validate(on)


def test_the_real_events_that_donate_or_give_runic_pieces_are_huang_promotions(on):
    """現在真的內容裡用到這兩個效果的事件（兩側的選項都算）：全是黃巾的晉升奇遇；而且沒有任何事件用 next_event 接到晉升奇遇，
    所以只有拿著自己陣營的召見的人演得到。"""
    users = {
        event.id for event in on.events.values() for choice in event.choices for effect in (choice.effect, choice.fail_effect)
        if effect.donate_grain or effect.runic
    }
    huang = {c.event for p in on.promotions if p.faction == "huang" for leg in p.legs for c in leg.casts}
    assert users == {"promo_huang_3_zh", "promo_huang_3_zl", "promo_huang_4"}  # 捐糧：趙弘、張梁那兩則；符文殘片：張角的密令
    assert users <= huang
    promo_ids = {c.event for p in on.promotions for leg in p.legs for c in leg.casts} | {
        e for p in on.promotions for e in (p.event_main, p.event_handoff) if e}
    reached = {effect.next_event for event in on.events.values() for choice in event.choices
               for effect in (choice.effect, choice.fail_effect) if effect.next_event}
    assert not reached & promo_ids


def test_the_real_timetable_moves_the_presenters_where_the_leg_casts_expect_them(on):
    """丙二最終審查 m2：上面換人的測試都用 _retire 手設人物的狀態，沒有一個把 legs 的版本跟真的時刻表結果接起來。這裡照真的時刻表結算
    （timetable.resolve，跟管理者定結果走的是同一條）：第 7 週秦頡斬張曼成 → 宛城之戰官軍大勝 → 張角病逝，每一步之後看召見的
    出面的人是誰、他此刻在哪裡。時刻表若把趙弘、張梁、張寶挪到別處（或改了誰在哪一件事退場），這一條就會斷。
    （人物表裡趙弘的起始地點改了不會斷：第 7 週張曼成退場，趙弘照接位的規則到任、站在張曼成的營裡。）"""
    from tianxia import timetable

    game = _game(on, at="xiaquyang")
    state, p, rng = game.state, game.state.player, random.Random(0)
    events = {e.id: e for e in on.timetable}

    def settle(event_id, key=None):
        timetable.resolve(state, on, events[event_id], rng, key=key)
        assert event_id in state.world.timeline

    def standing(fid):
        now = figures.state_of(state, on, fid)
        return now.status, now.location

    # 開頭：張寶在下曲陽給符，下一段是南陽黃巾營的張曼成
    _ready(game, 2)
    assert ranks.check_summons(state, on) == ["張寶召你到下曲陽。"]
    assert standing("zhangbao") == ("active", "xiaquyang")
    game.choose("act:summons")
    game.choose("choice:0")
    assert (p.summons.event, p.summons.figure, p.summons.location) == (
        "promo_huang_3_zmc", "zhangmancheng", "nanyang_huangjin_camp")
    assert standing("zhangmancheng") == ("active", "nanyang_huangjin_camp")

    # 第 3 週張曼成攻殺太守（成）、第 7 週秦頡斬張曼成：他退場，趙弘還在營裡——召見那一句沒變、悄悄換成趙弘
    settle("zhangmancheng_wan", "成")
    settle("qinjie_slays_zhangmancheng")
    assert standing("zhangmancheng")[0] == "retired"
    assert standing("zhaohong") == ("active", "nanyang_huangjin_camp")
    assert ranks.check_summons(state, on) == []
    assert (p.summons.event, p.summons.figure, p.summons.location) == (
        "promo_huang_3_zh", "zhaohong", "nanyang_huangjin_camp")

    # 第 9 週宛城之戰官軍大勝：趙弘戰死，南陽沒有人接符，改去廣宗的張梁
    settle("wancheng", "guan:大勝")
    assert standing("zhaohong")[0] == "retired"
    assert standing("zhangliang") == ("active", "guangzong")
    assert ranks.check_summons(state, on) == ["南陽那邊沒有人接應了，改去廣宗支援張梁。"]
    assert (p.summons.event, p.summons.figure, p.summons.location) == ("promo_huang_3_zl", "zhangliang", "guangzong")
    p.location = "guangzong"
    game.choose("act:summons")
    assert "你升為小方渠帥。" in game.choose("choice:2")

    # 張角還在：他親自交密令；第 10 週張角病逝：由張寶在下曲陽交令
    _ready(game, 3)
    assert ranks.check_summons(state, on) == ["張角召你到廣宗。"]
    assert (p.summons.event, p.summons.figure) == ("promo_huang_4", "zhangjiao")
    assert standing("zhangjiao") == ("active", "guangzong")
    settle("zhangjiao_dies", "成")
    assert standing("zhangjiao")[0] == "retired"
    assert standing("zhangbao") == ("active", "xiaquyang")
    assert ranks.check_summons(state, on) == ["張寶召你到下曲陽。"]
    assert (p.summons.event, p.summons.figure, p.summons.location) == ("promo_huang_4_heir", "zhangbao", "xiaquyang")
    p.location = "xiaquyang"
    game.choose("act:summons")
    game.choose("choice:0")
    assert p.qualified and p.runic_pieces == 0
