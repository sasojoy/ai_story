"""玉璽碎片第二批：天命之季與天命之爭（docs/superpowers/specs/2026-10-11-玉璽碎片-design.md 第八節；
計畫 docs/superpowers/plans/2026-10-13-玉璽-2-天命之爭.md）。"""
from __future__ import annotations

import random

import pytest

from conftest import real_content
from test_seal import SALT, _ended, _registry, seal_problems, sealed  # noqa: F401  sealed 是夾具
from test_seal_engine import _admin, _player
from tianxia import seal
from tianxia.engine import Game
from tianxia import atlas, fusion, seal, social


def install_mandate(content):
    """sealed 的內容再加天命之爭：時刻表一件 tianming（mandate_only、第 12 週週一 20:00）與它的 BattleDef（照長社複製、北區打、
    守方黃巾），劇本兩個天命結局（標 mandate，排在最後也不當保底）。"""
    from tianxia.models import Ending, TimetableEvent, TimetableOutcome

    content.battles["tianming"] = content.battles["changshe_fire"].model_copy(
        update={"id": "tianming", "name": "天命之爭", "timetable_event": "tianming", "defender": "huang", "front": "jizhou"},
    )
    content.mandate_timetable = [TimetableEvent(
        id="tianming", week=12, front="jizhou", title="天命之爭", kind="showdown", mandate_only=True, weekday=0, hour=20,
        mandate_endings={"guan": "s1_tianming_guan", "huang": "s1_tianming_huang"},
        outcomes={f"{side}:{m}": TimetableOutcome(text=f"天命之爭，{side}{m}。", chronicle=f"天命之爭{side}{m}。")
                  for side in ("guan", "huang") for m in ("大勝", "險勝")},
    )]
    content.scenario.endings += [
        Ending(id="s1_tianming_guan", title="漢室重光", text="天命歸漢。", season_one=True, mandate=True),
        Ending(id="s1_tianming_huang", title="黃天當立", text="天命歸於黃天。", season_one=True, mandate=True),
    ]
    return content


@pytest.fixture
def mandated(sealed):
    install_mandate(sealed)
    assert seal_problems(sealed) == []
    return sealed


def _opened(content, world):
    world.seed_first_season(content)
    if world.season_phase() == "preparing":
        world.open_season(content, 0.0)


def _all_emerged(content, world, **held):
    """七片這一輪都現世過：held 的那幾片有主（since_season 0），其餘隱沒。"""
    reg = _registry(content, **held)
    for shard in reg.shards.values():
        shard.emerged_round = reg.round
        if shard.state == "hidden":
            shard.state = "sunk"
    world.mutate(lambda st: setattr(st, "seal", reg))
    return reg


def _mandate_now(world):
    """把這一季直接當成天命之季（不經過蓋章：只測季的規則時用）。"""
    def _apply(st):
        st.season.mandate = True
        st.seal.mandate_season = st.season_number
    world.mutate(_apply)


# ── Task 1：內容與資料形狀 ──────────────────────────────


def test_the_real_content_keeps_tianming_out_of_the_twelve():
    """8.3、8.5（要 PM 定的第 1 條）：天命之爭寫在 timetable.json，載入時分到 mandate_timetable；一般的時刻表照舊 12 件。
    它有自己的決戰（冀州、官軍對黃巾、豪強第三方）與兩個天命結局（漢室重光、黃天當立，標 mandate）。"""
    c = real_content()
    assert len(c.timetable) == 12 and all(not e.mandate_only for e in c.timetable)
    (event,) = c.mandate_timetable
    assert (event.id, event.week, event.weekday, event.hour, event.kind, event.seal) == ("tianming", 12, 0, 20, "showdown", None)
    battle = c.battles["tianming"]
    assert battle.timetable_event == "tianming" and battle.region == "jizhou" and "third" not in battle.model_fields_set
    endings = {e.id: e for e in c.scenario.endings}
    assert {endings[i].title for i in event.mandate_endings.values()} == {"漢室重光", "黃天當立"}
    assert all(endings[i].mandate and endings[i].season_one for i in event.mandate_endings.values())
    assert set(event.mandate_endings) == {"guan", "huang"}  # PM 戊：豪強不能得天命


