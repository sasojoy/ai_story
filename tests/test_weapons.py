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


# ── Task 3：加成乘進威力、一門打不遍 ──

from tianxia import team  # noqa: E402
from tianxia.state import Weapon  # noqa: E402


def _on(content):
    content.config.weapons.enabled = True
    return content


def _blade(kind="劍", attribute="柔", tier=1, quality="下品", edge=100):
    return Weapon(id="兵:1", name="試刃", kind=kind, attribute=attribute, tier=tier, quality=quality, edge=edge)


def _game(content, world, art="sword"):
    import random
    from tianxia import rules
    from tianxia.engine import Game
    game = Game.new(content, "試劍", rng=random.Random(0), world=world)
    game.client = None
    rules.learn_skill(game.state, content, art)
    return game


def test_bonus_adds_tier_quality_and_match(content, world):
    _on(content)
    sword = team.resolve_art("sword", content, world)  # 流雲劍：柔
    assert weapons.bonus(_blade(attribute="柔"), sword, content, world) == pytest.approx(0.05 + 0.05)
    assert weapons.bonus(_blade(attribute="剛"), sword, content, world) == pytest.approx(0.0)  # 剛剋柔：0.05−0.05
    assert weapons.bonus(_blade(attribute="快", tier=3, quality="上品"), sword, content, world) == pytest.approx(0.19)


def test_bonus_is_zero_when_kind_differs_or_off(content, world):
    sword = team.resolve_art("sword", content, world)
    assert weapons.bonus(_blade(), sword, content, world) == 0.0  # 開關關著
    _on(content)
    assert weapons.bonus(_blade(kind="刀"), sword, content, world) == 0.0
    assert weapons.bonus(None, sword, content, world) == 0.0
    assert weapons.bonus(_blade(), None, content, world) == 0.0


def test_edge_scales_the_bonus_down_to_half(content, world):
    _on(content)
    sword = team.resolve_art("sword", content, world)
    full = weapons.bonus(_blade(attribute="快"), sword, content, world)
    assert weapons.bonus(_blade(attribute="快", edge=0), sword, content, world) == pytest.approx(full * 0.5)
    assert weapons.bonus(_blade(attribute="快", edge=50), sword, content, world) == pytest.approx(full * 0.75)


def test_player_boost_multiplies_the_weapon(content, world):
    _on(content)
    game = _game(content, world)
    before = team.player_boost(game.state, content, world).factor
    game.state.player.weapon = _blade(attribute="快")
    assert team.player_boost(game.state, content, world).factor == pytest.approx(before * 1.05)


def test_bonus_follows_the_worn_art(content, world):
    _on(content)
    game = _game(content, world)
    game.state.player.weapon = _blade(attribute="快")
    from tianxia import rules
    rules.learn_skill(game.state, content, "fist")  # 換上拳腳：劍用不上
    if game.state.player.member.wugong_id != "fist":
        team.switch_art(game.state, content, world, "fist")
    assert game.state.player.member.wugong_id == "fist"
    wugong = team.player_art(game.state, content, world, "fist")
    neigong = team.player_art(game.state, content, world, game.state.player.member.neigong_id)
    assert team.player_boost(game.state, content, world).factor == pytest.approx(
        team.pairing(content, wugong, neigong) * team.resonance(game.state, content, wugong)
        * team.resonance(game.state, content, neigong)
    )


def test_style_factor_is_softer_than_the_art_one(content, world):
    from tianxia.styles import Style
    _on(content)
    sword = team.resolve_art("sword", content, world)
    assert weapons.style_factor(_blade(attribute="快"), sword, content, world, Style("快", "慢")) == pytest.approx(1.1)
    assert weapons.style_factor(_blade(attribute="慢"), sword, content, world, Style("快", "慢")) == pytest.approx(0.9)
    assert weapons.style_factor(_blade(attribute="剛"), sword, content, world, Style("快", "慢")) == 1.0
    assert weapons.style_factor(_blade(kind="刀", attribute="快"), sword, content, world, Style("快", "慢")) == 1.0
    assert weapons.style_factor(_blade(attribute="快"), sword, content, world, None) == 1.0


