"""綁手機才能用（帳號與客服第 205 批；設計 4.5）：截殺、切磋與論武的發起與答應、贈物。只問動手的那一個人：
沒綁手機（不是假人）被擋、回 identity_base.PHONE_NEEDED、什麼都不動，卡上那一顆灰掉寫同一句；綁了的、假人照舊；
對手是沒綁的真人、綁了的真人、假人，發起人看到的逐字相同；phone_gate 關著（或 identity 整包關著）一個字不變。

每一種情形各開一個資料庫（tmp_path 底下），兩個角色照伺服器的做法每個動作先重讀、做完存回去（同 test_raid、test_spar）。"""
from __future__ import annotations

import random

import phone_kit
import pytest

from conftest import install_season_one
from tianxia import rules
from tianxia.characters import CharacterStore
from tianxia.core.identity_base import PHONE_NEEDED
from tianxia.engine import Game
from tianxia.models import FactionDef
from tianxia.sqlite_world import open_world
from tianxia.state import BotProfile

pytestmark = pytest.mark.whole_content

NOW = 1000.0
KINDS = ("raid", "spar", "discuss", "gift")
ACT = {
    "raid": {},
    "spar": {"arg": "invite"},
    "discuss": {"arg": "invite:insight:feng"},
    "gift": {"arg": "material", "choice": "gang_1", "amount": 1},
}
LOGIN = {"甲": ("ray1", phone_kit.PHONE_A), "乙": ("ray2", phone_kit.PHONE_B)}


@pytest.fixture(autouse=True)
def _season(content, tmp_path, monkeypatch):
    content.skills["fist"].quality = "下品"  # 同 test_discuss：長拳當論武的那一門
    phone_kit.keyed(monkeypatch, tmp_path)
    install_season_one(content)
    content.config.auto_open_first_season = True
    content.config.newbie_days = -1
    content.scenario.factions = [
        FactionDef(id="guan", name="官軍", join_at=["town"]),
        FactionDef(id="huang", name="黃巾", join_at=["lake"]),
    ]


def _world(content, tmp_path, tag: str, me: str = "bound", them: str = "unbound"):
    """甲（官軍）、乙（黃巾）都在湖畔。me／them：none（沒帳號的真人）、unbound（有帳號沒綁手機）、bound（綁了）、bot（假人，沒帳號）。"""
    world = open_world(tmp_path / f"{tag}.db")
    for name, faction, insight, wugong, who in (("甲", "guan", "feng", "basic_fist", me), ("乙", "huang", "huo", "fist", them)):
        game = Game.new(content, name, rng=random.Random(0), world=world)
        game.client = None
        rules.learn_skill(game.state, content, "fist")
        p = game.state.player
        p.faction, p.location, p.stamina = faction, "lake", 100.0
        p.stats["silver"], p.stats["xinde"] = 200, 100
        p.member.wugong_id, p.insights = wugong, [insight]
        p.materials["gang_1"] = 3
        if who == "bot":
            p.bot = BotProfile(personality="普通", seed=1)
        game.sync(NOW)
        CharacterStore(world.db).save(game.state)
        if who in ("unbound", "bound"):
            login, phone = LOGIN[name]
            phone_kit.account(world.db, name, login, phone if who == "bound" else None)
    return world


def _do(content, world, name, act):
    state = CharacterStore(world.db).load(name)
    game = Game(content, state, random.Random(0), world)
    game.client = None
    game.sync(NOW)
    msgs = act(game)
    game._save_season()
    CharacterStore(world.db).save(game.state)
    return msgs, game


def _buttons(content, world, name, other, kind):
    card = _do(content, world, name, lambda g: g.peer_card(other))[0]
    return [b for b in card["actions"] if b["action"] == kind]


def _turn(content, world, kind):
    """甲看乙的卡上那一種鈕（全欄），再按下去（同一個亂數種子）：（鈕, 回話）。"""
    shown = _buttons(content, world, "甲", "乙", kind)
    return shown, _do(content, world, "甲", lambda g: g.peer_act("乙", kind, dict(ACT[kind])))[0]


def _footprint(world):
    me = CharacterStore(world.db).load("甲").player
    season = world.get_season()
    return (me.stamina, me.stats["silver"], dict(me.materials), dict(season.raids), len(season.invites),
            dict(CharacterStore(world.db).load("乙").player.materials))


@pytest.mark.parametrize("kind", KINDS)
def test_gate_off_cards_and_acts_unchanged(content, tmp_path, kind):
    """phone_gate 關（identity 開著）與 identity 整包關著：沒綁手機的人卡上的鈕與按下去的回話逐字相同，跟閘開著綁了的也一樣。"""
    phone_kit.gate(content, on=False, identity=False)
    whole_off = _turn(content, _world(content, tmp_path, "off", me="unbound"), kind)
    phone_kit.gate(content, on=False)
    gate_off = _turn(content, _world(content, tmp_path, "gate_off", me="unbound"), kind)
    phone_kit.gate(content, on=True)
    bound = _turn(content, _world(content, tmp_path, "bound", me="bound"), kind)
    assert whole_off == gate_off == bound
    assert whole_off[0] and all(b["note"] != PHONE_NEEDED for b in whole_off[0])


