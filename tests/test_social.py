"""玩家之間的互動（social.py）：第一層「此地還有誰」與玩家卡、卡上動作的登記表。"""
from __future__ import annotations

import random

import pytest

from tianxia import social
from tianxia.characters import CharacterStore
from tianxia.engine import Game
from tianxia.state import BotProfile

NOW = 1_000_000.0


def _player(content, name, *, at="town", now=NOW, bot=False, save=True):
    game = Game.new(content, name, rng=random.Random(0))
    game.sync(now)
    game.state.player.location = at
    if bot:
        game.state.player.bot = BotProfile(personality="普通", seed=1)
    if save:
        CharacterStore(game.world.db).save(game.state)
    return game


def test_people_in_the_same_place_see_each_other(content):
    a = _player(content, "甲")
    _player(content, "乙")
    _player(content, "丙", at="lake")  # 別的地方
    assert a.peers_here() == [{"name": "乙", "side": "散人"}]


def test_only_recently_seen_people_are_listed(content):
    gap = content.config.presence_seconds
    a = _player(content, "甲", now=NOW + gap + 10)
    _player(content, "乙", now=NOW)  # 上次同步是 presence_seconds 以前：下線了
    _player(content, "丙", now=NOW + 20)
    assert [p["name"] for p in a.peers_here()] == ["丙"]


def test_people_on_the_road_are_not_listed_and_see_nobody(content):
    a = _player(content, "甲")
    b = _player(content, "乙", save=False)
    b.state.player.journey = _journey(b)
    CharacterStore(b.world.db).save(b.state)
    assert a.peers_here() == []
    assert b.peers_here() == []


def _journey(game):
    from tianxia.state import Journey

    return Journey(mode="walk", path=["lake"], arrive_at=[game.state.world.time + 3600])


def test_bots_are_listed_the_same_way_as_people(content):
    a = _player(content, "甲")
    _player(content, "乙", bot=True)
    _player(content, "丙")
    here = a.peers_here()
    assert sorted(p["name"] for p in here) == ["丙", "乙"] and all(p == {"name": p["name"], "side": "散人"} for p in here)
    assert a.peer_card("乙").keys() == a.peer_card("丙").keys()


def test_the_card_shows_title_level_and_worn_arts(content):
    a = _player(content, "甲")
    b = _player(content, "乙")
    card = a.peer_card("乙")
    assert card["name"] == "乙" and card["affiliation"] == "散人" and card["level"] == b.state.player.member.level
    kinds = [row["kind"] for row in card["arts"]]
    assert set(kinds) <= {"內功", "武學"} and all(row["name"] and row["quality"] for row in card["arts"])
    assert card["actions"] == [] or all("action" in x for x in card["actions"])


def test_someone_who_left_has_no_card(content):
    a = _player(content, "甲")
    _player(content, "乙", at="lake")
    assert a.peer_card("乙") is None and a.peer_card("沒這個人") is None
    assert a.peer_act("乙", "anything") == [social.GONE]


@pytest.fixture
def poke():
    """測試用的一種互動：卡上一顆鈕，按了在對方的銀兩上加 1。測完拿掉。"""
    def run(game, other, params):
        other.state.player.stats["silver"] = other.state.player.stats.get("silver", 0) + 1
        return [f"你戳了{other.state.player.name}一下（{params.get('arg')}）。"]

    action = social.register(social.CardAction(
        id="poke", buttons=lambda game, other: [social.CardButton(action="poke", label="戳一下", arg="x")], run=run,
    ))
    yield action
    social.ACTIONS.pop("poke", None)


def test_registered_actions_show_on_every_card_and_change_the_other_save(content, poke):
    a = _player(content, "甲")
    b = _player(content, "乙")
    silver = b.state.player.stats.get("silver", 0)
    card = a.peer_card("乙")
    assert {"action": "poke", "label": "戳一下", "arg": "x"}.items() <= card["actions"][0].items()
    assert a.peer_act("乙", "poke", {"arg": "x"}) == ["你戳了乙一下（x）。"]
    stored = CharacterStore(a.world.db).load("乙")
    assert stored.player.stats["silver"] == silver + 1
    assert stored.last_real == b.state.last_real  # 替他寫東西不替他補算時間：下了線的人不會因此一直掛在名單上
    assert a.peer_act("乙", "no-such") == ["（沒有這個動作。）"]
