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


@pytest.mark.smoke
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
        # at（收場那一刻的季時間，FB-175）不比：排程那一條推季的時鐘、旁人的畫面那一條只讀，兩條路的季時間本來就不一樣
        outcomes.append(world.seal_state().registry.history[-1].model_dump(exclude={"at"}))
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
        game.choose("act:explore")  # 別的動作（收尾 _save_season 整份存回賽季）
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


# ── Task 9：放手一搏三段式、伺服器 ──

def _active_with_me(content, world):
    """開打了、挑戰者在場（回合 1 剛開）的單挑；回挑戰者的 Game（own_request）。"""
    _open_duel(content, world)
    me = _player(content, world, world.seal_state().duels[0].challenger.name)
    me.mark_seen(170.0)
    with at(me, 170.0):
        me.options()
    with at(me, 180.0):
        me.options()
    return me


def test_the_a_step_only_reads_and_carries_the_foe_line(sealed, world):
    """5.7 A 段：鎖內、只讀；單子帶單挑 id、回合、哪一邊、文字、場景與對手的身手那一行（只寫比較，不寫數字）。"""
    me = _active_with_me(sealed, world)
    before = world.seal_state()
    with at(me, 181.0):
        request = me.seal_text_request("  踢起沙土迷他的眼  ")
    assert isinstance(request, seal_duel.TextRequest)
    assert (request.round, request.side, request.text) == (0, "challenger", "踢起沙土迷他的眼")
    assert "懷璽" in request.target and not any(ch.isdigit() for ch in request.target)
    assert world.seal_state().duels == before.duels


def test_an_absent_side_cannot_open_a_request(sealed, world):
    _active_with_me(sealed, world)
    holder = _player(sealed, world, "懷璽")
    holder.mark_seen(181.0)
    with at(holder, 181.0):
        assert holder.seal_text_request("拚了") == [f"（{seal_duel.LATE}）"]


def test_the_c_step_applies_only_to_the_same_round_side_and_text(sealed, world):
    """5.7 C 段：同一場、同一回合、同一邊、同一句才採用；回合對不上回「這一回合已經結算」、不重評；送出不等於結算。"""
    me = _active_with_me(sealed, world)
    with at(me, 181.0):
        request = me.seal_text_request("踢起沙土")
        stale = request._replace(round=request.round - 1)
        assert me.seal_gamble("踢起沙土", 70, ("甲踢起沙土。", "甲踢空了。"), request=stale) == [f"（{seal_duel.GONE}）"]
        assert me.seal_gamble("換一句", 70, ("", ""), request=request) == [f"（{seal_duel.RESEND}）"]
        me.seal_gamble("踢起沙土", 70, ("甲踢起沙土。", "甲踢空了。"), request=request)
    duel = world.seal_state().duels[0]
    assert duel.pending == {"challenger": seal_duel.TEXT} and duel.rates == {"challenger": 70} and duel.round == 0


def test_a_side_gets_no_input_box_after_two_gambles(sealed, world):
    me = _active_with_me(sealed, world)
    world.mutate(lambda st: setattr(st.seal_duels[0].challenger, "gambles", 2))
    with at(me, 181.0):
        assert me.seal_free_text_prompt() is None
        assert me.seal_text_request("再來") == [f"（{seal_duel.NO_MORE_GAMBLE}）"]


def test_the_input_box_goes_to_the_seal_duel_before_the_boss_duel(sealed, world):
    """5.7 最後一條：輸入框三選一，「正在打的決戰 > 奪璽單挑 > 頭目戰」。"""
    import server

    me = _active_with_me(sealed, world)
    with at(me, 181.0):
        view = server.main_view(me)
    assert view["free_op"] == "seal_text" and view["free_text"] == seal_duel.PROMPT


