"""切磋（玩家互動第二層，企劃者 2026-10-08「互動的兩層也可以派下去做了」）：同一地點的人發邀請、對方答應才打；
本人對本人的單次判定，不扣氣血、不掉銀兩，雙方各一份戰報、經驗與心得照 Config.spar，同一對人每個遊戲日有上限。

兩個角色開在同一個資料庫；每一個動作照伺服器的做法先從資料庫重讀自己（server._locked），做完存回去。"""
from __future__ import annotations

import random

import pytest

from conftest import FixedRandom, install_season_one
from tianxia import encounter, invites, rules, social, team
from tianxia.characters import CharacterStore
from tianxia.engine import Game

NOW = 1000.0


@pytest.fixture
def pair(content, world):
    install_season_one(content)
    content.config.auto_open_first_season = True
    games = []
    for name in ("甲", "乙"):
        game = Game.new(content, name, rng=random.Random(0), world=world)
        game.client = None
        rules.learn_skill(game.state, content, "fist")
        game.state.player.stamina = 100.0
        game.sync(NOW)
        CharacterStore(world.db).save(game.state)
        games.append(game)
    return content, world


def _do(content, world, name, act, rng=None):
    """照伺服器：重讀這個人、補算到此刻、做一個動作、存回去（連同共用賽季）。回傳（訊息, 做完的 Game）。"""
    state = CharacterStore(world.db).load(name)
    game = Game(content, state, rng or random.Random(0), world)
    game.client = None
    game.sync(NOW)
    msgs = act(game)
    game._save_season()
    CharacterStore(world.db).save(game.state)
    return msgs, game


def _load(world, name):
    return CharacterStore(world.db).load(name)


def _ids(content, world, name):
    return {o.id for o in _do(content, world, name, lambda g: g.options(odds=False))[1].options(odds=False)}


def _invite_id(world):
    return world.get_season().invites[0].id


def test_an_invite_shows_up_on_both_menus(pair):
    content, world = pair
    msgs, _ = _do(content, world, "甲", lambda g: g.peer_act("乙", "spar", {"arg": "invite"}))
    assert "等他回覆" in msgs[-1]
    iid = _invite_id(world)
    assert {f"invite:yes:{iid}", f"invite:no:{iid}"} <= _ids(content, world, "乙")
    assert f"invite:cancel:{iid}" in _ids(content, world, "甲")
    status = _do(content, world, "乙", lambda g: g.status_data())[0]
    assert status["invites"]["incoming"][0]["who"] == "甲"
    assert status["invites"]["incoming"][0]["seconds_left"] == content.config.invite_ttl_seconds


def test_accepting_fights_once_and_both_get_a_record(pair):
    content, world = pair
    cost, cfg = content.config.action_cost["train"], content.config.spar
    before = {n: _load(world, n) for n in ("甲", "乙")}
    _do(content, world, "甲", lambda g: g.peer_act("乙", "spar", {"arg": "invite"}))
    iid = _invite_id(world)
    _do(content, world, "乙", lambda g: g.choose(f"invite:yes:{iid}"))
    after = {n: _load(world, n) for n in ("甲", "乙")}
    tiers = {}
    for name in ("甲", "乙"):
        b, a = before[name].player, after[name].player
        assert a.stamina == pytest.approx(b.stamina - cost, abs=0.5)  # 同一刻，回復可以不計
        assert a.member.neili == b.member.neili and a.stats["silver"] == b.stats["silver"]  # 不扣氣血、不掉銀兩
        record = after[name].battles[0]
        assert record.kind == "spar" and len(record.ours) == 1 and record.rounds
        assert record.opponent == ("乙" if name == "甲" else "甲")
        assert after[name].battle_card == record.id
        want = cfg.win_xinde if record.tier in team.WIN_TIERS else cfg.draw_xinde if record.tier in team.DRAW_TIERS else cfg.lose_xinde
        assert a.stats["xinde"] - b.stats.get("xinde", 0) == want == record.xinde
        assert record.exp == cfg.exp
        tiers[name] = record.tier
        assert any("切磋" in e.title for e in after[name].journal)
    won = {n for n, t in tiers.items() if t in team.WIN_TIERS}
    drawn = {n for n, t in tiers.items() if t in team.DRAW_TIERS}
    assert (len(won) == 1 and len(drawn) == 0) or drawn == {"甲", "乙"}  # 一邊贏另一邊輸，不然兩邊都平手
    assert world.get_season().invites == []


