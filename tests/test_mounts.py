"""坐騎（docs/superpowers/specs/2026-10-10-裝備四欄-design.md 第五節；計畫 docs/superpowers/plans/2026-10-11-裝備-2-坐騎.md）。"""
from __future__ import annotations

import random

import pytest

from conftest import next_season, real_content, walk_to
from tianxia import atlas, encounter, equipment, mounts, rules
from tianxia.characters import CharacterStore
from tianxia.engine import Game
from tianxia.state import Equipment, GameState, Journey, Tagalong


def _on(content):
    """打開坐騎（測試內容三欄都關著）。"""
    content.config.mounts.enabled = True
    return content


def _horse(tier=1, quality="下品", edge=100, hid="騎:1", name="棗騮馬"):
    return Equipment(id=hid, slot="mount", name=name, tier=tier, quality=quality, edge=edge)


def _game(content, world, name="騎客", at="town", stamina=100.0, silver=200, horse=None):
    """坐騎開著的一個角色，同步過了才擺好：人在 at、體力、銀兩、身上那匹。測試內容：小鎮—湖邊 3 分鐘路程，趕路每分鐘 1 點、疾行 2 點。"""
    _on(content)
    game = Game.new(content, name, rng=random.Random(0), world=world)
    game.client = None
    game.sync(0.0)
    p = game.state.player
    p.location, p.stamina, p.stats["silver"], p.mount = at, stamina, silver, horse
    return game


def _ids(game):
    return {o.id: o for o in game.options(odds=False)}


# ── Task 1：資料形狀與數字 ──

def test_the_mount_slot_is_on_by_its_own_switch(content):
    assert not equipment.on(content, "mount")  # 測試內容關著（設計 2.6）
    _on(content)
    slot = equipment.SLOTS["mount"]
    assert equipment.on(content, "mount") and (slot.prefix, slot.label, slot.road_locked) == ("騎", "坐騎", True)
    assert "mount" in equipment.WIELDABLE and "mount" not in equipment.DISMANTLABLE  # 坐騎能換、不能拆（4.8）
    assert not equipment.SLOTS["weapon"].road_locked and not equipment.SLOTS["armor"].road_locked


def test_a_horse_saves_stamina_speeds_the_road_and_counts_how_fed_it_is(content, state):
    """設計 5.1：省體力 25／40／55%、路上快 30／45／60%（品質中 +3、上 +5 個百分點只加這兩列）、騎兵 5／10／15%、脫身 30／50／70%，
    全部乘飽足係數（0.5＋0.5×飽足度／100）；腳力＝省體力×飽足係數。"""
    _on(content)
    p = state.player

    def numbers():
        return (mounts.saving(state, content), mounts.pace(state, content), mounts.cavalry(state, content), mounts.escape(state, content))

    assert numbers() == (0.0, 1.0, 0.0, 0.0)  # 沒騎馬
    p.mount = _horse()
    assert numbers() == pytest.approx((0.25, 0.70, 0.05, 0.30))
    p.mount.edge = 50  # 飽足係數 0.75
    assert numbers() == pytest.approx((0.1875, 0.775, 0.0375, 0.225))
    p.mount.edge = 0  # 餓到底剩一半
    assert numbers() == pytest.approx((0.125, 0.85, 0.025, 0.15))
    p.mount = _horse(tier=2, quality="中品")  # 品質只加省體力、路上快
    assert numbers() == pytest.approx((0.43, 0.52, 0.10, 0.50))
    p.mount = _horse(tier=3, quality="上品")  # 最好的名駒上品省 60%、快 65%
    assert numbers() == pytest.approx((0.60, 0.35, 0.15, 0.70))
    content.config.mounts.enabled = False  # 開關關著：騎著也當沒騎
    assert numbers() == (0.0, 1.0, 0.0, 0.0)