def test_everyone_sees_the_seal_card_and_the_parties_are_watched(sealed, world):
    """5.10：奪璽卡全服看得到；seal_watch 在單挑雙方與被璽動那一場的參戰者、持有者為真（網頁在背景也輪詢，5.5）。"""
    _open_duel(sealed, world)
    crowd = _player(sealed, world, "路人")
    card = crowd.status_data()["seal_duel"]
    assert card["holder"] == "懷璽" and card["shard"] == "螭首" and not card["mine"]
    assert crowd.status_data()["seal_watch"] is False
    side = _player(sealed, world, world.seal_state().duels[0].challenger.name)
    assert side.status_data()["seal_watch"] is True


# ── Task 10：收場補送、碎片卡、江湖史 ──

def _finished(content, world, taken: bool, won: bool = True):
    """跑完一場單挑（管理者式的定結果：fixed＝taken）；won 時持有者的池子只剩 1（第一回合就見底，挑戰者大勝），否則挑戰者的只剩 1。
    回挑戰者的名號。兩人都還沒建角色（他們第一次同步就補送）。"""
    game = _open_duel(content, world)

    def _rig(st):
        d = st.seal_duels[0]
        d.fixed = taken
        (d.holder if won else d.challenger).hp = 1.0

    world.mutate(_rig)
    t = 180.0
    while world.seal_state().duels and t < 500.0:
        with at(game, t):
            game.options()
        t += 20.0
    event = world.seal_state().registry.history[-1]
    return event.holder if event.kind == "take" else event.other


def test_a_take_is_delivered_to_both_with_a_seal_report_and_fame_in_the_same_season(sealed, world):
    """5.9：易手只改登記；兩人各自同步時補一份戰報（kind seal，回合一行一行）與一則紀錄；失主名望 +5；補過的不補第二次；抄本照登記重抄。"""
    challenger = _finished(sealed, world, taken=True)
    old = _player(sealed, world, "懷璽", now=600.0)  # 第一次同步就補到
    report = old.state.battles[0]
    assert report.kind == "seal" and report.rounds and old.state.player.stats.get("fame", 0) == 5
    assert old.state.player.heirloom is None
    seen = old.state.player.seal_seen
    old.sync(700.0)
    assert old.state.player.seal_seen == seen and len([b for b in old.state.battles if b.kind == "seal"]) == 1
    new = _player(sealed, world, challenger, now=600.0)
    assert new.state.battles[0].kind == "seal" and new.state.player.heirloom.template == "chishou"


def test_a_near_miss_gives_the_challenger_one_fame_and_the_holder_three(sealed, world):
    """PM 丁：挑戰者打贏單挑（大勝）、再擲沒中，名望 +1；持有者懷璽不失 +3。"""
    challenger = _finished(sealed, world, taken=False, won=True)
    holder = _player(sealed, world, "懷璽", now=600.0)
    them = _player(sealed, world, challenger, now=600.0)
    assert holder.state.player.stats.get("fame", 0) == 3 and them.state.player.stats.get("fame", 0) == 1


def test_a_holder_back_only_next_season_gets_the_report_but_no_fame(sealed, world):
    """5.9：跨季才回來的只補戰報與紀錄（名望每季重來），抄本照登記。"""
    from conftest import next_season

    _finished(sealed, world, taken=True)
    old = Game.new(sealed, "懷璽", rng=random.Random(0), world=world)  # 建好但這一季沒同步過
    next_season(sealed, world, old)
    assert any(b.kind == "seal" for b in old.state.battles) and old.state.player.stats.get("fame", 0) == 0


def test_the_emergence_winner_learns_the_emerge_skill_in_the_same_season(sealed, world):
    """11.2 第 4 條：混元一氣改給現世的得主，只在補送當下還是同一季、還沒學過、持有沒滿才給。測試內容沒有混元一氣，借一門內容武學當 emerge_skill。"""
    from test_seal import _ended
    from tianxia import library

    skill = next(s for s in sealed.skills if s not in sealed.config.starter_skills)
    sealed.config.seal.emerge_skill = skill
    _setup(sealed, world)
    game = _player(sealed, world, "旁人")
    winner = _player(sealed, world, "得主", "guan")
    game._seal_settle(_ended("wancheng_jia", [("得主", "guan", 9, 9)], seal_emerge="yunzhuan"), sealed.battles["wancheng_jia"],
                      {"side": "guan", "margin": "大勝"})
    winner.sync(50.0)
    assert winner.state.player.heirloom.template == "yunzhuan" and skill in library.owned_arts(winner.state)
    assert any("雲篆" in e.tag for e in winner.state.journal)


