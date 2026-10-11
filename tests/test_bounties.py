"""懸賞榜（PM 2026-10-08 派工「加強散人玩法」）：陣營每週一自動掛討伐、打探、護送；投靠了陣營的人可以花銀兩通緝敵對陣營的人。
散人兩邊的都能接，陣營的人只能接自己陣營的；接了才算，前 quota 個完成的人有賞（散人另記俠名）。

角色開在同一個資料庫；每一個動作照伺服器的做法先從資料庫重讀自己，做完存回去（同 test_raid）。"""
from __future__ import annotations

import random

import pytest

from conftest import install_season_one, real_content
from tianxia import bot, bot_policy, bounties, calendar, ranger, rules
from tianxia.characters import CharacterStore
from tianxia.engine import Game
from tianxia.models import FactionDef
from tianxia.sqlite_world import open_world
from tianxia.state import Bounty, GameState, PlayerState, WorldState
from tianxia.world import advance_world_state, settle_season_start
from tianxia.world_state import fresh_season

NOW = 1000.0
WEEK = 10_000_000.0  # 測試裡的懸賞一律掛到很久以後
HOUR = 3600.0


def _seat(content, world, people):
    """開角色：都在城鎮（town）、會基礎拳腳、體力 100、銀兩 200，照伺服器的做法同步一次存進資料庫。"""
    content.config.auto_open_first_season = True
    content.config.newbie_days = -1  # 截殺不等新手期
    content.squads["thug"].faction = "huang"  # 湖邊的對手算黃巾：官軍的討伐打它
    for name, faction in people:
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


@pytest.fixture
def setup(content, world):
    """第一季（install_season_one）：官軍的甲、黃巾的乙、散人丙。"""
    install_season_one(content)
    content.scenario.factions = [
        FactionDef(id="guan", name="官軍", join_at=["town"]),
        FactionDef(id="huang", name="黃巾", join_at=["lake"]),
    ]
    return _seat(content, world, (("甲", "guan"), ("乙", "huang"), ("丙", None)))


@pytest.fixture
def beta_setup(content, world):
    """第一季規則關著的季（不叫 install_season_one，season_one 維持 False、季長照測試內容）：三個陣營（加地方豪強的丁），其餘同 setup
    （懸賞榜設計 10.1）。懸賞榜、名號、截殺、通緝每季都有。"""
    content.scenario.factions = [
        FactionDef(id="guan", name="官軍", join_at=["town"]),
        FactionDef(id="huang", name="黃巾", join_at=["lake"]),
        FactionDef(id="haoqiang", name="地方豪強", join_at=["cave"]),
    ]
    return _seat(content, world, (("甲", "guan"), ("乙", "huang"), ("丙", None), ("丁", "haoqiang")))


def _do(content, world, name, act):
    """照伺服器的 act 做一個動作：從資料庫重讀自己、同步、做、只存角色（server.act 不替動作存季）。動作改了共用賽季卻沒自己存的，
    改的那些在這裡就丟了——以前這裡每一步都補存季，蓋住了截殺交差沒存季（FB-119）。"""
    state = CharacterStore(world.db).load(name)
    game = Game(content, state, random.Random(0), world)
    game.client = None
    game.sync(NOW)
    msgs = act(game)
    CharacterStore(world.db).save(game.state)
    return msgs, game


def _direct(content, world, name, act):
    """直接呼叫 bounties 的函式（揭下、交差的掛鉤）：伺服器上它們都在某個動作裡跑、由那個動作存季；直接呼叫沒有動作替它存，
    這裡自己存（同 _do，只多存季）。"""
    def run(game):
        msgs = act(game)
        game._save_season()
        return msgs

    return _do(content, world, name, run)


def _load(world, name):
    return CharacterStore(world.db).load(name)


def _post(world, expires=WEEK, **kw) -> Bounty:
    """直接在榜上貼一張（每週的自動掛單另外測）。"""
    def add(season):
        season.bounty_seq += 1
        season.bounties.append(Bounty(id=f"b{season.bounty_seq}", week=1, expires=expires, **kw))

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


def test_no_board_outside_town(setup):
    content_, world_ = setup
    _post(world_, kind="scout", faction="guan", silver=10, deeds=2, location="lake")
    state = _load(world_, "丙")
    state.player.location = "lake"
    CharacterStore(world_.db).save(state)
    assert "act:bounties" not in _ids(content_, world_, "丙")


