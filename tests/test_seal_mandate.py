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