def test_the_mandate_numbers_are_the_defaults():
    from tianxia.models import SealTuning

    m = SealTuning().mandate
    assert (m.start_shift, m.start_shift_cap, m.holder_weight, m.fame, m.pay_scale, m.decisive_from_week, m.recall_battles) == (
        3, 12, 1.2, 10, 2, 13, 2)


@pytest.mark.parametrize("change, message", [
    (lambda c: c.mandate_timetable.append(c.mandate_timetable[0].model_copy(update={"id": "tianming2"})), "最多一件"),
    (lambda c: setattr(c.mandate_timetable[0], "seal", "stir"), "不能標 seal"),
    (lambda c: c.mandate_timetable[0].mandate_endings.update(haoqiang="s1_tianming_guan"), "交戰兩軍"),
    (lambda c: c.mandate_timetable[0].mandate_endings.update(guan="nope"), "標了 mandate"),
    (lambda c: c.battles.pop("tianming"), "battles.json"),
    (lambda c: c.scenario.endings.append(c.scenario.endings[-1].model_copy(update={"id": "stray"})), "沒有天命之爭指到它"),
])
def test_a_bad_mandate_setup_is_refused_at_load(mandated, change, message):
    change(mandated)
    assert any(message in p for p in seal_problems(mandated)), seal_problems(mandated)


def test_old_saves_read_without_the_new_fields():
    """舊存檔：新欄位都有預設值（不升版）；登記記一筆時寫上這一輪。"""
    from tianxia.battle_instance import BattleInstance
    from tianxia.state import WorldState
    from tianxia.world_state import SealEvent, SealRegistry

    assert (WorldState().mandate, WorldState().mandate_result) == (False, None)
    reg = SealRegistry.model_validate({"round": 2, "history": [{"seq": 1, "season": 3, "kind": "emerge"}]})
    assert (reg.mandate_season, reg.mandate_pending, reg.history[0].round, reg.history[0].holders) == (None, False, None, {})
    assert seal.log(reg, 4, "recall", shard="chishou").round == 2
    assert SealEvent(seq=9, season=1, kind="scatter").kind == "scatter"
    assert BattleInstance(battle_id="x").seal_lean == {}


@pytest.mark.smoke
def test_mandate_endings_stay_out_of_the_normal_list(mandated, world):
    """天命結局只由 evaluate_ending 照 mandate_endings 挑（Task 6），不進一般的清單：任務區塊的提示、決定性勝利、保底都看不到它們。"""
    from tianxia import world as world_rules

    state = Game.new(mandated, "路人", rng=random.Random(0), world=world).state
    assert all(not e.mandate for e in world_rules.season_endings(state, mandated))
    assert not world_rules.evaluate_ending(state, mandated).mandate


# ── Task 2：時刻表 ──────────────────────────────


def test_tianming_shows_up_only_in_a_mandate_season(mandated):
    """要 PM 定的第 1 條：timetable.events 在蓋了章的季才排進天命之爭（同一週排在季末之前）；find 照 id 兩份都找。"""
    from tianxia import timetable
    from tianxia.state import WorldState

    assert timetable.events(WorldState(), mandated) is mandated.timetable
    ids = [e.id for e in timetable.events(WorldState(mandate=True), mandated)]
    assert ids[-2:] == ["tianming", "xiaquyang"] and ids.index("tianming") > ids.index("wancheng")
    assert timetable.find(mandated, "tianming").mandate_only and timetable.find(mandated, "wancheng").kind == "showdown"


def test_tianming_defaults_to_monday_eight_pm_of_week_twelve(mandated):
    from tianxia import calendar, timetable
    from tianxia.state import WorldState
    from tianxia.world_state import stamp_season

    season = WorldState(storyline=mandated.scenario.storylines[0].id)
    stamp_season(season, mandated)
    at = timetable.default_time(timetable.find(mandated, "tianming"), mandated, season)
    assert calendar.point_text(calendar.point(at + 1, mandated, season)) == "第 12 週・週一 20:00"  # +1：避開浮點落在 19:59
    assert "tianming" not in season.schedule  # 一般季的預設排程不排它（蓋章時才排）