def test_the_board_stays_with_the_season_one_switch_off(beta_setup):
    """懸賞榜每季都有（企劃者 2026-10-10）：第一季規則關著的季照樣有榜、揭得下，散人交差照記俠名。"""
    content, world = beta_setup
    assert not content.config.season_one and not world.get_season().season_one
    b = _post(world, kind="scout", faction="guan", silver=10, deeds=2, location="lake")
    assert "act:bounties" in _ids(content, world, "丙")
    _do(content, world, "丙", lambda g: g.choose("act:bounties"))
    assert "俠名 +2" in _ids(content, world, "丙")[f"bounty:take:{b.id}"].label
    _do(content, world, "丙", lambda g: g.choose(f"bounty:take:{b.id}"))
    msgs, game = _direct(content, world, "丙", lambda g: bounties.on_explore(g.state, g.content, g.world, "lake"))
    assert msgs[0].startswith("【懸賞】") and game.state.player.ranger_deeds == 2


def test_no_board_when_switched_off_or_without_factions(setup):
    content, world = setup
    _post(world, kind="scout", faction="guan", silver=10, deeds=2, location="lake")
    assert "act:bounties" in _ids(content, world, "丙")
    content.config.bounties.enabled = False
    assert "act:bounties" not in _ids(content, world, "丙")
    content.config.bounties.enabled = True
    content.scenario.factions = []  # 劇本沒有陣營：沒有人掛單
    assert "act:bounties" not in _ids(content, world, "丙")


def test_scouting_pays_silver_exp_and_deeds_to_a_loner(setup):
    content, world = setup
    b = _post(world, kind="scout", faction="huang", silver=10, deeds=2, location="lake")
    _direct(content, world, "丙", lambda g: bounties.take(g.state, g.content, b.id))
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
    assert _direct(content, world, "甲", lambda g: bounties.take(g.state, g.content, theirs.id))[0] == ["這一張不是給你接的。"]
    _direct(content, world, "甲", lambda g: bounties.take(g.state, g.content, ours.id))
    msgs, game = _direct(content, world, "甲", lambda g: bounties.on_win(g.state, g.content, g.world, "lake", "thug"))
    assert f"銀兩 +{round(20 * content.config.bounties.faction_share)}" in msgs
    assert game.state.player.ranger_deeds == 0


def test_strike_counts_any_enemy_squad_at_that_place(setup):
    content, world = setup
    b = _post(world, kind="strike", faction="guan", silver=20, deeds=3, location="lake", squad="thug")
    _direct(content, world, "丙", lambda g: bounties.take(g.state, g.content, b.id))
    assert _direct(content, world, "丙", lambda g: bounties.on_win(g.state, g.content, g.world, "town", "thug"))[0] == []
    content.squads["thug"].faction = "guan"  # 自己人：不算
    assert _direct(content, world, "丙", lambda g: bounties.on_win(g.state, g.content, g.world, "lake", "thug"))[0] == []
    content.squads["thug"].faction = "huang"
    msgs, _ = _direct(content, world, "丙", lambda g: bounties.on_win(g.state, g.content, g.world, "lake", "thug"))
    assert msgs[0].startswith("【懸賞】") and "俠名 +3" in msgs


def test_escort_is_taken_at_the_start_and_done_on_arrival(setup):
    content, world = setup
    b = _post(world, kind="escort", faction="guan", silver=15, deeds=2, location="lake", end="town")
    assert "要在湖邊接" in _direct(content, world, "丙", lambda g: bounties.take(g.state, g.content, b.id))[0][0]

    def at_lake(g):
        g.state.player.location = "lake"
        return bounties.take(g.state, g.content, b.id)

    assert _direct(content, world, "丙", at_lake)[0][0].startswith("你揭下了")
    msgs, _ = _direct(content, world, "丙", lambda g: bounties.on_arrive(g.state, g.content, g.world, "town"))
    assert msgs and _load(world, "丙").player.bounties_done == 1


def test_at_most_max_taken_and_quota_runs_out(setup):
    content, world = setup
    content.config.bounties.max_taken = 1
    first = _post(world, kind="scout", faction="guan", silver=10, deeds=2, location="lake")
    second = _post(world, kind="scout", faction="huang", silver=10, deeds=2, location="cave")
    _direct(content, world, "丙", lambda g: bounties.take(g.state, g.content, first.id))
    assert "先交了差" in _direct(content, world, "丙", lambda g: bounties.take(g.state, g.content, second.id))[0][0]
    _, game = _direct(content, world, "丙", lambda g: bounties.on_explore(g.state, g.content, g.world, "lake"))
    assert first.id not in {x.id for x in bounties.open_bounties(game.state, content)}  # 名額用完下榜


