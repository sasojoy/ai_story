"""領地爭奪第二批 Task 11：攻城戰（範本、開集結、留守、收場、易手、作廢、軍餉；Review Focus 3；裁決 8、14）。"""
from __future__ import annotations

import pytest

from conquest_kit import announce, conquest_game, go, join, plain_game
from tianxia import battle_instance, battlelog, conquest, conquest_day, rules, siege
from tianxia.state import BattleRecord
import random
from conquest_kit import conquest_game, go, join, plain_game
from tianxia import battle_instance, conquest
from tianxia.battle_instance import SiegeInfo
from tianxia.bot_runner import BotRunner
from tianxia.characters import open_characters
from tianxia.database import SCHEMA_VERSION
from tianxia.sqlite_world import open_world
from conquest_kit import announce, conquest_game, go, join
from tianxia import battle_instance, conquest, siege
from tianxia.battle_instance import GUARD
import inspect
import server
from conquest_kit import announce, conquest_game, go, join, win_sortie
from tianxia import atlas, bot_policy, conquest, conquest_day, orders, ranks, siege
from tianxia.engine import Game
from tianxia.state import Order
from tianxia import battle_instance, siege
from conquest_kit import announce, conquest_game, go, join, plain_game, press
from tianxia import conquest, howto
from tianxia import siege
from conquest_kit import announce, conquest_game, go, join, press
from tianxia import atlas, conquest, mapdata, orders, siege
from fastapi.testclient import TestClient
from conftest import real_content
from conquest_kit import conquest_rules
from tianxia import accounts, conquest
from tianxia.engine import SIEGE_STATUS


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
    # （新規則的測試在 tests/test_conquest_siege.py）
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


# ── 原 test_conquest_multi_battle.py（整檔搬進來） ──
# 領地爭奪第二批 Task 10：多場戰鬥並存（攻城戰另存一串、找戰場、加入鈕、季終收兵、暫停繼續、假人、補戰報；Review Focus 4、5）。
# 資料庫結構不動（第 6 版排給商城）：攻城存在既有的 battles 表、world 那一列的 JSON 記流水號。

def _template(content, region: str = "yingru"):
    """那個大區的攻城範本（Task 11 寫進內容；還沒有時照長社火攻借一份，只換 id）。"""
    tid = f"siege_{region}"
    if tid not in content.battles:
        base = content.battles["changshe_fire"]
        content.battles[tid] = base.model_copy(update={"id": tid, "timetable_event": None, "defender": None, "front": None, "region": region})
    return content.battles[tid]


def _siege(game, loc: str, attackers=("huang",), holder="guan", now: float = NOW):
    info = SiegeInfo(slot_id=f"s-{loc}", loc=loc, attackers=list(attackers), holder=holder)
    region = next(r for r in game.content.map.regions if r.id == _region(game, loc))
    return game.world.start_siege(_template(game.content, region.id), now, 50, info)


def _region(game, loc: str) -> str:
    from tianxia import atlas

    return atlas.region_of(game.content, loc).id


def _two(game):
    """潁川汝南的兩場攻城（同一個大區、同時集結）。"""
    w, c = game.state.world, game.content
    blocks = [loc for loc in conquest.blocks(c) if conquest.capturable(c, loc) and _region(game, loc) == "yingru"][:2]
    return _siege(game, blocks[0]), _siege(game, blocks[1])


def _user_version(world) -> int:
    with world.db.snapshot() as conn:
        return conn.execute("PRAGMA user_version").fetchone()[0]


def test_two_sieges_persist_and_reload():
    game = conquest_game("season21")
    a, b = _two(game)
    assert a.record_id is not None and b.record_id is not None and a.record_id != b.record_id
    again = open_world(game.world.db.path)  # 重開資料庫
    assert [s.record_id for s in again.get_sieges()] == [a.record_id, b.record_id]
    assert again.get_sieges()[0].siege.loc == a.siege.loc
    assert again.get_battle() is None  # 決戰那一格不受影響
    # 結構版本不動：領地爭奪不升版。合 develop 之後基準是商城的第 6 版（以前寫死 5，那時 develop 的商城還沒合進來）
    assert _user_version(again) == SCHEMA_VERSION == 9  # 拿掉 rumor_heard 升到 8、登入狀態（sessions，審查 S-10）升到 9


def test_submit_in_one_battle_does_not_touch_the_other():
    game = go(join(conquest_game("season21"), "huang"), "runan")
    game.now = NOW
    a, b = _two(game)
    joins = [o.id for o in game.options() if o.id.startswith("battle:join")]
    game.choose(next(i for i in joins if i.endswith(f"@{a.record_id}")))
    for rid in (a.record_id, b.record_id):  # 兩場都開打
        game.world.mutate_siege(rid, lambda x: battle_instance.close_muster(x, _template(game.content), random.Random(0), NOW))
    act = next(o.id for o in game.options() if o.id.startswith("battle:act:"))
    assert "@" not in act  # 參戰之後只有那一場：鈕照舊不帶 @
    game.choose(act)
    one, two = game.world.get_sieges()
    assert game.state.player.name in one.round.pending_actions or one.round_number == 1
    assert two.round.pending_actions == {} and two.participants == {}


def test_two_battles_one_region_join_is_explicit():
    game = go(join(conquest_game("season21"), "huang"), "runan")
    game.now = NOW
    a, b = _two(game)
    joins = [o.id for o in game.options() if o.id.startswith("battle:join")]
    assert joins == [f"battle:join:huang@{a.record_id}", f"battle:join:huang@{b.record_id}"]  # 兩顆各帶 @流水號
    game.choose(joins[1])
    assert game.state.player.name in game.world.get_sieges()[1].participants
    assert game.state.player.name not in game.world.get_sieges()[0].participants
    after = [o for o in game.options() if o.id.startswith("battle:join")]
    assert [o.id for o in after] == ["battle:join:huang"] and not after[0].enabled  # 加入了一場：另一場的鈕不見
    game.choose(f"battle:join:huang@{a.record_id}")  # 另一場的鈕已經不在選單上：不收
    assert game.state.player.name not in game.world.get_sieges()[0].participants
    assert game._battle_choose(f"join:huang@{a.record_id}") == ["（你已經在另一場戰局裡。）"]  # 直接送也不收


def test_season_end_shelves_sieges():
    game = go(join(conquest_game("season21"), "huang"), "runan")
    game.now = NOW
    a, _ = _two(game)
    game.choose(next(o.id for o in game.options() if o.id.endswith(f"@{a.record_id}")))
    game.state.world.ended = True
    game._battle_status(tick=True)
    assert game.world.get_sieges() == []  # 收起來了
    ended = game.world.ended_battle(a.record_id)
    assert ended is not None and ended.unfinished and ended.outcome_side == ""  # 不算勝負、不易手
    titles = [e.title for e in game.state.journal]
    assert any(battle_instance.UNFINISHED_TITLE in t for t in titles)


def test_resume_shifts_siege_deadlines():
    game = conquest_game("season21")
    a, _ = _two(game)
    before = a.muster_deadline_real
    assert game.world.pause_clock(NOW + 10)
    game.world.resume_clock(game.content, NOW + 610)
    assert game.world.get_sieges()[0].muster_deadline_real == pytest.approx(before + 600)


def test_bot_runner_owes_both_battles():
    game = go(join(conquest_game("season21", name="甲某"), "huang"), "runan")
    other = go(join(conquest_game("season21", name="乙某", world=game.world), "huang"), "runan")
    game.now = other.now = NOW
    _template(other.content)  # 兩局各自一份內容
    a, b = _two(game)
    game.choose(next(o.id for o in game.options() if o.id.endswith(f"@{a.record_id}")))
    other.choose(next(o.id for o in other.options() if o.id.endswith(f"@{b.record_id}")))
    for rid in (a.record_id, b.record_id):
        game.world.mutate_siege(rid, lambda x: battle_instance.close_muster(x, _template(game.content), random.Random(0), NOW))
    runner = BotRunner(game.content, game.world, open_characters(), random.Random(1), clock=lambda: NOW)
    assert runner._battle_owes() == frozenset({"甲某", "乙某"})
    assert runner.battle_on()


def test_results_are_delivered_out_of_order():
    """先開的那一場晚收場：補戰報不能只看「比補過的最大流水號大」（ended_battles 以前的前提）。"""
    game = go(join(conquest_game("season21"), "huang"), "runan")
    game.now = NOW
    a, b = _two(game)
    game.choose(next(o.id for o in game.options() if o.id.endswith(f"@{a.record_id}")))

    def _end(x):
        x.phase, x.unfinished, x.end_time = "ended", True, 0.0

    game.world.mutate_siege(b.record_id, _end)  # 後開的先收場
    game._deliver_battle_results()
    assert b.record_id in game.state.player.battle_results_seen
    game.world.mutate_siege(a.record_id, _end)  # 先開的（流水號小）後收場
    game._deliver_battle_results()
    assert a.record_id in game.state.player.battle_results_seen


def test_switch_off_single_battle_unchanged():
    game = go(join(plain_game("season21"), "guan"), "changshe")
    game.now = NOW
    assert game.battles_now() == []
    game.world.start_battle(game.content.battles["changshe_fire"], NOW, 50)
    assert [b.record_id for b in game.battles_now()] == [game.world.get_battle().record_id]
    assert "battle:join:guan" in [o.id for o in game.options()]  # 只有一場：鈕不帶 @
    assert game.world.get_sieges() == []


# ── 原 test_conquest_melee.py（整檔搬進來） ──
# 領地爭奪裁決 22（企劃者 2026-10-21）：兩軍同時攻同一塊中立地＝三方混戰（計畫第四章 Task 11b）。
#
# 中立的守將留著、兩軍都打他；兩軍之間照決戰互打（戰線只算兩軍之間，強攻打得到對面）；一軍打守將的力道乘這一回合開打時戰線往自己偏多少；
# 守將的池子歸零那一回合打守將打得多的那一軍拿下（一樣多看戰線、再一樣照自己的亂數）；回合打完守將沒倒，守住、照舊中立。散人可以助守。

SCORES = {"強攻": 60.0, "固守": 60.0, "奇襲": 60.0}


LOC = "nanyang_road"


def _game_melee(side="guan", name="沈浪", world=None):
    game = go(join(conquest_game("season21", name=name, world=world), side), LOC)
    game.now = NOW
    return game


def _open_melee(game, merged=("guan", "huang"), side="guan"):
    """排一場攻城、此刻開集結（照 world 的路，siege.open_waiting）；回那一場。"""
    slot = announce(game, LOC, side, merged=merged)
    w = game.state.world
    slot.muster_at, slot.at, slot.status = w.time, w.time + 1800, "waiting"
    game._save_season()
    siege.open_waiting(game.world, game.content, NOW)
    game.state.world = game.world.get_season()
    return next(b for b in game.world.get_sieges() if b.siege.slot_id == slot.id)


def _add(game, battle, who: dict[str, str]):
    """名號 → 站哪一格（集結時加入，份量都一樣）。"""
    def fn(b):
        for name, side in who.items():
            battle_instance.join_faction(b, name, side, 300.0, power=100.0, scores=dict(SCORES))
    return game.world.mutate_siege(battle.record_id, fn)


