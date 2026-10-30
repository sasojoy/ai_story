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
from tianxia.state import Bounty, BotProfile, GameState, PlayerState, WorldState
from tianxia.world import advance_world_state, season_end_time, settle_season_start
from tianxia.world_state import fresh_season
from conftest import real_content
from tianxia import bounties, calendar
from tianxia.state import Bounty
from tianxia.world_state import fresh_season, season_length_days, stamp_season

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


@pytest.mark.smoke
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
    monkeypatch.setattr(Game, "_spar_power", staticmethod(lambda who, against, seal=True: 1000.0 if who.state.player.name == "丙" else 1.0))
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
    monkeypatch.setattr(Game, "_spar_power", staticmethod(lambda who, against, seal=True: 1000.0 if who.state.player.name == "丙" else 1.0))
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
    monkeypatch.setattr(Game, "_spar_power", staticmethod(lambda who, against, seal=True: 1.0 if who.state.player.name == "乙" else 1000.0))
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


def test_a_board_emptied_while_open_says_so_above_back(setup):
    """榜開著的時候，看得到的單被別人交光，第二層不能只剩「返回」（FB-156；FB-121 第 3 件想避免的畫面換條路還是會出現）：
    「返回」上面多一行灰掉的 bounty:empty；它按不下去，整季機器人與假人不挑它；還有別的行時不畫；返回照舊收起榜。"""
    content, world = setup
    scout = _post(world, kind="scout", faction="guan", silver=10, deeds=2, location="lake")
    _do(content, world, "甲", lambda g: g.choose("act:bounties"))
    assert list(_ids(content, world, "甲")) == [f"bounty:take:{scout.id}", "bounty:back"]  # 還有單的時候不畫那一行
    _direct(content, world, "丙", lambda g: bounties.take(g.state, g.content, scout.id))
    _direct(content, world, "丙", lambda g: bounties.on_explore(g.state, g.content, g.world, "lake"))  # 丙交了差，名額 1 滿了
    menu = _ids(content, world, "甲")
    assert list(menu) == ["bounty:empty", "bounty:back"]
    assert not menu["bounty:empty"].enabled and menu["bounty:empty"].label == bounties.BOARD_EMPTY and menu["bounty:back"].enabled
    _, game = _do(content, world, "甲", lambda g: g)
    profile = BotProfile(personality="普通", seed=1, faction="guan", season_number=1)
    assert bot_policy.score(game, menu["bounty:empty"], profile) is None  # 假人：給不了分
    assert "bounty:empty" not in {o.id for o in game.options(odds=False) if o.enabled}  # 整季機器人、假人都只挑 enabled 的
    assert _do(content, world, "甲", lambda g: g.choose("bounty:empty"))[0] == ["（此刻無法這麼做。）"]  # 直接打 API 也沒作用，榜還開著
    assert _load(world, "甲").player.picking_bounty
    _do(content, world, "甲", lambda g: g.choose("bounty:back"))
    assert not _load(world, "甲").player.picking_bounty and "act:bounties" not in _ids(content, world, "甲")


def test_the_full_hands_refusal_states_how_many_you_really_hold(setup):
    """手上滿了的拒絕句寫手上真的有幾張（FB-155）：平常滿格就是上限（3 張），可是截殺開關關著時通緝不佔格、又揭滿 3 張，開回來通緝回到手上，
    手上有 4 張——每一行都寫「已經有 3 張」跟手上的張數對不上。"""
    content, world = setup
    cap = content.config.bounties.max_taken
    assert cap == 3
    for name in ("甲", "乙"):
        state = _load(world, name)
        state.player.location = "lake"
        CharacterStore(world.db).save(state)
    _do(content, world, "甲", lambda g: g.peer_act("乙", "wanted", {"amount": 50}))
    wanted = world.get_season().bounties[-1]
    _direct(content, world, "丙", lambda g: bounties.take(g.state, g.content, wanted.id))
    content.config.raid.enabled = False  # 通緝收起來：不佔格
    for _ in range(cap):
        scout = _post(world, kind="scout", faction="guan", silver=10, deeds=2, location="lake")
        assert _direct(content, world, "丙", lambda g: bounties.take(g.state, g.content, scout.id))[0][0].startswith("你揭下了")
    extra = _post(world, kind="scout", faction="guan", silver=10, deeds=2, location="lake")
    refusal = _direct(content, world, "丙", lambda g: bounties.take(g.state, g.content, extra.id))[0]
    assert refusal == [bounties.HELD_FULL.format(count=cap)] and "3 張" in refusal[0]  # 平常滿格：就是 3 張
    content.config.raid.enabled = True  # 開回來：通緝回到手上，4 張
    _do(content, world, "丙", lambda g: g.choose("act:bounties"))
    assert _direct(content, world, "丙", lambda g: len(bounties.mine(g.state, g.content)))[0] == cap + 1
    row = _ids(content, world, "丙")[f"bounty:take:{extra.id}"]
    assert not row.enabled and bounties.HELD_FULL.format(count=cap + 1) in row.label and "4 張" in row.label
    refusal = _direct(content, world, "丙", lambda g: bounties.take(g.state, g.content, extra.id))[0]
    assert refusal == [bounties.HELD_FULL.format(count=cap + 1)]