def test_the_stronger_one_wins(pair):
    """威力差很多的兩個人：強的那一邊穩贏（判定照 encounter 的比例門檻）。"""
    content, world = pair
    weak = _load(world, "乙")
    weak.player.member.wugong_id = None  # 沒有武學：威力 0
    CharacterStore(world.db).save(weak)
    _do(content, world, "乙", lambda g: g.peer_act("甲", "spar", {"arg": "invite"}))
    _do(content, world, "甲", lambda g: g.choose(f"invite:yes:{_invite_id(world)}"), rng=FixedRandom(0.5))
    assert _load(world, "甲").battles[0].tier == "大勝"
    assert _load(world, "乙").battles[0].tier == "落敗"
    assert _load(world, "甲").battles[0].difficulty == 0  # 寫的是對手的威力


def test_the_mirror_reads_from_the_other_side():
    win = encounter.EncounterResult(tier="大勝", margin=60, our_power=100, difficulty=40)
    assert Game._spar_mirror(win, 40).tier == "落敗"
    lose = encounter.EncounterResult(tier="落敗", margin=-80, our_power=40, difficulty=100)
    mirrored = Game._spar_mirror(lose, 100)
    assert (mirrored.tier, mirrored.margin, mirrored.our_power, mirrored.difficulty) == ("大勝", 80, 100, 40)
    close = encounter.EncounterResult(tier="落敗", margin=-35, our_power=100, difficulty=60)
    assert Game._spar_mirror(close, 60).tier == "險勝"  # 強的那一邊運氣差輸了，差距不到他威力的五成：你險勝
    draw = encounter.EncounterResult(tier="僵持", margin=-5, our_power=40, difficulty=40)
    assert Game._spar_mirror(draw, 40).tier == "僵持"


def test_a_pair_spars_at_most_per_pair_day_times_a_day(pair):
    content, world = pair
    for _ in range(content.config.spar.per_pair_day):
        _do(content, world, "甲", lambda g: g.peer_act("乙", "spar", {"arg": "invite"}))
        _do(content, world, "乙", lambda g: g.choose(f"invite:yes:{_invite_id(world)}"))
    msgs, _ = _do(content, world, "乙", lambda g: g.peer_act("甲", "spar", {"arg": "invite"}))  # 換誰發都一樣
    assert "今天已經切磋過" in msgs[-1] and world.get_season().invites == []
    card = _do(content, world, "甲", lambda g: g.peer_card("乙"))[0]
    assert [(b["label"], b["enabled"]) for b in card["actions"] if b["action"] == "spar"] == [("切磋", False)]


def test_declining_tells_the_sender(pair):
    content, world = pair
    _do(content, world, "甲", lambda g: g.peer_act("乙", "spar", {"arg": "invite"}))
    stamina = _load(world, "乙").player.stamina
    _do(content, world, "乙", lambda g: g.choose(f"invite:no:{_invite_id(world)}"))
    assert world.get_season().invites == []
    assert any("婉拒" in e.title for e in _load(world, "甲").journal)
    assert _load(world, "乙").player.stamina == stamina and not _load(world, "乙").battles


def test_the_sender_can_take_it_back(pair):
    content, world = pair
    _do(content, world, "甲", lambda g: g.peer_act("乙", "spar", {"arg": "invite"}))
    _do(content, world, "甲", lambda g: g.choose(f"invite:cancel:{_invite_id(world)}"))
    assert world.get_season().invites == []
    assert not any(i.startswith("invite:") for i in _ids(content, world, "乙"))


def test_one_waiting_invite_per_pair(pair):
    content, world = pair
    _do(content, world, "甲", lambda g: g.peer_act("乙", "spar", {"arg": "invite"}))
    msgs, _ = _do(content, world, "乙", lambda g: g.peer_act("甲", "spar", {"arg": "invite"}))
    assert "已經有一張" in msgs[-1] and len(world.get_season().invites) == 1


def test_an_invite_runs_out(pair):
    content, world = pair
    _do(content, world, "甲", lambda g: g.peer_act("乙", "spar", {"arg": "invite"}))
    season = world.get_season()
    season.time += content.config.invite_ttl_seconds
    assert invites.incoming(season, "乙") == []


@pytest.mark.parametrize("why", ["away", "resting", "tired", "nobody", "self"])
def test_refusals(pair, why):
    content, world = pair
    target = "乙"
    other = _load(world, "乙")
    if why == "away":
        other.player.location = next(l for l in content.locations if l != other.player.location)
    elif why == "resting":
        other.player.resting_since = 0.0
    elif why == "tired":
        other.player.stamina = 0.0
    elif why == "nobody":
        target = "丙"
    elif why == "self":
        target = "甲"
    CharacterStore(world.db).save(other)
    msgs, _ = _do(content, world, "甲", lambda g: g.peer_act(target, "spar", {"arg": "invite"}))
    assert world.get_season().invites == []
    gone = social.GONE
    assert {"away": gone, "resting": "正忙", "tired": "體力不夠", "nobody": gone, "self": gone}[why] in msgs[-1]