def _start(game, battle):
    """集結截止：照引擎的路開打（Game._tick_siege → _advance_battle_round，守將的池子在這一下照到場人數定）。"""
    game.now = battle.muster_deadline_real + 1
    game._tick_siege(battle)
    return _now(game, battle)


def _now(game, battle):
    return next(b for b in game.world.get_sieges() if b.record_id == battle.record_id)


def _guard(battle):
    return next(c for c in battle.commanders if c.faction == GUARD)


def _round(game, battle, moves: dict[str, str], setup=None, texts: dict[str, tuple[str, int]] | None = None):
    """每個人出一招（三招的名字），texts 是放手一搏（名號 →（字, 成功率））；setup 在送出之前改這一場。結算一回合，收場了就套結果。"""
    d = game._definition_of(battle)
    log: dict[str, list[str]] = {}

    def fn(b):
        if setup is not None:
            setup(b)
        for name, move in moves.items():
            tag = next(o.tag for o in battle_instance.fixed_options(b, d, name) if o.move == move)
            battle_instance.submit_action(b, name, tag)
        for name, (text, rate) in (texts or {}).items():
            tag = next(o.tag for o in battle_instance.options_for(b, d, name) if o.free_text)
            battle_instance.submit_action(b, name, tag, text, rate)
        log["msgs"] = game._advance_battle_round(b, d)

    after = game.world.mutate_siege(battle.record_id, fn)
    if after.phase == "ended":
        game._apply_battle_outcome(after)
        game.state.world = game.world.get_season()
    return after, log.get("msgs", [])


def _big_guard(b, neili=1000.0, cap=1000.0, order=None):
    g = _guard(b)
    g.neili_cap, g.neili = cap, neili
    if order is not None:
        b.orders[GUARD] = order


def test_melee_keeps_the_neutral_guard():
    game = _game_melee()
    battle = _open_melee(game)
    info = battle.siege
    assert info.attackers == ["guan", "huang"] and info.holder is None and info.guard_side == GUARD
    assert battle_instance.melee(battle)
    guards = [c for c in battle.commanders if c.fid.startswith("squad:")]
    assert len(guards) == 1 and guards[0].faction == GUARD
    assert battle_instance.side_names(battle, game._definition_of(battle))[GUARD] == battle_instance.GUARD_SIDE


def test_single_side_neutral_is_not_a_melee():
    game = _game_melee()
    battle = _open_melee(game, merged=(), side="huang")
    assert battle.siege.guard_side == "guan" and not battle_instance.melee(battle)  # 單方攻中立地照舊（守將站另一軍那一格）


def test_guard_pool_follows_the_head_count_at_the_start():
    game = _game_melee()
    battle = _add(game, _open_melee(game), {"甲": "guan", "丙": "guan", "乙": "huang"})
    battle = _start(game, battle)
    per_head = game.content.config.conquest.melee_pool_per_head
    assert battle.phase == "active"
    assert _guard(battle).neili_cap == _guard(battle).neili == pytest.approx(per_head * 3)


def test_both_armies_hit_the_guard():
    game = _game_melee()
    battle = _start(game, _add(game, _open_melee(game), {"甲": "guan", "乙": "huang"}))
    focus = game.content.config.battle.focus_per_attacker
    after, msgs = _round(game, battle, {"甲": "強攻", "乙": "強攻"}, setup=lambda b: _big_guard(b))
    assert _guard(after).neili == pytest.approx(1000 - 2 * focus)  # 戰線在中線：兩軍各打 focus_per_attacker
    text = "\n".join(msgs)
    assert "官軍的強攻撲向" in text and "黃巾軍的強攻撲向" in text


def test_the_line_scales_how_hard_an_army_hits_the_guard():
    game = _game_melee()
    battle = _start(game, _add(game, _open_melee(game), {"甲": "guan", "乙": "huang"}))
    focus = game.content.config.battle.focus_per_attacker

    def setup(b):
        _big_guard(b)
        b.trend = 70  # 這一回合開打時戰線往官軍偏 20：官軍打守將 ×1.4

    after, _ = _round(game, battle, {"甲": "強攻", "乙": "固守"}, setup=setup)
    assert _guard(after).neili == pytest.approx(1000 - focus * 70 / 50)


def test_strong_attack_still_hits_the_other_army():
    game = _game_melee()
    battle = _start(game, _add(game, _open_melee(game), {"甲": "guan", "乙": "huang"}))

    def setup(b):
        _big_guard(b, order="奇襲")  # 守將不出強攻：乙挨的集火只會是官軍的
        b.marked["乙"] = b.act_index  # 乙這一幕顯眼：對面的強攻集火打得到他

    after, _ = _round(game, battle, {"甲": "強攻", "乙": "奇襲"}, setup=setup)
    assert after.trend > 50  # 強攻剋奇襲：戰線往官軍推（戰線只算兩軍之間）
    assert after.participants["乙"].hurt_taken > 0  # 官軍的強攻集火打到黃巾顯眼的人


def test_the_line_moving_far_does_not_end_a_melee():
    game = _game_melee()
    battle = _start(game, _add(game, _open_melee(game), {"甲": "guan", "乙": "huang"}))

    def setup(b):
        _big_guard(b, order="固守")
        b.trend = 95

    after, _ = _round(game, battle, {"甲": "固守", "乙": "固守"}, setup=setup)
    assert after.phase == "active"  # 偏離中線 40 以上照打：三方混戰只看守將倒下或回合打完


def test_last_blow_takes_the_block():
    game = _game_melee()
    battle = _start(game, _add(game, _open_melee(game), {"甲": "guan", "乙": "huang"}))
    after, msgs = _round(game, battle, {"甲": "強攻", "乙": "固守"}, setup=lambda b: _big_guard(b, neili=10.0, order="固守"))
    assert after.phase == "ended" and after.round_number == 1  # 守將倒下那一回合當場收場
    guard = _guard(after)
    assert guard.fallen_round == 1 and guard.felled_by == "甲"
    assert after.siege.blow == "guan" and after.participants["甲"].slew == 1
    assert any("甲" in m and "最後一刀" in m for m in msgs)
    w = game.state.world
    assert conquest.holder(w, game.content, LOC) == "guan"
    assert any("甲" in r.text and "最後一刀" in r.text for r in w.rumors if r.layer == "world")
    ended = game.world.ended_battle(after.record_id)
    assert ended.outcome_side == "guan" and "最後一刀" in ended.outcome_title and "南陽官道" in ended.outcome_title
    assert "甲" in ended.outcome_reason and "最後一刀" in ended.outcome_reason


def test_both_armies_reach_zero_in_one_round_more_damage_wins():
    game = _game_melee()
    battle = _start(game, _add(game, _open_melee(game), {"甲": "guan", "丙": "guan", "乙": "huang"}))
    after, _ = _round(game, battle, {"甲": "強攻", "丙": "強攻", "乙": "強攻"}, setup=lambda b: _big_guard(b, neili=20.0, order="固守"))
    assert after.phase == "ended" and after.siege.blow == "guan"  # 官軍兩人打 30、黃巾一人打 15：官軍拿下
    assert _guard(after).felled_by in ("甲", "丙")
    assert conquest.holder(game.state.world, game.content, LOC) == "guan"


def test_blow_side_tie_breaks():
    armies = ("guan", "huang")
    assert battle_instance.blow_side({"guan": 10.0, "huang": 30.0}, 80, armies, "x") == "huang"  # 打得多的那一軍
    assert battle_instance.blow_side({"guan": 15.0, "huang": 15.0}, 60, armies, "x") == "guan"  # 一樣多：戰線偏向誰
    assert battle_instance.blow_side({"guan": 15.0, "huang": 15.0}, 40, armies, "x") == "huang"
    coin = {battle_instance.blow_side({"guan": 15.0, "huang": 15.0}, 50, armies, f"seed{i}") for i in range(20)}
    assert coin == {"guan", "huang"}  # 戰線也在中線：照自己的亂數擲
    assert battle_instance.blow_side({"guan": 15.0, "huang": 15.0}, 50, armies, "seed1") == \
        battle_instance.blow_side({"guan": 15.0, "huang": 15.0}, 50, armies, "seed1")  # 同一個種子同一個結果


def test_same_damage_same_round_follows_the_line():
    game = _game_melee()
    battle = _start(game, _add(game, _open_melee(game), {"甲": "guan", "乙": "huang"}))

    def setup(b):
        _big_guard(b, neili=8.0, order="固守")
        b.trend = 50

    after, _ = _round(game, battle, {"甲": "強攻", "乙": "強攻"}, setup=setup)
    seed = f"最後一刀|{after.battle_id}|{after.record_id}|1"
    assert after.siege.blow == battle_instance.blow_side({"guan": 1.0, "huang": 1.0}, 50, ("guan", "huang"), seed)


def test_guard_survives_and_the_block_stays_neutral():
    game = _game_melee()
    battle = _start(game, _add(game, _open_melee(game), {"甲": "guan", "乙": "huang"}))
    rounds = battle_instance.total_rounds(game._definition_of(battle))
    after = battle
    for _ in range(rounds):
        after, _ = _round(game, after, {"甲": "固守", "乙": "固守"})
    assert after.phase == "ended" and after.round_number == rounds and _guard(after).fallen_round is None
    w = game.state.world
    assert conquest.holder(w, game.content, LOC) is None  # 守將守住：照舊中立
    ended = game.world.ended_battle(after.record_id)
    assert ended.outcome_side == GUARD and "守軍守住南陽官道" in ended.outcome_title
    assert any("守住" in r.text and "南陽官道" in r.text for r in w.rumors if r.layer == "world")
    found = next(s for s in w.conquest.schedule if s.id == after.siege.slot_id)
    assert found.status == "done" and found.winner is None


def test_ranger_can_help_the_guard_in_a_melee():
    game = _game_melee()
    battle = _open_melee(game)
    ranger = _game_melee(side=None, name="散某", world=game.world)
    enlists = {o.id for o in ranger.options() if o.id.startswith("battle:enlist:")}
    assert enlists == {"battle:enlist:guan", "battle:enlist:huang", f"battle:enlist:{GUARD}"}
    label = next(o.label for o in ranger.options() if o.id == f"battle:enlist:{GUARD}")
    assert "助守" in label and "守軍" in label
    ranger.choose(f"battle:enlist:{GUARD}")
    battle = _now(game, battle)
    assert battle.participants["散某"].faction == GUARD
    battle = _start(game, _add(game, battle, {"甲": "guan", "乙": "huang"}))  # 裁決 23：只有一軍到場會轉回單方攻中立地，這裡要兩軍都有人
    assert battle_instance.melee(battle) and battle.participants["散某"].faction == GUARD  # 集結結束不被改分到兩軍
    ranger.now = game.now
    acts = [o.label for o in ranger.options() if o.id.startswith("battle:act:")]
    assert len(acts) == 3 and not any(" 分" in a or battle_instance.ORDER_MARK in a for a in acts)  # 份量不推戰線：不寫分數與將令
    focus = game.content.config.battle.focus_per_attacker
    per = game.content.config.battle.generals.guard_per

    def setup(b):
        _big_guard(b, order="固守")
        b.participants["散某"].role = ""  # 不是盾陣：擋 guard_per

    after, _ = _round(game, battle, {"甲": "強攻", "乙": "固守", "散某": "固守"}, setup=setup)
    assert _guard(after).neili == pytest.approx(1000 - focus * (1 - per))  # 助守的固守替守將擋一成
    assert after.participants["散某"].hurt_taken == pytest.approx(focus * per)


