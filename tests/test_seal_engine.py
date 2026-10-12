"""玉璽碎片接進 Game（玉璽碎片設計第四節～第五節；計畫 docs/superpowers/plans/2026-10-12-玉璽-1-核心.md Task 8～11）。"""
from __future__ import annotations

import random

import pytest

from conftest import at
from test_seal import SALT, _ended, _registry, sealed  # noqa: F401  sealed 是夾具
from tianxia import seal, seal_duel
from tianxia.characters import CharacterStore
from tianxia.engine import Game


def _player(content, world, name, faction=None, now=0.0):
    """建一個角色、同步一次（投靠了就記進名冊）、存進資料庫（別人才讀得到他）。"""
    game = Game.new(content, name, rng=random.Random(0), world=world)
    game.state.player.faction = faction
    game.sync(now)
    CharacterStore(world.db).save(game.state)
    return game


def _stirred(content, holder_side="guan", holder="懷璽", rows=None, rounds=3):
    """長社收場、牽動了懷璽的螭首：預設懷璽（官軍，出手 3）、官甲、黃甲（戰功最高）、黃乙、黃丙（出手 1）。五個人＜10：門檻 1 回合。"""
    rows = rows or [("懷璽", "guan", 3, 0), ("官甲", "guan", 3, 1), ("黃甲", "huang", 3, 3), ("黃乙", "huang", 3, 1), ("黃丙", "huang", 1, 0)]
    return _ended("changshe_fire", rows, rounds=rounds, seal_shard="chishou", seal_holder=holder,
                  seal_holder_faction=holder_side, seal_holder_side=holder_side)


def _setup(content, world, holder="懷璽"):
    world.seed_first_season(content)
    if world.season_phase() == "preparing":
        world.open_season(content, 0.0)
    world.mutate(lambda st: setattr(st, "seal", _registry(content, chishou=holder)))


def _settle(game, content, battle, side="huang", margin="大勝"):
    game._seal_settle(battle, content.battles["changshe_fire"], {"side": side, "margin": margin})


def test_a_big_win_for_the_holder_opens_no_duel(sealed, world):
    _setup(sealed, world)
    _player(sealed, world, "懷璽", "guan")
    _settle(_player(sealed, world, "旁人"), sealed, _stirred(sealed), side="guan", margin="大勝")
    assert world.seal_state().duels == []
    assert any(r.text == seal.NO_DUEL.format(holder="懷璽", shard="螭首") for r in world.get_season().rumors)


def test_a_lost_showdown_calls_out_the_top_merit_foe(sealed, world):
    """持有者那一方大敗：從對面（黃巾）合格的人裡照戰功前三名抽；持有者親自出陣，上限 25% × 1.0 × 0.7；下戰書一句天下大事；
    不碰 Game.rng。"""
    _setup(sealed, world)
    _player(sealed, world, "懷璽", "guan")
    game = _player(sealed, world, "旁人")
    before = game.rng.getstate()
    _settle(game, sealed, _stirred(sealed))
    assert game.rng.getstate() == before
    duel = world.seal_state().duels[0]
    assert duel.challenger.name in {"黃甲", "黃乙", "黃丙"} and duel.holder.name == "懷璽"
    assert (duel.tier, duel.phase, duel.where) == ("大敗", "muster", "長社火攻") and duel.cap == pytest.approx(0.25 * 0.7)
    assert any("下了戰書" in r.text for r in world.get_season().rumors if r.layer == "world")


def test_the_snapshot_beats_a_late_defection(sealed, world):
    """4.2 第 3 條：璽動之後持有者叛到挑戰者那一方的陣營——比的是快照（guan），不是名冊；他改算旁觀、挑戰者從勝方挑、不套同陣營過濾。"""
    _setup(sealed, world)
    world.record_faction("懷璽", "huang")
    _settle(_player(sealed, world, "旁人"), sealed, _stirred(sealed))
    duel = world.seal_state().duels[0]
    assert duel.tier == "旁觀" and duel.challenger.name.startswith("黃")


def test_a_free_holder_who_enlists_with_the_winner_still_duels(sealed, world):
    """4.5：快照是散人（None）一律旁觀；他臨時投效大勝的那一方、出手滿門檻，只多護璽 ×0.7，照樣打。"""
    _setup(sealed, world)
    rows = [("懷璽", "huang", 3, 0), ("黃甲", "huang", 3, 3), ("官甲", "guan", 3, 0)]
    _settle(_player(sealed, world, "旁人"), sealed, _stirred(sealed, holder_side=None, rows=rows))
    duel = world.seal_state().duels[0]
    assert duel.tier == "旁觀" and duel.challenger.name == "黃甲" and duel.cap == pytest.approx(0.25 * 0.7)