def test_tianming_comes_due_and_lists_only_in_a_mandate_season(mandated, world):
    """到期（due_showdowns → 開集結）、管理者「立刻開戰」與「三場大戲」、時刻表那幾列，都只在天命之季看得到天命之爭。"""
    from tianxia import timetable
    from tianxia import world as world_rules
    from tianxia.world import _season_vehicle

    _opened(mandated, world)
    admin = _admin(mandated, world)

    def _late(st):
        st.season.time = timetable.default_time(timetable.find(mandated, "tianming"), mandated, st.season) + 1

    world.mutate(_late)
    admin.state.world = world.get_season()  # 不 sync：sync 會補算季、把到期的大事都結算掉，這裡只看清單
    vehicle = _season_vehicle(mandated, world.get_season())
    assert "tianming" not in [e.id for e in timetable.due_showdowns(vehicle, mandated)]
    assert "tianming" not in [b.id for b in admin.admin_battles()]
    assert "tianming" not in [r["id"] for r in timetable.status_rows(vehicle, mandated)]
    assert any("沒有這件大事" in m for m in admin.admin_resolve_event("tianming", "guan:大勝"))  # 一般季直接送 id 也定不了
    assert world_rules.open_showdown(world, mandated, "tianming", 0.0) == [] and world.get_battle() is None  # 也開不了
    _mandate_now(world)
    admin.state.world = world.get_season()
    vehicle = _season_vehicle(mandated, world.get_season())
    assert "tianming" in [e.id for e in timetable.due_showdowns(vehicle, mandated)]
    assert "tianming" in [r["id"] for r in timetable.status_rows(vehicle, mandated)]
    assert "tianming" in [e.id for e, _ in admin.admin_showdowns()]


def test_only_the_gatekeepers_read_the_mandate_timetable():
    """要 PM 定的第 1 條的守門：content.mandate_timetable 只准 timetable.py、seal.py、content.py、models.py 讀；
    其他地方要看得到天命之爭一律走 timetable.events（照這一季的章）或 timetable.find。"""
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    allowed = {"tianxia/timetable.py", "tianxia/seal.py", "tianxia/content.py", "tianxia/models.py"}
    hits = [
        f"{p.relative_to(root).as_posix()}:{n}" for p in [*root.glob("tianxia/*.py"), root / "server.py"]
        for n, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1)
        if "mandate_timetable" in line and p.relative_to(root).as_posix() not in allowed
    ]
    assert hits == []


# ── Task 3：蓋章與散去 ──────────────────────────────


def test_a_season_after_all_seven_emerged_is_stamped_the_season_of_the_mandate(mandated, world):
    """8.1（PM 己）：七片這一輪都現世過（有主的、隱沒的都算），換季時新的一季蓋上天命之季的章：WorldState.mandate、登記記下季別、
    天命之爭排在第 12 週週一 20:00；天下大事與江湖史各一句。"""
    from conftest import next_season
    from tianxia import calendar

    _opened(mandated, world)
    _all_emerged(mandated, world, chishou="甲", xuanniu="乙")
    next_season(mandated, world)
    season, view = world.get_season(), world.seal_state()
    assert season.mandate and season.mandate_result is None
    assert view.registry.mandate_season == view.season and not view.registry.mandate_pending
    assert calendar.point_text(calendar.point(season.schedule["tianming"] + 1, mandated, season)) == "第 12 週・週一 20:00"
    text = seal.MANDATE_OPEN.format(battle="天命之爭")
    assert any(r.text == text for r in season.rumors if r.layer == "world") and any(r.text == text for r in season.chronicle)


def test_one_shard_never_seen_keeps_the_mandate_away(mandated, world):
    from conftest import next_season

    _opened(mandated, world)
    reg = _all_emerged(mandated, world, chishou="甲")
    reg.shards["guixin"].state, reg.shards["guixin"].emerged_round = "hidden", None
    world.mutate(lambda st: setattr(st, "seal", reg))
    next_season(mandated, world)
    assert not world.get_season().mandate and not world.seal_state().registry.mandate_pending


def test_a_season_without_the_season_one_stamp_defers_the_mandate(mandated, world):
    """8.1：新的一季沒蓋第一季規則的章（沒有時刻表決戰），天命之季延到下一個有蓋章的季（mandate_pending）。"""
    from conftest import next_season

    _opened(mandated, world)
    _all_emerged(mandated, world, chishou="甲")
    mandated.config.season_one = False
    next_season(mandated, world)
    assert not world.get_season().mandate and world.seal_state().registry.mandate_pending
    mandated.config.season_one = True
    next_season(mandated, world)
    assert world.get_season().mandate and not world.seal_state().registry.mandate_pending