def test_helper_gamble_mends_the_guard():
    game = _game_melee()
    battle = _open_melee(game)
    ranger = _game_melee(side=None, name="散某", world=game.world)
    ranger.choose(f"battle:enlist:{GUARD}")
    battle = _start(game, _add(game, _now(game, battle), {"甲": "guan", "乙": "huang"}))
    gen = game.content.config.battle.generals
    after, msgs = _round(game, battle, {"甲": "固守", "乙": "固守"}, setup=lambda b: _big_guard(b, neili=500.0, order="固守"),
                         texts={"散某": ("死守寨門", 100)})
    assert _guard(after).neili == pytest.approx(500 + 1000 * gen.hit_base)  # 成功率 100：風險 0，補回 hit_base
    assert after.trend == battle.trend  # 助守的人不推戰線（兩軍都固守，戰線不動）
    assert any("散某" in m and "補回" in m for m in msgs)


# ── 裁決 23（PM 2026-10-21）：集結結束只有一軍到場，轉回單方攻中立地 ──


def _squad(battle):
    """守將那一個人（隊伍當的，fid 是「squad:…」），不管他站哪一格。"""
    return next(c for c in battle.commanders if c.fid.startswith("squad:"))


def test_one_army_alone_turns_back_into_a_single_attack_on_neutral():
    game = _game_melee()
    battle = _start(game, _add(game, _open_melee(game), {"甲": "guan", "丙": "guan"}))  # 黃巾一個人都沒來
    assert battle.phase == "active"
    assert not battle_instance.melee(battle)  # 不是三方混戰了
    info = battle.siege
    assert info.attackers == ["guan"] and info.holder is None and info.guard_side == "huang"  # 同單方攻中立地：守將站沒來的那一軍那一格
    assert battle_instance.neutral_guard(battle) == "huang"
    names = battle_instance.side_names(battle, game._definition_of(battle))
    assert names["huang"] == battle_instance.GUARD_SIDE  # FB-540：寫給人看的是「守軍」
    assert GUARD not in battle_instance.fields(battle, game._definition_of(battle))
    # 守將跟單方攻中立地一模一樣（同一個人、同一個池子；不是三方混戰那一個小池子）
    expected = siege.guard_squad(game.state.world, game.content, LOC, "huang")
    assert _squad(battle).model_dump() == expected.model_dump()
    assert _squad(battle).neili_cap == game.content.config.battle.generals.pool[0]
    assert battle.orders.get("huang") in battle_instance.MOVES  # 守將照單方的喊令（不是 GUARD 那一格）
    assert GUARD not in battle.orders


def test_the_other_army_alone_also_turns_back():
    game = _game_melee(side="huang")
    battle = _start(game, _add(game, _open_melee(game, side="huang"), {"乙": "huang"}))  # 官軍沒來
    info = battle.siege
    assert not battle_instance.melee(battle)
    assert info.attackers == ["huang"] and info.guard_side == "guan"
    assert _squad(battle).faction == "guan"


def test_the_lone_army_takes_the_block_by_the_line_without_felling_the_guard():
    game = _game_melee()
    battle = _start(game, _add(game, _open_melee(game), {"甲": "guan"}))

    def setup(b):
        _squad(b).score = 1.0  # 守將別把戰線推回來：這一條只看「過了門檻就拿下」
        b.trend = 95

    after, msgs = _round(game, battle, {"甲": "固守"}, setup=setup)
    assert after.phase == "ended"  # 偏離中線 40 以上當場收場（單方攻中立地的老規矩）
    assert _squad(after).fallen_round is None  # 不用把守將打倒
    w = game.state.world
    assert conquest.holder(w, game.content, LOC) == "guan"
    texts = [r.text for r in w.rumors if r.layer == "world"]
    assert any("南陽官道落入" in t for t in texts) and not any("最後一刀" in t for t in texts)  # 天下大事照單方攻中立地的寫
    ended = game.world.ended_battle(after.record_id)
    assert ended.outcome_side == "guan" and ended.outcome_title == "官軍大勝，拿下南陽官道"
    found = next(s for s in w.conquest.schedule if s.id == after.siege.slot_id)
    assert found.status == "done" and found.winner == "guan"


def test_the_lone_army_does_not_get_a_harder_fight_than_attacking_alone():
    # 另一軍沒來算棄權：到場的那一軍，比只有自己宣戰時（單方攻中立地）不能更難。同一個局面兩種打法，結果要一樣。
    game = _game_melee()
    melee_battle = _start(game, _add(game, _open_melee(game), {"甲": "guan"}))
    other = _game_melee(world=None)
    single = _start(other, _add(other, _open_melee(other, merged=(), side="guan"), {"甲": "guan"}))
    assert not battle_instance.melee(single)
    assert melee_battle.siege.attackers == single.siege.attackers and melee_battle.siege.guard_side == single.siege.guard_side
    assert _squad(melee_battle).model_dump() == _squad(single).model_dump()
    assert melee_battle.orders == single.orders

    def setup(b):
        _squad(b).score = 1.0
        b.trend = 95

    for g, b in ((game, melee_battle), (other, single)):
        after, _ = _round(g, b, {"甲": "固守"}, setup=setup)
        assert after.phase == "ended" and conquest.holder(g.state.world, g.content, LOC) == "guan"


def test_the_guard_holds_a_lone_army_by_the_line():
    game = _game_melee()
    battle = _start(game, _add(game, _open_melee(game), {"甲": "guan"}))

    def setup(b):
        b.trend = 5  # 戰線壓在守將那一頭

    after, _ = _round(game, battle, {"甲": "固守"}, setup=setup)
    assert after.phase == "ended"
    assert conquest.holder(game.state.world, game.content, LOC) is None  # 照舊中立
    texts = [r.text for r in game.state.world.rumors if r.layer == "world"]
    assert any("守住" in t and "南陽官道" in t for t in texts) and not any("兩軍都沒能" in t for t in texts)  # 單方的 HELD_LINE


def test_both_armies_present_is_still_a_melee():
    game = _game_melee()
    battle = _start(game, _add(game, _open_melee(game), {"甲": "guan", "乙": "huang"}))  # 各只到一個人也照三方混戰
    assert battle_instance.melee(battle)
    assert battle.siege.attackers == ["guan", "huang"] and battle.siege.guard_side == GUARD
    assert _guard(battle).faction == GUARD and _guard(battle).neili_cap == game.content.config.conquest.melee_pool_per_head * 2


def test_helpers_of_the_guard_follow_the_guard_when_it_turns_back():
    game = _game_melee()
    battle = _open_melee(game)
    ranger = _game_melee(side=None, name="散某", world=game.world)
    ranger.choose(f"battle:enlist:{GUARD}")  # 集結時助守【守軍】
    battle = _start(game, _add(game, _now(game, battle), {"甲": "guan"}))
    assert not battle_instance.melee(battle)
    assert battle.participants["散某"].faction == "huang"  # 助守的人站守將那一格（單方攻中立地的助守）
    assert battle.participants["甲"].faction == "guan"
    ranger.now = game.now
    assert any(o.id.startswith("battle:act:") for o in ranger.options())  # 還能出招
    # 助守的固守替守將擋，跟單方攻中立地的助守一樣（戰線上算進守將那一邊）
    after, _ = _round(game, battle, {"甲": "固守", "散某": "固守"})
    assert after.participants["散某"].faction == "huang"


def test_a_ranger_who_enlisted_for_the_only_army_counts_as_present():
    game = _game_melee()
    battle = _open_melee(game)
    ranger = _game_melee(side=None, name="散某", world=game.world)
    ranger.choose("battle:enlist:huang")  # 只有一個散人投效黃巾，官軍沒人
    battle = _start(game, _now(game, battle))
    assert battle.phase == "active" and not battle_instance.melee(battle)
    assert battle.siege.attackers == ["huang"] and battle.siege.guard_side == "guan"
    assert battle.participants["散某"].faction == "huang"


def test_nobody_shows_up_is_still_void_even_with_a_guard_helper():
    game = _game_melee()
    battle = _open_melee(game)
    ranger = _game_melee(side=None, name="散某", world=game.world)
    ranger.choose(f"battle:enlist:{GUARD}")  # 只有助守的人，兩軍一個人都沒來
    battle = _start(game, _now(game, battle))
    assert battle.phase == "ended" and battle.unfinished and battle.siege.void == "absent"  # 裁決 19：照舊作罷
    w = game.state.world
    found = next(s for s in w.conquest.schedule if s.id == battle.siege.slot_id)
    assert found.status == "void" and conquest.holder(w, game.content, LOC) is None
    assert len([n for n in w.conquest.day_log if n.void == "absent" and n.loc == LOC]) == 2  # 每一個攻方一筆
    assert not any("作罷" in r.text for r in w.rumors if r.layer == "world")


def test_the_absent_army_cannot_come_late_and_the_scene_says_so():
    game = _game_melee()
    battle = _start(game, _add(game, _open_melee(game), {"甲": "guan"}))
    assert siege.join_problem(game.content, battle.siege, "huang", "huang") is not None  # 棄權的那一軍晚到也插不上手
    assert siege.slots(battle.siege, "guan") == ["guan"]
    assert siege.slots(battle.siege, None) == ["guan", "huang"]  # 散人可以投效到場那一軍、或助守
    assert battle.siege.absent == "huang"
    line = siege.scene_line(game.content, battle.siege, battle)
    assert line.startswith(siege.SCENE_LINE.format(attackers="官軍", place="南陽官道", defender=_squad(battle).name))  # 場景照單方攻中立地的寫
    assert siege.ABSENT_SCENE_LINE.format(absent="黃巾軍") in line  # 再加一句沒到場的是誰


# ── 原 test_conquest_letter.py（整檔搬進來） ──
# 翻地與爭搶：戰書（輿圖簡化設計 4.4、第九章第 13 條；PM 2026-10-20 第 1、2 條）——這一週在任的第 4 階、自己那一邊的進度到門檻、一邊一天
# 一張、時段挑最近的、下了那一塊凍結到打完、另一邊可以併進同一場；攻城戰打贏照推滿易手（分紅、冷卻）、打輸砍半；換天只作罷沒開成的；
# 投票與 22:00 公告結算拿掉了；軍令照「此刻進度最高的那一塊」列與記；救場。
#
# 合進區塊表 v3（輿圖第三版第 2 批，feature/territory-conquest b9ee3c9c）之後嵩山深處是官軍的、黃巾開季碰不到荒丘：官軍的第二塊目標從嵩山深處換成汝南荒野，兩軍併進同一場的地方從荒丘換成汝南荒野；斷言不動。