def test_horse_names_and_grades_are_original(content):
    from tianxia import naming
    names = [mounts.horse_name(coat, tier) for coat in mounts.COATS for tier in (1, 2)]
    first = mounts.COATS[0]
    assert len(set(names)) == 12 and names[:2] == [first + mounts.NOUNS[1], first + mounts.NOUNS[2]]  # 毛色＋馬／駒（5.6；字待 joy 潤，不寫死）
    real = real_content()
    assert not [n for n in names if naming.name_problem(n, real, None)]
    taken = {s.name for s in real.skills.values()} | {m.name for m in real.materials.values()} | {ch.name for ch in real.characters.values()}
    assert not set(names) & taken
    assert mounts.grade(_horse()) == f"{mounts.TIER_NAMES[1]}・下品"
    assert mounts.grade(_horse(tier=2, quality="中品")) == f"{mounts.TIER_NAMES[2]}・中品"
    assert mounts.name_of(_horse(name="青驄駒")) == "青驄駒"


def test_odds_text_rounds_half_up_and_says_under_one_tenth():
    assert [mounts.tenths(x) for x in (0.25, 0.15, 0.24, 0.04)] == [3, 2, 2, 0]  # .5 進位（round(2.5) 會給 2）
    assert mounts.odds_text(0.25) == "約 3 成" and mounts.odds_text(0.04) == "不到一成"
    # 百分比也是 .5 進位：f"{x:.0%}" 跟 round 一樣把 .5 捨到偶數（餓到底的駑馬省 12.5% 會寫成 12%、騎兵 2.5% 寫成 2%）
    assert [mounts.pct(x) for x in (0.125, 0.025, 0.225, 0.2, 0.43)] == ["13%", "3%", "23%", "20%", "43%"]


def test_old_save_from_equipment_batch_one_reads_on_foot_with_a_plain_pace(content, world):
    """裝備四欄 3.2、5.3：裝備一的舊存檔（沒有 mount、hunger_warned、picking_market，路上的 Journey 沒有 pace）讀得進來，
    沒騎馬、步調 1，已經排好的抵達時刻照舊。"""
    game = Game.new(content, "舊檔", rng=random.Random(0), world=world)
    game.state.player.journey = Journey(mode="walk", path=["lake"], arrive_at=[180.0])
    raw = game.state.model_dump()
    for key in ("mount", "hunger_warned", "picking_market"):
        raw["player"].pop(key)
    raw["player"]["journey"].pop("pace")
    loaded = GameState.model_validate(raw).player
    assert loaded.mount is None and loaded.hunger_warned is False and loaded.picking_market is False
    assert loaded.journey.pace == 1.0 and loaded.journey.arrive_at == [180.0]


def test_a_new_season_starts_on_foot(content, world):
    game = _game(content, world, horse=_horse())
    p = game.state.player
    p.rack, p.hunger_warned = [_horse(hid="騎:2", name="青驄馬")], True
    next_season(content, world, game)
    p = game.state.player
    assert p.mount is None and p.rack == [] and not p.hunger_warned and not p.picking_market  # 新欄位跟著新角色重來（2.4）


def test_a_mount_cannot_be_changed_on_the_road_but_can_in_seclusion(content, world):
    """設計 2.3：路上不能換坐騎（快慢出發時就算進抵達時刻，換了也不會變快），閉關中照樣能換；換上不花體力。"""
    game = _game(content, world, horse=_horse())
    p = game.state.player
    p.rack = [_horse(hid="騎:2", name="青驄駒", tier=2)]
    game.choose("move:lake")
    assert p.journey is not None
    assert game.wield_weapon("騎:2") == [equipment.ROAD_LOCKED.format(label="坐騎")] and p.mount.id == "騎:1"
    p.journey = None  # 到了（省掉等）
    p.busy_until = game.state.world.time + 3600.0  # 閉關中
    stamina = p.stamina
    assert game.wield_weapon("騎:2") == [equipment.WIELDED.format(name="青驄駒")] and p.mount.id == "騎:2" and p.stamina == stamina
    assert [m.id for m in p.rack] == ["騎:1"]
