"""兵器（docs/superpowers/specs/2026-10-09-兵器-design.md，第一批：拿著就有用）。"""
from __future__ import annotations

import pytest

from conftest import real_content
from tianxia import weapons
from tianxia.martial_arts import MartialArt
from tianxia.models import WEAPON_KINDS


def test_every_real_wugong_has_a_weapon_kind_and_neigong_has_none():
    c = real_content()
    for skill in c.skills.values():
        if skill.kind == "武學":
            assert skill.weapon in WEAPON_KINDS, skill.id
        else:
            assert skill.weapon is None, skill.id


@pytest.mark.parametrize("skill_id,kind", [
    ("guanyu_wugong", "刀"), ("liubei_wugong", "劍"), ("zhangfei_wugong", "槍"),
    ("lishi_chui", "棍"), ("qiangnu", "弓弩"), ("jichu_quanjiao", "拳腳"), ("zhuifeng", "拳腳"),
])
def test_real_wugong_kinds_follow_the_spec_table(skill_id, kind):
    assert real_content().skills[skill_id].weapon == kind


def test_art_weapon_reads_content_and_none_for_neigong(content, world):
    assert weapons.art_weapon("sword", content, world) == "劍"
    assert weapons.art_weapon("breath", content, world) is None
    assert weapons.art_weapon(None, content, world) is None
    assert weapons.art_weapon("no_such_art", content, world) is None


def _fused(art_id, base=None, parents=()):
    return MartialArt(id=art_id, name=art_id, kind="武學", quality="下品", attribute="剛", base_power=10, top_power=20,
                      origin="fused", base=base, parents=list(parents))


def test_fused_art_inherits_weapon_kind(content, world, monkeypatch):
    registered = {
        "f1": _fused("f1", base="sword"),
        "f2": _fused("f2", base="f1"),
        "b1": _fused("b1", parents=["fist", "sword"]),
        "old": _fused("old"),
    }
    monkeypatch.setattr(world, "get_skill", lambda art_id: registered.get(art_id))
    assert weapons.art_weapon("f1", content, world) == "劍"
    assert weapons.art_weapon("f2", content, world) == "劍"
    assert weapons.art_weapon("b1", content, world) in ("拳腳", "劍")
    assert weapons.art_weapon("b1", content, world) == weapons.art_weapon("b1", content, world)
    assert weapons.art_weapon("old", content, world) is None


# ── Task 2：兵器的資料、設定與存檔 ──

def test_old_save_without_weapon_fields_loads(content, world):
    import random
    from tianxia.engine import Game
    from tianxia.state import GameState
    game = Game.new(content, "舊檔", rng=random.Random(0), world=world)
    raw = game.state.model_dump()
    for key in ("weapon", "rack", "weapon_serial", "picking_smith", "edge_warned"):
        raw["player"].pop(key, None)
    loaded = GameState.model_validate(raw)
    assert loaded.player.weapon is None and loaded.player.rack == [] and loaded.player.weapon_serial == 0


def test_weapon_round_trips_through_json():
    from tianxia.state import Weapon
    w = Weapon(id="兵:1", name="厚背刀", kind="刀", attribute="剛", tier=1, quality="下品")
    assert Weapon.model_validate_json(w.model_dump_json()) == w
    assert w.edge == 100 and w.tempers == 0


def test_fixture_turns_weapons_off_and_real_content_on(content):
    assert content.config.weapons.enabled is False
    assert real_content().config.weapons.enabled is True