def test_the_season_after_the_mandate_scatters_all_seven(mandated, world):
    """8.4：天命之季之後的換季，七片全部回到未現世（不判隱沒）、round +1；舊持有者同步時補一句、抄本清掉；江湖史七格只列這一輪。"""
    from conftest import next_season

    _opened(mandated, world)
    holder = _player(mandated, world, "甲")
    _all_emerged(mandated, world, chishou="甲")
    next_season(mandated, world)  # 第 2 季：天命之季
    next_season(mandated, world)  # 第 3 季：七片散去
    view = world.seal_state()
    assert view.registry.round == 2 and not world.get_season().mandate
    assert all(s.state == "hidden" and s.holder is None and s.emerged_round is None for s in view.registry.shards.values())
    assert any(e.kind == "scatter" and e.other == "甲" for e in view.registry.history)
    assert not any(e.kind == "sink" for e in view.registry.history)
    holder.sync(500.0)
    assert holder.state.player.heirloom is None
    assert any(seal.SCATTER_MINE.format(shard="螭首") in e.lines for e in holder.state.journal)
    block = seal.chronicle_block(mandated, view.registry)
    assert block.startswith(seal.BOOK_ROUND.format(round=2)) and "甲懷中" not in block and "不知所蹤" not in block


# ── Task 4：天命之季的規則 ──────────────────────────────


def test_the_mandate_season_stirs_one_shard_every_marked_battle(sealed):
    """8.2（PM 丙）：天命之季每場標了 seal 的決戰必定牽動一片——不擲 7%、沒有新主保護、沒有全服兩次的上限；每片每季照舊最多一次；
    亂數 seal-mandate|event_id。"""
    reg = _registry(sealed, chishou="甲", xuanniu="乙", yunzhuan="丙")
    for shard in reg.shards.values():
        shard.since_season = 5  # 這一季才到手：一般季有新主保護
    assert seal.roll_stir(reg, sealed, 5, 0, "changshe_fire") is None
    assert seal.roll_stir(reg, sealed, 5, 0, "changshe_fire", mandate=True) == seal.roll_stir(reg, sealed, 5, 0, "changshe_fire", mandate=True)
    got = []
    for event in ("changshe_fire", "wancheng", "guangzong"):
        shard = seal.roll_stir(reg, sealed, 5, 0, event, mandate=True)
        reg.shards[shard].stirred_season = 5
        seal.log(reg, 5, "stir", shard=shard)
        got.append(shard)
    assert sorted(got) == ["chishou", "xuanniu", "yunzhuan"]  # 三場三片；第三場照樣動（全服兩次的上限拿掉）
    assert seal.roll_stir(reg, sealed, 5, 0, "again", mandate=True) is None  # 都動過了


def test_a_mandate_season_muster_stirs_a_new_holder_and_raises_nothing(mandated, world):
    """8.2、3.2：天命之季開集結——剛到手的那一片照樣被牽動；標 emerge 的那一場不擲現世（管理者的強制現世也不擲，記號留著）。"""
    from tianxia import world as world_rules

    _opened(mandated, world)
    reg = _all_emerged(mandated, world, chishou="甲")
    reg.shards["guixin"].state, reg.shards["guixin"].emerged_round = "hidden", None
    reg.force_emerge = "guixin"
    world.mutate(lambda st: (setattr(st, "seal", reg), setattr(st.seal.shards["chishou"], "since_season", st.season_number)))
    _mandate_now(world)
    world_rules.open_showdown(world, mandated, "wancheng", 0.0)
    battle = world.get_battle()
    assert battle.seal_shard == "chishou" and battle.seal_emerge is None
    assert world.seal_state().registry.force_emerge == "guixin"