def test_tier_four_loners_get_the_silver_bonus(setup):
    content, world = setup
    b = _post(world, kind="scout", faction="guan", silver=20, deeds=2, location="lake")

    def strong(g):
        g.state.player.ranger_good = content.config.ranger.thresholds[-1]
        bounties.take(g.state, g.content, b.id)
        return bounties.on_explore(g.state, g.content, g.world, "lake")

    msgs, game = _direct(content, world, "丙", strong)
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
    _direct(content, world, "丙", lambda g: bounties.take(g.state, g.content, b.id))
    assert any(x["action"] == "raid" for x in _do(content, world, "丙", lambda g: g.peer_card("乙"))[0]["actions"])
    monkeypatch.setattr(Game, "_spar_power", staticmethod(lambda who, against: 1000.0 if who.state.player.name == "丙" else 1.0))
    msgs, game = _do(content, world, "丙", lambda g: g.peer_act("乙", "raid"))
    p = game.state.player
    assert any(m.startswith("【懸賞】") for m in msgs) and p.bounties_done == 1
    assert p.contrib == 0 and not any("貢獻" in m for m in msgs)  # 散人不記貢獻
    assert p.ranger_deeds == content.config.bounties.deeds["wanted"]


def test_a_wanted_closed_by_a_raid_is_saved_to_the_season(setup, monkeypatch):
    """FB-119：截殺打贏交了通緝的差，要存回共用賽季（Game.raid 以前在打之前就存了季，交差改的 done_by／takers 沒再存，
    server.act 只存角色）。沒存的話同一張還在榜上、可以再揭再領，過期了押金還照退給掛單的人。"""
    content, world = setup
    for name in ("甲", "乙", "丙"):
        state = _load(world, name)
        state.player.location = "lake"
        CharacterStore(world.db).save(state)
    _do(content, world, "甲", lambda g: g.peer_act("乙", "wanted", {"amount": 50}))
    b = world.get_season().bounties[-1]
    _direct(content, world, "丙", lambda g: bounties.take(g.state, g.content, b.id))
    monkeypatch.setattr(Game, "_spar_power", staticmethod(lambda who, against: 1000.0 if who.state.player.name == "丙" else 1.0))
    msgs, _ = _do(content, world, "丙", lambda g: g.peer_act("乙", "raid"))
    assert any(m.startswith("【懸賞】") for m in msgs)
    saved = next(x for x in world.get_season().bounties if x.id == b.id)
    assert saved.done_by == ["丙"] and saved.takers == []
    _, again = _do(content, world, "丙", lambda g: g)
    assert not bounties.hunting(again.state, content, "乙")  # 卡上的截殺跟著收掉
    assert b.id not in {x.id for x in bounties.open_bounties(again.state, content)}  # 名額用完，下榜
    world.mutate_season(lambda s: setattr(next(x for x in s.bounties if x.id == b.id), "expires", 0.0))
    _, poster = _do(content, world, "甲", lambda g: None)
    assert poster.state.player.stats["silver"] == 150  # 有人交了差：押金不退
    assert not next(x for x in world.get_season().bounties if x.id == b.id).refunded


def test_a_wanted_runs_end_to_end_with_the_season_one_switch_off(beta_setup, monkeypatch):
    """通緝與截殺每季都有：押錢 → 揭下 → 卡上有截殺 → 打贏交差；散人記俠名、誰都不記貢獻（懸賞榜設計 10.2）。"""
    content, world = beta_setup
    for name in ("甲", "乙", "丙"):
        state = _load(world, name)
        state.player.location = "lake"  # 湖畔不是城鎮類，截殺打得了
        CharacterStore(world.db).save(state)
    msgs, _ = _do(content, world, "甲", lambda g: g.peer_act("乙", "wanted", {"amount": 50}))
    assert msgs[0].startswith("你押了 50 兩")
    b = world.get_season().bounties[-1]
    _direct(content, world, "丙", lambda g: bounties.take(g.state, g.content, b.id))
    assert any(x["action"] == "raid" for x in _do(content, world, "丙", lambda g: g.peer_card("乙"))[0]["actions"])
    monkeypatch.setattr(Game, "_spar_power", staticmethod(lambda who, against: 1.0 if who.state.player.name == "乙" else 1000.0))
    msgs, game = _do(content, world, "丙", lambda g: g.peer_act("乙", "raid"))
    p = game.state.player
    assert any(m.startswith("【懸賞】") for m in msgs) and p.bounties_done == 1
    assert p.ranger_deeds == content.config.bounties.deeds["wanted"] and p.contrib == 0
    world.mutate_season(lambda s: s.raided.clear())  # 乙剛被截殺過的保護時間：清掉，換甲截殺他
    msgs, game = _do(content, world, "甲", lambda g: g.peer_act("乙", "raid"))
    assert game.state.player.contrib == 0 and not any("貢獻" in m for m in msgs)  # 敵對陣營互截：規則關著的季不記貢獻


