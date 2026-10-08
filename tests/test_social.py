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
    assert {"action": "poke", "label": "戳一下", "arg": "x"}.items() <= card["actions"][-1].items()  # order 100：排在內建的幾種後面
    assert a.peer_act("乙", "poke", {"arg": "x"}) == ["你戳了乙一下（x）。"]
    stored = CharacterStore(a.world.db).load("乙")
    assert stored.player.stats["silver"] == silver + 1
    assert stored.last_real == b.state.last_real  # 替他寫東西不替他補算時間：下了線的人不會因此一直掛在名單上
    assert a.peer_act("乙", "no-such") == ["（沒有這個動作。）"]


# ── 第二層：贈物、打招呼、結伴同行 ──


def _as(content, world, name, now):
    """伺服器那樣：讀他的存檔、補算到 now。做完要 _done 存回去。"""
    game = Game(content, CharacterStore(world.db).load(name), random.Random(0), world)
    game.client = None
    game.sync(now)
    return game


def _done(game):
    CharacterStore(game.world.db).save(game.state)


def _titles(game):
    return [e.title for e in game.state.journal]


def _lines(game):
    return [line for e in game.state.journal for line in e.lines + e.changes]


def test_a_gift_moves_silver_and_is_written_in_both_journals(content):
    a = _player(content, "甲")
    _player(content, "乙")
    a.state.player.stats["silver"] = 50
    card = a.peer_card("乙")
    silver = next(b for b in card["actions"] if b["action"] == "gift" and b["arg"] == "silver")
    assert silver["amount"] == 50 and silver["enabled"]
    assert a.peer_act("乙", "gift", {"arg": "silver", "amount": 80}) == ["（身上的銀兩不夠。）"]
    assert a.peer_act("乙", "gift", {"arg": "silver", "amount": "x"}) == ["（要送多少？）"]
    assert a.peer_act("乙", "gift", {"arg": "silver", "amount": 20})[0] == "你把銀子 20 兩送給了乙。"
    _done(a)
    b = _as(content, a.world, "乙", NOW + 5)
    assert a.state.player.stats["silver"] == 30 and b.state.player.stats["silver"] == 50 + 20
    assert "收禮・甲" in _titles(b) and "銀兩 +20" in _lines(b)
    assert "贈物・乙" in _titles(a) and "銀兩 -20" in _lines(a)


def test_materials_and_pills_can_be_given_too(content):
    a = _player(content, "甲")
    pills = _player(content, "乙").state.player.stamina_pills  # 建角送的
    a.state.player.materials = {"gang_1": 3}
    a.state.player.stamina_pills = 2
    card = a.peer_card("乙")
    mats = next(b for b in card["actions"] if b["arg"] == "material")
    assert mats["choices"] == [{"id": "gang_1", "label": content.materials["gang_1"].name, "max": 3}]
    assert a.peer_act("乙", "gift", {"arg": "material", "choice": "gang_1", "amount": 4}) == ["（身上沒有那麼多。）"]
    a.peer_act("乙", "gift", {"arg": "material", "choice": "gang_1", "amount": 2})
    a.peer_act("乙", "gift", {"arg": "pill", "amount": 2})
    stored = CharacterStore(a.world.db).load("乙")
    assert stored.player.materials == {"gang_1": 2} and stored.player.stamina_pills == pills + 2
    assert a.state.player.materials == {"gang_1": 1} and a.state.player.stamina_pills == 0
    assert not any(b["arg"] == "pill" for b in a.peer_card("乙")["actions"])  # 沒有丹了就不畫那一顆


def _calls(game):
    return game.calls_here()


