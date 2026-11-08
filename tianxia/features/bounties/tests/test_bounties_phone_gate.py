"""綁手機才能用（帳號與客服第 205 批；設計 4.5）：掛通緝（鍵 wanted）、揭與交玩家掛的單（鍵 bounty_post，只看發單的是不是玩家：
Bounty.poster 有字）。只問動手的那一個人；系統掛的單（poster 空著）照舊揭得了；phone_gate 關著一個字不變。

角色開在同一個資料庫；每一個動作照伺服器的做法先從資料庫重讀自己，做完存回去（同 test_bounties）。"""
from __future__ import annotations

import random

import phone_kit
import pytest

from conftest import install_season_one
from tianxia import rules
from tianxia.characters import CharacterStore
from tianxia.core.identity_base import PHONE_NEEDED
from tianxia.engine import Game
from tianxia.features.bounties import actions as bounty_actions
from tianxia.models import FactionDef
from tianxia.state import Bounty

pytestmark = pytest.mark.whole_content

NOW = 1000.0
WEEK = 10_000_000.0


@pytest.fixture
def setup(content, world, tmp_path, monkeypatch):
    """第一季：官軍的甲、黃巾的乙、散人丙，都在城鎮；三個都有帳號、都沒綁手機。"""
    phone_kit.keyed(monkeypatch, tmp_path)
    install_season_one(content)
    content.scenario.factions = [
        FactionDef(id="guan", name="官軍", join_at=["town"]),
        FactionDef(id="huang", name="黃巾", join_at=["lake"]),
    ]
    content.config.auto_open_first_season = True
    content.config.newbie_days = -1
    for name, faction, login in (("甲", "guan", "ray1"), ("乙", "huang", "ray2"), ("丙", None, "ray3")):
        game = Game.new(content, name, rng=random.Random(0), world=world)
        game.client = None
        rules.learn_skill(game.state, content, "fist")
        p = game.state.player
        p.faction, p.location, p.stamina = faction, "town", 100.0
        p.stats["silver"] = 200
        game.sync(NOW)
        CharacterStore(world.db).save(game.state)
        phone_kit.account(world.db, name, login)
    return content, world


def _do(content, world, name, act):
    state = CharacterStore(world.db).load(name)
    game = Game(content, state, random.Random(0), world)
    game.client = None
    game.sync(NOW)
    msgs = act(game)
    game._save_season()
    CharacterStore(world.db).save(game.state)
    return msgs, game


def _post(world, **kw) -> Bounty:
    def add(season):
        season.bounty_seq += 1
        season.bounties.append(Bounty(id=f"b{season.bounty_seq}", week=1, expires=WEEK, **kw))

    world.mutate_season(add)
    return world.get_season().bounties[-1]


def _wanted_button(content, world):
    card = _do(content, world, "甲", lambda g: g.peer_card("乙"))[0]
    return [b for b in card["actions"] if b["action"] == "wanted"]


def _board(content, world, name="丙"):
    _do(content, world, name, lambda g: g.choose("act:bounties"))
    return {o.id: (o.label, o.enabled, o.note) for o in _do(content, world, name, lambda g: g.options(odds=False))[0]}


def _two_wanted(world):
    player = _post(world, kind="wanted", faction="guan", silver=50, deeds=3, poster="甲", target="乙")
    system = _post(world, kind="wanted", faction="guan", silver=0, deeds=3, poster=None, target="乙")
    return player, system


def test_post_wanted_blocked(setup):
    content, world = setup
    phone_kit.gate(content, on=True)
    assert _do(content, world, "甲", lambda g: g.peer_act("乙", "wanted", {"amount": 50}))[0] == [PHONE_NEEDED]
    assert CharacterStore(world.db).load("甲").player.stats["silver"] == 200 and not world.get_season().bounties
    phone_kit.bind(world.db, "ray1", phone_kit.PHONE_A)
    msgs = _do(content, world, "甲", lambda g: g.peer_act("乙", "wanted", {"amount": 50}))[0]
    assert msgs[0].startswith("你押了") and world.get_season().bounties[0].poster == "甲"


def test_wanted_card_greyed(setup):
    content, world = setup
    phone_kit.gate(content, on=False)
    [plain] = _wanted_button(content, world)
    assert plain["enabled"]
    phone_kit.gate(content, on=True)
    [grey] = _wanted_button(content, world)
    assert (grey["enabled"], grey["note"], grey["label"]) == (False, PHONE_NEEDED, "通緝")


def test_take_player_wanted_blocked_but_system_wanted_not(setup):
    content, world = setup
    player, system = _two_wanted(world)
    phone_kit.gate(content, on=True)
    _board(content, world)
    # 選單上那一顆是灰的，choose 照舊先擋（灰的選項回通用那一句）；直接叫動作（兩個分頁搶、假人程式）回手機那一句
    assert _do(content, world, "丙", lambda g: g.choose(f"bounty:take:{player.id}"))[0] == ["（此刻無法這麼做。）"]
    assert _do(content, world, "丙", lambda g: bounty_actions.bounty(g, f"take:{player.id}"))[0] == [PHONE_NEEDED]
    assert world.get_season().bounties[0].takers == []
    msgs = _do(content, world, "丙", lambda g: g.choose(f"bounty:take:{system.id}"))[0]
    assert any(m.startswith("你揭下了") for m in msgs)


def test_give_to_player_posted_blocked(setup):
    """交（求兵）也只看發單的是不是玩家：poster 有字的那張先問手機（現行求兵都是系統掛的，這一條守的是判斷的位置）。"""
    content, world = setup
    posted = _post(world, kind="arms", faction="guan", silver=10, deeds=1, poster="甲")
    phone_kit.gate(content, on=True)
    assert _do(content, world, "丙", lambda g: bounty_actions.bounty(g, f"give:{posted.id}:兵:1"))[0] == [PHONE_NEEDED]
    phone_kit.gate(content, on=False)
    assert _do(content, world, "丙", lambda g: bounty_actions.bounty(g, f"give:{posted.id}:兵:1"))[0] != [PHONE_NEEDED]


def test_board_option_greyed_only_for_player_posted(setup):
    content, world = setup
    player, system = _two_wanted(world)
    phone_kit.gate(content, on=True)
    board = _board(content, world)
    label, enabled, _ = board[f"bounty:take:{player.id}"]
    assert not enabled and label.endswith(f"（{PHONE_NEEDED}）")
    assert board[f"bounty:take:{system.id}"][1] is True


def test_gate_off_board_unchanged(setup):
    content, world = setup
    _two_wanted(world)
    phone_kit.gate(content, on=False, identity=False)
    whole_off = (_board(content, world), _wanted_button(content, world))
    phone_kit.gate(content, on=False)
    assert (_board(content, world), _wanted_button(content, world)) == whole_off
    assert all(enabled for key, (_, enabled, _) in whole_off[0].items() if key.startswith("bounty:take:"))