def test_a_newcomer_cannot_take_a_wanted_he_could_not_deliver(beta_setup):
    """揭的人自己還在截殺的新手期就揭不了通緝（FB-154）：通緝只能靠截殺交差，新手期的人截殺不了（Game.raid_refusal），揭了只是白佔一格到過期。
    榜上那一行灰掉、寫原因，bounties.take 也拒絕，整季機器人與假人不揭；別種單照揭；新手期從他自己加入那一刻算，規則關著的季一樣，過了就揭得下。"""
    content, world = beta_setup
    content.config.newbie_days = 18
    newbie = content.config.newbie_days * 86400 / calendar.cal_scale(content, world.get_season())
    world.mutate_season(lambda season: setattr(season, "time", 2 * newbie))
    _seat(content, world, (("戊", None),))  # 季初就在的甲乙丙丁早就過了新手期，戊是很晚才來的
    content.config.newbie_days = 18  # _seat 把新手期關掉了，這裡要它
    wanted = _post(world, kind="wanted", faction="guan", silver=50, deeds=3, poster="甲", target="乙")
    _do(content, world, "戊", lambda g: g.choose("act:bounties"))
    row = _ids(content, world, "戊")[f"bounty:take:{wanted.id}"]
    assert not row.enabled and bounties.WANTED_NEWBIE in row.label
    assert _direct(content, world, "戊", lambda g: bounties.take(g.state, g.content, wanted.id))[0] == [bounties.WANTED_NEWBIE]
    _, game = _do(content, world, "戊", lambda g: g)
    assert not bounties.mine(game.state, content) and not bot_policy._takeable(game)  # 假人：沒有揭得下的，不為它打開榜
    _direct(content, world, "戊", bot.take_bounties)
    assert world.get_season().bounties[0].takers == []  # 整季機器人：不揭
    scout = _post(world, kind="scout", faction="guan", silver=10, deeds=2, location="lake")
    assert _ids(content, world, "戊")[f"bounty:take:{scout.id}"].enabled  # 擋的只有通緝
    assert _direct(content, world, "戊", lambda g: bounties.take(g.state, g.content, scout.id))[0][0].startswith("你揭下了")
    world.mutate_season(lambda season: setattr(season, "time", season.time + newbie + 60))
    assert _ids(content, world, "戊")[f"bounty:take:{wanted.id}"].enabled
    assert _direct(content, world, "戊", lambda g: bounties.take(g.state, g.content, wanted.id))[0][0].startswith("你揭下了")
    assert world.get_season().bounties[0].takers == ["戊"]


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


def _batch(content) -> int:
    """一批幾張：官軍、黃巾各 kinds 裡的每一張，加上每個陣營各 give_kinds 裡的每一種（兵器開著才有求兵；正式內容 8＋3＝11 張，求藝 2026-10-21 拿掉）。"""
    cfg = content.config.bounties
    gives = [k for k in cfg.give_kinds if k != "arms" or content.config.weapons.enabled]
    return 2 * len(cfg.kinds) + len(content.scenario.factions) * len(gives)


def test_weekly_issue_on_the_real_map():
    content = real_content("week7")
    state = GameState(player=Game.new(content, "測", rng=random.Random(0)).state.player, world=WorldState(season_one=True))
    again = state.model_copy(deep=True)
    bounties.issue(state, content, 1)
    board = state.world.bounties
    assert len(board) == _batch(content) == 11
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
    assert all(0 < n <= _batch(content) for *_, n in batches)
    assert season.bounty_week == 4 and season.hooked_week == 0
    assert {b.expires for b in season.bounties if b.week == 4} == {calendar.week_start(6, content, season)}


def test_going_live_mid_season_posts_only_this_week():
    """上線那一刻（懸賞榜設計 2.4 情形一）：季走到第 8 週（第 210 小時）、榜上一張都沒有，推進一步只掛第 8 週那一批（不補掛 1～7 週），
    期限錨在 week_start(10)＝第 252 小時（不是 210＋56）。"""
    content = real_content()
    season = _beta_season(content, time=210 * HOUR)
    advance_world_state(season, content, HOUR, random.Random(0))
    assert {b.week for b in season.bounties} == {8}
    assert 0 < len(season.bounties) <= _batch(content)
    assert {b.expires for b in season.bounties} == {calendar.week_start(10, content, season)} == {252 * HOUR}
    assert season.bounty_week == 8 and season.hooked_week == 0


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
    """期限的寫法（懸賞榜設計 3.5）：規則關著寫「第N天 HH:MM」；到季末或過了季末一律「到季末」——
    14 天的季第 11、12 週掛的單到期是第 336、364 小時，不寫這一季沒有的「第15天 00:00」「第16天 04:00」。
    （第一季週曆的「第 N 週・週X HH:MM」只有封存的週末季用；21 天、7 天季的寫法見 tests/test_season21_daily.py。）"""
    beta = real_content()
    season = _beta_season(beta)
    assert [_due(beta, season, week) for week in (1, 10, 11, 12)] == ["第3天 08:00", "第13天 20:00", "到季末", "到季末"]


def _short(content, season, expires, done=()):
    b = Bounty(id="b1", kind="scout", faction="guan", week=1, silver=10, deeds=2, quota=3, done_by=list(done), expires=expires)
    return bounties.due_short(b, content, season)


def test_the_notice_gets_a_short_due_line_that_cannot_wrap_fb196():
    """FB-196：店面的告示寫短的（草圖「期限 第 6 週・剩 2」）——第一季寫週次、規則關著只寫第幾天，名額寫「剩 N」，
    到季末寫「到季末・剩 N」；完整的時刻與「名額還剩 N」（due_line）留在點開的紙上。自動掛的單都在第 N 週週一 00:00 到期，
    第 N 週一開始就過了：寫最後還有效的那一週「到第 N−1 週」（PM 2026-10-14，不然玩家讀成「做到第 N 週為止」白跑一趟）。"""
    def auto(content, season, week):
        return calendar.week_start(week + content.config.bounties.auto_weeks, content, season)

    beta = real_content()
    season = _beta_season(beta)
    assert [_short(beta, season, auto(beta, season, week)) for week in (1, 10, 11)] == ["期限 第3天・剩 3", "期限 第13天・剩 3", "到季末・剩 3"]
    assert _short(beta, season, auto(beta, season, 1), done=("甲", "乙")) == "期限 第3天・剩 1"


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
    content = real_content()
    state = GameState(player=Game.new(content, "丙", rng=random.Random(0)).state.player, world=WorldState())
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
    """正式內容、預設設定（14 天、第一季規則關著）讓整季機器人玩一季（懸賞榜設計 10.2 的 slow）：一直到收季那一週，每週剛好一批
    （同一週的單在同一步一起出現），bounty_week 最後是收季那一週、hooked_week 一直是 0。大勢門檻可能讓季提早收
    （黃巾稱霸，最早第 decisive_from_week 週；FB-184 多了官軍大營之後，種子 1 這一季在第 11 週收），所以不寫死 12 週。
    門檻在第 decisive_from_week 週以前就到了的季，一到那一週的週一 00:00 就收：那一週一刻都沒跑、掛不出那一週的單，
    最後一批是前一週（意境提示改了內容之後種子 1 就是這樣：第 10 週週一 00:00 收、最後一批第 9 週）。"""
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
    last = max(batches)
    assert season.ended and sorted(batches) == list(range(1, last + 1))
    end = calendar.point(season.time, content, season).week  # 收季那一週
    ran = end - 1 if season.time == calendar.week_start(end, content, season) else end  # 正好在週一 00:00 收：那一週沒跑
    assert content.config.decisive_from_week <= end <= content.config.season_weeks and last == ran
    assert all(len(steps) == 1 for steps in batches.values())
    sizes = [sum(1 for _, w in seen.values() if w == week) for week in range(1, last + 1)]
    assert all(0 < n <= _batch(content) for n in sizes)
    assert season.bounty_week == last and season.hooked_week == 0


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
    state.world.flags.add("cave_open")  # 測試內容的山洞要 cave_open 才開放：週初掛單只挑已開放的地點（FB-150）
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
    w.flags.add("cave_open")  # 測試內容的山洞要 cave_open 才開放：週初掛單只挑已開放的地點（FB-150）
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


