"""療傷只在醫館（企劃者 2026-10-12「療傷我認為不能隨地療傷，應該去城鎮有醫館的地方」；tianxia/clinic.py）。
測試內容把 Config.heal_at_clinic 關著，這裡用正式內容。"""

import random
from pathlib import Path

import pytest

from tianxia import atlas, bot, clinic, skillview, team
from tianxia.content import ContentError, load_content, validate
from tianxia.engine import Game

CONTENT_DIR = Path(__file__).parent.parent / "content"


@pytest.fixture(scope="module")
def real():
    content = load_content(CONTENT_DIR)
    content.config.auto_open_first_season = True
    return content


def _game(real, where="yingchuan", injury=40.0, silver=100):
    game = Game.new(real, "甲", rng=random.Random(0), graduated=True)
    p = game.state.player
    p.location, p.journey = where, None
    p.member.injury, p.member.neili = injury, 50.0
    p.stats["silver"] = silver
    return game


def test_every_region_has_a_clinic_and_the_first_stop_out_of_the_prologue_is_one(real):
    places = clinic.clinics(real)
    assert {atlas.region_of(real, loc).id for loc in places} == {region.id for region in real.map.regions}
    assert real.scenario.start_location in places


def test_away_from_a_clinic_healing_is_refused_and_names_the_nearest(real):
    game = _game(real, where="yingshui")  # 潁水河畔：隔壁就是潁川郡
    p = game.state.player
    assert game.heal() == ["這裡沒有醫館，最近的在潁川郡（陽翟）。"]
    assert (p.member.injury, p.stats["silver"]) == (40.0, 100)
    assert skillview.heal_button(game.state, real) == {
        "ok": False, "why": "這裡沒有醫館，最近的在潁川郡（陽翟）。", "clinic": "這裡沒有醫館，最近的在潁川郡（陽翟）。",
    }
    assert "act:heal" not in [o.id for o in game.options(odds=False)]


def test_no_injury_says_so_before_the_clinic(real):
    game = _game(real, where="yingshui", injury=0.0)
    assert game.heal() == ["氣血無恙，不用療傷。"]


def test_on_the_road_there_is_no_clinic(real):
    game = _game(real)
    game.choose("move:yingshui")
    assert game.state.player.journey is not None
    assert not clinic.here(game.state, real) and game.heal()[0].startswith("這裡沒有醫館")


def test_at_a_clinic_the_place_offers_healing_at_the_same_price(real):
    game = _game(real)
    p = game.state.player
    (option,) = [o for o in game.options(odds=False) if o.id == "act:heal"]
    assert option.enabled and option.label == f"{clinic.HEAL}（內傷 40・{team.heal_cost(real, p.member)} 兩）"
    assert skillview.heal_button(game.state, real) == {"ok": True, "why": None, "clinic": None}
    stamina = p.stamina
    msgs = game.choose("act:heal")
    assert "療傷完畢，內傷 -40、氣血回滿（銀兩 -20）。" in msgs
    assert (p.member.injury, p.member.neili, p.stats["silver"], p.stamina) == (0.0, None, 80, stamina)
    assert game.state.journal[0].title == "療傷・潁川郡（陽翟）"
    assert "act:heal" not in [o.id for o in game.options(odds=False)]  # 沒有內傷就不畫


def test_too_poor_to_heal_greys_the_option(real):
    game = _game(real, silver=3)
    (option,) = [o for o in game.options(odds=False) if o.id == "act:heal"]
    assert not option.enabled and "銀兩不足" in option.label


def test_time_and_meditation_never_cure_the_injury(real):
    game = _game(real, where="yingshui")
    game.advance(12 * 3600)
    member = game.state.player.member
    assert member.injury == 40.0
    _, cap = team.member_neili(real, member, team.con_of(game.state, real, game.world, "player"))
    assert team.member_neili(real, member, team.con_of(game.state, real, game.world, "player"))[0] == cap - 40.0


def test_with_the_switch_off_healing_works_anywhere(real):
    off = real.model_copy(update={"config": real.config.model_copy(update={"heal_at_clinic": False})})
    game = _game(off, where="yingshui")
    assert game.heal()[0].startswith("療傷完畢")


def test_a_clinic_is_required_when_the_switch_is_on(real):
    bare = real.model_copy(deep=True)
    for loc in bare.locations.values():
        loc.tags = [tag for tag in loc.tags if tag != clinic.CLINIC_TAG]
    with pytest.raises(ContentError, match="醫館"):
        validate(bare)


def test_bots_detour_to_the_nearest_clinic_when_the_injury_is_heavy(real):
    game = _game(real, where="yingshui", injury=10.0)
    assert bot.clinic_hop(game) is None  # 輕傷：不繞路
    game.state.player.member.injury = 100.0
    assert bot.clinic_hop(game) == "yingchuan"
    game.state.player.stats["silver"] = 0
    assert bot.clinic_hop(game) is None  # 付不起：去了也白去
    game = _game(real, injury=100.0)
    assert bot.clinic_hop(game) is None and bot.wants_heal(game)  # 已經在醫館：就地療傷