def _game_letter(side="guan", loc="hilltop_wilds", name="沈浪", world=None, seated=True):
    game = go(join(conquest_game("season21", name=name, world=world), side), loc)
    game.now = NOW
    if world is not None:
        game.state.world = world.get_season()
    if seated:
        game.state.player.qualified = True
        game.state.world.seats[side] = [name]
    return game


def _fill(game, loc, side, value, who="先鋒"):
    conquest.push(game.state.world, game.content, loc, side, who, value, "attack")


def _open_letter(game, slot):
    w = game.state.world
    slot.muster_at, slot.at, slot.status = w.time, w.time + 1800, "waiting"
    game._save_season()
    siege.open_waiting(game.world, game.content, NOW)
    game.state.world = game.world.get_season()


def _end_letter(game, trend):
    battle = next(b for b in game.world.get_sieges() if b.phase != "ended")

    def _close(b):
        b.phase, b.trend, b.end_time = "ended", trend, game.state.world.time

    game._apply_battle_outcome(game.world.mutate_siege(battle.record_id, _close))
    game.state.world = game.world.get_season()


def test_a_seated_rank4_letters_the_nearest_slot_and_freezes_the_block():
    game = _game_letter()
    w, c = game.state.world, game.content
    assert ranks.rank_of(game.state) == ranks.SEAT_RANK
    _fill(game, "hilltop_wilds", "guan", 60)
    want = conquest_day.next_slot(w, c, NOW)
    msgs = game.conquest_letter("hilltop_wilds")
    (slot,) = game.state.world.conquest.schedule
    assert (slot.loc, slot.attackers, slot.by, slot.reasons) == ("hilltop_wilds", ["guan"], {"guan": "letter"}, {"guan": "沈浪"})
    assert (slot.key, slot.minute) == want and slot.status == "planned"
    assert slot.muster_at == pytest.approx(slot.at - c.config.conquest.muster_minutes * 60)
    assert any("下了戰書" in m and "荒丘" in m for m in msgs)
    w = game.state.world
    assert conquest.push_problem(w, c, "guan", "hilltop_wilds", "attack") == conquest.WHY_FROZEN
    assert any(r.text.startswith("沈浪替官軍下了戰書") for r in w.rumors)  # 只有真人會下戰書：具名
    assert w.conquest.day_log[-1].by == "letter" and w.conquest.letter_days["guan"] == conquest_day.day_key(NOW, c.config)
    assert any(e.title == "下戰書" for e in game.state.journal)
    _fill(game, "runan_wilds", "guan", 70)
    again = game.conquest_letter("runan_wilds")
    assert "今天已經下過戰書了" in again[0] and len(game.state.world.conquest.schedule) == 1  # 一邊一天一張


def test_only_a_seated_rank4_can_letter_and_only_past_the_threshold():
    game = _game_letter(seated=False)
    _fill(game, "hilltop_wilds", "guan", 80)
    assert game.conquest_letter("hilltop_wilds") == ["（只有這一週在任的第 4 階才能下戰書。）"]
    seated = _game_letter()
    _fill(seated, "hilltop_wilds", "guan", 59)
    assert seated.letter_problem("hilltop_wilds") == "進度要到 60 才能下戰書（此刻 59）"
    assert seated.state.world.conquest.schedule == []


def test_the_other_side_joins_the_same_siege():
    game = _game_letter(loc="runan_wilds")
    _fill(game, "runan_wilds", "guan", 60)
    _fill(game, "runan_wilds", "huang", 65)
    game.conquest_letter("runan_wilds")
    game._save_season()
    rival = _game_letter(side="huang", loc="runan_wilds", name="張角徒", world=game.world)
    msgs = rival.conquest_letter("runan_wilds")
    (slot,) = rival.state.world.conquest.schedule
    assert slot.attackers == ["guan", "huang"] and slot.by == {"guan": "letter", "huang": "letter"}
    assert any("併進" in m for m in msgs)
    assert any("也下了戰書" in r.text for r in rival.state.world.rumors)


def test_a_siege_win_flips_with_payouts_and_cooling():
    game = _game_letter(side="huang", loc="nanyang_road")
    _fill(game, "nanyang_road", "huang", 70, who="沈浪")
    game.conquest_letter("nanyang_road")
    slot = game.state.world.conquest.schedule[0]
    _open_letter(game, slot)
    battle = game.world.get_sieges()[0]
    assert battle.trend_start == 46  # 進度 70：往黃巾偏 4（戰局以官軍為正向）
    game.choose(next(o.id for o in game.options() if o.id.startswith("battle:join:huang")))
    _end_letter(game, 10)
    w, c = game.state.world, game.content
    assert conquest.holder(w, c, "nanyang_road") == "huang" and conquest.cooling(w, c, "nanyang_road")
    assert conquest.bars(w, "nanyang_road") == {}
    (pay,) = [p for p in w.conquest.payouts if p.name == "沈浪"]
    assert (pay.silver, pay.exp, pay.fame, pay.top) == (200, 300, 20, True)
    assert conquest.push_problem(w, c, "huang", "nanyang_road", "hold") not in conquest.FROZEN_WHY.values()  # 打完就解凍（冷卻另算）


def test_a_siege_loss_halves_the_bar_and_unfreezes():
    game = _game_letter(side="huang", loc="nanyang_road")
    _fill(game, "nanyang_road", "huang", 80)
    game.conquest_letter("nanyang_road")
    _open_letter(game, game.state.world.conquest.schedule[0])
    _end_letter(game, 60)  # 守將那一邊佔上風
    w, c = game.state.world, game.content
    assert conquest.holder(w, c, "nanyang_road") is None and conquest.bar(w, "nanyang_road", "huang") == 40
    assert conquest.push_problem(w, c, "huang", "nanyang_road", "attack") is None


def test_day_turn_only_voids_letters_that_never_opened():
    game = _game_letter()
    w, c = game.state.world, game.content
    key = conquest_day.day_key(NOW, c.config)
    w.conquest.settled_key = key
    stale = announce(game, "hilltop_wilds", "guan")
    stale.key = key
    tomorrow = announce(game, "runan_wilds", "guan")
    tomorrow.key = key + 1  # 21:30 之後下的戰書排在下一天
    game.now = conquest_day.key_start(key + 1, c.config) + 60
    msgs = game._conquest_tick(save=False)
    assert stale.status == "void" and tomorrow.status == "planned"
    assert any("時辰已過" in m for m in msgs)
    assert [s.id for s in game.state.world.conquest.schedule] == [tomorrow.id]
    assert game.state.world.conquest.settled_key == key + 1


def test_votes_and_the_22_settle_are_gone():
    assert "conquest_vote" not in server.MAIN_ACTIONS and "conquest_letter" in server.MAIN_ACTIONS
    assert "conquest_settle_now" not in server.ADMIN_ACTIONS
    assert {"conquest_progress", "admin_conquest_letter"} <= set(server.ADMIN_ACTIONS)  # FB-609：管理者那一個改名，不蓋掉玩家的
    assert not hasattr(Game, "conquest_vote")
    assert not any(hasattr(conquest_day, name) for name in ("tally", "plan", "merge", "settle", "settle_now", "commander_picks"))
    assert "conquest_letter" not in inspect.getsource(bot_policy)  # 假人不下戰書


def test_orders_list_and_credit_the_highest_block():
    game = _game_letter(loc="runan_wilds")
    s, c = game.state, game.content
    order = Order(id="t:guan:siege:yingru", template="siege", faction="guan", week=orders.period_of(s, c), front="yingru",
                  quota=6, text="（測試）")
    s.world.orders.append(order)
    _fill(game, "hilltop_wilds", "guan", 30)
    _fill(game, "runan_wilds", "guan", 10)
    assert orders.siege_places(c, "guan", "yingru", s.world) == ["hilltop_wilds"]
    how = atlas.siege_how(s, c, order)
    assert "荒丘" in how and "汝南荒野" not in how
    win_sortie(game)  # 在汝南荒野打贏：不是最高的那一塊，記不到
    assert s.player.name not in order.progress
    go(game, "hilltop_wilds")
    win_sortie(game)
    assert order.progress.get(s.player.name) == 1


def test_admin_tools_flip_and_letter():
    game = _game_letter()
    game.state.player.name = "Rayal"
    w, c = game.state.world, game.content
    game.admin_conquest_progress("hilltop_wilds", "guan", 100)
    w = game.state.world
    assert conquest.holder(w, c, "hilltop_wilds") == "guan" and conquest.cooling(w, c, "hilltop_wilds")
    game.admin_conquest_letter("runan_wilds", "guan")
    (slot,) = game.state.world.conquest.schedule
    assert slot.loc == "runan_wilds" and slot.muster_at == pytest.approx(game.state.world.time)
    assert "guan" not in game.state.world.conquest.letter_days  # 不算那一邊今天的那一張


# ── 原 test_conquest_fb540_guard.py（整檔搬進來） ──
# FB-540：單方攻中立地時，守將站的是另一軍的那一格（SiegeInfo.guard_side），畫面、戰報、天下大事卻照那一格的陣營寫成那一軍
# （散人的鈕「臨時投效【官軍】」、陣容「〔官軍〕主將…（守將）」、幕文字「漢家的旗」、論功「官軍首功…」、替守將助守加了官軍人物的情誼）。
#
# 守中立地的那一邊寫成中立的守軍（battle_instance.GUARD_SIDE），不冠任何一軍；散人助守的鈕寫「助守」；助守中立地不加任何一軍人物的
# 情誼（PM 2026-10-21：中立守軍不是哪一軍）。陣營佔著的區塊、兩軍同時搶同一塊中立地，照舊寫兩軍的名字。字待 joy 潤。

PLACE = "hilltop_wilds"  # 荒丘：還沒人佔的中立地（QA 那一場：黃巾攻荒丘，守將站官軍那一格）


def _game_fb540guard(side, name, world=None, loc=PLACE):
    game = go(join(conquest_game("season21", name=name, world=world), side), loc)
    game.now = NOW
    return game


def _open_fb540guard(game, slot):
    """把這一場排到此刻開集結（半小時後開打），照 world 的路開（同 test_conquest_siege._open）。"""
    w = game.state.world
    slot.muster_at, slot.at, slot.status = w.time, w.time + 1800, "waiting"
    game._save_season()
    siege.open_waiting(game.world, game.content, NOW)
    game.state.world = game.world.get_season()
    return next(b for b in game.world.get_sieges() if b.siege.slot_id == slot.id)


def _neutral(attacker="huang", guard="guan"):
    """attacker 攻還沒人佔的荒丘：守將站 guard 那一格；散人散六、攻方的人甲一。"""
    them = _game_fb540guard(attacker, "甲一")
    battle = _open_fb540guard(them, announce(them, PLACE, attacker))
    assert battle.siege.holder is None and battle.siege.guard_side == guard
    ranger = _game_fb540guard(None, "散六", world=them.world)
    return them, ranger, battle


def _latest(game, battle):
    return next(b for b in game.world.get_sieges() if b.record_id == battle.record_id)