def test_challengers_skip_turncoats_newbies_and_the_warlords(sealed, world):
    _setup(sealed, world)
    _player(sealed, world, "懷璽", "guan")
    battle = _stirred(sealed)
    battle.participants["黃甲"].turncoat = True
    battle.participants["黃乙"].newbie = True
    battle.participants["黃丙"].faction = "haoqiang"  # 站在豪強那一邊：不是交戰兩軍
    _settle(_player(sealed, world, "旁人"), sealed, battle)  # 旁人自己是新角色（新手期），也補不上
    assert world.seal_state().duels == []  # 對面無人能上前，懷璽不失
    assert any(r.text == seal.NO_DUEL.format(holder="懷璽", shard="螭首") for r in world.get_season().rumors)


def test_a_small_battle_lets_a_spectating_free_agent_step_up(sealed, world):
    """PM 癸：參戰名單不到 10 人時，人在決戰大區、剛同步過、名冊上是散人、不在新手期的旁觀者也能被挑上陣前（戰功當 0）。"""
    _setup(sealed, world)
    watcher = Game.new(sealed, "看熱鬧的", rng=random.Random(0), world=world)
    watcher.sync(0.0)
    watcher.state.player.location, watcher.state.player.joined_at = "town", -1e9  # 小鎮在北區（install_showdowns）；早就不是新手
    CharacterStore(world.db).save(watcher.state)
    game = _player(sealed, world, "旁人")
    game.now = 10.0
    _settle(game, sealed, _stirred(sealed, rows=[("懷璽", "guan", 3, 0), ("官甲", "guan", 3, 0)]), margin="險勝")
    duel = world.seal_state().duels[0]
    assert duel.challenger.name == "看熱鬧的" and duel.challenger.hp_cap > 0


def test_a_holder_unseen_this_season_fights_as_a_fresh_character_and_is_not_saved(sealed, world):
    """5.3：這一季還沒上線過（seen_real 早於 opened_real）的持有者照新角色的身手（fresh），不存回他的存檔、season_number 不被改寫。"""
    _setup(sealed, world)
    world.mutate(lambda st: setattr(st.seal, "opened_real", 1000.0))
    old = _player(sealed, world, "懷璽", "guan")
    old.state.player.seen_real = 10.0
    old.state.player.member.level = 20
    CharacterStore(world.db).save(old.state)
    _settle(_player(sealed, world, "旁人"), sealed, _stirred(sealed, holder_side=None, rows=[("黃甲", "huang", 3, 3)]))
    duel = world.seal_state().duels[0]
    assert duel.holder.fresh
    saved = CharacterStore(world.db).load("懷璽")
    assert saved.player.member.level == 20 and saved.player.season_number == old.state.player.season_number


def _open_duel(content, world, now=0.0):
    """開一場下戰書的單挑（starts_real ＝ now ＋ 180），回旁人的 Game（不是單挑的任何一方）。"""
    _setup(content, world)
    game = _player(content, world, "旁人", now=now)
    game.now = now
    _settle(game, content, _stirred(content))
    return game


def test_the_duel_runs_paced_rounds_when_nobody_is_there(sealed, world):
    """5.4：下戰書 180 秒，接著兩邊都不在場就 20 秒一回合；誰輪詢誰推，一次最多一回合；收場寫登記與天下大事。"""
    game = _open_duel(sealed, world)
    for t in (100.0, 180.0):
        with at(game, t):
            game.options()
    duel = world.seal_state().duels[0]
    assert (duel.phase, duel.round) == ("active", 0)
    t = 180.0
    while world.seal_state().duels and t < 400.0:
        t += 20.0
        with at(game, t):
            game.options()
    view = world.seal_state()
    assert view.duels == [] and view.registry.history[-1].kind in ("take", "keep")
    rounds = [r.text for r in world.get_season().rumors if r.text.startswith("奪璽第")]
    assert 1 <= len(rounds) <= 5 and len(rounds) == len(set(rounds))


def test_only_your_own_request_marks_you_present(sealed, world):
    """5.5：只有他自己的請求（own_request）記 last_seen，15 秒最多寫一次；不是自己的請求（_kin、假人、管理者建的 Game）一律不記。"""
    _open_duel(sealed, world)
    me = _player(sealed, world, world.seal_state().duels[0].challenger.name)
    with at(me, 10.0):
        me.options()
    assert world.seal_state().duels[0].challenger.last_seen is None
    me.mark_seen(20.0)
    for t, expect in ((20.0, 20.0), (30.0, 20.0), (40.0, 40.0)):
        with at(me, t):
            me.options()
        assert world.seal_state().duels[0].challenger.last_seen == expect