def test_a_sunk_shard_is_recalled_at_the_first_two_marked_battles(mandated, world):
    """8.2 喚回（PM 辛）：天命之季標了 seal 的前兩場收場時，從隱沒的碎片裡喚回一片給勝方戰功前三名抽到的人；不算現世（emerged_round、
    emerge_season 不動）；亂數 seal-recall，不碰 Game.rng。"""
    _opened(mandated, world)
    _all_emerged(mandated, world, chishou="甲")
    _mandate_now(world)
    game = _player(mandated, world, "旁人")
    before = game.rng.getstate()
    battle = _ended("changshe_fire", [("官甲", "guan", 3, 3), ("黃甲", "huang", 3, 0)], record=11)
    game._seal_settle(battle, mandated.battles["changshe_fire"], {"side": "guan", "margin": "大勝"})
    view = world.seal_state()
    back = [s for s in view.registry.shards.values() if s.holder == "官甲"]
    assert len(back) == 1 and back[0].state == "held" and back[0].emerged_round == view.registry.round
    assert view.registry.emerge_season is None and game.rng.getstate() == before
    event = next(e for e in view.registry.history if e.kind == "recall")
    assert event.holder == "官甲" and event.text in [r.text for r in world.get_season().chronicle]
    winner = _player(mandated, world, "官甲", "guan")
    assert winner.state.player.heirloom is not None and any("尋回" in line for e in winner.state.journal for line in e.lines)


def test_recall_takes_the_first_two_marked_battles_of_the_real_timetable():
    assert seal.recall_events(real_content()) == ["changshe_fire", "wancheng"]


def test_the_holder_card_says_it_is_the_season_of_the_mandate(mandated, world):
    _opened(mandated, world)
    _all_emerged(mandated, world, chishou="甲")
    _mandate_now(world)
    card = _player(mandated, world, "甲").seal_view()
    assert card["state"] == seal.CARD_MANDATE and len(card["dates"]) == 3  # 長社、宛城、天命之爭


# ── Task 5：天命之爭開集結 ──────────────────────────────


def _destiny_open(content, world, **held):
    """七片都現世過（held 有主、其餘隱沒），這一季當天命之季，開天命之爭的集結。回集結公告。"""
    from tianxia import world as world_rules

    _opened(content, world)
    _all_emerged(content, world, **held)
    _mandate_now(world)
    return world_rules.open_showdown(world, content, "tianming", 0.0)


def test_the_mandate_battle_leans_toward_the_army_holding_shards(mandated, world):
    """8.3：開集結那一刻碎片在哪一軍（投靠名冊）戰局起點就往哪一軍偏，每片 3 點；豪強、散人、隱沒的不推；起點同時寫進 trend 與
    trend_start；天命之爭本身不璽動、不現世。"""
    from tianxia import world as world_rules

    _opened(mandated, world)  # 先開季再建角色（同 test_seal_engine._setup），投靠名冊記在這一季
    for name, faction in (("官一", "guan"), ("官二", "guan"), ("黃一", "huang"), ("豪一", "haoqiang"), ("散一", None)):
        _player(mandated, world, name, faction)
    base = world_rules.showdown_start(world_rules._season_vehicle(mandated, world.get_season()), mandated, mandated.battles["tianming"])
    msgs = _destiny_open(mandated, world, chishou="官一", xuanniu="官二", yunzhuan="黃一", jinjiao="豪一", chenglu="散一")
    battle = world.get_battle()
    assert battle.battle_id == "tianming" and battle.seal_lean == {"guan": 2, "huang": 1}
    assert battle.trend == battle.trend_start == base + 3
    assert battle.seal_shard is None and battle.seal_emerge is None
    text = seal.MANDATE_MUSTER.format(battle="天命之爭", lean="官軍握著2片、黃巾軍握著1片", shift="戰局起點往官軍偏了 3 點")  # FB-186
    assert any(text in m for m in msgs) and any(r.text == text for r in world.get_season().rumors)


def test_the_lean_is_capped_at_twelve_points(mandated):
    battle = mandated.battles["tianming"]
    cfg = mandated.config.seal
    assert seal.lean_shift({"guan": 6, "huang": 1}, battle, cfg) == 12
    assert seal.lean_shift({"huang": 3}, battle, cfg) == -9
    assert seal.lean_shift({"haoqiang": 7}, battle, cfg) == 0
    assert seal.lean_text({}, battle) == seal.LEAN_NONE


