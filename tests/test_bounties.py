"""懸賞榜（PM 2026-10-08 派工「加強散人玩法」）：陣營每週一自動掛討伐、打探、護送；投靠了陣營的人可以花銀兩通緝敵對陣營的人。
散人兩邊的都能接，陣營的人只能接自己陣營的；接了才算，前 quota 個完成的人有賞（散人另記俠名）。

角色開在同一個資料庫；每一個動作照伺服器的做法先從資料庫重讀自己，做完存回去（同 test_raid）。"""
from __future__ import annotations

import random

import pytest

from conftest import install_season_one, real_content
from tianxia import bot, bot_policy, bounties, ranger, rules
from tianxia.characters import CharacterStore
from tianxia.engine import Game
from tianxia.models import FactionDef
from tianxia.state import Bounty, GameState, WorldState

NOW = 1000.0
WEEK = 10_000_000.0  # 測試裡的懸賞一律掛到很久以後


@pytest.fixture
def setup(content, world):
    install_season_one(content)
    content.config.auto_open_first_season = True
    content.config.newbie_days = -1  # 截殺不等新手期
    content.scenario.factions = [
        FactionDef(id="guan", name="官軍", join_at=["town"]),
        FactionDef(id="huang", name="黃巾", join_at=["lake"]),
    ]
    content.squads["thug"].faction = "huang"  # 湖邊的對手算黃巾：官軍的討伐打它
    for name, faction in (("甲", "guan"), ("乙", "huang"), ("丙", None)):
        game = Game.new(content, name, rng=random.Random(0), world=world)
        game.client = None
        rules.learn_skill(game.state, content, "fist")
        game.state.player.faction = faction
        game.state.player.location = "town"
        game.state.player.stamina = 100.0
        game.state.player.stats["silver"] = 200
        game.sync(NOW)
        CharacterStore(world.db).save(game.state)
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


def _load(world, name):
    return CharacterStore(world.db).load(name)


def _post(world, **kw) -> Bounty:
    """直接在榜上貼一張（每週的自動掛單另外測）。"""
    def add(season):
        season.bounty_seq += 1
        season.bounties.append(Bounty(id=f"b{season.bounty_seq}", week=1, expires=WEEK, **kw))

    world.mutate_season(add)
    return world.get_season().bounties[-1]


def _ids(content, world, name):
    return {o.id: o for o in _do(content, world, name, lambda g: g.options(odds=False))[0]}


def test_the_board_is_in_town_and_takes_a_bounty(setup):
    content, world = setup
    b = _post(world, kind="scout", faction="guan", silver=10, deeds=2, location="lake")
    assert "act:bounties" in _ids(content, world, "丙")
    _do(content, world, "丙", lambda g: g.choose("act:bounties"))
    menu = _ids(content, world, "丙")
    assert set(menu) == {f"bounty:take:{b.id}", "bounty:back"}
    assert "打探・湖邊" in menu[f"bounty:take:{b.id}"].label and "俠名 +2" in menu[f"bounty:take:{b.id}"].label
    msgs, _ = _do(content, world, "丙", lambda g: g.choose(f"bounty:take:{b.id}"))
    assert msgs[0].startswith("你揭下了")
    assert f"bounty:drop:{b.id}" in _ids(content, world, "丙")  # 揭了之後榜還開著，那一張換成放棄
    _do(content, world, "丙", lambda g: g.choose("bounty:back"))
    assert not _load(world, "丙").player.picking_bounty
    assert _do(content, world, "丙", lambda g: g.status_data())[0]["bounties"][0]["id"] == b.id


def test_no_board_outside_town_or_with_the_switch_off(setup):
    content_, world_ = setup
    state = _load(world_, "丙")
    state.player.location = "lake"
    CharacterStore(world_.db).save(state)
    assert "act:bounties" not in _ids(content_, world_, "丙")
    content_.config.season_one = False
    world_.mutate_season(lambda s: setattr(s, "season_one", False))
    state.player.location = "town"
    CharacterStore(world_.db).save(state)
    assert "act:bounties" not in _ids(content_, world_, "丙")


def test_scouting_pays_silver_exp_and_deeds_to_a_loner(setup):
    content, world = setup
    b = _post(world, kind="scout", faction="huang", silver=10, deeds=2, location="lake")
    _do(content, world, "丙", lambda g: bounties.take(g.state, g.content, b.id))
    before = _load(world, "丙").player

    def scout(g):
        g.state.player.location = "lake"
        return g.choose("act:explore")

    msgs, game = _do(content, world, "丙", scout)
    p = game.state.player
    assert any(m.startswith("【懸賞】") for m in msgs)
    assert p.bounties_done == 1 and p.ranger_deeds == 2
    assert p.stats["silver"] >= before.stats["silver"] + 10
    assert world.get_season().bounties[0].done_by == ["丙"]