def test_a_greeting_waits_for_a_reply_and_both_sides_remember_it(content):
    a = _player(content, "甲")
    _player(content, "乙")
    assert a.peer_act("乙", "greet", {"arg": "bow"}) == ["你向乙抱拳見禮。"]
    assert a.peer_act("乙", "greet", {"arg": "toast"}) == ["（乙還沒回禮。）"]
    assert all(not b["enabled"] for b in a.peer_card("乙")["actions"] if b["action"] == "greet")
    assert not any(o.id.startswith("invite:") for o in a.options())  # 打招呼不用收回
    _done(a)
    b = _as(content, a.world, "乙", NOW + 10)
    [call] = _calls(b)
    assert call["text"] == "甲向你抱拳見禮。" and [o["label"] for o in call["options"]] == ["抱拳還禮", "點頭致意"]
    assert b.choose(call["options"][0]["id"])[-1] == "你抱拳還禮。"
    _done(b)
    assert _calls(b) == []
    a = _as(content, a.world, "甲", NOW + 20)
    assert "你向乙抱拳見禮，乙抱拳還禮。" in _lines(a) and a.peer_card("乙")["actions"][0]["enabled"]


def test_an_unanswered_greeting_runs_out(content):
    a = _player(content, "甲")
    _player(content, "乙")
    a.peer_act("乙", "greet", {"arg": "taunt"})
    _done(a)
    later = NOW + content.config.invite_ttl_seconds / content.config.time_scale + 1
    b = _as(content, a.world, "乙", later)
    assert _calls(b) == [] and not any(o.id.startswith("invite:") for o in b.options())


def _walk_to_lake(game):
    return game.choose("move:lake")


def test_travelling_together_the_follower_copies_the_leaders_route_and_shares_road_gains(content):
    a = _player(content, "甲")
    _player(content, "乙")
    assert a.peer_act("乙", "travel") == ["你邀乙結伴同行，等他回應。"]
    _done(a)
    b = _as(content, a.world, "乙", NOW + 5)
    [call] = _calls(b)
    assert [o["label"] for o in call["options"]] == ["答應", "婉拒"]
    assert b.choose(call["options"][0]["id"])[-1] == "你答應與甲結伴同行，等他動身。"
    _done(b)
    a = _as(content, a.world, "甲", NOW + 6)
    assert a.party_view()["names"] == ["乙"]
    assert next(x for x in a.peer_card("乙")["actions"] if x["action"] == "travel")["enabled"] is False
    _walk_to_lake(a)
    a.state.player.leg_actions.discard("think")
    _done(a)
    b = _as(content, a.world, "乙", NOW + 7)
    assert b.state.player.journey == a.state.player.journey
    ids = [o.id for o in b.options()]
    assert "act:part" in ids and not any(i.startswith("road:back") for i in ids) and "act:halt" not in ids
    assert b.travel_refusal("town") == "跟著甲同行，要改道先分道揚鑣"
    xinde = b.state.player.stats.get("xinde", 0)
    _done(b)
    a = _as(content, a.world, "甲", NOW + 8)
    msgs = a.choose("road:think")
    assert "（同行的乙也有一份。）" in msgs
    _done(a)
    b = _as(content, a.world, "乙", NOW + 9)
    assert b.state.player.stats["xinde"] == xinde + content.config.road_think_xinde and "think" in b.state.player.leg_actions
    arrive = a.state.player.journey.arrive_at[-1]
    _done(b)
    far = NOW + (arrive - a.state.world.time) / content.config.time_scale + 60
    b = _as(content, a.world, "乙", far)
    assert b.state.player.location == "lake" and b.state.player.tagalong is None
    assert any("拱手作別" in line for line in _lines(b))


def test_a_follower_who_cannot_keep_up_is_left_behind(content):
    a = _player(content, "甲")
    b = _player(content, "乙")
    from tianxia.state import Tagalong

    b.state.player.tagalong = Tagalong(leader="甲", since=NOW)
    b.state.player.stamina = 0
    _done(b)
    a.set_move_mode("hurry")
    msgs = a.choose("move:lake:hurry")
    assert "乙沒能跟上，你們就此分開。" in msgs
    stored = CharacterStore(a.world.db).load("乙")
    assert stored.player.tagalong is None and stored.player.journey is None