def test_with_raids_switched_off_a_wanted_is_not_an_undeliverable_bounty(setup):
    """Config.raid.enabled 關著時通緝一起收（懸賞榜設計 2.2 第 3 點）：卡上沒有通緝鈕、押不了；已經押的不在榜上、揭了的人手上不算它
    （不佔 max_taken）、假人不會為它打開榜；開關打開之後還沒到期的照常出現；過了期限押金照退。"""
    content, world = setup
    for name in ("甲", "乙"):
        state = _load(world, name)
        state.player.location = "lake"
        CharacterStore(world.db).save(state)
    _do(content, world, "甲", lambda g: g.peer_act("乙", "wanted", {"amount": 50}))
    b = world.get_season().bounties[-1]
    _direct(content, world, "丙", lambda g: bounties.take(g.state, g.content, b.id))
    content.config.raid.enabled = False
    card = _do(content, world, "乙", lambda g: g.peer_card("甲"))[0]
    assert not any(x["action"] in ("wanted", "raid") for x in card["actions"])  # 押不了、也截殺不了
    assert _do(content, world, "乙", lambda g: g.peer_act("甲", "wanted", {"amount": 50}))[0] == ["（此刻無法這麼做。）"]
    _, game = _do(content, world, "丙", lambda g: g)
    assert bounties.open_bounties(game.state, content) == [] and bounties.mine(game.state, content) == []
    assert not bounties.hunting(game.state, content, "乙") and not bot_policy._takeable(game)
    content.config.bounties.max_taken = 1
    scout = _post(world, kind="scout", faction="guan", silver=10, deeds=2, location="lake")
    assert _direct(content, world, "丙", lambda g: bounties.take(g.state, g.content, scout.id))[0][0].startswith("你揭下了")  # 不佔格
    content.config.raid.enabled = True
    _, game = _do(content, world, "丙", lambda g: g)
    assert b.id in {x.id for x in bounties.mine(game.state, content)}  # 開關打開：還沒到期的照常出現，揭的人手上照舊
    content.config.raid.enabled = False
    world.mutate_season(lambda s: setattr(next(x for x in s.bounties if x.id == b.id), "expires", 0.0))
    _, poster = _do(content, world, "甲", lambda g: None)
    assert poster.state.player.stats["silver"] == 200  # 過了期限押金照退


def test_no_wanted_on_a_newcomer(beta_setup):
    """通緝補一道新手期（企劃者 2026-10-10，懸賞榜設計 6.2、14.1 丁）：截殺不了還在新手期的人，押了錢也只能等退，所以先不讓押。
    新手期從他自己加入的那一刻算，規則關著的季也一樣。"""
    content, world = beta_setup
    content.config.newbie_days = 18
    newbie = content.config.newbie_days * 86400 / calendar.cal_scale(content, world.get_season())
    world.mutate_season(lambda season: setattr(season, "time", 2 * newbie))
    _seat(content, world, (("戊", "huang"),))
    content.config.newbie_days = 18  # _seat 把新手期關掉了，這裡要它
    [button] = [x for x in _do(content, world, "甲", lambda g: g.peer_card("戊"))[0]["actions"] if x["action"] == "wanted"]
    assert not button["enabled"] and "戊初入江湖" in button["note"]
    assert "新手期" in _do(content, world, "甲", lambda g: g.peer_act("戊", "wanted", {"amount": 50}))[0][0]
    assert _load(world, "甲").player.stats["silver"] == 200
    world.mutate_season(lambda season: setattr(season, "time", season.time + newbie + 60))
    [button] = [x for x in _do(content, world, "甲", lambda g: g.peer_card("戊"))[0]["actions"] if x["action"] == "wanted"]
    assert button["enabled"]


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