def test_the_lean_says_how_far_the_start_moved_fb186(mandated):
    """FB-186：起點偏了幾點、往哪一軍偏，公告與畫面都寫；偏 0 也寫一句（兩軍各有碎片就說持璽相當），不寫成「從正中開打」——
    偏移之前的起點照戰況，不一定在正中。"""
    battle = mandated.battles["tianming"]
    assert seal.shift_text(3, {"guan": 2, "huang": 1}, battle) == seal.LEAN_SHIFT.format(side="官軍", n=3) == "戰局起點往官軍偏了 3 點"
    assert seal.shift_text(-9, {"huang": 3}, battle) == seal.LEAN_SHIFT.format(side="黃巾軍", n=9)
    assert seal.shift_text(0, {"guan": 1, "huang": 1}, battle) == seal.LEAN_EVEN
    assert seal.shift_text(0, {"haoqiang": 2}, battle) == seal.shift_text(0, {}, battle) == seal.LEAN_STILL


def test_a_holder_joining_the_mandate_battle_weighs_more(mandated, world):
    """8.3：手上有碎片的人到場，份量 ×1.2（加入時算進快照；只在天命之爭）；沒有碎片的照舊。"""
    _opened(mandated, world)
    one = _player(mandated, world, "官一", "guan")
    two = _player(mandated, world, "官二", "guan")
    _destiny_open(mandated, world, chishou="官一")
    for game in (one, two):
        game.sync(10.0)
    plain_one, plain_two = one._battle_scores(), two._battle_scores()
    one.choose("battle:join:guan")
    two.choose("battle:join:guan")
    people = world.get_battle().participants
    assert people["官一"].scores == {k: round(v * 1.2, 1) for k, v in plain_one.items()}
    assert people["官二"].scores == plain_two


def test_the_mandate_battle_scene_names_who_holds_the_shards(mandated, world):
    _opened(mandated, world)
    game = _player(mandated, world, "官一", "guan")
    _destiny_open(mandated, world, chishou="官一")
    game.sync(10.0)
    assert seal.MANDATE_SCENE.format(lean="官軍握著1片", shift="戰局起點往官軍偏了 3 點", weight=seal.MANDATE_WEIGHT) in game.scene_text()  # FB-186、FB-189


# ── Task 6：天命 ──────────────────────────────


def test_winning_the_mandate_battle_rewrites_the_ending(mandated, world):
    """8.3：天命之爭打完，勝方得天命——這一季記下 mandate_result、登記記一筆 mandate（那一刻每一片在誰手上＝合璽之人）、
    天下大事與江湖史；季末的結局是 mandate_endings 那一個；合璽之人同步時補一句。"""
    from conftest import at
    from test_engine import _play_showdown

    _opened(mandated, world)
    game = _player(mandated, world, "沈浪", "guan")
    _destiny_open(mandated, world, chishou="沈浪")
    game.sync(10.0)
    _play_showdown(game, "guan_strong")
    with at(game, game.now + 1):
        game.options()
    season = world.get_season()
    assert season.mandate_result == "guan" and "tianming" in season.timeline
    event = next(e for e in world.seal_state().registry.history if e.kind == "mandate")
    assert event.result == "guan" and event.holders == {"chishou": "沈浪"}
    text = seal.MANDATE_WON.format(side="官軍") + seal.MANDATE_NAMES.format(names="沈浪")
    assert event.text == text and text in [r.text for r in season.chronicle]
    assert any(seal.MANDATE_MINE.format(shard="螭首") in e.lines for e in game.state.journal)
    _admin(mandated, world).admin_end_season(now=900.0)
    assert world.get_season().ending_id == "s1_tianming_guan"


def test_the_mandate_winners_get_double_pay_and_ten_fame(mandated, world):
    """8.3（要 PM 定的第 3 條）：得天命那一方的參戰者軍餉（銀兩、經驗）× pay_scale、名望 +fame；輸的一方照常。"""
    from tianxia.models import ShowdownPay

    mandated.config.showdown_pay = ShowdownPay()
    _opened(mandated, world)
    game = _player(mandated, world, "官甲", "guan")
    rows = [("官甲", "guan", 6, 0)]

    def paid(battle_id, side):
        battle = _ended(battle_id, rows, outcome_side=side, outcome_margin="大勝")
        before = dict(game.state.player.stats)
        changes = game._showdown_pay(battle, battle.participants["官甲"], [])
        after = game.state.player.stats
        return after.get("silver", 0) - before.get("silver", 0), after.get("fame", 0) - before.get("fame", 0), changes

    plain, _, _ = paid("changshe_fire", "guan")
    double, fame, changes = paid("tianming", "guan")
    assert double == 2 * plain and fame == 10 and "名望 +10" in changes
    lost, lost_fame, _ = paid("tianming", "huang")
    assert lost == paid("changshe_fire", "huang")[0] and lost_fame == 0