def test_the_leader_halting_halts_the_follower_and_parting_frees_him(content):
    a = _player(content, "甲")
    b = _player(content, "乙")
    from tianxia.state import Tagalong

    b.state.player.tagalong = Tagalong(leader="甲", since=NOW)
    _done(b)
    a.state.world.flags.add("cave_open")
    a.state.player.surveyed |= {"lake", "cave"}  # 乙不認得寶洞也跟得去：路是帶頭的人認得的
    assert a.travel("cave")[-1] == "乙跟著你。"
    a.choose("act:halt")
    _done(a)
    b = _as(content, a.world, "乙", NOW + 1)
    assert b.state.player.journey.stop_at == 0 == a.state.player.journey.stop_at
    assert b.choose("act:part")[-1] == "你與甲分道揚鑣。"
    assert b.state.player.tagalong is None and any(o.id.startswith("road:back") for o in b.options())
    _done(b)
    assert a.party_view() is None


def test_a_rejected_or_stale_party_comes_to_nothing(content):
    a = _player(content, "甲")
    _player(content, "乙")
    a.peer_act("乙", "travel")
    _done(a)
    b = _as(content, a.world, "乙", NOW + 5)
    b.choose(_calls(b)[0]["options"][1]["id"])
    _done(b)
    a = _as(content, a.world, "甲", NOW + 6)
    assert "乙拱手婉拒了你的邀請。" in _lines(a)
    a.peer_act("乙", "travel")
    _done(a)
    b = _as(content, a.world, "乙", NOW + 7)
    b.choose(_calls(b)[0]["options"][0]["id"])
    _done(b)
    b = _as(content, a.world, "乙", NOW + 7 + content.config.party_wait_seconds + 1)
    assert b.state.player.tagalong is None and "甲遲遲沒有動身，你們各走各的。" in _lines(b)


@pytest.mark.parametrize("kind, arg, want", [
    ("greet", "bow", {"bow", "nod", None}),
    ("travel", "", {"yes", "no", None}),
])
def test_bots_answer_at_a_human_pace(content, kind, arg, want):
    """假人回打招呼、結伴邀請：剛收到不回；過了一陣子，各種假人（seed 不同）有回有拒有不理（None）。"""
    from tianxia import bot_policy

    a = _player(content, "甲")
    _player(content, "乙", bot=True)
    a.peer_act("乙", kind, {"arg": arg})
    _done(a)
    b = _as(content, a.world, "乙", NOW + 1)
    assert bot_policy.answer_call(b, b.state.player.bot) is None
    later = NOW + (bot_policy.REPLY_MIN_SECONDS + bot_policy.REPLY_SPREAD_SECONDS + 1) * content.config.time_scale
    b = _as(content, a.world, "乙", later)
    seen = set()
    for seed in range(60):
        b.state.player.bot.seed = seed
        option = bot_policy.answer_call(b, b.state.player.bot)
        seen.add(option.split(":")[1] if option else None)
    assert seen == want
    b.state.player.bot.seed = next(n for n in range(60) if (lambda o: o and o.split(":")[1] in ("bow", "yes"))(
        bot_policy.answer_call(b, b.state.player.bot.model_copy(update={"seed": n}))))
    bot_policy.take_turn(b, b.state.player.bot, random.Random(0))  # 照選單那一顆按下去
    assert _calls(b) == []


def test_a_bot_waiting_for_its_leader_stays_put(content):
    from tianxia import bot_policy
    from tianxia.state import Tagalong

    _player(content, "甲")
    b = _player(content, "乙", bot=True)
    b.state.player.tagalong = Tagalong(leader="甲", since=NOW)
    before = b.state.player.location
    for _ in range(5):
        bot_policy.take_turn(b, b.state.player.bot, random.Random(0))
    assert b.state.player.location == before and b.state.player.journey is None