def _beta_season(content, **kw) -> WorldState:
    """第一季規則關著的季（預設設定 14 天、season_one 維持 False）照劇本種出的一份共用賽季（world_state.fresh_season，蓋了章），
    kw 蓋掉幾個欄位；直接拿 world.advance_world_state 推。"""
    season = fresh_season(content)
    for key, value in kw.items():
        setattr(season, key, value)
    return season


def test_a_beta_season_posts_one_batch_at_each_week_start():
    """第一季規則關著的季，季曆跨進新的一週就掛那一週的一批（懸賞榜設計 3.3）：一小時一步走三週多，每週剛好一批、
    bounty_week 跟著遞增，hooked_week 一直是 0（週初掛鉤只屬於第一季）。"""
    content = real_content()
    assert not content.config.season_one
    season = _beta_season(content)
    rng = random.Random(0)
    batches = []
    for _ in range(3 * 28 + 1):  # 14 天的季一週是現實 28 小時
        before = {b.id for b in season.bounties}
        advance_world_state(season, content, HOUR, rng)
        new = [b for b in season.bounties if b.id not in before]
        if new:
            batches.append((calendar.point(season.time, content, season).week, {b.week for b in new}, len(new)))
    assert [(week, weeks) for week, weeks, _ in batches] == [(1, {1}), (2, {2}), (3, {3}), (4, {4})]
    assert all(0 < n <= 2 * len(content.config.bounties.kinds) for *_, n in batches)
    assert season.bounty_week == 4 and season.hooked_week == 0
    assert {b.expires for b in season.bounties if b.week == 4} == {calendar.week_start(6, content, season)}


def test_going_live_mid_season_posts_only_this_week():
    """上線那一刻（懸賞榜設計 2.4 情形一）：季走到第 8 週（第 210 小時）、榜上一張都沒有，推進一步只掛第 8 週那一批（不補掛 1～7 週），
    期限錨在 week_start(10)＝第 252 小時（不是 210＋56）。"""
    content = real_content()
    season = _beta_season(content, time=210 * HOUR)
    advance_world_state(season, content, HOUR, random.Random(0))
    assert {b.week for b in season.bounties} == {8}
    assert 0 < len(season.bounties) <= 2 * len(content.config.bounties.kinds)
    assert {b.expires for b in season.bounties} == {calendar.week_start(10, content, season)} == {252 * HOUR}
    assert season.bounty_week == 8 and season.hooked_week == 0


def test_issue_skips_old_weeks_and_posts_a_week_once():
    """第一季那一條（WEEK_HOOKS）也走同一道擋：被補跑舊週時不掛；同一週叫兩次只掛一次（懸賞榜設計 3.2、3.4）。"""
    content = real_content("weekend")
    state = GameState(player=Game.new(content, "測", rng=random.Random(0)).state.player, world=WorldState(season_one=True))
    state.world.time = 3 * bounties.week_seconds(state, content)  # 第 4 週週一
    bounties.issue(state, content, 2)
    assert state.world.bounties == [] and state.world.bounty_week == 0
    bounties.issue(state, content, 4)
    board = list(state.world.bounties)
    bounties.issue(state, content, 4)
    assert board and state.world.bounties == board and state.world.bounty_week == 4
    assert {b.expires for b in board} == {calendar.week_start(6, content, state.world)}


def test_opening_a_beta_season_posts_week_one_and_leaves_hooked_week_alone():
    """規則關著的季開季那一刻（world.settle_season_start）掛第 1 週，不碰 hooked_week；再叫一次不重掛，收了季不掛（懸賞榜設計 3.3）。"""
    content = real_content()
    season = _beta_season(content)
    settle_season_start(season, content, random.Random(0))
    board = list(season.bounties)
    assert board and {b.week for b in board} == {1} and season.bounty_week == 1 and season.hooked_week == 0
    settle_season_start(season, content, random.Random(0))
    assert season.bounties == board
    ended = _beta_season(content, ended=True)
    assert settle_season_start(ended, content, random.Random(0)) == [] and ended.bounties == []