def test_a_mandate_battle_nobody_fights_leaves_the_mandate_unsettled(mandated, world):
    """8.3（要 PM 定的第 4 條）：保底收場是天命未定——時間軸記成跳過（不公告哪一方勝）、戰報標題寫天命未定、江湖史一句；結局照三方態勢。"""
    from test_engine import _settle_without_fighters
    from tianxia import timetable

    _opened(mandated, world)
    game = _player(mandated, world, "旁人")
    _destiny_open(mandated, world)
    _settle_without_fighters(game, mandated.battles["tianming"])
    season = world.get_season()
    assert season.timeline["tianming"].key == timetable.SKIPPED and season.mandate_result == ""
    assert world.get_battle().outcome_title == seal.MANDATE_UNSETTLED_TITLE
    assert seal.MANDATE_UNSETTLED.format(battle="天命之爭") in [r.text for r in season.chronicle]
    _admin(mandated, world).admin_end_season(now=900.0)
    season = world.get_season()
    assert not season.ending_id.startswith("s1_tianming")
    assert [r.text for r in season.chronicle].count(seal.MANDATE_UNSETTLED_END) == 0  # 已經寫過一次，季末不再寫


def test_a_mandate_battle_never_fought_is_unsettled_at_the_season_end(mandated, world):
    _opened(mandated, world)
    _mandate_now(world)
    _admin(mandated, world).admin_end_season(now=900.0)
    season = world.get_season()
    assert season.mandate_result == "" and seal.MANDATE_UNSETTLED_END in [r.text for r in season.chronicle]
    assert not season.ending_id.startswith("s1_tianming")


def test_the_admin_result_for_tianming_also_settles_the_mandate(mandated, world):
    _opened(mandated, world)
    _mandate_now(world)
    admin = _admin(mandated, world)
    admin.admin_resolve_event("tianming", "huang:險勝")
    assert world.get_season().mandate_result == "huang"


def test_a_normal_season_never_picks_a_mandate_ending(mandated, world):
    """沒蓋章的季就算 mandate_result 被寫了東西，結局也照舊（天命結局只在天命之季）。"""
    from tianxia import world as world_rules

    game = _player(mandated, world, "路人")
    game.state.world.mandate_result = "guan"
    assert not world_rules.evaluate_ending(game.state, mandated).mandate


def test_the_howto_fame_section_names_the_mandate_winners():
    """名望多了一條來源（得天命那一軍 +fame，玉璽二）：玩法說明「名望」那一節照 Config.seal.mandate.fame 寫（test_explain2 的守門要求）。"""
    from test_explain2 import _fame_section, _war

    c = real_content()
    c.config.seal.enabled = True
    assert seal.MANDATE_FAME.format(fame=c.config.seal.mandate.fame) in _fame_section(_war(c))


# ── Task 7：管理者 ──────────────────────────────


def test_the_admin_can_stamp_the_next_season_without_seven_shards(mandated, world):
    """第十二節「蓋天命之季」：「下一季」不看七片現世過沒；公告照自然發生寫。天命之季裡不能再按「下一季」。"""
    from conftest import next_season

    _opened(mandated, world)
    admin = _admin(mandated, world)
    admin.admin_seal_mandate("next")
    assert world.seal_state().registry.mandate_pending and admin.admin_seal_choices()["mandate"] == "next"
    next_season(mandated, world)
    assert world.get_season().mandate
    admin.sync(500.0)
    assert any("天命之季" in line for line in admin.admin_seal_mandate("next"))
    assert not world.seal_state().registry.mandate_pending