def _post_seasons(content, flags=(), seeds=range(5)) -> tuple[int, list[Bounty]]:
    """用同一份內容連掛幾季（規則關著的季，一季 12 週一週一批）：每一季是一份全新的賽季，蓋掉 trends（週初掛單的亂數種子含此刻的戰況，
    五種戰況就是五套不同的抽法）、旗標只放 flags，一週一週把時間推到週初、掛單。回傳（掛了幾批，掛過的每一張單，含已下榜的）。"""
    posted: list[Bounty] = []
    batches = 0
    for seed in seeds:
        season = _beta_season(content, trends={"huangjin": 20 + 10 * seed, "yuxi": 0}, flags=set(flags))
        state = GameState(player=PlayerState(name="測", location="town", stats={}, stamina=0), world=season)
        for week in range(1, 13):
            season.time = calendar.week_start(week, content, season)
            before = {b.id for b in season.bounties}
            bounties.issue(state, content, week)
            new = [b for b in season.bounties if b.id not in before]
            batches += bool(new)
            posted += new
    return batches, posted


def test_weekly_posting_only_picks_places_that_are_open_fb150():
    """FB-150：週初掛單只挑已開放的地點。正式內容的南華觀（jade_cave，打探的候選）要等世界旗標 xi_open 立起來才開放，
    以前沒立旗標就照掛，揭的人「無法安排前往這裡」、那張單白占 56 小時。用正式內容、14 天的季（規則關著）掛 5 季 ×12 週＝60 批
    （每季換一套 trends 抽不同的地點）：沒立 xi_open 時南華觀不出現在任何一張單（打探地點、討伐地點、護送起訖）；立了之後
    同樣的 60 批裡南華觀至少當過一次打探地點。草廬（mentor_hut，序章專屬）照建構就挑不到：危險度 1、不是城鎮、沒有敵人。"""
    content = real_content()
    assert content.locations["jade_cave"].unlock_flag == "xi_open" and content.locations["jade_cave"].danger >= 2
    hut = content.locations["mentor_hut"]
    assert hut.prologue_only and hut.danger < 2 and not bounties.is_town(content, "mentor_hut") and not hut.enemies

    def places(posted):
        return {p for b in posted for p in (b.location, b.end) if p}

    batches, shut = _post_seasons(content)
    assert batches >= 50 and any(b.kind == "scout" for b in shut)  # 不是空轉
    assert "jade_cave" not in places(shut) and "mentor_hut" not in places(shut)

    batches, opened = _post_seasons(content, flags={"xi_open"})
    assert batches >= 50
    assert any(b.kind == "scout" and b.location == "jade_cave" for b in opened)  # 旗標立起來就照常挑得到
    assert "mentor_hut" not in places(opened)


def test_strike_escort_and_scout_all_skip_a_closed_place_fb150():
    """FB-150 的另外兩種單：正式內容裡唯一沒開放的南華觀不是城鎮、也沒有敵人，只擋得到打探，所以討伐與護送的過濾在這裡人工關：
    先掛 5 季看每一種單最常挑的地點（討伐地點、護送起點與終點、打探地點），把它們各加上一個沒立的 unlock_flag 再掛一次：
    被關的地點在對應的欄位上一張都沒有、每一種單照樣掛得出來；旗標立起來之後掛出來的單跟當初一模一樣（開放的地點抽法不位移）。"""
    from collections import Counter

    content = real_content()
    _, base = _post_seasons(content)

    def common(kind, field):
        return Counter(getattr(b, field) for b in base if b.kind == kind).most_common(1)[0][0]

    closed = {
        "strike": ("location", common("strike", "location")),
        "scout": ("location", common("scout", "location")),
        "escort-start": ("location", common("escort", "location")),
        "escort-end": ("end", common("escort", "end")),
    }
    for _, spot in closed.values():
        content.locations[spot].unlock_flag = "shut_by_test"
    _, shut = _post_seasons(content)
    for kind, (field, spot) in closed.items():
        base_kind = kind.split("-")[0]
        assert not any(getattr(b, field) == spot for b in shut if b.kind == base_kind), (kind, spot)
    assert {b.kind for b in shut if b.kind not in bounties.GIVE_KINDS} == set(content.config.bounties.kinds)  # 求兵不掛地點，另算

    _, reopened = _post_seasons(content, flags={"shut_by_test"})
    assert [(b.kind, b.faction, b.location, b.end) for b in reopened] == [(b.kind, b.faction, b.location, b.end) for b in base]


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


# ── FB-151：換陣營時手上接不了的懸賞要說一聲 ──────────────────────────────


@pytest.fixture(params=["setup", "beta_setup"])
def either(request):
    """第一季的季、規則關著的季各跑一次（FB-151 的投靠與叛投兩邊都一樣）。"""
    return request.getfixturevalue(request.param)


def _told(game):
    """江湖紀錄裡所有的「【懸賞】」行（懸賞榜標題的、或併進別的標題的都算）。"""
    return [line for e in game.state.journal for line in e.lines if line.startswith("【懸賞】")]


def _hold(content, world, name, *bounty_ids):
    for bid in bounty_ids:
        _direct(content, world, name, lambda g, bid=bid: bounties.take(g.state, g.content, bid))


def _takers(world, bounty):
    return next(b for b in world.get_season().bounties if b.id == bounty.id).takers