def _due(content, season, week):
    """第 week 週自動掛的單（期限 week_start(週次＋2)）給玩家看的期限。"""
    b = Bounty(id="b1", kind="scout", faction="guan", week=week, silver=10, deeds=2,
               expires=calendar.week_start(week + content.config.bounties.auto_weeks, content, season))
    return bounties.due_text(b, content, season)


def test_due_text_follows_the_season_and_says_season_end_past_the_last_day():
    """期限的寫法（懸賞榜設計 3.5）：規則關著寫「第N天 HH:MM」、第一季寫「第 N 週・週X HH:MM」；到季末或過了季末一律「到季末」——
    14 天的季第 11、12 週掛的單到期是第 336、364 小時，不寫這一季沒有的「第15天 00:00」「第16天 04:00」；週末設定一樣。"""
    beta = real_content()
    season = _beta_season(beta)
    assert [_due(beta, season, week) for week in (1, 10, 11, 12)] == ["第3天 08:00", "第13天 20:00", "到季末", "到季末"]
    weekend = real_content("weekend")
    season = fresh_season(weekend)
    assert season.season_one
    assert [_due(weekend, season, week) for week in (1, 10, 11, 12)] == ["第 3 週・週一 00:00", "第 12 週・週一 00:00", "到季末", "到季末"]


def test_board_lines_card_rows_and_the_take_reply_show_the_due_time_and_places_left(setup):
    """FB-121 第 5 件：懸賞榜每一行、懸賞卡每一列、揭下的回話都寫期限與名額（期限走 due_text；第一季寫季曆時刻）。"""
    content, world = setup
    due = calendar.week_start(3, content, world.get_season())
    b = _post(world, kind="scout", faction="guan", silver=10, deeds=2, location="lake", quota=3, expires=due)
    _do(content, world, "丙", lambda g: g.choose("act:bounties"))
    assert "（賞銀 10・經驗 10・俠名 +2；期限 第 3 週・週一 00:00・名額還剩 3）" in _ids(content, world, "丙")[f"bounty:take:{b.id}"].label
    msgs, _ = _do(content, world, "丙", lambda g: g.choose(f"bounty:take:{b.id}"))
    assert "期限 第 3 週・週一 00:00・名額還剩 3" in msgs[0]
    assert _do(content, world, "丙", lambda g: g.status_data())[0]["bounties"][0]["due"] == "期限 第 3 週・週一 00:00・名額還剩 3"


def test_a_bounty_filled_by_others_or_expired_says_so_once(setup):
    """FB-121 第 5 件：揭了的那一張被別人交滿名額、或過了期限，同步時補一句、拿掉名字（只補一次），不再默默消失。"""
    content, world = setup
    full = _post(world, kind="scout", faction="guan", silver=10, deeds=2, location="lake")  # 名額 1
    late = _post(world, kind="scout", faction="huang", silver=10, deeds=2, location="cave")
    for name in ("甲", "丙"):
        _direct(content, world, name, lambda g: bounties.take(g.state, g.content, full.id))
    _direct(content, world, "丙", lambda g: bounties.take(g.state, g.content, late.id))
    _direct(content, world, "甲", lambda g: bounties.on_explore(g.state, g.content, g.world, "lake"))  # 甲先交了：名額滿
    world.mutate_season(lambda s: setattr(next(x for x in s.bounties if x.id == late.id), "expires", 0.0))
    _, game = _do(content, world, "丙", lambda g: None)
    told = [line for e in game.state.journal if e.title == bounties.BOARD for line in e.lines]
    assert bounties.LAPSED_FULL.format(title=bounties.title(content, full)) in told
    assert bounties.LAPSED_DUE.format(title=bounties.title(content, late)) in told
    assert all("丙" not in b.takers for b in world.get_season().bounties)
    _, game = _do(content, world, "丙", lambda g: None)
    assert [line for e in game.state.journal if e.title == bounties.BOARD for line in e.lines] == told  # 只補一次


def test_issue_keeps_an_expired_bounty_until_its_takers_hear_of_it():
    """過了期限還有人揭著的單，掛新單時先留著（不在榜上、不能揭），等揭的人同步聽到那一句之後的下一次掛單才清掉。"""
    content = real_content("weekend")
    state = GameState(player=Game.new(content, "丙", rng=random.Random(0)).state.player, world=WorldState(season_one=True))
    bounties.issue(state, content, 1)
    held = state.world.bounties[0]
    held.takers = ["丙"]
    state.world.time = 3 * bounties.week_seconds(state, content)
    bounties.issue(state, content, 4)
    assert held.id in {b.id for b in state.world.bounties}
    assert held.id not in {b.id for b in bounties.open_bounties(state, content)}
    assert {b.week for b in state.world.bounties if b.id != held.id} == {4}  # 其他過期的照清
    assert bounties.deliver_lapses(state, content) == [bounties.LAPSED_DUE.format(title=bounties.title(content, held))]
    state.world.time = 4 * bounties.week_seconds(state, content)
    bounties.issue(state, content, 5)
    assert held.id not in {b.id for b in state.world.bounties}