@pytest.mark.parametrize("kind", KINDS)
@pytest.mark.parametrize("me", ["unbound", "none"])
def test_unbound_actor_blocked(content, tmp_path, kind, me):
    """閘開、沒綁手機（有帳號、或真人卻查不到帳號）：回那一句，體力、銀兩、素材、冷卻、邀請都不動；卡上那一顆灰、note 是它。"""
    phone_kit.gate(content, on=True)
    world = _world(content, tmp_path, "w", me=me)
    shown = _buttons(content, world, "甲", "乙", kind)
    assert shown and all(not b["enabled"] and b["note"] == PHONE_NEEDED for b in shown)
    before = _footprint(world)
    assert _do(content, world, "甲", lambda g: g.peer_act("乙", kind, dict(ACT[kind])))[0] == [PHONE_NEEDED]
    assert _footprint(world) == before


@pytest.mark.parametrize("kind", KINDS)
def test_bound_actor_and_bot_actor_pass(content, tmp_path, kind):
    """閘開：綁了的人跟閘關著一樣；假人（沒帳號）跟閘關著的假人一樣。"""
    phone_kit.gate(content, on=False)
    plain = _turn(content, _world(content, tmp_path, "plain", me="bound"), kind)
    bot_plain = _turn(content, _world(content, tmp_path, "bot_plain", me="bot"), kind)
    phone_kit.gate(content, on=True)
    assert _turn(content, _world(content, tmp_path, "bound", me="bound"), kind) == plain
    assert _turn(content, _world(content, tmp_path, "bot", me="bot"), kind) == bot_plain
    assert all(b["note"] != PHONE_NEEDED for b in plain[0]) and plain[1] != [PHONE_NEEDED]


@pytest.mark.parametrize("kind", KINDS)
def test_initiator_sees_same_for_three_rivals(content, tmp_path, kind):
    """只問動手的人：對手是沒綁的真人、綁了的真人、假人，發起人（綁了）看到的卡（CardButton 全欄）與回話逐字相同。"""
    phone_kit.gate(content, on=True)
    seen = [_turn(content, _world(content, tmp_path, them, me="bound", them=them), kind) for them in ("unbound", "bound", "bot")]
    assert seen[0] == seen[1] == seen[2]
    assert seen[0][1] != [PHONE_NEEDED]


ANSWER = {"spar": "yes", "discuss": "yes:insight:huo"}


@pytest.mark.parametrize("kind", ["spar", "discuss"])
def test_blocked_accept_keeps_invite_and_sender_sees_nothing(content, tmp_path, kind):
    """沒綁的人答應：回那一句、邀請還在；發起人的存檔與他看對方的卡跟「沒人理」那一份逐字相同；答應鈕灰、婉拒照舊按得下去。"""
    phone_kit.gate(content, on=True)
    world = _world(content, tmp_path, "w", me="bound", them="unbound")
    _do(content, world, "甲", lambda g: g.peer_act("乙", kind, dict(ACT[kind])))
    ignored = (CharacterStore(world.db).load("甲").model_dump(), _buttons(content, world, "甲", "乙", kind))
    [inv] = world.get_season().invites
    answer = _buttons(content, world, "乙", "甲", kind)
    yes = [b for b in answer if b["arg"].startswith("yes")]
    assert yes and all(not b["enabled"] and b["note"] == PHONE_NEEDED for b in yes)
    assert [b for b in answer if b["arg"] == "no"][0]["enabled"]
    assert _do(content, world, "乙", lambda g: g.peer_act("甲", kind, {"arg": ANSWER[kind]}))[0] == [PHONE_NEEDED]
    assert [i.id for i in world.get_season().invites] == [inv.id]
    assert (CharacterStore(world.db).load("甲").model_dump(), _buttons(content, world, "甲", "乙", kind)) == ignored


@pytest.mark.parametrize("kind", ["spar", "discuss"])
def test_decline_and_cancel_not_blocked(content, tmp_path, kind):
    """婉拒、收回不擋：沒綁的人照舊婉拒得了；發邀請的人解綁之後照舊收回得了。"""
    phone_kit.gate(content, on=True)
    world = _world(content, tmp_path, "w", me="bound", them="unbound")
    _do(content, world, "甲", lambda g: g.peer_act("乙", kind, dict(ACT[kind])))
    msgs = _do(content, world, "乙", lambda g: g.peer_act("甲", kind, {"arg": "no"}))[0]
    assert msgs != [PHONE_NEEDED] and "婉拒" in msgs[-1] and not world.get_season().invites
    _do(content, world, "甲", lambda g: g.peer_act("乙", kind, dict(ACT[kind])))
    phone_kit.unbind(world.db, "ray1")
    msgs = _do(content, world, "甲", lambda g: g.peer_act("乙", kind, {"arg": "cancel"}))[0]
    assert "收回" in msgs[-1] and not world.get_season().invites


def test_discuss_request_none_when_blocked(content, tmp_path):
    """論武的 A 段：答應的人沒綁手機就不開取名單、不叫模型（C 段由 answer_invite 擋）；閘關著照舊開單。"""
    phone_kit.gate(content, on=True)
    world = _world(content, tmp_path, "w", me="bound", them="unbound")
    _do(content, world, "甲", lambda g: g.peer_act("乙", "discuss", dict(ACT["discuss"])))
    ask = lambda g: g.peer_request("甲", "discuss", {"arg": ANSWER["discuss"]})  # noqa: E731
    assert _do(content, world, "乙", ask)[0] is None
    phone_kit.gate(content, on=False)
    assert _do(content, world, "乙", ask)[0] is not None