def test_joining_a_faction_drops_the_other_sides_held_bounties_and_says_so_fb151(either):
    """FB-151：散人丙揭了兩張黃巾的討伐，投靠官軍：確認畫面先講手上幾張會作廢；確定之後名字從兩張單的 takers 拿掉（存進共用的季）、
    回話與江湖紀錄各補一句原因（不是之後才補的「過了期限」），懸賞卡空了，之後再同步也不再提。"""
    content, world = either
    first = _post(world, kind="strike", faction="huang", silver=10, deeds=2, location="lake")
    second = _post(world, kind="strike", faction="huang", silver=10, deeds=2, location="cave")
    _hold(content, world, "丙", first.id, second.id)
    assert len(_do(content, world, "丙", lambda g: g.status_data())[0]["bounties"]) == 2
    msgs, _ = _do(content, world, "丙", lambda g: g.choose("faction:guan"))
    assert bounties.STRANDED_JOIN.format(n=2) in msgs[0] and msgs[0].endswith("確定投靠官軍？")
    msgs, game = _do(content, world, "丙", lambda g: g.choose("faction:confirm"))
    lines = [bounties.LAPSED_SIDE.format(faction="官軍", title=bounties.title(content, b)) for b in (first, second)]
    assert msgs[0] == "你投靠了官軍。" and [m for m in msgs if m in lines] == lines
    assert _told(game) == lines  # 紀錄各一句，順序同手上的
    assert "丙" not in _takers(world, first) and "丙" not in _takers(world, second)
    assert _do(content, world, "丙", lambda g: g.status_data())[0]["bounties"] == []
    _, game = _do(content, world, "丙", lambda g: None)
    assert _told(game) == lines  # 之後同步不再提
    world.mutate_season(lambda s: [setattr(b, "expires", 0.0) for b in s.bounties])  # 過了期限也沒有第二句
    _, game = _do(content, world, "丙", lambda g: None)
    assert _told(game) == lines


def test_joining_keeps_what_the_new_side_can_still_take_and_says_nothing_when_nothing_is_lost_fb151(either):
    """只拿掉新陣營接不了的：丙揭了一張官軍的、一張黃巾的，投靠官軍只丟黃巾那一張（確認畫面寫 1 張）；手上沒有這種單時，確認畫面跟以前一個字不差。"""
    content, world = either
    nothing = _do(content, world, "丙", lambda g: g.choose("faction:guan"))[0][0]  # 手上沒有單：確認畫面沒有多一句
    assert "懸賞" not in nothing and nothing.startswith("投靠後這一季不能改投（叛投另論）。目前")
    _do(content, world, "丙", lambda g: g.choose("faction:cancel"))
    ours = _post(world, kind="scout", faction="guan", silver=10, deeds=2, location="lake")
    theirs = _post(world, kind="scout", faction="huang", silver=10, deeds=2, location="cave")
    _hold(content, world, "丙", ours.id, theirs.id)
    msgs, _ = _do(content, world, "丙", lambda g: g.choose("faction:guan"))
    assert bounties.STRANDED_JOIN.format(n=1) in msgs[0]
    msgs, game = _do(content, world, "丙", lambda g: g.choose("faction:confirm"))
    assert bounties.LAPSED_SIDE.format(faction="官軍", title=bounties.title(content, theirs)) in msgs
    assert not any(bounties.title(content, ours) in m for m in msgs if m.startswith("【懸賞】"))
    assert "丙" in _takers(world, ours) and "丙" not in _takers(world, theirs)
    assert [b.id for b in bounties.mine(game.state, content)] == [ours.id]


def test_defecting_drops_the_old_sides_held_bounties_and_the_prompt_lists_them_fb151(either):
    """FB-151：官軍甲揭了兩張官軍的單，到黃巾的投靠點叛投：確認畫面把「手上 2 張…作廢」列進損失（這是唯一的損失，所以不再說
    「沒有什麼進度要作廢」）；確定之後兩張單拿掉他的名字、回話與紀錄各補一句；沒揭單的人，確認畫面照舊。"""
    content, world = either
    first = _post(world, kind="strike", faction="guan", silver=10, deeds=2, location="lake")
    second = _post(world, kind="scout", faction="guan", silver=10, deeds=2, location="cave")
    _hold(content, world, "甲", first.id, second.id)
    state = _load(world, "甲")
    state.player.location = "lake"
    CharacterStore(world.db).save(state)
    plain = _do(content, world, "乙", lambda g: g.choose("defect:guan"))[0][0]  # 乙是黃巾的人，手上沒有單，在城鎮有官軍的投靠點
    assert plain.startswith("叛投官軍沒有什麼進度要作廢") and "懸賞" not in plain
    _do(content, world, "乙", lambda g: g.choose("defect:cancel"))
    msgs, _ = _do(content, world, "甲", lambda g: g.choose("defect:huang"))
    assert bounties.STRANDED_LOST.format(n=2, faction="官軍") in msgs[0] and "沒有什麼進度要作廢" not in msgs[0]
    assert msgs[0].startswith("叛投黃巾之後，") and msgs[0].endswith("確定叛投黃巾？")
    msgs, game = _do(content, world, "甲", lambda g: g.choose("defect:confirm"))
    lines = [bounties.LAPSED_SIDE.format(faction="黃巾", title=bounties.title(content, b)) for b in (first, second)]
    assert game.state.player.faction == "huang" and "你叛出官軍，投了黃巾。" in msgs
    assert [m for m in msgs if m in lines] == lines and _told(game) == lines
    assert "甲" not in _takers(world, first) and "甲" not in _takers(world, second)
    assert _do(content, world, "甲", lambda g: g.status_data())[0]["bounties"] == []
    _, game = _do(content, world, "甲", lambda g: None)
    assert _told(game) == lines