@pytest.mark.slow
def test_a_whole_beta_season_posts_one_batch_a_week(tmp_path):
    """正式內容、預設設定（14 天、第一季規則關著）讓整季機器人玩一季（懸賞榜設計 10.2 的 slow）：12 週每週剛好一批
    （同一週的單在同一步一起出現），bounty_week 最後是 12、hooked_week 一直是 0。"""
    content = real_content()
    assert not content.config.season_one and content.config.bounties.enabled
    seen: dict[str, tuple[int, int]] = {}  # 懸賞 id → (第一次看到它的那一步, 它是第幾週掛的)
    step = [0]

    def observe(game):
        step[0] += 1
        for b in game.state.world.bounties:
            if b.kind != "wanted":
                seen.setdefault(b.id, (step[0], b.week))

    game = bot.play_season(content, 1, world=open_world(tmp_path / "season.db"), observe=observe)
    season = game.state.world
    batches: dict[int, set[int]] = {}
    for at, week in seen.values():
        batches.setdefault(week, set()).add(at)
    assert season.ended and sorted(batches) == list(range(1, 13))
    assert all(len(steps) == 1 for steps in batches.values())
    sizes = [sum(1 for _, w in seen.values() if w == week) for week in range(1, 13)]
    assert all(0 < n <= 2 * len(content.config.bounties.kinds) for n in sizes)
    assert season.bounty_week == 12 and season.hooked_week == 0


def test_the_board_count_only_counts_what_you_can_see(beta_setup):
    """FB-121 第 3 件：「懸賞榜（N 張）」只算看得到的——陣營的人不算別的陣營的、交過的不算、截殺關著時通緝不算；0 張不畫那顆鈕
    （豪強的人這一批還沒有自己的懸賞，不給一顆打開只有「返回」的鈕）。N 等於打開之後列出的張數。"""
    content, world = beta_setup
    _post(world, kind="scout", faction="guan", silver=10, deeds=2, location="lake")
    _post(world, kind="scout", faction="huang", silver=10, deeds=2, location="cave")
    done = _post(world, kind="strike", faction="guan", silver=20, deeds=3, location="lake", squad="thug", quota=3, done_by=["甲"])
    _post(world, kind="wanted", faction="guan", silver=50, deeds=4, poster="甲", target="乙")

    def button(name):
        return _ids(content, world, name).get("act:bounties")

    assert button("丙").label == "懸賞榜（4 張）"  # 散人：兩邊的都算，通緝也算
    assert button("甲").label == "懸賞榜（1 張）"  # 官軍：黃巾的、自己交過的、自己掛的通緝都不算
    assert button("丁") is None  # 豪強：沒有一張是給他的
    _do(content, world, "甲", lambda g: g.choose("act:bounties"))
    assert [o for o in _ids(content, world, "甲") if o != "bounty:back"] == [f"bounty:take:{b.id}" for b in world.get_season().bounties
                                                                         if b.kind == "scout" and b.faction == "guan"]
    assert f"bounty:take:{done.id}" not in _ids(content, world, "甲")
    content.config.raid.enabled = False
    assert button("丙").label == "懸賞榜（3 張）"  # 截殺關著：通緝不算張數


def test_no_seclusion_while_the_board_or_the_smith_is_open(beta_setup):
    """FB-121 第 4 件：懸賞榜開著時閉關，選單會卡在榜上（options 先回懸賞榜，排在閉關前面），所以擋下來；鐵匠鋪同一個洞一起補。"""
    content, world = beta_setup
    _post(world, kind="scout", faction="guan", silver=10, deeds=2, location="lake")
    _do(content, world, "丙", lambda g: g.choose("act:bounties"))
    msgs, game = _do(content, world, "丙", lambda g: g.seclude(2))
    assert msgs == ["你現在無法閉關。"] and game.state.player.busy_until is None
    _do(content, world, "丙", lambda g: g.choose("bounty:back"))
    content.config.weapons.enabled = True
    _do(content, world, "丙", lambda g: g.choose("act:smith"))
    msgs, game = _do(content, world, "丙", lambda g: g.seclude(2))
    assert msgs == ["你現在無法閉關。"] and game.state.player.busy_until is None
    _do(content, world, "丙", lambda g: g.choose("smith:back"))
    _, game = _do(content, world, "丙", lambda g: g.seclude(2))
    assert game.state.player.busy_until is not None  # 兩個都收起來就閉得了