def _start_fb540guard(game, battle, trend: int):
    """集結結束、開打，戰局停在 trend（高於 50 是官軍那一格佔上風）。"""
    definition = game._definition_of(battle)

    def _go(b):
        battle_instance.close_muster(b, definition, random.Random(0), NOW)
        b.trend = trend

    return game.world.mutate_siege(battle.record_id, _go)


def _end_fb540guard(game, battle, trend: int):
    """收場（戰局停在 trend），照收場那一下的路套結果（同 test_conquest_siege._end）。"""
    def _close(b):
        b.phase, b.trend, b.end_time = "ended", trend, game.state.world.time

    after = game.world.mutate_siege(battle.record_id, _close)
    game._apply_battle_outcome(after)
    game.state.world = game.world.get_season()
    return after


@pytest.mark.parametrize(("attacker", "guard", "army"), [("huang", "guan", "官軍"), ("guan", "huang", "黃巾軍")])
def test_ranger_buttons_say_help_guard(attacker, guard, army):
    _, ranger, battle = _neutral(attacker, guard)
    labels = {o.id: o.label for o in ranger.options() if o.id.startswith("battle:enlist:")}
    help_guard = labels[f"battle:enlist:{guard}"]
    assert "助守" in help_guard and army not in help_guard  # 修前「臨時投效【官軍】（只算這一場）」
    other = "黃巾軍" if attacker == "huang" else "官軍"
    assert labels[f"battle:enlist:{attacker}"] == f"臨時投效【{other}】（只算這一場）"  # 攻方那一顆照舊
    msgs = ranger.choose(f"battle:enlist:{guard}")
    assert ranger.world.get_sieges()[0].participants["散六"].faction == guard  # 規則照舊：站守將那一格
    assert not any(army in m for m in msgs) and any("助守" in m for m in msgs)
    after = {o.id: o.label for o in ranger.options() if o.id.startswith("battle:enlist:")}
    assert "助守" in after[f"battle:enlist:{guard}"] and army not in after[f"battle:enlist:{guard}"]
    scene = ranger._battle_scene_text(_latest(ranger, battle), ranger._definition_of(battle))
    assert army not in scene  # 修前「官軍：主將荒丘刀客（守將）」「你已臨時投效【官軍】」
    assert battle_instance.GUARD_SIDE in scene


def test_fight_screen_names_the_guard_side_as_the_garrison():
    them, ranger, battle = _neutral()
    ranger.choose("battle:enlist:guan")
    them.choose("battle:join:huang")
    b = _start_fb540guard(ranger, battle, 70)  # 守將那一格（官軍那一格）佔上風
    definition = ranger._definition_of(b)
    scene = ranger._battle_scene_text(b, definition)
    assert "官軍" not in scene and "漢家" not in scene  # 修前「〔官軍〕主將荒丘刀客（守將）」「寨牆上的旗一面面換成了漢家的」
    assert f"〔{battle_instance.GUARD_SIDE}〕" in scene  # 陣容那一行
    gauge = ranger.battle_gauge()
    assert "官軍" not in gauge["caption"]
    assert gauge["left"]["name"] == battle_instance.GUARD_SIDE and gauge["right"]["name"] == "黃巾軍"
    b = _start_fb540guard(ranger, battle, 30)  # 攻方佔上風：那一句也不寫官軍
    text = battle_instance.act_text(b, definition)
    assert "官軍" not in text and "黃巾" in text
    for g in (ranger, them):  # 打一回合：回合那一句照守軍寫
        g.choose(next(o.id for o in g.options() if o.id.startswith("battle:act:")))
    after = _latest(ranger, battle)
    assert after.round_number == 1
    assert "官軍" not in "\n".join(after.narrative_log)  # 修前「這一回合官軍佔了上風…官軍的武藝更勝一籌」
    assert "官軍" not in ranger._battle_scene_text(after, definition)


def test_reports_and_merit_name_the_garrison_without_army_affinity():
    them, ranger, battle = _neutral()
    ranger.choose("battle:enlist:guan")
    them.choose("battle:join:huang")

    def _acted(b):
        for p in b.participants.values():
            p.acted_rounds = 5

    _start_fb540guard(ranger, battle, 50)
    ranger.world.mutate_siege(battle.record_id, _acted)
    ended = _end_fb540guard(ranger, _latest(ranger, battle), 70)  # 守將那一格守住
    assert conquest.holder(ranger.state.world, ranger.content, PLACE) is None
    assert ended.outcome_side == "guan"  # 規則照舊：守將那一格贏
    mine = next(r for r in ranger.state.battles if r.battle_ref == battle.record_id)
    notes = "\n".join(mine.notes)
    assert "情誼" not in notes  # 修前「皇甫嵩、朱儁、曹操…聽說了這件事，情誼 +2。」（PM：助守中立地不加任何一軍人物的情誼）
    assert "官軍" not in notes  # 修前「在官軍排第 1／1」「你是官軍這一仗的首功」
    assert mine.side == battle_instance.GUARD_SIDE and f"在{battle_instance.GUARD_SIDE}排第 1" in notes
    entry = next(e for e in ranger.state.journal if e.battle_id == mine.id)
    assert "官軍" not in entry.tag and "官軍" not in "\n".join(entry.lines)
    rumors = [r.text for r in ranger.state.world.rumors if "論功" in r.text]
    assert rumors and not any("官軍" in t for t in rumors)  # 修前「攻城・荒丘論功：官軍首功散六，黃巾軍首功甲一。」
    assert any(f"{battle_instance.GUARD_SIDE}首功散六" in t for t in rumors)
    them.state.world = them.world.get_season()
    them._deliver_battle_results()
    theirs = next(r for r in them.state.battles if r.battle_ref == battle.record_id)
    assert theirs.opponent == battle_instance.GUARD_SIDE  # 攻方的戰報：對手是守軍，不是官軍


def test_held_block_keeps_army_names():
    """陣營佔著的區塊（官軍佔南陽官道，黃巾來攻）：沒有守將，兩軍照舊寫自己的名字。"""
    them = _game_fb540guard("huang", "甲一", loc="nanyang_road")
    conquest.set_control(them.state.world, them.content, "nanyang_road", "guan")
    battle = _open_fb540guard(them, announce(them, "nanyang_road", "huang"))
    assert battle.siege.holder == "guan" and battle.siege.guard_side is None
    ranger = _game_fb540guard(None, "散六", world=them.world, loc="nanyang_road")
    labels = {o.id: o.label for o in ranger.options() if o.id.startswith("battle:enlist:")}
    assert labels == {"battle:enlist:guan": "臨時投效【官軍】（只算這一場）", "battle:enlist:huang": "臨時投效【黃巾軍】（只算這一場）"}
    assert battle_instance.side_names(battle, them._definition_of(battle)) == {"guan": "官軍", "huang": "黃巾軍"}


# ── 原 test_conquest_fb542_543.py（整檔搬進來） ──
# 領地爭奪第二批複驗開的兩張單（dev/conquest-2c）。
#
# FB-542：放手一搏點名守將，以前要照抄顯示名「劫道響馬（守將）」才算；只寫守將的名字本身（隊伍名「劫道響馬」）也要算點名到守將。
# 三方混戰與單方攻中立地（含裁決 23 轉回單方的那一場）都一樣；只寫一個字、或只是隊伍名的一部分、或隊伍名是另一個人名字的一部分，
# 照原本的規則判斷（不算）。
# FB-543：單方攻中立地時，守將那一格是另一軍的 id；另一軍站在那一區旁觀的人（沒參戰）的場景不能把守將的將令當成自己這邊的令。
# 助守的人（站在守將那一格）看得到令（他們的鈕本來就寫「主將令」）。字待 joy 潤。

LOC_fb542543 = "nanyang_road"  # 南陽官道：守將劫道響馬（守將）


PLACE_fb542543 = "hilltop_wilds"  # 荒丘：守將荒丘刀客（守將）


SQUAD = "劫道響馬"


def _game_fb542543(side="guan", name="沈浪", world=None, loc=LOC_fb542543):
    game = go(join(conquest_game("season21", name=name, world=world), side), loc)
    game.now = NOW
    return game


def _open_fb542543(game, merged=("guan", "huang"), side="guan", loc=LOC_fb542543):
    """排一場攻城、此刻開集結（照 world 的路，siege.open_waiting）；回那一場。"""
    slot = announce(game, loc, side, merged=merged)
    w = game.state.world
    slot.muster_at, slot.at, slot.status = w.time, w.time + 1800, "waiting"
    game._save_season()
    siege.open_waiting(game.world, game.content, NOW)
    game.state.world = game.world.get_season()
    return next(b for b in game.world.get_sieges() if b.siege.slot_id == slot.id)


def _add_fb542543(game, battle, who: dict[str, str]):
    def fn(b):
        for name, side in who.items():
            battle_instance.join_faction(b, name, side, 300.0, power=100.0, scores=dict(SCORES))
    return game.world.mutate_siege(battle.record_id, fn)


def _start_fb542543(game, battle):
    game.now = battle.muster_deadline_real + 1
    game._tick_siege(battle)
    return _now(game, battle)


def _squad_fb542543(battle):
    return next(c for c in battle.commanders if c.fid.startswith("squad:"))


def _round_fb542543(game, battle, moves: dict[str, str], setup=None, texts: dict[str, tuple[str, int]] | None = None):
    d = game._definition_of(battle)
    log: dict[str, list[str]] = {}

    def fn(b):
        if setup is not None:
            setup(b)
        for name, move in moves.items():
            tag = next(o.tag for o in battle_instance.fixed_options(b, d, name) if o.move == move)
            battle_instance.submit_action(b, name, tag)
        for name, (text, rate) in (texts or {}).items():
            tag = next(o.tag for o in battle_instance.options_for(b, d, name) if o.free_text)
            battle_instance.submit_action(b, name, tag, text, rate)
        log["msgs"] = game._advance_battle_round(b, d)

    after = game.world.mutate_siege(battle.record_id, fn)
    return after, log.get("msgs", [])


def _big(b):
    """守將的池子加大，這一回合打掉的量一眼看得出來。"""
    g = _squad_fb542543(b)
    g.neili_cap = g.neili = 1000.0


def _melee():
    """三方混戰開打（官甲、黃乙）；回（game, battle）。"""
    game = _game_fb542543()
    return game, _start_fb542543(game, _add_fb542543(game, _open_fb542543(game), {"甲": "guan", "乙": "huang"}))


def _lone():
    """裁決 23：只有官軍到場，轉回單方攻中立地（守將站黃巾那一格）；回（game, battle）。"""
    game = _game_fb542543()
    battle = _start_fb542543(game, _add_fb542543(game, _open_fb542543(game), {"甲": "guan", "丙": "guan"}))
    assert not battle_instance.melee(battle) and battle.siege.guard_side == "huang"
    return game, battle


def _single():
    """官軍單方攻南陽官道（merged 空）：守將站黃巾那一格。"""
    game = _game_fb542543()
    battle = _add_fb542543(game, _open_fb542543(game, merged=(), side="guan"), {"甲": "guan", "丙": "guan"})
    battle = _start_fb542543(game, battle)
    assert not battle_instance.melee(battle) and battle.siege.guard_side == "huang"
    return game, battle