def test_a_holder_who_can_no_longer_take_a_bounty_hears_the_faction_reason_once_fb151(beta_setup):
    """換版之前就換了陣營的存檔（名字還留在接不了的單上）：同步時拿掉名字、說陣營的原因一次，不說「過了期限」「名額被別人交滿了」；
    單子已經過期或名額滿了，也是這一句（人是先接不了的）。"""
    content, world = beta_setup
    live = _post(world, kind="scout", faction="huang", silver=10, deeds=2, location="lake")
    late = _post(world, kind="strike", faction="huang", silver=10, deeds=2, location="cave", expires=0.0)
    full = _post(world, kind="scout", faction="huang", silver=10, deeds=2, location="cave", done_by=["乙"])
    ours = _post(world, kind="scout", faction="guan", silver=10, deeds=2, location="lake")

    def stale(season):
        for b in season.bounties:
            if b.id in (live.id, late.id, full.id, ours.id):
                b.takers.append("甲")  # 甲是官軍：黃巾的三張他早就接不了了

    world.mutate_season(stale)
    _, game = _do(content, world, "甲", lambda g: None)
    told = _told(game)
    lines = [bounties.LAPSED_SIDE.format(faction="官軍", title=bounties.title(content, b)) for b in (live, late, full)]
    assert sorted(told) == sorted(lines)
    assert not any(bounties.LAPSED_DUE.format(title=bounties.title(content, b)) in told for b in (live, late))
    assert bounties.LAPSED_FULL.format(title=bounties.title(content, full)) not in told
    assert all("甲" not in _takers(world, b) for b in (live, late, full)) and "甲" in _takers(world, ours)  # 自己陣營的不動
    _, game = _do(content, world, "甲", lambda g: None)
    assert sorted(_told(game)) == sorted(lines)  # 只補一次


def test_joining_a_sect_through_an_event_choice_drops_them_too_fb151(beta_setup):
    """拜入陣營名下的門派（事件的選項，走 choose）也是投靠：散人丙手上的黃巾單同一下拿掉，回話與紀錄各一句。"""
    from tianxia.models import Choice, Effect, Event

    content, world = beta_setup
    content.scenario.factions[0].sects = ["cloud"]  # 門派歸官軍
    theirs = _post(world, kind="scout", faction="huang", silver=10, deeds=2, location="cave")
    _hold(content, world, "丙", theirs.id)
    event = Event(
        id="t_join_sect", title="結社", text="有人問你要不要入夥。", actions=[],
        choices=[Choice(text="入夥", effect=Effect(join_sect="cloud"))],
    )
    content.events[event.id] = event

    def join(game):
        game._present(event)
        return game.choose("choice:0")

    msgs, game = _do(content, world, "丙", join)
    line = bounties.LAPSED_SIDE.format(faction="官軍", title=bounties.title(content, theirs))
    assert game.state.player.faction == "guan" and "你從此是官軍的人了。" in msgs and line in msgs
    assert _told(game) == [line] and "丙" not in _takers(world, theirs)
    assert _do(content, world, "丙", lambda g: g.status_data())[0]["bounties"] == []


def _sect_event(content):
    """入夥（歸官軍的門派 cloud）與婉拒兩個選項的事件；門派歸官軍。"""
    from tianxia.models import Choice, Effect, Event

    content.scenario.factions[0].sects = ["cloud"]
    event = Event(
        id="t_join_sect_note", title="結社", text="有人問你要不要入夥。", actions=[],
        choices=[Choice(text="入夥", effect=Effect(join_sect="cloud")), Choice(text="婉拒")],
    )
    content.events[event.id] = event
    return event


def _labels(content, world, name, event):
    def menu(game):
        game._present(event)
        return {o.id: o.label for o in game.options(odds=False)}

    return _do(content, world, name, menu)[0]


def test_an_event_choice_that_joins_a_sect_warns_about_the_bounties_it_will_void_fb159(beta_setup):
    """FB-159：選項會拜入陣營名下的門派（Effect.join_sect → 那個門派歸哪個陣營），而手上有那個陣營接不了的單時，選項那一行
    跟投靠的確認畫面一樣先講幾張會作廢（STRANDED_JOIN，照 bounties.stranded 數）；沒有單、單都是新陣營的、已經有陣營的人，一個字不多。
    婉拒那種不拜入的選項不受影響；選下去真的作廢的就是那幾張。"""
    content, world = beta_setup
    event = _sect_event(content)
    assert _labels(content, world, "丙", event) == {"choice:0": "入夥", "choice:1": "婉拒"}  # 手上沒有單
    ours = _post(world, kind="scout", faction="guan", silver=10, deeds=2, location="lake")
    _hold(content, world, "丙", ours.id)
    assert _labels(content, world, "丙", event)["choice:0"] == "入夥"  # 官軍的單，拜入官軍的門派不丟
    theirs = _post(world, kind="strike", faction="huang", silver=10, deeds=2, location="lake")
    other = _post(world, kind="scout", faction="huang", silver=10, deeds=2, location="cave")
    _hold(content, world, "丙", theirs.id, other.id)
    labels = _labels(content, world, "丙", event)
    assert labels["choice:0"] == "入夥（" + bounties.STRANDED_JOIN.format(n=2) + "）" and labels["choice:1"] == "婉拒"
    assert _labels(content, world, "甲", event)["choice:0"] == "入夥"  # 甲已經是官軍：拜入不換陣營，什麼都不丟
    msgs, game = _do(content, world, "丙", lambda g: (g._present(event), g.choose("choice:0"))[1])
    lapsed = {bounties.LAPSED_SIDE.format(faction="官軍", title=bounties.title(content, b)) for b in (theirs, other)}
    assert lapsed <= set(msgs)  # 警告說的兩張，選下去就是這兩張作廢
    assert [b.id for b in bounties.mine(game.state, content)] == [ours.id]


def test_the_sect_warning_follows_the_sect_owner_in_the_real_content():
    """正式內容：潁川書院的「投身書院」歸官軍、曹氏莊院的「接招」歸地方豪強；選項標籤的警告看的是門派的主人（Scenario.sect_owner），不是寫死的陣營名。"""
    content = real_content()
    owners = {}
    for event in content.events.values():
        for choice in event.choices:
            for effect in (choice.effect, choice.fail_effect):
                if effect.join_sect:
                    owners[event.id] = content.scenario.sect_owner(effect.join_sect).id
    assert owners == {"yingchuan_join": "guan", "cao_manor_join": "haoqiang"}