def test_the_holder_card_tells_the_shard_its_effect_and_the_risky_dates(sealed, world):
    """第十節：持有者的碎片卡寫哪一片與效果、「新得之季，此季不動」或「此季已動過」、這一季標了 seal 還沒到的決戰時刻（Game.stamp）；不寫機率。"""
    _setup(sealed, world)
    holder = _player(sealed, world, "懷璽")
    card = holder.status_data()["seal"]
    assert card["name"] == "螭首" and "氣血上限" in card["effect_text"] and len(card["dates"]) == 2
    assert not any("%" in d for d in card["dates"]) and _player(sealed, world, "路人").status_data()["seal"] is None


def test_the_chronicle_opens_with_the_seven_shards(sealed, world):
    _setup(sealed, world)
    text = _player(sealed, world, "路人").chronicle_text()
    head = text.split("---")[0]
    assert "傳國玉璽" in head and "螭首" in head and "懷璽" in head and head.count("未現世") == 6


def test_a_retired_bot_holding_a_shard_may_come_back_regardless_of_gaps(sealed, world):
    """7.6：每季開季後第一次補人，持碎片的退隱假人各擲一次回不回來（bot_return_chance），不看缺額；回來的派到名冊人數最少的陣營。"""
    from tianxia.bot_runner import BotRunner, TickReport
    from tianxia.state import BotProfile

    _setup(sealed, world, holder="老假人")
    bot = Game.new(sealed, "老假人", rng=random.Random(0), world=world)
    bot.state.player.bot = BotProfile(personality="普通", seed=1, faction="guan", season_number=0)  # 上一季的：退隱
    CharacterStore(world.db).save(bot.state)
    sealed.config.seal.bot_return_chance = 1.0
    runner = BotRunner(sealed, world, CharacterStore(world.db), random.Random(0), clock=lambda: 100.0)
    report = TickReport()
    runner._wake_seal_bots(100.0, report)
    woken = CharacterStore(world.db).load("老假人")
    assert woken.player.bot.season_number == world.seal_state().season and report.added == 1
    runner._wake_seal_bots(110.0, report)
    assert report.added == 1  # 這一季擲過了


# ── Task 11：管理者、假人 ──

def _admin(content, world):
    content.config.admins = ["管理者"]
    return _player(content, world, "管理者")


def test_assigning_a_shard_only_touches_the_registry(sealed, world):
    """第十二節：指定持有者只改登記，不讀、不建他的存檔（_admin_target(sync=False) 也不用）；一人一片照擋；公告不寫管理者。"""
    _setup(sealed, world)
    admin = _admin(sealed, world)
    admin.admin_seal_assign("yunzhuan", "不在線的人", "held")
    view = world.seal_state()
    shard = view.registry.shards["yunzhuan"]
    assert (shard.state, shard.holder, shard.since_season) == ("held", "不在線的人", view.season)  # 管理者指定的也有新主保護
    assert CharacterStore(world.db).load("不在線的人") is None
    assert "管理者" not in " ".join(r.text for r in world.get_season().rumors)
    admin.admin_seal_assign("xuanniu", "懷璽", "held")  # 懷璽已經有螭首：一人一片
    assert world.seal_state().registry.shards["xuanniu"].holder is None
    admin.admin_seal_assign("yunzhuan", "", "sunk")
    assert world.seal_state().registry.shards["yunzhuan"].state == "sunk"


