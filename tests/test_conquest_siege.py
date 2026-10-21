"""領地爭奪第二批 Task 11：攻城戰（範本、開集結、留守、收場、易手、作廢、軍餉；Review Focus 3；裁決 8、14）。"""
from __future__ import annotations

import pytest

from conquest_kit import announce, conquest_game, go, join, plain_game
from tianxia import battle_instance, battlelog, conquest, conquest_day, rules, siege
from tianxia.state import BattleRecord

pytestmark = pytest.mark.slow  # 建 Game、載正式內容

NOW = 1_792_000_000.0


def _game(side="huang", loc="nanyang_road", name="沈浪", world=None):
    game = go(join(conquest_game("season21", name=name, world=world), side), loc)
    game.now = NOW
    return game


def _open(game, slot):
    """把這一場排到此刻開集結（半小時後開打），照 world 的路開（siege.open_waiting）。"""
    w = game.state.world
    slot.muster_at, slot.at, slot.status = w.time, w.time + 1800, "waiting"
    game._save_season()
    msgs = siege.open_waiting(game.world, game.content, NOW)
    game.state.world = game.world.get_season()
    return msgs


def _siege_of(game, slot):
    found = next(s for s in game.state.world.conquest.schedule if s.id == slot.id)
    return next((b for b in game.world.get_sieges() if b.record_id == found.record_id), None), found


def _end(game, battle, trend: int):
    """收場（戰局停在 trend），照收場那一下的路套結果。"""
    def _close(b):
        b.phase, b.trend, b.end_time = "ended", trend, game.state.world.time

    after = game.world.mutate_siege(battle.record_id, _close)
    game._apply_battle_outcome(after)
    game.state.world = game.world.get_season()
    return after


def test_templates_exist_for_every_region_and_stay_off_the_admin_menu():
    game = conquest_game("season21")
    c = game.content
    for loc in conquest.blocks(c):
        if conquest.capturable(c, loc):
            assert siege.template(c, loc).siege
    assert not any(b.siege for b in game.admin_battles())


def test_siege_opens_at_muster_with_progress_shift():
    game = _game()
    slot = announce(game, "nanyang_road", "huang")
    conquest.push(game.state.world, game.content, "nanyang_road", "huang", "某", 80, "attack")  # 黃巾那一條 80：偏 6（戰局以官軍為正向，往下）
    msgs = _open(game, slot)
    battle, found = _siege_of(game, slot)
    assert battle is not None and found.status == "open" and found.record_id == battle.record_id
    assert battle.trend_start == 44 and battle.trend == 44
    assert battle.muster_deadline_real == pytest.approx(NOW + 1800)  # 集結截止＝開打的那一刻
    assert battle.siege.loc == "nanyang_road" and battle.siege.attackers == ["huang"] and battle.siege.holder is None
    assert any("攻城・南陽官道" in m for m in msgs)
    # 打完之前推不動；集結中的原因照那一步寫（FB-552：去加入攻城），不再是「已下戰書」
    assert conquest.push_problem(game.state.world, game.content, "huang", "nanyang_road", "attack") == conquest.WHY_MUSTER


def test_neutral_siege_has_a_guard_commander():
    game = _game()
    _open(game, announce(game, "nanyang_road", "huang"))
    battle = game.world.get_sieges()[0]
    assert battle.siege.guard_side == "guan"
    guards = [c for c in battle.commanders if c.fid.startswith("squad:")]
    assert len(guards) == 1 and guards[0].faction == "guan" and guards[0].name not in battle.participants
    assert guards[0].score > 0 and guards[0].neili == guards[0].neili_cap > 0