def test_a_faction_set_by_a_bare_effect_is_caught_at_the_next_sync_with_the_faction_reason_fb151(beta_setup):
    """入口不經過 choose 的（直接套 Effect(join_sect=…)）：效果本身不碰懸賞榜，下一次同步由 deliver_lapses 補，說的是陣營的原因、不是過期。"""
    from tianxia.models import Effect

    content, world = beta_setup
    content.scenario.factions[0].sects = ["cloud"]
    theirs = _post(world, kind="scout", faction="huang", silver=10, deeds=2, location="cave")
    _hold(content, world, "丙", theirs.id)

    def join(game):
        rules.apply_effect(Effect(join_sect="cloud"), game.state, game.content, game.world)

    _, game = _do(content, world, "丙", join)
    assert game.state.player.faction == "guan" and "丙" in _takers(world, theirs)  # 效果本身沒碰
    _, game = _do(content, world, "丙", lambda g: None)
    line = bounties.LAPSED_SIDE.format(faction="官軍", title=bounties.title(content, theirs))
    assert _told(game) == [line] and "丙" not in _takers(world, theirs)
    _, game = _do(content, world, "丙", lambda g: None)
    assert _told(game) == [line]


def test_stranded_asks_the_same_question_as_can_take_fb151(beta_setup):
    """stranded(state, content, 陣營) ＝ 手上揭著、還有效、那個陣營的人接不了（同 can_take）的單；已過期的不算（它另有一句）；
    散人（陣營 None）什麼都接得了，所以沒有。"""
    content, world = beta_setup
    huang = _post(world, kind="scout", faction="huang", silver=10, deeds=2, location="lake")
    guan = _post(world, kind="scout", faction="guan", silver=10, deeds=2, location="lake")
    old = _post(world, kind="scout", faction="huang", silver=10, deeds=2, location="cave", expires=0.0)
    _hold(content, world, "丙", huang.id, guan.id)

    def mark_old(season):
        next(b for b in season.bounties if b.id == old.id).takers.append("丙")

    world.mutate_season(mark_old)
    _, game = _do(content, world, "丙", lambda g: g)
    ids = lambda faction: sorted(b.id for b in bounties.stranded(game.state, content, faction))  # noqa: E731
    assert ids("guan") == [huang.id] and ids("huang") == [guan.id] and ids(None) == []
    game.state.player.faction = "guan"
    assert bounties.mine(game.state, content) == [next(b for b in game.state.world.bounties if b.id == guan.id)]


# ── FB-152、FB-153：寫「到季末」的單撐到季真的收了 ──────────────────────────────


def _sync_at(content, world, name, now):
    """照伺服器的做法從資料庫重讀自己、在現實時間 now 同步、存回（_do 的時間固定在 NOW；這裡要讓共用的季往前走）。
    time_scale 是 1，現實過幾秒世界就過幾秒；走過季末就真的收季（catch_up_season → end_season），不是測試自己把 ended 設成真。"""
    state = CharacterStore(world.db).load(name)
    game = Game(content, state, random.Random(0), world)
    game.client = None
    game.sync(now)
    CharacterStore(world.db).save(game.state)
    return game


def _advance_to(world, content, hours):
    """共用的季推到第 hours 小時（走 advance_world_state，跟被動追趕同一個函式；不開決戰、不碰任何人的角色）。"""
    world.mutate_season(lambda s: advance_world_state(s, content, hours * HOUR - s.time, random.Random(0), world))
    return world.get_season()


def test_a_season_end_bounty_lasts_until_the_season_closes_then_every_held_bounty_lapses_alike_fb152(either):
    """FB-152：第 11 週掛的單到期正好是季末、第 12 週掛的在季末後一週，都寫「到季末」。季還在跑時兩張都好好地在卡上；
    季真的收了（走追趕到季末收季）之後，兩張在揭的人下次同步時補同一句「這一季收了」（不是一張「過了期限」、一張還掛著），
    名字拿掉、卡空了、榜不開，之後再同步不重複。"""
    content, world = either
    season = world.get_season()
    eleven = _post(world, kind="scout", faction="huang", silver=10, deeds=2, location="lake", expires=calendar.week_start(13, content, season))
    twelve = _post(world, kind="scout", faction="huang", silver=10, deeds=2, location="cave", expires=calendar.week_start(14, content, season))
    arms = _post(world, kind="arms", faction="guan", silver=0, deeds=2, quota=3, attribute="柔", weapon_kind="劍",
                 expires=calendar.week_start(14, content, season))
    _hold(content, world, "丙", eleven.id, twelve.id)  # 求兵不用揭
    assert [bounties.due_text(b, content, season) for b in (eleven, twelve)] == [bounties.SEASON_END] * 2
    game = _sync_at(content, world, "丙", NOW + 30 * HOUR)  # 季還在跑
    assert not world.get_season().ended and _told(game) == []
    assert [b.id for b in bounties.mine(game.state, content)] == [eleven.id, twelve.id]
    assert len(game.status_data()["bounties"]) == 2
    assert arms.id in {b.id for b in bounties.visible(game.state, content)} and bounties.board_here(game.state, content)
    game = _sync_at(content, world, "丙", NOW + 3 * calendar.DAY)  # 走過季末：真的收季
    assert world.get_season().ended
    lines = [bounties.LAPSED_SEASON.format(title=bounties.title(content, b)) for b in (eleven, twelve)]
    assert _told(game) == lines  # 兩張同一句，沒有「過了期限」
    assert "丙" not in _takers(world, eleven) and "丙" not in _takers(world, twelve)
    assert game.status_data()["bounties"] == []
    s, c = game.state, content
    assert bounties.open_bounties(s, c) == [] and bounties.mine(s, c) == [] and bounties.visible(s, c) == []
    assert bounties.status(s, c, world) == [] and not bounties.board_here(s, c)
    left = next(b for b in s.world.bounties if b.id == arms.id)  # 求兵一樣：榜上看不到、交不了，也沒有作廢的話（沒人揭）
    assert left.id not in {b.id for b in bounties.visible(s, c)} and bounties.give_problem(s, c, world, left, "x") == bounties.NOT_NOW
    assert bounties.give_choice(s, c, world) is None
    assert [o.id for o in game.options(odds=False)] == ["season:resting"]  # 休季的選單沒有懸賞榜那一顆
    game = _sync_at(content, world, "丙", NOW + 3 * calendar.DAY + 60)
    assert _told(game) == lines  # 只補一次


