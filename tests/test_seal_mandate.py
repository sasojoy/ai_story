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
    assert battle.timetable_event == "tianming" and battle.region == "jizhou" and battle.third.faction == "haoqiang"
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

    root = Path(__file__).resolve().parent.parent
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