def test_leaving_before_the_answer_calls_it_off(pair):
    content, world = pair
    _do(content, world, "甲", lambda g: g.peer_act("乙", "spar", {"arg": "invite"}))
    sender = _load(world, "甲")
    sender.player.location = next(l for l in content.locations if l != sender.player.location)
    CharacterStore(world.db).save(sender)
    msgs, _ = _do(content, world, "乙", lambda g: g.choose(f"invite:yes:{_invite_id(world)}"))
    assert msgs[0] == social.GONE and world.get_season().invites == []
    assert not _load(world, "乙").battles


def test_nothing_while_the_switch_is_off(content, world):
    content.config.auto_open_first_season = True
    for name in ("甲", "乙"):
        game = Game.new(content, name, rng=random.Random(0), world=world)
        game.sync(NOW)
        CharacterStore(world.db).save(game.state)
    msgs, game = _do(content, world, "甲", lambda g: g.peer_act("乙", "spar", {"arg": "invite"}))
    assert msgs == ["（此刻無法這麼做。）"] and "invites" not in game.status_data()
    assert not any(b["action"] == "spar" for b in game.peer_card("乙")["actions"])


def test_the_other_side_is_told(pair, monkeypatch):
    """伺服器做完動作，被邀的人（答應、婉拒時是發邀請的人）開著的分頁也刷新（server._tell_tabs 讀 Game.touched）。"""
    import server

    content, world = pair
    calls = []

    class Hub:
        def notify(self, name, kind="self"):
            calls.append(name)

    monkeypatch.setattr(server, "HUB", Hub())
    _, game = _do(content, world, "甲", lambda g: g.peer_act("乙", "spar", {"arg": "invite"}))
    assert game.touched == {"乙"}
    server._tell_tabs(game)
    assert calls == ["甲", "乙"] and game.touched == set()


@pytest.mark.parametrize(("roll", "answer"), [(0.0, "yes"), (0.99, "no")])
def test_a_bot_answers_on_its_own_turn(pair, roll, answer):
    """假人在自己那一輪看到邀請才答：多半答應、有時婉拒（跟真人一樣），答的走同一個選項。"""
    from tianxia import bot_policy

    content, world = pair
    _do(content, world, "甲", lambda g: g.peer_act("乙", "spar", {"arg": "invite"}))
    iid = _invite_id(world)
    _, bot_game = _do(content, world, "乙", lambda g: None)
    assert bot_policy._answer_invite(bot_game, FixedRandom(roll)) == f"invite:{answer}:{iid}"


def test_a_tired_bot_declines(pair):
    from tianxia import bot_policy

    content, world = pair
    _do(content, world, "甲", lambda g: g.peer_act("乙", "spar", {"arg": "invite"}))
    tired = _load(world, "乙")
    tired.player.stamina = 1.0
    CharacterStore(world.db).save(tired)
    _, bot_game = _do(content, world, "乙", lambda g: None)
    assert bot_policy._answer_invite(bot_game, FixedRandom(0.0)).startswith("invite:no:")


def test_the_card_buttons_follow_the_invite(pair):
    """玩家卡上：沒有邀請是「切磋」；他邀了你是「答應切磋」「婉拒」；你邀了他是「收回切磋邀請」。按卡上的鈕跟按選單一樣。"""
    content, world = pair

    def spar_buttons(name, other):
        card = _do(content, world, name, lambda g: g.peer_card(other))[0]
        return [(b["label"], b["arg"]) for b in card["actions"] if b["action"] == "spar"]

    assert spar_buttons("甲", "乙") == [("切磋", "invite")]
    _do(content, world, "甲", lambda g: g.peer_act("乙", "spar", {"arg": "invite"}))
    assert spar_buttons("甲", "乙") == [("收回切磋邀請", "cancel")]
    assert spar_buttons("乙", "甲") == [("答應切磋", "yes"), ("婉拒", "no")]
    msgs, _ = _do(content, world, "乙", lambda g: g.peer_act("甲", "spar", {"arg": "cancel"}))  # 不是你發的收不回
    assert msgs == ["這份邀請已經不在了。"] and len(world.get_season().invites) == 1
    _do(content, world, "乙", lambda g: g.peer_act("甲", "spar", {"arg": "yes"}))
    assert _load(world, "甲").battles[0].kind == _load(world, "乙").battles[0].kind == "spar"
    assert spar_buttons("甲", "乙") == [("切磋", "invite")]