def test_a_bounty_that_is_not_for_the_season_end_still_lapses_at_its_own_time_fb152(beta_setup):
    """沒寫「到季末」的單（第 2 週掛的、第 4 週初到期）照舊在自己的時間作廢、說「過了期限」，不等季收；寫「到季末」的那張還留著，
    季收了才補「這一季收了」。"""
    content, world = beta_setup
    season = world.get_season()
    early = _post(world, kind="scout", faction="huang", silver=10, deeds=2, location="lake", expires=calendar.week_start(4, content, season))
    late = _post(world, kind="scout", faction="huang", silver=10, deeds=2, location="cave", expires=calendar.week_start(13, content, season))
    _hold(content, world, "丙", early.id, late.id)
    assert bounties.due_text(early, content, season) != bounties.SEASON_END
    game = _sync_at(content, world, "丙", NOW + calendar.week_start(4, content, season) + 60)
    assert not world.get_season().ended
    assert _told(game) == [bounties.LAPSED_DUE.format(title=bounties.title(content, early))]
    assert [b.id for b in bounties.mine(game.state, content)] == [late.id]
    game = _sync_at(content, world, "丙", NOW + 3 * calendar.DAY)
    assert world.get_season().ended
    assert sorted(_told(game)) == sorted([bounties.LAPSED_DUE.format(title=bounties.title(content, early)),
                                          bounties.LAPSED_SEASON.format(title=bounties.title(content, late))])  # 兩次同步各一則紀錄


def test_a_bounty_past_its_own_time_says_so_even_if_the_holder_only_syncs_after_the_close_fb152(beta_setup):
    """揭著的人一直沒同步、季先收了：自己的期限先到的那張還是說「過了期限」（那才是它先消失的原因），寫「到季末」的才說「這一季收了」。"""
    content, world = beta_setup
    season = world.get_season()
    early = _post(world, kind="scout", faction="guan", silver=10, deeds=2, location="lake", expires=calendar.week_start(4, content, season))
    late = _post(world, kind="scout", faction="guan", silver=10, deeds=2, location="cave", expires=calendar.week_start(14, content, season))
    _hold(content, world, "甲", early.id, late.id)
    game = _sync_at(content, world, "甲", NOW + 3 * calendar.DAY)
    assert world.get_season().ended
    assert _told(game) == [bounties.LAPSED_DUE.format(title=bounties.title(content, early)),
                           bounties.LAPSED_SEASON.format(title=bounties.title(content, late))]


def test_a_wanted_that_runs_to_the_season_end_is_refunded_when_the_season_closes_fb152(beta_setup):
    """通緝寫「到季末」也一樣：季還在跑時押金不退，季收了掛單的人下次同步時退回（一次）。"""
    content, world = beta_setup
    for name in ("甲", "乙"):
        state = _load(world, name)
        state.player.location = "lake"
        CharacterStore(world.db).save(state)
    _do(content, world, "甲", lambda g: g.peer_act("乙", "wanted", {"amount": 40}))
    wanted_id = world.get_season().bounties[-1].id
    world.mutate_season(lambda s: setattr(s.bounties[-1], "expires", calendar.week_start(14, content, s)))

    def wanted():
        return next(b for b in world.get_season().bounties if b.id == wanted_id)

    assert bounties.due_text(wanted(), content, world.get_season()) == bounties.SEASON_END
    game = _sync_at(content, world, "甲", NOW + 30 * HOUR)
    assert game.state.player.stats["silver"] == 160 and not wanted().refunded
    game = _sync_at(content, world, "甲", NOW + 3 * calendar.DAY)
    assert world.get_season().ended and wanted().refunded
    assert game.state.player.stats["silver"] == 200
    assert any("押金退回" in line for e in game.state.journal if e.title.startswith(bounties.BOARD) for line in e.lines)
    game = _sync_at(content, world, "甲", NOW + 3 * calendar.DAY + 60)
    assert game.state.player.stats["silver"] == 200  # 只退一次


def test_one_past_due_question_serves_every_expiry_check_fb152_fb153(setup):
    """管理者把季末往後排（80 小時），世界走到第 61 小時（名義季末 60 已過、季還在跑）：寫「到季末」的單在每一處都還算有效——
    榜上有、掛通緝的人不能再掛第二張、押金不退、週初掛單不把它清掉也不佔著它的地點；沒寫「到季末」的照自己的期限。"""
    content, world = setup
    state = _load(world, "甲")
    state.player.stats["silver"] = 200
    world.mutate_season(lambda s: s.schedule.__setitem__("finale", 80 * HOUR))
    season = _advance_to(world, content, 61)
    assert not season.ended and season_end_time(season, content) == 80 * HOUR and season.time > 60 * HOUR
    scout = _post(world, kind="scout", faction="guan", silver=10, deeds=2, location="lake", expires=calendar.week_start(13, content, season))
    wanted = _post(world, kind="wanted", faction="guan", silver=40, deeds=4, quota=1, poster="甲", target="乙",
                   expires=calendar.week_start(13, content, season))
    ordinary = _post(world, kind="scout", faction="guan", silver=10, deeds=2, location="cave", expires=calendar.week_start(9, content, season))
    state.world = world.get_season().model_copy(deep=True)
    scout, wanted, ordinary = (next(b for b in state.world.bounties if b.id == x.id) for x in (scout, wanted, ordinary))
    open_ids = {b.id for b in bounties.open_bounties(state, content)}
    assert {scout.id, wanted.id} <= open_ids and ordinary.id not in open_ids  # 沒寫「到季末」的 ordinary 過期了
    assert not any(bounties.past_due(b, content, state.world) for b in (scout, wanted))
    assert bounties.past_due(ordinary, content, state.world)
    other = _load(world, "乙")
    assert bounties.post_problem(state, content, other) == "你已經掛著一張通緝了，等它揭下再說。"
    assert bounties.deliver_refunds(state, content) == [] and not wanted.refunded
    state.world.bounty_week = 11
    for k in range(10):  # 週初掛單的亂數看流水號：換幾個種子，新的一批都不會挑到被「到季末」的單佔著的地點
        trial = state.model_copy(deep=True)
        trial.world.bounty_seq += k
        bounties.issue(trial, content, 12)
        board = {b.id for b in trial.world.bounties}
        assert scout.id in board and wanted.id in board and ordinary.id not in board
        assert all(b.location != "lake" for b in trial.world.bounties if b.kind == "scout" and b.id != scout.id and b.week == 12)
    state.world.ended = True  # 季收了：一律算過了
    assert all(bounties.past_due(b, content, state.world) for b in (scout, wanted, ordinary))
    assert bounties.open_bounties(state, content) == []
    assert bounties.post_problem(state, content, other) == bounties.NOT_NOW
    assert bounties.deliver_refunds(state, content)[0].startswith("【懸賞】你通緝")