def test_a_forced_duel_hangs_on_the_last_showdown_unless_the_qa_tools_are_on(sealed, world):
    """第十二節：正式伺服器的強制開單挑只能掛在最近一場剛收場、還沒開過單挑的時刻表決戰上（公告照那一場寫）；qa_tools 開著才能不必有決戰。"""
    _setup(sealed, world)
    admin = _admin(sealed, world)
    _player(sealed, world, "挑戰者", "huang")
    admin.admin_seal_duel("chishou", "挑戰者", 1.0, 0.0)
    assert world.seal_state().duels == []
    world.mutate(lambda st: (setattr(st.seal, "last_showdown", 9), setattr(st.seal, "last_showdown_where", "長社火攻")))
    admin.admin_seal_duel("chishou", "挑戰者", 1.0, 0.0)
    duel = world.seal_state().duels[0]
    assert (duel.id, duel.where, duel.cap, duel.phase) == ("9:chishou", "長社火攻", 0.25, "muster")
    world.mutate(lambda st: setattr(st, "seal_duels", []))
    admin.admin_seal_duel("chishou", "挑戰者", 1.0, 0.0)
    assert world.seal_state().duels == []  # 那一場已經掛過單挑
    sealed.config.seal.qa_tools = True
    admin.admin_seal_duel("chishou", "挑戰者", 0.5, 0.0)
    duel = world.seal_state().duels[0]
    assert duel.id.startswith("qa") and duel.cap == 0.125 and duel.where == ""


def test_fix_and_cancel_a_running_duel(sealed, world):
    _open_duel(sealed, world)
    admin = _admin(sealed, world)
    admin.admin_seal_fix(True)
    assert world.seal_state().duels[0].fixed is True
    admin.admin_seal_cancel()
    view = world.seal_state()
    assert view.duels == [] and view.registry.history[-1].kind == "unsettled" and view.registry.shards["chishou"].holder == "懷璽"


def test_the_sink_check_only_reports(sealed, world):
    _setup(sealed, world, holder="久未上線")
    world.mutate(lambda st: (setattr(st.seal, "opened_real", 0.0), setattr(st.seal.shards["chishou"], "absent", 2)))
    lines = _admin(sealed, world).admin_seal_sink_check(100 * 86400.0)
    assert any("螭首" in line for line in lines) and world.seal_state().registry.shards["chishou"].state == "held"


def test_server_bots_never_press_a_seal_move_and_are_never_present(sealed, world):
    """14.1：假人在單挑裡一律被代打——bot_policy 不按 seal:，假人程式的 Game 不記 last_seen。"""
    from tianxia import bot_policy
    from tianxia.bot_runner import BotRunner
    from tianxia.engine import Option

    _open_duel(sealed, world)
    name = world.seal_state().duels[0].challenger.name
    state = _player(sealed, world, name).state
    bot = BotRunner(sealed, world, CharacterStore(world.db), random.Random(0), clock=lambda: 20.0)._bot_game(state)
    assert bot_policy.score(bot, Option(id="seal:強攻", label="強攻（剋奇襲）"), None) is None
    with at(bot, 20.0):
        bot.options()
    assert world.seal_state().duels[0].challenger.last_seen is None


# ── 最終審查的修正 ──

def test_the_holder_report_is_written_from_the_holder_side(sealed, world):
    """最終審查 I-2：持有者那一份照挑戰者的翻過來寫（5.9）：挑戰者落敗時持有者是勝；兩份都不寫「我方威力 0／對手難度 0」、
    沒有空的「我方」那一行，類型那一格寫「奪璽：『螭首』」而不是「奪璽：奪璽・『螭首』」。"""
    from tianxia import battlelog

    challenger = _finished(sealed, world, taken=False, won=False)  # 挑戰者的池子只剩 1：落敗
    holder = _player(sealed, world, "懷璽", now=600.0)
    them = _player(sealed, world, challenger, now=600.0)
    mine, theirs = holder.state.battles[0], them.state.battles[0]
    assert theirs.tier == "落敗" and mine.tier in ("大勝", "險勝")
    for record in (mine, theirs):
        text = battlelog.detail_text(record)
        assert "威力 0" not in text and "難度 0" not in text and "**我方**" not in text
        assert "奪璽：『螭首』" in text and "奪璽・" not in text
        battlelog.outcome_text(record)  # 照四種結果字查表：不會 KeyError