def _gamble_hits(game, battle, text, who="甲"):
    """who 這一回合放手一搏（成功率 100、風險 0）寫 text，其餘人固守；回守將這一回合掉的氣血。"""
    others = {n: "固守" for n, p in battle.participants.items() if n != who and p.faction != GUARD}
    after, _ = _round_fb542543(game, battle, others, setup=_big, texts={who: (text, 100)})
    return 1000.0 - _squad_fb542543(after).neili


# ── FB-542 ──

NAMED = [
    "一槍直取劫道響馬的咽喉",  # 修前：只當沒點名
    "劫道響馬",
    "先斬劫道響馬，再取寨門",
    "一槍直取劫道響馬（守將）的咽喉",  # 原本就認
]


NOT_NAMED = [
    "先斬響馬頭目",  # 只是隊伍名的一部分
    "響馬",
    "劫道",
    "馬",  # 一個字
    "劫",
    "殺出一條血路",  # 沒點名
]


@pytest.mark.parametrize("build", [_melee, _lone, _single])
@pytest.mark.parametrize("text", NAMED)
def test_naming_the_guard_by_its_own_name_hits_the_guard(build, text):
    game, battle = build()
    hp = _gamble_hits(game, battle, text)
    want = game.content.config.battle.generals.hit_base * 1000.0  # 成功率 100：風險 0，打掉 hit_base
    assert hp == pytest.approx(want), f"{text}：守將應該被點名打到"


@pytest.mark.slow  # 單一條超過一秒（2026-10-27 測試整理 4 量的）
@pytest.mark.parametrize("build", [_melee, _lone])
@pytest.mark.parametrize("text", NOT_NAMED)
def test_not_naming_the_guard_does_not_hit_the_guard(build, text):
    game, battle = build()
    assert _gamble_hits(game, battle, text) == pytest.approx(0.0)  # 沒點名：推戰線，守將的池子不動


def test_find_commander_takes_the_squad_name_and_the_full_name():
    game, battle = _melee()
    d = game._definition_of(battle)
    guard = _squad_fb542543(battle)
    assert guard.name == f"{SQUAD}（守將）"
    for text in NAMED:
        assert battle_instance.find_commander(battle, d, "甲", text) is guard
        assert battle_instance.find_commander(battle, d, "乙", text) is guard  # 兩軍都點得到他
    for text in NOT_NAMED:
        assert battle_instance.find_commander(battle, d, "甲", text) is None


def test_target_line_describes_the_guard_when_named_by_its_own_name():
    game, battle = _melee()
    d = game._definition_of(battle)
    tuning = game.content.config.battle
    line = battle_instance.target_line(battle, d, "甲", "一槍直取劫道響馬的咽喉", tuning)
    assert SQUAD in line and "守軍" in line and "主將" in line  # 給模型評成功率的那一行也要有
    assert battle_instance.target_line(battle, d, "甲", "先斬響馬頭目", tuning) == ""


def test_a_name_that_is_part_of_another_persons_name_is_not_the_guard():
    """同一邊的人名字裡含著隊伍名（甲方的「劫道響馬王」）：文字寫他，不當成點名守將；find_target 點不到同一邊的人。"""
    game = _game_fb542543()
    battle = _start_fb542543(game, _add_fb542543(game, _open_fb542543(game), {"甲": "guan", "乙": "huang", "劫道響馬王": "guan"}))  # 集結時才報得了名
    assert "劫道響馬王" in battle.participants
    d = game._definition_of(battle)
    assert battle_instance.find_target(battle, d, "甲", "迎面撞上劫道響馬王") is None  # 同一邊
    assert battle_instance.find_commander(battle, d, "甲", "迎面撞上劫道響馬王") is None
    assert battle_instance.find_commander(battle, d, "甲", "迎面撞上劫道響馬王，一槍直取劫道響馬") is not None  # 另外還寫了守將
    # 對面的人名字含著隊伍名：由 find_target 先認走（參戰者優先），輪不到守將
    assert battle_instance.find_target(battle, d, "乙", "迎面撞上劫道響馬王").name == "劫道響馬王"


def test_other_commanders_keep_their_whole_name_rule():
    """決戰的上陣人物沒有「（守將）」後綴：照原本整個名字比，一個字都不放寬。"""
    game, battle = _melee()
    d = game._definition_of(battle)
    guard = _squad_fb542543(battle)
    guard.name, guard.fid = "皇甫嵩", "figure:huangfu"
    assert battle_instance.find_commander(battle, d, "甲", "直取皇甫嵩") is guard
    assert battle_instance.find_commander(battle, d, "甲", "直取皇甫") is None
    assert battle_instance.find_commander(battle, d, "甲", "直取嵩") is None


# ── FB-543 ──

def _single_hilltop(attacker="huang", guard="guan"):
    them = _game_fb542543(attacker, "甲一", loc=PLACE_fb542543)
    slot = announce(them, PLACE_fb542543, attacker)
    w = them.state.world
    slot.muster_at, slot.at, slot.status = w.time, w.time + 1800, "waiting"
    them._save_season()
    siege.open_waiting(them.world, them.content, NOW)
    them.state.world = them.world.get_season()
    battle = next(b for b in them.world.get_sieges() if b.siege.slot_id == slot.id)
    assert battle.siege.holder is None and battle.siege.guard_side == guard
    return them, battle


def _begin(game, battle, trend=50):
    definition = game._definition_of(battle)

    def _go(b):
        battle_instance.close_muster(b, definition, random.Random(0), NOW)
        b.trend = trend

    return game.world.mutate_siege(battle.record_id, _go)


def _scene(game, battle):
    return game._battle_scene_text(_now(game, battle), game._definition_of(battle))


@pytest.mark.parametrize(("attacker", "guard"), [("huang", "guan"), ("guan", "huang")])
def test_the_other_army_watching_does_not_read_the_guards_order_as_its_own(attacker, guard):
    them, battle = _single_hilltop(attacker, guard)
    watcher = _game_fb542543(guard, "乙二", world=them.world, loc=PLACE_fb542543)  # 守將那一格是他陣營的 id，人沒參戰
    them.choose(f"battle:join:{attacker}")
    battle = _begin(them, battle)
    assert battle_instance.order_text(battle, guard, them.content.config.battle)  # 守將有喊令（規則照舊：守將照令出招，助守的人看得到）
    watcher.now = them.now
    scene = _scene(watcher, battle)
    assert "傳令" not in scene and "照令出招" not in scene  # 修前「荒丘刀客（守將）傳令：強攻（照令出招，份量多 15%）」
    assert "荒丘刀客（守將）" in scene  # 陣容那一行照舊看得到守將
    assert "插不上手" in scene  # 場景照舊說明自己這邊插不上手


def test_a_helper_of_the_guard_still_reads_the_order_and_the_attacker_is_unchanged():
    them, battle = _single_hilltop()
    ranger = _game_fb542543(None, "散六", world=them.world, loc=PLACE_fb542543)
    ranger.choose("battle:enlist:guan")  # 助守
    them.choose("battle:join:huang")
    battle = _begin(them, battle)
    ranger.now = them.now
    assert "傳令" in _scene(ranger, battle)  # 助守的人站守將那一格：令是他的（他的鈕也寫主將令）
    assert "傳令" not in _scene(them, battle)  # 攻方這一邊沒有人物，沒有令可寫


def test_an_unaligned_watcher_reads_no_order_either():
    them, battle = _single_hilltop()
    ranger = _game_fb542543(None, "散六", world=them.world, loc=PLACE_fb542543)
    them.choose("battle:join:huang")
    battle = _begin(them, battle)
    ranger.now = them.now
    assert "傳令" not in _scene(ranger, battle)


def test_the_absent_army_arriving_late_after_the_turn_back_reads_no_order():
    """裁決 23 轉回單方攻中立地後，沒到場那一軍（守將站它那一格）晚來的人，場景上也不能看到守將的令。"""
    game, battle = _lone()
    late = _game_fb542543("huang", "黃晚", world=game.world)
    late.now = game.now
    scene = late._battle_scene_text(_now(game, battle), late._definition_of(battle))
    assert "傳令" not in scene and "插不上手" in scene


# ── 原 test_conquest_fb552_siege_state.py（整檔搬進來） ──
# FB-552（PM 2026-10-20，輿圖第 1 批 QA 開的，領地爭奪第二批就有）：攻城集結的那半小時，站在那一塊，出陣那一行不能寫錯攻城在哪一步。
#
# 第二批（投票、22:00 公告）時的寫法是「只有今天公告、還沒開打的推得動，其餘寫今天沒有公告攻城」，這一支原本鎖的是那一版的字。
# 翻地與爭搶（dev/flip-1，PM 2026-10-20 第 1、2 條）之後投票與公告拿掉了：沒有排攻城的塊隨時推得動；第 4 階下了戰書，那一塊凍結到那一場
# 打完或作罷（conquest.frozen）。所以照翻地改字（收尾，2026-10-21）：凍結的那一段，推不動的原因照那一場在哪一步寫（conquest.FROZEN_WHY，
# push_problem 照 _step）——已下戰書（還沒開集結）、集結中（去加入攻城）、開打中；打完、作罷就解凍，照常推得動。列與記同一個判斷：那一行寫
# 推不動，出陣就真的推不動（sortie_progress 是 0）。自家的守那一句也一樣照實寫，不接「有人來攻時守拉的量…」。關著的季一個字都不變。

FROZEN = (("planned", "planned", conquest.WHY_FROZEN), ("open", "muster", conquest.WHY_MUSTER),
          ("open", "fight", conquest.WHY_FIGHTING))


def _note(game, loc_id):
    return game._sortie_line(game.content.locations[loc_id])  # 行動列底下出陣那一行（action_notes 的 act:train）


def _put(game, slot, status, phase):
    """把這一場放在某一步：open 的集結中是世界時間還沒到開打、開打中是過了開打的時刻。"""
    slot.status = status
    w = game.state.world
    w.time = slot.at - 60 if phase == "muster" else slot.at + 60 if phase == "fight" else w.time


def test_state_of_a_block_follows_the_slot():
    game = conquest_game("season21")
    w = game.state.world
    assert conquest.siege_state(w, "nanyang_road") is None  # 沒排過
    slot = announce(game, "nanyang_road", "huang")
    assert conquest.siege_state(w, "nanyang_road") == "planned"
    slot.status = "waiting"
    assert conquest.siege_state(w, "nanyang_road") == "planned"  # 到了開集結的時候、還沒開
    slot.status = "open"
    assert conquest.siege_state(w, "nanyang_road") == "muster"
    w.time = slot.at + 1
    assert conquest.siege_state(w, "nanyang_road") == "fight"
    slot.status = "done"
    assert conquest.siege_state(w, "nanyang_road") == "done"
    slot.status = "void"
    assert conquest.siege_state(w, "nanyang_road") == "void"
    assert conquest.siege_state(w, "hilltop_wilds") is None  # 別的塊不受影響