def test_the_admin_can_stamp_this_season_and_open_tianming(mandated, world):
    _opened(mandated, world)
    admin = _admin(mandated, world)
    admin.admin_seal_mandate("now")
    season = world.get_season()
    assert season.mandate and "tianming" in season.schedule and admin.state.world.mandate
    assert "tianming" in [b.id for b in admin.admin_battles()]
    admin.admin_start_battle("tianming", 50.0)
    assert world.get_battle().battle_id == "tianming"
    assert any("已經是天命之季" in line for line in admin.admin_seal_mandate("now"))


def test_the_admin_can_take_back_a_pending_stamp_and_stamp_during_the_rest(mandated, world):
    """審查 I2：「下一季」按了收得回（cancel 只清延後的記號；七片這一輪都現世過的話換季照樣蓋）；休季也按得了「下一季」與收回
    （同 FB-178：休季正是要決定下一季的時候）；「這一季立刻蓋章」照舊要季在跑。"""
    from conftest import next_season

    _opened(mandated, world)
    admin = _admin(mandated, world)
    assert any("沒有要蓋" in line for line in admin.admin_seal_mandate("cancel"))
    admin.admin_seal_mandate("next")
    admin.admin_seal_mandate("cancel")
    assert not world.seal_state().registry.mandate_pending and admin.admin_seal_choices()["mandate"] == ""
    admin.admin_end_season(now=900.0)
    assert any("沒有在進行" in line for line in admin.admin_seal_mandate("now"))
    admin.admin_seal_mandate("next")
    assert world.seal_state().registry.mandate_pending
    next_season(mandated, world)
    assert world.get_season().mandate


def test_an_admin_stamp_without_seven_emerged_announces_another_line_fb187(mandated, world):
    """FB-187：管理者蓋章（「這一季立刻蓋章」「下一季」）時七片這一輪沒有都現世過，天下大事與江湖史換 MANDATE_OPEN_EARLY
    （不寫「七片玉璽都已現世過了」，跟江湖史七格對得上；公告照舊不寫管理者）；照規則蓋的照舊 MANDATE_OPEN。"""
    from conftest import next_season

    _opened(mandated, world)
    admin = _admin(mandated, world)
    admin.admin_seal_mandate("now")
    early, plain = seal.MANDATE_OPEN_EARLY.format(battle="天命之爭"), seal.MANDATE_OPEN.format(battle="天命之爭")
    season = world.get_season()
    assert any(r.text == early for r in season.rumors) and any(r.text == early for r in season.chronicle)
    assert not any(r.text == plain for r in [*season.rumors, *season.chronicle]) and "七片" not in early
    admin.admin_end_season(now=900.0)
    next_season(mandated, world)  # 天命之季過後：散去
    admin.sync(1000.0)
    admin.admin_seal_mandate("next")
    next_season(mandated, world)
    texts = [r.text for r in world.get_season().rumors]
    assert early in texts and plain not in texts


def test_the_mandate_texts_stay_true_when_the_admin_stamps_early_fb187():
    """FB-187（審查 I1）：管理者提前蓋章時，這一輪七片可能一片都沒現世、沒人懷璽：公告不說每場大戰都會牽動碎片（沒人懷璽就牽動
    不了），時刻表前言與天命之爭的幾幕也不寫「七片玉璽都在江湖上」——照規則蓋章與提前蓋章都讀得通。"""
    c = real_content()
    assert "牽動" not in seal.MANDATE_OPEN_EARLY and "現世" not in seal.MANDATE_OPEN_EARLY
    (event,) = c.mandate_timetable
    acts = c.battles["tianming"].acts
    texts = [event.preface or "", *(a.text for a in acts), *(line for a in acts for line in a.text_by_lead.values())]
    assert texts[0] and not any("七片" in line for line in texts)


# ── 原 test_fb_batch_b.py ──

# ── FB-189：沒有人持有碎片的天命之季，決戰畫面不寫「懷璽的人到場」 ──


def test_fb189_the_holders_clause_only_shows_when_someone_holds_a_shard(mandated, world):
    from test_seal_mandate import _destiny_open, _opened
    from test_seal_mandate import _player as _mandate_player

    _opened(mandated, world)
    game = _mandate_player(mandated, world, "官一", "guan")
    _destiny_open(mandated, world)  # 第 2 輪：七片全都沒人持有
    game.sync(10.0)
    scene = game.scene_text()
    assert "天命之爭：" in scene and seal.MANDATE_WEIGHT not in scene
    assert not seal.holders(world.seal_state().registry)