def test_a_challenger_win_reads_as_a_win_and_the_holder_as_a_loss(sealed, world):
    challenger = _finished(sealed, world, taken=True, won=True)  # 持有者的池子只剩 1：挑戰者大勝（或提前大勝）
    holder = _player(sealed, world, "懷璽", now=600.0)
    them = _player(sealed, world, challenger, now=600.0)
    assert them.state.battles[0].tier == "大勝" and holder.state.battles[0].tier == "落敗"


def test_the_emergency_switch_does_not_hold_the_season_open(sealed, world, monkeypatch):
    """最終審查 I-3：主機關掉碎片（seal.enabled = false）時，沒打完的單挑不再擋提前收季（它也推不動了）。"""
    from tianxia import calendar
    from tianxia import world as world_rules

    _open_duel(sealed, world)
    sealed.config.seal.enabled = False
    monkeypatch.setattr(world_rules, "decisive_ending", lambda vehicle, content: content.scenario.endings[0])
    season = world.get_season()
    world_rules.advance_world_state(season, sealed, calendar.cal_hour_seconds(sealed, season), random.Random(0), world)
    assert season.ended


def test_next_season_clears_a_duel_left_open_by_the_emergency_switch(sealed, world):
    """最終審查 I-3：開關關著時換季照樣清掉沒打完的單挑、記成未分勝負（兩人補得到），不帶進下一季。"""
    from conftest import next_season

    game = _open_duel(sealed, world)
    sealed.config.seal.enabled = False
    next_season(sealed, world, game)
    view = world.seal_state()
    assert view.duels == [] and view.registry.history[-1].kind == "unsettled"

# ── QA 玉璽一（qa-seal-1）的單 ──

def test_the_gamble_scene_tells_the_model_the_shard_is_not_won_yet(sealed, world):
    """FB-176：放手一搏只爭一回合的氣勢，碎片要到收場再擲；給模型的場景寫明不寫「奪下碎片」。"""
    me = _active_with_me(sealed, world)
    with at(me, 181.0):
        request = me.seal_text_request("虛晃一槍反手奪印")
    assert seal_duel.SCENE_RULE in request.scene


def test_the_sink_check_also_runs_while_the_season_rests(sealed, world):
    """FB-178：「隱沒判斷」只印不改，換季前的休季正是要看的時候。"""
    _setup(sealed, world, holder="久未上線")
    admin = _admin(sealed, world)
    admin.admin_end_season(now=50.0)
    lines = admin.admin_seal_sink_check(100.0)
    assert lines and "無法觸發" not in lines[0]
    assert world.seal_state().registry.shards["chishou"].state == "held"


def test_the_card_countdown_stops_while_the_clock_is_paused(sealed, world):
    """FB-179：暫停賽季時鐘時奪璽卡的倒數停在按下暫停的那一刻（同決戰那一格）。"""
    game = _open_duel(sealed, world)  # 180 秒後開打
    world.pause_clock(100.0)
    game.now = 150.0
    assert game.seal_duel_card()["left"] == 80


def test_the_heirloom_row_is_not_called_swappable(sealed, world):
    """FB-180：寶物段的說明寫「隨時能換」，傳承那一件不能換下：有傳承時說明多一句；寶物關著、只有傳承時不寫寶物那一套。"""
    from tianxia import skillview

    _setup(sealed, world)
    holder = _player(sealed, world, "懷璽")
    sealed.config.treasures.enabled = True
    block = next(b for b in skillview.gear_rows(holder.state, sealed, world)["slots"] if b["slot"] == "treasure")
    assert "不能換下" in block["note"]
    sealed.config.treasures.enabled = False
    block = next(b for b in skillview.gear_rows(holder.state, sealed, world)["slots"] if b["slot"] == "treasure")
    assert "不能換下" in block["note"] and "隨時能換" not in block["note"]