def test_a_present_side_gets_three_moves_and_an_absent_one_waits(sealed, world):
    """5.5：在場的那一邊選單最前面三招（寫剋哪一招）；回合開始時判成不在場的那一邊這一回合灰掉、寫中性的字（不寫代打）。"""
    _open_duel(sealed, world)
    me = _player(sealed, world, world.seal_state().duels[0].challenger.name)
    me.mark_seen(170.0)
    with at(me, 170.0):
        me.options()
    with at(me, 180.0):
        opts = me.options()
    assert [o.id for o in opts[:3]] == ["seal:強攻", "seal:固守", "seal:奇襲"] and all(o.enabled for o in opts[:3])
    holder = _player(sealed, world, "懷璽")
    holder.mark_seen(181.0)
    with at(holder, 181.0):
        late = [o for o in holder.options() if o.id.startswith("seal:")]
    assert late and not any(o.enabled for o in late) and seal_duel.LATE in late[0].label
    with at(me, 182.0):
        me.choose("seal:強攻")
    assert world.seal_state().duels[0].pending == {"challenger": "強攻"}


def test_whoever_ticks_the_duel_gets_the_same_result(sealed, tmp_path):
    """5.13：同一場單挑，由排程（Game.for_world 的 world_tick）推或由旁人的畫面推，結果一模一樣。兩個各自的資料庫。"""
    from tianxia.sqlite_world import open_world

    outcomes = []
    for i, ticker in enumerate(("world", "player")):
        world = open_world(tmp_path / f"{i}.db")
        game = _open_duel(sealed, world)
        pusher = Game.for_world(sealed, world) if ticker == "world" else game
        t = 180.0
        while world.seal_state().duels and t < 500.0:
            if ticker == "world":
                pusher.world_tick(t)
            else:
                with at(pusher, t):
                    pusher.options()
            t += 20.0
        outcomes.append(world.seal_state().registry.history[-1].model_dump())
    assert outcomes[0] == outcomes[1]


def test_a_paused_season_freezes_the_duel_and_resume_shifts_it(sealed, world):
    game = _open_duel(sealed, world)
    world.pause_clock(100.0)
    with at(game, 500.0):
        game.options()
    assert world.seal_state().duels[0].phase == "muster"
    world.resume_clock(sealed, 1100.0)  # 停了 1000 秒
    assert world.seal_state().duels[0].starts_real == pytest.approx(180.0 + 1000.0)


def test_choosing_something_else_mid_duel_does_not_roll_the_round_back(sealed, world):
    """5.12：單挑回合推進之後有人 choose() 別的動作（收尾 _save_season 整份存回賽季），回合不倒回、天下大事不重複。"""
    game = _open_duel(sealed, world)
    with at(game, 180.0):
        game.options()
    with at(game, 200.0):
        game.choose("act:rest")
    with at(game, 201.0):
        game.options()
    texts = [r.text for r in world.get_season().rumors if r.text.startswith("奪璽第")]
    assert world.seal_state().duels[0].round == len(texts) == 1


def test_the_season_does_not_end_early_while_a_duel_is_open(sealed, world, monkeypatch):
    """5.11：有沒打完的奪璽單挑時，那一個曆時不提前收季；沒有就照收。"""
    from tianxia import calendar
    from tianxia import world as world_rules

    _open_duel(sealed, world)
    monkeypatch.setattr(world_rules, "decisive_ending", lambda vehicle, content: content.scenario.endings[0])
    season = world.get_season()
    hour = calendar.cal_hour_seconds(sealed, season)
    world_rules.advance_world_state(season, sealed, hour, random.Random(0), world)
    assert not season.ended
    world.mutate(lambda st: setattr(st, "seal_duels", []))
    world_rules.advance_world_state(season, sealed, hour, random.Random(0), world)
    assert season.ended


def test_ending_the_season_leaves_the_duel_unsettled(sealed, world):
    """5.11：管理者立刻收季（自然收季同）：之後第一次推就記成未分勝負，碎片留在原主。"""
    game = _open_duel(sealed, world)
    sealed.config.admins = ["管理者"]
    _player(sealed, world, "管理者").admin_end_season(now=150.0)
    game.sync(160.0)
    with at(game, 160.0):
        game.options()
    view = world.seal_state()
    assert view.duels == [] and view.registry.history[-1].kind == "unsettled"
    assert view.registry.shards["chishou"].holder == "懷璽"