def test_styled_fighters_multiplies_the_weapon_into_the_player_only(content, world, monkeypatch):
    from tianxia import styles
    from tianxia.styles import Style
    _on(content)
    game = _game(content, world)
    squad = next(iter(content.squads.values()))
    arts = team.team_arts(game.state, content, world)
    base = team._styled_fighters(game.state, content, world, arts, squad)[2]
    game.state.player.weapon = _blade(attribute="快")
    monkeypatch.setattr(styles, "style_of", lambda *a, **k: Style("快", "慢"))
    boosts = team._styled_fighters(game.state, content, world, arts, squad)[2]
    # 身上武學流雲劍（柔）不在路數裡，所以變的只有兵器：本人 ×1.05（加成）×1.1（路數）
    assert boosts[0].factor == pytest.approx(base[0].factor * 1.05 * 1.1)
    assert [b.factor for b in boosts[1:]] == [b.factor for b in base[1:]]
    monkeypatch.setattr(styles, "style_of", lambda *a, **k: None)
    off = team._styled_fighters(game.state, content, world, arts, squad)[2]
    assert off[0].factor == pytest.approx(base[0].factor * 1.05)



# ── Task 4：打仗會鈍 ──

def _new_state(content, world, name):
    import random
    from tianxia.engine import Game
    return Game.new(content, name, rng=random.Random(0), world=world).state


def test_wear_by_tier_and_warn_once(content, world):
    _on(content)
    state = _new_state(content, world, "鈍刀")
    state.player.weapon = _blade(edge=35)
    assert weapons.wear(state, content, "大勝") == []
    assert state.player.weapon.edge == 33
    msgs = weapons.wear(state, content, "落敗")
    assert state.player.weapon.edge == 28 and msgs == [weapons.EDGE_WARNING.format(name="試刃")]
    assert weapons.wear(state, content, "僵持") == []  # 只提醒一次
    assert state.player.weapon.edge == 25
    state.player.weapon.edge = 1
    weapons.wear(state, content, "落敗")
    assert state.player.weapon.edge == 0


def test_wear_does_nothing_without_weapon_or_switch(content, world):
    state = _new_state(content, world, "空手")
    _on(content)
    assert weapons.wear(state, content, "落敗") == []
    content.config.weapons.enabled = False
    state.player.weapon = _blade()
    assert weapons.wear(state, content, "落敗") == [] and state.player.weapon.edge == 100  # 開關關著


def test_training_fight_wears_the_blade_and_the_reminder_reaches_the_journal(content, world):
    _on(content)
    game = _game(content, world)
    game.state.player.weapon = _blade(edge=31)
    game.state.player.location = "lake"
    game.state.player.stamina = 100.0
    game.sync(0.0)
    game.choose("act:train")
    assert game.state.player.weapon.edge < 31
    record = game.state.battles[-1]
    assert record.kind == "train"
    assert weapons.EDGE_WARNING.format(name="試刃") in record.notes  # 戰鬥卡片
    assert any(weapons.EDGE_WARNING.format(name="試刃") in line for line in game.state.journal[0].lines)  # 江湖紀錄


def test_file_battle_skips_event_fights(content, world):
    _on(content)
    game = _game(content, world)
    game.state.player.weapon = _blade()
    from tianxia.state import BattleRecord
    record = BattleRecord(id=1, time=0.0, location="湖邊", kind="event", event="劇情", opponent="誰", ours=[],
                          tier="落敗", our_power=1.0, difficulty=1.0)
    game._file_battle(record)
    assert game.state.player.weapon.edge == 100
    record = record.model_copy(update={"id": 2, "kind": "wild"})
    game._file_battle(record)
    assert game.state.player.weapon.edge == 95