def test_a_faction_member_only_sees_and_takes_his_own_side_at_half_pay(setup):
    content, world = setup
    ours = _post(world, kind="strike", faction="guan", silver=20, deeds=3, location="lake", squad="thug")
    theirs = _post(world, kind="strike", faction="huang", silver=20, deeds=3, location="lake", squad="thug")
    _do(content, world, "甲", lambda g: g.choose("act:bounties"))
    menu = _ids(content, world, "甲")
    assert f"bounty:take:{ours.id}" in menu and f"bounty:take:{theirs.id}" not in menu
    assert "俠名" not in menu[f"bounty:take:{ours.id}"].label  # 陣營的人名號凍結
    assert _do(content, world, "甲", lambda g: bounties.take(g.state, g.content, theirs.id))[0] == ["這一張不是給你接的。"]
    _do(content, world, "甲", lambda g: bounties.take(g.state, g.content, ours.id))
    msgs, game = _do(content, world, "甲", lambda g: bounties.on_win(g.state, g.content, g.world, "lake", "thug"))
    assert f"銀兩 +{round(20 * content.config.bounties.faction_share)}" in msgs
    assert game.state.player.ranger_deeds == 0


def test_strike_counts_any_enemy_squad_at_that_place(setup):
    content, world = setup
    b = _post(world, kind="strike", faction="guan", silver=20, deeds=3, location="lake", squad="thug")
    _do(content, world, "丙", lambda g: bounties.take(g.state, g.content, b.id))
    assert _do(content, world, "丙", lambda g: bounties.on_win(g.state, g.content, g.world, "town", "thug"))[0] == []
    content.squads["thug"].faction = "guan"  # 自己人：不算
    assert _do(content, world, "丙", lambda g: bounties.on_win(g.state, g.content, g.world, "lake", "thug"))[0] == []
    content.squads["thug"].faction = "huang"
    msgs, _ = _do(content, world, "丙", lambda g: bounties.on_win(g.state, g.content, g.world, "lake", "thug"))
    assert msgs[0].startswith("【懸賞】") and "俠名 +3" in msgs


def test_escort_is_taken_at_the_start_and_done_on_arrival(setup):
    content, world = setup
    b = _post(world, kind="escort", faction="guan", silver=15, deeds=2, location="lake", end="town")
    assert "要在湖邊接" in _do(content, world, "丙", lambda g: bounties.take(g.state, g.content, b.id))[0][0]

    def at_lake(g):
        g.state.player.location = "lake"
        return bounties.take(g.state, g.content, b.id)

    assert _do(content, world, "丙", at_lake)[0][0].startswith("你揭下了")
    msgs, _ = _do(content, world, "丙", lambda g: bounties.on_arrive(g.state, g.content, g.world, "town"))
    assert msgs and _load(world, "丙").player.bounties_done == 1


def test_at_most_max_taken_and_quota_runs_out(setup):
    content, world = setup
    content.config.bounties.max_taken = 1
    first = _post(world, kind="scout", faction="guan", silver=10, deeds=2, location="lake")
    second = _post(world, kind="scout", faction="huang", silver=10, deeds=2, location="cave")
    _do(content, world, "丙", lambda g: bounties.take(g.state, g.content, first.id))
    assert "先交了差" in _do(content, world, "丙", lambda g: bounties.take(g.state, g.content, second.id))[0][0]
    _, game = _do(content, world, "丙", lambda g: bounties.on_explore(g.state, g.content, g.world, "lake"))
    assert first.id not in {x.id for x in bounties.open_bounties(game.state, content)}  # 名額用完下榜


def test_tier_four_loners_get_the_silver_bonus(setup):
    content, world = setup
    b = _post(world, kind="scout", faction="guan", silver=20, deeds=2, location="lake")

    def strong(g):
        g.state.player.ranger_good = content.config.ranger.thresholds[-1]
        bounties.take(g.state, g.content, b.id)
        return bounties.on_explore(g.state, g.content, g.world, "lake")

    msgs, game = _do(content, world, "丙", strong)
    assert ranger.tier(game.state, content) == 4 and f"銀兩 +{round(20 * content.config.ranger.bounty_bonus)}" in msgs