def test_attacker_win_flips_and_reweighs():
    game = _game()
    slot = announce(game, "nanyang_road", "huang")
    conquest.push(game.state.world, game.content, "nanyang_road", "huang", "沈浪", 70, "attack")
    _open(game, slot)
    battle = game.world.get_sieges()[0]
    game.choose(next(o.id for o in game.options() if o.id.startswith("battle:join:huang")))
    game.world.mutate_siege(battle.record_id, lambda b: setattr(b.participants[game.state.player.name], "acted_rounds", 5))
    before = rules.world_trend_value(game.state.world, game.content, "nanyang")
    after = _end(game, battle, 10)  # 黃巾大勝
    w = game.state.world
    assert conquest.holder(w, game.content, "nanyang_road") == "huang"
    assert rules.world_trend_value(w, game.content, "nanyang") > before  # 照新的基準
    assert any("南陽官道落入" in r.text for r in w.rumors)
    assert conquest.bars(w, "nanyang_road") == {} and conquest.cooling(w, game.content, "nanyang_road")  # 照推滿易手：清掉、冷卻
    assert [p.name for p in w.conquest.payouts] == ["沈浪"]  # 推過的人分紅
    _, found = _siege_of(game, slot)
    assert found.status == "done" and found.winner == "huang"
    ended = game.world.ended_battle(after.record_id)
    assert ended.outcome_side == "huang" and ended.outcome_margin == "大勝" and ended.outcome_title == "黃巾軍大勝，拿下南陽官道"
    report = next(r for r in game.state.battles if r.battle_ref == after.record_id)
    assert report.kind == "siege" and report.event == "攻城・南陽官道"


def test_defender_win_keeps_holder():
    game = _game()
    slot = announce(game, "nanyang_road", "huang")
    conquest.push(game.state.world, game.content, "nanyang_road", "huang", "某", 70, "attack")
    _open(game, slot)
    battle = game.world.get_sieges()[0]
    _end(game, battle, 60)  # 守將那一邊（官軍那一格）佔上風
    assert conquest.holder(game.state.world, game.content, "nanyang_road") is None  # 中立還是中立
    assert conquest.bar(game.state.world, "nanyang_road", "huang") == 35  # 打輸進度砍半（設計 4.4）
    _, found = _siege_of(game, slot)
    assert found.status == "done" and found.winner is None


def test_siege_void_when_no_attacker():
    game = _game(side="guan", loc="nanyang_road")  # 官軍的人在場、黃巾一個人都沒來
    slot = announce(game, "nanyang_road", "huang")
    _open(game, slot)
    battle = game.world.get_sieges()[0]
    conquest.push(game.state.world, game.content, "nanyang_road", "huang", "某", 70, "attack")
    game._save_season()
    game.now = NOW + 1801  # 集結截止
    game._battle_status(tick=True)
    game.state.world = game.world.get_season()
    ended = game.world.ended_battle(battle.record_id)
    assert ended is not None and ended.unfinished and ended.siege.void
    _, found = _siege_of(game, slot)
    assert found.status == "void" and conquest.bar(game.state.world, "nanyang_road", "huang") == 70  # 作罷：進度照留、解凍
    assert not any("作罷" in r.text for r in game.state.world.rumors if r.layer == "world")  # 裁決 19：不發天下大事（test_conquest_void_quiet）
    assert not any(r.battle_ref == battle.record_id and r.kind == "siege" for r in game.state.battles)  # 沒有戰報、沒有軍餉


def test_siege_void_when_attacker_already_holds():
    game = _game()
    slot = announce(game, "nanyang_road", "huang")
    conquest.set_control(game.state.world, game.content, "nanyang_road", "huang")
    _open(game, slot)
    assert game.world.get_sieges() == []
    _, found = _siege_of(game, slot)
    assert found.status == "void"


def test_later_siege_fights_the_new_holder():
    game = _game()
    first = announce(game, "nanyang_road", "guan", minute=14 * 60)
    _open(game, first)
    _end(game, game.world.get_sieges()[0], 90)  # 官軍 14:00 先拿下
    assert conquest.holder(game.state.world, game.content, "nanyang_road") == "guan"
    second = announce(game, "nanyang_road", "huang", minute=20 * 60)
    _open(game, second)
    battle = next(b for b in game.world.get_sieges() if b.phase != "ended")
    assert battle.siege.holder == "guan" and battle.siege.guard_side is None and battle.siege.attackers == ["huang"]
    assert battle.commanders and {c.faction for c in battle.commanders} == {"guan"}  # 守方是官軍的留守