def test_attack_line_says_where_the_siege_is():
    game = go(join(conquest_game("season21"), "huang"), "nanyang_road")
    assert howto.SORTIE_PROGRESS in _note(game, "nanyang_road")  # 沒排攻城：隨時推得動
    slot = announce(game, "nanyang_road", "huang")  # 戰書排了一場：凍結
    for status, phase, why in FROZEN:
        _put(game, slot, status, phase)
        note = _note(game, "nanyang_road")
        assert howto.SORTIE_BLOCKED.format(why=why) in note, (status, phase)
        assert game.sortie_progress("nanyang_road") == 0.0  # 列與記：寫推不動就真的推不動
    for status in ("done", "void"):  # 打完（這裡沒易手：輸了砍半另算）、作罷：解凍
        _put(game, slot, status, "")
        assert howto.SORTIE_PROGRESS in _note(game, "nanyang_road"), status
        assert game.sortie_progress("nanyang_road") > 0


def test_own_block_under_siege_says_the_same_in_the_hold_line():
    """自家的區塊被下了戰書（守）：凍結的那一段照實寫在哪一步，不接「有人來攻時守拉的量…」（攻城已經排了）；打完照常守得動。"""
    game = go(join(conquest_game("season21"), "guan"), "yingchuan_wilds")
    assert howto.SORTIE_BLOCKED_HOLD.format(why=conquest.WHY_IDLE, half="一半") in _note(game, "yingchuan_wilds")  # 沒人推：照舊
    press(game, "yingchuan_wilds", "huang")
    assert howto.SORTIE_HOLD_PROGRESS in _note(game, "yingchuan_wilds")  # 黃巾在推：守得動
    slot = announce(game, "yingchuan_wilds", "huang")
    for status, phase, why in FROZEN:
        _put(game, slot, status, phase)
        note = _note(game, "yingchuan_wilds")
        assert note.startswith("這裡是自家地盤：不用打，") and "拿自家隊伍" in note, (status, phase)
        assert howto.SORTIE_BLOCKED.format(why=why) in note and "有人來攻時" not in note, (status, phase)
        assert game.sortie_progress("yingchuan_wilds") == 0.0
    _put(game, slot, "done", "")
    assert howto.SORTIE_HOLD_PROGRESS in _note(game, "yingchuan_wilds")


def test_another_block_is_not_dragged_along():
    """站在沒排攻城的另一塊，不因為別處有一場在集結而改字。"""
    game = go(join(conquest_game("season21"), "huang"), "hilltop_wilds")
    slot = announce(game, "nanyang_road", "huang")
    _put(game, slot, "open", "muster")
    note = _note(game, "hilltop_wilds")
    assert not any(why in note for why in conquest.FROZEN_WHY.values())


def test_the_base_keeps_its_line():
    """大本營（搶不下來）的字不動。"""
    game = go(join(conquest_game("season21"), "guan"), "changshe")
    assert "沒有進度可推" in _note(game, "changshe")


# ── 原 test_conquest_fb566.py（整檔搬進來） ──
# FB-566（領地爭奪小單 QA 開的，`97567ff0` 就有）：同一個大區兩場攻城同時集結，排在前面的那一場自己站不進去時，自己站得進去的那一場
# 沒有加入鈕。重現：官軍攻嵩山深處、黃巾攻荒丘（都是中立地、同一刻開集結），黃巾的人站在荒丘：`_joinable()` 是黃巾那一場，`_battle_now`
# 卻回排第一的官軍那一場——選單沒有 `battle:` 鈕、場景寫「插不上手」，那一場最後作罷。修法：`_battle_now` 先照自己站得進去的那一場。
#
# 合進區塊表 v3（輿圖第三版第 2 批）之後嵩山深處是官軍的、黃巾開季碰不到荒丘：換成官軍攻荒丘、黃巾攻汝南荒野（都是中立地、同一個大區），斷言不動。

def _two_sieges(side: str, loc: str):
    game = go(join(conquest_game("season21"), side), loc)
    game.now = NOW
    w = game.state.world
    for slot in (announce(game, "hilltop_wilds", "guan", minute=20 * 60), announce(game, "runan_wilds", "huang", minute=20 * 60)):
        slot.muster_at, slot.at, slot.status = w.time, w.time + 1800, "waiting"
    game._save_season()
    siege.open_waiting(game.world, game.content, NOW)
    game.state.world = game.world.get_season()
    return game


@pytest.mark.parametrize(("side", "loc", "target"), [("huang", "runan_wilds", "runan_wilds"), ("guan", "hilltop_wilds", "hilltop_wilds")])
def test_the_siege_you_can_join_is_the_one_you_see(side, loc, target):
    game = _two_sieges(side, loc)
    sieges = game.world.get_sieges()
    assert [b.siege.loc for b in sieges] == ["hilltop_wilds", "runan_wilds"]  # 官軍那一場排在前面
    assert [b.siege.loc for b in game._joinable()] == [target]
    assert game._battle_now().siege.loc == target  # 修前黃巾的人看到的是官軍那一場
    joins = [o for o in game.options() if o.id.startswith(f"battle:join:{side}")]
    assert joins and joins[0].enabled
    assert "插不上手" not in game.scene_text()
    game.choose(joins[0].id)
    joined = next(b for b in game.world.get_sieges() if b.siege.loc == target)
    assert game.state.player.name in joined.participants


# ── 原 test_conquest_fb605_frozen_defend.py（整檔搬進來） ──
# FB-605（flip-1 收尾開發回報，PM 2026-10-21 給號；QA 驗輿圖第三版第 1 批照樣重現）：自家那一塊被戰書凍結時，守城卡寫「此刻沒有可守的」。
#
# 翻地之後守城軍令只認「自家被推得最高、守得動」的那幾塊（orders.defend_places → conquest.focus_blocks(…, "defend")），被戰書凍結的那一塊
# push_problem 回凍結的原因、守不動，所以不列——可是那一塊正等著一場攻城，正是最該守的地方。PM 定的修法：凍結的那一塊照樣列進守城
# （列與記同一個判斷），在那一場攻城戰站守方、守方守住時記一次（orders.SIEGE_GUARD）；在那裡出陣守、按守勢行動不算（守不動進度）。

def _game_fb605frozend(name: str = "沈浪", world=None):
    """黃巾的人站在汝南（黃巾開季的陣營區塊）；官軍在那裡推到 60、下了戰書（announce：排進時程表＝那一塊被凍結）。開季的軍令清掉，
    只剩一道黃巾潁川汝南的守城。"""
    game = go(join(conquest_game("season21", name=name, world=world), "huang"), "runan")
    game.now = NOW
    if world is not None:
        game.state.world = world.get_season()
    return game


def _setup(game):
    s, c = game.state, game.content
    s.world.orders.clear()
    order = Order(id="t:huang:defend", template="defend", faction="huang", week=orders.period_of(s, c), front="yingru",
                  quota=99, text="（測試）")
    s.world.orders.append(order)
    press(game, "runan", "guan", 60)
    slot = announce(game, "runan", "guan")
    return order, slot


def _open_fb605frozend(game, slot):
    w = game.state.world
    slot.muster_at, slot.at, slot.status = w.time, w.time + 1800, "waiting"
    game._save_season()
    siege.open_waiting(game.world, game.content, NOW)
    game.state.world = game.world.get_season()


def _end_fb605frozend(game, trend):
    battle = next(b for b in game.world.get_sieges() if b.phase != "ended")

    def _close(b):
        b.phase, b.trend, b.end_time = "ended", trend, game.state.world.time

    game._apply_battle_outcome(game.world.mutate_siege(battle.record_id, _close))
    game.state.world = game.world.get_season()


def _order(game) -> Order:
    return next(o for o in game.state.world.orders if o.id == "t:huang:defend")


def test_a_frozen_own_block_is_listed_for_defend_on_the_card_map_and_bots():
    game = _game_fb605frozend()
    order, _ = _setup(game)
    c, w = game.content, game.state.world
    assert conquest.push_problem(w, c, "huang", "runan", "hold") == conquest.WHY_FROZEN  # 守不動進度（規則沒變）
    assert orders.defend_places(c, w, order) == ["runan"]  # 修前是空的
    text = atlas.order_how(game.state, c, order)
    assert text != atlas.DEFEND_NONE_CONQUEST.format(front=atlas.trend_name(c, "yingru"))  # 修前「此刻沒有…沒有可守的」
    assert text == atlas.DEFEND_SIEGE_CONQUEST.format(where="汝南")
    assert mapdata._order_marks(game.state, c, "huang").get("runan") == mapdata.ORDER_WORDS["defend"]
    assert "runan" in orders.targets(game.state, c, "huang")


def test_on_the_frozen_block_only_the_siege_guard_counts():
    """列與記同一個判斷：凍結的那一塊在清單上，記的是攻城戰守住；在那裡出陣守、按守勢行動不算（守不動），別的守城地方反過來只認那兩種。"""
    game = _game_fb605frozend()
    order, _ = _setup(game)
    c, w = game.content, game.state.world
    press(game, "runan_academy", "guan", 10)  # 另一塊自家的地方被推：照舊是出陣守、守勢行動的地方
    assert orders.defend_places(c, w, order) == ["runan", "runan_academy"]

    def counts(kind, loc):
        return orders._counts(c, order, kind, loc, None, None, None, None, None, w)

    assert counts(orders.SIEGE_GUARD, "runan") and not counts("duty", "runan")
    assert counts("duty", "runan_academy") and not counts(orders.SIEGE_GUARD, "runan_academy")
    assert not orders.duty_counts(game.state, c, "huang", "runan") and orders.duty_counts(game.state, c, "huang", "runan_academy")
    text = atlas.order_how(game.state, c, order)
    assert "汝南學宮" in text and "汝南正等著一場攻城" in text


def test_a_hold_sortie_on_the_frozen_block_does_not_count():
    game = _game_fb605frozend()
    order, _ = _setup(game)
    game.choose("act:train")  # 自家的區塊：出陣・守（凍結，推不動）
    assert _order(game).progress == {}


def test_defenders_who_hold_the_siege_get_one_credit_each():
    game = _game_fb605frozend()
    order, slot = _setup(game)
    other = _game_fb605frozend(name="張角徒", world=game.world)  # 同一邊、沒去打的人
    _open_fb605frozend(game, slot)
    game.choose(next(o.id for o in game.options() if o.id.startswith("battle:join:huang")))
    _end_fb605frozend(game, 10)  # 戰局往黃巾（守方）那一邊：守住
    w, c = game.state.world, game.content
    assert conquest.holder(w, c, "runan") == "huang" and conquest.frozen(w, "runan") is None
    assert _order(game).progress == {"沈浪": 1}  # 修前沒有記：卡上寫沒有可守的、攻城戰也不記
    assert "張角徒" not in _order(game).progress
    assert other.state.player.name == "張角徒"


def test_no_credit_when_the_block_falls():
    game = _game_fb605frozend()
    order, slot = _setup(game)
    _open_fb605frozend(game, slot)
    game.choose(next(o.id for o in game.options() if o.id.startswith("battle:join:huang")))
    _end_fb605frozend(game, 90)  # 官軍拿下
    w, c = game.state.world, game.content
    assert conquest.holder(w, c, "runan") == "guan"
    assert _order(game).progress == {}


