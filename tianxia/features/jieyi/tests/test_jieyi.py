"""結義（tianxia/features/jieyi/；設計稿 v2 卷一，Joy 2026-11-07「先做丙，跨季保留關係」）：互換過名帖才邀得了、答應婉拒、
入義與滿員、割袍斷義與冷卻、剩一人就散、換季不清、假人的回法。"""
from __future__ import annotations

import pytest
from test_social import NOW, _as, _done, _player

from tianxia.core.option import Option
from tianxia.features.jieyi import actions, bots, rules
from tianxia.state import Mingtie, MingtieCopy

pytestmark = pytest.mark.whole_content


@pytest.fixture
def on(content):
    content.config.jieyi.enabled = True
    return content


def _swap(*games):
    """這幾個人兩兩互換過名帖（直接放進名帖匣，換帖本身是名帖的測試在管）。"""
    for g in games:
        for h in games:
            if g is not h:
                g.state.player.mingtie_box.append(MingtieCopy(name=h.state.player.name, card=Mingtie(version=1), when="", place="", season=1))
        _done(g)


def _btn(game, name):
    card = game.peer_card(name)
    return next(b for b in card["actions"] if b["action"] == "jieyi")


def _ask_and_answer(content, a, b_name, now, yes=True):
    a.peer_act(b_name, "jieyi", {"arg": "ask"})
    _done(a)
    b = _as(content, a.world, b_name, now)
    pick = next(o.id for o in b.options() if o.id.startswith(f"jieyi:{'yes' if yes else 'no'}:"))
    msgs = b.choose(pick)
    _done(b)
    return b, msgs


def _book(game):
    return game.world.read().jieyi


@pytest.mark.smoke
def test_two_who_swapped_cards_can_swear_brotherhood(on):
    a, b = _player(on, "甲"), _player(on, "乙")
    _swap(a, b)
    a = _as(on, a.world, "甲", NOW + 1)
    assert _btn(a, "乙")["enabled"] and _btn(a, "乙")["label"] == "邀他結義"
    b, msgs = _ask_and_answer(on, a, "乙", NOW + 2)
    bond = rules.bond_of(_book(b), "甲")
    assert bond is not None and bond.members == ["甲", "乙"]
    assert rules.FORMED.format(him="甲", bond="小鎮二義", rank="二") in msgs
    a = _as(on, a.world, "甲", NOW + 3)
    assert not _btn(a, "乙")["enabled"] and "同為" in _btn(a, "乙")["label"]
    view = a.feature_status()["jieyi"]
    assert view["name"] == "小鎮二義" and view["rank"] == "一" and [m["name"] for m in view["members"]] == ["甲", "乙"]
    assert len(view["log"]) == 1 and "結義" in view["log"][0]


def test_no_cards_no_brotherhood_and_closed_says_nothing(on):
    a, _b = _player(on, "甲"), _player(on, "乙")
    btn = _btn(a, "乙")
    assert not btn["enabled"] and btn["note"] == rules.NEED_CARDS
    on.config.jieyi.enabled = False
    assert not any(b["action"] == "jieyi" for b in a.peer_card("乙")["actions"])


def test_declining_leaves_no_bond(on):
    a, b = _player(on, "甲"), _player(on, "乙")
    _swap(a, b)
    a = _as(on, a.world, "甲", NOW + 1)
    b, msgs = _ask_and_answer(on, a, "乙", NOW + 2, yes=False)
    assert msgs and rules.bond_of(_book(b), "乙") is None and not _book(b).offers


def test_a_member_brings_in_a_third_and_the_name_follows_the_count(on):
    on.config.jieyi.max_members = 3
    a, b, c, d = (_player(on, n) for n in "甲乙丙丁")
    _swap(a, b, c, d)
    a = _as(on, a.world, "甲", NOW + 1)
    _ask_and_answer(on, a, "乙", NOW + 2)
    b = _as(on, a.world, "乙", NOW + 3)
    _ask_and_answer(on, b, "丙", NOW + 4)
    bk = _book(a)
    bond = rules.bond_of(bk, "丙")
    assert bond.members == ["甲", "乙", "丙"] and rules.bond_name(bk, on, bond).endswith("三義") and rules.rank_of(bond, "丙") == 3
    a = _as(on, a.world, "甲", NOW + 5)
    btn = _btn(a, "丁")
    assert not btn["enabled"] and "滿 3 人" in btn["note"]


def test_leaving_cools_down_and_the_last_one_left_ends_it(on):
    a, b = _player(on, "甲"), _player(on, "乙")
    _swap(a, b)
    a = _as(on, a.world, "甲", NOW + 1)
    _ask_and_answer(on, a, "乙", NOW + 2)
    a = _as(on, a.world, "甲", NOW + 3)
    msgs = actions.leave(a)
    _done(a)
    assert "割袍斷義" in msgs[0]
    bk = _book(a)
    assert rules.bond_of(bk, "甲") is None and rules.bond_of(bk, "乙") is None and not bk.bonds  # 剩一人就散
    assert rules.cooling(bk, on.config.jieyi, "甲", NOW + 4) > 0 and rules.cooling(bk, on.config.jieyi, "乙", NOW + 4) == 0
    a = _as(on, a.world, "甲", NOW + 5)
    assert "小時後才能再結義" in _btn(a, "乙")["note"]


def test_the_bond_outlives_the_season(on):
    a, b = _player(on, "甲"), _player(on, "乙")
    _swap(a, b)
    a = _as(on, a.world, "甲", NOW + 1)
    _ask_and_answer(on, a, "乙", NOW + 2)
    season = a.world.read().season_number
    a.world.mutate(lambda shared: setattr(shared, "season_number", shared.season_number + 1))
    shared = a.world.read()
    assert shared.season_number == season + 1 and rules.bond_of(shared.jieyi, "乙").members == ["甲", "乙"]


def test_an_empty_book_is_not_written():
    from tianxia.world_state import SharedWorldState

    assert "jieyi" not in SharedWorldState().model_dump()


def test_bots_answer_some_offers_after_a_while_and_never_both_ways(on):
    a, b = _player(on, "甲"), _player(on, "乙", bot=True)
    _swap(a, b)
    a = _as(on, a.world, "甲", NOW + 1)
    a.peer_act("乙", "jieyi", {"arg": "ask"})
    _done(a)
    offer = _book(a).offers[0]
    b = _as(on, a.world, "乙", NOW + 2)
    yes, no = Option(id=f"jieyi:yes:{offer.id}", label=""), Option(id=f"jieyi:no:{offer.id}", label="")
    assert bots.score(b, yes) is None and bots.score(b, no) is None  # 還沒等夠
    b = _as(on, a.world, "乙", NOW + 1 + on.config.jieyi.bot_reply_seconds + 1)
    picked = [s for s in (bots.score(b, yes), bots.score(b, no)) if s is not None]
    assert len(picked) <= 1
    assert bots.score(b, yes) == bots.score(b, yes)  # 同一張永遠一樣