def test_merged_siege_keeps_the_guard():
    # 裁決 22（企劃者 2026-10-21）翻過來：以前兩軍同時搶同一塊中立地拿掉守將、兩軍正面打；現在是三方混戰，守將留著站第三格
    # （新規則的測試在 tests/test_conquest_melee.py）
    game = _game()
    _open(game, announce(game, "nanyang_road", "huang", merged=("guan", "huang")))
    battle = game.world.get_sieges()[0]
    assert battle.siege.attackers == ["guan", "huang"] and battle.siege.guard_side == battle_instance.GUARD
    assert [c.faction for c in battle.commanders] == [battle_instance.GUARD]


def test_pay_is_half_of_a_showdown():
    game = _game()
    _open(game, announce(game, "nanyang_road", "huang"))
    battle = game.world.get_sieges()[0]
    game.choose(next(o.id for o in game.options() if o.id.startswith("battle:join:huang")))
    battle = game.world.mutate_siege(battle.record_id, lambda b: setattr(b.participants[game.state.player.name], "acted_rounds", 6))
    battle.outcome_side, battle.outcome_margin = "huang", "險勝"
    me = battle.participants[game.state.player.name]
    silver0 = game.state.player.stats.get("silver", 0)
    game._showdown_pay(battle, me, [])
    siege_pay = game.state.player.stats["silver"] - silver0
    showdown = battle.model_copy(update={"siege": None})
    game._showdown_pay(showdown, me, [])
    full = game.state.player.stats["silver"] - silver0 - siege_pay
    assert siege_pay == round(full * game.content.config.conquest.pay_share)


def test_other_army_cannot_stand_with_the_guard():
    game = _game(side="guan", loc="nanyang_road")
    _open(game, announce(game, "nanyang_road", "huang"))
    assert not any(o.id.startswith("battle:") for o in game.options())  # 黃巾攻中立地：官軍插不上手，照常遊玩
    assert game._battle_choose_in("join:guan") != ["你加入了這場戰局。"]
    assert "插不上手" in game.scene_text() and "人要到了那裡" not in game.scene_text()  # 場景說對原因
    ranger = _game(side=None, loc="nanyang_road", name="散某", world=game.world)
    enlists = {o.id for o in ranger.options() if o.id.startswith("battle:enlist:")}
    assert enlists == {"battle:enlist:guan", "battle:enlist:huang"}  # 散人可以投效守將那一邊（助守，裁決 8）
    ranger.choose("battle:enlist:guan")
    assert ranger.world.get_sieges()[0].participants["散某"].faction == "guan"


def test_siege_reports_keep_their_own_twenty():
    game = conquest_game("season21")
    s = game.state
    for i in range(battlelog.MAX_RECORDS + 5):
        battlelog.add_record(s, BattleRecord(id=i + 1, time=float(i), location="x", kind="siege", event="攻城・x", opponent="y",
                                             ours=[], tier="官軍大勝", our_power=0.0, difficulty=0.0))
    battlelog.add_record(s, BattleRecord(id=99, time=99.0, location="x", kind="showdown", event="長社火攻", opponent="y",
                                         ours=[], tier="官軍大勝", our_power=0.0, difficulty=0.0))
    assert sum(1 for r in s.battles if r.kind == "siege") == battlelog.SIEGE_KEEP
    assert any(r.kind == "showdown" for r in s.battles)


def test_switch_off_nothing_opens():
    game = plain_game("season21")
    assert siege.open_waiting(game.world, game.content, NOW) == []
    assert game.world.get_sieges() == []
    assert conquest_day.today(game.state.world, game.content, "huang", "attack") == []