def test_the_same_place_is_not_posted_twice_while_a_bounty_is_up(content):
    """FB-121 第 2 件：榜上還有效的同一種單已經用掉的地點不再掛（討伐同一個陣營不重複、打探不分陣營、護送不重複終點），
    一次遊歷或探索不會交兩張差。測試內容只有湖邊打得到黃巾、打探只有湖邊與山洞兩處：第 2 週沒地方可挑就跳過。"""
    content.scenario.factions = [
        FactionDef(id="guan", name="官軍", join_at=["town"]),
        FactionDef(id="huang", name="黃巾", join_at=["lake"]),
    ]
    content.squads["thug"].faction = "huang"
    state = GameState(player=PlayerState(name="測", location="town", stats={}, stamina=0), world=WorldState())
    for week in (1, 2):
        state.world.time = (week - 1) * bounties.week_seconds(state, content)
        bounties.issue(state, content, week)
    board = state.world.bounties
    assert [(b.faction, b.location) for b in board if b.kind == "strike"] == [("guan", "lake")]
    assert sorted(b.location for b in board if b.kind == "scout") == ["cave", "lake"]


def test_a_place_frees_up_once_its_bounty_is_past_due_or_filled(content):
    """同一地點不重複只看榜上還有效的單（issue 的 live：沒過期、名額沒滿）：第 1 週的兩張打探到第 2 週一張過了期限
    （還有人揭著，issue 照樣留在榜上等 deliver_lapses）、一張名額被交滿，湖邊與山洞就又能掛第 2 週的打探。"""
    content.scenario.factions = [
        FactionDef(id="guan", name="官軍", join_at=["town"]),
        FactionDef(id="huang", name="黃巾", join_at=["lake"]),
    ]
    content.squads["thug"].faction = "huang"
    state = GameState(player=PlayerState(name="測", location="town", stats={}, stamina=0), world=WorldState())
    w = state.world
    bounties.issue(state, content, 1)
    held, filled = [b for b in w.bounties if b.kind == "scout"]
    w.time = bounties.week_seconds(state, content)  # 第 2 週的週初
    held.expires, held.takers = w.time, ["甲"]  # 過了期限、還有人揭著
    filled.done_by = [f"交差{i}" for i in range(filled.quota)]  # 名額交滿了，期限還沒到
    bounties.issue(state, content, 2)
    assert held in w.bounties and filled in w.bounties  # 兩張都還在榜上，只是不算有效
    assert sorted(b.location for b in w.bounties if b.kind == "scout" and b.week == 2) == ["cave", "lake"]


def test_live_bounties_never_share_a_place_on_the_real_map():
    """FB-121 第 2 件（設計 7.2）照正式地圖、14 天的季一週一週掛完一季：每一週掛完，榜上還有效的打探不重複地點、
    護送不重複終點（都不分陣營），討伐同一個陣營不重複地點。測試內容只有一個城鎮、掛不出護送，所以用正式內容。"""
    content = real_content()
    state = GameState(player=PlayerState(name="測", location="town", stats={}, stamina=0), world=_beta_season(content))
    w = state.world
    for week in range(1, 13):
        w.time = calendar.week_start(week, content, w)
        bounties.issue(state, content, week)
        live = [b for b in w.bounties if b.expires > w.time]
        assert {b.week for b in live} == ({week} if week == 1 else {week - 1, week})  # 掛兩週：上一週的還在
        for kind, place in (("scout", lambda b: b.location), ("escort", lambda b: b.end),
                            ("strike", lambda b: (b.faction, b.location))):
            spots = [place(b) for b in live if b.kind == kind]
            assert len(spots) == len(set(spots)), (week, kind, spots)
    assert w.bounty_week == 12
    assert any(b.kind == "escort" for b in w.bounties) and any(b.kind == "scout" for b in w.bounties)  # 不是空轉


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