# ── 原 test_fb500_bounty_season_end.py（整檔搬進來） ──
# FB-500（7 天濃縮季 QA，2026-10-20）：最後兩天的懸賞，同一個期限寫成兩種字。
#
# 照現實天的季（21 天季、7 天濃縮季）有開季偏移 cal_offset：週三 14:00 開的 7 天季，季末是第 8 天 00:00，世界秒是 7 天減 14 小時。
# bounties.to_season_end 比的是名義季長 × DAY（7 天），剛好在季末到期的第 6 天那一批判不成「到季末」，告示寫「期限 第 7 天」，
# 第 7 天那一批卻寫「到季末」——兩批其實都撐到季末。修成比這一季的季曆終點（季曆最後一刻之後那一瞬，同 timetable.finale_default，
# 管理者往後排的季末不算）。週末、14 天的季偏移是 0，照舊比季長 × DAY，一個字都不變。

HOUR_fb500, DAY = 3600, 86400


WED10 = 1792549800  # 2026-10-21 週三 10:30（台灣）


WED14 = WED10 + 3.5 * HOUR_fb500  # 2026-10-21 週三 14:00（台灣）


MON = 1792339200  # 2026-10-19 週一 00:00（台灣）


def _season(content, now):
    season = fresh_season(content)
    stamp_season(season, content, now=now)
    return season


def _batch_fb500(content, season, day):
    """季曆第 day 天 00:00 掛的那一批（bounties.issue_day），回這一天掛的單。"""
    from tianxia import world

    vehicle = world._season_vehicle(content, season)
    season.time = calendar.day_start(day, content, season) + 1
    season.bounty_day = day - 1
    bounties.issue_day(vehicle, content, day)
    hung = [b for b in season.bounties if b.day == day]
    assert hung, day
    return hung


@pytest.mark.slow
def test_the_last_two_days_of_an_afternoon_week7_season_both_say_season_end():
    """修前重現：週三 14:00 開的 7 天季，第 6 天那一批（第 8 天 00:00 到期＝季末）寫「期限 第 7 天・剩 N」、紙上「第 7 天 23:59」，
    第 7 天那一批寫「到季末」。修後兩批都寫「到季末」。"""
    c7 = real_content("week7")
    season = _season(c7, WED14)
    assert season.cal_offset == 14 * HOUR_fb500
    end = season.schedule["finale"]
    for day in (6, 7):
        for b in _batch_fb500(c7, season, day):
            assert b.expires >= end - calendar.EPS_SECONDS, (day, b.id)
            assert bounties.to_season_end(b, c7, season), (day, b.id)
            assert bounties.due_text(b, c7, season) == bounties.SEASON_END
            assert bounties.due_short(b, c7, season).startswith(f"{bounties.SEASON_END}・剩 ")
    for b in _batch_fb500(c7, season, 5):  # 第 5 天那一批在第 7 天 00:00 到期，照舊寫最後還有效的那一天
        assert not bounties.to_season_end(b, c7, season)
        assert bounties.due_short(b, c7, season).startswith("到第 6 天・剩 ")
        assert bounties.due_text(b, c7, season) == "第 7 天 00:00"


@pytest.mark.slow
def test_a_midnight_week7_season_was_already_right():
    """00:00 開的季偏移是 0：修前修後一樣，第 6、7 天兩批都寫「到季末」。"""
    c7 = real_content("week7")
    season = _season(c7, MON)
    assert season.cal_offset == 0
    for day in (6, 7):
        assert all(bounties.to_season_end(b, c7, season) for b in _batch_fb500(c7, season, day))


@pytest.mark.slow
def test_season21_last_two_days_say_season_end_too():
    """21 天季同一個錯（QA 對照腳本：週三 10:30 開，最後兩天的單都寫「期限 第 3 週週日」）：修後寫「到季末」；
    第 19 天那一批（第 21 天 00:00 到期）照舊寫「到第 3 週週六」。"""
    c21 = real_content("season21")
    season = _season(c21, WED10)
    assert season.cal_offset == 2 * DAY + 10.5 * HOUR_fb500
    for day in (20, 21):
        for b in _batch_fb500(c21, season, day):
            assert bounties.to_season_end(b, c21, season), (day, b.id)
            assert bounties.due_short(b, c21, season).startswith(f"{bounties.SEASON_END}・剩 ")
    for b in _batch_fb500(c21, season, 19):
        assert not bounties.to_season_end(b, c21, season)
        assert bounties.due_short(b, c21, season).startswith("到第 3 週週六・剩 ")


@pytest.mark.slow
def test_an_admin_pushed_finale_keeps_both_batches_until_the_real_close():
    """連帶（QA）：管理者把季末往後排時，第 6、7 天兩批都撐到季真的收了（past_due 照 to_season_end），不是一批第 8 天 00:00 就作廢。"""
    c7 = real_content("week7")
    season = _season(c7, WED14)
    hung = _batch_fb500(c7, season, 6) + _batch_fb500(c7, season, 7)
    season.schedule["finale"] = season.schedule["finale"] + 6 * HOUR_fb500
    season.time = calendar.day_start(8, c7, season) + HOUR_fb500  # 名義季末過了一小時，季還在跑
    assert not season.ended
    assert not any(bounties.past_due(b, c7, season) for b in hung)


@pytest.mark.slow
@pytest.mark.parametrize("profile", [None])
def test_weekend_and_fourteen_day_seasons_compare_with_the_season_length_as_before(profile):
    """週末、14 天的季沒有偏移：照舊比季長 × DAY，一個字都不變（剛好在季長、差一秒、多一秒三種都跟以前同一個答案）。"""
    content = real_content(profile) if profile else real_content()
    season = _season(content, MON)
    assert season.cal_offset == 0 and not calendar.season21_on(season, content)
    length = season_length_days(season, content) * DAY
    probe = Bounty(id="b0", kind="scout", faction="guan", week=1, expires=0.0, silver=10, deeds=1)
    for expires in (length - 1, length - calendar.EPS_SECONDS / 2, length, length + 1, length + 7 * DAY):
        b = probe.model_copy(update={"expires": expires})
        assert bounties.to_season_end(b, content, season) == (expires >= length - calendar.EPS_SECONDS), expires