def test_a_ranger_helping_the_defence_is_not_credited():
    """臨時投效、助守的散人只算這一場：不記軍令（他沒有陣營，也不能記到黃巾的軍令上）。"""
    game = _game_fb605frozend()
    order, slot = _setup(game)
    ranger = go(join(conquest_game("season21", name="浪人", world=game.world), None), "runan")
    ranger.now = NOW
    _open_fb605frozend(game, slot)
    ranger.state.world = ranger.world.get_season()
    joins = [o.id for o in ranger.options() if o.id.startswith("battle:") and "huang" in o.id and o.enabled]
    assert joins, [o.id for o in ranger.options() if o.id.startswith("battle:")]
    ranger.choose(joins[0])
    _end_fb605frozend(game, 10)
    assert "浪人" not in _order(game).progress


# ── 原 test_conquest_fb609_letter_route.py（整檔搬進來） ──
# FB-609（QA 驗輿圖第三版第 1 批）：玩家下戰書的 API 被管理者的同名動作蓋掉，沒有一個玩家下得了戰書。
#
# server.MAIN_ACTIONS 與 ADMIN_ACTIONS 都有 conquest_letter（玩家的 Game.conquest_letter、管理者的「立刻下戰書」），/api/do/{op} 先查
# ADMIN_ACTIONS：在任第 4 階的玩家打 POST /api/do/conquest_letter 回 400「只有管理者能這麼做。」。修法（PM 2026-10-21）：管理者那一個改名
# admin_conquest_letter（同 Game.admin_conquest_letter），兩張表不准重名。
#
# 伺服器用正式內容的 21 天季、打開領地爭奪，自己的一份（不碰別的測試的 server.CONTENT）。

ADMIN = "掌門"


PLAYER = "沈青衫"


# /api/do 在查 MAIN_ACTIONS 之前先接走的那幾個（server.api_do）：管理者的動作也不能叫這幾個名字
SPECIAL_OPS = {"battle_text", "seal_text", "duel_text", "tavern_ask", "feast_text", "gather_text"}


@pytest.fixture(autouse=True)
def conquest_server(monkeypatch):
    content = conquest_rules(real_content("season21"))
    content.config.auto_open_first_season = True
    content.config.admins = [ADMIN]
    monkeypatch.setattr(server, "CONTENT", content)
    monkeypatch.setattr(accounts, "SCRYPT_PARAMS", {"n": 2, "r": 1, "p": 1, "dklen": 32})  # 這裡測的不是密碼
    monkeypatch.setattr(server, "_breaker_until", None, raising=False)
    for store in (server.LOGIN_FAILURES, server.SESSIONS, server.GAMES):
        store.clear()
    yield content
    for store in (server.LOGIN_FAILURES, server.SESSIONS, server.GAMES):
        store.clear()


def _player(client):
    client.post("/api/register", json={"login": "shen_01", "password": "secret-pw", "again": "secret-pw"})
    client.post("/api/character", json={"name": PLAYER})
    client.post("/api/do/skip_tutorial", json={})
    return server.game_for(PLAYER)


def _seated_rank4(content):
    """存檔裡的這個玩家改成官軍、站在荒丘、這一週在任的第 4 階；官軍在荒丘的進度推到戰書的門檻。"""
    state = open_characters().load(PLAYER)
    p = state.player
    p.faction, p.location, p.journey, p.qualified = "guan", "hilltop_wilds", None, True
    p.visited.add("hilltop_wilds")
    open_characters().save(state)
    game = server.game_for(PLAYER)

    def _season(s):
        s.seats["guan"] = [PLAYER]
        conquest.push(s, content, "hilltop_wilds", "guan", "先鋒", content.config.conquest.letter_at, "attack")

    game.world.mutate_season(_season)


def _admin(client):
    boss = server.open_game(ADMIN)
    open_characters().save(boss.state)
    store = server.account_store()
    store.register("boss", "secret-pw")
    store.bind_character("boss", ADMIN)
    client.post("/api/login", json={"login": "boss", "password": "secret-pw"})
    return server.game_for(ADMIN)


@pytest.mark.slow  # 單一條超過一秒（2026-10-27 測試整理 4 量的）
def test_a_seated_rank4_player_letters_through_the_route(conquest_server):
    client = TestClient(server.app)
    _player(client)
    _seated_rank4(conquest_server)
    out = client.post("/api/do/conquest_letter", json={"loc": "hilltop_wilds"})
    assert out.status_code == 200, out.json()  # 修前 400「只有管理者能這麼做。」
    assert "下了戰書" in out.json()["message"]
    season = server.game_for(PLAYER).world.get_season()
    (slot,) = season.conquest.schedule
    assert (slot.loc, slot.attackers, slot.reasons) == ("hilltop_wilds", ["guan"], {"guan": PLAYER})


def test_the_admin_letter_has_its_own_name_and_players_are_refused(conquest_server):
    player = TestClient(server.app)
    _player(player)
    refused = player.post("/api/do/admin_conquest_letter", json={"id": "runan_wilds", "side": "huang"})
    assert refused.status_code == 400 and refused.json() == {"error": "只有管理者能這麼做。"}
    boss = TestClient(server.app)
    _admin(boss)
    done = boss.post("/api/do/admin_conquest_letter", json={"id": "runan_wilds", "side": "huang"})
    assert done.status_code == 200, done.json()
    assert "汝南荒野" in done.json()["message"]
    (slot,) = server.game_for(ADMIN).world.get_season().conquest.schedule
    assert (slot.loc, slot.attackers) == ("runan_wilds", ["huang"])


def test_player_and_admin_action_names_never_collide():
    """/api/do 先查管理者那一張：同名的玩家動作永遠走不到（FB-609）。兩張表、以及 api_do 先接走的那幾個，名字都不能重。
    功能包的管理者工具（server.FEATURE_ADMIN_ACTIONS，開發規範手冊 3.3 的 admin_tools）又排在這些前面、最先查，一樣不能跟它們重。"""
    assert set(server.MAIN_ACTIONS) & set(server.ADMIN_ACTIONS) == set()
    assert set(server.ADMIN_ACTIONS) & SPECIAL_OPS == set()
    assert set(server.MAIN_ACTIONS) & SPECIAL_OPS == set()
    tools = set(server.FEATURE_ADMIN_ACTIONS)
    assert "mall_reissue" in tools  # 讀到了（商城那三樣）
    assert tools & (set(server.MAIN_ACTIONS) | set(server.ADMIN_ACTIONS) | SPECIAL_OPS) == set()
    assert "admin_conquest_letter" in server.ADMIN_ACTIONS and "conquest_letter" in server.MAIN_ACTIONS


# ── 原 test_conquest_void_quiet.py（整檔搬進來） ──
# 領地爭奪第二批：攻方沒人到、這一場攻城作罷時不發天下大事（PM 裁決，第二批開發回報第 3 點；計畫第八章裁決 19）。
#
# 人少的服每天空轉一場，天下大事就多一句「一個人都沒到」，洗版（反目標 2）。作罷只記在時程表（那一場 void）與當天的 day_log
# （一筆 void="absent"）；公告卡照常寫「作罷」。有人參戰的照舊發。

def _game_voidquiet(side, loc="nanyang_road"):
    game = go(join(conquest_game("season21"), side), loc)
    game.now = NOW
    return game


def _open_voidquiet(game, slot):
    """把這一場排到此刻開集結（半小時後開打），照 world 的路開（同 test_conquest_siege._open）。"""
    w = game.state.world
    slot.muster_at, slot.at, slot.status = w.time, w.time + 1800, "waiting"
    game._save_season()
    siege.open_waiting(game.world, game.content, NOW)
    game.state.world = game.world.get_season()
    return game.world.get_sieges()[0]


def _close_muster(game):
    game.now = NOW + 1801  # 集結截止
    game._battle_status(tick=True)
    game.state.world = game.world.get_season()


def _world_rumors(game) -> list[str]:
    return [r.text for r in game.world.get_season().rumors if r.layer == "world"]


def test_nobody_came_posts_no_world_news():
    game = _game_voidquiet("guan")  # 官軍的人在場、黃巾一個人都沒來
    slot = announce(game, "nanyang_road", "huang")
    battle = _open_voidquiet(game, slot)
    before = _world_rumors(game)
    _close_muster(game)
    ended = game.world.ended_battle(battle.record_id)
    assert ended is not None and ended.unfinished and ended.siege.void == "absent"
    assert _world_rumors(game) == before  # 修前多一句「攻城・南陽官道：黃巾軍一個人都沒到，這一仗作罷。」


def test_nobody_came_is_kept_in_the_schedule_and_the_day_log():
    game = _game_voidquiet("guan")
    slot = announce(game, "nanyang_road", "huang")
    _open_voidquiet(game, slot)
    _close_muster(game)
    state = game.state.world.conquest
    found = next(s for s in state.schedule if s.id == slot.id)
    assert found.status == "void"
    notes = [n for n in state.day_log if n.void]
    assert len(notes) == 1  # 修前 day_log 沒有這一筆
    note = notes[0]
    assert (note.key, note.side, note.loc, note.minute, note.void) == (slot.key, "huang", "nanyang_road", slot.minute, "absent")
    card = next(row for row in game.conquest_view()["today"] if row["id"] == slot.id)  # 公告卡照常寫
    assert card["status"] == "void" and card["status_text"] == SIEGE_STATUS["void"]


def test_a_merged_siege_nobody_came_notes_each_side():
    game = _game_voidquiet("guan", "nanyang_road")
    slot = announce(game, "nanyang_road", "huang", merged=("guan", "huang"))
    battle = _open_voidquiet(game, slot)
    before = _world_rumors(game)
    _close_muster(game)
    assert game.world.ended_battle(battle.record_id).siege.void == "absent"
    assert _world_rumors(game) == before
    notes = [n for n in game.state.world.conquest.day_log if n.void]
    assert sorted(n.side for n in notes) == ["guan", "huang"]


def test_somebody_came_still_posts_the_result():
    game = _game_voidquiet("huang")
    slot = announce(game, "nanyang_road", "huang")
    battle = _open_voidquiet(game, slot)
    game.choose(next(o.id for o in game.options() if o.id.startswith("battle:join:huang")))
    game.world.mutate_siege(battle.record_id, lambda b: setattr(b.participants[game.state.player.name], "acted_rounds", 5))
    _close_muster(game)
    assert game.world.ended_battle(battle.record_id) is None  # 有人到：照常開打，不作罷
    before = _world_rumors(game)

    def _close(b):
        b.phase, b.trend, b.end_time = "ended", 10, game.state.world.time  # 黃巾大勝

    after = game.world.mutate_siege(battle.record_id, _close)
    game._apply_battle_outcome(after)
    news = _world_rumors(game)[len(before):]
    assert any("南陽官道落入" in text for text in news)
    assert not [n for n in game.world.get_season().conquest.day_log if n.void]