def test_wanted_poster_hunter_and_the_raid(setup, monkeypatch):
    content, world = setup
    for name in ("甲", "乙", "丙"):
        state = _load(world, name)
        state.player.location = "lake"  # 湖畔不是城鎮類，截殺打得了
        CharacterStore(world.db).save(state)
    card = _do(content, world, "甲", lambda g: g.peer_card("乙"))[0]
    wanted = next(b for b in card["actions"] if b["action"] == "wanted")
    assert wanted["enabled"] and wanted["amount"] == 200
    assert not any(b["action"] == "wanted" for b in _do(content, world, "丙", lambda g: g.peer_card("乙"))[0]["actions"])
    msgs, _ = _do(content, world, "甲", lambda g: g.peer_act("乙", "wanted", {"amount": 50}))
    assert msgs[0].startswith("你押了 50 兩") and _load(world, "甲").player.stats["silver"] == 150
    b = world.get_season().bounties[-1]
    assert (b.kind, b.target, b.poster, b.silver) == ("wanted", "乙", "甲", 50)
    assert "已經掛著" in _do(content, world, "甲", lambda g: g.peer_act("乙", "wanted", {"amount": 50}))[0][0]
    # 散人揭了通緝：卡上多一顆截殺
    assert not any(x["action"] == "raid" for x in _do(content, world, "丙", lambda g: g.peer_card("乙"))[0]["actions"])
    _do(content, world, "丙", lambda g: bounties.take(g.state, g.content, b.id))
    assert any(x["action"] == "raid" for x in _do(content, world, "丙", lambda g: g.peer_card("乙"))[0]["actions"])
    monkeypatch.setattr(Game, "_spar_power", staticmethod(lambda who, against: 1000.0 if who.state.player.name == "丙" else 1.0))
    msgs, game = _do(content, world, "丙", lambda g: g.peer_act("乙", "raid"))
    p = game.state.player
    assert any(m.startswith("【懸賞】") for m in msgs) and p.bounties_done == 1
    assert p.contrib == 0 and not any("貢獻" in m for m in msgs)  # 散人不記貢獻
    assert p.ranger_deeds == content.config.bounties.deeds["wanted"]


def test_an_unclaimed_wanted_refunds_the_poster(setup):
    content, world = setup
    for name in ("甲", "乙"):
        state = _load(world, name)
        state.player.location = "lake"
        CharacterStore(world.db).save(state)
    _do(content, world, "甲", lambda g: g.peer_act("乙", "wanted", {"amount": 40}))
    world.mutate_season(lambda s: setattr(s.bounties[-1], "expires", 0.0))
    _, game = _do(content, world, "甲", lambda g: None)
    assert game.state.player.stats["silver"] == 200 and world.get_season().bounties[-1].refunded
    assert any(e.title.startswith(bounties.BOARD) for e in game.state.journal)
    _, game = _do(content, world, "甲", lambda g: None)
    assert game.state.player.stats["silver"] == 200  # 只退一次


def test_weekly_issue_on_the_real_map():
    content = real_content("weekend")
    state = GameState(player=Game.new(content, "測", rng=random.Random(0)).state.player, world=WorldState(season_one=True))
    again = state.model_copy(deep=True)
    bounties.issue(state, content, 1)
    board = state.world.bounties
    assert len(board) == 2 * len(content.config.bounties.kinds)
    for faction in ("guan", "huang"):
        strikes = [b for b in board if b.faction == faction and b.kind == "strike"]
        assert len({b.location for b in strikes}) == len(strikes)
        for b in strikes:
            assert content.squads[b.squad].faction == bounties.ENEMY[faction]
    for b in board:
        if b.kind == "escort":
            assert bounties.is_town(content, b.location) and bounties.is_town(content, b.end)
            assert b.end not in {str(x) for x in content.locations[b.location].connections}
    bounties.issue(again, content, 1, random.Random(99))
    assert [b.location for b in again.world.bounties] == [b.location for b in board]  # 不吃季的亂數：照週次與戰況一樣
    state.world.time = 3 * bounties.week_seconds(state, content)
    bounties.issue(state, content, 4)
    assert len(state.world.bounties) == len(board)  # 過期的下榜


def test_bots_skip_the_board_button_but_score_taking(setup):
    content, world = setup
    _post(world, kind="scout", faction="guan", silver=10, deeds=2, location="lake")
    game = _do(content, world, "丙", lambda g: g)[0]
    options = [o for o in game.options(odds=False) if o.enabled]
    assert any(o.id == "act:bounties" for o in options)
    assert all(o.id != "act:bounties" for o in options if bot.pick(game, [o], random.Random(0)) == o.id)
    assert bot_policy._takeable(game)
    bot.take_bounties(game)
    assert len(bounties.mine(game.state, content)) == 1 and not game.state.player.picking_bounty
